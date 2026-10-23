"""todo/38 stealth scheduler: life profiles, the calibrator, the weighted pick and the rate controller (no network, no
real files, fake clocks). The invariant under test everywhere: stealth is bought with voices and never costs volume,
so the pool's capacity stays >= 1.15 x 2.9 writes a minute and no voice is ever faster than its 4-minute floor."""
import collections
import datetime as dt
import json
import pathlib
import random
import statistics
import sys
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from swan_bot import bot, config, content, stealth  # noqa: E402

SYD = ZoneInfo("Australia/Sydney")
T0 = dt.datetime(2026, 10, 23, tzinfo=SYD).timestamp()      # Sydney midnight
FLOOR = config.ACCOUNT_MIN_GAP_S


@pytest.fixture(autouse=True)
def scheduler_on(monkeypatch):
    monkeypatch.setattr(config, "POOL_SCHEDULER", True)
    monkeypatch.setattr(config, "LOCAL_TZ", "Australia/Sydney")
    stealth.reset()
    stealth._RNG.seed(7)
    yield
    stealth.reset()


def pool(n):
    return [dict(username=f"voice{i}_{i * 13 % 97}", persona=f"p{i}", status="active", last_write=0, role="voice")
            for i in range(n)]


def run(n, hours, seed=1, recs=None, step=2.0, hook=None):
    """A team of n voices and a writer paced at POOL_TARGET_RATE on a fake clock (the writer asks for a voice every
    60 / 2.9 s and waits when none is ready), the way bot.Accounts.eligible drives stealth. Returns (recs, writes, per,
    order, longest) where longest counts the picks that were the voice that had rested longest."""
    stealth.reset()
    stealth._RNG.seed(seed)
    recs = pool(n) if recs is None else recs
    t, end, next_write = T0, T0 + hours * 3600, T0
    writes, per, order, longest = [], collections.defaultdict(list), [], 0
    while t < end:
        stealth.refresh(recs, t)
        if t >= next_write:
            ready = [r for r in recs if r["last_write"] + FLOOR <= t and r.get("next_ok", 0) <= t
                     and not stealth.rest(r, t)]
            if not ready:
                stealth.note_empty(t)
            else:
                r = stealth.pick(ready, t)
                longest += r is min(ready, key=lambda x: x["last_write"])
                r["last_write"] = t
                stealth.on_write(r, t)
                writes.append(t)
                per[r["username"]].append(t)
                order.append(r["username"])
                next_write = max(next_write + 60 / config.POOL_TARGET_RATE, t)
                if hook:
                    hook(t, r)
        t += step
    return recs, writes, per, order, longest


def awake_gaps(per, cap=3 * 3600):
    """Each voice's gaps between consecutive writes, less the ones that span a sleep or an outage."""
    return {u: [b - a for a, b in zip(ts, ts[1:]) if b - a < cap] for u, ts in per.items()}


# ---- the calibrator -------------------------------------------------------------------------------------------------
NEED = 1.15 * 2.9


@pytest.mark.parametrize("target", [2.0, 2.5, 2.9, 3.0])
def test_capacity_invariant_for_every_pool_size(target):
    """N = 9..40: the level is lowered until the awake voices' capacity is >= 1.15 x target, whenever that is reachable
    at all (the 4-minute floor caps a pool of n at n / 4 a minute: under 14 voices at 2.9 it is not, and the level is 0)."""
    for n in range(9, 41):
        p = stealth.plan(n, target=target)
        floor_min = FLOOR / 60
        assert 0.0 <= p["level"] <= 1.0
        assert p["mean_gap_s"] >= FLOOR, "no voice is ever faster than its floor"
        if n * 1.0 / floor_min >= 1.15 * target:             # reachable at L = 0
            assert p["capacity"] >= 1.15 * target - 1e-9, (n, p)
            assert p["capacity_ratio"] >= 1.15 - 1e-9 and p["feasible"]
        else:
            assert p["level"] == 0.0 and not p["feasible"], (n, p)
            assert p["capacity"] == pytest.approx(n / floor_min)       # the physical limit, reported honestly
        if n <= config.STEALTH_N_LO:
            assert p["level"] == 0.0


