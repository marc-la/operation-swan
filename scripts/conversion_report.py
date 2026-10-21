"""Replies that convert (todo/20): what our citizen-facing writes did, per arm, and what the portal said around them.

    python scripts/conversion_report.py                       # last 24 h, from logs/ and data/ here (run it on the box)
    python scripts/conversion_report.py --split 2026-10-21T15:30   # the 24 h before against the 24 h after a deploy
    python scripts/conversion_report.py --hours 12 --out docs/06-strategy/conversion-2026-10-22.md

Reads logs/swan_actions.jsonl, logs/swan_outcomes.jsonl, logs/swan_followups.jsonl and data/portal.json (the portal's
hourly points log, kept 48 h; --activity takes a portal CSV export for longer windows). Read-only: no platform calls.

Sections: the portal's changes of mind per 100 citizen-facing writes; per arm (style, read stance, target class,
own like, second-voice delay, lever, frame...) the citizen reply rate with a 90% interval and citizen likes per write;
the portal's hourly events shared out over the writes of the 0-3 h before them (weak inference: compare arms, don't
prove effects); the light read against the regex class, and its skips by reason; the gate (LLM calls per accepted
reply, fixes, requeues, losses). It reports numbers; what to change is a human call.
"""
import argparse
import collections
import datetime as dt
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from swan_bot import config  # noqa: E402
from swan_bot.analysis import latest_by_post, parse_activity, ts_of, wilson  # noqa: E402

CITIZEN_WRITES = ("reply", "reply_back", "second_voice")
LAG_S = 3 * 3600                     # a portal event is shared over the writes of the 3 h before it
DIMS = [("style", "reply style (mirror_concede vs current)"), ("read_stance", "the light read's stance"),
        ("target_class", "regex class"), ("own_like", "one own like on the reply"),
        ("sv_delay", "second-voice delay (second voices)"), ("lever", "lever"), ("read_frame", "frame the read picked"),
        ("frame", "frame written"), ("reply_mode", "reply mode (current style)"), ("group", "todo/23 group"),
        ("arm", "todo/21 arm"), ("backend", "model"), ("act", "kind of write")]


def jsonl(path):
    out = []
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def portal_events(root, activity=None):
    """[{ts, towards, away, neither, primary_towards, neither_vaccination}] from data/portal.json (or a CSV export)."""
    if activity:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        from zoneinfo import ZoneInfo
        from import_activity import read
        rows = [dict(r, message=r.get("text", "")) for r in read(activity, ZoneInfo(config.LOCAL_TZ))]
    else:
        try:
            rows = json.loads((root / "data" / "portal.json").read_text()).get("events") or []
        except (OSError, ValueError):
            rows = []
    out = []
    for e in rows:
        if e.get("type") not in (None, "SCORE_NARRATIVE"):
            continue
        p = parse_activity(e.get("message") or "")
        msg = (e.get("message") or "").lower()
        out.append(dict(ts=ts_of(e["ts"]), towards=p["towards"], away=p["away"], neither=p["neither"],
                        primary_towards=p.get("mind_primary_towards", 0),
                        neither_vaccination=p["neither"] if "neither" in msg and "vaccination" in msg else 0))
    return out


def citizen_writes(rows, since, until):
    return [r for r in rows if r.get("act") in CITIZEN_WRITES and r.get("live") and r.get("post_id")
            and config.is_citizen(r.get("target_author")) and since <= ts_of(r["ts"]) < until]


def answered(w, outcomes, followups):
    """Did a citizen reply to this write? From the outcome reads (citizen_replies) or the follow-up (replied_to_this).
    None when neither has read it yet."""
    o, f = outcomes.get(w["post_id"]), followups.get(w["post_id"])
    if o is None and f is None:
        return None
    return bool((o or {}).get("citizen_replies")) or bool((f or {}).get("replied_to_this"))


def pct(x):
    return "–" if x is None else f"{100 * x:.0f}%"


def per100(k, n):
    return "–" if not n else f"{100 * k / n:.1f}"


def share_events(writes, events, dim):
    """{arm: {towards, away, neither}}: each portal event shared over the writes of the LAG_S before it, by count."""
    out = collections.defaultdict(lambda: collections.Counter())
    for e in events:
        win = [w for w in writes if e["ts"] - LAG_S <= ts_of(w["ts"]) < e["ts"]]
        if not win:
            continue
        for w in win:
            for k in ("towards", "away", "neither"):
                out[str(w.get(dim))][k] += e[k] / len(win)
    return out


