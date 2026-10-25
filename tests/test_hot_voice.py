"""Hot-account mode (24 Oct, Marc): config.HOT_VOICES names the voices in order of use and ONLY the first active one writes;
a suspended one hands over to the next spare at once. Off by default. No network."""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import capturethenarrative as ctn  # noqa: E402

from swan_bot import bot, config  # noqa: E402
from swan_bot.bot import Accounts  # noqa: E402
from test_bot_split import FakeWorld, actions, block_network, run_main, setup_world  # noqa: E402

NAMES = ("ana_d94", "tui4", "vika68")


def accounts(*names, extra=()):
    acc = Accounts(None, live=True)
    acc.records = [dict(username=n, account_id=100 + i, persona=p, role="voice", status="active", last_write=0, writes=0)
                   for i, (n, p) in enumerate(zip(names, ("kiri", "sione", "esther", "ana", "ben")))]
    acc.records += [dict(username=n, account_id=900 + i, persona="mere", role="booster", status="active") for i, n in enumerate(extra)]
    return acc


@pytest.fixture
def hot(monkeypatch):
    """Hot mode on for the roster NAMES, everything hot_mode_apply touches restored afterwards."""
    for name in ("ACCOUNT_MIN_GAP_S", "REPOST_MIN_GAP_S", "POOL_SCHEDULER", "POOL_LIVE", "SECOND_VOICE", "ONE_VOICE_PER_CITIZEN", "ONE_VOICE_AUTO",
                 "VOICE_DAY_CAP", "VOICE_HOUR_CAP", "VOICE_SLEEP", "VOICE_JITTER", "VOICE_STAGGER", "HOT_VOICES", "POOL_WRITERS",
                 "POOL_PIPELINE"):
        monkeypatch.setattr(config, name, getattr(config, name))
    return lambda names=NAMES: config.hot_from_env({"SWAN_HOT_VOICES": ",".join(names)})


def test_off_by_default_changes_nothing():
    assert config.HOT_VOICES == () and not config.hot_mode()
    acc = accounts("a1", "a2", "a3")
    assert [r["username"] for r in acc.voices()] == ["a1", "a2", "a3"]
    assert acc.hot() is None


def test_env_parses_a_roster_and_stands_the_spreading_rules_down(hot):
    assert hot((" ana_d94", "tui4 ", "tui4", "vika68")) == NAMES            # trimmed, in order, no duplicates
    assert config.hot_mode()
    assert config.ACCOUNT_MIN_GAP_S == config.HOT_GAP_S
    assert not any((config.POOL_SCHEDULER, config.POOL_LIVE, config.SECOND_VOICE, config.ONE_VOICE_PER_CITIZEN,
                    config.VOICE_DAY_CAP, config.VOICE_HOUR_CAP, config.VOICE_SLEEP, config.VOICE_JITTER, config.VOICE_STAGGER))


def test_env_refuses_a_bad_name(hot):
    with pytest.raises(SystemExit):
        hot(("ana_d94", "no spaces here"))


def test_unset_env_leaves_the_switch_off(monkeypatch):
    monkeypatch.setattr(config, "HOT_VOICES", ())
    assert config.hot_from_env({}) == () and not config.hot_mode()


def test_only_the_first_active_voice_writes_and_a_suspension_hands_over(hot):
    hot()
    acc = accounts("ana_d94", "tui4", "vika68", "other", extra=("b1",))
    assert [r["username"] for r in acc.voices()] == ["ana_d94"], "not the spares, not a voice outside the roster, no booster"
    assert acc.hot() == dict(active="ana_d94", spares=["tui4", "vika68"], lost=[], missing=[])
    acc.mark_suspended(acc.records[0])
    assert [r["username"] for r in acc.voices()] == ["tui4"], "the next spare is the voice on the very next call"
    acc.mark_suspended(acc.records[1])
    acc.mark_suspended(acc.records[2])
    assert acc.voices() == [] and acc.hot()["active"] is None and acc.hot()["lost"] == list(NAMES)


def test_a_name_with_no_record_is_reported_and_skipped(hot):
    hot(("ghost", "tui4"))
    acc = accounts("ana_d94", "tui4")
    assert [r["username"] for r in acc.voices()] == ["tui4"]
    assert acc.hot()["missing"] == ["ghost"]


def test_the_hot_voice_may_write_again_seconds_after_its_last_write(hot, monkeypatch):
    hot()
    monkeypatch.setattr(bot.time, "time", lambda: 1_000.0)
    acc = accounts(*NAMES)
    rec = acc.voices()[0]
    rec["last_write"] = 1_000.0 - 3
    assert acc.ready(rec, 1_000.0), "the 4-minute floor is gone: the write budget paces the bot"
    rec["last_write"] = 1_000.0 - 1
    assert not acc.ready(rec, 1_000.0)


