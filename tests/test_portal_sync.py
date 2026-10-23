"""todo/40 item 4: the portal's suspension list (data/portal.json, written by the dashboard poller) marks our accounts
suspended on a timer, on an exact username + id match, and a missing, stale or malformed file marks nothing (no network)."""
import datetime as dt
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from swan_bot import config, pool, watch  # noqa: E402
from swan_bot.bot import Accounts  # noqa: E402

NOW = 1_800_000_000.0


def iso(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat()


def portal_doc(read_at=NOW - 300, rows=None):
    """What swan_dash.portal.run writes, cut to the keys we read."""
    rows = [dict(ts=iso(NOW - 1800), username="ana_fifita_rn27", id=4603, why="3 posts hidden"),
            dict(ts=iso(NOW - 600), username="josh_k_sparky36", id=4567, why="reported as a bot")] if rows is None else rows
    return dict(ts=iso(read_at), error=None, rank=3, account_log=dict(counts=[], suspended=rows))


@pytest.fixture
def portal(tmp_path):
    path = config.PORTAL_FILE                       # conftest points it into tmp_path

    def write(doc):
        path.write_text(doc if isinstance(doc, str) else json.dumps(doc))
        return path
    return write


def accounts(*recs):
    acc = Accounts(None, live=True)
    acc.records = [{"status": "active", **r} for r in recs]
    return acc


def voices():
    return accounts(dict(username="ana_fifita_rn27", account_id=4603, persona="ana", role="voice"),
                    dict(username="josh_k_sparky36", account_id=4567, persona="josh", role="voice"),
                    dict(username="mere_t_nana21", account_id=4700, persona="mere", role="voice"))


# ---- the reader -------------------------------------------------------------------------------------------------
def test_reads_the_pollers_file(portal):
    portal(portal_doc())
    got = watch.portal_suspended(now=NOW)
    assert set(got) == {("ana_fifita_rn27", 4603), ("josh_k_sparky36", 4567)}
    assert got[("ana_fifita_rn27", 4603)]["why"] == "3 posts hidden"


def test_missing_file_is_nothing():
    assert not config.PORTAL_FILE.exists() and watch.portal_suspended(now=NOW) == {}


@pytest.mark.parametrize("text", ["", "{not json", "[]", "null", '{"ts": "2026-10-24T00:00:00+00:00"}',
                                  json.dumps(portal_doc(rows="oops")), json.dumps({"ts": "junk", "account_log": {"suspended": []}}),
                                  json.dumps({"account_log": {"suspended": [dict(ts=iso(NOW), username="a", id=1)]}}),
                                  json.dumps({"ts": iso(NOW), "account_log": None})])
def test_malformed_file_is_nothing(portal, text):
    portal(text)
    assert watch.portal_suspended(now=NOW) == {}


def test_stale_file_is_nothing(portal):
    portal(portal_doc(read_at=NOW - config.PORTAL_MAX_AGE_S - 60))
    assert watch.portal_suspended(now=NOW) == {}
    portal(portal_doc(read_at=NOW - config.PORTAL_MAX_AGE_S + 60))
    assert watch.portal_suspended(now=NOW) != {}
    assert watch.portal_suspended(now=NOW, max_age_s=10) == {}, "the age is a parameter"


def test_a_bad_entry_is_skipped_on_its_own(portal):
    rows = [dict(ts=iso(NOW), username="ok_one", id=11, why="x"), dict(ts=iso(NOW), username="", id=12),
            dict(ts=iso(NOW), username="bool_id", id=True), dict(ts=iso(NOW), username="str_id", id="13"),
            dict(ts="junk", username="bad_ts", id=14), dict(username="no_ts", id=15), "not a dict",
            dict(ts=iso(NOW), username="ok_two", id=16)]
    portal(portal_doc(rows=rows))
    assert set(watch.portal_suspended(now=NOW)) == {("ok_one", 11), ("ok_two", 16)}


# ---- marking ----------------------------------------------------------------------------------------------------
def test_marks_exactly_the_accounts_named(portal):
    portal(portal_doc())
    acc, logged = voices(), []
    assert acc.sync_portal(logged.append, NOW) == ["ana_fifita_rn27", "josh_k_sparky36"]
    by = {r["username"]: r for r in acc.records}
    assert by["ana_fifita_rn27"]["status"] == by["josh_k_sparky36"]["status"] == "suspended"
    assert by["mere_t_nana21"]["status"] == "active" and "suspended_at" not in by["mere_t_nana21"]
    assert [x["username"] for x in acc.voices()] == ["mere_t_nana21"], "the slot is free at once"
    assert pool.status_of(by["ana_fifita_rn27"]) == "suspended"
    assert pool.parse_ts(by["ana_fifita_rn27"]["suspended_at"]) == pytest.approx(NOW - 1800), "the portal's time, not ours"
    assert [(x["act"], x["username"], x["via"], x["why"]) for x in logged] == [
        ("suspended", "ana_fifita_rn27", "portal", "3 posts hidden"), ("suspended", "josh_k_sparky36", "portal", "reported as a bot")]
    assert json.loads(config.ACCOUNTS_FILE.read_text())[0]["status"] == "suspended", "saved"


@pytest.mark.parametrize("name, ident", [("ana_fifita_rn2", 4603), ("ana_fifita_rn277", 4603), ("Ana_Fifita_RN27", 4603),
                                         ("ana_fifita_rn27 ", 4603), ("ana_fifita_rn27", 4604), ("other_name", 4603),
                                         ("ana_fifita_rn27", None), ("ana_fifita_rn27", "4603"), ("ana_fifita_rn27", True)])
def test_no_match_unless_username_and_id_are_both_exact(portal, name, ident):
    portal(portal_doc())
    acc = accounts(dict(username=name, account_id=ident, persona="ana", role="voice"))
    logged = []
    assert acc.sync_portal(logged.append, NOW) == [] and not logged
    assert acc.records[0]["status"] == "active" and "suspended_at" not in acc.records[0]


def test_only_active_records_are_touched(portal):
    portal(portal_doc())
    acc = accounts(dict(username="ana_fifita_rn27", account_id=4603, persona="ana", status="pending"),
                   dict(username="josh_k_sparky36", account_id=4567, persona="josh", status="suspended",
                        suspended_at="2026-10-22T07:45:10+00:00"))
    logged = []
    assert acc.sync_portal(logged.append, NOW) == [] and not logged
    assert acc.records[0]["status"] == "pending"
    assert acc.records[1]["suspended_at"] == "2026-10-22T07:45:10+00:00", "the first time stands"


def test_boosters_are_marked_too(portal):
    portal(portal_doc())
    acc = accounts(dict(username="josh_k_sparky36", account_id=4567, role="booster", persona=None))
    assert acc.sync_portal(lambda r: None, NOW) == ["josh_k_sparky36"]


def test_stale_or_broken_file_marks_nothing(portal):
    acc = voices()
    portal(portal_doc(read_at=NOW - 2 * 3600))
    assert acc.sync_portal(lambda r: None, NOW) == []
    portal("{broken")
    assert acc.sync_portal(lambda r: None, NOW + 1000) == []
    assert all(r["status"] == "active" for r in acc.records)


def test_it_runs_on_a_timer_not_every_call(portal):
    acc, logged = voices(), []
    assert acc.sync_portal(logged.append, NOW) == [], "no file yet"
    portal(portal_doc())
    assert acc.sync_portal(logged.append, NOW + config.PORTAL_SYNC_S - 1) == [], "too soon: not read"
    assert acc.sync_portal(logged.append, NOW + config.PORTAL_SYNC_S + 1) == ["ana_fifita_rn27", "josh_k_sparky36"]
    assert acc.sync_portal(logged.append, NOW + 2 * config.PORTAL_SYNC_S + 2) == [], "once: they are suspended now"
    assert len(logged) == 2


def test_flag_off_and_dry_run_read_nothing(portal, monkeypatch):
    portal(portal_doc())
    monkeypatch.setattr(config, "PORTAL_SYNC", False)
    assert voices().sync_portal(lambda r: None, NOW) == []
    monkeypatch.setattr(config, "PORTAL_SYNC", True)
    dry = voices()
    dry.live = False
    assert dry.sync_portal(lambda r: None, NOW) == []
    assert {"PORTAL_SYNC", "PORTAL_SYNC_S", "PORTAL_MAX_AGE_S"} <= set(config.STEALTH_ENV)


def test_a_portal_time_in_the_future_is_clamped(portal):
    portal(portal_doc(rows=[dict(ts=iso(NOW + 7200), username="ana_fifita_rn27", id=4603, why="x")]))
    acc = voices()
    acc.sync_portal(lambda r: None, NOW)
    assert pool.parse_ts(acc.records[0]["suspended_at"]) == pytest.approx(NOW)


# ---- the 403 paths share the one marker --------------------------------------------------------------------------
def test_mark_suspended_keeps_the_first_time_and_saves():
    acc = voices()
    rec = acc.records[2]
    acc.mark_suspended(rec, at="2026-10-23T01:00:00+00:00")
    acc.mark_suspended(rec)                                  # a later 403 on the same voice
    assert rec["status"] == "suspended" and rec["suspended_at"] == "2026-10-23T01:00:00+00:00"
    assert json.loads(config.ACCOUNTS_FILE.read_text())[2]["status"] == "suspended"
