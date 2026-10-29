"""The panel (todo/52 WS2, 29 Oct, Marc): our persuasion KPI, from the light reads.

Every first reply's JSON reads the citizen's stance (read_stance on the action row). A citizen we answer twice or more is
on the panel, and a change between two of their reads in a row is a move: toward No (from Yes-but, firm Yes or unsure to
lean or firm No; lean to firm No) or toward Yes (the reverse). Counted by Sydney day, per 100 citizens re-read that day.
Each move is joined to our last write to the citizen before the post that showed it: its flip (fear/evidence/turn), the
news story and the fear dial. The 24 h before and after each deploy are compared, and the portal's persuasion lines
(data/portal.json) sit beside the days: they are the ground truth, but aggregate.

It is noisy: a light read is a model's judgement of one post. So only citizens with 2+ reads count, reads with no
position (unclear) are skipped, the order is the order the citizen wrote the posts (post ids), and rates are per 100.
On 25-29 Oct about 28-37 of every 100 re-read citizens "moved" each way a day: mostly the read's noise, symmetric. The
net (to No minus to Yes, per 100) is the signal; read the gross moves only beside it.

Read-only: logs/swan_actions.jsonl (streamed), logs/deploys.jsonl, data/portal.json. No platform call, no LLM call.
On the box, from ~/ctn:

    .venv/bin/python scripts/panel.py                          # the daily table and the last 24 h
    .venv/bin/python scripts/panel.py --days 5 --touch --deploys
    .venv/bin/python scripts/panel.py --json data/panel.json   # what swan-panel.timer runs (the dashboard's Room tile)
"""
import argparse
import collections
import datetime as dt
import json
import pathlib
import sys
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from swan_bot import jsonl  # noqa: E402

SYDNEY = ZoneInfo("Australia/Sydney")        # competition days roll over at midnight Sydney (the portal's days)
SCALE = dict(firm_yes=0, yes_but=1, unsure=2, lean_no=3, firm_no=4)     # unclear: no position, skipped
YES_SIDE, NO_SIDE = ("firm_yes", "yes_but", "unsure"), ("lean_no", "firm_no")
TOUCHES = ("reply", "reply_back", "second_voice")
KINDS = ("to_no", "lean_firm", "to_yes", "firm_lean")     # the moves counted (kind() below)


def kind(a, b):
    """The move from stance a to b: to_no, lean_firm, to_yes, firm_lean, or None (no move, or one the KPI leaves out:
    firm Yes and Yes-but between themselves, unsure to and from them)."""
    if a in YES_SIDE and b in NO_SIDE:
        return "to_no"
    if (a, b) == ("lean_no", "firm_no"):
        return "lean_firm"
    if a in NO_SIDE and b in ("firm_yes", "yes_but"):
        return "to_yes"
    if (a, b) == ("firm_no", "lean_no"):
        return "firm_lean"
    return None


def ts(s):
    return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))


def load(path, since):
    """(reads, touches) since `since` (aware datetime): reads {author: [(their post id, write time, stance)]} from live
    first replies with a light read; touches {author: [(our post id, write time, flip, news, flip_fear)]} from every
    live write to them."""
    reads, touches = collections.defaultdict(list), collections.defaultdict(list)
    for x in jsonl.Reader(path, contains=b'"live": true'):
        if x.get("live") is not True or x.get("act") not in TOUCHES or x.get("target_author") is None:
            continue
        try:
            t = ts(x["ts"])
        except (KeyError, ValueError):
            continue
        if t < since:
            continue
        a = str(x["target_author"])
        if x.get("post_id") is not None:
            touches[a].append((x["post_id"], t, x.get("flip"), x.get("news"), x.get("flip_fear")))
        if x["act"] == "reply" and x.get("read_stance") in SCALE and x.get("target_post") is not None:
            reads[a].append((x["target_post"], t, x["read_stance"]))
    return reads, touches


