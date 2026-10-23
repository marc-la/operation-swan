"""Dashboard stealth rates and the bans forecast (todo/42): the Wilson hide rate with its 3.6 h censor, writes per ban
from voices still alive, one bans number, the forecast rows for the x1, x2 and x4 days, and the leaderboard gap to 3rd.
Synthetic logs; the pure maths module (todo/39) is pinned to tests/_budget_stub.py so no number here depends on it."""
import datetime as dt
import json
import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import _budget_stub  # noqa: E402
import test_dash as td  # noqa: E402
from swan_dash import build  # noqa: E402

NOW = td.NOW                                                              # 22 Oct 06:00 UTC
T24 = dt.datetime(2026, 10, 24, 6, 0, tzinfo=dt.timezone.utc)             # 17:00 Sydney on 24 Oct (a x1 day)
PLAN = {f"2026-10-{d}": w for d, w in {24: 2320, 25: 2320, 26: 3480, 27: 3480, 28: 3480, 29: 3480, 30: 3480, 31: 3480}.items()}
PLAN.update({"2026-11-01": 4320, "2026-11-02": 4320})                      # x1: 16 bans at 145 a ban; x2: 24; x4: 29.8


@pytest.fixture(autouse=True)
def pinned_budget(monkeypatch):
    monkeypatch.setattr(build, "budget", _budget_stub.MODULE)
    monkeypatch.setattr(build.bot_config, "BAN_PLAN", PLAN, raising=False)
    monkeypatch.setattr(build.bot_config, "RESERVE_GOAL", 60, raising=False)
    monkeypatch.setattr(build.bot_config, "RESERVE_DAY", "2026-10-31", raising=False)
    monkeypatch.setattr(build.bot_config, "WRITES_PER_BAN_DEFAULT", 145, raising=False)
    monkeypatch.setattr(build.bot_config, "BUDGET_END_DAY", "2026-11-02", raising=False)


def at(now, hours_ago):
    return (now - dt.timedelta(hours=hours_ago)).isoformat()


def text_write(now, hours_ago, pid, user="lani_42", act="reply", **kw):
    return {"ts": at(now, hours_ago), "act": act, "live": True, "username": user, "post_id": pid, "text": "x", **kw}


def build_root(tmp_path, now, actions=(), counts=None, suspended=None, hidden=(), extra_portal=None):
    root = td.make_root(tmp_path, actions)
    now_iso = now.isoformat()
    portal = {"ts": now_iso, "account_log": {"counts": counts or [], "suspended": suspended or []}, **(extra_portal or {})}
    (root / "data" / "portal.json").write_text(json.dumps(portal))
    (root / "data" / "status.json").write_text(json.dumps({"ts": now_iso, "per_min": 2.5, "llm": [], "accounts": {}}))
    if hidden:
        (root / "logs" / "swan_watch.jsonl").write_text("".join(
            json.dumps({"ts": now_iso, "act": "hidden_post", "username": u, "post_id": p}) + "\n" for u, p in hidden))
    return root


def gather(root, now):
    ctx = build.gather(root, now, "active")
    return ctx, build.render(ctx)


def counts_24(**over):
    rows = [dict(ts="2026-10-20T10:00:00+00:00", registered=20, banned=0),
            dict(ts="2026-10-22T10:00:00+00:00", registered=58, banned=12),
            dict(ts="2026-10-23T10:00:00+00:00", registered=73, banned=25),         # the end of 23 Oct (Sydney)
            dict(ts="2026-10-24T02:00:00+00:00", registered=75, banned=28)]         # 24 Oct so far: +2 registered, +3 banned
    return rows


def plain(html):
    return re.sub(r"\s+([,.·)])", r"\1", " ".join(re.sub(r"<[^>]+>", " ", html).split()))


def stealth_row(ctx, name):
    return next(r for r in ctx["reach"]["rows"] if r["name"].startswith(name))


