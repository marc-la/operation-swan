"""The room (todo/52 WS1, 29 Oct, Marc): what the citizens are saying about the vote right now, by worry, in their words.

scripts/room_read.py read it once, from the posts we answered (docs/06-strategy/situation-2026-10-29.md §13b): 73-81% a
conditional Yes, an end date in 69% of those, the list of places in 44%, the hospitals in 23%. This keeps that read live
and wider. Targeter._consider shows observe() every citizen post on the vote it judges, not only the ones we answer, with
a cheap stance from the keyword rules (targeting.room_stance); the writer adds the light read's stance of each first
reply (observe with stance=). Hourly buckets over the last RECENT_H + BASE_H hours count the posts by stance and by
driver (content/room.toml: their conditions, their fears, the No case) x stance, the fear index (the share voicing a
fear driver), and each post's 2-4 word phrases once.

write() puts the read in data/room.json every config.ROOM_EVERY_S (the dashboard's Room tile) and the buckets in
data/room_state.json, which load() reads back after a restart. Rising: a driver whose share of the last RECENT_H hours
is config.ROOM_RISE times its share in the BASE_H hours before (with one post of smoothing) lifts its flip items: lift()
is x config.ROOM_LIFT in flip.choose, like the news trend. A rising phrase is their vocabulary of the moment: shown, never
put in a prompt. No network call, no LLM call, and nothing here is ever posted.
"""
import collections
import datetime as dt
import json
import os
import random
import re
import threading
import time
import tomllib

from . import config

FILE = config.ROOT / "content" / "room.toml"
OUT_NAME, STATE_NAME = "room.json", "room_state.json"     # in config.DATA, looked up at each write (tests move it)
FAMILIES = ("but", "fear", "no", "meta")
STANCES = ("firm_yes", "yes_but", "unsure", "unclear", "lean_no", "firm_no")     # the light read's (content.READ_STANCES)
YES = ("firm_yes", "yes_but")
RECENT_H, BASE_H = 3, 24        # the window, and the day before it that a rise is measured against
LATE_S = 2 * 3600               # a post first seen this long after it was written is not counted (the sweep, older posts)
GRAM_MIN = 2                    # an hour out of the window keeps the phrases of 2+ posts (no post can join it any more)
RISE_MIN = 6                    # posts in the window before a driver or a phrase can rise
BASE_MIN = 300                  # posts in the day before, under which nothing rises (the baseline is still building)
SHOWN = 8                       # rising phrases in room.json
STALE_S = 3 * 600               # a lift worked out longer ago than this (the room thread stopped) lifts nothing
SEED_BYTES = 120_000_000        # seed() reads this much of the action log's tail (~40 MB a day of rows)
KEEP = 400                      # the newest posts kept for the pulse's sample (sample(), todo/52 WS6)

_lock, _file_lock = threading.Lock(), threading.Lock()
_cache = {"mtime": None, "drivers": {}}
_buckets = {}                   # hour (unix time // 3600) -> counts (_new)
_seen, _read = set(), set()     # post ids counted at first sight / with a light read, this run
_recent = collections.deque(maxlen=KEEP)     # (when written, text) of the posts counted at first sight, newest last
_lifted = {"t": 0.0, "keys": frozenset()}


def parse(text):
    """{key: driver} from room.toml text, in the file's order. Raises ValueError on a driver the module can't use."""
    out = {}
    for key, d in (tomllib.loads(text).get("driver") or {}).items():
        missing = [f for f in ("family", "label", "keywords") if not d.get(f)]
        if missing or d["family"] not in FAMILIES:
            raise ValueError(f"[driver.{key}] needs {', '.join(missing) or 'a family: ' + ', '.join(FAMILIES)}")
        out[key] = dict(d, key=key, lifts=list(d.get("lifts") or []), rx=[re.compile(k, re.I) for k in d["keywords"]])
    if not out:
        raise ValueError("no [driver.*] items")
    return out


