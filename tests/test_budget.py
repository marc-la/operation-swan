"""todo/39 account budget: swan_bot/budget.py (pure) and the 20-minute job in swan_bot/watch.py that runs it (no network).

Pinned: the Kaplan-Meier median on hand-worked cases (all censored, few bans, ties, exactly 0.5), the seeded bootstrap, the
forecast arithmetic (spare runs out, plan fallback), reserve_status, the alert thresholds, de-duplication, the Sydney day
boundary (AEDT, UTC+11 from 4 Oct 2026), and the voice list built from synthetic log rows, records and portal data.
It is a forecast and an alert: nothing here may throttle writes or block the pool (test_job_changes_nothing).
"""
import datetime as dt
import json
import socket

import pytest

from swan_bot import budget, config, watch


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **kw):
        raise OSError("tests/test_budget.py: no network in tests")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def ts(s):
    return dt.datetime.fromisoformat(s).timestamp()


def vs(banned=(), alive=()):
    return [{"writes": w, "banned": True} for w in banned] + [{"writes": w, "banned": False} for w in alive]


# ---- Kaplan-Meier -----------------------------------------------------------------------------------------------------
def test_km_all_banned_is_the_ordinary_median():
    km = budget.km_writes_per_ban(vs(banned=[100, 120, 140]))     # S: 2/3 at 100, 1/3 at 120 -> median 120
    assert km["median"] == 120 and km["n_banned"] == 3 and km["n_alive"] == 0
    assert km["lo"] is None and km["hi"] is None                  # under 5 bans: no interval


def test_km_censoring_moves_the_median_up():
    # 50 is censored first, leaving 3 at risk: S(100) = 2/3, S(120) = 1/3 -> 120 (not the median of the banned, 120 too)
    assert budget.km_writes_per_ban(vs(banned=[100, 120, 140], alive=[50]))["median"] == 120
    # a censored voice that outlives everything: S(100)=0.8, S(110)=0.6, never 0.5 -> None
    km = budget.km_writes_per_ban(vs(banned=[100, 110], alive=[300, 300, 300]))
    assert km["median"] is None and km["n_banned"] == 2 and km["n_alive"] == 3


def test_km_all_censored_and_empty():
    km = budget.km_writes_per_ban(vs(alive=[10, 50, 90]))
    assert km == {"median": None, "lo": None, "hi": None, "n_banned": 0, "n_alive": 3}
    assert budget.km_writes_per_ban([])["median"] is None


def test_km_survival_of_exactly_half_counts_and_ties_ban_first():
    # S(10) = 3/4, S(20) = 3/4 * (1 - 1/3) = 1/2 exactly: the median is 20
    assert budget.km_writes_per_ban(vs(banned=[10, 20], alive=[30, 40]))["median"] == 20
    # at 100 a ban and a censored voice tie: the ban sees both at risk (S = 2/3), then at 200 the last one is banned
    assert budget.km_writes_per_ban([{"writes": 100, "banned": True}, {"writes": 100, "banned": False},
                                     {"writes": 200, "banned": True}])["median"] == 200


def test_km_bootstrap_interval_is_seeded_and_brackets_the_median():
    voices = vs(banned=range(100, 200, 10), alive=[60, 80, 100, 120, 140])
    a, b = budget.km_writes_per_ban(voices), budget.km_writes_per_ban(list(reversed(voices)))
    assert a == b, "the same voices give the same answer, whatever their order"
    assert a["n_banned"] == 10 and a["median"] is not None
    assert a["lo"] <= a["median"] <= a["hi"]
    assert budget.km_writes_per_ban(voices) == a


def test_km_interval_needs_five_bans():
    four = budget.km_writes_per_ban(vs(banned=[90, 100, 110, 120]))
    assert four["median"] == 100 and four["lo"] is None and four["hi"] is None
    five = budget.km_writes_per_ban(vs(banned=[90, 100, 110, 120, 130]))
    assert five["median"] == 110 and five["lo"] is not None and five["hi"] is not None


