"""Today's news for replies (29 Oct, Marc; docs/06-strategy/situation-2026-10-29.md §6).

None of our replies had mentioned the week's news (early voting, the Cabinet's ID-card promise, the voluntary first
shipment, the narrowing poll), while citizens read the papers daily. content/news.toml lists the stories that favour
No, each with the facts it rests on, a plain line of what happened and what it means for a No. A share of first replies
and reply-backs (config.NEWS_SHARE, every turnout reply) gets one story in the prompt, to use only if it bears on the
citizen's point.

Which story: salience, the way news behaves. A story weighs WEIGHT[impact] and halves every HALF_LIFE_H[impact] hours,
so a passing item is gone by the evening and a poll or a climb-down stays for a day or more; it drops out after
MAX_AGE_H. What citizens are talking about lifts it: each citizen post the targeter sees is matched against the stories'
keywords (observe), and a story's matches over the last TREND_WINDOW_S raise its weight by up to TREND_GAIN. A story the
post being answered talks about counts double (REL_GAIN). The pick is drawn among the TOP stories by that score, so the
salient story leads without every reply carrying the same one.

No network call: the file is re-read when it changes, the facts come from facts.ok (a paused fact drops its story).
"""
import collections
import datetime as dt
import random
import re
import threading
import time
import tomllib

from . import config
from . import facts as fact_store

FILE = config.ROOT / "content" / "news.toml"
WEIGHT = {1: 1.0, 2: 2.0, 3: 3.0}
HALF_LIFE_H = {1: 6.0, 2: 12.0, 3: 30.0}
MAX_AGE_H = 72.0
TREND_WINDOW_S = 6 * 3600
TREND_CAP = 20                  # matches in the window at which the trend lift is full
TREND_GAIN = 1.0                # full lift: x2
REL_GAIN = 1.0                  # the story the citizen's own post is about: x2
TOP = 3

_lock = threading.Lock()
_cache = {"mtime": None, "stories": {}}
_seen = collections.deque()     # (t, story key) for citizen posts about a story, the last TREND_WINDOW_S
_seen_ids = set()


def _ts(value):
    if isinstance(value, dt.datetime):
        return (value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)).timestamp()
    return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()


def parse(text):
    """{key: story} from news.toml text. Raises ValueError on a story the module can't use."""
    out = {}
    for key, s in tomllib.loads(text).items():
        missing = [f for f in ("published", "impact", "line", "reading", "keywords") if not s.get(f)]
        if missing or s["impact"] not in WEIGHT:
            raise ValueError(f"[{key}] needs {', '.join(missing) or 'impact 1, 2 or 3'}")
        out[key] = dict(s, key=key, t=_ts(s["published"]), requires=list(s.get("requires") or []),
                        turnout=bool(s.get("turnout")),
                        rx=[re.compile(k, re.I) for k in s["keywords"]])
    return out


def stories(path=None):
    """The stories in the file, re-read when it changes; {} when there is none (the feature is then a no-op)."""
    path = path or FILE
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return {}
    with _lock:
        if _cache["mtime"] != (path, mtime):
            _cache.update(mtime=(path, mtime), stories=parse(path.read_text()))
        return _cache["stories"]


def matches(story, text):
    return sum(bool(r.search(text or "")) for r in story["rx"])


def observe(post_id, text, t=None):
    """A citizen post the targeter saw for the first time: count it for every story it is about (the trend)."""
    t = time.time() if t is None else t
    with _lock:
        if post_id in _seen_ids:
            return
        _seen_ids.add(post_id)
        if len(_seen_ids) > 50000:
            _seen_ids.clear()
    hits = [k for k, s in stories().items() if matches(s, text)]
    with _lock:
        _seen.extend((t, k) for k in hits)
        _prune(t)


def _prune(t):
    while _seen and _seen[0][0] < t - TREND_WINDOW_S:
        _seen.popleft()


def trend(key, t=None):
    t = time.time() if t is None else t
    with _lock:
        _prune(t)
        return sum(1 for _, k in _seen if k == key)


def salience(story, t=None, n_trend=None):
    """WEIGHT x half-life decay x the trend lift; 0 when it is too old, not yet out, or rests on a paused fact."""
    t = time.time() if t is None else t
    age_h = (t - story["t"]) / 3600
    if age_h < 0 or age_h > MAX_AGE_H or not fact_store.ok(story["requires"]):
        return 0.0
    n = trend(story["key"], t) if n_trend is None else n_trend
    return (WEIGHT[story["impact"]] * 0.5 ** (age_h / HALF_LIFE_H[story["impact"]])
            * (1 + TREND_GAIN * min(n, TREND_CAP) / TREND_CAP))


def pick(target_text, t=None, rng=random, turnout=False):
    """The story for one reply, or None: drawn among the TOP by salience, doubled for the story the citizen's post is
    about (and, for a turnout reply, for a turnout story)."""
    t = time.time() if t is None else t
    scored = []
    for s in stories().values():
        w = salience(s, t)
        if w <= 0:
            continue
        w *= 1 + REL_GAIN * min(matches(s, target_text), 1)
        if turnout and s["turnout"]:
            w *= 2
        scored.append((w, s["key"], s))
    if not scored:
        return None
    scored.sort(key=lambda x: (-x[0], x[1]))
    top = scored[:TOP]
    return rng.choices([s for _, _, s in top], weights=[w for w, _, _ in top])[0]


def reset():
    """Tests: forget the trend and the cached file."""
    with _lock:
        _seen.clear()
        _seen_ids.clear()
        _cache.update(mtime=None, stories={})
