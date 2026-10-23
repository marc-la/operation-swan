"""todo/40 item 6: the second-voice delay arm (sv_delay) is fixed per voice and Sydney day, about 50/50, and the same after a
restart (no network)."""
import datetime as dt
import pathlib
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from swan_bot import config, experiment  # noqa: E402

ARMS = ["fast", "slow"]
SYD = ZoneInfo("Australia/Sydney")


def at(day, hour=12, minute=0, second=0):
    return dt.datetime(2026, 10, day, hour, minute, second, tzinfo=SYD).timestamp()


def arm(voice, t, arms=ARMS, **kw):
    return experiment.per_voice_day("sv_delay", arms, voice, t=t, **kw)


def test_same_voice_same_day_same_arm():
    for v in (f"voice{i}" for i in range(60)):
        day = {arm(v, at(24, h, m)) for h in (0, 3, 12, 23) for m in (0, 59)}
        assert len(day) == 1, v


def test_the_day_rolls_over_at_sydney_midnight():
    changed = 0
    for i in range(200):
        v = f"voice{i}"
        assert arm(v, at(24, 0, 0, 1)) == arm(v, at(24, 23, 59, 59))
        changed += arm(v, at(24, 23, 59, 59)) != arm(v, at(25, 0, 0, 1))
    assert 60 < changed < 140, "about half of the voices switch arm with the new day"


def test_a_restart_changes_nothing():
    t = at(24)
    before = {f"v{i}": arm(f"v{i}", t) for i in range(80)}
    experiment._TURN.clear()                                   # the process state alternate() keeps: a restart forgets it
    assert before == {f"v{i}": arm(f"v{i}", t) for i in range(80)}


def test_fifty_fifty_over_voice_days():
    days = range(14, 31)
    picks = [arm(f"voice{i}", at(d)) for i in range(150) for d in days]
    share = picks.count("fast") / len(picks)
    assert len(picks) == 2550 and 0.46 < share < 0.54, share
    for d in days:                                              # and no day is lopsided
        today = [arm(f"voice{i}", at(d)) for i in range(150)]
        assert 0.38 < today.count("fast") / len(today) < 0.62, d


def test_a_voice_gets_both_arms_over_the_days():
    for i in range(30):
        assert len({arm(f"voice{i}", at(d)) for d in range(14, 31)}) == 2


def test_the_arm_does_not_depend_on_the_dict_order_or_the_dimension_name_clash():
    t = at(24)
    for i in range(40):
        v = f"voice{i}"
        assert arm(v, t, ["fast", "slow"]) == arm(v, t, ["slow", "fast"])
        assert arm(v, t, ("fast", "slow")) == arm(v, t, {"slow": 1, "fast": 2})
    other = [experiment.per_voice_day("own_like", ARMS, f"voice{i}", t=t) for i in range(80)]
    assert other != [arm(f"voice{i}", t) for i in range(80)], "each dimension is split on its own"


def test_one_arm_left_is_that_arm_and_the_pin_wins(monkeypatch):
    assert {arm(f"voice{i}", at(24), ["slow"]) for i in range(30)} == {"slow"}      # a big pool: no fast arm (todo/38)
    monkeypatch.setattr(config, "PIN", {"sv_delay": "fast"})
    assert {arm(f"voice{i}", at(24)) for i in range(30)} == {"fast"}
    monkeypatch.setattr(config, "PIN", {"sv_delay": "not_an_arm"})
    assert {arm(f"voice{i}", at(24)) for i in range(60)} == {"fast", "slow"}


def test_meta_gets_the_arm_and_the_flag_is_wired():
    meta = {}
    assert arm("voice1", at(24), meta=meta) == meta["sv_delay"]
    assert config.SV_DELAY_PER_VOICE_DAY is True and "SV_DELAY_PER_VOICE_DAY" in config.STEALTH_ENV
    assert set(config.SECOND_VOICE_ARMS) == set(ARMS)
