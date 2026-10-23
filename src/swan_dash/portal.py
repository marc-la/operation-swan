"""Read our standing from the CTN portal for the dashboard (todo/09). swan-portal.timer runs it every 15 min.

    python -m swan_dash.portal          # (from src/) one read of the leaderboard and our points log

Logs in with the session cookie in secrets/portal_cookie (one line, name=value, copied from a logged-in browser), so
no portal password is stored. Three read-only GETs per run. It writes numbers and points-log lines only, to
data/portal.json, and appends to data/score.json when the score or rank changes. The portal shows our team code on
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
KEEP_EVENTS_H = 48


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


def checked(obj, banned):
    """JSON text for obj; raises if a secret would be written."""
    s = json.dumps(obj, indent=1)
    if any(b in s for b in banned):
        raise RuntimeError("refusing to write: output contains the team code or the cookie")
    return s


def write_atomic(path, s):
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(s)
    os.replace(tmp, path)


def run(root, now, get=fetch, pause=2):
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
        time.sleep(pause)                            # be gentle: two requests, a moment apart
        accounts = parse_accounts(get(TEAM_PAGE, cookie))      # the page shows the team code: parse one table only
        time.sleep(pause)
        events = parse_activity(get(ACTIVITY_CSV, cookie))
    except SessionExpired as e:
        write_atomic(out_path, checked({**previous, "error": f"{e}: paste a new cookie into secrets/portal_cookie",
                                        "error_ts": now.isoformat()}, banned))
        raise
    if not board:
        raise RuntimeError("leaderboard table not found (page layout changed?)")
    keep_from = (now - dt.timedelta(hours=KEEP_EVENTS_H)).isoformat()
    result = dict(ts=now.isoformat(), error=None, **standing(board), accounts=accounts,
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
    return result


def main():
    try:
        r = run(ROOT, dt.datetime.now(dt.timezone.utc))
    except SessionExpired as e:
        sys.exit(f"{e}: paste a new cookie into secrets/portal_cookie")
    print(f"portal: rank {r['rank']} of {r['teams']}, score {r['score']}, {len(r['events'])} points events")


if __name__ == "__main__":
    main()