def test_level_shape_and_the_numbers_for_16_24_31():
    assert [stealth.plan(n)["level"] for n in range(9, 14)] == [0.0] * 5, "no sleep windows up to 13 voices"
    levels = [stealth.plan(n)["level"] for n in range(14, 41)]
    assert levels == sorted(levels), "more voices never means less stealth"
    assert stealth.plan(28)["level"] == 1.0 and stealth.plan(40)["level"] == 1.0
    p16, p24, p31 = stealth.plan(16), stealth.plan(24), stealth.plan(31)
    assert p16["level"] == pytest.approx(0.2, abs=0.001) and p16["wanted"] == pytest.approx(0.2, abs=0.001)
    assert p24["level"] == pytest.approx(0.733, abs=0.001)
    assert p31["level"] == 1.0
    for p in (p16, p24, p31):
        assert p["capacity"] == pytest.approx(NEED) and p["capacity_ratio"] == pytest.approx(1.15)
    assert p16["mean_gap_s"] == pytest.approx(264.8, abs=0.5)
    assert p24["mean_gap_s"] == pytest.approx(305.2, abs=0.5)
    assert p31["mean_gap_s"] == pytest.approx(334.6, abs=0.5)
    # a pool that is too small to sleep in is held back from the level its size alone would ask for
    p14 = stealth.plan(14)
    assert p14["level"] < p14["wanted"] + 1e-9 and p14["feasible"]


def test_a_smaller_target_or_a_bigger_floor_never_raises_the_level_past_the_invariant():
    for n in range(9, 41):
        for floor in (180, 240, 300):
            p = stealth.plan(n, floor_s=floor)
            if n * 60.0 / floor >= NEED:
                assert p["capacity"] >= NEED - 1e-9


# ---- life profiles --------------------------------------------------------------------------------------------------
def test_life_is_stored_once_and_deterministic_across_restarts():
    first = pool(31)
    for r in first:
        stealth.ensure_life(r, [x for x in first if "life" in x], 31)
    saved = json.loads(json.dumps(first))                 # what the accounts file keeps
    again = json.loads(json.dumps(saved))
    for r, old in zip(again, saved):
        assert stealth.ensure_life(r) == old["life"], "a stored life is never redrawn"
    # a record that lost its life gets the same one back from its username alone
    lone_a, lone_b = pool(1)[0], pool(1)[0]
    assert stealth.ensure_life(lone_a) == stealth.ensure_life(lone_b)
    # and in a pool, drawn in the same order, the same lives come out again
    redo = pool(31)
    for r in redo:
        stealth.ensure_life(r, [x for x in redo if "life" in x], 31)
    assert [r["life"] for r in redo] == [r["life"] for r in first]


def test_no_two_voices_share_parameters_and_ranges_hold():
    recs = pool(40)
    stealth.refresh(recs, T0)
    lives = [r["life"] for r in recs]
    assert len({(x["sleep_start"], x["gap_mult"], x["vol_mult"]) for x in lives}) == 40
    assert len({x["seed"] for x in lives}) == 40
    for x in lives:
        assert set(stealth.LIFE_KEYS) <= set(x)
        assert 6.0 <= x["sleep_h"] <= 9.0 and 0 <= x["sleep_start"] < 24
        assert stealth.LIFE_GAP_CLIP[0] <= x["gap_mult"] <= stealth.LIFE_GAP_CLIP[1]
        assert stealth.LIFE_VOL_CLIP[0] <= x["vol_mult"] <= stealth.LIFE_VOL_CLIP[1]
        assert x["burst_max"] in (1, 2, 3, 4)
    mids = sorted(stealth._mid(x) for x in lives)
    spread = [(b - a) for a, b in zip(mids, mids[1:] + [mids[0] + 24])]
    assert max(spread) < 5.0, "the sleep windows are spread across the day, not clumped"
    assert len({x["burst_max"] for x in lives}) >= 3 and len({x["sleep_h"] for x in lives}) >= 35
    assert len({tuple(x[k] for k in stealth.LIFE_KEYS) for x in lives}) == 40


