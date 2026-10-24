"""Portal reader (swan_dash/portal.py): parsing, score history, expired sessions, and that the team code is never
written. A fake portal stands in for the network."""
import datetime as dt
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from swan_dash import build, portal  # noqa: E402

CODE = "TEAMCODE1234ABCD"
NOW = dt.datetime(2026, 10, 22, 6, 0, tzinfo=dt.timezone.utc)

BOARD = """<table><tr><th>#</th><th>Team</th><th>Team Leader's University</th><th>Members</th><th>Score</th></tr>
<tr><td>1</td><td><a href="/x">Opus4.8Maxxing</a></td><td>UWA</td><td>2</td><td>39113</td></tr>
<tr><td>2</td><td>Vertex_CTN</td><td>QUT</td><td>3</td><td>38912</td></tr>
<tr><td>3</td><td>Operation Swan</td><td>UWA</td><td>4</td><td>31,200</td></tr>
<tr><td>4</td><td>swag &amp; co</td><td>UNSW</td><td>2</td><td>30000</td></tr></table>"""
TEAM = f"""<h1>Operation Swan</h1><h2>{CODE}</h2>
<table><tr><th>Registered</th><th>Banned</th><th>Maximum total</th><th>Maximum active at once</th></tr>
<tr><td>47</td><td>1</td><td>200</td><td>50</td></tr></table>
<table><tr><th>Name</th><th>Email</th></tr><tr><td>Someone</td><td>x</td></tr></table>"""
CSV = """When (UTC),Type,Message
2026-10-22 05:53:49,SCORE_NARRATIVE,+220 points: NPC engagement: 40 views and 9 replies
2026-10-22 05:53:50,SCORE_NARRATIVE,-2 points: NPC engagement: 1 contribution to a change of mind away from your side
2026-10-21 04:53:50,SCORE_NARRATIVE,+100 points: NPC engagement: 10 views
2026-10-17 11:02:04,TEAMCODE,Created with team code ending in ...BCD
"""


def make_root(tmp_path):
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "portal_cookie").write_text("session=cookievalue123\n")
    (tmp_path / ".env").write_text(f'CTN_TEAM_CODE="{CODE}"\nCTN_SIDE=no\n')
    return tmp_path


def fake(pages):
    def get(path, cookie):
        assert cookie == "session=cookievalue123"
        return pages[path]
    return get


PAGES = {portal.LEADERBOARD: BOARD, portal.TEAM_PAGE: TEAM, portal.ACTIVITY_CSV: CSV}


def test_run_writes_standing_accounts_and_recent_score_events(tmp_path):
    root = make_root(tmp_path)
    r = portal.run(root, NOW, get=fake(PAGES), pause=0)
    assert (r["rank"], r["score"], r["teams"]) == (3, 31200, 4)
    assert r["above"]["team"] == "Vertex_CTN" and r["below"]["team"] == "swag & co"
    assert r["accounts"] == {"registered": 47, "banned": 1, "max_total": 200, "max_active": 50}
    assert [e["points"] for e in r["events"]] == [-2, 220, 100]          # newest first, SCORE_* only
    written = (root / "data" / "portal.json").read_text()
    assert CODE not in written and "cookievalue123" not in written


def test_events_older_than_two_days_are_kept_for_the_blue_days_table(tmp_path):
    # the days table sums each Sydney day's points from this log: a 48 h window zeroed every day older than that
    old = "2026-10-19 18:30:00,SCORE_NARRATIVE,+13 points: Moderation: 1 first inauthentic report\n"
    pages = {**PAGES, portal.ACTIVITY_CSV: CSV + old}
    r = portal.run(make_root(tmp_path), NOW, get=fake(pages), pause=0)
    assert [e["points"] for e in r["events"]][-1] == 13


def test_score_history_appends_only_on_change(tmp_path):
    root = make_root(tmp_path)
    portal.run(root, NOW, get=fake(PAGES), pause=0)
    portal.run(root, NOW + dt.timedelta(minutes=15), get=fake(PAGES), pause=0)
    entries = json.loads((root / "data" / "score.json").read_text())
    assert len(entries) == 1 and entries[0]["by"] == "portal" and entries[0]["score"] == 31200