# ---- the forecast -----------------------------------------------------------------------------------------------------
def test_forecast_spare_runs_out_and_alive_falls():
    plan = {"2026-10-24": 290, "2026-10-26": 580}                  # 2 bans, then 4 a day
    rows = budget.forecast_days(plan, 145, alive=48, spare=5, first_day="2026-10-24", last_day="2026-10-27")
    assert [r["day"] for r in rows] == ["2026-10-24", "2026-10-25", "2026-10-26", "2026-10-27"]
    assert [r["planned_writes"] for r in rows] == [290, 290, 580, 580]      # 25 and 27 take the last given day's value
    assert [r["forecast_bans"] for r in rows] == [2, 2, 4, 4]
    assert [r["spare_end"] for r in rows] == [3, 1, 0, 0]
    assert [r["alive_end"] for r in rows] == [48, 48, 45, 41]      # held at the cap while spare lasts, then falls


def test_forecast_is_a_float_and_never_negative_spare():
    rows = budget.forecast_days({"2026-10-24": 2400}, 145, 48, 100, "2026-10-24", "2026-10-24")
    assert rows[0]["forecast_bans"] == pytest.approx(2400 / 145)
    assert rows[0]["spare_end"] == pytest.approx(100 - 2400 / 145)
    assert budget.forecast_days({"2026-10-24": 2400}, 145, 48, 3, "2026-10-24", "2026-10-25")[-1]["spare_end"] == 0
    assert budget.forecast_days({"2026-10-24": 2400}, 145, 5, 0, "2026-10-24", "2026-10-26")[-1]["alive_end"] == 0


def test_forecast_plan_fallbacks():
    assert budget.plan_for_day({"2026-10-26": 5, "2026-10-28": 9}, "2026-10-24") == 5      # before the plan: the earliest
    assert budget.plan_for_day({"2026-10-26": 5, "2026-10-28": 9}, "2026-10-27") == 5      # between: the last given
    assert budget.plan_for_day({"2026-10-26": 5, "2026-10-28": 9}, "2026-11-02") == 9      # after: the last given
    assert budget.plan_for_day({}, "2026-10-24") == 0
    rows = budget.forecast_days({}, 145, 48, 10, "2026-10-24", "2026-10-25")
    assert all(r["forecast_bans"] == 0 and r["spare_end"] == 10 for r in rows)


def test_forecast_accepts_dates_and_rejects_a_bad_rate():
    rows = budget.forecast_days({"2026-10-24": 145}, 145, 48, 10, dt.date(2026, 10, 24), dt.date(2026, 10, 24))
    assert rows[0]["day"] == "2026-10-24" and rows[0]["forecast_bans"] == 1
    with pytest.raises(ValueError):
        budget.forecast_days({}, 0, 48, 10, "2026-10-24", "2026-10-25")
    assert budget.forecast_days({}, 145, 48, 10, "2026-10-26", "2026-10-25") == []


def test_default_plan_costs_about_what_the_todo_says():
    """127 spare and 2,400 writes a day at 145 a ban is 16.6 bans a day: spare is gone on 31 Oct, 60 short of the goal (the
    todo's 'about 25 spare' assumed 12-16 deaths a day, the observed 22-23 Oct rate)."""
    rows = budget.forecast_days(config.BAN_PLAN, config.WRITES_PER_BAN_DEFAULT, 48, 127, "2026-10-24", config.BUDGET_END_DAY)
    by_day = {r["day"]: r for r in rows}
    assert by_day["2026-10-30"]["spare_end"] == pytest.approx(127 - 7 * 2400 / 145)
    st = budget.reserve_status(rows, config.RESERVE_GOAL, config.RESERVE_DAY)
    assert st["spare_on_reserve_day"] == 0 and st["delta"] == -60 and st["on_track"] is False
    assert by_day["2026-11-02"]["alive_end"] < 48 - 8, "the x4 days then cost live accounts"
    at_12_a_day = budget.forecast_days({"2026-10-24": 12 * 145}, 145, 48, 127, "2026-10-24", "2026-10-31")
    assert at_12_a_day[-1]["spare_end"] == 127 - 8 * 12 == 31


