"""todo/31 stealth, the behaviour half: each voice keeps a human day (todo/31-stealth.md).

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
import time
from zoneinfo import ZoneInfo

from . import config

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
    return rec.get("persona") or rec.get("username")


def writes_in(rec, t, window):
    return sum(1 for x in rec.get("day_writes") or () if 0 <= t - x < window)


def rest(rec, t=None, citizen=True):
    """Why this voice may not write now under the human-day rules, or None: "voice_asleep" in its sleep window,
    "voice_capped" at its daily budget (for a write that isn't to a citizen, VOICE_CITIZEN_RESERVE short of it: the
    rest of the day is kept for citizens) or at its hourly cap."""
    t = time.time() if t is None else t
    if asleep(key_of(rec), t):
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
    waits = [wakes_in(key_of(rec), t), rec.get("next_ok", 0) - t]
    times = sorted(x for x in rec.get("day_writes") or () if 0 <= t - x < DAY_S)
    if config.VOICE_HOUR_CAP:
        hour = [x for x in times if t - x < HOUR_S]
        if len(hour) >= config.VOICE_WRITES_PER_H:
            waits.append(hour[len(hour) - config.VOICE_WRITES_PER_H] + HOUR_S - t)
    if config.VOICE_DAY_CAP and len(times) >= config.VOICE_WRITES_PER_DAY:
        waits.append(times[len(times) - config.VOICE_WRITES_PER_DAY] + DAY_S - t)
    return max([0.0] + waits)


def gap_on():
    return config.VOICE_JITTER or config.VOICE_STAGGER


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
    if config.VOICE_JITTER:
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
    if not config.ONE_VOICE_PER_CITIZEN or job["mode"] not in CITIZEN_MODES or job["mode"] == "reply_back":
        return None
    target = job.get("target") or {}
    if not config.is_citizen(target.get("author_id")):
        return None
    mine = owners(state, target, t)
    return "voice_owner" if mine and mine != {job["rec"]["persona"]} else None


def required_voice(state, target, t=None):
    """(persona, None) when one voice has this citizen today, (None, None) when none does, (None, "voice_owner") when
    two do (the citizen mentioned another voice, which answered): then no third reply goes out today."""
    if not config.ONE_VOICE_PER_CITIZEN or not config.is_citizen((target or {}).get("author_id")):
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
            writes_1h=sum(t - x < HOUR_S for x in times), hours_active_24h=len({int(x // HOUR_S) for x in times}),
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
