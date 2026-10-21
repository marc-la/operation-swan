"""Build the team dashboard (todo/09): one static HTML page from the bot's own files. swan-dash.timer runs it every
minute on EC2 and nginx serves the result behind a password.

    python -m swan_dash.build --out /var/www/swan        # (from src/) what the timer runs
    python -m swan_dash.build --out /tmp/swan            # local preview from this checkout's logs/ and data/

It reads logs/ and data/ only. It never opens .env or secrets/ (the systemd unit also makes them inaccessible) and
needs no network. Every value on the page is picked field by field; whole records are never rendered.
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import subprocess
from zoneinfo import ZoneInfo

import jinja2

ROOT = pathlib.Path(__file__).resolve().parents[2]
PERTH = ZoneInfo("Australia/Perth")
SYDNEY = ZoneInfo("Australia/Sydney")          # competition days roll over at midnight Sydney (9pm Perth)
TEAM_CAP_PER_MIN = 3                           # posts + replies + reposts, team-wide (rules)
LIVE_CAP, TOTAL_CAP = 50, 200                  # accounts alive at once / ever
WRITES = {"post": "post", "reply": "reply", "second_voice": "2nd voice", "reply_back": "reply-back",
          "journalist": "journalist", "thread": "own thread", "thread_answer": "thread answer", "repost": "repost"}
# poll awards and Red multiplier changes, as Sydney calendar dates (docs/01-competition/schedule.md)
POLLS = [(dt.date(2026, 10, 21), "Poll 1", 1), (dt.date(2026, 10, 25), "Poll 2", 2500),
         (dt.date(2026, 10, 29), "Poll 3", 2500)]
MULTIPLIERS = [(dt.date(2026, 10, 26), 2), (dt.date(2026, 11, 1), 4)]     # derived, not confirmed by organisers
LOG_TAIL_BYTES = 6_000_000                     # likes are logged one per line; this covers several hours
STALE_STATUS_S = 300
STALL_S = 5 * 60                               # every LLM parked this long or longer: red
PORTAL_STALE_S = 45 * 60                       # swan-portal.timer runs every 15 min
PULSE_MAX_AGE_S = 2 * 3600                     # swan_bot config.PULSE_MAX_AGE_S: older, the bot doesn't use it
ACTIVITY_TOP, ACTIVITY_ALL = 12, 60          # rows always shown / rows behind "Older activity"
LONG_PARK_S = 600                              # per-minute parks are noise; longer ones go in the activity log


def read_json(path, default=None):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def tail_jsonl(path, nbytes=LOG_TAIL_BYTES):
    """Records from the last nbytes of a jsonl file, oldest first (a cut first line is skipped)."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - nbytes))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except FileNotFoundError:
        return []
    if size > nbytes:
        lines = lines[1:]
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def tail_lines(path, n=50):
    try:
        return path.read_text().splitlines()[-n:]
    except FileNotFoundError:
        return []


