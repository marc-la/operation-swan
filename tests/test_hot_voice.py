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
    for name in ("ACCOUNT_MIN_GAP_S", "POOL_SCHEDULER", "POOL_LIVE", "SECOND_VOICE", "ONE_VOICE_PER_CITIZEN", "ONE_VOICE_AUTO",
                 "VOICE_DAY_CAP", "VOICE_HOUR_CAP", "VOICE_SLEEP", "VOICE_JITTER", "VOICE_STAGGER", "HOT_VOICES"):
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
