"""todo/31 stealth, the behaviour half: each voice keeps a human day (docs/06-strategy/stealth.md).

Audit 2026-10-22 ~10:15 UTC: each voice wrote 100-200 times in 24 h and was active 18-24 hours of the 24, and 294 of 730
citizens got two of our voices within 60 min. Other teams' Blue reporters read that as a bot farm (33 posts hidden on
16 voices, 13 of our 61 accounts banned). The rules here, each with its switch in config (# ---- todo/31 stealth ----):
  - a daily and an hourly write budget per voice (VOICE_WRITES_PER_DAY, VOICE_WRITES_PER_H; rolling windows);
  - a fixed sleep window of 7-8 h per voice in Kingstonia time, derived from its persona key (stable across restarts);
  - jittered gaps between one voice's writes, and now and then a 1-2 h break;
  - one voice per citizen per day: no other voice of ours writes to a citizen, or under their post, for ONE_VOICE_S
    (a reply-back stays with the voice the citizen answered or mentioned);
  - staggered starts after a restart;
  - the numbers for data/status.json (metrics()).
They hold only for the live bot (bot.Accounts.rest); a dry run rotates personas without waiting, as before.
Kingstonia has no stated time zone (docs/01-competition/setting.md): its clock is the competition's, Sydney
(config.LOCAL_TZ), which is also when the citizens are online and when the competition day rolls over.
"""
import collections
import datetime as dt
import hashlib
import json
import math
import random
import threading
import time
from zoneinfo import ZoneInfo

from . import config, pool

# every write a voice makes (the dashboard's WRITES), and the ones to a citizen that count for one voice per citizen
WRITE_MODES = ("post", "reply", "reply_back", "second_voice", "journalist", "thread", "thread_answer", "repost")
CITIZEN_MODES = ("reply", "reply_back", "second_voice")
DAY_S, HOUR_S = 24 * 3600, 3600


def _tz():
    return ZoneInfo(config.LOCAL_TZ)


