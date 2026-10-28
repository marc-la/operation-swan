"""Read our standing from the CTN portal for the dashboard (todo/09). swan-portal.timer runs it every minute with --auto,
which reads only when one is due (plan(): a full read at :02 and :32, and a short one a minute apart for up to 12 min
after the portal posts the hour's points, until the board's scores change).

    python -m swan_dash.portal          # (from src/) one full read of the leaderboard, team page and points log
    python -m swan_dash.portal --auto   # what the timer runs: reads only when plan() says one is due

Logs in with the session cookie in secrets/portal_cookie (one line, name=value, copied from a logged-in browser), so
no portal password is stored. Three read-only GETs per full run, two per short run (no team page). It writes numbers and points-log lines only, to
data/portal.json, appends to data/score.json when the score or rank changes, and adds one line an hour to
data/leaderboard.jsonl (rank, our score, the 1st and 3rd place scores, team count: the gap to 3rd over time, todo/42) and
one line an hour to data/team_scores.jsonl (every team's score: the dashboard's points-an-hour column per team, 25 Oct).
The portal shows our team code on
the team page, so every write is checked first: a run that would write the team code or the cookie fails instead.
"""
import csv
import datetime as dt
import html
import io
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
BASE = "https://community.capturethenarrative.com"
LEADERBOARD = "/user/competitions/2"
TEAM_PAGE = "/user/teams/170"
ACTIVITY_CSV = "/user/teams/170/activity.csv"
TEAM_NAME = "Operation Swan"
USER_AGENT = "OperationSwan-dashboard/1.0 (team 170)"
KEEP_EVENTS_H = 24 * 16                        # the whole competition (19 Oct - 2 Nov): the Blue days table sums a day's
                                               # points from this log, and a 48 h window zeroed every day older than that
LEADERBOARD_LOG = "leaderboard.jsonl"
LEADERBOARD_KEEP = 24 * 14                     # hourly lines kept (two weeks): the file never grows past this
TEAM_SCORES_LOG = "team_scores.jsonl"          # {ts, scores: {team: score}} an hour, same bound (about 5 KB a line)


POLL_STATE = "portal_poll.json"                # {last_try, last_full}: written before a read, so a failing read is not retried every minute
FULL_SLOTS = (2, 32)                           # minutes past the hour of the full reads; the first in a UTC hour makes the hourly history lines
BURST_FROM_S = 40                              # the portal posts the hour's points at about :19:10; read from 40 s after that minute starts
BURST_FOR_S = 12 * 60                          # ... for at most 12 min
BURST_GAP_S = 55                               # ... and no more than once a minute
SCHEDULE_H = 3                                 # hours of points events that tell us which minute of the hour the portal posts at


class SessionExpired(Exception):
    pass


def read_secrets(root):
    """(cookie line, [values that must never be written]). The team code comes from .env."""
    cookie = (root / "secrets" / "portal_cookie").read_text().strip()
    env = {}
    for line in (root / ".env").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip().removeprefix("export ").strip()] = v.strip().strip("\"'")
    banned = [s for s in (env.get("CTN_TEAM_CODE"), cookie.split("=", 1)[-1]) if s and len(s) >= 6]
    return cookie, banned


