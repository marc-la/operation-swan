#!/usr/bin/env python3
"""Read-only: where do the portal's citizen replies and likes land on our writes? (todo/46, Marc 25 Oct)

The portal pays ~23 citizen replies per 100 writes; our 6 h outcome read of a first reply sees ~6. This answers where the rest is.

    python scripts/engagement_recon.py placed --day 2026-10-24           # portal vs the 6 h reads, for writes of one UTC day (run on the box)
    python scripts/engagement_recon.py tail --n 150                      # 150 posts 24-44 h old: when did citizens reply / like? (public reads)
    python scripts/engagement_recon.py tail --n 160 --cover              # also: did the writing voice answer each citizen reply?

`placed` reads logs/swan_actions.jsonl, logs/swan_outcomes.jsonl and data/portal.json. `tail` and `--cover` make plain public
reads (`replies`, `likers`, the 300-a-minute routes; no login, no team code), paced at about 2 a second, and never write.
25 Oct result (docs/06-strategy/engagement-audit-2026-10-25.md): the 6 h reads place 25% of the portal's replies and likes;
7 in 10 citizen replies on a first reply arrive after 6 h, and replies that arrive hours later are mostly not answered.
"""
import argparse
import collections
import datetime as dt
import json
import pathlib
import random
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from swan_bot import config, jsonl  # noqa: E402
from swan_bot.analysis import parse_activity, ts_of  # noqa: E402

TEXT_WRITES = ("reply", "reply_back", "second_voice", "post", "journalist", "thread", "thread_answer")
BUCKETS = ((0, 1, "0-1 h"), (1, 6, "1-6 h"), (6, 24, "6-24 h"), (24, 1e9, "over 24 h"))
PACE_S = 0.5


def bucket(delay_h):
    """'0-1 h' ... 'over 24 h' for a delay in hours."""
    return next(name for lo, hi, name in BUCKETS if lo <= delay_h < hi)


def delay_table(events):
    """{bucket: count} for [(delay in hours)], every bucket present, in order."""
    out = collections.OrderedDict((name, 0) for _, _, name in BUCKETS)
    for h in events:
        out[bucket(h)] += 1
    return out


def placed(portal, seen):
    """(share, portal, seen): the share of the portal's count that the reads place on a write. None with no portal count."""
    return (seen / portal if portal else None), portal, seen


def portal_counts(path, lo, hi):
    """{'likes', 'replies', 'reposts', 'follows'} the portal booked in [lo, hi) (epoch s) from data/portal.json."""
    out = collections.Counter()
    for e in json.loads(pathlib.Path(path).read_text()).get("events") or []:
        if lo <= ts_of(e["ts"]) < hi:
            p = parse_activity(e.get("message") or "")
            for k in ("likes", "replies", "reposts", "follows"):
                out[k] += p.get(k, 0)
    return out


def cmd_placed(a):
    day = dt.datetime.fromisoformat(a.day).replace(tzinfo=dt.timezone.utc).timestamp()
    lo, hi = day, day + 86400
    writes = {}
    for r in jsonl.Reader(ROOT / "logs" / "swan_actions.jsonl", contains='"live"'):
        if r.get("live") and r.get("act") in TEXT_WRITES and r.get("post_id") and lo <= ts_of(r["ts"]) < hi:
            writes[r["post_id"]] = r["act"]
    last = {}
    for r in jsonl.Reader(ROOT / "logs" / "swan_outcomes.jsonl", contains='"outcome"'):
        p = r.get("post_id")
        if r.get("act") == "outcome" and p in writes and not r.get("error") and r.get("check", 0) >= last.get(p, {}).get("check", 0):
            last[p] = r
    seen = collections.Counter()
    for r in last.values():
        seen["replies"] += r.get("citizen_replies") or 0
        seen["likes"] += r.get("citizen_likes") or 0
    pc = portal_counts(ROOT / "data" / "portal.json", lo + 3600, hi + 3600)     # the portal books an hour late
    print(f"## Placed on a write, {a.day} UTC: {len(writes)} text writes ({len(last)} with a read)\n")
    print("| | portal | placed by the 6 h reads | share |\n|---|---|---|---|")
    for k in ("replies", "likes"):
        s, p, n = placed(pc[k], seen[k])
        print(f"| citizen {k} | {p} | {n} | {'—' if s is None else format(s, '.0%')} |")
    print(f"\nPortal per 100 writes: {100 * pc['replies'] / max(1, len(writes)):.0f} replies, {100 * pc['likes'] / max(1, len(writes)):.0f} likes.")