def test_refresh_gives_a_life_once_and_says_so():
    recs = pool(16)
    assert stealth.refresh(recs, T0) is True
    assert stealth.refresh(recs, T0 + 10) is False
    old = [dict(r["life"]) for r in recs]
    stealth.refresh(recs, T0 + 20)
    assert [r["life"] for r in recs] == old


def test_sleep_window_scales_with_the_level_and_is_off_at_zero():
    recs = pool(31)
    stealth.refresh(recs, T0)
    assert stealth._S["level"] == 1.0
    r = recs[0]
    life = r["life"]
    hours = [h / 4 for h in range(96)]
    asleep = [stealth.life_asleep(r, T0 + h * 3600, ignore_relief=True) for h in hours]
    assert sum(asleep) / 4 == pytest.approx(life["sleep_h"], abs=0.5)
    stealth._S["level"] = 0.5
    half = sum(stealth.life_asleep(r, T0 + h * 3600, ignore_relief=True) for h in hours) / 4
    assert half == pytest.approx(life["sleep_h"] / 2, abs=0.5)
    stealth._S["level"] = 0.0
    assert not any(stealth.life_asleep(r, T0 + h * 3600) for h in hours)
    assert stealth.life_wakes_in(r, T0) == 0.0


def test_relief_wakes_sleepers_when_the_awake_capacity_falls_under_the_need():
    """Sleep starts bunched together would leave too few awake: the soonest-waking sleepers are woken, so the hard
    invariant holds on the actual pool and not only in expectation."""
    recs = pool(31)
    stealth.refresh(recs, T0)
    for r in recs:                                       # everyone sleeps through the same 8 h
        r["life"].update(sleep_start=1.0, sleep_h=8.0)
    stealth.reset()
    t = T0 + 4 * 3600                                    # 04:00, in the middle of it
    stealth.refresh(recs, t)
    st = stealth.controller_status(t)
    assert st["relieved"] > 0 and st["awake"] == len(recs) - st["asleep"]
    cap = sum(60.0 / stealth._gap_at(r, 1.0) for r in recs if not stealth.life_asleep(r, t))
    assert cap >= NEED - 1e-9
    assert st["asleep"] > 0, "only as many as needed are woken"


def test_next_gap_is_never_under_the_floor_and_is_noisy_only_with_stealth_on():
    recs = pool(31)
    stealth.refresh(recs, T0)
    r = recs[3]
    gaps = [stealth.schedule_gap(r, T0) for _ in range(3000)]
    assert min(gaps) >= FLOOR
    assert statistics.mean(gaps) == pytest.approx(stealth.voice_gap_s(r), rel=0.15), "the mean gap is the voice's own"
    assert statistics.pstdev(gaps) / statistics.mean(gaps) > 0.1, "the part above the floor is small at N = 31; the pick adds the rest"
    stealth.reset()
    one = pool(13)
    stealth.refresh(one, T0)                              # N = 13: L = 0
    g0 = [stealth.schedule_gap(one[0], T0) for _ in range(100)]
    assert min(g0) >= FLOOR and len(set(g0)) == 1, "L = 0: no jitter beyond the weighted pick"


# ---- the weighted pick ----------------------------------------------------------------------------------------------
def test_pick_is_weighted_random_not_a_rotation_over_20k_picks():
    recs = pool(30)
    stealth.refresh(recs, T0)
    t = T0 + 3600
    rng = random.Random(3)
    for r in recs:
        r["last_write"] = t - rng.uniform(300, 3000)
        r["next_ok"] = r["last_write"] + stealth.voice_gap_s(r)
    weights = {r["username"]: stealth.weight(r, t) for r in recs}
    total = sum(weights.values())
    picks = collections.Counter(stealth.pick(recs, t, random.Random(i)) ["username"] for i in range(20000))
    assert set(picks) == set(weights), "every voice is picked now and then"
    for user, w in weights.items():
        assert picks[user] / 20000 == pytest.approx(w / total, abs=0.012)
    longest = min(recs, key=lambda r: r["last_write"])["username"]
    assert picks[longest] / 20000 < 0.25, "not the longest-rest-first rule"
    assert stealth.pick([], t) is None