def moves(reads, touches):
    """Every pair of reads in a row for one citizen: dict(author, t (the later read's write), a, b, kind, flip, news,
    flip_fear of our last write before the later post). Each citizen's reads in the order they wrote the posts."""
    out = []
    for a, rs in reads.items():
        rs = sorted({p: (p, t, s) for p, t, s in rs}.values())            # one read per post, by post id
        ts_ = sorted(touches.get(a, []), key=lambda x: x[0])
        for (p0, _, s0), (p1, t1, s1) in zip(rs, rs[1:]):
            last = next((x for x in reversed(ts_) if x[0] < p1), None)  # our last write before their later post
            out.append(dict(author=a, t=t1, a=s0, b=s1, kind=kind(s0, s1), post=p1,
                            flip=last and last[2], news=last and last[3], flip_fear=last and last[4]))
    return out


def window(pairs, lo, hi):
    """Counts over the pairs whose later read was written in [lo, hi): citizens re-read, those with each kind of move
    (a citizen counts once per kind), and the rates per 100 re-read citizens."""
    ps = [p for p in pairs if lo <= p["t"] < hi]
    reread = {p["author"] for p in ps}
    out = dict(reread=len(reread), pairs=len(ps))
    for k in KINDS:
        out[k] = len({p["author"] for p in ps if p["kind"] == k})
        out[f"per100_{k}"] = round(100 * out[k] / len(reread), 2) if reread else None
    out["net"] = out["to_no"] - out["to_yes"]                 # the moves either way are mostly read noise: the net is the signal
    out["per100_net"] = round(100 * out["net"] / len(reread), 2) if reread else None
    return out


def portal_minds(path, days):
    """{Sydney day: {toward, away, neither, primary_toward}} from the portal's points log (swan_dash.build._minds, the
    dashboard's Conversion tile)."""
    from swan_dash.build import _minds
    try:
        events = json.loads(pathlib.Path(path).read_text()).get("events") or []
    except (OSError, ValueError):
        return {}
    pts = []
    for e in events:
        try:
            pts.append(dict(e, _t=ts(e["ts"])))
        except (KeyError, TypeError, ValueError):
            continue
    floor = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    return {d: _minds([e for e in pts if e["_t"].astimezone(SYDNEY).date() == d], floor) for d in days}


def by_touch(pairs):
    """Rates by what our last write before the move carried: the flip's fear, its turn, the news story, the fear dial.
    Per 100 pairs (not citizens): {field: [(value, pairs, to_no, to_yes)]}, the biggest first."""
    out = {}
    for field, get in (("fear", lambda p: (p["flip"] or "none").split("/")[0]),
                       ("turn", lambda p: (p["flip"] or "none/none/none").split("/")[-1]),
                       ("news", lambda p: p["news"] or "none"),
                       ("flip_fear", lambda p: "none" if p["flip_fear"] is None else str(p["flip_fear"]))):
        c = collections.defaultdict(collections.Counter)
        for p in pairs:
            c[get(p)]["n"] += 1
            c[get(p)][p["kind"] or "-"] += 1
        out[field] = sorted(((v, x["n"], x["to_no"] + x["lean_firm"], x["to_yes"] + x["firm_lean"]) for v, x in c.items()),
                            key=lambda r: -r[1])
    return out


def deploys(path, since, now):
    """[(time, short sha)] of the good deploys since `since`."""
    out = []
    try:
        for x in jsonl.Reader(path, contains=b'"ok"'):
            if x.get("result") == "ok" and ts(x["ts"]) >= since and ts(x["ts"]) <= now:
                out.append((ts(x["ts"]), x["new"][:7]))
    except (KeyError, ValueError):
        pass
    return out


def build(log, deploy_log, portal, now, days=4):
    """Everything the script prints and writes: the days, the last 24 h and the day before, by touch, around deploys."""
    since = now - dt.timedelta(days=days + 2)              # a citizen's earlier read may sit before the first day shown
    reads, touches = load(log, since)
    pairs = moves(reads, touches)
    first = (now - dt.timedelta(days=days - 1)).astimezone(SYDNEY).date()
    day_list = [first + dt.timedelta(days=i) for i in range((now.astimezone(SYDNEY).date() - first).days + 1)]
    minds = portal_minds(portal, day_list)
    rows = []
    for d in day_list:
        lo = dt.datetime.combine(d, dt.time(), SYDNEY).astimezone(dt.timezone.utc)
        rows.append(dict(day=d.isoformat(), **window(pairs, lo, lo + dt.timedelta(days=1)),
                         reads=sum(1 for rs in reads.values() for _, t, _ in rs if lo <= t < lo + dt.timedelta(days=1)),
                         portal=minds.get(d) or {}))
    h24 = dt.timedelta(hours=24)
    recent = [p for p in pairs if p["t"] >= now - 2 * h24]
    around = [dict(at=t.isoformat(timespec="minutes"), sha=sha, before=window(pairs, t - h24, t), after=window(pairs, t, t + h24))
              for t, sha in deploys(deploy_log, now - dt.timedelta(days=days), now)]
    return dict(ts=now.isoformat(timespec="seconds"), last24=window(pairs, now - h24, now + dt.timedelta(minutes=1)),
                day_before=window(pairs, now - 2 * h24, now - h24), days=rows,
                by_touch=by_touch([p for p in recent if p["t"] >= now - h24]), deploys=around,
                panel=dict(citizens=len(reads), on_panel=sum(1 for rs in reads.values() if len({p for p, _, _ in rs}) >= 2)))