def fetch(path, cookie):
    req = urllib.request.Request(BASE + path, headers={"Cookie": cookie, "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            if "/login" in r.geturl():
                raise SessionExpired("portal session expired")
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise SessionExpired(f"portal session expired ({e.code})") from e
        raise


def text(fragment):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def parse_leaderboard(page):
    """[{rank, team, score}] from the competition page's table (# | Team | University | Members | Score)."""
    table = re.search(r"<table\b.*?</table>", page, re.S)
    rows = []
    for tr in re.findall(r"<tr\b.*?</tr>", table.group(0) if table else "", re.S):
        cells = [text(c) for c in re.findall(r"<td\b[^>]*>(.*?)</td>", tr, re.S)]
        if len(cells) >= 5 and cells[0].isdigit():
            rows.append(dict(rank=int(cells[0]), team=cells[1], score=int(cells[-1].replace(",", ""))))
    return rows


def parse_accounts(page):
    """{registered, banned, max_total, max_active} from the team page's account table, or None."""
    for table in re.findall(r"<table\b.*?</table>", page, re.S):
        heads = [text(h).lower() for h in re.findall(r"<th\b[^>]*>(.*?)</th>", table, re.S)]
        if heads[:2] == ["registered", "banned"]:
            cells = [text(c) for c in re.findall(r"<td\b[^>]*>(.*?)</td>", table, re.S)]
            if len(cells) >= 4 and all(c.isdigit() for c in cells[:4]):
                return dict(zip(("registered", "banned", "max_total", "max_active"), map(int, cells[:4])))
    return None


def parse_activity(body):
    """[{ts, type, points, message}] from activity.csv (When (UTC), Type, Message), newest first."""
    out = []
    for row in list(csv.reader(io.StringIO(body)))[1:]:
        if len(row) < 3:
            continue
        try:
            t = dt.datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue
        m = re.match(r"([+-]?\d[\d,]*) points?:\s*(.*)", row[2])
        out.append(dict(ts=t.isoformat(), type=row[1], points=int(m.group(1).replace(",", "")) if m else None,
                        message=m.group(2) if m else row[2]))
    return sorted(out, key=lambda e: e["ts"], reverse=True)


ACCOUNT_COUNTS = re.compile(r"(\d+) registered; (\d+) banned")
SUSPENDED = re.compile(r"your account @(\w+) \(id (\d+)\) has been suspended(.*)")


def account_log(events):
    """{counts: [{ts, registered, banned}], suspended: [{ts, username, id, why}]}, oldest first, from every row of
    activity.csv: PLATFORM_ACCOUNTS (the team's counts at each change) and the moderator's suspension messages."""
    counts, suspended = [], []
    for e in sorted(events, key=lambda e: e["ts"]):
        m = ACCOUNT_COUNTS.search(e["message"]) if e["type"] == "PLATFORM_ACCOUNTS" else None
        if m:
            counts.append(dict(ts=e["ts"], registered=int(m.group(1)), banned=int(m.group(2))))
        m = SUSPENDED.search(e["message"]) if e["type"] == "MESSAGE_NARRATIVE" else None
        if m:
            suspended.append(dict(ts=e["ts"], username=m.group(1), id=int(m.group(2)),
                                  why="3 posts hidden" if "3 of its posts were hidden" in m.group(3) else "reported as a bot"))
    return dict(counts=counts, suspended=suspended)


FINALISTS = 3                                  # the top three teams fly to Sydney to present


def standing(board):
    """Our rank, score and neighbours, the leader, the finalist places (top three), and the team count."""
    us = next((r for r in board if r["team"] == TEAM_NAME), None)
    if not us:
        return dict(rank=None, score=None, teams=len(board))
    by_rank = {r["rank"]: r for r in board}
    return dict(rank=us["rank"], score=us["score"], teams=len(board), leader=board[0] if board else None,
                top=[r for r in board if r["rank"] <= FINALISTS],
                rows=board,
                above=by_rank.get(us["rank"] - 1), below=by_rank.get(us["rank"] + 1))


def checked(obj, banned, indent=1):
    """JSON text for obj; raises if a secret would be written."""
    s = json.dumps(obj, indent=indent)
    if any(b in s for b in banned):
        raise RuntimeError("refusing to write: output contains the team code or the cookie")
    return s


def write_atomic(path, s):
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(s)
    os.replace(tmp, path)


def leaderboard_line(result, now):
    """One hourly leaderboard point: {ts, rank, score, first, third, teams}. first/third are the 1st and 3rd place scores
    (None when the board has no such row); rank/score are ours (None when we are not on the board)."""
    place = lambda n: next((r["score"] for r in result.get("rows") or [] if r["rank"] == n), None)
    return dict(ts=now.isoformat(), rank=result["rank"], score=result["score"], first=place(1), third=place(3),
                teams=result["teams"])


def team_scores_line(result, now):
    """One hourly point of the whole board: {ts, seen, scores: {team name: score}} (rank is the order of the scores).
    `seen` is when these scores first showed on the board (the site changes them once an hour, we poll every 15 min),
    so a pace is measured between two board changes, not between two poll times."""
    return dict(ts=now.isoformat(), seen=result.get("scores_ts") or now.isoformat(),
                scores={r["team"]: r["score"] for r in result.get("rows") or []})


def board_scores(rows):
    return {r["team"]: r["score"] for r in rows or []}


def scores_seen(previous, rows, now):
    """When the board's scores last changed, as our poll saw it: `now` if any team's score differs from the previous
    read, else the time carried over from it (the previous read's own time when it predates this field)."""
    if previous.get("rows") and board_scores(previous["rows"]) == board_scores(rows):
        return previous.get("scores_ts") or previous.get("ts") or now.isoformat()
    return now.isoformat()


def append_leaderboard(path, line, banned, keep=LEADERBOARD_KEEP):
    """Add `line` to the jsonl history unless the file already has a line from the same clock hour (UTC); keep the last
    `keep` lines. Atomic (a temp file replaces the old one) and checked for secrets like every other write. True if added."""
    new = checked(line, banned, indent=None)
    try:
        old = [ln for ln in path.read_text().splitlines() if ln.strip()]
    except FileNotFoundError:
        old = []
    hour = lambda s: s[:13]                      # '2026-10-24T05': ISO UTC timestamps share this prefix within an hour
    try:
        if old and hour(json.loads(old[-1])["ts"]) == hour(line["ts"]):
            return False
    except (ValueError, KeyError, TypeError):    # a damaged last line: write a new one after it
        pass
    write_atomic(path, "\n".join((old + [new])[-keep:]) + "\n")
    return True


def parse_time(s):
    try:
        return dt.datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def update_minute(events, now):
    """The minute of the hour at which the portal posts its hourly points, from the score events of the last SCHEDULE_H
    hours: the minute that turns up in the most distinct hours (a single poll award does not outvote the hourly rows;
    a tie goes to the newest). None without events. The minute moved four times in the first three days (:53, :47,
    :16, :19), so it is read from the log each time, never fixed in code."""
    hours = {}
    for e in events or []:
        t = parse_time(e.get("ts"))
        if t and dt.timedelta(0) <= now - t <= dt.timedelta(hours=SCHEDULE_H):
            hours.setdefault(t.minute, set()).add(t.replace(minute=0, second=0, microsecond=0))
    newest = {m: max(h) for m, h in hours.items()}
    return max(hours, key=lambda m: (len(hours[m]), newest[m]), default=None)


def plan(now, previous, state):
    """What the timer's run should read now: 'full' (leaderboard, team page, points log), 'short' (leaderboard and points
    log) or None. Full at each :02 and :32 slot; short once a minute from BURST_FROM_S after the portal's posting minute
    until the board's scores have changed since it (at most BURST_FOR_S; not while the session is expired)."""
    last_full, last_try = parse_time(state.get("last_full")), parse_time(state.get("last_try"))
    if last_full is None:
        return "full"
    hour = now.replace(minute=0, second=0, microsecond=0)
    slot = max(t for t in (hour + dt.timedelta(hours=k, minutes=m) for k in (-1, 0) for m in FULL_SLOTS) if t <= now)
    if last_full < slot:
        return "full"
    minute = update_minute(previous.get("events"), now)
    if minute is None or previous.get("error"):  # (no history, or a failed first read: wait for the next slot)
        return None
    due = now.replace(minute=minute, second=0, microsecond=0)
    due -= dt.timedelta(hours=1) if due > now else dt.timedelta(0)
    changed = parse_time(previous.get("scores_ts")) or parse_time(previous.get("ts"))
    if (dt.timedelta(seconds=BURST_FROM_S) <= now - due <= dt.timedelta(seconds=BURST_FOR_S)
            and (changed is None or changed < due) and (last_try is None or (now - last_try).total_seconds() >= BURST_GAP_S)):
        return "short"
    return None


def run(root, now, get=fetch, pause=2, full=True):
    data = root / "data"
    data.mkdir(exist_ok=True)
    out_path = data / "portal.json"
    try:
        previous = json.loads(out_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        previous = {}
    cookie, banned = read_secrets(root)
    try:
        board = parse_leaderboard(get(LEADERBOARD, cookie))
        time.sleep(pause)                            # be gentle: requests a moment apart
        if full:
            accounts = parse_accounts(get(TEAM_PAGE, cookie))  # the page shows the team code: parse one table only
            time.sleep(pause)
        else:
            accounts = previous.get("accounts")
        events = parse_activity(get(ACTIVITY_CSV, cookie))
    except SessionExpired as e:
        write_atomic(out_path, checked({**previous, "error": f"{e}: paste a new cookie into secrets/portal_cookie",
                                        "error_ts": now.isoformat()}, banned))
        raise
    if not board:
        raise RuntimeError("leaderboard table not found (page layout changed?)")
    keep_from = (now - dt.timedelta(hours=KEEP_EVENTS_H)).isoformat()
    result = dict(ts=now.isoformat(), error=None, **standing(board), scores_ts=scores_seen(previous, board, now),
                  accounts=accounts,
                  events=[e for e in events if e["ts"] >= keep_from and e["type"].startswith("SCORE")],
                  account_log=account_log(events))
    write_atomic(out_path, checked(result, banned))

    if result["score"] is not None:                      # the dashboard's score history (scripts/score.sh too)
        score_path = data / "score.json"
        try:
            entries = json.loads(score_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            entries = []
        last = entries[-1] if entries else {}
        if (last.get("score"), last.get("rank"), last.get("teams")) != (result["score"], result["rank"], result["teams"]):
            entries.append(dict(ts=now.isoformat(), score=result["score"], rank=result["rank"],
                                teams=result["teams"], by="portal"))
            write_atomic(score_path, checked(entries, banned))
    if result["rank"] is not None:                       # the hourly leaderboard series: the gap to 3rd over time
        append_leaderboard(data / LEADERBOARD_LOG, leaderboard_line(result, now.astimezone(dt.timezone.utc)), banned)
    if result.get("rows"):                               # every team's score an hour: their pace on the dashboard
        append_leaderboard(data / TEAM_SCORES_LOG, team_scores_line(result, now.astimezone(dt.timezone.utc)), banned)
    try:                                                 # which side each rival is on, from the polls' awards (sides.py): labels only
        from swan_dash import sides
        sides.update(data, now)
    except Exception as e:                               # a labelling fault must never cost a score read
        print(f"portal: sides not updated: {e}", file=sys.stderr)
    return result


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    now = dt.datetime.now(dt.timezone.utc)
    data = ROOT / "data"
    kind = "full"
    if "--auto" in argv:
        read = lambda name: json.loads((data / name).read_text()) if (data / name).exists() else {}
        try:
            previous, state = read("portal.json"), read(POLL_STATE)
        except ValueError:                                  # a damaged file: do a full read, which rewrites it
            previous, state = {}, {}
        kind = plan(now, previous, state)
        if kind is None:
            return
        data.mkdir(exist_ok=True)
        write_atomic(data / POLL_STATE, json.dumps(dict(last_try=now.isoformat(),
                                                        last_full=now.isoformat() if kind == "full" else state.get("last_full"))))
    try:
        r = run(ROOT, now, full=kind == "full")
    except SessionExpired as e:
        sys.exit(f"{e}: paste a new cookie into secrets/portal_cookie")
    print(f"portal: {kind} read, rank {r['rank']} of {r['teams']}, score {r['score']}, {len(r['events'])} points events")


if __name__ == "__main__":
    main()
