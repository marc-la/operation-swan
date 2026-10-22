"""Arms: the randomly assigned choices behind each draft, so the overnight experiments can compare them (todo/13).

Every dimension is drawn independently per draft (factorial), by weight, unless:
  - config.PIN pins it to one arm (e.g. {"lever": "loss"}), or
  - config.SWITCHBACK runs it in time blocks: one arm for the whole block, rotating, so the portal's hourly
    towards / neither / away counts can be compared block by block. Run ONE switchback dimension at a time.
The arm and the block id go into the draft's meta and from there into the action record (bot.py), the Mongo
`experiments` collection (scripts/swan_sync_mongo.py) and the morning report (scripts/experiment_report.py).
config.ARM_WEIGHTS can reweight arms (the bandit, from night 2); keep every arm ≥ 20% of uniform.
"""
import random
import subprocess
import time

from . import config

VERSION = 3             # bump when the arms or their wording change, so reports don't pool unlike drafts
                        # 2: lengths in words, one post beat (todo/14)
                        # 3: the light read, reply styles, levers reweighted, no vaccine advocacy (todo/20)

# How each draft ends (H7). `frame` (posts only) is the curated question from the frame's craft `asks`.
ASK_KINDS = {
    "people": "End with one real question about who in the reader's own life it would touch.",
    "loss": "End with one real question about what the reader would lose or miss themselves.",
    "switching": "End with one real question about whether they know anyone who has gone from Yes or unsure to No.",
    "status_quo": "End with one real question about what's wrong, for them, with keeping things as they are today.",
    "none": "End on a plain statement of your No, with no question at all (this replaces any instruction above "
            "to finish on a question).",
}
# 2026-10-23: switching 0 (its closer was in 28% of the hidden posts, 9% of the rest); its weight to the three other questions
ASK_WEIGHTS = {"frame": 0.18, "people": 0.24, "loss": 0.24, "switching": 0.0, "status_quo": 0.24, "none": 0.10}

# Target length per mode: (sentences, lo, hi) in WORDS (todo/14: flash-lite ignores character counts, so posts ran
# 554-657 characters against the 495 cap; it keeps to sentences and words). At WORDS_TO_CHARS (about 5.4 characters a
# word with the space, measured on the voices' gold posts) every band sits inside quality.LENGTHS with room to spare.
WORDS_TO_CHARS = 5.4
LENGTH_BANDS = {
    "post": {"short": ("3", 40, 50), "medium": ("4", 45, 60), "long": ("5", 55, 70)},
    "reply": {"short": ("1 or 2", 18, 28), "medium": ("2", 25, 38), "long": ("3", 32, 45)},
    "second_voice": {"short": ("1", 12, 22), "medium": ("1 or 2", 20, 32), "long": ("2", 28, 40)},
}

# H1: answer the reason they lean Yes (v2, 20 Oct) or argue with their conditions (v1, before 20 Oct).
REPLY_MODES = ("reason_first", "conditions_first")

# How a post ends (todo/14): most put the question last, ~1 in 4 put it before the verdict, so 12 accounts don't share
# one "question? #Tag" ending. (ask_kind "none" has no question at all.)
CLOSES = {"question_last": 0.75, "verdict_last": 0.25}

# H5: reposts on a heavy-amplified post (dose-response for the Trending cutoff).
AMP_REPOSTS = (4, 6, 8)


def _uniform(arms):
    return {a: 1.0 for a in arms}


def block(dim, t=None):
    """(block_id, arm) if `dim` is in a running switchback, else (None, None). The arm order shifts by one each
    UTC day, so no arm always gets the same clock hours (12 two-hour blocks a day would otherwise fix them)."""
    for name, arms, period in getattr(config, "SWITCHBACK", ()):
        if name == dim:
            t = time.time() if t is None else t
            n = int(t // period)
            return f"{dim}:{period}:{n}", arms[(n + int(t // 86400)) % len(arms)]
    return None, None


def draw(dim, arms, meta=None, rng=random, t=None):
    """The arm for this draft. `arms` is a list (uniform) or {arm: weight}. Pinned, then switchback, then random.
    Writes meta[dim] (and meta["block_id"] in a switchback) when meta is given."""
    weights = dict(arms) if isinstance(arms, dict) else _uniform(arms)
    pinned = getattr(config, "PIN", {}).get(dim)
    block_id, arm = block(dim, t)
    if pinned is not None and pinned in weights:
        arm, block_id = pinned, None
    elif arm is None or arm not in weights:
        block_id = None
        over = getattr(config, "ARM_WEIGHTS", {}).get(dim, {})
        keys = list(weights)
        arm = rng.choices(keys, weights=[over.get(k, weights[k]) for k in keys])[0]
    if meta is not None:
        meta[dim] = arm
        if block_id:
            meta["block_id"] = block_id
    return arm


_TURN = {}


def alternate(dim, arms, meta=None, rng=random):
    """The arm for this draft, taking `arms` strictly in turn (todo/20: alternate replies, so both arms see the same
    hours and supply), from a random start per process. config.PIN still wins. Writes meta[dim] when meta is given."""
    pinned = getattr(config, "PIN", {}).get(dim)
    if pinned in arms:
        arm = pinned
    else:
        n = _TURN.setdefault(dim, rng.randrange(len(arms)))
        arm, _TURN[dim] = arms[n % len(arms)], n + 1
    if meta is not None:
        meta[dim] = arm
    return arm


def length_line(mode, meta=None, rng=random):
    """("2 or 3", lo, hi) for this draft's length band."""
    bands = LENGTH_BANDS[mode]
    return bands[draw("length_band", list(bands), meta, rng)]


_SHA = None


def git_sha():
    """The commit the bot runs (read once). Reports split by it so a mid-night deploy doesn't blur arms."""
    global _SHA
    if _SHA is None:
        try:
            _SHA = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=config.ROOT, capture_output=True,
                                  text=True, timeout=5).stdout.strip() or "unknown"
        except (OSError, subprocess.SubprocessError):
            _SHA = "unknown"
    return _SHA
