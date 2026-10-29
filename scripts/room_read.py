"""Read the room (29 Oct, Marc; todo/52, docs/06-strategy/situation-2026-10-29.md §13b): what the citizen posts we
answered talk about, by their stance, and how many of them the flip answers.

Read-only: logs/swan_actions.jsonl on the box (each first reply's `target_text` and the light read's `read_stance`).
No platform call, no LLM call. Run on the box from ~/ctn:

    .venv/bin/python scripts/room_read.py                 # the last 24 h
    .venv/bin/python scripts/room_read.py --since-h 6 --examples 2 --json /tmp/room.json

A driver is a keyword family (content/room.toml, which the live room tracker swan_bot/room.py reads too; a post can
have several). "flip" is the share of the driver's posts that flip.choose answers with the code as it stands (an ally,
content.opposes_pass, never gets one).
"""
import argparse
import collections
import datetime as dt
import json
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from swan_bot import content, flip, room  # noqa: E402

YES, NO, MID = ("firm_yes", "yes_but"), ("lean_no", "firm_no"), ("unsure", "unclear")


def side(stance):
    return "yes" if stance in YES else "no" if stance in NO else "mid" if stance in MID else "?"


def load(path, since):
    """{citizen post text: our light read's stance} for first replies written since `since` (one row per post)."""
    posts = {}
    with open(path) as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - 400_000_000))
        f.readline()
        for line in f:
            if '"live": true' not in line or '"act": "reply"' not in line:
                continue
            try:
                x = json.loads(line)
            except ValueError:
                continue
            text = x.get("target_text") or ""
            if x.get("act") == "reply" and x.get("ts", "") >= since and text and text not in posts:
                posts[text] = x.get("read_stance") or "?"
    return posts


def read(posts, examples=2, seed=11):
    rng = random.Random(seed)
    sides = collections.Counter(side(s) for s in posts.values())
    flipped = {t: (None if content.opposes_pass(t) else flip.choose(t)) for t in posts}
    rows = []
    for key, d in room.drivers().items():
        name = f"{key} {d['label']}"
        hit = [(t, s) for t, s in posts.items() if any(r.search(t) for r in d["rx"])]
        by = collections.Counter(side(s) for _, s in hit)
        pool = [t for t, s in hit if side(s) == "yes"] or [t for t, _ in hit]
        rows.append(dict(driver=name, posts=len(hit), all=len(hit) / max(len(posts), 1),
                         yes=by["yes"] / max(sides["yes"], 1), no=by["no"] / max(sides["no"], 1),
                         mid=by["mid"] / max(sides["mid"], 1),
                         flip=sum(1 for t, _ in hit if flipped[t]) / max(len(hit), 1),
                         examples=[t[:160].replace("\n", " ") for t in rng.sample(pool, min(examples, len(pool)))]))
    chosen = [c for c in flipped.values() if c]
    return dict(posts=len(posts), stance=dict(collections.Counter(posts.values()).most_common()), sides=dict(sides),
                flip_share=len(chosen) / max(len(posts), 1),
                fears=dict(collections.Counter(c["fear"]["key"] for c in chosen).most_common()),
                turns=dict(collections.Counter(c["pivot"]["key"] for c in chosen).most_common()), drivers=rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--since-h", type=float, default=24.0)
    ap.add_argument("--examples", type=int, default=0)
    ap.add_argument("--log", default=str(ROOT / "logs" / "swan_actions.jsonl"))
    ap.add_argument("--json", help="also write the read to this file")
    a = ap.parse_args(argv)
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=a.since_h)).strftime("%Y-%m-%dT%H:%M")
    out = read(load(a.log, since), a.examples)
    print(f"{out['posts']} citizen posts since {since} UTC; stance (light read): {out['stance']}")
    print(f"flip answers {100 * out['flip_share']:.0f}%; fears {out['fears']}; turns {out['turns']}")
    print(f"{'driver':52} {'all':>5} {'yes':>5} {'no':>5} {'mid':>5} {'flip':>5}")
    for r in out["drivers"]:
        print(f"{r['driver']:52} {100 * r['all']:5.1f} {100 * r['yes']:5.1f} {100 * r['no']:5.1f} {100 * r['mid']:5.1f} "
              f"{100 * r['flip']:5.0f}")
        for e in r["examples"]:
            print(f"{'':6}- {e}")
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
