"""python -m swan_lab personas | run | report | status   (docs/06-strategy/npc-lab.md)

    python -m swan_lab personas --per-class 5      # cards from citizens we replied to (read-only reads, 30/min)
    python -m swan_lab run                         # the queue, forever (swan-lab.service); --once, --limit N
    python -m swan_lab report [--out FILE]         # the results tables (markdown)
    python -m swan_lab status                      # queue size, trials so far
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from swan_bot import config  # noqa: E402
from swan_lab import cards, library, report, trials  # noqa: E402


def personas(args):
    have = {c["author_id"] for c in library.personas()}
    pool = cards.candidates(pathlib.Path(args.log) if args.log else config.ACTIONS_LOG)
    read = cards.Reader()
    for cls in cards.CLASSES:
        made = sum(1 for c in library.personas() if c.get("stance_class") == cls)
        for author, post, text, _ in pool.get(cls, []):
            if made >= args.per_class:
                break
            if author in have:
                continue
            card = cards.build(author, post, text, cls, read)
            if not card or not card["posts"]:
                continue
            library.save_persona(card)
            have.add(author)
            made += 1
            print(f"card {card['id']}: {cls}, {card['certainty']}, {', '.join(card['concerns']) or '-'}")
        print(f"{cls}: {made} cards (pool {len(pool.get(cls, []))})")


def main():
    ap = argparse.ArgumentParser(prog="swan_lab")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("personas")
    p.add_argument("--per-class", type=int, default=5)
    p.add_argument("--log", help="the write log to pick citizens from (default logs/swan_actions.jsonl)")
    r = sub.add_parser("run")
    r.add_argument("--once", action="store_true", help="stop when the queue is empty")
    r.add_argument("--limit", type=int, help="stop after this many trials")
    o = sub.add_parser("report")
    o.add_argument("--out")
    sub.add_parser("status")
    args = ap.parse_args()
    config.load_env()
    if args.cmd == "personas":
        personas(args)
    elif args.cmd == "run":
        trials.loop(once=args.once, limit=args.limit)
    elif args.cmd == "report":
        md = report.markdown()
        if args.out:
            pathlib.Path(args.out).write_text(md)
        print(md)
    else:
        q = library.queue(library.strategies(), library.personas(),
                          library.done_keys(library.trials(), config.LAB_MODEL))
        print(json.dumps(dict(queued=len(q), trials=len(library.trials()), personas=len(library.personas()),
                              strategies=[s["name"] for s in library.strategies()]), indent=1))


if __name__ == "__main__":
    main()
