#!/usr/bin/env python
"""Offline check of Blue's fleets (todo/43 item 4): do accounts that sit together in a fleet share a fate more than chance?

Reads only local files from the rival census (data/rival_census/: census.jsonl, pilot.jsonl, rest.jsonl, and
box/blue_state.json for Blue's own cluster labels). No network, no secrets, nothing posted.

An account is 'dead' if its newest post is 24 h or more older than the newest post in the pull, 'alive' if under 6 h
(as scripts/rival_feat.py); the ones in between are left out. For each (id gap, time gap) it builds the fleets with
swan_blue.fleets and reports, over the pairs of labelled accounts inside one fleet, the share with the same fate,
against the same count with the fate labels shuffled across accounts (the chance level), and a permutation z.
It also reports how many fleets there are, how many accounts sit in a fleet of 2+, the biggest fleet, and (with
Blue's labels) how often two accounts of one fleet carry the same cluster label.

usage: python scripts/blue_fleet_eval.py [data/rival_census] [--min-posts N]
"""
import argparse
import collections
import datetime as dt
import json
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from swan_blue import fleets as F  # noqa: E402


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def read(path):
    for line in open(path):
        if line.strip():
            yield json.loads(line)


def fates(dirname, min_posts, ours):
    last, n = {}, {}
    for f in ("pilot", "rest"):
        p = dirname / f"{f}.jsonl"
        if not p.exists():
            continue
        for r in read(p):
            if r["account_id"] in ours or r.get("err") or not r["posts"]:
                continue
            last[r["account_id"]] = max(ts(x["t"]) for x in r["posts"])
            n[r["account_id"]] = len(r["posts"])
    ref = max(last.values())
    out = {}
    for i, t in last.items():
        idle = (ref - t) / 3600
        if n[i] >= min_posts and (idle >= 24 or idle < 6):
            out[i] = int(idle >= 24)
    return out, ref


def agreement(fmap, lab, shuffles, rng):
    groups = collections.defaultdict(list)
    for i in lab:
        if i in fmap:
            groups[fmap[i]].append(i)
    pairs = [(a, b) for m in groups.values() if len(m) > 1 for k, a in enumerate(m) for b in m[k + 1:]]
    if not pairs:
        return None
    obs = sum(lab[a] == lab[b] for a, b in pairs) / len(pairs)
    ids, vals, sh = list(lab), [lab[i] for i in lab], []
    for _ in range(shuffles):
        rng.shuffle(vals)
        d = dict(zip(ids, vals))
        sh.append(sum(d[a] == d[b] for a, b in pairs) / len(pairs))
    mean = sum(sh) / len(sh)
    sd = (sum((x - mean) ** 2 for x in sh) / len(sh)) ** 0.5 or 1e-9
    return obs, mean, (obs - mean) / sd, len(pairs)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", nargs="?", default="data/rival_census")
    ap.add_argument("--min-posts", type=int, default=10, help="accounts with fewer visible posts have no usable fate")
    ap.add_argument("--shuffles", type=int, default=30)
    args = ap.parse_args()
    d, rng = pathlib.Path(args.dir), random.Random(7)
    census = list(read(d / "census.jsonl"))
    ours = set()
    if (d / "ours_all.json").exists():
        ours = {a for v in json.load(open(d / "ours_all.json")).values() for a, _ in v}
    rs = F.rows(census, skip=ours)
    lab, ref = fates(d, args.min_posts, ours)
    print(f"{len(rs)} team accounts in the census, {len(lab)} with a fate (>= {args.min_posts} posts; "
          f"{sum(lab.values())} dead, {len(lab) - sum(lab.values())} alive; pull ends {dt.datetime.fromtimestamp(ref, dt.timezone.utc):%d %b %H:%M} UTC)")
    labels = {}
    if (d / "box" / "blue_state.json").exists():
        labels = {int(k): v for k, v in json.load(open(d / "box" / "blue_state.json"))["labels"].items()}
        print(f"{len(labels)} accounts carry a Blue cluster label ({len(set(labels.values()))} clusters)")

    # the old yardstick: consecutive labelled accounts by raw id, no creation time (the census doc's 74% vs 51%)
    ids = sorted(lab)
    for g in (3, 10, 30):
        pr = [(a, b) for a, b in zip(ids, ids[1:]) if b - a <= g]
        same = sum(lab[a] == lab[b] for a, b in pr) / len(pr)
        print(f"  consecutive labelled ids <= {g} apart: same fate {same:.3f} over {len(pr)} pairs")
    print("\nid gap  time gap | same fate  shuffled   z    pairs | fleets  in 2+  biggest  | same Blue label")
    for g in (1, 3, FleetDefaults.id_gap, 10):
        for s in (5, 10, 20, FleetDefaults.gap_s, 45, 60, 120, 1e9):
            fm = F.fleets_from_rows(rs, id_gap=g, gap_s=s)
            sizes = collections.Counter(fm.values())
            multi = sum(c for c in sizes.values() if c > 1) / len(fm)
            r = agreement(fm, lab, args.shuffles, rng)
            lb = ""
            if labels:
                grp = collections.defaultdict(list)
                for i in labels:
                    if i in fm:
                        grp[fm[i]].append(i)
                pr = [(a, b) for m in grp.values() for k, a in enumerate(m) for b in m[k + 1:]]
                lb = f"{sum(labels[a] == labels[b] for a, b in pr) / max(len(pr), 1):.3f} ({len(pr)} pairs)"
            mark = "  <- chosen" if (g, s) == (FleetDefaults.id_gap, FleetDefaults.gap_s) else ""
            if r:
                print(f"{g:5d}  {'none' if s >= 1e9 else int(s):>8} | {r[0]:9.3f}  {r[1]:8.3f} {r[2]:6.1f} {r[3]:7d} | "
                      f"{len(sizes):6d}  {multi:5.0%}  {max(sizes.values()):7d}  | {lb}{mark}")
    if labels:
        tot = len(labels)
        cl = collections.Counter(labels.values())
        print(f"\nchance two labelled accounts share a Blue label: {sum(c * (c - 1) for c in cl.values()) / (tot * (tot - 1)):.3f}"
              f"; biggest cluster {max(cl.values())} accounts (a team holds at most {F.FLEET_MAX})")


class FleetDefaults:
    id_gap, gap_s = F.FLEET_ID_GAP, F.FLEET_GAP_S


if __name__ == "__main__":
    main()
