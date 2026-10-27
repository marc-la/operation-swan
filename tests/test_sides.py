"""Which side each rival team is on, read off a poll's awards (src/swan_dash/sides.py), and the leaderboard labels.
Synthetic hourly scoreboards: nothing here reads a file from the box or touches the platform."""
import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import test_dash as td  # noqa: E402
import test_dash_stealth as ts  # noqa: E402
from swan_dash import build, sides  # noqa: E402

DAY = dt.date(2026, 10, 29)
POLL_HOUR = dt.datetime(2026, 10, 28, 21, 2, tzinfo=dt.timezone.utc)       # 08:02 Sydney on the 29th
PACE = {"Operation Swan": 2400, "A": 2000, "B": 1500, "C": 900, "D": 700, "E": 300, "Tiny": 100}


def series(awards, hours=10):
    """Hourly lines ending two hours after the poll hour; `awards` {team: points added at the poll hour}."""
    lines, score = [], {t: 20_000 if t != "Tiny" else 500 for t in PACE}
    for k in range(-hours, 3):
        at = POLL_HOUR + dt.timedelta(hours=k)
        for t, p in PACE.items():
            score[t] += p + (awards.get(t, 0) if k == 0 else 0)
        lines.append(dict(ts=at.isoformat(), scores=dict(score)))
    return lines


def test_a_win_by_the_other_side_marks_the_paid_teams_yes_and_the_unpaid_eligible_teams_no():
    got = sides.attribute(series({"A": 6000, "C": 6000, "E": 6000}), "Poll 3", DAY, 7000)
    assert got["status"] == "win"
    assert got["sides"] == {"A": "yes", "C": "yes", "E": "yes", "Operation Swan": "no", "B": "no", "D": "no"}
    assert "Tiny" not in got["sides"]                       # under the 7,000 bar: not eligible, so unknown
    assert got["evidence"]["A"].startswith("+") and got["evidence"]["B"].startswith("no award")


def test_a_win_that_pays_us_marks_the_paid_teams_no():
    got = sides.attribute(series({"Operation Swan": 6000, "B": 6000, "D": 6000}), "Poll 3", DAY, 7000)
    assert got["sides"] == {"Operation Swan": "no", "B": "no", "D": "no", "A": "yes", "C": "yes", "E": "yes"}


def test_a_too_close_poll_pays_everyone_and_says_nothing():
    got = sides.attribute(series({t: 3000 for t in PACE}), "Poll 3", DAY, 7000)
    assert got["status"] == "close" and got["sides"] == {}


def test_no_poll_hour_in_the_lines_is_none_and_a_lone_jump_is_not_a_poll():
    assert sides.attribute(series({}), "Poll 3", DAY, 7000)["status"] == "none"
    assert sides.attribute(series({"A": 6000}), "Poll 3", DAY, 7000)["status"] == "none"
    assert sides.attribute([], "Poll 3", DAY, 7000)["status"] == "none"


def test_poll_two_is_read_from_the_first_and_third_place_scores():
    # the all-teams series starts after the poll; the board series (first, third, ours) spans it
    base = dt.datetime(2026, 10, 24, 14, 3, tzinfo=dt.timezone.utc)
    board = []
    first, third, ours = 100_000, 90_000, 55_000
    for k in range(16):                                   # 14:03 on the 24th to 05:03 on the 25th, like the live series
        first += 900 + (6200 if k == 7 else 0)
        third += 800 + (5000 if k == 7 else 0)
        ours += 900
        board.append(dict(ts=(base + dt.timedelta(hours=k)).isoformat(), score=ours, first=first, third=third))
    lines = [dict(ts="2026-10-25T04:32:00+00:00", scores={"Vertex": board[-1]["first"], "Placeholder": board[-1]["third"], "Us": 1, "Other": 5})]
    got = sides.attribute_first_third(board, lines, "Poll 2", dt.date(2026, 10, 25))
    assert got["sides"] == {"Vertex": "yes", "Placeholder": "yes"} and got["status"] == "win"
    assert "1st place gained" in got["evidence"]["Vertex"]
    lines[0]["scores"]["Other"] = board[-1]["first"]       # two teams on one score: nobody is named
    assert sides.attribute_first_third(board, lines, "Poll 2", dt.date(2026, 10, 25))["sides"] == {"Placeholder": "yes"}


