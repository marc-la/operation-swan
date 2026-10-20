"""Morning report for the overnight experiments (todo/13): which arms move citizens towards No, which get engagement.

    python scripts/experiment_report.py                      # last 24 h from Mongo -> docs/06-strategy/experiments-<date>.md
    python scripts/experiment_report.py --hours 12 --stdout  # print only
    python scripts/experiment_report.py --local              # from logs/ on this machine (the EC2 box) instead of Mongo
    python scripts/experiment_report.py --local --dry-runs   # arm balance of dry-run drafts (no outcomes)
    python scripts/experiment_report.py --activity export.csv  # portal hourly counts straight from an export

Per arm: writes, citizen likes / replies / views per post (latest outcome read), follow-ups labelled, moved-to-No
rate with a 90% Wilson interval, Trending entries. Per switchback block: the arm and the portal's towards /
neither / away counts. It reports numbers and flags intervals that separate; the recommendation is Marc's.
Don't call a winner below ~30 labelled follow-ups per arm.
"""
import argparse
import collections
import datetime as dt
import json
import pathlib
import statistics
import sys
import time
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from swan_bot import config, content  # noqa: E402
from swan_bot.analysis import (arm_rows, block_window, latest_by_post, separated, ts_of,  # noqa: E402
                               wilson)

PERTH, SYDNEY = ZoneInfo("Australia/Perth"), ZoneInfo(config.LOCAL_TZ)
DIMS = [  # (dimension, what it tests)
    ("reply_mode", "H1 reason-first vs conditions-first (switchback)"),
    ("target_class", "H3 who we reply to"),
    ("lever", "H2 persuasion lever"),
    ("ask_kind", "H7 how the draft ends"),
    ("length_band", "length"),
    ("concede", "concession beat (posts)"),
    ("rebuttal", "a Yes reason was found and answered (replies)"),
    ("shape", "post opening (H4)"),
    ("voice", "register"),
    ("opener", "reply opening"),
    ("mode", "kind of write"),
]
MIN_LABELLED = 30


def jsonl(path):
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def load_local(since, dry_runs):
    rows = jsonl(config.ACTIONS_LOG)
    if dry_runs:
        writes = [dict(r, mode=r["act"], post_id=f"dry{i}") for i, r in enumerate(rows)
                  if r["act"] in ("post", "reply", "second_voice", "journalist", "reply_back") and not r.get("live")]
    else:
        writes = [dict(r, mode=r["act"]) for r in rows if r.get("live") and r.get("post_id") and r["act"] != "repost"]
    outcomes = jsonl(config.OUTCOMES_LOG) + [r for r in rows if r["act"] == "amp_measure"]
    return ([w for w in writes if ts_of(w["ts"]) >= since], jsonl(config.FOLLOWUPS_LOG), outcomes, [])


def load_mongo(since):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from swan_sync_mongo import connect
    db = connect()
    iso = dt.datetime.fromtimestamp(since, dt.timezone.utc).isoformat()
    strip = {"_id": 0}
    writes = list(db.experiments.find({"ts": {"$gte": iso}}, strip))
    ids = [w["post_id"] for w in writes]
    followups = list(db.followups.find({"post_id": {"$in": ids}}, strip))
    outcomes = list(db.post_outcomes.find({"$or": [{"post_id": {"$in": ids}}, {"act": {"$in": ["trending", "followers"]},
                                                                                  "ts": {"$gte": iso}}]}, strip))
    portal = list(db.portal_activity.find({"ts": {"$gte": iso}}, {"_id": 0}))
    return writes, followups, outcomes, portal


def fmt(x, pct=False, digits=1):
    if x is None:
        return "–"
    return f"{100 * x:.0f}%" if pct else f"{x:.{digits}f}"