# ---- Wilson interval ----
def test_wilson_edges():
    assert build.wilson(0, 0) is None
    lo, hi = build.wilson(0, 100)
    assert lo == 0.0 and hi == pytest.approx(0.0370, abs=5e-4)               # zero hits: a real upper bound, not zero width
    lo, hi = build.wilson(100, 100)
    assert hi == 1.0 and lo == pytest.approx(0.9630, abs=5e-4)
    lo, hi = build.wilson(0, 1)
    assert lo == 0.0 and hi == pytest.approx(0.7935, abs=1e-3)               # a single clean write says almost nothing
    lo, hi = build.wilson(1, 1)
    assert hi == 1.0 and lo == pytest.approx(0.2065, abs=1e-3)
    lo, hi = build.wilson(66, 4664)                                          # the 23 Oct figure: 1.37% [1.08, 1.75]
    assert (lo, hi) == (pytest.approx(0.0111, abs=3e-4), pytest.approx(0.0180, abs=3e-4))
    assert build.wilson(5, 3) == build.wilson(3, 3) and build.wilson(-2, 10) == build.wilson(0, 10)     # k is clamped


# ---- the log pass and the 3.6 h censor ----
def test_life_scan_counts_only_our_live_text_writes_and_survives_junk(tmp_path):
    rows = [text_write(NOW, 5, 1), text_write(NOW, 5, 1),                        # the same post logged twice: one write
            text_write(NOW, 5, 2, act="repost"),                                 # a repost: a write, not a text write
            dict(text_write(NOW, 5, 3), live=False),                             # a dry run
            {"ts": at(NOW, 5), "act": "like", "live": True, "username": "lani_42"},
            {"ts": at(NOW, 5), "act": "repost", "post_id": 9, "username": "booster_1"},    # the swarm's rows have no live flag
            text_write(NOW, 30, 4),                                              # before the window
            {"ts": at(NOW, 1), "act": "suspended", "username": "gone_7"}]
    path = tmp_path / "a.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows) + "garbage\n" + '{"ts": "2026-10-22T05:00:00+00:00", "act": "reply"')
    life = build.life_scan(path, NOW - dt.timedelta(hours=25))
    assert sorted(life["text"]) == ["1"] and life["voice_posts"]["lani_42"] == {"1", "4"}
    assert sum(life["day_writes"].values()) == 4 and "gone_7" in life["dead"]
    assert build.life_scan(tmp_path / "missing.jsonl", NOW)["text"] == {}


def test_hide_rate_counts_only_writes_at_least_3_6_h_old(tmp_path):
    rows = [text_write(NOW, 5 + i / 100, 100 + i) for i in range(10)]            # 10 old enough (5 h)
    rows += [text_write(NOW, 2, 200 + i) for i in range(5)]                      # 5 too young: the hide has not shown yet
    rows += [text_write(NOW, 26, 300 + i) for i in range(3)]                     # 3 outside the 24 h window
    path = tmp_path / "a.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    life = build.life_scan(path, NOW - dt.timedelta(hours=25))
    hr = build.hide_rate(life, {"100", "101", "200", "300"}, NOW)                # a young and an old-window hide are not counted
    assert (hr["n"], hr["k"]) == (10, 2) and hr["rate"] == 0.2
    assert hr["lo"] < 0.2 < hr["hi"]
    assert build.hide_rate(life, set(), NOW)["rate"] == 0.0
    assert build.hide_rate(build.life_scan(tmp_path / "none", NOW), set(), NOW) == dict(n=0, k=0, rate=None, lo=None, hi=None)


def hide_tile(tmp_path, n, k):
    writes = [text_write(NOW, 6 + (i % 100) / 100, 1000 + i, user=f"v{i % 20}") for i in range(n)]
    hidden = [(f"v{i % 20}", 1000 + i) for i in range(k)]
    ctx, _ = gather(build_root(tmp_path, NOW, writes, hidden=hidden), NOW)
    return stealth_row(ctx, "Hide rate"), ctx


def test_hide_rate_row_colours_by_whether_the_interval_clears_the_target(tmp_path):
    for n, k, want in ((400, 0, "green"), (400, 6, "amber"), (400, 40, "red"), (299, 0, "grey")):
        row, ctx = hide_tile(tmp_path / f"h{n}-{k}", n, k)
        assert row["light"] == want, (n, k, row["now"])
    green, _ = hide_tile(tmp_path / "x", 400, 0)
    assert green["now"].startswith("0.00% [0.00%–0.95%] · 0 hidden of 400 text writes")
    grey, _ = hide_tile(tmp_path / "y", 120, 3)
    assert "n = 120" in grey["now"] and grey["light"] == "grey"
    empty, ctx = hide_tile(tmp_path / "z", 0, 0)
    assert empty["light"] == "grey" and "no text writes old enough" in empty["now"]