def test_no_fixed_rotation_and_the_gap_spread_at_full_level():
    recs, writes, per, order, longest = run(31, 24)
    assert stealth._S["level"] == 1.0
    rate = len(writes) / (24 * 60)
    assert rate == pytest.approx(2.9, rel=0.03)
    gaps = awake_gaps(per)
    cvs = [statistics.pstdev(g) / statistics.mean(g) for g in gaps.values() if len(g) > 8]
    assert len(cvs) >= 25
    assert statistics.mean(cvs) > 0.35, f"per-voice gap coefficient of variation {statistics.mean(cvs):.2f}"
    assert min(min(g) for g in gaps.values() if g) >= FLOOR
    pooled = [x for g in gaps.values() for x in g]
    assert statistics.pstdev(pooled) / statistics.mean(pooled) > 0.35
    assert longest / len(writes) < 0.5, "the longest-rested voice is not the usual one"
    # others written between a voice's own writes vary: no fixed rotation
    idx = collections.defaultdict(list)
    for i, u in enumerate(order):
        idx[u].append(i)
    between = [statistics.pstdev(b - a for a, b in zip(ix, ix[1:])) / statistics.mean(b - a for a, b in zip(ix, ix[1:]))
               for ix in idx.values() if len(ix) > 8]
    assert statistics.mean(between) > 0.35
    # a voice in the pool is asleep for part of the day (sleep windows are in use) and the volumes differ
    counts = [len(v) for v in per.values()]
    assert max(counts) > 1.3 * min(counts)


def test_level_zero_keeps_the_floor_and_never_sleeps(monkeypatch):
    monkeypatch.setattr(config, "STEALTH_N_LO", 99)       # force L = 0 for a pool of 16
    recs, writes, per, order, _ = run(16, 6)
    assert stealth._S["level"] == 0.0
    assert not any(stealth.life_asleep(r, T0 + h * 900) for r in recs for h in range(96))
    gaps = [g for gs in awake_gaps(per).values() for g in gs]
    assert min(gaps) >= FLOOR
    assert len(writes) / (6 * 60) == pytest.approx(2.9, rel=0.03)


def test_pool_of_13_still_reaches_what_the_floor_allows():
    recs, writes, per, order, _ = run(13, 6)
    gaps = [g for gs in awake_gaps(per).values() for g in gs]
    assert min(gaps) >= FLOOR
    assert len(writes) / (6 * 60) >= 0.85 * (13 / (FLOOR / 60))       # 3.25/min is the physical limit; most of it is used


# ---- the rate controller ----------------------------------------------------------------------------------------------
def test_controller_converges_to_the_target_on_a_simulated_team(monkeypatch):
    """The plan is made wrong on purpose (it assumes nobody sleeps) and relief is off, so 31 voices cannot keep 2.9/min at
    mult = 1; the controller has to shorten the gaps. Frozen at 1 the team falls far short."""
    monkeypatch.setattr(config, "STEALTH_SLEEP_PLAN_FRAC", 0.0)
    monkeypatch.setattr(stealth, "_relieve", lambda *a, **kw: None)
    hours = 8
    _, writes, _, _, _ = run(31, hours)
    late = [w for w in writes if w >= T0 + (hours - 4) * 3600]
    assert len(late) / 240 == pytest.approx(config.POOL_TARGET_RATE, rel=0.05), len(late) / 240
    st = stealth.controller_status(T0 + hours * 3600)
    lo, _ = config.POOL_MULT_RANGE
    assert lo <= st["mult"] < 1.0, "the controller shortened the gaps"
    assert st["observed_rate"] == pytest.approx(config.POOL_TARGET_RATE, rel=0.08)
    monkeypatch.setattr(config, "POOL_MULT_RANGE", (1.0, 1.0))
    _, frozen, _, _, _ = run(31, hours)
    assert len([w for w in frozen if w >= T0 + (hours - 4) * 3600]) / 240 < 0.9 * config.POOL_TARGET_RATE