def pct(x):
    return "   —" if x is None else f"{x:4.1f}"


def main(argv=None, now=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--days", type=int, default=4, help="Sydney days in the table (default 4)")
    ap.add_argument("--log", default=str(ROOT / "logs" / "swan_actions.jsonl"))
    ap.add_argument("--deploy-log", default=str(ROOT / "logs" / "deploys.jsonl"))
    ap.add_argument("--portal", default=str(ROOT / "data" / "portal.json"))
    ap.add_argument("--touch", action="store_true", help="also the moves by what our last write carried (last 24 h)")
    ap.add_argument("--deploys", action="store_true", help="also the 24 h before and after each deploy")
    ap.add_argument("--json", help="write the panel to this file (data/panel.json: the dashboard reads it)")
    ap.add_argument("--quiet", action="store_true", help="print nothing (the timer)")
    a = ap.parse_args(argv)
    now = now or dt.datetime.now(dt.timezone.utc)
    out = build(a.log, a.deploy_log, a.portal, now, a.days)
    if a.json:
        path = pathlib.Path(a.json)
        tmp = path.with_name(f".{path.name}.tmp")
        tmp.write_text(json.dumps(out, indent=1, default=str))
        tmp.replace(path)
    if a.quiet:
        return
    p = out["panel"]
    print(f"panel: {p['on_panel']:,} of {p['citizens']:,} citizens with a light read have 2+ (last {a.days + 2} days)")
    print(f"{'Sydney day':11} {'reads':>6} {'re-read':>7} {'net/100':>7} {'to No':>6} {'/100':>5} {'to Yes':>6} {'/100':>5} "
          f"{'lean>firm':>9} {'firm>lean':>9} | portal toward / away")
    for r in out["days"]:
        m = r["portal"]
        print(f"{r['day']:11} {r['reads']:6,} {r['reread']:7,} {pct(r['per100_net']):>7} {r['to_no']:6} {pct(r['per100_to_no'])} "
              f"{r['to_yes']:6} {pct(r['per100_to_yes'])} {r['lean_firm']:9} {r['firm_lean']:9} | "
              f"{m.get('toward', '—')} / {m.get('away', '—')}")
    for name in ("last24", "day_before"):
        w = out[name]
        print(f"{name:11} re-read {w['reread']:,}: net {w['net']:+d} ({pct(w['per100_net']).strip()}/100) = to No {w['to_no']} "
              f"({pct(w['per100_to_no']).strip()}/100) - to Yes {w['to_yes']} ({pct(w['per100_to_yes']).strip()}/100); "
              f"lean>firm {w['lean_firm']}, firm>lean {w['firm_lean']}")
    if a.touch:
        print("\nby our last write before the move, last 24 h (pairs, toward No, toward Yes):")
        for field, rows in out["by_touch"].items():
            print(f"  {field}: " + " · ".join(f"{v} {n} ({tn}/{ty})" for v, n, tn, ty in rows[:10]))
    if a.deploys:
        print("\naround the last 10 deploys (net per 100 re-read, the 24 h before -> after; n re-read):")
        for d in out["deploys"][-10:]:
            b, f = d["before"], d["after"]
            print(f"  {d['at']} {d['sha']}: {pct(b['per100_net']).strip()} -> {pct(f['per100_net']).strip()} "
                  f"(n {b['reread']} -> {f['reread']}{', the 24 h after not over' if f['reread'] < b['reread'] / 2 else ''})")


if __name__ == "__main__":
    main()
