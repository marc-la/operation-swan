"""Account budget (todo/39, 2026-10-24): how many accounts the planned writing will cost, and whether the reserve for the
x4 days (1-2 Nov) survives. A FORECAST and an ALERT only: nothing here throttles or blocks the pool. Marc cuts writes by
hand (POOL_WRITERS / SWAN_VOICE_WRITES_PER_DAY, runbook "Account budget"). PURE: no I/O, no clock, no globals; the
caller passes the voices, the plan and the time. swan_bot/config.py holds the numbers (BAN_PLAN, LEFT_GOAL, BAN_PATH...),
scripts/swan_watch.py runs it every 20 min, the dashboard (todo/42) shows it.

  km_writes_per_ban   the life of a voice in writes: Kaplan-Meier median of writes at ban (a ban is the event, a voice
                      still alive is censored at its writes so far) with a seeded bootstrap interval. 23 Oct: ~145 [127, 178]
  forecast_days       per Sydney day: planned writes / writes-per-ban = bans; each ban takes one spare registration to
                      replace it while spare lasts, so alive stays at its cap until spare is 0
  reserve_status      accounts LEFT at the end of the goal day against the goal. "Left" is the one term for the account
                      budget (Marc, 24 Oct): accounts not banned = alive + not yet registered = allowance - banned
  ban_path            the cumulative-bans path Marc steers by (config.BAN_PATH), interpolated between its given days
  ban_alert           plain sentences when accounts left is off track or the last 24 h ran well over the forecast
"""
import datetime as dt
import math
import random
import re
from zoneinfo import ZoneInfo

BOOT_N = 1000                       # bootstrap resamples (fixed seed: the same voices always give the same interval)
BOOT_SEED = 3908
BOOT_MIN_BANS = 5                   # an interval from fewer bans than this is noise: lo and hi are None
OVER_FACTOR = 1.5                   # bans in 24 h above this x the forecast...
OVER_MIN_BANS = 4                   # ...and at least this many (one or two bans are a coin toss at ~12 a day)
SYDNEY = "Australia/Sydney"         # competition days roll over at midnight here (9pm Perth); AEDT, UTC+11, from 4 Oct 2026

# Text writes: what a hide or a ban is counted against (hide-risk-analysis-2026-10-23: replies, posts, threads; not likes
# or reposts). The act names are the actions log's.
TEXT_WRITES = ("post", "reply", "reply_back", "second_voice", "journalist", "thread", "thread_answer")


# ---- the life of a voice -----------------------------------------------------------------------------------------------
def _km_median(pairs):
    """Median of the Kaplan-Meier curve over (writes, banned) pairs: the first writes value where survival is <= 0.5, or
    None when it never gets that low (too few bans). At a tie a ban is taken before a censored voice."""
    pairs = sorted(pairs)
    at_risk, surv, i = len(pairs), 1.0, 0
    while i < len(pairs):
        t, bans, j = pairs[i][0], 0, i
        while j < len(pairs) and pairs[j][0] == t:
            bans += pairs[j][1]
            j += 1
        if bans:
            surv *= 1.0 - bans / at_risk
            if surv <= 0.5:
                return float(t)
        at_risk -= j - i
        i = j
    return None


def km_writes_per_ban(voices):
    """voices: [{"writes": int, "banned": bool}]. {"median", "lo", "hi", "n_banned", "n_alive"}: the Kaplan-Meier
    median writes at ban (a voice still alive is censored), and a 95% bootstrap interval (BOOT_N resamples of the
    voices, seeded, so the same input gives the same answer) that is None with fewer than BOOT_MIN_BANS bans. A resample
    whose curve never reaches 0.5 counts as infinite: an end of the interval that lands there is None."""
    pairs = [(int(v.get("writes") or 0), bool(v.get("banned"))) for v in voices]
    n_banned = sum(b for _, b in pairs)
    out = {"median": _km_median(pairs), "lo": None, "hi": None, "n_banned": n_banned, "n_alive": len(pairs) - n_banned}
    if n_banned < BOOT_MIN_BANS:
        return out
    rng = random.Random(BOOT_SEED)
    meds = sorted(math.inf if m is None else m for m in
                  (_km_median([rng.choice(pairs) for _ in pairs]) for _ in range(BOOT_N)))
    lo, hi = meds[int(0.025 * BOOT_N)], meds[int(0.975 * BOOT_N)]
    out["lo"], out["hi"] = (None if lo == math.inf else lo), (None if hi == math.inf else hi)
    return out


# ---- the forecast ------------------------------------------------------------------------------------------------------
def _date(day):
    return day if isinstance(day, dt.date) else dt.date.fromisoformat(str(day))


