"""One swarm run: maybe register one swarm account, scan for Vote No posts, like and repost them.
DRY RUN unless --live. On EC2 the swan-swarm.timer runs this every 5 minutes (docs/04-technical/swarm.md).

    python scripts/swan_swarm.py                 # dry run: reads feeds, prints the plan, writes nothing
    python scripts/swan_swarm.py --live          # really register / like / repost
    touch SWARM_OFF                              # pause the timer's runs
"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import capturethenarrative as ctn  # noqa: E402
from swan_bot import config  # noqa: E402
from swan_bot.swarm import Swarm  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live", action="store_true", help="really register accounts, like and repost (default: dry run)")
    ap.add_argument("--owner", default=config.SWARM_OWNER, help="team member accountable for the swarm")
    ap.add_argument("--no-register", action="store_true", help="skip registration this run")
    args = ap.parse_args()
    config.load_env()
    config.assigned_side()
    code = config.team_code() if args.live else None
    social = ctn.LegitSocial(max_retries=0)       # handle 429s ourselves: never hammer a spent budget
    Swarm(social, args.live, owner=args.owner, code=code).run_once(register=not args.no_register)


if __name__ == "__main__":
    main()
