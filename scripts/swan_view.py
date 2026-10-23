"""Read-only: show swan_bot's drafts/posts in place, as they sit in the thread (news item > citizen > our reply).

    python scripts/swan_view.py              # last 20 actions
    python scripts/swan_view.py -n 50 --rejects
    python scripts/swan_view.py --md logs/view.md   # also write a Markdown copy (gitignored logs/)
"""
import argparse
import collections
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from swan_bot import config, jsonl  # noqa: E402

WRITES = {"post", "reply", "second_voice", "journalist", "reply_back"}


def render(r):
    lines = []
    head = f"{r['ts'][11:16]} UTC  {r['act'].upper()}  {'LIVE #' + str(r['post_id']) if r.get('live') else 'dry run'}"
    lines.append(f"{head}  |  {r.get('persona')} ({r.get('username')})  |  {r.get('frame')}  |  {r.get('backend')}")
    if r.get("context"):
        lines.append(f"  NEWS     {r['context'][:110]}")
    if r.get("target_text"):
        who = "journalist" if r["act"] == "journalist" else f"citizen {r.get('target_author')}"
        lines.append(f"  {who:<8} {r['target_text'][:300]}")
    lines.append(f"  US       {r['text']}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=20)
    ap.add_argument("--rejects", action="store_true", help="also show rejected drafts and why")
    ap.add_argument("--md", help="also write the view to this Markdown file")
    args = ap.parse_args()
    if not config.ACTIONS_LOG.exists():
        print("no actions logged yet")
        return
    keep = collections.deque((r for r in jsonl.Reader(config.ACTIONS_LOG)
                              if r["act"] in WRITES or (args.rejects and r["act"] == "reject")),
                             maxlen=args.n or None)         # the last n (-n 0 = all, as keep[-0:] was)
    out = []
    for r in keep:
        if r["act"] == "reject":
            out.append(f"{r['ts'][11:16]} UTC  REJECTED ({r['why']})  {r.get('mode')} | {r.get('persona')}\n  draft    {r.get('raw')}")
        else:
            out.append(render(r))
    text = "\n\n".join(out)
    print(text)
    if args.md:
        pathlib.Path(args.md).write_text("```\n" + text + "\n```\n")


if __name__ == "__main__":
    main()