def test_hidden_count_row_stays_green_but_the_rate_row_may_colour_the_tile(tmp_path):
    row, ctx = hide_tile(tmp_path, 400, 40)
    assert stealth_row(ctx, "Posts hidden")["light"] == "green"                 # Marc, 23 Oct: the count never colours
    assert td.light(ctx, "stealth") == "red"                                     # the rate (a rate with an interval) may


def test_hidden_posts_are_found_in_the_watch_log_and_the_alert_log(tmp_path):
    root = build_root(tmp_path, NOW, hidden=[("a", 5)])
    (root / "logs" / "alerts.log").write_text(f"{at(NOW, 1)[:19]}Z [swan-ec2] @b: post #6 hidden by the moderator (1 hidden)\n")
    assert build.hidden_posts(root / "logs") == {"5": "a", "6": "b"}
    assert build.hidden_posts(tmp_path / "nowhere") == {}


# ---- writes per ban: the voices, censored ----
def test_voice_lives_censors_a_voice_that_is_still_alive(tmp_path):
    rows = [text_write(NOW, 10 + i / 10, 10 * 100 + i, user="alive") for i in range(50)]
    rows += [text_write(NOW, 30 + i / 10, 2000 + i, user="dead") for i in range(80)]
    rows += [text_write(NOW, 100 + i / 10, 3000 + i, user="old_dead") for i in range(60)]       # banned 4 days ago
    rows += [text_write(NOW, 100 + i / 10, 4000 + i, user="old_alive") for i in range(60)]      # alive but silent for 4 days
    rows += [text_write(NOW, 5, 5000, user="repost_only", act="repost")]
    path = tmp_path / "a.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    life = build.life_scan(path, NOW)
    banned_at = {"dead": NOW - dt.timedelta(hours=20), "old_dead": NOW - dt.timedelta(hours=90), "unseen": NOW}
    lives = build.voice_lives(life, banned_at, NOW)
    assert lives == [dict(username="alive", writes=50, banned=False), dict(username="dead", writes=80, banned=True)]
    km = _budget_stub.km_writes_per_ban(lives)                                   # alive is censored, not counted as a ban
    assert (km["n_banned"], km["n_alive"], km["median"]) == (1, 1, 80.0)


def test_writes_per_ban_row_and_the_forecast_use_the_km_median_once_there_are_enough_bans(tmp_path):
    rows, suspended = [], []
    for v in range(6):                                                            # six voices banned at 100 text writes
        rows += [text_write(T24, 30 + v + i / 100, 10_000 * (v + 1) + i, user=f"dead{v}") for i in range(100)]
        suspended.append(dict(ts=at(T24, 12), username=f"dead{v}", id=v, why="3 posts hidden"))
    for v in range(4):
        rows += [text_write(T24, 20 + v + i / 100, 90_000 + 100 * v + i, user=f"live{v}") for i in range(50)]
    ctx, html = gather(build_root(tmp_path, T24, rows, counts_24(), suspended), T24)
    row = stealth_row(ctx, "Writes per ban")
    assert row["now"] == "100 text writes" and "6 banned, 4 alive" in row["target"]
    assert ctx["forecast"]["wpb"] == 100 and ctx["forecast"]["wpb_src"] == "Kaplan-Meier"
    assert next(r for r in ctx["forecast"]["rows"] if r["date"] == "2026-10-24")["forecast"] == pytest.approx(23.2)


def test_default_writes_per_ban_below_five_bans(tmp_path):
    ctx, _ = gather(build_root(tmp_path, T24, [text_write(T24, 6, 1)], counts_24()), T24)
    assert ctx["forecast"]["wpb"] == 145 and ctx["forecast"]["wpb_src"] == "default"
    assert "too few bans" in stealth_row(ctx, "Writes per ban")["now"] and "145" in stealth_row(ctx, "Writes per ban")["now"]