def _frac(key, salt):
    """A number in [0, 1] fixed by the key (sha256, so the same on every machine and after every restart)."""
    return int(hashlib.sha256(f"{salt}:{key}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def sleep_window(key):
    """(start, length) in hours of Kingstonia's clock for this persona key: a start inside its kind's range
    (VOICE_SLEEP_KIND: early risers, night-shift workers, everyone else at night) and a length in VOICE_SLEEP_H, both
    fixed by the key, so the voices go to sleep at different times and each always at the same one."""
    lo, hi = config.VOICE_SLEEP_STARTS[config.VOICE_SLEEP_KIND.get(key, "night")]
    start = (lo + (hi - lo) * _frac(key, "sleep-start")) % 24
    a, b = config.VOICE_SLEEP_H
    return round(start, 2), round(a + (b - a) * _frac(key, "sleep-length"), 2)


def local_hour(t=None):
    local = dt.datetime.fromtimestamp(time.time() if t is None else t, _tz())
    return local.hour + local.minute / 60 + local.second / 3600


def asleep(key, t=None):
    if not config.VOICE_SLEEP or not key:
        return False
    start, length = sleep_window(key)
    return (local_hour(t) - start) % 24 < length


def wakes_in(key, t=None):
    """Seconds until this persona's sleep window ends (0 when awake)."""
    if not asleep(key, t):
        return 0.0
    start, length = sleep_window(key)
    return ((start + length - local_hour(t)) % 24) * 3600


def window_text(key):
    start, length = sleep_window(key)
    hm = lambda h: f"{int(h % 24):02d}:{int(round(h % 1 * 60)) % 60:02d}"
    return f"{hm(start)}-{hm(start + length)}"


def key_of(rec):
    """The key a voice's sleep window comes from: its persona, or for a booster turned voice its username (the
    suspended voice on the same card kept that card's hours)."""
    if rec.get("converted"):
        return rec.get("username")
    return rec.get("persona") or rec.get("username")


def voice_since(rec):
    """Epoch seconds a voice's life began, for todo/40's first-hours rule, or None when the record says nothing (then it
    counts as old, so a dry-run record or an old one without dates is never held back). A converted booster: converted.at.
    A warmed account the pool activated: its pool note (act activate / convert) or ramp.from. Any other voice: created
    (an original voice wrote within minutes of registering), so its first write is its first minutes."""
    conv = rec.get("converted") or {}
    note = rec.get("pool") or {}
    for v in (conv.get("at"), note.get("at") if note.get("act") in ("activate", "convert") else None,
              (rec.get("ramp") or {}).get("from"), rec.get("created")):
        t = pool.parse_ts(v)
        if t is not None:
            return t
    return None


def voice_age_h(rec, t=None):
    """Hours of voice life (voice_since), or None when unknown."""
    since = voice_since(rec)
    return None if since is None else ((time.time() if t is None else t) - since) / 3600


def new_voice(rec, t=None):
    """todo/40: still inside its first NEW_VOICE_NO_POST_H hours of voice life, so it writes replies only: no persona
    post, amplified post or thread reply (a converted voice's first top-level posts were hidden 33% of the time)."""
    age = voice_age_h(rec, t)
    return bool(config.NEW_VOICE_NO_POST_H) and age is not None and age < config.NEW_VOICE_NO_POST_H


def writes_in(rec, t, window):
    return sum(1 for x in rec.get("day_writes") or () if 0 <= t - x < window)


def rest(rec, t=None, citizen=True):
    """Why this voice may not write now under the human-day rules, or None: "voice_asleep" in its sleep window,
    "voice_capped" at its daily budget (for a write that isn't to a citizen, VOICE_CITIZEN_RESERVE short of it: the
    rest of the day is kept for citizens) or at its hourly cap."""
    t = time.time() if t is None else t
    if config.POOL_SCHEDULER:                  # todo/38: the voice's own life profile replaces the fixed window
        if life_asleep(rec, t):
            return "voice_asleep"
    elif asleep(key_of(rec), t):
        return "voice_asleep"
    if config.VOICE_DAY_CAP:
        cap = config.VOICE_WRITES_PER_DAY - (0 if citizen else config.VOICE_CITIZEN_RESERVE)
        if writes_in(rec, t, DAY_S) >= cap:
            return "voice_capped"
    if config.VOICE_HOUR_CAP and writes_in(rec, t, HOUR_S) >= config.VOICE_WRITES_PER_H:
        return "voice_capped"
    return None


def free_in(rec, t=None):
    """Seconds until this voice may write again (an estimate for backing off a citizen who waits for it)."""
    t = time.time() if t is None else t
    waits = [life_wakes_in(rec, t) if config.POOL_SCHEDULER else wakes_in(key_of(rec), t), rec.get("next_ok", 0) - t]
    times = sorted(x for x in rec.get("day_writes") or () if 0 <= t - x < DAY_S)
    if config.VOICE_HOUR_CAP:
        hour = [x for x in times if t - x < HOUR_S]
        if len(hour) >= config.VOICE_WRITES_PER_H:
            waits.append(hour[len(hour) - config.VOICE_WRITES_PER_H] + HOUR_S - t)
    if config.VOICE_DAY_CAP and len(times) >= config.VOICE_WRITES_PER_DAY:
        waits.append(times[len(times) - config.VOICE_WRITES_PER_DAY] + DAY_S - t)
    return max([0.0] + waits)


def gap_on():
    return config.VOICE_JITTER or config.VOICE_STAGGER or config.POOL_SCHEDULER


def next_gap():
    """Seconds before this voice's next ordinary write: lognormal around VOICE_GAP's median, clipped to its bounds,
    or now and then (VOICE_BREAK_P) a break of VOICE_BREAK_S. Reply-backs, reposts and own-thread answers keep their
    own short gaps (bot.voice_wait): a person answers someone who talks to them."""
    if random.random() < config.VOICE_BREAK_P:
        return random.uniform(*config.VOICE_BREAK_S)
    median, sigma, lo, hi = config.VOICE_GAP
    return min(max(random.lognormvariate(math.log(median), sigma), lo), hi)


def on_write(rec, t=None):
    """After a write by this voice: its time joins day_writes (the last 25 h, kept in the account record) and, with
    VOICE_JITTER, its next ordinary write waits next_gap()."""
    t = time.time() if t is None else t
    rec["day_writes"] = [x for x in rec.get("day_writes") or () if t - x < DAY_S + HOUR_S] + [t]
    if config.POOL_SCHEDULER and _S["active"]:         # todo/38: the voice's life profile and the pool's level set the gap
        rec["next_ok"] = t + schedule_gap(rec, t)
        note_write(t)
    elif config.VOICE_JITTER:
        rec["next_ok"] = t + next_gap()


def stagger(voices, t=None):
    """After a (re)start: each voice waits its own random 0-VOICE_STAGGER_S before its first ordinary write, so they
    don't all start on the same minute."""
    if not config.VOICE_STAGGER:
        return
    t = time.time() if t is None else t
    for r in voices:
        r["next_ok"] = max(r.get("next_ok", 0), t + random.uniform(0, config.VOICE_STAGGER_S))


# ---- one voice per citizen per day ---------------------------------------------------------------------------------
def _fresh(entries, t):
    return [e for e in entries if t - e[0] < config.ONE_VOICE_S]


def owners(state, target, t=None):
    """Our voices that wrote to this target's author, or under the citizen post this target sits under, in the last
    ONE_VOICE_S: state["voice_of"] = {citizen: [[ts, persona], ...]}, state["thread_voice"] = {citizen post: [...]}
    (a citizen's own post, so a news thread with many citizens in it isn't held by one voice)."""
    t = time.time() if t is None else t
    target = target or {}
    root = target.get("root_post_id") or target.get("post_id")
    entries = (state.get("voice_of") or {}).get(str(target.get("author_id")), []) + \
        (state.get("thread_voice") or {}).get(str(root), [])
    return {p for _, p in _fresh(entries, t)}


def owner_problem(state, job, t=None):
    """"voice_owner" when another of our voices has this citizen (or their thread) today and this job's voice isn't
    it, else None. A reply-back is never held: the citizen answered or mentioned this voice."""
    if not one_voice_on() or job["mode"] not in CITIZEN_MODES or job["mode"] == "reply_back":
        return None
    target = job.get("target") or {}
    if not config.is_citizen(target.get("author_id")):
        return None
    mine = owners(state, target, t)
    return "voice_owner" if mine and mine != {job["rec"]["persona"]} else None


def required_voice(state, target, t=None):
    """(persona, None) when one voice has this citizen today, (None, None) when none does, (None, "voice_owner") when
    two do (the citizen mentioned another voice, which answered): then no third reply goes out today."""
    if not one_voice_on() or not config.is_citizen((target or {}).get("author_id")):
        return None, None
    mine = owners(state, target, t)
    if len(mine) > 1:
        return None, "voice_owner"
    return (next(iter(mine)) if mine else None), None


def record(state, target, persona, mode, t=None):
    """After a write to a citizen (CITIZEN_MODES): this voice has them, and their post's thread, for ONE_VOICE_S.
    Kept even with ONE_VOICE_PER_CITIZEN off, for the metric."""
    if mode not in CITIZEN_MODES or not target or not config.is_citizen(target.get("author_id")):
        return
    t = time.time() if t is None else t
    for key, ident in (("voice_of", target["author_id"]),
                       ("thread_voice", None if target.get("reply_to_post_id") else target.get("post_id"))):
        if ident is None:
            continue
        m = state.setdefault(key, {})
        for k in list(m):
            m[k] = _fresh(m[k], t)
            if not m[k]:
                del m[k]
        m.setdefault(str(ident), []).append([t, persona])


# ---- read back the last day on start ---------------------------------------------------------------------------------
def _ts(rec):
    try:
        return dt.datetime.fromisoformat(rec["ts"].replace("Z", "+00:00")).timestamp()
    except (KeyError, ValueError, AttributeError):
        return None


def recent_writes(path, t=None, window=DAY_S + HOUR_S, nbytes=None):
    """Our live writes in the last `window` from the actions log, oldest first: the tail of the file only
    (STEALTH_SEED_BYTES), so a long log costs no more than that."""
    t = time.time() if t is None else t
    nbytes = config.STEALTH_SEED_BYTES if nbytes is None else nbytes
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.seek(max(0, f.tell() - nbytes))
            raw = f.read()
    except OSError:
        return []
    lines = raw.split(b"\n")
    if size:
        lines = lines[1:]                     # the first line may be cut
    out = []
    for line in lines:
        if b'"live": true' not in line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        ts = _ts(rec)
        if (ts is not None and t - ts < window and rec.get("act") in WRITE_MODES and rec.get("post_id")
                and rec.get("live") is True):
            out.append((ts, rec))
    return out


def seed(records, state, path, t=None):
    """On start, the live bot reads its last day of writes back from the actions log (once per field): each voice's
    day_writes (accounts that have none yet) and, when the state has none, who wrote to which citizen (voice_of,
    thread_voice). So the budgets and the one-voice rule hold from the first minute after a deploy."""
    t = time.time() if t is None else t
    voices = [r for r in records if r.get("role", "voice") != "booster" and "day_writes" not in r]
    need_state = "voice_of" not in state
    if not voices and not need_state:
        return
    writes = recent_writes(path, t)
    by_user = collections.defaultdict(list)
    for ts, a in writes:
        by_user[a.get("username")].append(ts)
    for r in voices:
        r["day_writes"] = by_user.get(r.get("username"), [])
    if need_state:
        state.setdefault("voice_of", {})
        state.setdefault("thread_voice", {})
        for ts, a in writes:
            if a.get("act") in CITIZEN_MODES and a.get("persona") and t - ts < config.ONE_VOICE_S:
                target = dict(post_id=a.get("target_post"), author_id=a.get("target_author"),
                              reply_to_post_id=a.get("parent_post"))
                record(state, target, a["persona"], a["act"], ts)


# ---- status.json ---------------------------------------------------------------------------------------------------
def doubles(state, t=None):
    """(citizens written to in the last 24 h, of them by two or more of our voices)."""
    t = time.time() if t is None else t
    hit = [{p for ts, p in v if t - ts < DAY_S} for v in (state.get("voice_of") or {}).values()]
    hit = [v for v in hit if v]
    return len(hit), sum(len(v) >= 2 for v in hit)


def metrics(voices, hidden, state, t=None, status=None):
    """The numbers todo/31 is judged by, for data/status.json: per voice its writes in the last 24 h and since
    Kingstonia midnight, the hours of the last 24 it wrote in, hidden posts, its sleep window and what holds it now;
    team-wide the share of citizens written to by two or more of our voices in 24 h. Targets: 0 doubles,
    <= VOICE_WRITES_PER_DAY writes and <= 16 active hours a voice."""
    t = time.time() if t is None else t
    midnight = dt.datetime.fromtimestamp(t, _tz()).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    per = {}
    for r in voices:
        times = [x for x in r.get("day_writes") or () if 0 <= t - x < DAY_S]
        key = key_of(r)
        per[r["username"]] = dict(
            persona=r.get("persona"), writes_24h=len(times), writes_today=sum(x >= midnight for x in times),
            writes_1h=sum(t - x < HOUR_S for x in times),
            hours_active_24h=len({int((t - x) // HOUR_S) for x in times}),       # of the last 24 hours: at most 24
            hidden=hidden.get(r["username"], 0), sleep=window_text(key) if config.VOICE_SLEEP else None,
            now=(status(r) if status else None) or "free")
    citizens, two = doubles(state, t)
    return dict(
        voices=per,
        team=dict(writes_24h=sum(v["writes_24h"] for v in per.values()),
                  max_writes_24h=max((v["writes_24h"] for v in per.values()), default=0),
                  max_hours_active_24h=max((v["hours_active_24h"] for v in per.values()), default=0),
                  citizens_24h=citizens, citizens_two_voices_24h=two,
                  two_voice_share=round(two / citizens, 3) if citizens else 0.0,
                  now=dict(collections.Counter(v["now"] for v in per.values()))),
        targets=dict(two_voice_share=0.0, writes_per_voice_day=config.VOICE_WRITES_PER_DAY,
                     writes_per_voice_hour=config.VOICE_WRITES_PER_H, hours_active=16),
        rules={k: getattr(config, k) for k in ("VOICE_DAY_CAP", "VOICE_HOUR_CAP", "VOICE_SLEEP", "VOICE_JITTER",
                                               "VOICE_STAGGER", "ONE_VOICE_PER_CITIZEN")})


# ---- todo/38 pool scheduler: stealth bought with voices, never at the cost of volume (2026-10-23) ----------------------
# Four parts, all behind config.POOL_SCHEDULER (False = the longest-rest-first pick of before, nothing here runs):
#   plan(n)            pure: the stealth level L from the number of voices able to write, lowered until the awake
#                      voices' capacity is >= POOL_HEADROOM x POOL_TARGET_RATE; and the mean gap awake that gives;
#   life profile       per voice, drawn once and stored in its record (rec["life"]): sleep window, mean-gap multiplier,
#                      session style, volume multiplier; lazily and deterministically from the username if missing;
#   pick()             a weighted random choice among the voices ready now (how overdue vs its own mean gap, session
#                      state, volume multiplier), O(N), no I/O; schedule_gap() sets the voice's next_ok after a write;
#   rate controller    a global gap multiplier in POOL_MULT_RANGE that tracks POOL_TARGET_RATE from the writes seen in
#                      the last POOL_RATE_WINDOW_S (kept in memory), and relief: a sleeper is woken when the awake
#                      capacity falls under the need (uneven sleep starts), soonest-waking first.
# The per-voice floor ACCOUNT_MIN_GAP_S (4 min) is never shortened. All state lives in _S behind _LOCK, so the drafters
# and the writer (which already hold Accounts' mu) can call it freely.
LIFE_SLEEP_H = (6.0, 9.0)                       # a voice's full sleep window (hours of the Sydney clock)
LIFE_GAP_SIGMA, LIFE_GAP_CLIP = 0.25, (0.7, 1.45)    # log-normal mean-gap multiplier around 1
LIFE_BURST = (1, 4)                             # writes in a session before its break
LIFE_VOL_SIGMA, LIFE_VOL_CLIP = 0.2, (0.7, 1.4)      # daily-volume multiplier: the voice's weight in the pick
GAP_NOISE_SIGMA = 1.1                           # at L = 1: mean-preserving log-normal noise on a gap's part above the floor
BURST_COMPRESS = 0.35                           # at L = 1 the gaps inside a session are 35% shorter than the mean gap
BURST_BOOST = 1.6                               # weight factor of a voice in mid-session (at L = 1)
OVERDUE_CAP = 3.0                               # overdue (in mean gaps) beyond which a waiting voice gains no more weight
WEIGHT_POWER = 0.75                             # weight = (1 + overdue) ** this: 0 = flat among the ready, large = longest-rest
REFRESH_CACHE_S = 3.0
LIFE_KEYS = ("sleep_start", "sleep_h", "gap_mult", "burst_max", "vol_mult", "seed")
_LOCK = threading.RLock()
_RNG = random.Random()
_SESS = {}                                      # username -> writes left in its current session (memory only)


def _fresh_state():
    return dict(active=False, n=0, level=0.0, mean_gap_s=float(config.ACCOUNT_MIN_GAP_S), plan=None, relief=frozenset(),
                one_voice=False, at=0.0, since=None, mult=1.0, mult_hi=1.0, mult_at=0.0, awake=0, asleep=0,
                writes=collections.deque(), empties=collections.deque())


_S = _fresh_state()


def reset():
    """Forget the pool's state (tests, and a restart in-process): level 0, multiplier 1, no sessions or observations."""
    with _LOCK:
        _S.clear()
        _S.update(_fresh_state())
        _SESS.clear()


def plan(n, target=None, floor_s=None, headroom=None):
    """The calibrator (pure): from n voices able to write, the stealth level and the mean gap that keep the capacity.
      wanted = clip((n - N_LO) / (N_HI - N_LO), 0, 1)                       0 up to N_LO = 13, 1 from N_HI = 28
      awake(L) = n (1 - SLEEP_PLAN_FRAC L)                                   expected awake voices (0.40: mean 7.5 h = 31% + slack)
      need = HEADROOM x target                                               3.335 writes/min at 2.9
      L <= (n - need floor) / (SLEEP_PLAN_FRAC n + need floor GAP_SLACK)     awake(L) / (floor (1 + GAP_SLACK L)) >= need
      mean gap awake = max(floor, awake / need)                              so capacity = awake / mean gap = need
    floor is ACCOUNT_MIN_GAP_S. L = min(wanted, that bound), floored at 0 and rounded down to 0.001. Below about 14
    voices need is out of reach even at L = 0 (n / floor < need): feasible is False and capacity is the physical n / floor.
    Returns dict(n, level, wanted, awake, mean_gap_s, capacity, capacity_ratio, need, feasible, target, floor_s)."""
    target = config.POOL_TARGET_RATE if target is None else target
    floor_s = config.ACCOUNT_MIN_GAP_S if floor_s is None else floor_s
    need = (config.POOL_HEADROOM if headroom is None else headroom) * target
    floor, a, b = floor_s / 60.0, config.STEALTH_SLEEP_PLAN_FRAC, config.STEALTH_GAP_SLACK
    lo, hi = config.STEALTH_N_LO, config.STEALTH_N_HI
    n = max(0, int(n))
    wanted = 0.0 if n <= lo else min(1.0, (n - lo) / (hi - lo))
    bound = (n - need * floor) / (a * n + need * floor * b) if n else -1.0
    level = math.floor(max(0.0, min(wanted, bound)) * 1000) / 1000
    awake = n * (1 - a * level)
    gap_min = max(floor, awake / need) if n else floor
    capacity = awake / gap_min if n else 0.0
    return dict(n=n, level=level, wanted=round(wanted, 3), awake=round(awake, 2), mean_gap_s=gap_min * 60,
                capacity=capacity, capacity_ratio=capacity / target if target else 0.0, need=need,
                feasible=capacity >= need - 1e-9, target=target, floor_s=floor_s)


# ---- the life profile -------------------------------------------------------------------------------------------------
def valid_life(life):
    return isinstance(life, dict) and all(k in life for k in LIFE_KEYS)


def _circ(a, b):
    d = abs(a - b) % 24
    return min(d, 24 - d)


def _mid(life):
    return (life["sleep_start"] + life["sleep_h"] / 2) % 24


def life_profile(rng=None, n_writers=None, taken=()):
    """One voice's life, drawn once: sleep_start (Sydney hour the full sleep window starts) and sleep_h (6-9 h; the pool
    level L scales the window around its middle), gap_mult (log-normal around 1: this voice's share of the mean gap),
    burst_max (1-4 writes a session, then its break), vol_mult (weight in the pick: voices differ in daily volume), seed.
    taken: the middles of the windows already drawn; the start is the best of several candidates (more with more
    writers) farthest from them, so the starts spread across the day."""
    rng = rng or random.Random()
    sleep_h = rng.uniform(*LIFE_SLEEP_H)
    k = max(6, min(24, int(n_writers or 16))) if taken else 1
    mids = [rng.uniform(0, 24) for _ in range(k)]
    mid = max(mids, key=lambda m: min((_circ(m, x) for x in taken), default=24.0))
    clip = lambda v, c: min(max(v, c[0]), c[1])
    return dict(sleep_start=round((mid - sleep_h / 2) % 24, 2), sleep_h=round(sleep_h, 2),
                gap_mult=round(clip(rng.lognormvariate(0, LIFE_GAP_SIGMA), LIFE_GAP_CLIP), 3),
                burst_max=rng.randint(*LIFE_BURST),
                vol_mult=round(clip(rng.lognormvariate(0, LIFE_VOL_SIGMA), LIFE_VOL_CLIP), 3), seed=rng.getrandbits(40))


def ensure_life(rec, peers=(), n_writers=None):
    """rec["life"], drawn now when the voice has none: from an rng seeded by its username (sha256), so a record that is
    lost and drawn again gets the same life and a restart never reshuffles the pool. The caller saves the record (the
    life is stored once, then kept). peers: the other voices (their lives keep the sleep starts apart; no two voices
    end up with the same parameters)."""
    life = rec.get("life")
    if valid_life(life):
        return life
    user = rec.get("username") or rec.get("persona") or ""
    rng = random.Random(int(hashlib.sha256(f"life:{user}".encode()).hexdigest()[:16], 16))
    others = [p["life"] for p in peers if p is not rec and valid_life(p.get("life"))]
    taken = [_mid(x) for x in others]
    sig = lambda x: (x["sleep_start"], x["gap_mult"], x["vol_mult"])
    while True:
        life = life_profile(rng, n_writers or len(others) + 1, taken)
        if all(sig(life) != sig(x) for x in others):
            break
    rec["life"] = life
    return life


def _span(life, level):
    """(start, length) in Sydney hours of the sleep window at stealth level `level`: the middle stays, the length scales."""
    length = life["sleep_h"] * level
    return (_mid(life) - length / 2) % 24, length


def life_asleep(rec, t=None, ignore_relief=False):
    """Is this voice in its sleep window now (scaled by the pool's level; none at level 0)? A voice woken by relief is not."""
    level = _S["level"] if _S["active"] else 0.0
    if level <= 0 or not config.POOL_SCHEDULER:
        return False
    if not ignore_relief and rec.get("username") in _S["relief"]:
        return False
    start, length = _span(ensure_life(rec), level)
    return (local_hour(t) - start) % 24 < length


def life_wakes_in(rec, t=None):
    """Seconds until the end of this voice's sleep window (0 when awake)."""
    if not life_asleep(rec, t):
        return 0.0
    start, length = _span(ensure_life(rec), _S["level"])
    return ((start + length - local_hour(t)) % 24) * 3600


# ---- gaps and the weighted pick ---------------------------------------------------------------------------------------
def _gap_at(rec, mult):
    life = rec.get("life")
    m = life["gap_mult"] ** _S["level"] if valid_life(life) else 1.0
    return max(float(config.ACCOUNT_MIN_GAP_S), _S["mean_gap_s"] * mult * m)


def voice_gap_s(rec):
    """This voice's own mean gap between writes while awake: the pool's mean gap x the controller's multiplier x its
    gap_mult ** L, never under the 4-min floor."""
    return _gap_at(rec, _S["mult"])


def schedule_gap(rec, t=None, rng=None):
    """Seconds this voice waits after a write before its next ordinary one (>= the floor, always).
    Its mean is voice_gap_s(rec). At L = 0 that is all. Above it the voice works in sessions of 1..burst_max writes: the
    gaps inside a session are shorter (floor-bound), the break after it longer so the mean holds, and each gap's part
    above the floor gets mean-preserving log-normal noise (sigma GAP_NOISE_SIGMA x L)."""
    rng = rng or _RNG
    floor, L = float(config.ACCOUNT_MIN_GAP_S), _S["level"]
    g = voice_gap_s(rec)
    if L <= 0 or not valid_life(rec.get("life")):
        return g
    with _LOCK:
        user = rec.get("username")
        inside = max(floor, g * (1 - BURST_COMPRESS * L))
        if _SESS.get(user, 0) > 0:
            _SESS[user] -= 1
            base = inside
        else:
            b = rng.randint(max(1, rec["life"]["burst_max"] - 1), rec["life"]["burst_max"])
            _SESS[user] = b - 1
            base = max(floor, b * g - (b - 1) * inside)
    sigma = GAP_NOISE_SIGMA * L
    noise = math.exp(sigma * rng.gauss(0, 1) - sigma * sigma / 2)
    gap = floor + (base - floor) * min(noise, 4.0) + rng.uniform(0, 20 * L)
    return max(floor, min(gap, 4 * max(base, g)))


def weight(rec, t=None):
    """A ready (or nearly ready) voice's weight in the pick: (1 + overdue) ** WEIGHT_POWER, overdue = how long past its own next_ok
    in its mean gaps (capped, and as low as -0.9 for a voice still in its gap: assignable), x vol_mult ** L, x
    BURST_BOOST ** L while it is mid-session."""
    t = time.time() if t is None else t
    L = _S["level"]
    due = max(rec.get("next_ok", 0), rec.get("last_write", 0) + config.ACCOUNT_MIN_GAP_S)
    w = (1 + min(OVERDUE_CAP, max(-0.9, (t - due) / voice_gap_s(rec)))) ** WEIGHT_POWER
    if L > 0 and valid_life(rec.get("life")):
        w *= rec["life"]["vol_mult"] ** L
        if _SESS.get(rec.get("username"), 0) > 0:
            w *= BURST_BOOST ** L
    return w


def pick(candidates, t=None, rng=None):
    """Who writes next: a weighted random choice among `candidates` (the voices ready now, or free to be assigned).
    O(len), no I/O, no sleeping. None for an empty list."""
    if not candidates:
        return None
    t = time.time() if t is None else t
    with _LOCK:
        weights = [weight(r, t) for r in candidates]
    return (rng or _RNG).choices(candidates, weights=weights)[0]


# ---- the pool: refresh (level, relief, controller) -----------------------------------------------------------------------
def refresh(records, t=None):
    """Called by Accounts before it picks (live only): `records` are the voices able to write. Gives each a life if it has
    none (returns True then: the caller saves), sets N, L and the mean gap from plan(), the ONE_VOICE hysteresis, the
    relief set, and steps the rate controller. Cached for REFRESH_CACHE_S while nothing changed."""
    if not config.POOL_SCHEDULER:
        return False
    t = time.time() if t is None else t
    with _LOCK:
        have = [r for r in records if valid_life(r.get("life"))]
        created = False
        for r in records:
            if not valid_life(r.get("life")):
                ensure_life(r, have, len(records))
                have.append(r)
                created = True
        n = len(records)
        if not created and _S["active"] and n == _S["n"] and 0 <= t - _S["at"] < REFRESH_CACHE_S:
            return False
        p = plan(n)
        _S.update(active=True, n=n, level=p["level"], mean_gap_s=p["mean_gap_s"], plan=p, at=t)
        if _S["since"] is None:
            _S["since"] = t
        if n >= config.ONE_VOICE_AUTO_N:
            _S["one_voice"] = True
        elif n < config.ONE_VOICE_AUTO_OFF_N:
            _S["one_voice"] = False
        _relieve(records, t, p)
        _control(t, p)
        return created


def _relieve(records, t, p):
    """Wake sleepers, soonest-waking first, while the awake voices' capacity (at the plan's multiplier 1) is under the
    need: the hard invariant holds on the actual pool at this minute, not only in expectation."""
    awake_cap, sleepers = 0.0, []
    for r in records:
        if life_asleep(r, t, ignore_relief=True):
            start, length = _span(ensure_life(r), _S["level"])
            sleepers.append(((start + length - local_hour(t)) % 24, r["username"]))
        else:
            awake_cap += 60.0 / _gap_at(r, 1.0)
    relief = set()
    for _, user in sorted(sleepers):
        if awake_cap >= p["need"]:
            break
        relief.add(user)
        awake_cap += 60.0 / _gap_at(next(r for r in records if r["username"] == user), 1.0)
    _S.update(relief=frozenset(relief), awake=len(records) - len(sleepers) + len(relief),
              asleep=len(sleepers) - len(relief))


def note_write(t=None):
    """A write happened (on_write): it joins the observations the rate controller reads."""
    t = time.time() if t is None else t
    with _LOCK:
        _S["writes"].append(t)
        while _S["writes"] and t - _S["writes"][0] > config.POOL_RATE_WINDOW_S:
            _S["writes"].popleft()


def note_empty(t=None):
    """The picker found no voice ready (voices exist but all are in their gap, asleep or reserved): the controller reads
    these as 'voices are the limit' before it shortens the gaps."""
    t = time.time() if t is None else t
    with _LOCK:
        _S["empties"].append(t)
        while _S["empties"] and t - _S["empties"][0] > 600:
            _S["empties"].popleft()


def observed_rate(t=None):
    """Team writes per minute over the last POOL_RATE_WINDOW_S (or since start, if shorter); None under 5 min of data."""
    t = time.time() if t is None else t
    with _LOCK:
        if _S["since"] is None:
            return None
        span = min(config.POOL_RATE_WINDOW_S, t - _S["since"])
        if span < 300:
            return None
        return sum(1 for x in _S["writes"] if t - x <= config.POOL_RATE_WINDOW_S) / (span / 60.0)


def _control(t, p):
    """The rate controller: a global multiplier on every voice's mean gap, one step a minute at most, in POOL_MULT_RANGE.
    The upper end is also bounded by the capacity (mult <= capacity / need, which is 1 when the plan sits on the need):
    stealth never buys a gap that takes the pool under HEADROOM x target. Sagging below target with the picker finding
    nobody ready (voices are the limit): shorter gaps, by up to 15% a step. Above the ceiling: longer, within the bound.
    On target: hold; after 5 quiet minutes with the rate still at target, drift back to 1."""
    lo, hi = config.POOL_MULT_RANGE
    bound = max(1.0, min(hi, p["capacity"] / p["need"])) if p["n"] and p["need"] else 1.0
    _S["mult_hi"] = bound
    m = _S["mult"]
    if t - _S["mult_at"] >= 60:
        _S["mult_at"] = t
        obs = observed_rate(t)
        if obs is not None:
            target, ceiling = config.POOL_TARGET_RATE, config.POOL_RATE_CEILING
            err = (target - obs) / target
            starved = any(t - e < 300 for e in _S["empties"])
            if obs > ceiling:
                m *= 1 + min(0.10, (obs - ceiling) / ceiling * 2 + 0.02)
            elif err > 0.03 and starved:
                m *= 1 - min(0.15, 0.5 * err)
            elif err <= 0.03 and not starved and m != 1.0:
                m += (1.0 - m) * 0.05
    _S["mult"] = min(max(m, lo), bound)


def one_voice_on():
    """ONE_VOICE_PER_CITIZEN as it is effective now: the config value, or on automatically (ONE_VOICE_AUTO) while the
    pool has ONE_VOICE_AUTO_N (24) writers or more, off again under ONE_VOICE_AUTO_OFF_N (22)."""
    return bool(config.ONE_VOICE_PER_CITIZEN or (config.POOL_SCHEDULER and config.ONE_VOICE_AUTO and _S["one_voice"]))


def second_voice_arms():
    """config.SECOND_VOICE_ARMS, less the 'fast' arm (a second voice 1-4 min after the first: the pattern a reply-ring
    report is made of) once the pool is bigger than SECOND_FAST_MAX_N."""
    arms = dict(config.SECOND_VOICE_ARMS)
    if config.POOL_SCHEDULER and _S["active"] and _S["n"] > config.SECOND_FAST_MAX_N and len(arms) > 1:
        arms.pop("fast", None)
    return arms


def controller_status(t=None):
    """The scheduler's numbers for data/status.json (plain JSON types)."""
    t = time.time() if t is None else t
    with _LOCK:
        p = _S["plan"] or {}
        obs = observed_rate(t)
        return dict(
            enabled=bool(config.POOL_SCHEDULER), active=_S["active"], n_writers=_S["n"], level=_S["level"],
            wanted_level=p.get("wanted"), mean_gap_s=round(_S["mean_gap_s"], 1), capacity_per_min=round(p.get("capacity", 0.0), 3),
            capacity_ratio=round(p.get("capacity_ratio", 0.0), 3), need_per_min=round(p.get("need", 0.0), 3),
            feasible=p.get("feasible"), awake=_S["awake"], asleep=_S["asleep"], relieved=len(_S["relief"]),
            mult=round(_S["mult"], 3), mult_range=[config.POOL_MULT_RANGE[0], round(_S["mult_hi"], 3)],
            observed_rate=None if obs is None else round(obs, 3), target_rate=config.POOL_TARGET_RATE,
            ceiling=config.POOL_RATE_CEILING, over_ceiling=bool(obs is not None and obs > config.POOL_RATE_CEILING),
            empties_5m=sum(1 for e in _S["empties"] if t - e < 300), one_voice_effective=one_voice_on(),
            second_fast=("fast" in second_voice_arms()))
