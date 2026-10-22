"""The dashboard's Lab page (todo/25): the NPC lab's results from data/lab/ and content/lab/, rebuilt with the main page.

Per stand-in model (never pooled): one row per strategy (trials, toward No / same / toward Yes per 100, net against
Control, by stance class), click-through to example trials (their post, our reply, the stand-in's view after, the
verdict). Fields are picked one by one; whole records are never rendered. Reads files only.
"""
import collections
import json
import pathlib

from swan_lab import library, report

CLASSES = ("firm_yes", "yes_but", "yes_reason", "unsure", "lean_no", "firm_no")
EXAMPLES = 4


def _trials(path):
    out = []
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _per100(k, n):
    return None if not n else round(100 * k / n)


def strategy_row(name, rows, control_net, meta, control_rows=()):
    n, no, same, yes = report._rates(rows)
    paired, pairs = report.shift(rows, control_rows) if name != report.CONTROL else (None, 0)
    d = report.net(rows)
    by_class = {}
    for cls in CLASSES:
        rs = [r for r in rows if r.get("stance_class") == cls]
        by_class[cls] = None if not rs else round(report.net(rs))
    examples = [dict(cls=r.get("stance_class") or "", them=(r.get("target_text") or "")[:300],
                     reply=(r.get("reply") or "")[:500], after=(r.get("after") or "")[:400],
                     verdict=r.get("verdict") or "", voice=r.get("voice") or "")
                for r in rows[-EXAMPLES:]][::-1]
    return dict(name=name, author=meta.get("author") or "", notes=(meta.get("notes") or "")[:300], n=n,
                shift=None if paired is None else round(paired, 2), pairs=pairs,
                no=_per100(no, n), same=_per100(same, n), yes=_per100(yes, n),
                net=None if d is None else round(d),
                vs=None if d is None or control_net is None or name == report.CONTROL else round(d - control_net),
                by_class=by_class, examples=examples)


def gather_lab(root):
    root = pathlib.Path(root)
    strats = library.strategies(root / "content" / "lab" / "strategies")
    cards = {c["id"]: c for c in library.personas(root / "content" / "lab" / "personas")}
    allrows = _trials(root / "data" / "lab" / "trials.jsonl")
    try:
        status = json.loads((root / "data" / "lab" / "status.json").read_text())
    except (OSError, ValueError):
        status = {}
    meta = {s["name"]: s for s in strats}
    models = []
    for model in sorted({r.get("lab_model") or "?" for r in allrows}):
        rows = report.current([r for r in allrows if (r.get("lab_model") or "?") == model], strats)
        for r in rows:                                  # their post, from the card (the trial keeps the persona id)
            r["target_text"] = (cards.get(r["persona"]) or {}).get("target_text")
        by = collections.defaultdict(list)
        for r in rows:
            by[r["strategy"]].append(r)
        control = report.net(by.get(report.CONTROL, []))
        table = [strategy_row(s, by[s], control, meta.get(s, {}), by.get(report.CONTROL, [])) for s in by]
        table.sort(key=lambda t: -(t["shift"] if t["shift"] is not None else -9))
        models.append(dict(model=model, trials=len(rows), control=None if control is None else round(control),
                           table=table))
    skipped = collections.Counter(r["strategy"] for r in allrows if r.get("skip"))
    return dict(models=models, classes=CLASSES, personas=len(cards),
                per_class=collections.Counter(c.get("stance_class") for c in cards.values()),
                strategies=[dict(name=s["name"], author=s.get("author") or "", priority=s["priority"],
                                 skipped=skipped.get(s["name"], 0)) for s in strats],
                queued=status.get("queued"), down=status.get("down"), status_ts=status.get("ts"),
                lab_model=status.get("lab_model"))
