#!/usr/bin/env python3
"""Read-only: how often does a citizen answer our reply-back again, by how deep the thread was? (Marc, 24 Oct; the depth test)

Reads logs/swan_actions.jsonl (live reply-backs carry `depth`: posts above the citizen's reply, and `depth_arm`: base = the
old cutoff of 8, deep = THREAD_DEPTH_TEST_CAP, off = test off; a deep_thread skip row carries the same) and
logs/swan_outcomes.jsonl (one row per check of a write; the last check at 5 h or more says whether a citizen replied to it).

    python scripts/depth_report.py                 # whole logs
    python scripts/depth_report.py --since 2026-10-25
    python scripts/depth_report.py --actions A --outcomes O

A depth equal to the cap ("8", "11") means at least that deep. The question the test answers: is the answer rate at depth 8-10
close to the rate at depth 4-7 (then the cutoff costs us chains) or near zero (then the platform's note is right and the
skips are free)? Roughly 100 reply-backs at depth 8 or more are needed to see it. Nothing here writes anywhere."""
import argparse
import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
BINS = ((0, 3, "1-3"), (4, 5, "4-5"), (6, 7, "6-7"), (8, 8, "8"), (9, 10, "9-10"), (11, 99, "11+"))


def bin_of(depth):
    for lo, hi, name in BINS:
        if lo <= depth <= hi:
            return name
    return "?"


def read_jsonl(path, since=""):
    with open(path) as f:
        for line in f:
            if since and line[8:18] < since:
                continue
            try:
                yield json.loads(line)
            except ValueError:
                continue


def report(actions, outcomes):
    """(lines) for rows of the two logs. A reply-back counts as 'answered' when its last outcome check at 5 h or later saw a
    citizen reply to it; reply-backs with no such check yet are counted apart (too new)."""
    last = {}
    for r in outcomes:
        if r.get("act") == "outcome" and (r.get("at_h") or 0) >= 5:
            last[r["post_id"]] = r
    written, skipped = collections.defaultdict(lambda: [0, 0, 0]), collections.Counter()   # key -> [n, read, answered]
    no_depth = 0
    for r in actions:
        if r.get("act") == "reply_back" and r.get("live"):
            if r.get("depth") is None:
                no_depth += 1
                continue
            key = (r.get("depth_arm") or "-", bin_of(r["depth"]))
            w = written[key]
            w[0] += 1
            o = last.get(r.get("post_id"))
            if o is not None:
                w[1] += 1
                w[2] += 1 if (o.get("citizen_replies") or 0) > 0 else 0
        elif r.get("act") == "skip" and r.get("mode") == "reply_back" and r.get("why") == "deep_thread":
            skipped[(r.get("depth_arm") or "-", bin_of(r["depth"]) if r.get("depth") is not None else "?")] += 1
    lines = [f"{'arm':5s} {'depth':6s} {'written':>8s} {'checked':>8s} {'answered':>9s} {'rate':>7s}"]
    for key in sorted(written, key=lambda k: (k[0], [b[2] for b in BINS].index(k[1]) if k[1] in [b[2] for b in BINS] else 99)):
        n, read, ans = written[key]
        rate = f"{100 * ans / read:5.1f}%" if read else "     -"
        lines.append(f"{key[0]:5s} {key[1]:6s} {n:8d} {read:8d} {ans:9d} {rate:>7s}")
    deep = [written[k] for k in written if k[1] in ("8", "9-10", "11+")]
    shallow = [written[k] for k in written if k[1] in ("4-5", "6-7")]
    d_read, d_ans = sum(x[1] for x in deep), sum(x[2] for x in deep)
    s_read, s_ans = sum(x[1] for x in shallow), sum(x[2] for x in shallow)
    lines.append("")
    lines.append(f"depth 8+: {d_ans}/{d_read} answered" + (f" ({100 * d_ans / d_read:.1f}%)" if d_read else "")
                 + f"   depth 4-7: {s_ans}/{s_read}" + (f" ({100 * s_ans / s_read:.1f}%)" if s_read else ""))
    if skipped:
        lines.append("skipped as deep_thread: " + ", ".join(f"{a}/{b}: {n}" for (a, b), n in sorted(skipped.items())))
    if no_depth:
        lines.append(f"{no_depth} reply-backs written before the depth was logged (no depth)")
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--actions", default=str(ROOT / "logs" / "swan_actions.jsonl"))
    ap.add_argument("--outcomes", default=str(ROOT / "logs" / "swan_outcomes.jsonl"))
    ap.add_argument("--since", default="", help="YYYY-MM-DD: only rows from this UTC day")
    args = ap.parse_args(argv)
    print("\n".join(report(read_jsonl(args.actions, args.since), read_jsonl(args.outcomes, args.since))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
