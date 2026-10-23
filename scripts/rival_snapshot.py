#!/usr/bin/env python
"""One census snapshot, run by swan-census.timer on the box every 6 h (todo/44). Read-only on Legit Social, paced, no login.

    python scripts/rival_snapshot.py            # refresh the account list, re-read the first page of every live account
    python scripts/rival_snapshot.py --dry      # print what it would read, touch nothing

What it does, in `data/rival_census/` (gitignored; README there):
  1. rival_census.py -> census-<name>.jsonl (all accounts, ~100 reads);
  2. picks the ids to read: team accounts (id > 2343, readable) whose newest post in the latest earlier snapshot is under --live-h
     hours old, plus accounts that are new since the previous account list;
  3. rival_pull.py -> snap-<name>.jsonl (first page, newest 100 posts, --rate reads a minute; resumes if re-run with the same --name);
  4. blue_scan_eval.py between the previous snapshot and this one -> scan-eval-<name>.txt (candidate vanished posts: todo/43).
Never reads or writes secrets. Skips when under 1 GB of disk is free. Our own accounts (ours_all.json) are left out.
"""
import argparse
import datetime as dt
import json
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
D = ROOT / "data" / "rival_census"
CITIZEN_MAX_ID = 2343


def _t(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def snapshot_files(d=D):
    """Earlier snapshots, oldest first: the first pass (pilot.jsonl + rest.jsonl) and every snap-*.jsonl."""
    first = [p for p in (d / "pilot.jsonl", d / "rest.jsonl") if p.exists()]
    later = sorted(d.glob("snap*.jsonl"), key=lambda p: p.stat().st_mtime)
    return first + later


def live_ids(files, ours, now, live_h=12.0):
    """Ids whose newest post, in their latest appearance across `files`, is under live_h hours old. Later files win."""
    last = {}
    for f in files:
        for line in open(f):
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("err") or not r.get("posts") or r["account_id"] in ours:
                continue
            last[r["account_id"]] = max(_t(p["t"]) for p in r["posts"])
    return sorted(i for i, t in last.items() if (now - t).total_seconds() < live_h * 3600)


def new_ids(old_ids, accounts):
    """Readable team accounts in `accounts` (census rows) that were not in the previous list."""
    return sorted(a["account_id"] for a in accounts
                  if a["account_id"] > CITIZEN_MAX_ID and a["account_id"] not in old_ids and not a.get("private"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", default=dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%MZ"))
    ap.add_argument("--live-h", type=float, default=12.0)
    ap.add_argument("--rate", type=float, default=60.0, help="reads a minute (the shared account_posts bucket is 300)")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    if shutil.disk_usage(ROOT).free < 2 ** 30:
        sys.exit("under 1 GB free: not taking a snapshot")
    py = sys.executable
    now = dt.datetime.now(dt.timezone.utc)
    ours = {a for v in json.load(open(D / "ours_all.json")).values() for a, _ in v} if (D / "ours_all.json").exists() else set()
    files = snapshot_files()
    lists = sorted(D.glob("census*.jsonl"), key=lambda p: p.stat().st_mtime)
    old = {json.loads(l)["account_id"] for l in open(lists[-1])} if lists else set()
    live = live_ids(files, ours, now, args.live_h)
    print(f"{args.name}: {len(live)} live accounts from {len(files)} earlier files; previous list {lists[-1].name if lists else None}")
    if args.dry:
        return
    census = D / f"census-{args.name}.jsonl"
    if not census.exists():
        subprocess.run([py, str(ROOT / "scripts" / "rival_census.py"), str(census)], check=True)
    fresh = new_ids(old, [json.loads(l) for l in open(census)])
    ids = sorted(set(live) | set(fresh))
    (D / f"snap-{args.name}-ids.txt").write_text(" ".join(map(str, ids)))
    print(f"reading {len(ids)} accounts ({len(live)} live, {len(fresh)} new)")
    snap = D / f"snap-{args.name}.jsonl"
    subprocess.run([py, str(ROOT / "scripts" / "rival_pull.py"), str(D / f"snap-{args.name}-ids.txt"), str(snap),
                    str(args.rate), "1"], check=True)
    prev = [f for f in files if f != snap]
    if prev:
        # compare against the newest earlier snapshot (the first pass is rest.jsonl); the eval prints candidates only
        out = D / f"scan-eval-{args.name}.txt"
        with open(out, "w") as fh:
            subprocess.run([py, str(ROOT / "scripts" / "blue_scan_eval.py"), str(prev[-1]), str(snap), "--census", str(census),
                            "--page", "100"], stdout=fh, stderr=subprocess.STDOUT, check=False)
        print("scan eval ->", out.name)


if __name__ == "__main__":
    main()
