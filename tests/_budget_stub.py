"""Stand-in for src/swan_bot/budget.py (todo/39) until that module is merged: the dashboard (todo/42) imports it, and the
tests must run without it. conftest.py imports this file first; it installs the stub as swan_bot.budget ONLY when the real
module cannot be imported, so once todo/39 is merged the real one is used and this file does nothing.

The four functions have the real signatures; the maths is the minimum that follows them (planned writes / writes per ban =
bans; a ban takes one spare registration while spare lasts). Tests that assert numbers pin `build.budget` to `MODULE`
(this stub) so they do not depend on the real module's choices."""
import datetime as dt
import sys
import types


def _day(d):
    return d if isinstance(d, dt.date) else dt.date.fromisoformat(str(d))


def _km_median(pairs):
    pairs = sorted(pairs)
    at_risk, surv, i = len(pairs), 1.0, 0
    while i < len(pairs):
        t, j, bans = pairs[i][0], i, 0
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
    pairs = [(int(v["writes"]), bool(v["banned"])) for v in voices]
    n = sum(b for _, b in pairs)
    return {"median": _km_median(pairs), "lo": None, "hi": None, "n_banned": n, "n_alive": len(pairs) - n}


def forecast_days(plan, writes_per_ban, alive, spare, first_day, last_day):
    rows, day, last = [], _day(first_day), _day(last_day)
    alive, spare = float(alive), float(spare)
    while day <= last:
        planned = float(plan.get(day.isoformat(), 0))
        bans = planned / writes_per_ban
        replaced = min(bans, spare)
        spare -= replaced
        alive -= bans - replaced
        rows.append({"day": day.isoformat(), "planned_writes": planned, "forecast_bans": bans,
                     "alive_end": alive, "spare_end": spare, "left_end": alive + spare})
        day += dt.timedelta(days=1)
    return rows


def reserve_status(days, reserve_goal, reserve_day):
    row = next((r for r in days if str(r["day"]) == _day(reserve_day).isoformat()), None)
    if row is None:
        return {"left_on_day": None, "goal": reserve_goal, "delta": None, "on_track": None}
    delta = row["left_end"] - reserve_goal
    return {"left_on_day": row["left_end"], "goal": reserve_goal, "delta": delta, "on_track": delta >= 0}


def ban_path(path, day):
    pts = sorted((_day(k), float(v)) for k, v in (path or {}).items())
    d = _day(day)
    if not pts or d < pts[0][0] or d > pts[-1][0]:
        return None
    for (d0, v0), (d1, v1) in zip(pts, pts[1:] + [pts[-1]]):
        if d0 <= d <= d1:
            return v0 if d1 == d0 else v0 + (v1 - v0) * (d - d0).days / (d1 - d0).days


def ban_alert(actual_bans_24h, forecast_bans_24h, status, goal_day=None):
    out = []
    if status and status.get("on_track") is False:
        out.append(f"Accounts left is off track: {-status['delta']:.0f} short of {status['goal']:.0f}.")
    if actual_bans_24h >= 4 and actual_bans_24h > 1.5 * forecast_bans_24h:
        out.append(f"Bans are running over forecast: {actual_bans_24h:.0f} in 24 h against {forecast_bans_24h:.0f}.")
    return out


MODULE = types.ModuleType("swan_bot.budget")
for _f in (km_writes_per_ban, forecast_days, reserve_status, ban_path, ban_alert):
    setattr(MODULE, _f.__name__, _f)


def install():
    try:
        import swan_bot.budget  # noqa: F401
    except ImportError:
        import swan_bot
        sys.modules["swan_bot.budget"] = MODULE
        swan_bot.budget = MODULE


install()
