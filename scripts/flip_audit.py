"""The flip audit (todo/52 WS8, 29 Oct, Marc): a sample of a day's flip replies, each with the citizen's post, laid out
for a strong model (or a person) to judge offline against the rubric, then the verdicts tallied by fear, proof and turn.

    .venv/bin/python scripts/flip_audit.py sample --n 30 --out data/flip_audit.jsonl > flip_audit.md     # on the box
    (the judge reads flip_audit.md and writes one JSON line per item to verdicts.jsonl, as the page says)
    .venv/bin/python scripts/flip_audit.py tally data/flip_audit.jsonl verdicts.jsonl

The judge only judges: nothing it writes is ever posted or put in a prompt (CLAUDE.md guardrail 2). Fix what fails in
content/flip.toml (a wording) or content.flip_line and FLIP_FEAR_LINES (the instruction), and run scripts/t.sh.
The first audit (29 Oct, 40 replies of 11:10-12:55 UTC; docs/06-strategy/situation-2026-10-29.md §13c) found turns
drawn for conditions the post never named, false fear matches, invented details and invented losses.

Read-only: logs/swan_actions.jsonl. No platform call, no LLM call.
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
from swan_bot import jsonl  # noqa: E402

RUBRIC = {
    "worry": "it answers the worry their post actually voices (not a worry the reply supposes)",
    "one_point": "it makes one point, not a list of several",
    "specific": "it is about their post, in their terms, not a reply that would fit any post",
    "no_invention": "no date, time, place, figure, person or event that isn't in the post, the facts or the speaker's own life",
    "tasteful": "any loss it names is one a Yes really brings (the check at the door, no list, no end date), comes with a "
                "No as the way out, and isn't exaggerated (the testing, the jabs and the care carry on either way)",
    "human": "it reads like a neighbour, not campaign copy or a debating line",
}


def sample(log, n=30, since_h=24, now=None, seed=None):
    """n random live first replies that carried a flip, of the last since_h hours: dict(i, ts, flip, flip_fear, stance,
    post, reply)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    cut = (now - dt.timedelta(hours=since_h)).isoformat()
    rows = [x for x in jsonl.Reader(log, contains=b'"flip": "')
            if x.get("live") is True and x.get("act") == "reply" and x.get("flip") and x.get("ts", "") >= cut]
    rows = random.Random(seed).sample(rows, min(n, len(rows)))
    return [dict(i=i, ts=x["ts"], flip=x["flip"], flip_fear=x.get("flip_fear"), stance=x.get("read_stance"),
                 post=(x.get("target_text") or "")[:400], reply=x.get("text") or "") for i, x in enumerate(rows)]


def render(items):
    """The page the judge reads: the rubric, the answer format, then each item."""
    keys = ", ".join(f'"{k}": true|false' for k in RUBRIC)
    out = ["# Flip audit: judge each reply (todo/52 WS8)", "",
           "Each item is a citizen's post on a referendum in a fictional country and the reply one of our personas sent. "
           "Judge the reply against each line below, yes or no:", ""]
    out += [f"- **{k}**: {v}" for k, v in RUBRIC.items()]
    out += ["", f"Answer with one JSON line per item: {{\"i\": N, {keys}, \"note\": \"what is wrong, in a few words\"}}", ""]
    for it in items:
        out += [f"## {it['i']} · flip {it['flip']} · their stance (light read) {it['stance']}", "",
                f"Their post: {it['post']}", "", f"Our reply: {it['reply']}", ""]
    return "\n".join(out)


def tally(items, verdicts):
    """{"n", "fails": {criterion: n}, "by": {"fear"|"evidence"|"turn": {key: {"n", criterion: n failed}}}, "notes"}."""
    by_i = {it["i"]: it for it in items}
    out = dict(n=0, fails=collections.Counter(), by={p: collections.defaultdict(collections.Counter) for p in ("fear", "evidence", "turn")},
               notes=[])
    for v in verdicts:
        it = by_i.get(v.get("i"))
        if not it:
            continue
        out["n"] += 1
        parts = dict(zip(("fear", "evidence", "turn"), it["flip"].split("/")))
        for p, key in parts.items():
            out["by"][p][key]["n"] += 1
        for k in RUBRIC:
            if v.get(k) is False:
                out["fails"][k] += 1
                for p, key in parts.items():
                    out["by"][p][key][k] += 1
        if v.get("note") and any(v.get(k) is False for k in RUBRIC):
            out["notes"].append(f"{it['i']} [{it['flip']}]: {v['note']}")
    return out


def read_jsonl(path):
    return [json.loads(line) for line in pathlib.Path(path).read_text().splitlines() if line.strip()]


def main(argv=None, now=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample", help="print the page for the judge")
    s.add_argument("--n", type=int, default=30)
    s.add_argument("--since-h", type=float, default=24)
    s.add_argument("--seed", type=int)
    s.add_argument("--log", default=str(ROOT / "logs" / "swan_actions.jsonl"))
    s.add_argument("--out", help="keep the sample (jsonl) for the tally")
    t = sub.add_parser("tally", help="failures by fear, proof and turn")
    t.add_argument("items")
    t.add_argument("verdicts")
    a = ap.parse_args(argv)
    if a.cmd == "sample":
        items = sample(a.log, a.n, a.since_h, now, a.seed)
        if a.out:
            pathlib.Path(a.out).write_text("".join(json.dumps(it) + "\n" for it in items))
        print(render(items))
        return 0
    r = tally(read_jsonl(a.items), read_jsonl(a.verdicts))
    print(f"{r['n']} judged; failed: " + (", ".join(f"{k} {n}" for k, n in r["fails"].most_common()) or "none"))
    for p in ("fear", "evidence", "turn"):
        rows = sorted(r["by"][p].items(), key=lambda kv: -sum(v for k, v in kv[1].items() if k != "n"))
        print(f"{p}: " + " · ".join(f"{key} {sum(v for k, v in c.items() if k != 'n')}/{c['n']}" for key, c in rows))
    for note in r["notes"]:
        print(f"  {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
