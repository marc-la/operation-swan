"""Hidden-post watch and ring self-audit (read-only); scripts/swan_watch.py runs it every 20 min on EC2.

A moderator-hidden post answers 404 "post not found" and drops out of its author's post list (checked 2026-10-21 on
@lani_wharfcafe23, suspended the day before with one hidden post; we never delete posts). One hidden post plus
≥100 actions means the next inauthentic-account report suspends the voice; three hidden posts suspend it outright
(scoring guide §3). So:
  hidden   every run: each voice's logged posts vs its post list; a missing one that answers 404 is hidden. The
           counts go to data/swan_watch.json, which the bot reads (Accounts.hidden): config.HIDDEN_OFF_AMP hidden
           posts take a voice off amplified posts and threads, config.HIDDEN_STOP stop it writing.
  ring     hourly: scripts/ring_audit.py's score on our last amplified posts and on Trending (others' posts only).
           Alert when our median reaches the leaders' median: that's when Blue reporters rank us next to them.
  budget   every run: the account forecast (swan_bot/budget.py, todo/39) to config.BUDGET_END_DAY and an alert when the
           spare registrations on config.RESERVE_DAY fall under config.RESERVE_GOAL or bans run over the forecast. It
           changes nothing; Marc cuts writes by hand (runbook "Account budget").
"""
import collections
import datetime as dt
import json
import os
import statistics

import capturethenarrative as ctn

from . import budget, config
from .analysis import ts_of

WATCH_FILE = config.DATA / "swan_watch.json"
WATCH_LOG = config.LOGS / "swan_watch.jsonl"
WRITES = {"post", "reply", "second_voice", "reply_back", "thread", "thread_answer", "journalist", "repost"}
SETTLE_S = 120              # a post this new may not be listed yet
MAX_CONFIRM = 60            # get_post confirmations per run (read budget: 300/min per endpoint, shared with the bot)
RING_EVERY_S = 3600
RING_OURS, RING_TRENDING = 8, 20
RING_ALERT_GAP_S = 6 * 3600
BUDGET_FILE = config.DATA / "swan_budget.json"      # the account-budget job's state: alerts sent, the last forecast (todo/39)
PORTAL_FILE = config.DATA / "portal.json"           # swan_dash/portal.py: team-page counts and the suspension messages


def load(path=None):
    try:
        return json.loads((path or WATCH_FILE).read_text())
    except (OSError, ValueError):
        return {}


def save(state, path=None):
    path = path or WATCH_FILE
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1))
    os.replace(tmp, path)                     # the bot reads this file: never let it see half a write


def logged_posts(rows, now):
    """{username: {post_id, ...}} of our live writes old enough to be listed."""
    out = {}
    for r in rows:
        if r.get("live") and r.get("post_id") and r.get("act") in WRITES and r.get("username"):
            try:
                ts = ts_of(r["ts"])
            except (KeyError, ValueError):
                continue
            if now - ts >= SETTLE_S:
                out.setdefault(r["username"], set()).add(r["post_id"])
    return out


class LogScan:
    """What swan_watch takes from the action log, gathered in one pass over its live rows (the log was 118 MB and 656k
    lines on 23 Oct: holding every row was a process the OOM killer took, todo/34). Feed it rows with a truthy "live";
    others are ignored, as the three readers it replaces (logged_posts, the per-voice action count, the amp_plan list)
    all required one."""

    def __init__(self):
        self.first_ts = {}                                    # username -> {post_id: earliest ts of a write row}
        self.actions = collections.Counter()                  # username -> live rows
        self.plans = collections.deque(maxlen=RING_OURS)      # post ids of the last RING_OURS live amp_plan rows
        self.text_ids = {}                                    # username -> post ids of live text writes (budget.TEXT_WRITES)

    def add(self, r):
        if not r.get("live"):
            return
        self.actions[r.get("username")] += 1
        if r.get("post_id") and r.get("act") == "amp_plan":
            self.plans.append(r["post_id"])
        if r.get("post_id") and r.get("act") in budget.TEXT_WRITES and r.get("username"):
            self.text_ids.setdefault(r["username"], set()).add(r["post_id"])
        if r.get("post_id") and r.get("act") in WRITES and r.get("username"):
            try:
                ts = ts_of(r["ts"])
            except (KeyError, ValueError):
                return
            seen = self.first_ts.setdefault(r["username"], {})
            seen[r["post_id"]] = min(ts, seen.get(r["post_id"], ts))

    def text_writes(self):
        """{username: live text writes}, as budget.text_writes_by_voice gives over the same rows."""
        return {u: len(ids) for u, ids in self.text_ids.items()}

    def logged_posts(self, now):
        """Same as logged_posts(rows, now): {username: {post_id, ...}} of our live writes old enough to be listed."""
        out = {}
        for username, seen in self.first_ts.items():
            ids = {pid for pid, ts in seen.items() if now - ts >= SETTLE_S}
            if ids:
                out[username] = ids
        return out