# ---- reserve_status ---------------------------------------------------------------------------------------------------
def test_reserve_status_reads_the_end_of_the_reserve_day():
    rows = [{"day": "2026-10-30", "spare_end": 90.0}, {"day": "2026-10-31", "spare_end": 61.5},
            {"day": "2026-11-01", "spare_end": 10.0}]
    assert budget.reserve_status(rows, 60, "2026-10-31") == {
        "spare_on_reserve_day": 61.5, "goal": 60, "delta": 1.5, "on_track": True}
    assert budget.reserve_status(rows, 60, "2026-11-01")["on_track"] is False
    assert budget.reserve_status(rows, 61.5, "2026-10-31")["on_track"] is True, "delta 0 is on track"
    miss = budget.reserve_status(rows, 60, "2026-11-05")
    assert miss["on_track"] is None and miss["spare_on_reserve_day"] is None and miss["goal"] == 60


# ---- alerts -----------------------------------------------------------------------------------------------------------
OFF = {"spare_on_reserve_day": 41.2, "goal": 60, "delta": -18.8, "on_track": False}
ON = {"spare_on_reserve_day": 70.0, "goal": 60, "delta": 10.0, "on_track": True}


def test_alert_when_the_reserve_is_off_track():
    out = budget.ban_alert(2, 12, OFF, "2026-10-31")
    assert len(out) == 1
    assert "41" in out[0] and "60" in out[0] and "19 short" in out[0] and "31 Oct" in out[0]
    assert budget.ban_alert(2, 12, ON) == []
    assert budget.ban_alert(2, 12, {**ON, "on_track": None}) == []


def test_alert_when_bans_run_over_the_forecast():
    assert budget.ban_alert(4, 2, ON) != [] and "4 accounts" in budget.ban_alert(4, 2, ON)[0]
    assert budget.ban_alert(3, 1, ON) == [], "under 4 bans is never an alert"
    assert budget.ban_alert(6, 4, ON) == [], "6 is exactly 1.5 x 4, not over"
    assert budget.ban_alert(7, 4, ON) != []
    assert budget.ban_alert(5, 0, ON) != [], "bans against a forecast of none"
    assert len(budget.ban_alert(20, 12, OFF)) == 2, "both at once: two sentences"


def test_alerts_are_deduplicated_for_six_hours():
    t0, gap = 1_000_000.0, 6 * 3600
    a1 = budget.ban_alert(2, 12, OFF)
    due, sent = budget.due_alerts(a1, {}, t0, gap)
    assert due == a1
    a2 = budget.ban_alert(2, 12, {**OFF, "spare_on_reserve_day": 40.7, "delta": -19.3})      # same alert, new numbers
    assert budget.alert_key(a1[0]) == budget.alert_key(a2[0])
    assert budget.due_alerts(a2, sent, t0 + 20 * 60, gap)[0] == []
    assert budget.due_alerts(a2, sent, t0 + gap - 1, gap)[0] == []
    due, sent = budget.due_alerts(a2, sent, t0 + gap, gap)
    assert due == a2 and list(sent.values()) == [t0 + gap]
    both = budget.ban_alert(20, 12, OFF)
    due, _ = budget.due_alerts(both, sent, t0 + gap + 60, gap)
    assert len(due) == 1 and "banned in the last 24 h" in due[0], "a different alert still goes out"