# ---- one bans number ----
def test_the_bans_number_comes_from_the_counts_row_with_the_lag_to_the_list():
    names = [dict(ts="2026-10-23T15:00:00+00:00", username=f"u{i}", id=i, why="3 posts hidden") for i in range(21)]
    log = dict(counts=[dict(ts="2026-10-23T14:00:00+00:00", registered=70, banned=20),
                       dict(ts="2026-10-23T16:03:00+00:00", registered=73, banned=25)], suspended=names)
    fig = build.ban_figures(log, {"registered": 70, "banned": 20})              # the team page is older: the counts row wins
    assert (fig["registered"], fig["banned"], fig["listed"], fig["lag"]) == (73, 25, 21, 4)
    assert fig["text"] == "25 banned (list shows 21)"
    caught_up = build.ban_figures(dict(log, suspended=names + [dict(names[0], id=100 + i, username=f"x{i}") for i in range(4)]), None)
    assert caught_up["lag"] == 0 and caught_up["text"] == "25 banned"
    assert build.ban_figures(None, {"registered": 61, "banned": 13})["text"] == "13 banned"      # no log: no lag to show
    assert build.ban_figures(None, None) is None and build.ban_figures({}, {"registered": "x"}) is None


def test_a_day_with_a_counts_row_but_no_suspended_rows_yet(tmp_path):
    log = dict(counts=counts_24(), suspended=[])
    days, listed = build.account_days(log, T24)
    today = days[0]
    assert (today["new"], today["why"], today["unnamed"], listed) == (3, "", 3, [])
    ctx, html = gather(build_root(tmp_path, T24, [text_write(T24, 6, 1)], counts_24()), T24)
    assert "28 banned (list shows 0)" in html and "3 not named yet" in html
    assert ctx["reach"]["lights"][-1]["head"] == "3 bans"                        # the tile still counts from the counts row
    assert stealth_row(ctx, "Banned in total")["now"] == "28 banned (list shows 0) of 75 registered"
    partly = build.account_days(dict(log, suspended=[dict(ts="2026-10-24T03:00:00+00:00", username="a", id=1, why="3 posts hidden")]), T24)[0][0]
    assert partly["unnamed"] == 2 and partly["why"] == "3 posts hidden ×1"


def test_bot_header_stealth_tile_and_accounts_line_say_the_same_number(tmp_path):
    names = [dict(ts="2026-10-24T01:00:00+00:00", username=f"u{i}", id=i, why="reported as a bot") for i in range(21)]
    ctx, html = gather(build_root(tmp_path, T24, [text_write(T24, 6, 1)], counts_24(), names), T24)
    assert html.count("28 banned (list shows 21)") >= 3                          # header, Accounts line, Stealth tile
    assert "28 banned ·" not in html and "28 banned<" not in html


# ---- the forecast: x1, x2 and x4 days ----
def rows_of(ctx):
    return {r["date"]: r for r in ctx["forecast"]["rows"]}


def test_forecast_rows_for_the_x1_x2_and_x4_days(tmp_path):
    ctx, _ = gather(build_root(tmp_path, T24, [text_write(T24, 6, 1)], counts_24()), T24)
    rows = rows_of(ctx)
    assert list(rows)[0] == "2026-10-20" and list(rows)[-1] == "2026-11-02"       # the first day on the portal to the budget end
    assert [rows[d]["mult"] for d in ("2026-10-25", "2026-10-26", "2026-10-31", "2026-11-01", "2026-11-02")] == [1, 2, 2, 4, 4]
    assert rows["2026-10-25"]["forecast"] == pytest.approx(16.0)
    assert rows["2026-10-26"]["forecast"] == pytest.approx(24.0)
    assert rows["2026-11-01"]["forecast"] == pytest.approx(4320 / 145)
    assert all(rows[d]["src"] == "plan" and rows[d]["planned"] for d in rows if d >= "2026-10-24")
    assert rows["2026-10-23"]["forecast"] is None and rows["2026-10-23"]["spare"] == 127        # history: actual balance, no forecast
    # the balance chain starts from the counts at the START of today (48 alive, 127 spare) and each ban takes a spare registration
    assert (rows["2026-10-24"]["alive"], rows["2026-10-24"]["spare"]) == (48, 111)
    assert rows["2026-10-25"]["spare"] == 95 and rows["2026-10-26"]["spare"] == 71
    assert rows["2026-10-29"]["spare"] == 0 and rows["2026-10-31"]["alive"] < 48     # the spares run out: alive starts to fall
    assert rows["2026-10-31"]["goal_delta"] == -60 and rows["2026-10-30"]["goal_delta"] is None
    assert ctx["forecast"]["status"]["on_track"] is False