def test_controller_stays_at_one_when_the_pool_keeps_up():
    _, writes, _, _, _ = run(31, 6)
    st = stealth.controller_status(T0 + 6 * 3600)
    assert 0.95 <= st["mult"] <= 1.0
    assert st["observed_rate"] == pytest.approx(2.9, rel=0.03)
    assert not st["over_ceiling"] and st["capacity_ratio"] == pytest.approx(1.15)
    json.dumps(st)                                        # status.json takes it as it is


def test_multiplier_is_bounded_by_the_range_and_by_capacity():
    recs = pool(31)
    stealth.refresh(recs, T0)
    assert stealth._S["mult_hi"] == pytest.approx(1.0), "the plan sits on the need: no room to slow the voices"
    stealth._S["mult"] = 1.6
    stealth.refresh(recs, T0 + 100)
    assert stealth._S["mult"] == pytest.approx(1.0)
    stealth.reset()
    stealth.refresh(recs, T0)
    stealth._S["mult"] = 0.1
    stealth.refresh(recs, T0 + 100)
    assert stealth._S["mult"] == config.POOL_MULT_RANGE[0]


def test_over_the_ceiling_is_flagged_and_the_multiplier_cannot_buy_stealth_with_volume():
    """A rate over POOL_RATE_CEILING (here 3/min, which the writer's own pacing prevents) is flagged in the status. The
    multiplier may not go over what the capacity invariant allows (1.0 when the plan sits on the need), so the pool is
    never slowed under 1.15 x target to chase it."""
    recs = pool(31)
    stealth.refresh(recs, T0)
    t = T0
    for i in range(1200):                                 # 3/min for 400 min of fake time
        t = T0 + i * 20
        stealth.note_write(t)
        if i % 3 == 0:
            stealth.refresh(recs, t)
    st = stealth.controller_status(t)
    assert st["over_ceiling"] and st["mult"] <= 1.0 + 1e-9 and st["mult_range"][1] == pytest.approx(1.0)


# ---- one voice per citizen, second voices ---------------------------------------------------------------------------
def test_one_voice_per_citizen_follows_the_pool_size_with_hysteresis(monkeypatch):
    monkeypatch.setattr(config, "ONE_VOICE_PER_CITIZEN", False)
    recs = pool(40)
    assert stealth.one_voice_on() is False
    stealth.refresh(recs[:23], T0)
    assert stealth.one_voice_on() is False
    stealth.refresh(recs[:24], T0 + 10)
    assert stealth.one_voice_on() is True
    stealth.refresh(recs[:22], T0 + 20)
    assert stealth.one_voice_on() is True, "no flapping at 22-23"
    stealth.refresh(recs[:21], T0 + 30)
    assert stealth.one_voice_on() is False
    stealth.refresh(recs[:30], T0 + 40)
    monkeypatch.setattr(config, "ONE_VOICE_AUTO", False)
    assert stealth.one_voice_on() is False, "the auto switch off: the config value alone"
    monkeypatch.setattr(config, "ONE_VOICE_PER_CITIZEN", True)
    assert stealth.one_voice_on() is True
    monkeypatch.setattr(config, "ONE_VOICE_AUTO", True)
    monkeypatch.setattr(config, "POOL_SCHEDULER", False)
    monkeypatch.setattr(config, "ONE_VOICE_PER_CITIZEN", False)
    assert stealth.one_voice_on() is False, "scheduler off: the config value alone"


def test_the_fast_second_voice_arm_only_in_a_small_pool():
    assert "fast" in stealth.second_voice_arms(), "before any refresh: the configured arms"
    stealth.refresh(pool(16), T0)
    assert set(stealth.second_voice_arms()) == {"fast", "slow"}
    stealth.refresh(pool(31), T0 + 10)
    assert set(stealth.second_voice_arms()) == {"slow"}
    assert set(config.SECOND_VOICE_ARMS) == {"fast", "slow"}, "the config itself is untouched"


# ---- the switch and Accounts --------------------------------------------------------------------------------------------
class Clock:
    """Stands in for the time module inside bot and stealth."""

    def __init__(self, t):
        self.now = t

    def time(self):
        return self.now

    def __getattr__(self, name):
        import time
        return getattr(time, name)