def ts(s):
    """ISO time ('...Z' or '+00:00') -> aware datetime, or None."""
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def service_state():
    """'active', 'inactive', 'failed', ... or None where systemd isn't there (a laptop preview)."""
    try:
        r = subprocess.run(["systemctl", "is-active", "swan-bot"], capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def ago(delta):
    s = int(delta.total_seconds())
    if s < 90:
        return "just now" if s < 45 else "1 min ago"
    if s < 5400:
        return f"{s // 60} min ago"
    if s < 48 * 3600:
        return f"{s // 3600} h ago"
    return f"{s // 86400} days ago"


def until(delta):
    s = max(0, int(delta.total_seconds()))
    d, h, m = s // 86400, s % 86400 // 3600, s % 3600 // 60
    return f"{d}d {h}h" if d else f"{h}h {m}m" if h else f"{m}m"


def perth(t):
    return t.astimezone(PERTH)


def hm(t):
    return perth(t).strftime("%H:%M")


def ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def short(text, n=110):
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def sydney_midnight(day):
    return dt.datetime.combine(day, dt.time(), SYDNEY)


def gather(root, now, service):
    """Everything the page shows, as plain values. root is the repo checkout (logs/ and data/ under it)."""
    logs, data = root / "logs", root / "data"
    day_start = sydney_midnight(now.astimezone(SYDNEY).date())
    hour_ago = now - dt.timedelta(hours=1)
    status = read_json(data / "status.json") or {}
    status_t = ts(status.get("ts"))
    portal = read_json(data / "portal.json") or {}               # swan_dash/portal.py: leaderboard + points log
    portal_t = ts(portal.get("ts"))
    points = [dict(e, _t=ts(e["ts"])) for e in portal.get("events") or []
              if ts(e.get("ts")) and e.get("points") is not None]
    actions = [a for a in tail_jsonl(logs / "swan_actions.jsonl") if ts(a.get("ts"))]
    for a in actions:
        a["_t"] = ts(a["ts"])

    # ---- vitals ----
    live_writes = [a for a in actions if a.get("act") in WRITES and a.get("live") is True]
    writes_hour = sum(a["_t"] >= hour_ago for a in live_writes)
    rejects_hour = sum(a.get("act") == "reject" and a["_t"] >= hour_ago for a in actions)
    last_write = max((a["_t"] for a in live_writes), default=None)
    chain = status.get("llm") or []
    current = next((i for i, m in enumerate(chain) if not m.get("parked_until")), None)
    parked = [dict(model=m["model"], why=m.get("why") or "parked",
                   until=hm(dt.datetime.fromtimestamp(m["parked_until"], dt.timezone.utc)))
              for m in chain if m.get("parked_until")]
    states = [dict(model=m["model"], state="in use" if i == current else
                   f"{m.get('why') or 'parked'} until {hm(dt.datetime.fromtimestamp(m['parked_until'], dt.timezone.utc))}"
                   if m.get("parked_until") else "ready", out=bool(m.get("parked_until")))
              for i, m in enumerate(chain)]
    acc = status.get("accounts") or {}
    banned_day = [a for a in actions if a.get("act") == "suspended" and a["_t"] >= now - dt.timedelta(hours=24)]
    per_min = status.get("per_min")

    # ---- banner: the first problem wins, worst first ----
    try:                                       # deploy/healthcheck.sh's current problem, the same text it alerts with
        health = (data / "health_state").read_text().strip()
    except FileNotFoundError:
        health = ""
    stale = status_t is None or (now - status_t).total_seconds() > STALE_STATUS_S
    red = amber = None
    if service not in (None, "active"):
        red = f"DOWN: swan-bot is {service}. On the box: journalctl -u swan-bot -n 50"
    elif health:
        red = health
    elif chain and current is None and min(m["parked_until"] for m in chain) - now.timestamp() >= STALL_S:
        first = min(m["parked_until"] for m in chain)
        red = f"STALLED: every LLM is parked until {hm(dt.datetime.fromtimestamp(first, dt.timezone.utc))}"
    elif chain and current is None:              # a short gap: the bot waits a minute and carries on
        first = min(m["parked_until"] for m in chain)
        amber = f"LLMS BUSY: every model is rate-limited, next free at {hm(dt.datetime.fromtimestamp(first, dt.timezone.utc))}"
    elif stale:
        amber = ("NO STATUS: the bot hasn't reported for "
                 + (ago(now - status_t).replace(" ago", "") if status_t else "a while (or isn't live)"))
    elif current:
        top = chain[0]
        amber = f"DEGRADED: on fallback LLM {chain[current]['model']} ({top['model']}: {top.get('why') or 'parked'})"
    elif banned_day:
        amber = f"ACCOUNT LOST: {len(banned_day)} suspended in the last 24 h ({banned_day[-1].get('username')})"
    elif status.get("rate_limited_last_hour"):
        amber = f"RATE-LIMITED: {status['rate_limited_last_hour']} × 429 in the last hour"
    elif portal.get("error"):
        amber = f"PORTAL: {portal['error']}"
    elif portal and (portal_t is None or (now - portal_t).total_seconds() > PORTAL_STALE_S):
        amber = "PORTAL: no score update for " + (ago(now - portal_t).replace(" ago", "") if portal_t else "a while")
    if red:
        banner = dict(level="red", text=red)
    elif amber:
        banner = dict(level="amber", text=amber)
    else:
        banner = dict(level="green", text="RUNNING · last post " + (ago(now - last_write) if last_write else "—"))

    # ---- score (typed in by hand: scripts/score.sh) ----
    entries = [e for e in (read_json(data / "score.json") or []) if ts(e.get("ts"))]
    score = None
    if entries:
        e = entries[-1]
        before = [x for x in entries if ts(x["ts"]) < day_start]
        delta = e["score"] - before[-1]["score"] if before else None
        hours = (ts(e["ts"]) - day_start).total_seconds() / 3600
        score = dict(points=e["score"], rank=e.get("rank"), teams=e.get("teams"), by=e.get("by", "?"),
                     ago=ago(now - ts(e["ts"])), delta=delta,
                     per_hour=round(delta / hours) if delta is not None and hours >= 0.5 else None,
                     last_hour=None, last_hour_at=None)
        if points:                             # the portal's own points log is exact: use it for today and last hour
            newest = max(e["_t"] for e in points)
            score["delta"] = sum(e["points"] for e in points if e["_t"] >= day_start)
            score["last_hour"] = sum(e["points"] for e in points if (newest - e["_t"]).total_seconds() < 600)
            score["last_hour_at"] = hm(newest)
    board = dict(leader=portal.get("leader"), above=portal.get("above"), below=portal.get("below"),
                 rank=portal.get("rank"), score=portal.get("score")) if portal.get("rank") else None
    history = [dict(time=perth(ts(x["ts"])).strftime("%a %H:%M"), score=x["score"], rank=x.get("rank"),
                    change=x["score"] - entries[i - 1]["score"] if i else None, by=x.get("by", "?"))
               for i, x in enumerate(entries)][-10:][::-1]
    today = now.astimezone(SYDNEY).date()
    poll = next(((d, name, need) for d, name, need in POLLS if d >= today), None)
    milestone = None
    if poll:
        d, name, need = poll
        have = score["points"] if score else None
        milestone = dict(name=name, date=d.strftime("%a %-d %b"), need=need,
                         reached=have is not None and have >= need,
                         short=None if have is None else max(0, need - have),
                         today=d == today)
    mult_now = next((m for d, m in reversed(MULTIPLIERS) if d <= today), 1)
    nxt = next(((d, m) for d, m in MULTIPLIERS if d > today), None)
    multiplier = dict(now=mult_now, next=nxt and nxt[1], date=nxt and nxt[0].strftime("%a %-d %b"),
                      left=nxt and until(sydney_midnight(nxt[0]) - now))

    # ---- activity: our writes, account events, long LLM parks, deploys and alerts ----
    rows = []
    for a in actions:
        act = a.get("act")
        if act in WRITES and a.get("live") is True:
            rows.append(dict(t=a["_t"], who=a.get("persona") or a.get("username"), what=WRITES[act],
                             text=short(a.get("text")), post=a.get("post_id"), kind="write"))
        elif act == "register":
            rows.append(dict(t=a["_t"], who=a.get("persona") or a.get("role") or "", what="new account",
                             text=a.get("username"), kind="event"))
        elif act == "suspended":
            rows.append(dict(t=a["_t"], who="", what="SUSPENDED", text=a.get("username"), kind="bad"))
        elif act == "llm_park":
            u = ts(a.get("until"))
            if u and (u - a["_t"]).total_seconds() >= LONG_PARK_S:
                rows.append(dict(t=a["_t"], who="", what="LLM parked",
                                 text=f"{a.get('model')}: {a.get('why')} until {hm(u)}", kind="event"))
    for e in points:                           # the outcome, interleaved with what we did
        rows.append(dict(t=e["_t"], who="", what=f"{e['points']:+,} pts", text=short(e.get("message"), 160),
                         kind="gain" if e["points"] >= 0 else "loss"))
    for line in tail_lines(logs / "alerts.log"):
        t, _, msg = line.partition(" ")
        if ts(t):
            msg = msg.removeprefix("[swan-ec2] ")
            rows.append(dict(t=ts(t), who="", what="deploy" if msg.startswith("deployed") else "alert",
                             text=short(msg), kind="event"))
    rows.sort(key=lambda r: r["t"], reverse=True)
    for r in rows[:ACTIVITY_ALL]:
        r["time"] = hm(r["t"])
        r.setdefault("post", None)

    # ---- the trending pulse the bot writes towards (todo/15): its newest "pulse" record ----
    p = next((a for a in reversed(actions) if a.get("act") == "pulse"), None)
    pulse = p and dict(id=p.get("id"), ago=ago(now - p["_t"]),
                       stale=(now - p["_t"]).total_seconds() > PULSE_MAX_AGE_S,
                       hooks=[short(h.get("text")) for h in p.get("hooks") or [] if isinstance(h, dict)],
                       no_shapes=[short(x) for x in p.get("no_shapes") or []],
                       yes_lines=[short(x) for x in p.get("yes_lines") or []],
                       avoid=[short(x) for x in p.get("avoid") or []])

    deploys = [d for d in tail_jsonl(logs / "deploys.jsonl", 200_000) if d.get("result") == "ok"]
    running = dict(sha=deploys[-1]["new"][:7], when=hm(ts(deploys[-1]["ts"]))) if deploys else None

    return dict(
        now=hm(now), banner=banner, score=score, history=history, board=board, milestone=milestone,
        multiplier=multiplier, portal_accounts=portal.get("accounts"),
        portal_checked=ago(now - portal_t) if portal_t else None,
        day_start=perth(day_start).strftime("%-I%p").lower(),
        writes=dict(hour=writes_hour, planned=round(per_min * 60) if per_min else None, cap=TEAM_CAP_PER_MIN * 60),
        accounts=dict(live=acc.get("live"), live_cap=LIVE_CAP, used=acc.get("used"), total_cap=TOTAL_CAP,
                      suspended=acc.get("suspended"), voices=acc.get("voices"), boosters=acc.get("boosters")),
        llm=dict(model=chain[current]["model"] if current is not None else None,
                 rank=ordinal(current + 1) if current is not None else None, of=len(chain), parked=parked,
                 chain=states),
        errors=dict(rate_limited=status.get("rate_limited_last_hour"), rejects=rejects_hour),
        activity=rows[:ACTIVITY_TOP], older=rows[ACTIVITY_TOP:ACTIVITY_ALL], running=running, pulse=pulse, built=perth(now).strftime("%H:%M:%S"))


def render(ctx):
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(pathlib.Path(__file__).parent / "templates"),
                             autoescape=True, undefined=jinja2.StrictUndefined, trim_blocks=True, lstrip_blocks=True)
    env.filters["n"] = lambda x: "—" if x is None else f"{x:,}"
    return env.get_template("index.html.j2").render(**ctx)


def write_atomic(path, text):
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=pathlib.Path, required=True, help="directory nginx serves")
    ap.add_argument("--root", type=pathlib.Path, default=ROOT, help="repo checkout with logs/ and data/")
    args = ap.parse_args()
    now = dt.datetime.now(dt.timezone.utc)
    html = render(gather(args.root, now, service_state()))
    args.out.mkdir(parents=True, exist_ok=True)
    write_atomic(args.out / "index.html", html)
    write_atomic(args.out / "robots.txt", "User-agent: *\nDisallow: /\n")
    write_atomic(args.out / "app.js", (pathlib.Path(__file__).parent / "templates" / "app.js").read_text())


if __name__ == "__main__":
    main()