def drivers(path=None):
    """The file's drivers, re-read when it changes; {} when there is none (the room then counts stances only). A file
    that doesn't parse keeps the last good drivers (summary() names the error): the room is read-only and must never
    stop the reader thread that calls observe()."""
    path = path or FILE
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return {}
    with _file_lock:
        if _cache["mtime"] != (path, mtime):
            try:
                _cache.update(mtime=(path, mtime), drivers=parse(path.read_text()), error=None)
            except (OSError, ValueError) as e:      # tomllib.TOMLDecodeError is a ValueError
                _cache.update(mtime=(path, mtime), error=f"{path.name}: {e}"[:200])
        return _cache["drivers"]


def voiced(text, ds=None):
    """The keys of the drivers the text voices, in the file's order."""
    ds = drivers() if ds is None else ds
    return [k for k, d in ds.items() if any(r.search(text or "") for r in d["rx"])]


_DROP = re.compile(r"https?://\S+|www\.\S+|[@#]\w+")
_WORD = re.compile(r"[a-z][a-z']*")
# words a phrase may not start or end on: "publish the venues" is a phrase, "the venues" is "venues"
_STOP = set("""a an the and or but so to of in on at for from by with as is are was were be been being it its it's this
that these those there their they them you your i i'm me my we our us he she his her do does did would could can will
just only even still then than if when what which who how why where all any some more most very really about into over
after before up out get got have has had""".split())


def phrases(text):
    """The post's 2-4 word phrases, each once: lower case, links, @ and # dropped; none starts or ends on a stop word, and
    each holds a word of 4+ letters."""
    words = _WORD.findall(_DROP.sub(" ", (text or "").lower().replace("’", "'")))
    out = set()
    for n in (2, 3, 4):
        for i in range(len(words) - n + 1):
            run = words[i:i + n]
            if run[0] not in _STOP and run[-1] not in _STOP and any(len(w) >= 4 for w in run):
                out.add(" ".join(run))
    return out


def _new():
    return dict(posts={}, drivers={}, fear=0, reads={}, read_drivers={}, read_fear=0, grams={})


def _add(counts, key, n=1):
    counts[key] = counts.get(key, 0) + n