def test_refuses_to_write_the_team_code(tmp_path):
    root = make_root(tmp_path)
    leaky = BOARD.replace("Vertex_CTN", f"Vertex {CODE}")
    with pytest.raises(RuntimeError, match="refusing"):
        portal.run(root, NOW, get=fake({**PAGES, portal.LEADERBOARD: leaky}), pause=0)
    assert not (root / "data" / "portal.json").exists()


def test_expired_session_keeps_last_numbers_and_flags_it(tmp_path):
    root = make_root(tmp_path)
    portal.run(root, NOW, get=fake(PAGES), pause=0)

    def expired(path, cookie):
        raise portal.SessionExpired("portal session expired")
    with pytest.raises(portal.SessionExpired):
        portal.run(root, NOW + dt.timedelta(hours=1), get=expired, pause=0)
    saved = json.loads((root / "data" / "portal.json").read_text())
    assert saved["rank"] == 3 and "paste a new cookie" in saved["error"]


def test_dashboard_shows_points_rows_and_portal_numbers(tmp_path):
    root = make_root(tmp_path)
    (root / "logs").mkdir()
    portal.run(root, NOW, get=fake(PAGES), pause=0)
    ctx = build.gather(root, NOW, "active")
    html = build.render(ctx)
    assert not [r for r in ctx["activity"] if "pts" in r["what"]]        # points sit under Score & targets (todo/29)
    assert ctx["score_lines"]["total"] == 218 and sum(r["points"] for r in ctx["score_lines"]["rows"]) == 218
    assert ctx["score"]["delta"] == 218 and ctx["score"]["last_hour"] == 218  # the +100 was before today's 9pm
    assert "7,712 behind #2" in html and "+218 since 9pm" in html and CODE not in html


def test_account_log_counts_and_suspensions_by_competition_day():
    body = """When (UTC),Type,Message
2026-10-22 12:51:10,MESSAGE_NARRATIVE,Moderation: your account @ana_fifita_rn27 (id 4603) has been suspended after 3 of its posts were hidden as inauthentic. It can no longer log in or post.
2026-10-22 07:45:10,MESSAGE_NARRATIVE,"Moderation: your account @josh_k_sparky36 (id 4567) has been suspended. It was reported for inauthentic (bot) activity, it already had a post hidden by the moderator, and it had taken at least 100 actions. It can no longer log in or post."
2026-10-22 07:45:13,PLATFORM_ACCOUNTS,Platform total accounts: 58 registered; 12 banned.
2026-10-21 23:57:42,PLATFORM_ACCOUNTS,Platform total accounts: 53 registered; 3 banned.
2026-10-21 13:49:52,PLATFORM_ACCOUNTS,Platform total accounts: 52 registered; 2 banned.
2026-10-19 17:52:10,PLATFORM_ACCOUNTS,Platform total accounts: 1 registered; 0 banned.
"""
    log = portal.account_log(portal.parse_activity(body))
    assert [c["banned"] for c in log["counts"]] == [0, 2, 3, 12]
    assert [(x["username"], x["id"], x["why"]) for x in log["suspended"]] == [
        ("josh_k_sparky36", 4567, "reported as a bot"), ("ana_fifita_rn27", 4603, "3 posts hidden")]
    days, listed = build.account_days(log, dt.datetime(2026, 10, 22, 15, tzinfo=dt.timezone.utc))
    assert [(d["banned"], d["new"]) for d in days] == [(12, 0), (12, 12), (0, 0), (0, 0)]   # Oct 23 (so far) back to 20
    assert days[1]["why"] == "reported as a bot ×1 · 3 posts hidden ×1" and listed[0]["username"] == "ana_fifita_rn27"


def test_standing_keeps_the_three_finalist_places(tmp_path):
    r = portal.run(make_root(tmp_path), NOW, get=fake(PAGES), pause=0)
    assert [t["rank"] for t in r["top"]] == [1, 2, 3]


def team(rank, score=1000):
    return dict(rank=rank, team=f"T{rank}", score=score - rank)


