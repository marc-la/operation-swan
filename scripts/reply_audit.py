"""Reply audit, read-only: how often the logged replies show the faults a citizen sees (swan_bot/reply_audit.py says
which, and why). Streams logs/swan_actions.jsonl, no network, no platform call, nothing written.

    python scripts/reply_audit.py                          # last 24 h of logs/swan_actions.jsonl
    python scripts/reply_audit.py --since-h 6 --live       # only rows that were really posted
    python scripts/reply_audit.py --actions /path/to/copy.jsonl --since-h 0     # 0: the whole file
    ssh swan-ec2 'cd ctn && .venv/bin/python scripts/reply_audit.py'            # on the bot's own log
"""
import argparse
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from swan_bot import content, jsonl, quality, reply_audit  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--actions", default=str(ROOT / "logs" / "swan_actions.jsonl"))
    ap.add_argument("--since-h", type=float, default=24.0, help="trailing window in hours; 0 reads everything")
    ap.add_argument("--live", action="store_true", help="skip dry-run rows (live: false)")
    args = ap.parse_args(argv)
    since = time.time() - args.since_h * 3600 if args.since_h else None
    recs = (r for r in jsonl.Reader(args.actions, contains='"target_text"') if not args.live or r.get("live"))
    result = reply_audit.audit(recs, content.opposes_pass, known_names=quality.KNOWN_CAPS, since=since)
    print(reply_audit.render(result))


if __name__ == "__main__":
    main()
