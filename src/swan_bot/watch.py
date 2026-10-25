"""Hidden-post watch and ring self-audit (read-only); scripts/swan_watch.py runs it every 20 min on EC2.

A moderator-hidden post answers 404 "post not found" and drops out of its author's post list (checked 2026-10-21 on
@lani_wharfcafe23, suspended the day before with one hidden post; we never delete posts). One hidden post plus
≥100 actions means the next inauthentic-account report suspends the voice; three hidden posts suspend it outright
(scoring guide §3). So:
  hidden   every run: each voice's logged posts vs its post list; a missing one that answers 404 is hidden. The
           counts go to data/swan_watch.json, which the bot reads (Accounts.hidden): config.HIDDEN_OFF_AMP hidden
           posts take a voice off amplified posts and threads, config.HIDDEN_STOP stop it writing.
           todo/40: a voice that is no longer active is still checked for config.WATCH_TAIL_S after its last write, and
           each hide is logged with its write, arms, card and timing (hide_fields), each suspension with the portal's
           time and reason (suspension_fields). Fields are only ever added to logs/swan_watch.jsonl and the state file.
  ring     hourly: scripts/ring_audit.py's score on our last amplified posts and on Trending (others' posts only).
           Alert when our median reaches the leaders' median: that's when Blue reporters rank us next to them.
  budget   every run: the account forecast (swan_bot/budget.py, todo/39) to config.BUDGET_END_DAY and an alert when the
           accounts left (not banned) on config.LEFT_DAY fall under config.LEFT_GOAL or bans run over the forecast. It
           changes nothing; Marc cuts writes by hand (runbook "Account budget").
"""
import collections
import datetime as dt
import json
import os
import re
import statistics
import time

import capturethenarrative as ctn

from . import budget, config, stealth
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
# What a hide record takes from the write's own action row (todo/40 item 5): the experiment arms, so a read-out can split hides by
# arm (sv_delay above all), and who/what wrote it. Only keys the row holds are kept.
HIDE_ARMS = ("sv_delay", "arm", "arm_conv", "arm_eng", "eng_cell", "group", "style", "own_like", "lever", "concede",
             "rebuttal", "ask_kind", "length_band", "reply_mode", "beat", "close", "theme_level", "block_id", "fresh",
             "agree", "amp_level", "target_class")


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


def portal_suspended(path=None, now=None, max_age_s=None):
    """{(username, account_id): {"ts": iso, "why": str}} of the accounts the portal says are suspended, read from the
    dashboard poller's file (config.PORTAL_FILE, account_log.suspended; no network). {} when the file is missing, not
    JSON, not the shape the poller writes, or older than max_age_s by its own `ts` (config.PORTAL_MAX_AGE_S): a stale
    file is no evidence. A malformed entry is skipped on its own. The key is the pair, so a caller matches on both."""
    now = time.time() if now is None else now
    max_age_s = config.PORTAL_MAX_AGE_S if max_age_s is None else max_age_s
    try:
        doc = json.loads((path or config.PORTAL_FILE).read_text())
        read_at = ts_of(doc["ts"])
        rows = doc["account_log"]["suspended"]
        if not isinstance(rows, list):
            return {}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}
    if now - read_at > max_age_s:
        return {}
    out = {}
    for r in rows:
        try:
            name, ident = r["username"], r["id"]
            if not isinstance(name, str) or not name or isinstance(ident, bool) or int(ident) != ident:
                continue
            ts_of(r["ts"])
            out[(name, int(ident))] = dict(ts=r["ts"], why=str(r.get("why") or ""))
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    return out


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
        self.ctx = {}                                         # post_id -> what its write row says (HIDE_ARMS, backend, draft_id...)
        self.actions = collections.Counter()                  # username -> live rows
        self.plans = collections.deque(maxlen=RING_OURS)      # post ids of the last RING_OURS live amp_plan rows
        self.text_ids = {}                                    # username -> post ids of live text writes (budget.TEXT_WRITES)
        self.text_ts = {}                                     # post id -> epoch of its first live text-write row

    def add(self, r):
        if not r.get("live"):
            return
        self.actions[r.get("username")] += 1
        if r.get("post_id") and r.get("act") == "amp_plan":
            self.plans.append(r["post_id"])
        if r.get("post_id") and r.get("act") in budget.TEXT_WRITES and r.get("username"):
            self.text_ids.setdefault(r["username"], set()).add(r["post_id"])
            try:
                self.text_ts[r["post_id"]] = min(ts_of(r["ts"]), self.text_ts.get(r["post_id"], float("inf")))
            except (KeyError, ValueError):
                pass
        if r.get("post_id") and r.get("act") in WRITES and r.get("username"):
            try:
                ts = ts_of(r["ts"])
            except (KeyError, ValueError):
                return
            seen = self.first_ts.setdefault(r["username"], {})
            if r["post_id"] not in seen:                      # the first row of a write is the write
                self.ctx[r["post_id"]] = dict(act=r["act"], ts=ts, backend=r.get("backend"), draft_id=r.get("draft_id"),
                                              length=r.get("length"),
                                              arms={k: r[k] for k in HIDE_ARMS if r.get(k) is not None})
            seen[r["post_id"]] = min(ts, seen.get(r["post_id"], ts))

    def text_writes(self):
        """{username: live text writes}, as budget.text_writes_by_voice gives over the same rows."""
        return {u: len(ids) for u, ids in self.text_ids.items()}

    def text_writes_since(self, since):
        """Live text writes (distinct posts) logged at or after epoch `since`."""
        return sum(t >= since for t in self.text_ts.values())

    def last_write(self, username):
        """Epoch seconds of the voice's latest logged live write, or None."""
        return max(self.first_ts.get(username, {}).values(), default=None)

    def logged_posts(self, now):
        """Same as logged_posts(rows, now): {username: {post_id, ...}} of our live writes old enough to be listed."""
        out = {}
        for username, seen in self.first_ts.items():
            ids = {pid for pid, ts in seen.items() if now - ts >= SETTLE_S}
            if ids:
                out[username] = ids
        return out