def test_merge_keeps_the_first_side_and_records_a_conflict():
    state = sides.merge({}, dict(poll="Poll 2", status="win", at="x", sides={"A": "yes"}, evidence={"A": "e"}))
    state = sides.merge(state, dict(poll="Poll 3", status="win", at="y", sides={"A": "no", "B": "no"}, evidence={}))
    assert state["teams"]["A"]["side"] == "yes" and state["teams"]["B"]["side"] == "no"
    assert state["conflicts"] == [dict(team="A", poll="Poll 3", side="no", kept="yes")]


def test_labels_and_clearance():
    state = {"teams": {"Y": dict(side="yes"), "N": dict(side="no")}}
    assert [sides.label(sides.side_of(state, t)) for t in ("Y", "N", "Z", "Operation Swan")] == ["(Yes)", "(No)", "(?)", "(No)"]
    rows = [dict(rank=1, team="N", score=200), dict(rank=2, team="Z", score=190), dict(rank=3, team="Operation Swan", score=180),
            dict(rank=4, team="Y", score=150)]
    c = sides.clearance(rows, state, 180, 3)
    assert c["over4"] == 30 and c["fourth"] == "Y"
    assert c["rival"] == "Z" and c["rival_side"] == "(?)" and c["margin"] == -10         # unknown counts against us; a known No does not
    state["teams"]["Z"] = dict(side="no")
    assert sides.clearance(rows, state, 180, 3)["rival"] == "Y"
    assert sides.clearance(rows, state, 100, 6)["over4"] is None                          # outside the top three: no margin over 4th


def test_update_saves_once_and_a_bad_file_does_not_raise(tmp_path):
    now = dt.datetime(2026, 10, 29, 12, tzinfo=dt.timezone.utc)
    (tmp_path / "team_scores.jsonl").write_text("".join(json.dumps(x) + "\n" for x in series({"A": 6000, "C": 6000})) + "not json\n")
    state = sides.update(tmp_path, now)
    assert state["teams"]["A"]["side"] == "yes" and (tmp_path / "team_sides.json").exists()
    stamp = (tmp_path / "team_sides.json").stat().st_mtime_ns
    assert sides.update(tmp_path, now) == state and (tmp_path / "team_sides.json").stat().st_mtime_ns == stamp   # unchanged: not rewritten
    assert sides.update(tmp_path / "nowhere", now) == {}


def test_leaderboard_shows_yes_no_or_unknown_after_each_name_and_the_clearance(tmp_path):
    full = dict(ts.leaderboard_portal(), rank=2, score=79_500, above=dict(rank=1, team="Alpha", score=82_000),
                below=dict(rank=3, team="Gamma", score=72_000))
    full["top"] = [dict(rank=1, team="Alpha", score=82_000), dict(rank=2, team="Operation Swan", score=79_500),
                   dict(rank=3, team="Gamma", score=72_000)]
    full["leader"] = full["top"][0]
    full["rows"] = [dict(rank=1, team="Alpha", score=82_000), dict(rank=2, team="Operation Swan", score=79_500),
                    dict(rank=3, team="Gamma", score=72_000), dict(rank=4, team="Delta", score=60_000),
                    dict(rank=5, team="Epsilon", score=50_000)]
    root = ts.build_root(tmp_path, ts.NOW, [td.write(3)], extra_portal=full)
    (root / "data" / "team_sides.json").write_text(json.dumps(dict(
        teams={"Gamma": dict(side="yes", poll="Poll 2"), "Delta": dict(side="no", poll="Poll 3")}, polls={"Poll 2": dict(status="win")})))
    ctx, html = ts.gather(root, ts.NOW)
    b = ctx["board"]
    assert [(r["team"], r["side"]) for r in b["finalists"]] == [("Alpha", "(?)"), ("Operation Swan", "(No)"), ("Gamma", "(Yes)")]
    assert b["fourth"]["team"] == "Delta" and b["fourth"]["side"] == "(No)" and [r["team"] for r in b["top10"]] == ["Delta", "Epsilon"]
    assert b["clearance"]["over4"] == 19_500 and b["clearance"]["rival"] == "Alpha" and b["clearance"]["margin"] == -2_500
    text = ts.plain(html)
    assert "Alpha (?)" in text and "Gamma (Yes)" in text and "Delta (No)" in text
    assert "Clear of #4 (Delta) by 19,500" in text and "best team not known to be No: Alpha (?)" in text and "-2,500" in text.replace("−", "-")
