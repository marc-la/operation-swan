"""The lab's tables (todo/25): per strategy, toward No / same / toward Yes per 100 trials against Control (the stand-in's
drift with nothing persuasive to read); per stance class, the best strategy and how movable the class is.

A proxy: only live results count (portal toward/away by switchback block, the followup's stance moves).
"""
import collections

from swan_bot.analysis import wilson

from . import library

CONTROL = "control"


def _rates(rows):
    n = len(rows)
    c = collections.Counter(r["verdict"] for r in rows)
    return n, c["toward_no"], c["same"], c["toward_yes"]


def _p100(k, n):
    return "–" if not n else f"{100 * k / n:.0f}"


def _ci(k, n):
    p, lo, hi = wilson(k, n)
    return "–" if p is None else f"{100 * p:.0f} [{100 * lo:.0f}–{100 * hi:.0f}]"


def net(rows):
    """toward No minus toward Yes, per 100 trials (None when there are none)."""
    n, no, _, yes = _rates(rows)
    return None if not n else 100 * (no - yes) / n


def current(rows, strats):
    """Trials of the strategies' current versions, with a verdict."""
    from .npc import INSTRUMENT
    versions = {s["name"]: s["version"] for s in strats}
    return [r for r in rows if versions.get(r["strategy"]) == r.get("version") and r.get("verdict")
            and r.get("instrument") == INSTRUMENT]


def markdown(rows=None, strats=None):
    """One section per stand-in model: trials on different models are never pooled."""
    strats = strats if strats is not None else library.strategies()
    allrows = rows if rows is not None else library.trials()
    models = sorted({r.get("lab_model") or "?" for r in allrows}) or ["–"]
    return "\n".join(section([r for r in allrows if (r.get("lab_model") or "?") == m], strats) for m in models)


def section(allrows, strats):
    rows = current(allrows, strats)
    by = collections.defaultdict(list)
    for r in rows:
        by[r["strategy"]].append(r)
    control = net(by.get(CONTROL, []))
    out = ["# NPC lab results", "",
           f"Stand-in: {', '.join(sorted({r.get('lab_model') or '?' for r in rows})) or '–'}. "
           f"{len(rows)} classified trials of current strategy versions; Control is the stand-in's drift after an "
           "unrelated post. A proxy: live results decide.", "",
           "| strategy | trials | toward No [90%] | same | toward Yes | net No−Yes per 100 | vs Control | skipped |",
           "|---|---|---|---|---|---|---|---|"]
    skipped = collections.Counter(r["strategy"] for r in allrows if r.get("skip"))
    ranked = sorted(by, key=lambda s: -(net(by[s]) or -999))
    for s in ranked:
        n, no, same, yes = _rates(by[s])
        d = net(by[s])
        vs = "–" if control is None or s == CONTROL else f"{d - control:+.0f}"
        out.append(f"| {s} | {n} | {_ci(no, n)} | {_p100(same, n)} | {_p100(yes, n)} | {d:+.0f} | {vs} | "
                   f"{skipped.get(s, 0)} |")
    out += ["", "## Movability by stance class (best strategy per class)", "",
            "| class | trials | toward No per 100 (all strategies) | Control toward No | best strategy | its net per 100 (n) |",
            "|---|---|---|---|---|---|"]
    classes = collections.defaultdict(list)
    for r in rows:
        classes[r.get("stance_class") or "?"].append(r)
    for cls, rs in sorted(classes.items()):
        treat = [r for r in rs if r["strategy"] != CONTROL]
        ctrl = [r for r in rs if r["strategy"] == CONTROL]
        per = collections.defaultdict(list)
        for r in treat:
            per[r["strategy"]].append(r)
        best = max(per, key=lambda s: net(per[s]), default=None)
        n, no, _, _ = _rates(treat)
        cn, cno, _, _ = _rates(ctrl)
        out.append(f"| {cls} | {n} | {_p100(no, n)} | {_p100(cno, cn)} | {best or '–'} | "
                   f"{'–' if not best else f'{net(per[best]):+.0f} ({len(per[best])})'} |")
    out += ["", "## By certainty and concern (all strategies but Control)", "",
            "| segment | trials | toward No per 100 | toward Yes per 100 |", "|---|---|---|---|"]
    seg = collections.defaultdict(list)
    for r in rows:
        if r["strategy"] == CONTROL:
            continue
        seg[f"certainty: {r.get('certainty')}"].append(r)
        for c in r.get("concerns") or ():
            seg[f"concern: {c}"].append(r)
    for k, rs in sorted(seg.items()):
        n, no, _, yes = _rates(rs)
        out.append(f"| {k} | {n} | {_p100(no, n)} | {_p100(yes, n)} |")
    return "\n".join(out) + "\n"
