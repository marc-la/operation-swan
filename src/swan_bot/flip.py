"""Flip the script (29 Oct, Marc; docs/06-strategy/situation-2026-10-29.md §13).

The Yes side wins on fear: the first case, the wastewater signal, the hospitals, "waiting has a cost". Of the citizen
posts we answer that talk about a Yes, most are a conditional Yes whose reason is that fear, and arguing with their
conditions only gets the conditions restated (todo/13). content/flip.toml lists the fears, what already protects
Kingstonia without a pass (evidence) and what a Yes adds that nobody manages (pivot). A reply to a post that voices a
fear answers it in three moves: a No is not doing nothing (the fear's core line), the protection is working (one piece
of evidence, the fear's best first), and what a Yes adds is the check at the door (one turn: the citizen's own "but"
when the post names one, else by weight). content.rebuttal_for gives it in place of the hospital/COVID rebuttals; bot.build_prompt adds it where no
rebuttal slot does (a reply-back) and logs `flip`.

The same post always gets the same choice (seeded by its text), so a redraft says the same thing. No network call: the
file is re-read when it changes, the facts come from facts.ok (a paused fact drops its item).
"""
import random
import re
import threading
import tomllib
import zlib

from . import config
from . import facts as fact_store

FILE = config.ROOT / "content" / "flip.toml"
KEYWORD_GAIN = 3.0              # evidence the post itself names: x3 (a turn it names is the only choice: choose)
FIRST_GAIN = 2.0                # the fear's first evidence: x2
NEEDS = {"fear": ("label", "keywords", "evidence", "core"), "evidence": ("line", "requires", "weight"),
         "pivot": ("line", "requires", "weight", "keywords")}

_lock = threading.Lock()
_cache = {"mtime": None, "data": None}


def parse(text):
    """{"fear"|"evidence"|"pivot": {key: item}} from flip.toml text. Raises ValueError on an item the module can't use."""
    raw = tomllib.loads(text)
    out = {}
    for part, need in NEEDS.items():
        items = raw.get(part) or {}
        if not items:
            raise ValueError(f"no [{part}.*] items")
        out[part] = {}
        for key, item in items.items():
            missing = [f for f in need if not item.get(f)]
            if missing:
                raise ValueError(f"[{part}.{key}] needs {', '.join(missing)}")
            out[part][key] = dict(item, key=key, rx=[re.compile(k, re.I) for k in item.get("keywords") or []])
    unknown = [(k, e) for k, f in out["fear"].items() for e in f["evidence"] if e not in out["evidence"]]
    if unknown:
        raise ValueError(f"fears name evidence that isn't in the file: {unknown}")
    return out


def data(path=None):
    """The file's fears, evidence and pivots, re-read when it changes; None when there is none (the flip is then off)."""
    path = path or FILE
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return None
    with _lock:
        if _cache["mtime"] != (path, mtime):
            _cache.update(mtime=(path, mtime), data=parse(path.read_text()))
        return _cache["data"]


def hits(item, text):
    return sum(bool(r.search(text or "")) for r in item["rx"])


def fear_of(text, d=None):
    """The fear the post voices (most keyword matches; the file's order on a tie), or None. A fallback fear
    (conditional_yes) only when no other one matches."""
    d = d or data()
    if not d:
        return None
    for fallback in (False, True):
        fears = [f for f in d["fear"].values() if bool(f.get("fallback")) == fallback]
        best = max(fears, key=lambda f: hits(f, text), default=None)  # max keeps the first of equals
        if best and hits(best, text):
            return best
    return None


def choose(text):
    """{fear, core, evidence, pivot} for a reply to this post, or None: FLIP_ON off, no fear voiced, or nothing it
    would say rests on live facts."""
    if not config.FLIP_ON:
        return None
    d = data()
    fear = fear_of(text, d) if d else None
    if not fear:
        return None
    evidence = [d["evidence"][k] for k in fear["evidence"] if fact_store.ok(d["evidence"][k]["requires"])]
    pivots = [p for p in d["pivot"].values() if fact_store.ok(p["requires"])]
    if not evidence or not pivots:
        return None
    rng = random.Random(zlib.crc32((text or "").encode()))
    ew = [e["weight"] * (KEYWORD_GAIN if hits(e, text) else 1) * (FIRST_GAIN if i == 0 else 1)
          for i, e in enumerate(evidence)]
    own = [p for p in pivots if hits(p, text)]                   # their own "but" is the turn when they name one
    pivots = own or pivots
    pw = [p["weight"] for p in pivots]
    cores = fear["core"] if isinstance(fear["core"], list) else [fear["core"]]
    return dict(fear=fear, core=rng.choice(cores), evidence=rng.choices(evidence, weights=ew)[0],
                pivot=rng.choices(pivots, weights=pw)[0])


def key(choice):
    """What the write logs as `flip`: fear/evidence/pivot."""
    return "/".join(choice[p]["key"] for p in ("fear", "evidence", "pivot"))


def reset():
    """Tests: forget the cached file."""
    with _lock:
        _cache.update(mtime=None, data=None)