def observe(post_id, text, cheap=None, stance=None, made=None, t=None):
    """Count one citizen post. cheap: its keyword stance, at first sight (Targeter._consider); None for a post off the vote,
    which isn't the room. stance: the light read's, once we answered it (the writer). A post counts once each way: at
    first sight in the hour it was written (made, unix seconds), and not at all if that was over LATE_S ago; a read in the
    hour of the read."""
    if not config.ROOM_ON or post_id is None or (cheap not in STANCES and stance not in STANCES):
        return
    t = time.time() if t is None else t
    ds = drivers()
    keys = voiced(text, ds)
    fear = any(ds[k]["family"] == "fear" for k in keys)
    first = cheap in STANCES and (made is None or t - made <= LATE_S)
    grams = phrases(text) if first else ()
    with _lock:
        if first and post_id not in _seen:
            _seen.add(post_id)
            b = _buckets.setdefault(int((t if made is None else made) // 3600), _new())
            _add(b["posts"], cheap)
            for k in keys:
                _add(b["drivers"].setdefault(k, {}), cheap)
            b["fear"] += fear
            for g in grams:
                _add(b["grams"], g)
            _recent.append((t if made is None else made, text))
        if stance in STANCES and post_id not in _read:
            _read.add(post_id)
            b = _buckets.setdefault(int(t // 3600), _new())
            _add(b["reads"], stance)
            for k in keys:
                _add(b["read_drivers"].setdefault(k, {}), stance)
            b["read_fear"] += fear
        for ids in (_seen, _read):
            if len(ids) > 100_000:
                ids.clear()
        _prune(t)


def _prune(t):
    """The caller holds _lock. Hours older than the window and the day before it go; an hour out of the window keeps only
    the phrases of GRAM_MIN+ posts (LATE_S < RECENT_H hours, so no post can join it any more)."""
    now_h = int(t // 3600)
    for h in [h for h in _buckets if h <= now_h - RECENT_H - BASE_H]:
        del _buckets[h]
    for h, b in _buckets.items():
        if h <= now_h - RECENT_H and not b.get("pruned"):
            b["grams"] = {g: n for g, n in b["grams"].items() if n >= GRAM_MIN}
            b["pruned"] = True


def _sum(bs, grams=False):
    out = _new()
    for b in bs:
        for part in ("posts", "reads"):
            for k, n in b[part].items():
                _add(out[part], k, n)
        for part in ("drivers", "read_drivers"):
            for d, counts in b[part].items():
                for k, n in counts.items():
                    _add(out[part].setdefault(d, {}), k, n)
        out["fear"] += b["fear"]
        out["read_fear"] += b["read_fear"]
        if grams:
            for g, n in b["grams"].items():
                _add(out["grams"], g, n)
    return out


def _shares(counts):
    n = sum(counts.values())
    return {k: round(counts[k] / n, 4) for k in STANCES if counts.get(k)} if n else {}


def rising(recent, base, n_r, n_b):
    """The phrases whose share of the window's posts is config.ROOM_RISE times the day before's (one post of smoothing),
    in RISE_MIN+ posts; the most posts over what the day before predicts first, and none inside one already listed."""
    found = []
    for g, n in recent.items():
        expect = n_r * (base.get(g, 0) + 1) / n_b
        if n >= RISE_MIN and n >= config.ROOM_RISE * expect:
            found.append((n - expect, g, n, n / expect))
    out = []
    for _, g, n, x in sorted(found, key=lambda f: (-f[0], f[1])):
        if any(f" {g} " in f" {o['phrase']} " or f" {o['phrase']} " in f" {g} " for o in out):
            continue                                  # "hard sunset" inside "a hard sunset clause"
        out.append(dict(phrase=g, n=n, share=round(n / n_r, 4), base=round(base.get(g, 0) / n_b, 4), x=round(x, 1)))
        if len(out) >= SHOWN:
            break
    return out


def summary(t=None):
    """The room now, as write() puts it in data/room.json: the posts and their stance mix over the window and the last
    day, the light read's mix of the posts we answered, the fear index, each driver's share against the day before, the
    rising phrases and the flip items lifted. Sets what lift() lifts."""
    t = time.time() if t is None else t
    now_h = int(t // 3600)
    ds = drivers()
    with _lock:
        _prune(t)
        hours = lambda lo, hi: [b for h, b in _buckets.items() if lo <= h <= hi]
        r = _sum(hours(now_h - RECENT_H + 1, now_h), grams=True)
        base = _sum(hours(now_h - RECENT_H - BASE_H + 1, now_h - RECENT_H), grams=True)
        day = _sum(hours(now_h - 23, now_h))
    n_r, n_b, n_d = (sum(x["posts"].values()) for x in (r, base, day))
    building = n_b < BASE_MIN
    yes_d = sum(day["reads"].get(s, 0) for s in YES)
    share = lambda n, of: round(n / of, 4) if of else None
    rows, lifted = [], set()
    for k, d in ds.items():
        n, nb = sum(r["drivers"].get(k, {}).values()), sum(base["drivers"].get(k, {}).values())
        x = (n / n_r) / ((nb + 1) / n_b) if n_r and n_b else None
        up = bool(not building and x is not None and n >= RISE_MIN and x >= config.ROOM_RISE)
        if up:
            lifted.update(d["lifts"])
        rows.append(dict(key=k, family=d["family"], label=d["label"], n=n, share=share(n, n_r), base=share(nb, n_b),
                         x=round(x, 2) if x is not None else None, rising=up,
                         day=share(sum(day["drivers"].get(k, {}).values()), n_d),
                         yes=share(sum(day["read_drivers"].get(k, {}).get(s, 0) for s in YES), yes_d)))
    _lifted.update(t=t, keys=frozenset(lifted))
    return dict(ts=dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat(timespec="seconds"),
                window_h=RECENT_H, base_h=BASE_H, building=building,
                posts=dict(recent=n_r, base=n_b, day=n_d),
                stance=dict(recent=_shares(r["posts"]), day=_shares(day["posts"])),
                reads=dict(recent=dict(n=sum(r["reads"].values()), mix=_shares(r["reads"])),
                           day=dict(n=sum(day["reads"].values()), mix=_shares(day["reads"]))),
                fear=dict(recent=share(r["fear"], n_r), base=share(base["fear"], n_b), day=share(day["fear"], n_d)),
                drivers=rows, phrases=[] if building else rising(r["grams"], base["grams"], n_r, n_b),
                lifted=sorted(lifted), lift=dict(on=bool(config.ROOM_LIFT_ON), x=config.ROOM_LIFT, rise=config.ROOM_RISE),
                error=_cache.get("error"))


def sample(n=50, max_age_s=2 * 3600, t=None, rng=random):
    """Up to n of the citizen posts on the vote written in the last max_age_s (counted at first sight), drawn at random
    when there are more, newest first: the pulse's read of the room (pulse.py, todo/52 WS6). Their text as they wrote
    it: the caller cleans it."""
    t = time.time() if t is None else t
    with _lock:
        fresh = [(w, text) for w, text in _recent if t - w <= max_age_s]
    picked = fresh if len(fresh) <= n else rng.sample(fresh, n)
    return [text for _, text in sorted(picked, key=lambda x: -x[0])]


def lift(part, key, t=None):
    """What the room multiplies a flip item's weight by now: config.ROOM_LIFT while a driver that lifts it ("pivot.no_end")
    is rising (the last summary, under STALE_S old), else 1."""
    if not (config.ROOM_ON and config.ROOM_LIFT_ON):
        return 1.0
    t = time.time() if t is None else t
    keys = _lifted["keys"] if t - _lifted["t"] <= STALE_S else ()
    return config.ROOM_LIFT if f"{part}.{key}" in keys else 1.0


def dump():
    """The buckets, json-able (load() reads them back)."""
    with _lock:
        return dict(saved=round(time.time()), buckets={str(h): b for h, b in _buckets.items()})


def load(path=None, t=None):
    """The buckets write() saved, after a restart: added to what this run has counted, hours too old dropped. A missing
    or unreadable file leaves the room as it is. Returns how many hours came back."""
    try:
        saved = json.loads((path or config.DATA / STATE_NAME).read_text())
    except (OSError, ValueError):
        return 0
    got = {int(h): b for h, b in ((saved.get("buckets") if isinstance(saved, dict) else None) or {}).items()
           if isinstance(b, dict)}
    with _lock:
        for h, b in got.items():
            merged = _sum([_buckets.get(h, _new()), dict(_new(), **b)], grams=True)
            _buckets[h] = dict(merged, pruned=bool(b.get("pruned")))
        _prune(time.time() if t is None else t)
        return sum(1 for h in got if h in _buckets)


def seed(path, cheap, t=None, nbytes=SEED_BYTES):
    """A first start with no saved counts (load() found none): the last RECENT_H + BASE_H hours from the action log's
    live first replies, so the lift has its day before from the first hour. Those are the posts we answered, a subset of
    the room: cheap(text) gives each its keyword stance, and the row its light read. Returns the posts counted."""
    t = time.time() if t is None else t
    cut, n = t - (RECENT_H + BASE_H) * 3600, 0
    try:
        f = open(path, "rb")
    except OSError:
        return 0
    with f:
        start = max(0, f.seek(0, 2) - nbytes)
        f.seek(start)
        if start:
            f.readline()                              # a line cut by the seek
        for line in f:
            if b'"live": true' not in line or b'"act": "reply"' not in line:
                continue
            try:
                x = json.loads(line)
                tw = dt.datetime.fromisoformat(x["ts"].replace("Z", "+00:00")).timestamp()
            except (ValueError, KeyError, AttributeError):
                continue
            text = x.get("target_text") or ""
            if x.get("act") == "reply" and cut <= tw <= t and text and x.get("target_post") is not None:
                observe(x["target_post"], text, cheap=cheap(text), stance=x.get("read_stance"), made=x.get("t_made"), t=tw)
                n += 1
    return n


def _save(path, obj, indent=None):
    path.parent.mkdir(exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(obj, indent=indent, separators=None if indent else (",", ":")))
    os.replace(tmp, path)


def write(t=None, out=None, state=None):
    """The read to data/room.json and the buckets to data/room_state.json, each atomically. Returns the read."""
    s = summary(t)
    _save(out or config.DATA / OUT_NAME, s, indent=1)
    _save(state or config.DATA / STATE_NAME, dump())
    return s


def reset():
    """Tests: forget the counts, the lift and the cached file."""
    with _lock:
        _buckets.clear()
        _seen.clear()
        _read.clear()
        _recent.clear()
        _lifted.update(t=0.0, keys=frozenset())
    with _file_lock:
        _cache.update(mtime=None, drivers={}, error=None)