def plan_for_day(plan, day):
    """Planned writes for a Sydney day: its own entry; a day not in the plan takes the last given day's value (the
    latest entry before it, else the earliest entry); 0 for an empty plan."""
    if not plan:
        return 0.0
    key = _date(day).isoformat()
    if key in plan:
        return float(plan[key])
    earlier = [d for d in plan if d < key]
    return float(plan[max(earlier) if earlier else min(plan)])


def forecast_days(plan, writes_per_ban, alive, spare, first_day, last_day):
    """One row per Sydney day, first_day to last_day inclusive: {"day", "planned_writes", "forecast_bans" (planned writes /
    writes_per_ban, a float), "alive_end", "spare_end", "left_end" (alive_end + spare_end: accounts not banned)}. alive and spare are the counts at the start of first_day. Each
    forecast ban is replaced by one spare registration while spare > 0 (the pool holds alive at its cap), so alive only
    falls once spare is 0. Days missing from plan use plan_for_day's fallback. Days are 'YYYY-MM-DD' strings or dates."""
    if not writes_per_ban or writes_per_ban <= 0:
        raise ValueError("writes_per_ban must be positive")
    rows, day, last = [], _date(first_day), _date(last_day)
    alive, spare = float(alive), float(spare)
    while day <= last:
        planned = plan_for_day(plan, day)
        bans = planned / writes_per_ban
        replaced = min(bans, spare)
        spare -= replaced
        alive = max(0.0, alive - (bans - replaced))
        rows.append({"day": day.isoformat(), "planned_writes": planned, "forecast_bans": bans,
                     "alive_end": alive, "spare_end": spare, "left_end": alive + spare})
        day += dt.timedelta(days=1)
    return rows


def reserve_status(days, left_goal, goal_day):
    """{"left_on_day", "goal", "delta" (left - goal), "on_track" (delta >= 0)} from the row of goal_day: accounts left (not
    banned: alive plus not yet registered) at the END of that day. A goal_day not in days gives None for left, delta
    and on_track."""
    row = next((r for r in days if str(r["day"]) == str(_date(goal_day).isoformat())), None)
    if row is None:
        return {"left_on_day": None, "goal": left_goal, "delta": None, "on_track": None}
    left = row["left_end"]
    return {"left_on_day": left, "goal": left_goal, "delta": left - left_goal, "on_track": left - left_goal >= 0}


def ban_path(path, day):
    """Cumulative bans Marc steers by at the END of a Sydney day: path is {'YYYY-MM-DD': bans}, a few given days with the
    days between interpolated in a straight line. None before the first given day or after the last (no path there)."""
    pts = sorted((_date(k), float(v)) for k, v in (path or {}).items())
    d = _date(day)
    if not pts or d < pts[0][0] or d > pts[-1][0]:
        return None
    for (d0, v0), (d1, v1) in zip(pts, pts[1:] + [pts[-1]]):
        if d0 <= d <= d1:
            return v0 if d1 == d0 else v0 + (v1 - v0) * (d - d0).days / (d1 - d0).days
    return None


def _n(x):
    return f"{x:.0f}"


def ban_alert(actual_bans_24h, forecast_bans_24h, status, goal_day=None):
    """Plain sentences, [] when there is nothing to say. One when accounts left is off track (status["on_track"] is False),
    one when the last 24 h of bans is over OVER_FACTOR x the forecast and at least OVER_MIN_BANS. goal_day (optional,
    a 'YYYY-MM-DD') only names the date in the text."""
    out = []
    if status and status.get("on_track") is False:
        when = f" on {_date(goal_day).strftime('%d %b')}" if goal_day else " on the goal day"
        out.append(f"Accounts left is off track: forecast {_n(status['left_on_day'])} not banned (alive plus not yet registered)"
                   f"{when} against the goal of {_n(status['goal'])} ({_n(-status['delta'])} short). "
                   f"To close it, cut planned writes by hand (runbook 'Account budget': POOL_WRITERS, SWAN_VOICE_WRITES_PER_DAY) "
                   f"and update config.BAN_PLAN.")
    if actual_bans_24h >= OVER_MIN_BANS and actual_bans_24h > OVER_FACTOR * forecast_bans_24h:
        out.append(f"Bans are running over forecast: {_n(actual_bans_24h)} accounts banned in the last 24 h against "
                   f"{_n(forecast_bans_24h)} forecast (alert at more than {OVER_FACTOR}x). "
                   f"Accounts left falls faster than the plan assumes.")
    return out


# ---- de-duplication of alerts (pure: the state dict is the caller's) --------------------------------------------------
def alert_key(text):
    """The alert with its numbers and dates blanked, so 'forecast 41 spare' and 'forecast 40 spare' are the same alert."""
    return re.sub(r"\d+(?:[.,]\d+)?", "#", text)


def due_alerts(texts, sent, now, gap_s):
    """(texts to send now, new sent-state). sent: {alert_key: epoch of the last send}. A text whose key went out less than
    gap_s ago is held back; keys older than gap_s are dropped from the state."""
    keep = {k: t for k, t in (sent or {}).items() if 0 <= now - t < gap_s}
    due = []
    for text in texts:
        key = alert_key(text)
        if key not in keep:
            due.append(text)
            keep[key] = now
    return due, keep