def test_a_ramping_voice_writes_at_the_full_rate_in_hot_mode(hot, monkeypatch):
    acc = accounts(*NAMES)
    rec = acc.records[0]
    rec["ramp"] = {"from": 0, "until": 10_000, "start": 0.0}                      # a pool ramp: ready with probability 0 at t=0
    assert not acc.ramp_ok(rec, 1.0), "off: the ramp holds the voice back"
    hot()
    assert all(acc.ramp_ok(rec, 1.0) for _ in range(50)), "hot mode: the one voice is not rolled against its ramp"


def test_reply_backs_and_reposts_are_not_starved_by_the_one_voice_writing_every_20_s(hot):
    """24 Oct: the 60 s rule after a voice's last write starved all reply-backs in hot mode (19 queued, none sent in 5 h)."""
    assert bot.reply_back_gap() == bot.REPLY_BACK_GAP_S == 60 and config.REPOST_MIN_GAP_S == 60
    hot()
    assert bot.reply_back_gap() == config.HOT_GAP_S < 20 and config.REPOST_MIN_GAP_S == config.HOT_GAP_S
    rec = dict(last_write=1_000.0 - 20)                        # the hot voice wrote 20 s ago
    job = dict(mode="reply_back", rec=rec)
    assert bot.voice_wait(job, None, True, t=1_000.0) == 0.0, "the writer sends it at once"


# ---- end to end: the split loop on the fake world --------------------------------------------------------------------
@pytest.mark.slow
def test_one_voice_writes_everything_and_the_next_takes_over_when_it_is_suspended(tmp_path, monkeypatch):
    block_network(monkeypatch)
    world, spies = setup_world(monkeypatch, tmp_path, True)
    monkeypatch.setattr(config, "HOT_VOICES", ("u1", "u2", "u3"))
    monkeypatch.setattr(config, "HOT_GAP_S", 0.05)
    config.hot_mode_apply()
    sends = {"u1": 0, "u1_403": 0}
    real_write = FakeWorld.write

    def write(self, rec, kind, target=None, body=None):
        if rec["username"] == "u1" and kind in ("reply", "post", "repost"):
            sends["u1"] += 1
            if sends["u1"] > 5:                       # suspended after its fifth write
                sends["u1_403"] += 1
                raise ctn.APIError("POST", "/posts", 403, json.dumps({"error": "Your account is suspended"}))
        return real_write(self, rec, kind, target, body)

    monkeypatch.setattr(FakeWorld, "write", write)
    run_main(monkeypatch, seconds=26)             # the writer waits 10 s after a 403 (bot.handle)
    users = [w["username"] for w in world.writes if w["kind"] in ("reply", "post", "repost")]
    assert users, "it wrote"
    assert set(users) <= {"u1", "u2"}, f"only the hot voice and the first spare: {sorted(set(users))}"
    assert "u2" in users, "the spare took over"
    assert users.index("u2") > max(i for i, u in enumerate(users) if u == "u1"), "no write by u1 after the hand-over"
    assert sends["u1_403"] <= 2, "a suspended voice is tried once or twice, not once per queued draft"
    recs = {r["username"]: r for r in json.loads((tmp_path / "secrets" / "swan_accounts.json").read_text())}
    assert recs["u1"]["status"] == "suspended" and recs["u2"]["status"] == "active" and recs["u3"].get("writes", 0) == 0
    switches = [a for a in actions(tmp_path) if a.get("act") == "hot_switch"]
    assert [s["to"] for s in switches] == ["u1", "u2"] and switches[0]["first"] is True
    assert any(m.startswith("HOT: @u2 now writes (1 spare left") for m in spies["alerts"]), spies["alerts"]


# ---- the refill: the pool orchestrator keeps the reserve topped up (25 Oct, Marc) -----------------------------------------
def pooled(acc, name, at, act="activate"):
    rec = next(r for r in acc.records if r["username"] == name)
    rec["pool"] = dict(by="pool", act=act, at=at)
    return rec


def test_a_pool_voice_joins_the_end_of_the_roster_in_activation_order(hot):
    hot(("ana_d94", "tui4"))
    acc = accounts("ana_d94", "tui4", "late", "early", "plain")
    pooled(acc, "late", "2026-10-25T09:00:00+00:00")
    pooled(acc, "early", "2026-10-25T01:00:00+00:00", act="convert")
    assert acc.hot_roster() == ["ana_d94", "tui4", "early", "late"], "named first, then the pool's, oldest first; a plain voice is not in it"
    assert [r["username"] for r in acc.voices()] == ["ana_d94"]
    for r in acc.records[:2]:
        acc.mark_suspended(r)
    assert [r["username"] for r in acc.voices()] == ["early"], "the refill writes once the named ones are gone"
    h = acc.hot()
    assert h["active"] == "early" and h["spares"] == ["late"] and h["lost"] == ["ana_d94", "tui4"]
    acc.records[4]["status"] = "suspended"
    assert "plain" not in acc.hot()["lost"], "a voice that is not on the roster is never reported lost"
    pooled(acc, "plain", "2026-10-25T00:00:00+00:00")
    assert "plain" not in acc.hot()["lost"], "nor an old pool voice that never wrote hot"