def test_today_compares_bans_so_far_with_the_forecast_for_the_part_of_the_day_gone(tmp_path):
    ctx, html = gather(build_root(tmp_path, T24, [text_write(T24, 6, 1)], counts_24()), T24)
    today = rows_of(ctx)["2026-10-24"]
    assert today["today"] and today["actual"] == 3 and today["forecast"] == pytest.approx(16.0)
    due = 16.0 * 17 / 24                                                          # 17:00 Sydney
    assert today["net"] == pytest.approx(3 - due) and today["tol"] == 5 and today["level"] == "up"     # well under: green
    s = ctx["forecast"]["summary"]
    assert s.startswith("bans today 3 · forecast 16 · net −8 · spare 125 · off track for 31 Oct: −60")
    assert "acct-plan" in html and "⋮" in html and s in html


def test_net_is_red_above_the_tolerance_and_plain_inside_it(tmp_path):
    for new, want in ((18, "down"), (13, ""), (3, "up")):                          # 17:00 Sydney: 11.3 due so far, tolerance 5
        counts = counts_24()
        counts[-1] = dict(counts[-1], banned=25 + new)
        ctx, _ = gather(build_root(tmp_path / str(new), T24, [text_write(T24, 6, 1)], counts), T24)
        today = rows_of(ctx)["2026-10-24"]
        assert (today["actual"], today["level"]) == (new, want)
    # a day that is over (25 Oct, seen on the 26th) is held to the whole forecast: 16, tolerance 6
    t26 = T24 + dt.timedelta(days=2)
    counts = counts_24() + [dict(ts="2026-10-25T10:00:00+00:00", registered=90, banned=28 + 25),    # +25 on 25 Oct: net +9, tol 6
                            dict(ts="2026-10-26T02:00:00+00:00", registered=91, banned=28 + 25 + 1)]
    ctx, _ = gather(build_root(tmp_path / "t26", t26, [text_write(t26, 6, 1)], counts), t26)
    rows = rows_of(ctx)
    assert rows["2026-10-25"]["actual"] == 25 and rows["2026-10-25"]["net"] == pytest.approx(9.0)
    assert rows["2026-10-25"]["tol"] == 6 and rows["2026-10-25"]["level"] == "down"
    assert rows["2026-10-24"]["actual"] == 3 and rows["2026-10-24"]["level"] == "up"     # 3 against 16: well under
    assert rows["2026-10-26"]["today"] and rows["2026-10-26"]["mult"] == 2


def test_on_track_when_the_plan_leaves_the_reserve(tmp_path, monkeypatch):
    light = {k: 870 for k in PLAN}                                                  # 6 bans a day
    monkeypatch.setattr(build.bot_config, "BAN_PLAN", light, raising=False)
    ctx, _ = gather(build_root(tmp_path, T24, [text_write(T24, 6, 1)], counts_24()), T24)
    f = ctx["forecast"]
    assert f["status"]["on_track"] is True and f["status"]["delta"] == pytest.approx(127 - 8 * 6 - 60)
    assert "on track for 31 Oct: +19" in f["summary"] and not any("off track" in a for a in f["alerts"])


def test_alert_when_bans_run_over_the_forecast(tmp_path):
    counts = counts_24()
    counts[-1] = dict(counts[-1], banned=25 + 30)                                   # 30 bans in a day against 16
    ctx, html = gather(build_root(tmp_path, T24, [text_write(T24, 6, 1)], counts), T24)
    assert any("running over forecast" in a for a in ctx["forecast"]["alerts"])
    assert any("off track" in a for a in ctx["forecast"]["alerts"]) and "running over forecast" in html