# ---- Sydney days ------------------------------------------------------------------------------------------------------
def test_sydney_day_rolls_at_midnight_sydney():
    """AEDT (UTC+11) from 4 Oct 2026 02:00: midnight Sydney is 13:00 UTC the day before = 9pm Perth."""
    assert budget.sydney_day(ts("2026-10-23T12:59:59+00:00")) == "2026-10-23"
    assert budget.sydney_day(ts("2026-10-23T13:00:00+00:00")) == "2026-10-24"
    assert budget.sydney_day(ts("2026-10-24T12:59:59+00:00")) == "2026-10-24"
    assert budget.sydney_day(ts("2026-10-24T13:00:00+00:00")) == "2026-10-25"
    assert budget.sydney_day(ts("2026-10-24T13:00:00+08:00")) == "2026-10-24", "5am Perth is the same Sydney day"
    assert budget.sydney_day(ts("2026-10-24T21:00:00+08:00")) == "2026-10-25", "9pm Perth is midnight Sydney"
    # the clocks went forward on 4 Oct: midnight was 14:00 UTC the day before that
    assert budget.sydney_day(ts("2026-10-03T13:59:59+00:00")) == "2026-10-03"
    assert budget.sydney_day(ts("2026-10-03T14:00:00+00:00")) == "2026-10-04"
    assert budget.sydney_day(ts("2026-11-02T12:59:59+00:00")) == "2026-11-02"


def test_day_left_fraction():
    assert budget.day_left_fraction(ts("2026-10-23T13:00:00+00:00")) == pytest.approx(1.0)
    assert budget.day_left_fraction(ts("2026-10-24T01:00:00+00:00")) == pytest.approx(0.5)       # noon Sydney
    assert budget.day_left_fraction(ts("2026-10-24T12:59:00+00:00")) == pytest.approx(1 / 1440)


# ---- the voice list ---------------------------------------------------------------------------------------------------
ROWS = [
    {"ts": "x", "act": "reply", "live": True, "username": "a", "post_id": 1},
    {"ts": "x", "act": "reply", "live": True, "username": "a", "post_id": 1},          # logged twice: one write
    {"ts": "x", "act": "post", "live": True, "username": "a", "post_id": 2},
    {"ts": "x", "act": "like", "live": True, "username": "a", "post_id": 3},           # not a text write
    {"ts": "x", "act": "repost", "live": True, "username": "a", "post_id": 4},         # not a text write
    {"ts": "x", "act": "reply", "live": False, "username": "a", "post_id": 5},         # dry run
    {"ts": "x", "act": "reply", "live": True, "username": "b", "post_id": 6},
    {"ts": "x", "act": "thread_answer", "live": True, "username": "b", "post_id": 7},
    {"ts": "x", "act": "reply", "live": True, "username": "c", "post_id": 8},
    {"ts": "x", "act": "reply", "live": True, "username": "ghost", "post_id": 9},      # portal-only banned voice
    {"ts": "x", "act": "reply", "live": True, "username": "a"},                        # no post id: did not happen
]
RECORDS = [
    {"username": "a", "role": "voice", "status": "active"},
    {"username": "b", "role": "voice", "status": "suspended"},                         # our 403 told us; portal lags
    {"username": "c", "status": "active"},                                              # role missing = voice
    {"username": "d", "role": "voice", "status": "active"},                            # alive, never wrote: left out
    {"username": "e", "role": "booster", "status": "active"},
    {"username": "f", "role": "voice", "status": "failed"},
    {"username": "g", "role": "voice", "status": "pending"},
]


def test_text_writes_count_distinct_live_text_posts():
    assert budget.text_writes_by_voice(ROWS) == {"a": 2, "b": 2, "c": 1, "ghost": 1}


def test_logscan_streams_the_same_counts():
    scan = watch.LogScan()
    for r in ROWS:
        scan.add(r)
    assert scan.text_writes() == budget.text_writes_by_voice(ROWS)


def test_build_voices_from_synthetic_data():
    w = budget.text_writes_by_voice(ROWS)
    out = budget.build_voices(w, RECORDS, portal_suspended=["a", "ghost"])
    assert out == [{"username": "a", "writes": 2, "banned": True},                    # portal says banned
                   {"username": "b", "writes": 2, "banned": True},                    # the record says banned
                   {"username": "c", "writes": 1, "banned": False},
                   {"username": "ghost", "writes": 1, "banned": True}]
    km = budget.km_writes_per_ban(out)
    assert km["n_banned"] == 3 and km["n_alive"] == 1 and km["median"] == 2