def test_hot_mode_refill_has_its_own_switch_and_target(monkeypatch):
    for name in ("POOL_LIVE", "POOL_WRITERS", "POOL_PIPELINE", "HOT_POOL_LIVE", "HOT_POOL_WRITERS", "HOT_POOL_PIPELINE",
                 "ACCOUNT_MIN_GAP_S", "REPOST_MIN_GAP_S", "POOL_SCHEDULER", "SECOND_VOICE", "ONE_VOICE_PER_CITIZEN", "ONE_VOICE_AUTO",
                 "VOICE_DAY_CAP", "VOICE_HOUR_CAP", "VOICE_SLEEP", "VOICE_JITTER", "VOICE_STAGGER", "HOT_VOICES"):
        monkeypatch.setattr(config, name, getattr(config, name))
    monkeypatch.setattr(config, "POOL_LIVE", True)                        # the box's SWAN_POOL_LIVE=1, for the many-voice pool
    config.hot_from_env({"SWAN_HOT_VOICES": "a1,a2"})
    assert config.POOL_LIVE is False, "hot mode does not inherit SWAN_POOL_LIVE: registering needs SWAN_HOT_POOL_LIVE"
    assert (config.POOL_WRITERS, config.POOL_PIPELINE) == (config.HOT_POOL_WRITERS, config.HOT_POOL_PIPELINE) == (8, 3)
    monkeypatch.setattr(config, "HOT_POOL_LIVE", True)
    config.hot_mode_apply()
    assert config.POOL_LIVE is True
    assert config.stealth_from_env({"SWAN_HOT_POOL_LIVE": "0", "SWAN_HOT_POOL_WRITERS": "6"}) == dict(HOT_POOL_LIVE=False, HOT_POOL_WRITERS=6)


def test_the_old_registrars_stand_down_in_hot_mode(hot, monkeypatch):
    from swan_bot import amplify
    hot()
    acc = accounts(*NAMES)
    registered = []
    acc.social = type("S", (), {"register": lambda *a, **k: registered.append(a)})()
    acc.next_register = 0
    acc.maybe_register(16, "code", "owner")
    amp = amplify.Amplifier.__new__(amplify.Amplifier)
    amp.accounts, amp.live, amp.boosters_target, amp.next_register, amp.owner = acc, True, 22, 0, "owner"
    amp.maybe_register_booster()
    assert registered == [] and len(acc.records) == 3, "only the pool registers while hot mode runs"


def test_stop_rule_counts_hot_writers_and_alerts_only_on_a_short_average(hot):
    hot(("w1", "w2", "w3", "w4"))
    acc = accounts("w1", "w2", "w3", "w4")
    acc.live = False                                                      # accounts.save() is then a no-op
    texts = []
    for i, (name, writes) in enumerate((("w1", 100), ("w2", 200), ("w3", 120), ("w4", 600))):
        rec = acc.records[i]
        h = acc.hot()
        assert h["active"] == name
        bot.hot_track(acc, h)
        assert rec["hot_from"]["w0"] == 0 and "w" not in rec["hot_from"], "a running writer only gets its start recorded"
        rec["writes"] = writes
        acc.mark_suspended(rec)
        texts.append(bot.hot_track(acc, acc.hot()))
    assert [r["hot_from"]["w"] for r in acc.records] == [100, 200, 120, 600]
    assert texts[:2] == [None, None], "fewer than three finished writers: no rule yet"
    assert texts[2] and "100, 200, 120" in texts[2] and "mean 140" in texts[2] and "Nothing was changed" in texts[2]
    assert texts[3] is None, "the last three (200, 120, 600) average 307: back above the line, no alert"


def test_a_spare_suspended_before_its_turn_is_not_a_hot_writer(hot):
    """24 Oct night: two spares were suspended unused in the same sweep as the writer; the rule counted them as 0-write writers
    (alert: 'last 3 lasted 605, 0, 0')."""
    hot(("w1", "w2", "w3", "w4"))
    acc = accounts("w1", "w2", "w3", "w4")
    acc.live = False
    for rec, w in zip(acc.records, (605, 0, 0)):
        rec["hot_from"] = dict(at=f"2026-10-24T21:2{acc.records.index(rec)}:00", w0=0, w=w)
        rec["status"] = "suspended"
    assert bot.hot_track(acc, acc.hot()) is None, "one real writer (605) and two that never wrote: no rule, no alert"
    acc.records[3]["hot_from"] = dict(at="2026-10-25T01:00:00", w0=0, w=100)
    acc.records[3]["status"] = "suspended"
    acc.records.append(dict(username="w5", status="suspended", hot_from=dict(at="2026-10-25T02:00:00", w0=0, w=40)))
    assert "605, 100, 40" in bot.hot_track(acc, acc.hot())