def test_a_day_without_a_plan_uses_actual_writes_then_the_three_day_average(tmp_path, monkeypatch):
    monkeypatch.setattr(build.bot_config, "BAN_PLAN", {}, raising=False)
    writes = [text_write(T24, 24 * d + 3 + i / 100, 1000 * d + i, user=f"v{i % 5}") for d in (1, 2, 3, 4) for i in range(10 * d)]
    ctx, _ = gather(build_root(tmp_path, T24, writes, counts_24()), T24)
    rows = rows_of(ctx)
    assert rows["2026-10-24"]["src"] == "average" and rows["2026-11-02"]["src"] == "average"
    assert rows["2026-10-26"]["planned"] == pytest.approx((10 + 20 + 30) / 3)       # 10, 20, 30 writes on 23, 22, 21 Oct; the 40 on 20 Oct is older
    t26 = T24 + dt.timedelta(days=2)                                                # two days on, 24 and 25 Oct are over: their own writes
    past = [text_write(t26, 44 + i, 5000 + i) for i in range(4)] + [text_write(t26, 20, 6000)]      # 24 Oct (x4), 25 Oct (x1)
    ctx, _ = gather(build_root(tmp_path / "t26", t26, past, counts_24()), t26)
    assert (rows_of(ctx)["2026-10-24"]["src"], rows_of(ctx)["2026-10-24"]["planned"]) == ("actual", 4)
    ctx, _ = gather(build_root(tmp_path / "b", T24, [], counts_24()), T24)           # nothing known at all: no forecast, no crash
    assert ctx["forecast"] is None


def test_without_the_budget_module_the_old_table_stays(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "budget", None)
    ctx, html = gather(build_root(tmp_path, T24, [text_write(T24, 6, 1)], counts_24()), T24)
    assert ctx["forecast"] is None and 'id="acct-plan"' not in html and "New bans" in html
    assert "Writes per ban" not in [r["name"] for r in ctx["reach"]["rows"]]


def test_runway_and_the_summary_row_on_the_stealth_tile(tmp_path):
    ctx, _ = gather(build_root(tmp_path, T24, [text_write(T24, 6, 1)], counts_24()), T24)
    runway = stealth_row(ctx, "Runway")
    assert runway["light"] == "grey"                                                # informational: the Pool line carries the alarm
    assert runway["now"].startswith(f"{125 / 16:.1f} d of spare accounts · ") and " d left" in runway["now"]
    assert "125 spare ÷ 16.0 bans a day (2320 planned writes ÷ 145 per ban, default)" in runway["target"]
    assert stealth_row(ctx, "Bans against the plan")["now"].startswith("bans today 3 · forecast 16")


# ---- hides per voice before a ban ----
def test_hides_per_voice_before_a_ban_is_skipped_without_data():
    assert build.hides_per_voice({}, ["a", "b", "c"]) is None
    assert build.hides_per_voice({"1": "a"}, ["a", "b"]) is None                    # fewer than three banned voices
    got = build.hides_per_voice({"1": "a", "2": "a", "3": "b", "4": "zz"}, ["a", "b", "c", "d", "e"])
    assert got == dict(median=0, n=5, with_hide=2)
    got = build.hides_per_voice({"1": "a", "2": "a", "3": "b", "4": "c", "5": "c", "6": "c"}, ["a", "b", "c"])
    assert got["median"] == 2 and got["with_hide"] == 3


def test_hides_row_appears_only_with_data(tmp_path):
    suspended = [dict(ts=at(T24, 5), username=u, id=i, why="3 posts hidden") for i, u in enumerate("abc")]
    ctx, _ = gather(build_root(tmp_path / "a", T24, [text_write(T24, 6, 1)], counts_24(), suspended), T24)
    assert "Hides before a ban" not in [r["name"] for r in ctx["reach"]["rows"]]
    ctx, _ = gather(build_root(tmp_path / "b", T24, [text_write(T24, 6, 1)], counts_24(), suspended,
                               hidden=[("a", 1), ("a", 2), ("b", 3)]), T24)
    assert "median 1 per banned voice · 2 of 3 had one" in stealth_row(ctx, "Hides before")["now"]


