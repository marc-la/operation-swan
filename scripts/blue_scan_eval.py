#!/usr/bin/env python
"""Offline test of Blue's live-lead scanner (todo/43 item 2) on two census snapshots. Reads local files only: no
network, no secrets, nothing posted.

The scanner (swan_blue.scan) re-reads the newest page of each live rival account and treats a post id that was on
the previous page and is missing now, from an account that is still posting, as a vanished-post candidate (an author's
own delete looks the same). This script runs exactly that rule on two pulls of the same accounts, in the
`data/rival_census/rest*.jsonl` format written by scripts/rival_pull.py:

    {"account_id": 5001, "err": null, "pages": 1, "truncated": false, "posts": [{"id": 150123, "t": "2026-10-23T14:50:01Z", ...}]}

and prints the candidate leads, the number of live accounts compared, and how many candidates a pass would hand
Blue per hour and per fleet. `get_post` confirmation (404 twice, 10 minutes apart) is the live scanner's job: here a
candidate is only a candidate; check a few by hand with get_post before turning BLUE_SCAN_FILE on.

usage: python scripts/blue_scan_eval.py SNAP1.jsonl SNAP2.jsonl [--census data/rival_census/census.jsonl]
           [--t2 2026-10-24T16:00:00Z] [--page 50] [--out live_leads.json]

--t1/--t2 are the times the pulls were taken (default: the newest post in each file). --page is the page size the
live scanner reads (50); the census pulls hold up to 100 posts, and only the newest --page are compared. With a gap
of 24 h only slow posters keep the old page inside the new one (the summary says how many): use --page 100 for the
24 h census pair, and read the candidate count as a floor. The live scanner's gap is 3 h.
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from swan_blue import fleets as F  # noqa: E402
from swan_blue import scan  # noqa: E402


def read(path):
    out = {}
    for line in open(path):
        if line.strip():
            r = json.loads(line)
            if not r.get("err") and r.get("posts"):
                out[r["account_id"]] = r
    return out


def newest(rows):
    return max(scan.ts(p["t"]) for r in rows.values() for p in r["posts"])


def evaluate(rows1, rows2, t2, page=scan.PAGE, ours=(), fleet_of=None):
    """(candidates, summary). A candidate: account, vanished ids, posts/h, last post, fleet."""
    leads, compared, live, checkable = [], 0, 0, 0
    for aid, r2 in sorted(rows2.items()):
        r1 = rows1.get(aid)
        if r1 is None or aid in ours or aid <= scan_citizen_max():
            continue
        p2 = sorted(r2["posts"], key=lambda p: -p["id"])[:page]
        p1 = sorted(r1["posts"], key=lambda p: -p["id"])[:page]
        compared += 1
        ids2, times2 = [p["id"] for p in p2], [scan.ts(p["t"]) for p in p2]
        if len(p2) < scan.MIN_POSTS or t2 - max(times2) > scan.LIVE_H * 3600:
            continue                                  # few posts, or not posting any more: the scanner drops it
        live += 1
        checkable += max(p["id"] for p in p1) > min(ids2)        # the old page's newest post is still inside the new page
        gone = scan.vanished([p["id"] for p in p1], ids2, page)
        if gone:
            span = max(times2) - min(times2)
            leads.append(dict(account=aid, vanished=gone, posts_per_h=scan.pace(len(p2), span),
                              last_post=max(times2), idle_h=round((t2 - max(times2)) / 3600, 2), posts=len(p2),
                              fleet=(fleet_of or {}).get(aid)))
    return leads, dict(compared=compared, live=live, checkable=checkable, candidates=len(leads))


def scan_citizen_max():
    from swan_bot import config
    return config.CITIZEN_MAX_ID


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("snap1")
    ap.add_argument("snap2")
    ap.add_argument("--census", help="census.jsonl: gives each candidate its fleet")
    ap.add_argument("--ours", help="ours_all.json: our own accounts are left out")
    ap.add_argument("--t1")
    ap.add_argument("--t2")
    ap.add_argument("--page", type=int, default=scan.PAGE)
    ap.add_argument("--out", help="write the leads as JSON (live_leads.json)")
    args = ap.parse_args()
    rows1, rows2 = read(args.snap1), read(args.snap2)
    t1 = scan.ts(args.t1) if args.t1 else newest(rows1)
    t2 = scan.ts(args.t2) if args.t2 else newest(rows2)
    ours = set()
    if args.ours:
        ours = {a for v in json.load(open(args.ours)).values() for a, _ in v}
    fleet_of = None
    if args.census:
        fleet_of = F.fleets([json.loads(x) for x in open(args.census) if x.strip()], skip=ours)
    leads, summary = evaluate(rows1, rows2, t2, args.page, ours, fleet_of)
    gap_h = (t2 - t1) / 3600
    print(f"snapshot 1: {len(rows1)} accounts, snapshot 2: {len(rows2)}; gap {gap_h:.1f} h")
    print(f"compared {summary['compared']} accounts in both, {summary['live']} live (30+ posts, posted within "
          f"{scan.LIVE_H:g} h of snapshot 2), {summary['checkable']} of those with the old page still inside the new "
          f"one (the rest posted a whole page since: a vanished post would have scrolled off), "
          f"{summary['candidates']} with a vanished post")
    if gap_h > 0:
        print(f"= {summary['candidates'] / gap_h:.1f} candidate leads an hour over the gap "
              f"(a 3 h pass would see about {summary['candidates'] * 3 / gap_h:.0f} per pass)")
    by_fleet = {}
    for x in leads:
        by_fleet.setdefault(x["fleet"] or "?", []).append(x["account"])
    if fleet_of:
        print(f"{len(by_fleet)} fleets among them; largest: " + ", ".join(
            f"{k} x{len(v)}" for k, v in sorted(by_fleet.items(), key=lambda kv: -len(kv[1]))[:5]))
    print("\naccount  vanished ids          posts/h  idle h  fleet")
    for x in sorted(leads, key=lambda x: -(x["posts_per_h"] or 0)):
        print(f"{x['account']:7d}  {','.join(map(str, x['vanished'][:4])):<20}  {x['posts_per_h'] or 0:7.1f}  "
              f"{x['idle_h']:6.2f}  {x['fleet'] or '-'}")
    if args.out:
        for x in leads:
            x["last_post"] = scan.dt.datetime.fromtimestamp(x["last_post"], scan.dt.timezone.utc).isoformat()
        json.dump(dict(snapshot1=args.snap1, snapshot2=args.snap2, gap_h=round(gap_h, 2), **summary, leads=leads),
                  open(args.out, "w"), indent=1)
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
