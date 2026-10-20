"""Read-only: after each live write, read what happened (swan_bot/followup.py). Every 30 min on EC2 (swan-followup.timer).

    python scripts/swan_followup.py              # one pass: every due check, until the read budget is used
    python scripts/swan_followup.py --dry        # list what is due, read nothing
    python scripts/swan_followup.py --max-reads 50
Writes logs/swan_outcomes.jsonl and logs/swan_followups.jsonl; state in data/swan_followup_state.json.
Needs no account and no secrets: every read is public (feeds, posts, counters, likers, followers).
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import capturethenarrative as ctn  # noqa: E402
from swan_bot import config, followup  # noqa: E402
from swan_bot.bot import load_json, save_json  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="list the due checks; read nothing")
    ap.add_argument("--max-reads", type=int, default=config.FOLLOWUP_MAX_READS)
    args = ap.parse_args()
    state = load_json(config.FOLLOWUP_STATE, {})
    n = followup.run(ctn.LegitSocial(max_retries=2), state, max_reads=args.max_reads, dry=args.dry)
    if not args.dry:
        save_json(config.FOLLOWUP_STATE, state)
    print(json.dumps(n))


if __name__ == "__main__":
    main()
