import argparse
import sys

from swan_bot import config
from . import __doc__ as DOC
from .service import Blue, approve


def main():
    ap = argparse.ArgumentParser(description=DOC, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", default="run", choices=["run", "approve"])
    ap.add_argument("keys", nargs="?", default="", help="approve: comma-separated keys, or all")
    ap.add_argument("--live", action="store_true", help="file reports (only swan-blue.service on EC2 passes this)")
    ap.add_argument("--once", action="store_true", help="one pass, print the ranked candidates, exit")
    args = ap.parse_args()
    config.load_env()
    if args.cmd == "approve":
        approve(args.keys.split(","))
        return
    config.assigned_side()                    # refuses to run for anything but our side's team setup
    blue = Blue(live=args.live)
    if not args.live:
        args.once = True
    ranked = blue.run(once=args.once)
    for c in ranked[:40]:
        print(f"{c['key']:>10} ev {c['ev']:>5} {c['label']:>8} n={c['n_today']} {','.join(c['classes']):<20} "
              f"{c.get('age_min', '-'):>4}m  {c['detail'][63:200]}")
    print(f"{len(ranked)} candidates", file=sys.stderr)


if __name__ == "__main__":
    main()
