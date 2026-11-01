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
file is re-read when it changes, the facts come from facts.ok (a paused fact drops its item, or a fear whose core
names one).

todo/52 (29 Oct): the room lifts what citizens are raising now. An evidence or turn item of a driver rising in the room
(room.lift: its share of the last 3 h twice the day before's) weighs x config.ROOM_LIFT; the lifted items of a choice
are logged as `flip_lift`. An evidence or turn line may be a list of wordings, drawn after the items, so the 80% of
replies that carry a flip don't all say the big turns alike.

1 Nov (Marc): a turn marked `context = true` (no_draft: the "30 Oct draft" neither paper has reported) is also their own
when the post they answer names it (choose's context: the job's parent text). config.DRAFT_CALLOUT_ON takes it out.
"""
import random
import re
import threading
import tomllib
import zlib

from . import config, room
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
    (conditional_yes) only when no other one matches; a fear whose `requires` names a paused fact never."""
    d = d or data()
    if not d:
        return None
    for fallback in (False, True):
        fears = [f for f in d["fear"].values() if bool(f.get("fallback")) == fallback and not f.get("fallback_only")
                 and fact_store.ok(f.get("requires") or ())]
        best = max(fears, key=lambda f: hits(f, text), default=None)  # max keeps the first of equals
        if best and hits(best, text):
            return best
    return None


def choose(text, fallback=None, context=None):
    """{fear, core, evidence, pivot, lifted, fallback} for a reply to this post, or None: FLIP_ON off, no fear voiced, or
    nothing it would say rests on live facts. fallback: the key of a fear to use when the post voices none (todo/54: a
    lean-No reply gets "no_firm"); its facts must be live too, and the choice then carries fallback=True. context: the
    post this one answers; a turn marked `context = true` (no_draft, 1 Nov) is their own when either names it."""
    if not config.FLIP_ON:
        return None
    d = data()
    fear = fear_of(text, d) if d else None
    used_fallback = False
    if not fear and fallback and d:
        f = d["fear"].get(fallback)
        if f and fact_store.ok(f.get("requires") or ()):
            fear, used_fallback = f, True
    if not fear:
        return None
    evidence = [d["evidence"][k] for k in fear["evidence"] if fact_store.ok(d["evidence"][k]["requires"])]
    pivots = [p for p in d["pivot"].values() if fact_store.ok(p["requires"])
              and (config.DRAFT_CALLOUT_ON or p["key"] != "no_draft")]
    if not evidence or not pivots:
        return None
    rng = random.Random(zlib.crc32((text or "").encode()))
    ew = [e["weight"] * (KEYWORD_GAIN if hits(e, text) else 1) * (FIRST_GAIN if i == 0 else 1)
          * room.lift("evidence", e["key"]) for i, e in enumerate(evidence)]
    own = [p for p in pivots if hits(p, text) or (p.get("context") and hits(p, context))]   # their own "but" is the turn
    pivots = own or [p for p in pivots if not p.get("own_only")]   # else a general one (todo/52 audit)
    pw = [p["weight"] * room.lift("pivot", p["key"]) for p in pivots]
    out = dict(fear=fear, core=rng.choice(as_list(fear["core"])), evidence=rng.choices(evidence, weights=ew)[0],
               pivot=rng.choices(pivots, weights=pw)[0], fallback=used_fallback)
    out["lifted"] = [f"{part}.{out[part]['key']}" for part in ("evidence", "pivot") if room.lift(part, out[part]["key"]) > 1]
    for part in ("evidence", "pivot"):                           # a wording of the item's line (drawn last: same items)
        out[part] = dict(out[part], line=rng.choice(as_list(out[part]["line"])))
    return out


def as_list(x):
    return x if isinstance(x, list) else [x]


def key(choice):
    """What the write logs as `flip`: fear/evidence/pivot."""
    return "/".join(choice[p]["key"] for p in ("fear", "evidence", "pivot"))


def reset():
    """Tests: forget the cached file."""
    with _lock:
        _cache.update(mtime=None, data=None)