def test_build_voices_falls_back_to_the_records_without_a_portal_list():
    out = budget.build_voices({"b": 90, "c": 10}, RECORDS)
    assert {v["username"]: v["banned"] for v in out} == {"b": True, "c": False}
    assert budget.build_voices({}, []) == []


def test_bans_in_window_prefers_the_counts_rows():
    now = ts("2026-10-24T12:00:00+00:00")
    counts = [{"ts": "2026-10-23T10:00:00+00:00", "registered": 70, "banned": 20},
              {"ts": "2026-10-23T20:00:00+00:00", "registered": 72, "banned": 24},
              {"ts": "2026-10-24T08:00:00+00:00", "registered": 73, "banned": 27}]
    assert budget.bans_in_window(counts, [], now) == 7                                  # 27 now - 20 at 24 h ago
    # no counts row old enough: the names in the window (epochs)
    assert budget.bans_in_window(counts[1:], [now - 3600, now - 10 * 3600, now - 30 * 3600], now) == 2
    assert budget.bans_in_window([], [], now) == 0


def test_account_counts_portal_first_then_records():
    portal = {"accounts": {"registered": 73, "banned": 25, "max_total": 200, "max_active": 50}}
    assert budget.account_counts(portal, [], 200) == (48, 127)
    log_only = {"account_log": {"counts": [{"ts": "2026-10-23T10:00:00+00:00", "registered": 60, "banned": 20},
                                           {"ts": "2026-10-24T10:00:00+00:00", "registered": 73, "banned": 25}]}}
    assert budget.account_counts(log_only, [], 200) == (48, 127)
    assert budget.account_counts({}, RECORDS, 200) == (5, 194)                # 6 used (f failed); alive a c d e g
    assert budget.account_counts({}, [], 200) is None


# ---- the job ----------------------------------------------------------------------------------------------------------
NOW = ts("2026-10-24T01:00:00+00:00")       # noon Sydney on 24 Oct: half the day left


def portal_data(registered=73, banned=25, suspended=(), last_24h=12):
    return {"accounts": {"registered": registered, "banned": banned, "max_total": 200, "max_active": 50},
            "account_log": {"counts": [{"ts": "2026-10-23T01:00:00+00:00", "registered": registered,
                                        "banned": banned - last_24h},
                                       {"ts": "2026-10-24T00:00:00+00:00", "registered": registered, "banned": banned}],
                            "suspended": [{"ts": "2026-10-23T05:00:00+00:00", "username": u, "id": 1, "why": "x"}
                                          for u in suspended]}}


def records(n_banned=3, n_alive=2):
    return ([{"username": f"b{i}", "role": "voice", "status": "suspended"} for i in range(n_banned)]
            + [{"username": f"v{i}", "role": "voice", "status": "active"} for i in range(n_alive)])


def test_report_uses_half_of_todays_plan_and_the_default_rate_with_few_bans():
    writes = {"b0": 100, "b1": 150, "b2": 200, "v0": 50, "v1": 60}
    rep = watch.budget_report(NOW, writes, records(), portal_data())
    assert rep["writes_per_ban"] == config.WRITES_PER_BAN_DEFAULT, "3 bans are under BUDGET_KM_MIN_BANS"
    assert rep["km"]["n_banned"] == 3
    today = rep["days"][0]
    assert today["day"] == "2026-10-24" and today["planned_writes"] == pytest.approx(1200)
    assert rep["days"][1]["planned_writes"] == 2400, "the half-day cut is today's only"
    assert rep["days"][-1]["day"] == "2026-11-02" and len(rep["days"]) == 10
    assert rep["alive"] == 48 and rep["spare"] == 127
    assert rep["actual_bans_24h"] == 12 and rep["forecast_bans_24h"] == pytest.approx(2400 / 145)
    assert rep["status"]["on_track"] is False
    assert len(rep["alerts"]) == 1, "12 bans against 16.6 forecast: only the reserve alert"