def watched(records, scan, now, tail_s=None):
    """The voices to check for hidden posts: every active one, and (todo/40 item 5) a voice that is no longer active for
    config.WATCH_TAIL_S after its last logged write. A post is ruled hidden about 3 h after it is written, so a voice
    suspended on its third hide, or on a report, still has posts awaiting rulings; the watch used to drop it at once."""
    tail_s = config.WATCH_TAIL_S if tail_s is None else tail_s
    out = []
    for r in records:
        if r.get("role", "voice") == "booster" or not r.get("username"):
            continue
        if r.get("status", "active") == "active":
            out.append(r)
            continue
        last = scan.last_write(r["username"])
        if tail_s and last is not None and now - last < tail_s:
            out.append(r)
    return out


def find_hidden(social, voices, logged, known):
    """New hidden posts as [(username, post_id)]: logged, not listed, and get_post answers 404. A voice that is no longer
    active (the watch's tail) is only believed when its post list shows some of its logged posts: a suspended account's
    list may be empty or gone, and then every post of it would read as hidden."""
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
        if rec.get("status", "active") != "active" and not listed & logged.get(rec["username"], set()):
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


def _iso(t):
    return None if t is None else dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat()


def _hours(a, b):
    """Hours from epoch a to b, 2 places, or None when either is missing."""
    return None if a is None or b is None else round((b - a) / 3600, 2)


def handle_shape(username):
    """A handle's form with each run of letters as a and each run of digits as 9 ("ana_fifita_rn27" -> "a_a_a9")."""
    return re.sub(r"\d+", "9", re.sub(r"[a-z]+", "a", (username or "").lower()))


def card_info(rec, records):
    """The attributes of a voice's card and account for a hide record (todo/40 item 5): role, age, place, handle shape,
    original or converted, and re-use of the card. Nothing secret is read: no password, token or code. `records` is the
    whole accounts list, only to count the other accounts that held the same card (all, and the suspended ones)."""
    from . import content                           # only the watch's records need it; the bot has it loaded already
    card = content.PERSONA_BY_KEY.get(rec.get("persona")) or {}
    variant, conv = rec.get("variant") or {}, rec.get("converted") or {}
    origin = "converted" if conv else "activated" if (rec.get("pool") or {}).get("act") == "activate" else "original"
    others = [r for r in records if r is not rec and r.get("persona") and r.get("persona") == rec.get("persona")]
    return dict(persona=rec.get("persona"), role=card.get("role"), place=card.get("place"),
                age=variant.get("age") or card.get("age"), shape=variant.get("shape"),
                handle=handle_shape(rec.get("username")), origin=origin, card_of=conv.get("card_of"),
                card_reuse=len(others), card_reuse_suspended=sum(r.get("status") == "suspended" for r in others))


def hide_fields(rec, records, post_id, scan, prev_hides, portal_hit, now):
    """Fields added to a hidden_post record (todo/40 item 5), all additive: the write (its id, kind, backend, age when
    found: the hide rate wants writes at least 3.6 h old), its arms (sv_delay and the rest), the voice (age at the write,
    card attributes, origin, card re-use), the time since its previous hide, and the portal's suspension time and reason
    when the portal already lists the voice. prev_hides: epoch times this voice's earlier hides were found (before this
    one). after_suspension: the voice was no longer active (the watch's tail, WATCH_TAIL_S)."""
    ctx = scan.ctx.get(post_id) or {}
    wrote = ctx.get("ts")
    return dict(write_id=ctx.get("draft_id"), write_act=ctx.get("act"), write_ts=_iso(wrote),
                write_age_h=_hours(wrote, now), backend=ctx.get("backend"), length=ctx.get("length"),
                arms=ctx.get("arms") or {}, voice_age_h=_hours(stealth.voice_since(rec), wrote),
                card=card_info(rec, records), hides_before=len(prev_hides),
                since_prev_hide_h=_hours(prev_hides[-1], now) if prev_hides else None,
                after_suspension=rec.get("status", "active") != "active",
                portal=dict(ts=portal_hit["ts"], why=portal_hit["why"]) if portal_hit else None)