def test_leaderboard_rows_midfield_shows_top_three_then_us_between_neighbours():
    top = [team(i, 9000) for i in (1, 2, 3)]
    rows = build.leaderboard_rows(dict(top=top, rank=12, score=500, above=team(11), below=team(13)))
    assert [r["rank"] for r in rows["finalists"]] == [1, 2, 3]
    assert [r["rank"] for r in rows["near"]] == [11, 12, 13] and rows["near"][1]["us"]
    assert rows["gap"] and rows["cutoff"] == 9000 - 3 - 500
    assert rows["between"] == []                                         # no full board saved yet: a plain gap
    full = top + [team(i) for i in range(4, 15)]
    rows = build.leaderboard_rows(dict(top=top, rows=full, rank=12, score=500, above=team(11), below=team(13)))
    assert [r["rank"] for r in rows["between"]] == [4, 5, 6, 7, 8, 9, 10]


def test_leaderboard_rows_do_not_repeat_finalists_near_the_line():
    top = [team(i, 9000) for i in (1, 2, 3)]
    fourth = build.leaderboard_rows(dict(top=top, rank=4, score=8000, above=team(3), below=team(5)))
    assert [r["rank"] for r in fourth["near"]] == [4, 5] and not fourth["gap"]
    third = build.leaderboard_rows(dict(top=top, rank=3, score=9000, above=team(2), below=team(4)))
    assert [r["rank"] for r in third["near"]] == [4] and third["cutoff"] is None
    assert [r["us"] for r in third["finalists"]] == [False, False, True]


def test_leaderboard_rows_cap_a_stale_saved_top_at_the_finalist_places():
    stale = [team(i, 9000) for i in (1, 2, 3, 4)]                       # portal.json written when the line was at four
    rows = build.leaderboard_rows(dict(top=stale, rank=12, score=500, above=team(11), below=team(13)))
    assert [r["rank"] for r in rows["finalists"]] == [1, 2, 3]


def test_leaderboard_history_is_one_line_an_hour_with_first_and_third(tmp_path):
    root = make_root(tmp_path)
    portal.run(root, NOW, get=fake(PAGES), pause=0)
    portal.run(root, NOW + dt.timedelta(minutes=15), get=fake(PAGES), pause=0)          # same clock hour: no second line
    portal.run(root, NOW + dt.timedelta(minutes=70), get=fake(PAGES), pause=0)
    lines = [json.loads(x) for x in (root / "data" / "leaderboard.jsonl").read_text().splitlines()]
    assert len(lines) == 2
    assert lines[0] == {"ts": NOW.isoformat(), "rank": 3, "score": 31200, "first": 39113, "third": 31200, "teams": 4}
    assert lines[1]["ts"] == (NOW + dt.timedelta(minutes=70)).isoformat()


def test_leaderboard_history_is_bounded_and_survives_a_damaged_line(tmp_path):
    path = tmp_path / "leaderboard.jsonl"
    path.write_text("not json\n")
    for h in range(5):
        line = dict(ts=(NOW + dt.timedelta(hours=h)).isoformat(), rank=3, score=h, first=9, third=8, teams=4)
        assert portal.append_leaderboard(path, line, [CODE], keep=3)
    rows = path.read_text().splitlines()
    assert [json.loads(x)["score"] for x in rows] == [2, 3, 4] and not list(tmp_path.glob(".*.tmp"))
    path.write_text("{broken\n")
    assert portal.append_leaderboard(path, dict(ts=NOW.isoformat(), rank=1, score=1, first=1, third=1, teams=1), [CODE])


def test_leaderboard_history_never_writes_the_team_code(tmp_path):
    path = tmp_path / "leaderboard.jsonl"
    with pytest.raises(RuntimeError, match="refusing"):
        portal.append_leaderboard(path, dict(ts=NOW.isoformat(), rank=1, score=1, first=1, third=1, teams=CODE), [CODE])
    assert not path.exists()


def test_no_leaderboard_line_when_we_are_not_on_the_board(tmp_path):
    root = make_root(tmp_path)
    away = BOARD.replace("Operation Swan", "Someone Else")
    portal.run(root, NOW, get=fake({**PAGES, portal.LEADERBOARD: away}), pause=0)
    assert not (root / "data" / "leaderboard.jsonl").exists()
