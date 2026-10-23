"""Pattern audit, read-only (swan_bot/pattern_audit.py says what it measures and where the thresholds are).

Reads logs/swan_actions.jsonl and the METADATA of the account records (username, persona, role, owner, created, status,
display_name, converted.at: nothing else is ever copied out of secrets/), writes data/pattern_audit.json atomically
(the dashboard's stealth tile reads it) and prints a short table. No network, no platform call, no secret in the output.

    python scripts/pattern_audit.py                      # last 24 h, writes data/pattern_audit.json
    python scripts/pattern_audit.py --window-h 6 --no-write
    python scripts/pattern_audit.py --actions /tmp/copy.jsonl --accounts /tmp/meta.json --now 2026-10-23T10:05:00+00:00 --out /tmp/audit.json
"""
import argparse
import json
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from swan_bot import jsonl, pattern_audit  # noqa: E402

META_KEYS = ("username", "persona", "role", "owner", "created", "status", "display_name")


def read_rows(path):
    """The write, register and convert rows of the log, only those fields the audit reads. Streams the file."""
    keep = ("ts", "act", "live", "username", "persona", "target_author", "target_post", "role")
    for rec in jsonl.Reader(path, contains='"username"'):
        if rec.get("act") in pattern_audit.WRITE_ACTS or rec.get("act") in ("register", "convert"):
            yield {k: rec[k] for k in keep if k in rec}


def read_accounts(paths):
    """Metadata of the account records, whitelisted key by key. Passwords, tokens, ids and follow lists are never read
    into the result."""
    out = []
    for p in paths:
        try:
            data = json.loads(pathlib.Path(p).read_text())
        except (OSError, ValueError):
            continue
        for rec in data if isinstance(data, list) else []:
            if not isinstance(rec, dict):
                continue
            meta = {k: rec[k] for k in META_KEYS if k in rec}
            conv = rec.get("converted")
            if isinstance(conv, dict) and conv.get("at"):
                meta["converted"] = {"at": conv["at"]}
            out.append(meta)
    return out


def write_atomic(path, report):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(report, indent=1, sort_keys=True))
    os.replace(tmp, path)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--window-h", type=float, default=24.0)
    ap.add_argument("--actions", default=str(ROOT / "logs" / "swan_actions.jsonl"))
    ap.add_argument("--accounts", action="append", help="account records (json list); repeatable; default secrets/swan_accounts.json and secrets/swarm_accounts.json")
    ap.add_argument("--now", help="ISO time to audit as of (default: now)")
    ap.add_argument("--out", default=str(ROOT / "data" / "pattern_audit.json"))
    ap.add_argument("--no-write", action="store_true", help="print only")
    args = ap.parse_args(argv)
    now = pattern_audit.parse_ts(args.now) if args.now else time.time()
    accounts = read_accounts(args.accounts or [ROOT / "secrets" / "swan_accounts.json", ROOT / "secrets" / "swarm_accounts.json"])
    rows = list(read_rows(args.actions)) if pathlib.Path(args.actions).exists() else []
    report = pattern_audit.audit(rows, accounts, now, args.window_h)
    print(pattern_audit.table(report))
    if not args.no_write:
        write_atomic(args.out, report)
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