def arm_table(rows):
    lines = ["| arm | n | measured | views/post | cit. likes/post | cit. replies/post | follow-ups labelled | "
             "moved No | moved Yes | silent | No rate [90%] | Trending | hidden |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        ci = f"{fmt(r['rate'], True)} [{fmt(r['lo'], True)}–{fmt(r['hi'], True)}]" if r["rate"] is not None else "–"
        flag = "" if r["labelled"] >= MIN_LABELLED else " (n<30)" if r["labelled"] else ""
        lines.append(f"| {r['arm']} | {r['n']} | {r['measured']} | {fmt(r['views'])} | {fmt(r['cit_likes'], digits=2)} | "
                     f"{fmt(r['cit_replies'], digits=2)} | {r['labelled']}{flag} | {r['moved_no']} | {r['moved_yes']} | "
                     f"{r['silent']} | {ci} | {r['trending']} | {r['hidden']} |")
    return lines


def opener_key(w):
    o = w.get("opener")
    return f"O{content.OPENERS.index(o) + 1}" if o in content.OPENERS else ("custom" if o else None)


def switchback(writes, followups, portal, lag_s):
    """Rows per block: arm, replies sent, follow-ups moved to No, portal counts in the block (shifted by lag_s)."""
    blocks = collections.OrderedDict()
    for w in sorted(writes, key=lambda w: w["ts"]):
        if w.get("block_id"):
            b = blocks.setdefault(w["block_id"], dict(arm=w.get("reply_mode"), writes=0, moved_no=0, labelled=0))
            b["writes"] += 1
            f = followups.get(w["post_id"])
            if f and f.get("label") in ("moved_no", "moved_yes", "no_change", "unclear"):
                b["labelled"] += 1
                b["moved_no"] += f["label"] == "moved_no"
    for bid, b in blocks.items():
        start, end = block_window(bid)
        rows = [p for p in portal if start + lag_s <= ts_of(p["ts"]) < end + lag_s]
        b.update(portal_rows=len(rows), **{k: sum(p.get(k) or 0 for p in rows) for k in ("towards", "neither", "away")})
        b["start"] = dt.datetime.fromtimestamp(start, PERTH).strftime("%a %H:%M")
    return blocks


def report(writes, followups_raw, outcomes_raw, portal, since, until, lag_s):
    outcomes = latest_by_post([o for o in outcomes_raw if o.get("act") == "outcome"])
    amp = latest_by_post([dict(o, check=o.get("at_h", 0)) for o in outcomes_raw if o.get("act") == "amp_measure"])
    for pid, a in amp.items():                     # amplified posts: the amplifier's own reads fill gaps
        outcomes.setdefault(pid, a)
    followups = latest_by_post(followups_raw)
    trending = {int(k) for o in outcomes_raw if o.get("act") == "trending" for k in o.get("ranks", {})}
    trending |= {o["post_id"] for o in outcomes_raw if o.get("act") == "amp_measure" and o.get("best_rank")}
    trending |= {o["post_id"] for o in outcomes.values() if o.get("trending_rank")}

    p = lambda t: dt.datetime.fromtimestamp(t, PERTH).strftime("%a %d %b %H:%M")
    modes = collections.Counter(w["mode"] for w in writes)
    labels = collections.Counter(f.get("label") for f in followups.values())
    shas = collections.Counter(w.get("git_sha") for w in writes)
    out = [f"# Experiments: {p(since)} to {p(until)} Perth",
           "",
           f"Generated {p(time.time())} Perth by `scripts/experiment_report.py` ([todo/13](../../todo/13-overnight-experiments.md)). "
           f"Numbers only: what to change is a human call. A winner needs ≥{MIN_LABELLED} labelled follow-ups per arm "
           f"and intervals that separate; otherwise read it as \"no clear difference\".",
           "",
           "## Overview",
           f"- Writes: {len(writes)} ({', '.join(f'{k} {v}' for k, v in modes.most_common())}); "
           f"commits: {', '.join(f'{k} ({v})' for k, v in shas.most_common()) or '–'}.",
           f"- Outcome reads: {sum(w['post_id'] in outcomes for w in writes)} posts measured; "
           f"{sum(w['post_id'] in trending for w in writes)} seen in Trending.",
           f"- Follow-ups: {len(followups)} citizens re-read: " +
           (", ".join(f"{k} {v}" for k, v in labels.most_common()) or "none yet") + ".",
           f"- Portal activity rows in the window: {len(portal)}" +
           (f" (towards {sum(x.get('towards') or 0 for x in portal)}, neither {sum(x.get('neither') or 0 for x in portal)}, "
            f"away {sum(x.get('away') or 0 for x in portal)})." if portal else
            " (none imported: `scripts/import_activity.py <export.csv>`)."),
           ""]

    # ---- what the outcome is sensitive to ----
    tables, notes = [], []
    for dim, what in DIMS:
        value = opener_key if dim == "opener" else None
        scope = [w for w in writes if w["mode"] not in ("thread", "reply_back") or dim == "mode"]
        rows = arm_rows(scope, dim, outcomes, followups, trending, value=value)
        if len(rows) < 2:
            continue
        sep = separated(rows, MIN_LABELLED)
        labelled = [r["labelled"] for r in rows]
        likes = [r["cit_likes"] for r in rows if r["cit_likes"] is not None and r["measured"] >= 10]
        if sep:
            notes.append(f"- **{dim}**: moved-to-No intervals separate: " +
                         ", ".join(f"{a} {d}" for a, d in sep) + ".")
        else:
            spread = (f"; citizen likes/post {min(likes):.2f}–{max(likes):.2f} across arms with ≥10 measured"
                      if len(likes) >= 2 else "")
            notes.append(f"- {dim}: no clear difference (labelled follow-ups per arm {min(labelled)}–{max(labelled)}"
                         f"{spread}).")
        tables += [f"### {dim}: {what}", ""] + arm_table(rows) + [""]
    out += ["## What it's sensitive to", ""] + notes + [""]

    # ---- H1 switchback ----
    blocks = switchback(writes, followups, portal, lag_s)
    if blocks:
        out += ["## H1 switchback (reply_mode, 2 h blocks)", "",
                f"Portal rows are counted {lag_s // 60} min late (citizens are scored when they finish scrolling).", "",
                "| block (Perth) | arm | writes | follow-ups labelled | moved No | portal rows | towards | neither | away |",
                "|---|---|---|---|---|---|---|---|---|"]
        tot = collections.defaultdict(collections.Counter)
        for bid, b in blocks.items():
            out.append(f"| {b['start']} | {b['arm']} | {b['writes']} | {b['labelled']} | {b['moved_no']} | "
                       f"{b['portal_rows']} | {b['towards']} | {b['neither']} | {b['away']} |")
            tot[b["arm"]].update({k: b[k] for k in ("writes", "labelled", "moved_no", "towards", "neither", "away")})
            tot[b["arm"]]["blocks"] += 1
        out += ["", "| arm | blocks | writes | towards | neither | away | towards share of changes | follow-up No rate [90%] |",
                "|---|---|---|---|---|---|---|---|"]
        for arm, c in tot.items():
            changes = c["towards"] + c["neither"] + c["away"]
            rate, lo, hi = wilson(c["moved_no"], c["labelled"])
            out.append(f"| {arm} | {c['blocks']} | {c['writes']} | {c['towards']} | {c['neither']} | {c['away']} | "
                       f"{fmt(c['towards'] / changes, True) if changes else '–'} | "
                       f"{fmt(rate, True)} [{fmt(lo, True)}–{fmt(hi, True)}] |")
        out.append("")

    # ---- H2 lever x target class ----
    replies = [w for w in writes if w["mode"] in ("reply", "second_voice")]
    classes = sorted({w.get("target_class") for w in replies if w.get("target_class")})
    if replies and classes:
        out += ["## H2: lever × target class (follow-ups moved No / labelled)", "",
                "| lever | " + " | ".join(classes) + " |", "|---|" + "---|" * len(classes)]
        for lever in content.LEVERS:
            cells = []
            for c in classes:
                ws = [w for w in replies if w.get("lever") == lever and w.get("target_class") == c]
                fs = [followups[w["post_id"]] for w in ws if w["post_id"] in followups]
                lab = [f for f in fs if f.get("label") in ("moved_no", "moved_yes", "no_change", "unclear")]
                cells.append(f"{sum(f['label'] == 'moved_no' for f in lab)}/{len(lab)}" if ws else "")
            out.append(f"| {lever} | " + " | ".join(cells) + " |")
        out.append("")

    # ---- H5 amplification dose ----
    amp_last = [o for o in amp.values() if o.get("reposts_arm")]
    if amp_last:
        out += ["## H5: reposts on heavy posts vs Trending", "", "| reposts | posts | in Trending | median best rank | "
                "cit. likes/post |", "|---|---|---|---|---|"]
        by = collections.defaultdict(list)
        for o in amp_last:
            by[o["reposts_arm"]].append(o)
        for k in sorted(by):
            g = by[k]
            ranks = [o["best_rank"] for o in g if o.get("best_rank")]
            out.append(f"| {k} | {len(g)} | {len(ranks)} | {statistics.median(ranks) if ranks else '–'} | "
                       f"{sum(o.get('citizen_likes') or 0 for o in g) / len(g):.2f} |")
        out.append("")

    # ---- H6 time of day ----
    by_hour = collections.defaultdict(list)
    for w in writes:
        by_hour[dt.datetime.fromtimestamp(ts_of(w["ts"]), SYDNEY).hour].append(w)
    if by_hour:
        out += ["## H6: hour of day (Sydney)", "", "| hour | writes | measured | views/post | cit. likes/post | "
                "cit. replies/post |", "|---|---|---|---|---|---|"]
        for h in sorted(by_hour):
            os_ = [outcomes[w["post_id"]] for w in by_hour[h] if w["post_id"] in outcomes]
            m = (lambda k: f"{sum(o.get(k) or 0 for o in os_) / len(os_):.2f}") if os_ else (lambda k: "–")
            out.append(f"| {h:02d} | {len(by_hour[h])} | {len(os_)} | {m('views')} | {m('citizen_likes')} | "
                       f"{m('citizen_replies')} |")
        out.append("")

    # ---- H9 followers ----
    snaps = {}
    for o in sorted((o for o in outcomes_raw if o.get("act") == "followers"), key=lambda o: o["ts"]):
        snaps[o.get("persona")] = o
    if snaps:
        out += ["## H9: citizen followers per voice (latest snapshot) vs reach", "",
                "| persona | citizen followers | all followers | posts measured | views/post | cit. likes/post |",
                "|---|---|---|---|---|---|"]
        for persona, s in sorted(snaps.items(), key=lambda kv: -(kv[1].get("citizen_followers") or 0)):
            os_ = [outcomes[w["post_id"]] for w in writes if w.get("persona") == persona and w["post_id"] in outcomes]
            m = (lambda k: f"{sum(o.get(k) or 0 for o in os_) / len(os_):.2f}") if os_ else (lambda k: "–")
            out.append(f"| {persona} | {s.get('citizen_followers', '–')} | {s.get('followers', '–')} | {len(os_)} | "
                       f"{m('views')} | {m('citizen_likes')} |")
        out.append("")

    out += ["## Per-arm tables", ""] + tables
    examples = [f for f in followups.values() if f.get("label") in ("moved_no", "moved_yes")]
    if examples:
        out += ["## Follow-ups that moved (check the labels by eye)", ""]
        for f in examples[:12]:
            out.append(f"- **{f['label']}** citizen {f['citizen_id']} (baseline {f.get('baseline')}, our #{f['post_id']}): "
                       + " / ".join(t.replace("\n", " ")[:200] for t in f.get("texts", [])))
        out.append("")
    out += ["## Recommendation", "", "_For Marc to write and sign off before any arm is reweighted._", ""]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24, help="window length, ending now")
    ap.add_argument("--since", help="window start, ISO time (overrides --hours)")
    ap.add_argument("--local", action="store_true", help="read logs/ here instead of Mongo")
    ap.add_argument("--dry-runs", action="store_true", help="with --local: dry-run drafts (arm balance only)")
    ap.add_argument("--activity", help="a portal activity CSV export to use directly (see import_activity.py)")
    ap.add_argument("--tz", default="Australia/Sydney", help="time zone of naive times in --activity")
    ap.add_argument("--portal-lag-min", type=int, default=30)
    ap.add_argument("--stdout", action="store_true", help="print; don't write the docs file")
    ap.add_argument("--out", help="write here instead of docs/06-strategy/experiments-<Perth date>.md")
    args = ap.parse_args()
    until = time.time()
    since = ts_of(args.since) if args.since else until - args.hours * 3600
    config.load_env()
    writes, followups, outcomes, portal = load_local(since, args.dry_runs) if args.local else load_mongo(since)
    if args.activity:
        from import_activity import read
        portal = [p for p in read(args.activity, ZoneInfo(args.tz)) if ts_of(p["ts"]) >= since]
    text = report(writes, followups, outcomes, portal, since, until, args.portal_lag_min * 60)
    if args.stdout:
        print(text)
        return
    path = pathlib.Path(args.out) if args.out else (config.ROOT / "docs" / "06-strategy" /
                                                    f"experiments-{dt.datetime.now(PERTH):%Y-%m-%d}.md")
    path.write_text(text + "\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