# ---- leaderboard gap to 3rd ----
def test_gap_trend_over_6_and_24_hours():
    rows = [dict(ts=at(NOW, 24), score=22_000, third=58_000), dict(ts=at(NOW, 6.2), score=29_000, third=69_500),
            dict(ts=at(NOW, 1), score=31_000, third=71_000), {"junk": 1}]
    got = build.gap_trend(rows, NOW, 32_000, 72_000)
    assert got["gap"] == 40_000 and got["points"] == 3
    six, day = got["windows"]
    assert (six["hours"], six["then"], six["change"], six["us"], six["them"]) == (6, 40_500, -500, 3_000, 2_500)   # closing
    assert (day["hours"], day["then"], day["change"]) == (24, 36_000, 4_000)                                       # widening
    assert build.gap_trend(rows[2:3], NOW, 32_000, 72_000)["windows"] == []         # one recent line: nothing 6 or 24 h back
    assert build.gap_trend([], NOW, 1, 2) == dict(gap=1, windows=[], points=0)


def leaderboard_portal(score=32_000):
    top = [dict(rank=1, team="Alpha", score=82_000), dict(rank=2, team="Beta", score=79_000),
           dict(rank=3, team="Gamma", score=72_000)]
    return dict(rank=10, score=score, teams=157, leader=top[0], top=top, rows=top,
                above=dict(rank=9, team="Nine", score=33_000), below=dict(rank=11, team="Eleven", score=31_000))


def test_leaderboard_area_shows_the_gap_and_whether_it_is_closing(tmp_path):
    root = build_root(tmp_path, NOW, [td.write(3)], extra_portal=leaderboard_portal())
    (root / "data" / "leaderboard.jsonl").write_text("".join(json.dumps(r) + "\n" for r in (
        dict(ts=at(NOW, 24), rank=14, score=22_000, first=60_000, third=58_000, teams=157),
        dict(ts=at(NOW, 6), rank=11, score=29_000, first=79_000, third=69_500, teams=157))))
    ctx, html = gather(root, NOW)
    assert ctx["board"]["cutoff"] == 40_000 and [w["hours"] for w in ctx["board"]["trend"]["windows"]] == [6, 24]
    text = plain(html)
    assert "40,000 behind #3" in text and "closing 500 in 6 h (us +3,000, #3 +2,500)" in text
    assert "widening 4,000 in 24 h (us +10,000, #3 +14,000)" in text
    assert [r["rank"] for r in ctx["board"]["finalists"]] == [1, 2, 3]            # the layout is unchanged: top three, a gap, us


def test_leaderboard_gap_with_no_history_says_so_and_in_the_top_three_shows_nothing(tmp_path):
    ctx, html = gather(build_root(tmp_path, NOW, [td.write(3)], extra_portal=leaderboard_portal()), NOW)
    assert ctx["board"]["trend"]["windows"] == [] and "Gap to #3: history building, 0 hourly points so far" in html
    top3 = dict(leaderboard_portal(), rank=3, score=72_000)
    ctx, html = gather(build_root(tmp_path / "b", NOW, [td.write(3)], extra_portal=top3), NOW)
    assert ctx["board"]["trend"] is None and "we are in the top three" in html


# ---- secrets and missing files ----
def test_nothing_secret_reaches_the_new_rows_and_missing_files_are_fine(tmp_path, monkeypatch):
    monkeypatch.setenv("CTN_TEAM_CODE", td.CANARY)
    rows = [text_write(T24, 6 + i / 100, 700 + i, user=f"v{i % 7}") for i in range(350)]
    root = build_root(tmp_path, T24, rows, counts_24(), hidden=[("v1", 701)], extra_portal=leaderboard_portal())
    (root / "secrets" / "portal_cookie").write_text(f"session={td.CANARY}\n")
    (root / "data" / "leaderboard.jsonl").write_text(json.dumps(dict(ts=at(T24, 6), score=1, third=2)) + "\n")
    ctx, html = gather(root, T24)
    assert td.CANARY not in html and td.CANARY not in json.dumps(ctx, default=str)
    assert 'id="acct-plan"' in html and "Hide rate" in html and "Gap to #3" in html
    # an empty checkout: no logs, no portal file, no history
    empty = tmp_path / "empty"
    for sub in ("logs", "data"):
        (empty / sub).mkdir(parents=True)
    ctx, html = gather(empty, T24)
    assert ctx["forecast"] is None and ctx["bans"] is None and "Swan" in html