def window_report(rows, outcomes, followups, events, since, until, title):
    writes = citizen_writes(rows, since, until)
    evs = [e for e in events if since <= e["ts"] < until + LAG_S]
    tot = {k: sum(e[k] for e in evs if since <= e["ts"] < until) for k in
           ("towards", "away", "neither", "primary_towards", "neither_vaccination")}
    n = len(writes)
    p = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%d %b %H:%M UTC")
    out = [f"## {title}: {p(since)} to {p(until)}", "",
           f"- Citizen-facing writes: **{n}** ({', '.join(f'{k} {v}' for k, v in collections.Counter(w['act'] for w in writes).most_common())}).",
           f"- Portal ({len([e for e in evs if since <= e['ts'] < until])} hourly rows): towards **{tot['towards']}** "
           f"(primary {tot['primary_towards']}), away **{tot['away']}**, neither {tot['neither']} (on vaccination "
           f"{tot['neither_vaccination']}).",
           f"- Per 100 citizen-facing writes: towards **{per100(tot['towards'], n)}**, away {per100(tot['away'], n)}, "
           f"neither {per100(tot['neither'], n)}. Goal: towards > away + neither.", ""]
    for dim, what in DIMS:
        scope = [w for w in writes if dim != "sv_delay" or w["act"] == "second_voice"]
        if dim in ("style", "read_stance", "own_like", "read_frame", "reply_mode", "lever", "group", "arm"):
            scope = [w for w in scope if w["act"] == "reply" or (dim == "style" and w["act"] == "reply_back")]
        groups = collections.defaultdict(list)
        for w in scope:
            groups[str(w.get(dim))].append(w)
        if len(groups) < 2 and dim != "style":
            continue
        shared = share_events(scope, evs, dim)
        out += [f"### {dim}: {what}", "",
                "| arm | writes | read | citizen replied [90%] | cit. likes/write | portal towards/away/neither per 100 (shared) |",
                "|---|---|---|---|---|---|"]
        for arm, ws in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            got = [a for a in (answered(w, outcomes, followups) for w in ws) if a is not None]
            rate, lo, hi = wilson(sum(got), len(got))
            likes = [outcomes[w["post_id"]].get("citizen_likes") or 0 for w in ws if w["post_id"] in outcomes]
            s, like_rate = shared.get(arm, {}), f"{sum(likes) / len(likes):.2f}" if likes else "–"
            portal = " / ".join(per100(s.get(k, 0), len(ws)) for k in ("towards", "away", "neither"))
            out.append(f"| {arm} | {len(ws)} | {len(got)} | {pct(rate)} [{pct(lo)}–{pct(hi)}] | {like_rate} | {portal} |")
        out.append("")
    return out


def read_report(rows, since, until):
    """The light read: stance against the regex class, its skips by reason, and how often its JSON came back."""
    reads = [r for r in rows if r.get("act") == "reply" and r.get("live") and "read_ok" in r
             and since <= ts_of(r["ts"]) < until]
    skips = [r for r in rows if r.get("act") == "skip" and r.get("why") == "read" and since <= ts_of(r["ts"]) < until]
    if not reads and not skips:
        return []
    out = ["## The light read", "",
           f"- Replies drafted with the read: {len(reads)}; JSON read OK on {sum(bool(r.get('read_ok')) for r in reads)}.",
           f"- Skipped by the read: **{len(skips)}** ({pct(len(skips) / (len(skips) + len(reads)) if reads or skips else None)} "
           f"of read items; loosen it if over ~5% or if any skip below isn't hostile or truly off topic).", ""]
    if skips:
        out += ["| skip reason (the read's words) | regex class | post |", "|---|---|---|"]
        for r in skips[-25:]:
            out.append(f"| {(r.get('detail') or '')[:80]} | {r.get('target_class')} | #{r.get('target_post')} |")
        out.append("")
    classes = sorted({str(r.get("target_class")) for r in reads})
    stances = ["firm_yes", "yes_but", "unsure", "unclear", "lean_no", "firm_no", "None"]
    if reads:
        out += ["Read stance (rows) against the regex class (columns):", "",
                "| read \\ regex | " + " | ".join(classes) + " |", "|---|" + "---|" * len(classes)]
        cross = collections.Counter((str(r.get("read_stance")), str(r.get("target_class"))) for r in reads)
        for s in stances:
            if any(cross[(s, c)] for c in classes):
                out.append(f"| {s} | " + " | ".join(str(cross[(s, c)] or "") for c in classes) + " |")
        out.append("")
    return out