def find_hidden(social, voices, logged, known):
    """New hidden posts as [(username, post_id)]: logged, not listed, and get_post answers 404."""
    new, budget = [], MAX_CONFIRM
    for rec in voices:
        mine = logged.get(rec["username"], set()) - set(known.get(rec["username"], []))
        if not mine or not rec.get("account_id"):
            continue
        try:
            listed = {p["post_id"] for p in social.iterate(social.account_posts, rec["account_id"], max_items=3000)}
        except ctn.APIError as e:
            print(f"{rec['username']}: account_posts {e.status} {e.message}")
            continue
        for pid in sorted(mine - listed):
            if budget <= 0:
                return new
            budget -= 1
            try:
                social.get_post(pid)                 # listed late, not hidden
            except ctn.APIError as e:
                if e.status == 404:
                    new.append((rec["username"], pid))
    return new


def ring_medians(ours, trending, score):
    """(our median, the leaders' median) of the ring score, None where a side has no rows."""
    med = lambda rows: statistics.median(score(r) for r in rows) if rows else None
    return med(ours), med(trending)


def ring_alarm(ours_med, leaders_med):
    return ours_med is not None and leaders_med is not None and ours_med >= leaders_med


# ---- account budget (todo/39): a forecast and an alert, nothing is throttled or blocked -------------------------------
def read_json(path):
    try:
        v = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return v if isinstance(v, dict) else {}


def budget_report(now, writes, records, portal):
    """The account budget now, as one dict (None when neither the portal nor the records say how many accounts we have).
    writes: {username: text writes}; records: the account records (usernames, roles, status: nothing secret is read);
    portal: data/portal.json. Writes per ban is the Kaplan-Meier median once config.BUDGET_KM_MIN_BANS bans are measured,
    else config.WRITES_PER_BAN_DEFAULT. Today's plan is cut to the part of the Sydney day left (the bans so far are already
    in alive and spare); bans of the last 24 h are compared with a whole day's plan."""
    counts = budget.account_counts(portal, records, config.POOL_TOTAL_CAP)
    if counts is None:
        return None
    alive, spare = counts
    log = portal.get("account_log") or {}
    names = {s["username"]: budget.epoch(s.get("ts")) for s in log.get("suspended") or [] if s.get("username")}
    km = budget.km_writes_per_ban(budget.build_voices(writes, records, names))
    measured = km["median"] is not None and km["n_banned"] >= config.BUDGET_KM_MIN_BANS and km["median"] > 0
    wpb = km["median"] if measured else float(config.WRITES_PER_BAN_DEFAULT)
    today = budget.sydney_day(now)
    first, last = dt.date.fromisoformat(today), dt.date.fromisoformat(config.BUDGET_END_DAY)
    span = [first + dt.timedelta(days=i) for i in range(max(0, (last - first).days + 1))]
    plan = {d.isoformat(): budget.plan_for_day(config.BAN_PLAN, d) for d in span}      # filled before today's is cut
    full_today = budget.plan_for_day(config.BAN_PLAN, today)
    if today in plan:
        plan[today] = full_today * budget.day_left_fraction(now)
    days = budget.forecast_days(plan, wpb, alive, spare, first, last) if span else []
    status = budget.reserve_status(days, config.RESERVE_GOAL, config.RESERVE_DAY)
    stamps = {u: t for u, t in names.items() if t is not None}
    for r in records:                                  # a suspension the portal's names have not shown yet
        t = budget.epoch(r.get("suspended_at"))
        if r.get("status") == "suspended" and t is not None and r.get("username") not in stamps:
            stamps[r["username"]] = t
    actual = budget.bans_in_window(log.get("counts"), list(stamps.values()), now)
    forecast24 = full_today / wpb
    return dict(ts=now, day=today, alive=alive, spare=spare, writes_per_ban=wpb, measured=measured, km=km, days=days,
                status=status, actual_bans_24h=actual, forecast_bans_24h=forecast24,
                alerts=budget.ban_alert(actual, forecast24, status, config.RESERVE_DAY))


def budget_run(now, writes, records, *, alert, record, dry=False):
    """One 20-minute pass: report, send each new alert once per config.BUDGET_ALERT_GAP_S (the state is BUDGET_FILE), log
    one summary row. dry prints the alerts and sends and saves nothing. A missing file is no error: no data, no alert."""
    rep = budget_report(now, writes, records, read_json(PORTAL_FILE))
    if rep is None:
        print("budget: no account counts (no portal file, no records)")
        return None
    state = read_json(BUDGET_FILE)
    due, sent = budget.due_alerts(rep["alerts"], state.get("sent"), now, config.BUDGET_ALERT_GAP_S)
    record({"act": "budget", "alive": rep["alive"], "spare": rep["spare"], "writes_per_ban": rep["writes_per_ban"],
            "km": rep["km"], "actual_bans_24h": rep["actual_bans_24h"],
            "forecast_bans_24h": round(rep["forecast_bans_24h"], 1), "reserve": rep["status"],
            "alerts": len(rep["alerts"]), "sending": len(due)})
    how = "measured" if rep["measured"] else "default"
    for text in due:
        msg = f"{text} [writes per ban {rep['writes_per_ban']:.0f} ({how}); now alive {rep['alive']}, spare {rep['spare']}]"
        if dry:
            print(f"budget alert (dry, not sent): {msg}")
        else:
            alert(msg)
    if not dry:
        BUDGET_FILE.parent.mkdir(parents=True, exist_ok=True)
        save({"ts": now, "sent": sent, "last": rep}, BUDGET_FILE)
    return rep