def test_report_uses_the_measured_rate_with_enough_bans():
    recs = records(n_banned=12, n_alive=1)
    writes = {f"b{i}": 100 + 10 * i for i in range(12)}              # banned at 100..210: median 150 of 13 voices at risk
    rep = watch.budget_report(NOW, writes, recs, portal_data(suspended=[f"b{i}" for i in range(12)]))
    assert rep["km"]["n_banned"] == 12 and rep["km"]["median"] is not None
    assert rep["writes_per_ban"] == rep["km"]["median"] != config.WRITES_PER_BAN_DEFAULT


def test_report_with_a_lighter_plan_is_on_track_and_quiet(monkeypatch):
    monkeypatch.setattr(config, "BAN_PLAN", {"2026-10-24": 290, "2026-11-01": 290})
    rep = watch.budget_report(NOW, {}, records(), portal_data(last_24h=1))
    assert rep["status"]["on_track"] is True and rep["alerts"] == []


def test_report_bans_over_forecast(monkeypatch):
    monkeypatch.setattr(config, "BAN_PLAN", {"2026-10-24": 290})                  # 2 bans forecast a day
    rep = watch.budget_report(NOW, {}, records(), portal_data())                 # 12 banned in 24 h
    assert rep["status"]["on_track"] is True
    assert len(rep["alerts"]) == 1 and "12 accounts banned" in rep["alerts"][0]


def test_report_after_the_reserve_day_has_no_reserve_alert():
    rep = watch.budget_report(ts("2026-11-01T01:00:00+00:00"), {}, records(), portal_data())
    assert rep["status"]["on_track"] is None and rep["status"]["spare_on_reserve_day"] is None
    assert not any("reserve" in a for a in rep["alerts"])


def test_report_degrades_without_data():
    assert watch.budget_report(NOW, {}, [], {}) is None
    rep = watch.budget_report(NOW, {}, records(), {})                            # no portal file: the records
    assert rep["alive"] == 2 and rep["spare"] == 195


def test_run_sends_once_then_holds_back_and_dry_sends_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(watch, "BUDGET_FILE", tmp_path / "swan_budget.json")
    monkeypatch.setattr(watch, "PORTAL_FILE", tmp_path / "portal.json")
    (tmp_path / "portal.json").write_text(json.dumps(portal_data()))
    sent, logged = [], []
    kw = dict(alert=sent.append, record=logged.append)

    watch.budget_run(NOW, {}, records(), dry=True, **kw)
    assert sent == [] and not (tmp_path / "swan_budget.json").exists(), "dry: nothing sent, no state saved"
    assert len(logged) == 1, "(the script's record() prints in dry; it does not write the log)"
    watch.budget_run(NOW, {}, records(), **kw)
    assert len(sent) == 1 and "off track" in sent[0]
    watch.budget_run(NOW + 20 * 60, {}, records(), **kw)
    assert len(sent) == 1, "the same alert is held back for 6 h"
    watch.budget_run(NOW + 6 * 3600 + 1, {}, records(), **kw)
    assert len(sent) == 2
    state = json.loads((tmp_path / "swan_budget.json").read_text())
    assert state["last"]["status"]["on_track"] is False and "sent" in state
    assert "password" not in json.dumps(state)


def test_run_without_any_file_says_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(watch, "BUDGET_FILE", tmp_path / "none" / "swan_budget.json")
    monkeypatch.setattr(watch, "PORTAL_FILE", tmp_path / "none" / "portal.json")
    sent = []
    watch.budget_run(NOW, {}, [], alert=sent.append, record=lambda r: None)
    assert sent == []


def test_job_changes_nothing():
    """A forecast and an alert: the budget code does not import the pool, the bot or the stealth caps."""
    import ast
    import inspect
    imported = set()
    for node in ast.walk(ast.parse(inspect.getsource(budget))):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "." * node.level)
    assert imported <= {"datetime", "math", "random", "re", "zoneinfo"}, f"budget.py is pure; it imports {imported}"
    src = inspect.getsource(watch.budget_run) + inspect.getsource(watch.budget_report)
    assert "pool." not in src and "POOL_WRITERS" not in src and "POOL_LIVE" not in src, "the job never touches the pool"