def gate_report(rows, since, until):
    """LLM calls per accepted citizen-facing draft (by model), the code fixes, requeues and losses."""
    win = [r for r in rows if since <= ts_of(r.get("ts", "1970-01-01T00:00:00+00:00")) < until]
    writes = [r for r in win if r.get("act") in CITIZEN_WRITES and r.get("live")]
    rejects = collections.Counter(r["draft_id"] for r in win if r.get("act") == "reject" and r.get("draft_id")
                                  and r.get("mode") in CITIZEN_WRITES)
    by_model = collections.defaultdict(list)
    for w in writes:                     # llm_calls since G9; before it, rejects with the write's draft_id + 1
        if w.get("llm_calls") or w.get("draft_id"):
            by_model[w.get("backend")].append(w.get("llm_calls") or rejects.get(w["draft_id"], 0) + 1)
    out = ["## The gate", "", "| model | accepted | LLM calls per accepted |", "|---|---|---|"]
    for m, calls in sorted(by_model.items(), key=lambda kv: -len(kv[1])):
        out.append(f"| {m} | {len(calls)} | {sum(calls) / len(calls):.2f} |")
    fixes = collections.Counter(f for w in writes for f in (w.get("fixes") or []))
    lost = collections.Counter(r.get("why") for r in win if r.get("act") == "lost" and r.get("mode") in CITIZEN_WRITES)
    requeued = collections.Counter(r.get("why") for r in win if r.get("act") == "requeue")
    replies = sum(w["act"] == "reply" for w in writes)
    out += ["", f"- Code fixes on accepted drafts: {dict(fixes) or 'none'}.",
            f"- Requeued: {sum(requeued.values())} ({dict(requeued.most_common(6))}).",
            f"- Lost at drafting: {sum(lost.values())} ({dict(lost.most_common(6))}); against {replies} replies sent. "
            f"Target ≤ 5% lost at the gate, ≤ 1.5 calls per accepted Kimi reply.", ""]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hours", type=float, default=24, help="window length")
    ap.add_argument("--split", help="ISO time (UTC): report the window before it and the window after it")
    ap.add_argument("--root", default=str(config.ROOT), help="where logs/ and data/ are")
    ap.add_argument("--activity", help="a portal activity CSV export instead of data/portal.json")
    ap.add_argument("--out", help="write the markdown here instead of printing it")
    args = ap.parse_args()
    root = pathlib.Path(args.root)
    rows = jsonl(root / "logs" / "swan_actions.jsonl")
    outcomes = latest_by_post([o for o in jsonl(root / "logs" / "swan_outcomes.jsonl") if o.get("act") == "outcome"])
    followups = latest_by_post(jsonl(root / "logs" / "swan_followups.jsonl"))
    events = portal_events(root, args.activity)
    span = args.hours * 3600
    if args.split:
        cut = ts_of(args.split if args.split[-6] in "+-" or args.split.endswith("Z") else args.split + "+00:00")  # UTC
        windows = [(cut - span, cut, "Before"), (cut, min(cut + span, time.time()), "After")]
    else:
        windows = [(time.time() - span, time.time(), "Window")]
    out = [f"# Conversion report ({dt.datetime.now(dt.timezone.utc):%d %b %H:%M} UTC)", "",
           "Generated by `scripts/conversion_report.py` ([todo/20](../../todo/20-replies-that-convert.md)). The portal "
           "shares are weak inference (events spread over the writes of the 3 h before them): compare arms, don't "
           "prove effects. Citizen replies come from the outcome and follow-up reads, so the last ~6 h are partly "
           "unread.", ""]
    for since, until, title in windows:
        out += window_report(rows, outcomes, followups, events, since, until, title)
        out += read_report(rows, since, until) + gate_report(rows, since, until)
    text = "\n".join(out)
    if args.out:
        pathlib.Path(args.out).write_text(text + "\n")
        print(f"wrote {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