def suspension_fields(rec, records, portal_hit, hide_times, hidden_n, scan):
    """The record of a voice's suspension as the portal states it (act "suspension", logged once per account), with what
    led up to it: when and how many of its hides were found, its last write, its age and its card. hide_times: epoch
    times its hides were found."""
    at = ts_of(portal_hit["ts"])
    last = scan.last_write(rec["username"])
    return dict(username=rec["username"], account_id=rec.get("account_id"), role=rec.get("role", "voice"),
                portal_ts=portal_hit["ts"], why=portal_hit["why"], hidden=hidden_n, hide_ts=[_iso(x) for x in hide_times],
                since_first_hide_h=_hours(hide_times[0], at) if hide_times else None,
                since_last_hide_h=_hours(hide_times[-1], at) if hide_times else None,
                last_write_ts=_iso(last), last_write_to_suspension_h=_hours(last, at),
                voice_age_h=_hours(stealth.voice_since(rec), at), card=card_info(rec, records))


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


def budget_report(now, writes, records, portal, recent_writes=None):
    """The account budget now, as one dict (None when neither the portal nor the records say how many accounts we have).
    writes: {username: text writes}; records: the account records (usernames, roles, status: nothing secret is read);
    portal: data/portal.json. recent_writes: live text writes in the last 24 h. Writes per ban is those writes / the bans
    in the same 24 h (the dashboard's headline) once config.BUDGET_MIN_BANS bans are in, else config.WRITES_PER_BAN_DEFAULT;
    km, the Kaplan-Meier median over the whole run, is only logged. Today's plan is cut to the part of the Sydney day left (the bans so far are already
    in alive and spare); bans of the last 24 h are compared with a whole day's plan."""
    counts = budget.account_counts(portal, records, config.POOL_TOTAL_CAP)
    if counts is None:
        return None
    alive, spare = counts
    log = portal.get("account_log") or {}
    names = {s["username"]: budget.epoch(s.get("ts")) for s in log.get("suspended") or [] if s.get("username")}
    km = budget.km_writes_per_ban(budget.build_voices(writes, records, names))
    stamps = {u: t for u, t in names.items() if t is not None}
    for r in records:                                  # a suspension the portal's names have not shown yet
        t = budget.epoch(r.get("suspended_at"))
        if r.get("status") == "suspended" and t is not None and r.get("username") not in stamps:
            stamps[r["username"]] = t
    actual = budget.bans_in_window(log.get("counts"), list(stamps.values()), now)
    measured = bool(recent_writes) and actual >= config.BUDGET_MIN_BANS
    wpb = recent_writes / actual if measured else float(config.WRITES_PER_BAN_DEFAULT)
    today = budget.sydney_day(now)
    first, last = dt.date.fromisoformat(today), dt.date.fromisoformat(config.BUDGET_END_DAY)
    span = [first + dt.timedelta(days=i) for i in range(max(0, (last - first).days + 1))]
    plan = {d.isoformat(): budget.plan_for_day(config.BAN_PLAN, d) for d in span}      # filled before today's is cut
    full_today = budget.plan_for_day(config.BAN_PLAN, today)
    if today in plan:
        plan[today] = full_today * budget.day_left_fraction(now)
    days = budget.forecast_days(plan, wpb, alive, spare, first, last) if span else []
    status = budget.reserve_status(days, config.LEFT_GOAL, config.LEFT_DAY)
    forecast24 = full_today / wpb
    return dict(ts=now, day=today, alive=alive, spare=spare, writes_per_ban=wpb, measured=measured, km=km, days=days,
                status=status, actual_bans_24h=actual, forecast_bans_24h=forecast24,
                alerts=budget.ban_alert(actual, forecast24, status, config.LEFT_DAY))


def budget_run(now, writes, records, *, alert, record, dry=False, recent_writes=None):
    """One 20-minute pass: report, send each new alert once per config.BUDGET_ALERT_GAP_S (the state is BUDGET_FILE), log
    one summary row. dry prints the alerts and sends and saves nothing. A missing file is no error: no data, no alert."""
    rep = budget_report(now, writes, records, read_json(PORTAL_FILE), recent_writes)
    if rep is None:
        print("budget: no account counts (no portal file, no records)")
        return None
    state = read_json(BUDGET_FILE)
    due, sent = budget.due_alerts(rep["alerts"], state.get("sent"), now, config.BUDGET_ALERT_GAP_S)
    record({"act": "budget", "alive": rep["alive"], "spare": rep["spare"], "writes_per_ban": rep["writes_per_ban"],
            "km": rep["km"], "recent_writes": recent_writes, "actual_bans_24h": rep["actual_bans_24h"],
            "forecast_bans_24h": round(rep["forecast_bans_24h"], 1), "reserve": rep["status"],
            "alerts": len(rep["alerts"]), "sending": len(due)})
    how = "last 24 h" if rep["measured"] else "default"
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