def accounts_at(monkeypatch, recs, t, live=True):
    clock = Clock(t)
    monkeypatch.setattr(bot, "time", clock)
    monkeypatch.setattr(stealth, "time", clock)
    acc = bot.Accounts(None, live)
    acc.records = recs
    return acc, clock


def voices(n):
    keys = [p["key"] for p in content.PERSONAS]
    return [dict(persona=keys[i % len(keys)], username=f"u{i}", status="active", last_write=0, writes=0, role="voice")
            for i in range(n)]


def test_scheduler_off_is_the_old_pick_exactly(monkeypatch):
    monkeypatch.setattr(config, "POOL_SCHEDULER", False)
    recs = voices(16)
    for i, r in enumerate(recs):
        r["last_write"] = T0 - 10_000 + i * 37
    acc, clock = accounts_at(monkeypatch, recs, T0)
    assert acc.eligible()["username"] == "u0" and acc.assignable()["username"] == "u0"
    recs[0]["last_write"] = T0 - 100
    assert acc.eligible()["username"] == "u1"
    assert "life" not in recs[1] and stealth._S["active"] is False
    stealth.on_write(recs[1], T0)
    assert "next_ok" not in recs[1], "no scheduler gap, and VOICE_JITTER is off"
    assert not stealth.gap_on()
    assert stealth.rest(recs[2], T0) is None and stealth.second_voice_arms() == config.SECOND_VOICE_ARMS
    assert config.stealth_from_env({"SWAN_POOL_SCHEDULER": "0"}) == {"POOL_SCHEDULER": False}


def test_env_switch(monkeypatch):
    assert "POOL_SCHEDULER" in config.STEALTH_ENV and "ONE_VOICE_AUTO" in config.STEALTH_ENV
    monkeypatch.setattr(config, "POOL_SCHEDULER", True)
    assert config.stealth_from_env({"SWAN_POOL_SCHEDULER": "off"}) == {"POOL_SCHEDULER": False}
    assert config.POOL_SCHEDULER is False
    assert config.stealth_from_env({"SWAN_POOL_SCHEDULER": "on"}) == {"POOL_SCHEDULER": True}
    with pytest.raises(SystemExit):
        config.stealth_from_env({"SWAN_POOL_SCHEDULER": "maybe"})


def test_dry_run_keeps_rotating_without_the_scheduler(monkeypatch):
    recs = voices(8)
    acc, _ = accounts_at(monkeypatch, recs, T0, live=False)
    recs[0]["last_write"] = T0 - 1
    assert acc.eligible()["username"] != "u0"
    assert stealth._S["active"] is False and "life" not in recs[1]


def test_accounts_pick_is_weighted_saves_the_lives_and_respects_the_floor(monkeypatch):
    recs = voices(24)
    acc, clock = accounts_at(monkeypatch, recs, T0)
    saved = []
    monkeypatch.setattr(acc, "save", lambda: saved.append(json.loads(json.dumps(acc.records))))
    seen, longest, last = [], 0, {}
    for step in range(900):
        clock.now = T0 + step * 20
        rec = acc.eligible()
        if rec is None:
            continue
        ready_longest = min((r for r in recs if r["last_write"] + FLOOR <= clock.now), key=lambda r: r["last_write"])
        longest += rec is ready_longest
        assert clock.now - last.get(rec["username"], -1e9) >= FLOOR
        last[rec["username"]] = clock.now
        rec["last_write"] = clock.now
        stealth.on_write(rec, clock.now)
        seen.append(rec["username"])
    assert len(saved) == 1 and all(valid for valid in (stealth.valid_life(r.get("life")) for r in saved[0])), \
        "the lives were stored once, in one save"
    assert len(seen) > 200 and len(set(seen)) >= 18, "5 h of fake time: a few voices sleep through it"
    assert longest / len(seen) < 0.6
    assert acc.n_writers() == 24
    # draft assignment (the voice may still be in its gap) also takes the weighted pick, from the same pool
    assert acc.assignable()["username"] in {r["username"] for r in recs}
    assert stealth._S["n"] == 24 and stealth.one_voice_on() is True        # 24 writers: auto one voice per citizen