# ---- the box's data -> the inputs --------------------------------------------------------------------------------------
def sydney_day(ts, tz=SYDNEY):
    """'YYYY-MM-DD' of the Sydney day an epoch time falls in (the day rolls at midnight Sydney)."""
    return dt.datetime.fromtimestamp(ts, ZoneInfo(tz)).date().isoformat()


def day_left_fraction(ts, tz=SYDNEY):
    """Share of the Sydney day (0 to 1] from ts to the next midnight there; a 23 h or 25 h day counts as it is."""
    zone = ZoneInfo(tz)
    now = dt.datetime.fromtimestamp(ts, zone)
    start = dt.datetime.combine(now.date(), dt.time(), zone)
    end = dt.datetime.combine(now.date() + dt.timedelta(days=1), dt.time(), zone)
    return (end.timestamp() - ts) / (end.timestamp() - start.timestamp())


def text_writes_by_voice(rows):
    """{username: distinct post ids} of live text writes (TEXT_WRITES) in action-log rows; rows without a post id are
    ignored (a write that did not happen has none). The same count watch.LogScan keeps while it streams the log."""
    out = {}
    for r in rows:
        if r.get("live") and r.get("act") in TEXT_WRITES and r.get("username") and r.get("post_id"):
            out.setdefault(r["username"], set()).add(r["post_id"])
    return {u: len(ids) for u, ids in out.items()}


def build_voices(writes, records, portal_suspended=()):
    """The voices list for km_writes_per_ban: [{"username", "writes", "banned"}]. writes: {username: text writes}.
    records: the account records (secrets/swan_accounts.json). portal_suspended: usernames in the portal's
    account_log.suspended. A voice is a record with a role other than "booster" (a converted booster has role "voice")
    that is active or suspended, or a username the portal says was suspended; banned = on the portal's list, or the record
    says suspended (the portal's names lag its counts and a missing file leaves only the records). A voice alive with no
    writes yet is left out: it is censored at 0 and says nothing."""
    portal = {u for u in portal_suspended if u}
    voices = {}
    for r in records:
        u = r.get("username")
        if not u or r.get("role", "voice") == "booster" or r.get("status", "active") not in ("active", "suspended"):
            continue
        voices[u] = r.get("status", "active") == "suspended"
    for u in portal:
        voices[u] = True
    out = []
    for u in sorted(voices):
        w = int(writes.get(u, 0))
        if voices[u] or u in portal or w > 0:
            out.append({"username": u, "writes": w, "banned": bool(voices[u] or u in portal)})
    return out


def epoch(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    try:
        d = dt.datetime.fromisoformat(str(v))
    except ValueError:
        return None
    return (d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)).timestamp()


def bans_in_window(counts, suspended_ts, now, window_s=24 * 3600):
    """Bans in the last window_s. counts: the portal's [{ts, registered, banned}] rows (they move before the names do): the
    rise in banned since the last row at or before now - window_s, when there is one. Otherwise the number of
    suspended_ts (epochs, from the portal's names and the records) in the window."""
    rows = sorted(((epoch(c.get("ts")), c.get("banned")) for c in counts or []
                   if epoch(c.get("ts")) is not None and isinstance(c.get("banned"), int)))
    before = [b for t, b in rows if t <= now - window_s]
    latest = [b for t, b in rows if t <= now]
    if before and latest:
        return max(0, latest[-1] - before[-1])
    return sum(1 for t in suspended_ts if now - window_s < t <= now)


def account_counts(portal, records, total_cap):
    """(alive, spare) now. The portal's team-page counts first ({registered, banned, max_total, max_active}), then the
    newest account_log.counts row, then the records (every record not "failed" is a used registration; alive = active or
    pending). None when there is neither (a missing file must not read as 200 spare)."""
    acc = (portal or {}).get("accounts") or {}
    if not isinstance(acc.get("registered"), int) or not isinstance(acc.get("banned"), int):
        rows = [c for c in ((portal or {}).get("account_log") or {}).get("counts") or []
                if isinstance(c.get("registered"), int) and isinstance(c.get("banned"), int)]
        acc = max(rows, key=lambda c: epoch(c.get("ts")) or 0) if rows else {}
    if isinstance(acc.get("registered"), int) and isinstance(acc.get("banned"), int):
        cap = acc.get("max_total") if isinstance(acc.get("max_total"), int) else total_cap
        return acc["registered"] - acc["banned"], max(0, cap - acc["registered"])
    used = [r for r in records if r.get("status", "active") != "failed"]
    if not used:
        return None
    alive =[r for r in used if r.get("status", "active") in ("active", "pending")]
    return len(alive), max(0, total_cap - len(used))