def cmd_tail(a):
    import capturethenarrative as ctn
    now = time.time()
    lo, hi = now - a.age_max * 3600, now - a.age_min * 3600
    cand = []
    for r in jsonl.Reader(ROOT / "logs" / "swan_actions.jsonl", contains='"live"'):
        if r.get("live") and r.get("act") in ("reply", "reply_back") and r.get("post_id") and lo <= ts_of(r["ts"]) < hi:
            cand.append((r["post_id"], ts_of(r["ts"]), r.get("account_id")))
    random.seed(a.seed)
    sample = random.sample(cand, min(a.n, len(cand)))
    social = ctn.LegitSocial()
    rep, lik, posts, cover = [], [], 0, collections.Counter()
    for pid, t, acc in sample:
        try:
            replies, likers = list(social.replies(pid, limit=50)), list(social.likers(pid, limit=50))
        except ctn.APIError as e:
            print("skip", pid, e.status, file=sys.stderr)
            continue
        posts += 1
        rep += [(x["author_id"], (ts_of(x["created_at"]) - t) / 3600) for x in replies if config.is_citizen(x["author_id"])]
        lik += [(x["account_id"], (ts_of(x["liked_at"]) - t) / 3600) for x in likers if config.is_citizen(x["account_id"])]
        if a.cover:
            for x in replies:
                if config.is_citizen(x["author_id"]):
                    late = (ts_of(x["created_at"]) - t) / 3600 >= 1
                    sub = list(social.replies(x["post_id"], limit=50))
                    cover[("late" if late else "early", any(s["author_id"] == acc for s in sub))] += 1
                    time.sleep(PACE_S)
        time.sleep(PACE_S)
    print(f"## When citizens reply and like: {posts} of our replies, {a.age_min:g}-{a.age_max:g} h old\n")
    print("| delay after our write | citizen replies | citizen likes |\n|---|---|---|")
    dr, dl = delay_table(h for _, h in rep), delay_table(h for _, h in lik)
    for name in dr:
        print(f"| {name} | {dr[name]} | {dl[name]} |")
    print(f"| all | {len(rep)} ({len(rep) / max(1, posts):.2f} a post) | {len(lik)} ({len(lik) / max(1, posts):.2f} a post) |")
    if rep:
        print(f"\nAfter 6 h: {sum(1 for _, h in rep if h >= 6) / len(rep):.0%} of replies, {sum(1 for _, h in lik if h >= 6) / max(1, len(lik)):.0%} of likes.")
    if a.cover:
        print("\n| citizen reply arrived | answered by the same voice | not answered |\n|---|---|---|")
        for when in ("early", "late"):
            print(f"| {'within 1 h' if when == 'early' else 'after 1 h'} | {cover[(when, True)]} | {cover[(when, False)]} |")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("placed", help="portal replies and likes against the 6 h reads, one UTC day")
    p.add_argument("--day", required=True, help="UTC date, e.g. 2026-10-24")
    p.set_defaults(fn=cmd_placed)
    t = sub.add_parser("tail", help="public reads of older posts: when did citizens reply and like?")
    t.add_argument("--n", type=int, default=150)
    t.add_argument("--age-min", type=float, default=24, help="hours old, at least")
    t.add_argument("--age-max", type=float, default=44, help="hours old, at most")
    t.add_argument("--cover", action="store_true", help="also read each citizen reply's own replies: did the writing voice answer?")
    t.add_argument("--seed", type=int, default=7)
    t.set_defaults(fn=cmd_tail)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
