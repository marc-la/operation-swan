"""todo/38 pool orchestrator: the planning core (swan_bot/pool.py) and its executor (swan_bot/pool_runner.py).

Nothing here can reach a network: every socket connect raises, the platform is FakePlatform, the clock is a list, the rng is
seeded, files go to tmp_path, no LLM. Invariants pinned (design doc, "Safety invariants"):
  I1 caps (alive 49, total 200) never exceeded, even for adversarial snapshots
  I2 nothing irreversible when POOL_LIVE is off, the bot is a dry run, or a POOL_OFF file exists
  I3 write-ahead: the pending record (username, password, whole variant) is on disk before the API call; a crash anywhere is
     reconciled by login, never an orphan, never a second registration of the same username
  I4 one registrar: while live, Accounts.maybe_register and the booster top-up stand down, convert_boosters.py refuses
  I5 the runway tripwire alerts once   I7 every action row says by="pool", reason, owner
and the control law (healthy / sagging / low), the 403-total-cap and 429 handling, the no-free-card state, the lock discipline
(a slow register never blocks mu) and a 10-day simulation at the observed loss rate and a stress rate.
"""
import importlib.util
import json
import pathlib
import random
import re
import socket
import sys
import threading
import time

import pytest

import capturethenarrative as ctn

from swan_bot import bot, config, content, pool, pool_runner, variants

ROOT = pathlib.Path(__file__).resolve().parents[1]
T0 = 1792810800.0                    # 2026-10-24 03:00 UTC
CARDS = [p["key"] for p in content.PERSONAS]
ALL_CARDS = sorted(variants.default_cards())       # live + staged: 32 cards, for the simulations (never used by the bot)
P = pool.Params()
ROW_KEYS = {"dry_run", "state", "writers_target", "writers", "ramping", "warming", "alive", "alive_cap", "total_used",
            "total_cap", "spare_total", "loss_per_day", "runway_days", "days_left", "next_add_in_min", "last_actions"}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **kw):
        raise OSError("tests/test_pool.py: no network in tests")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


# ---- fakes -------------------------------------------------------------------------------------------------------------
class Crash(BaseException):
    """The process dies here (not an Exception: nothing in the runner may swallow it)."""


class FakeAcc:
    def __init__(self, username, account_id):
        self.username, self.account_id, self.token = username, account_id, f"tok-{username}"


class FakePlatform:
    """register/login over a dict of accounts with the real caps. `swarm` accounts count against both caps. Scripted
    failures: fail_register = an exception (or list of them, popped one per call) raised INSTEAD of creating the account;
    crash_after = raise Crash once the account exists (before the caller can save); slow = seconds register sleeps."""

    def __init__(self, swarm=11, alive_cap=49, total_cap=200, existing=0):
        self.accounts, self.swarm, self.alive_cap, self.total_cap = {}, swarm, alive_cap, total_cap
        self.registered, self.refused, self.display_names, self.codes = [], 0, {}, set()
        self.fail_register, self.crash_after, self.slow, self.next_id = None, False, 0.0, 5000
        self.registers_called = 0
        self.logins = []
        self.lock = threading.Lock()

    def alive(self):
        return self.swarm + sum(1 for a in self.accounts.values() if a["alive"])

    def register(self, username, password, code, display_name=None):
        self.registers_called += 1
        self.codes.add(code)
        if self.slow:
            time.sleep(self.slow)
        if self.fail_register:
            err = self.fail_register.pop(0) if isinstance(self.fail_register, list) else self.fail_register
            if err is not None:
                raise err
        with self.lock:
            if username in self.accounts:
                self.refused += 1
                raise ctn.APIError("POST", "/auth/register", 409, json.dumps({"error": "username taken"}))
            if self.alive() + 1 > self.alive_cap or self.swarm + len(self.accounts) + 1 > self.total_cap:
                self.refused += 1
                raise ctn.APIError("POST", "/auth/register", 403, json.dumps({"error": "total cap reached"}))
            self.next_id += 1
            self.accounts[username] = dict(password=password, id=self.next_id, alive=True)
            self.display_names[username] = display_name
            self.registered.append(username)
        if self.crash_after:
            self.crash_after = False
            raise Crash()
        return FakeAcc(username, self.next_id)

    def login(self, username, password):
        self.logins.append(username)
        a = self.accounts.get(username)
        if a is None or a["password"] != password:
            raise ctn.APIError("POST", "/auth/login", 401, json.dumps({"error": "bad credentials"}))
        return FakeAcc(username, a["id"])


def api_error(status, msg, retry=None):
    body = json.dumps({"error": msg})
    return ctn.RateLimited("POST", "/auth/register", 429, body, retry) if status == 429 else \
        ctn.APIError("POST", "/auth/register", status, body)


def voice(i, card=None, **kw):
    return dict(dict(role="voice", persona=card or CARDS[i % len(CARDS)], username=f"v{i}", display_name=f"Voice {i}",
                     account_id=100 + i, token=f"tok-v{i}", password="pw", owner="tester",
                     created="2026-10-20T00:00:00+00:00", status="active", last_write=0, writes=0, followed=[]), **kw)


def booster(i, **kw):
    return dict(dict(role="booster", persona=None, username=f"b{i}", display_name=f"Boost {i}", account_id=300 + i,
                     token=f"tok-b{i}", password="pw", owner="tester", created="2026-10-20T00:00:00+00:00",
                     status="active", last_write=0, writes=0, followed=[], sleep_start=3.0), **kw)


def suspended(i, card=None, at=None):
    r = voice(50 + i, card=card or CARDS[i % len(CARDS)], status="suspended")
    r["username"] = f"s{i}"
    if at is not None:
        r["suspended_at"] = pool.iso(at)
    return r


class Rig:
    """A runner on a real bot.Accounts (saved to tmp_path), the fake platform, a list for a clock, list sinks for log/alert."""

    def __init__(self, tmp_path, records, platform=None, live=True, cards=None, swarm=11, params=None, seed=1, off=False,
                 acc_live=True):
        config.ACCOUNTS_FILE.write_text(json.dumps(records))
        self.platform = platform or FakePlatform(swarm=swarm)
        for r in records:
            if r.get("status", "active") not in ("failed", "pending"):
                self.platform.accounts.setdefault(r["username"], dict(password=r.get("password"), id=r.get("account_id") or 1,
                                                                      alive=r.get("status", "active") == "active"))
        self.acc = bot.Accounts(self.platform, acc_live)
        self.mu = threading.RLock()
        self.clock, self.rows, self.alerts = [T0], [], []
        self.flags = dict(live=live, off=off)
        self.runner = pool_runner.PoolRunner(
            self.acc, self.platform, self.mu, lambda r: self.rows.append({"ts": pool.iso(self.clock[0]), **r}),
            self.alerts.append, "secret-team-code", "tester", clock=lambda: self.clock[0], rng=random.Random(seed),
            cards=lambda: list(cards or CARDS), swarm=lambda: (swarm, swarm, set()), params=params or pool.Params(),
            live=lambda: self.flags["live"], off=lambda: self.flags["off"], say=lambda *a: None)
        self.runner._seeded = True

    def due(self, z=-2.0):
        """Make an add due now: the want arose long ago, the draw is the shortest."""
        self.runner.st.want_since, self.runner.st.z = self.clock[0] - 5 * 86400, z

    def tick(self, advance=0.0):
        self.clock[0] += advance
        return self.runner.tick()

    def on_disk(self):
        return json.loads(config.ACCOUNTS_FILE.read_text())

    def acts(self, *names):
        return [r for r in self.rows if r["act"] in names]


def rig(tmp_path, **kw):
    kw.setdefault("records", [voice(i) for i in range(14)] + [booster(i) for i in range(6)])
    return Rig(tmp_path, **kw)


# ---- the pure core: numbers ---------------------------------------------------------------------------------------------
def test_state_and_deficit():
    assert pool.state_of(31, 31, 0.7) == "healthy" and pool.state_of(35, 31, 0.7) == "healthy"
    assert pool.state_of(30, 31, 0.7) == "sagging" and pool.state_of(22, 31, 0.7) == "sagging"
    assert pool.state_of(21, 31, 0.7) == "low"             # 21 < 0.7 * 31 = 21.7
    assert pool.deficit_of(31, 31) == 0 and pool.deficit_of(0, 31) == 1 and abs(pool.deficit_of(21.7, 31) - 0.3) < 1e-9


def test_delays_shrink_monotonically_with_the_deficit_and_keep_the_floors():
    for z in (-2, -1, 0, 1, 2, 2.5):
        last = None
        for d in [i / 100 for i in range(0, 101)]:
            state = pool.state_of(31 * (1 - d), 31, 0.7)
            v = pool.delay_s(d, z, P, state)
            assert pool.floor_s(state, P) <= v <= P.delay_max_s, (d, z, v)
            assert last is None or v <= last + 1e-6, f"delay grew with the deficit at d={d}, z={z}"
            last = v
    assert pool.median_delay_s(0, P) == pytest.approx(5 * 3600)
    assert pool.median_delay_s(0.1, P) == pytest.approx(45 * 60)
    assert pool.median_delay_s(0.3, P) == pytest.approx(15 * 60)
    assert pool.median_delay_s(1.0, P) == pytest.approx(8 * 60)
    assert pool.floor_s("low", P) == 8 * 60 and pool.floor_s("sagging", P) == 15 * 60 == pool.floor_s("healthy", P)


def test_healthy_delays_are_heavy_tailed_around_five_hours():
    rng = random.Random(3)
    xs = sorted(pool.delay_s(0.0, pool.draw_z(rng), P, "healthy") for _ in range(4000))
    assert 0.8 * 5 * 3600 < xs[len(xs) // 2] < 1.25 * 5 * 3600
    assert xs[int(len(xs) * 0.95)] > 1.8 * xs[len(xs) // 2] and xs[int(len(xs) * 0.05)] < 0.6 * xs[len(xs) // 2]


def test_loss_rate_reads_the_steady_rate():
    now = 10 * 86400.0
    for per_day in (3, 13, 38):
        ts = [now - i * 86400.0 / per_day for i in range(int(per_day * 3))]
        assert pool.loss_rate_per_day(ts, now, P) == pytest.approx(per_day, rel=0.12)
    assert pool.loss_rate_per_day([], now, P) == 0
    assert pool.loss_rate_per_day([now - 80 * 3600], now, P) == 0, "older than the window"
    assert pool.runway_days(137, 13, P) == pytest.approx(137 / 13) and pool.runway_days(137, 0, P) == 137 / 0.5


def test_days_left_to_the_end_of_polling_day_sydney():
    end = pool.parse_ts(P.end_iso)
    assert end == pool.parse_ts("2026-11-02T13:00:00+00:00")           # midnight Sydney (UTC+11) after 2 Nov
    assert pool.days_left(end - 86400 * 2.5, P.end_iso) == pytest.approx(2.5) and pool.days_left(end + 5, P.end_iso) == 0


def test_snapshot_counts_and_cards():
    now = T0
    recs = ([voice(i) for i in range(10)] + [voice(10, ramp=dict(**{"from": now}, until=now + 1000, start=0.25))]
            + [booster(i) for i in range(5)] + [suspended(1, at=now - 3600), suspended(2, at=now - 100 * 3600)]
            + [dict(booster(9), pool_state="warming", warm_until=now - 5, variant=dict(base="vika")),
               dict(booster(8), pool_state="warming", warm_until=now + 9999, variant=dict(base="tess"), status="pending"),
               dict(booster(7), status="failed")])
    s = pool.snapshot(recs, now, P, cards=CARDS + ["vika", "tess"], swarm_alive=11, swarm_used=11, reporter="b0")
    assert (s["writers"], s["ramping"], s["voices"], s["warming"], s["supply"]) == (10, 1, 11, 2, 13)
    assert s["alive"] == 11 + 11 + 5 + 2 and s["total_used"] == 11 + len(recs) - 1 - 0 and s["spare_total"] == 200 - s["total_used"]
    assert [x["username"] for x in s["ready"]] == ["b9"] and s["convertible"] == ["b1", "b2", "b3", "b4"], "reporter b0 excluded"
    assert len(s["losses"]) == 1 and s["losses"][0]["username"] == "s1"
    assert "vika" not in s["free_cards"] and "tess" not in s["free_cards"], "reserved by a warming account"
    assert set(s["held_cards"]) == set(CARDS[:11]) and set(s["free_cards"]) == set(CARDS[11:])
    assert s["state"] == "low"


def test_a_suspended_holder_frees_its_card():
    recs = [voice(0), suspended(1, card=CARDS[1], at=T0 - 60)]
    s = pool.snapshot(recs, T0, P, cards=CARDS)
    assert CARDS[1] in s["free_cards"] and CARDS[0] not in s["free_cards"]
    assert CARDS[1] in s["fresh_loss_cards"]
    rng = random.Random(0)
    assert all(pool.choose_card(s, rng) != CARDS[1] for _ in range(50)), "a card suspended minutes ago is the last choice"


# ---- the pure core: the control law -------------------------------------------------------------------------------------
def snap_for(voices, warming=0, boosters=0, cards=ALL_CARDS, swarm=11, now=T0, st=None, **over):
    recs = [voice(i, card=cards[i % len(cards)]) for i in range(voices)]
    recs += [dict(booster(100 + i), pool_state="warming", warm_until=now + 3600 * (i + 1), variant=dict(base=f"x{i}"))
             for i in range(warming)]
    recs += [booster(i) for i in range(boosters)]
    s = pool.snapshot(recs, now, P, cards=cards, swarm_alive=swarm, swarm_used=swarm, st=st)
    s.update(over)
    return s


def test_healthy_adds_one_replacement_per_loss_at_long_delays():
    st = pool.PoolState(z=0.0)
    s = snap_for(31, warming=3, boosters=3, st=st, last_action_ts=T0 - 3 * 86400)
    assert s["state"] == "healthy" and not pool.add_wanted(dict(s, supply=35))
    assert pool.plan_step(dict(s, want_since=None), T0, random.Random(1), P) is None, "34 < 35 wants one, but not yet"
    s = dict(s, want_since=T0)
    assert pool.plan_step(s, T0 + 4 * 3600, random.Random(1), P) is None, "median is 5 h"
    a = pool.plan_step(s, T0 + 5 * 3600 + 5, random.Random(1), P)
    assert a and a["act"] == "register" and a["state"] == "healthy" and 6 <= a["warm_h"] <= 36 and a["card"]
    assert "replacement" in a["reason"]
    assert pool.plan_step(dict(s, supply=35), T0 + 99 * 3600, random.Random(1), P) is None, "pipeline full: nothing"
    assert not [x for x in (pool.plan_step(s, T0 + 6 * 3600, random.Random(i), P) for i in range(30)) if x["act"] != "register"], \
        "a healthy pool does not convert"


def test_sagging_delay_shrinks_with_the_deficit_and_never_under_the_floor():
    waits = []
    for v in (30, 28, 26, 24):
        s = snap_for(v, warming=0, boosters=0, st=pool.PoolState(z=0.0, want_since=T0), last_action_ts=T0 - 86400)
        assert s["state"] == "sagging"
        waits.append(pool.add_due_ts(s, P) - T0)
    assert waits == sorted(waits, reverse=True) and len(set(waits)) == 4 and waits[-1] >= 15 * 60
    s = snap_for(22, st=pool.PoolState(z=-2.0, want_since=T0), last_action_ts=T0)
    assert pool.add_due_ts(s, P) - T0 >= 15 * 60
    assert pool.plan_step(s, T0 + 14 * 60, random.Random(0), P) is None
    assert pool.plan_step(s, T0 + 15 * 60 + 1, random.Random(0), P)["act"] == "register"


def test_low_floor_is_eight_minutes_and_conversions_come_before_registrations():
    s = snap_for(14, boosters=6, st=pool.PoolState(z=-2.0, want_since=T0 - 9999), last_action_ts=T0)
    assert s["state"] == "low"
    assert pool.plan_step(s, T0 + 7 * 60, random.Random(0), P) is None
    a = pool.plan_step(s, T0 + 8 * 60 + 1, random.Random(0), P)
    assert a["act"] == "convert" and a["username"].startswith("b") and a["card"] in s["free_cards"] and a["state"] == "low"
    assert 6 <= a["ramp_h"] <= 12                      # a converted booster is aged: the short ramp (23 Oct), not the fresh-account one
    none = snap_for(14, boosters=0, st=pool.PoolState(z=-2.0, want_since=T0 - 9999), last_action_ts=T0)
    assert pool.plan_step(none, T0 + 9 * 60, random.Random(0), P)["act"] == "register", "no booster to convert"
    assert pool.plan_step(snap_for(14, boosters=6, st=pool.PoolState(z=-2.0, want_since=T0 - 9999), last_action_ts=T0,
                                   reporter=None), T0 + 9 * 60, random.Random(0), P)["act"] == "convert"


def test_blues_reporter_is_never_converted_or_activated():
    recs = [voice(i) for i in range(10)] + [booster(1), booster(2)]
    s = pool.snapshot(recs, T0, P, cards=CARDS, reporter="b1")
    assert s["convertible"] == ["b2"]
    warm = [dict(booster(5), pool_state="warming", warm_until=T0 - 1, variant=dict(base="vika"))]
    assert pool.snapshot(recs + warm, T0, P, cards=CARDS, reporter="b5")["ready"] == []


def test_a_warmed_account_is_activated_first_and_only_while_under_target():
    recs = [voice(i) for i in range(12)] + [dict(booster(5), pool_state="warming", warm_until=T0 - 5,
                                                variant=dict(base=CARDS[15]))]
    s = pool.snapshot(recs, T0, P, cards=CARDS, st=pool.PoolState(z=2.0, want_since=T0))
    a = pool.plan_step(s, T0 + 3600, random.Random(0), P)
    assert a["act"] == "activate" and a["username"] == "b5" and a["card"] == CARDS[15] and 36 <= a["ramp_h"] <= 48
    full = pool.snapshot([voice(i, card=ALL_CARDS[i]) for i in range(31)] + [recs[-1]],
                         T0, P, cards=ALL_CARDS)
    p = pool.plan_step(full, T0 + 99999, random.Random(0), P)
    assert p is None or p["act"] != "activate", "31 writers: it stays warming"


def test_an_activation_whose_card_was_taken_gets_another_free_card():
    held = CARDS[15]
    recs = [voice(i, card=CARDS[i]) for i in range(12)] + [voice(20, card=held)] + \
        [dict(booster(5), pool_state="warming", warm_until=T0 - 5, variant=dict(base=held))]
    s = pool.snapshot(recs, T0, P, cards=CARDS)
    a = pool.plan_step(s, T0 + 3600, random.Random(0), P)
    assert a["act"] == "activate" and a["card"] != held and a["card"] in s["free_cards"]


def test_no_free_card_means_no_register_and_no_convert():
    cards = CARDS[:14]
    s = snap_for(14, boosters=6, cards=cards, st=pool.PoolState(z=-2.0, want_since=T0 - 9999), last_action_ts=T0 - 9999)
    assert s["free_cards"] == [] and pool.plan_step(s, T0, random.Random(0), P) is None
    assert pool.waiting_reason(s, P, T0) == "no_free_card"


def test_fuzz_a_thousand_adversarial_steps_never_break_a_cap_or_a_floor():
    rng = random.Random(42)
    last, last_state, n_act = 0.0, None, 0
    now = T0
    for step in range(1000):
        now += rng.choice((1, 30, 60, 240, 480, 481, 900, 901, 7200))
        n_v, n_w, n_b = rng.randint(0, 40), rng.randint(0, 8), rng.randint(0, 22)
        sw = rng.choice((0, 11, 20))
        recs = [voice(i, card=ALL_CARDS[i % 32]) for i in range(n_v)]
        recs += [dict(booster(100 + i), pool_state="warming", warm_until=now + rng.choice((-10, 100)),
                      variant=dict(base=ALL_CARDS[(n_v + i) % 32])) for i in range(n_w)]
        recs += [booster(i) for i in range(n_b)] + [suspended(i, at=now - rng.randint(0, 80) * 3600) for i in range(rng.randint(0, 9))]
        st = pool.PoolState(z=pool.draw_z(rng), want_since=rng.choice((None, now - 99999, now)), last_action_ts=last,
                            blocked_until=rng.choice((0, now + 60)), terminal=rng.choice((None, None, None, "x")))
        s = pool.snapshot(recs, now, P, cards=rng.choice((ALL_CARDS, ALL_CARDS[:n_v], CARDS)), swarm_alive=sw, swarm_used=sw, st=st)
        if rng.random() < 0.15:
            s.update(alive=rng.choice((48, 49, 50)), total_used=rng.choice((198, 199, 200, 201)))
        a = pool.plan_step(s, now, rng, P)
        if a is None:
            continue
        n_act += 1
        assert now - last >= pool.floor_s(s["state"], P), f"two actions {now - last:.0f} s apart in state {s['state']}"
        if a["act"] == "register":
            assert s["alive"] + 1 <= 49 and s["total_used"] + 1 <= 200 and not s["terminal"] and s["free_cards"], "I1"
            assert now >= s["blocked_until"] and a["card"] in s["free_cards"]
        elif a["act"] == "convert":
            assert s["state"] != "healthy" and a["card"] in s["free_cards"] and a["username"] in s["convertible"]
        else:
            assert a["card"] not in s["held_cards"] and s["voices"] < s["target"]
        last = now
    assert n_act > 40, "the fuzz must exercise actions"


# ---- records -------------------------------------------------------------------------------------------------------------
def test_adopt_identity_keeps_the_boosters_name_and_username():
    rec = booster(1, display_name="Mele Taufa")
    card = variants.card_for("vika")
    v = variants.make_variant("vika", [], random.Random(1))
    v = pool.adopt_identity(v, rec, card)
    assert v["name"] == "Mele Taufa" and v["first"] == "Mele" and v["last"] == "Taufa" and v["handle"] == rec["username"]
    assert v["swap"][card["name"]] == "Mele Taufa" and v["base"] == "vika"
    rec2 = booster(2, display_name="Sam")
    assert pool.adopt_identity(variants.make_variant("vika", [], random.Random(2)), rec2, card)["last"] == ""


def test_ramp_chance_rises_from_a_quarter_to_one(monkeypatch):
    acc = bot.Accounts(None, True)
    rec = dict(ramp=dict(**{"from": 1000.0}, until=1000.0 + 100 * 3600, start=0.25))
    for frac, want in ((0.0, 0.25), (0.5, 0.625), (1.0, 1.0)):
        t = 1000.0 + frac * 100 * 3600
        monkeypatch.setattr(bot.random, "random", lambda w=want: w - 1e-9)
        assert acc.ramp_ok(rec, t) is True
        monkeypatch.setattr(bot.random, "random", lambda w=want: w + 1e-9)
        assert acc.ramp_ok(rec, t) is (want >= 1.0), (frac, want)
    assert acc.ramp_ok({}, 5.0) and acc.ramp_ok(rec, rec["ramp"]["until"] + 1)


# ---- the executor: shadow, switches (I2) --------------------------------------------------------------------------------
def test_shadow_logs_what_it_would_do_and_changes_nothing(tmp_path):
    r = rig(tmp_path, live=False)
    before = config.ACCOUNTS_FILE.read_bytes()
    r.due()
    for _ in range(40):
        r.tick(advance=9 * 60)
    assert r.platform.registers_called == 0 and not r.platform.logins
    assert config.ACCOUNTS_FILE.read_bytes() == before, "nothing saved"
    assert [x["username"] for x in r.acc.records] == [x["username"] for x in json.loads(before)]
    assert all("dry run" in a for a in r.alerts), "an alert in shadow says so"
    shadow = r.acts("pool_shadow")
    assert len(shadow) >= 5
    assert {"convert", "register"} >= {x["would"] for x in shadow if x["would"] != "activate"}
    assert all(x["by"] == "pool" and x["owner"] == "tester" and x["reason"] and x["dry_run"] is True for x in shadow)
    assert not r.acts("pool_register", "pool_convert", "pool_activate")
    secrets_seen = json.dumps(r.rows)
    assert "secret-team-code" not in secrets_seen and "tok-" not in secrets_seen and '"pw"' not in secrets_seen
    st = r.runner.status()
    assert st["dry_run"] is True and set(st) == ROW_KEYS


def test_shadow_converts_first_then_registers_then_activates_in_its_private_copy(tmp_path):
    r = rig(tmp_path, live=False)
    kinds = []
    for _ in range(400):
        r.due(); r.runner.st.last_action_ts = min(r.runner.st.last_action_ts, r.clock[0] - 3600)
        p = r.tick(advance=20 * 60)
        if p:
            kinds.append(p["act"])
    assert kinds[:5] == ["convert"] * 5 and kinds[5] == "register", "5 boosters (Blue's reporter is the 6th): converted first"
    assert set(kinds) <= {"convert", "register", "activate"}
    assert "activate" in kinds, "the shadow's warmed accounts activate in its private copy"
    acted = [x["username"] for x in r.acts("pool_shadow") if x["would"] == "activate"]
    assert len(acted) == len(set(acted)), "each virtual account is activated once, not on every tick"
    assert len(acted) <= len([x for x in r.acts("pool_shadow") if x["would"] == "register"])
    assert r.acts("pool_error")[0]["why"] == "no_free_card", "and with 20 cards all held it says so, once"
    assert len([x for x in r.acts("pool_error") if x["why"] == "no_free_card"]) == 1
    assert r.platform.registers_called == 0


@pytest.mark.parametrize("how", ["pool_live_off", "bot_dry_run", "pool_off_file"])
def test_nothing_irreversible_unless_live(tmp_path, how):
    r = rig(tmp_path, live=(how != "pool_live_off"), acc_live=(how != "bot_dry_run"), off=(how == "pool_off_file"))
    before = config.ACCOUNTS_FILE.read_bytes()
    r.due()
    for _ in range(30):
        r.tick(advance=10 * 60)
    assert r.platform.registers_called == 0 and not r.platform.logins
    assert config.ACCOUNTS_FILE.read_bytes() == before
    assert not r.acts("pool_register", "pool_convert", "pool_activate")
    if how == "pool_off_file":
        assert not r.acts("pool_shadow"), "POOL_OFF: no plan at all"
        assert r.runner.status()["dry_run"] is True


def test_pool_off_file_stops_a_live_pool_between_ticks(tmp_path):
    r = rig(tmp_path, records=[voice(i) for i in range(14)])
    r.due()
    assert r.tick(advance=1) and r.acts("pool_register")
    n = len(r.platform.registered)
    r.flags["off"] = True
    r.due(); r.runner.st.last_action_ts = 0
    for _ in range(20):
        r.tick(advance=3600)
    assert len(r.platform.registered) == n


def test_default_config_ships_off():
    assert config.POOL_LIVE is False
    assert "POOL_LIVE" in config.STEALTH_ENV
    assert config.stealth_from_env({"SWAN_POOL_LIVE": "1"}) == {"POOL_LIVE": True}      # the go-live switch (conftest restores it)
    config.POOL_LIVE = False
    assert (config.POOL_WRITERS, config.POOL_PIPELINE, config.POOL_FLOOR_S, config.POOL_FLOOR_LOW_S) == (31, 4, 900, 480)


# ---- live: register, convert, activate -------------------------------------------------------------------------------------
def test_live_register_writes_ahead_then_the_result(tmp_path):
    r = rig(tmp_path, records=[voice(i) for i in range(14)] + [booster(i) for i in range(3)])
    seen = {}
    real = r.platform.register

    def spying(username, password, code, display_name=None):
        disk = {x["username"]: x for x in r.on_disk()}
        seen["rec"] = disk.get(username)
        seen["lock_free"] = r.mu.acquire(blocking=False) or False          # mu must not be held across the call
        if seen["lock_free"]:
            r.mu.release()
        return real(username, password, code, display_name)
    r.platform.register = spying
    r.runner.st.last_action_ts = 0
    r.due()
    # no booster is convertible while the reporter is b0 and others exist: force a register by removing convertibles
    for rec in r.acc.records:
        if rec["role"] == "booster":
            rec["pool_state"] = "warming"; rec["warm_until"] = T0 + 10 ** 7; rec["variant"] = dict(base="zz")
    r.acc.save()
    plan = r.tick(advance=1)
    assert plan and plan["act"] == "register"
    rec = seen["rec"]
    assert rec and rec["status"] == "pending" and rec["password"] and rec["pool_state"] == "warming"
    assert rec["variant"]["base"] == plan["card"] and rec["variant"]["name"] and rec["display_name"] == rec["variant"]["name"]
    assert seen["lock_free"], "mu was held across the network call"
    username = rec["username"]
    assert r.platform.display_names[username] == rec["variant"]["name"], "display_name=variant name"
    assert r.platform.codes == {"secret-team-code"}
    done = {x["username"]: x for x in r.on_disk()}[username]
    assert done["status"] == "active" and done["account_id"] and done["token"] and done["role"] == "booster"
    assert done["warm_until"] > T0 and done["owner"] == "tester" and done["pool"]["by"] == "pool"
    assert rec["variant"]["base"] in CARDS and rec["variant"]["base"] not in {x["persona"] for x in r.acc.voices()}, \
        "a card no active account holds"
    rows = [x for x in r.rows if x["act"] == "pool_register"]
    assert [x["phase"] for x in rows] == ["intent", "done"]
    assert all(x["by"] == "pool" and x["owner"] == "tester" and x["reason"] for x in rows)
    assert not any(k in json.dumps(r.rows) for k in ("password", "tok-" + username, "secret-team-code"))


def test_live_convert_a_booster_into_a_ramping_voice(tmp_path):
    r = rig(tmp_path)
    r.due()
    plan = r.tick(advance=1)
    assert plan["act"] == "convert"
    rec = next(x for x in r.acc.records if x["username"] == plan["username"])
    assert rec["role"] == "voice" and rec["persona"] == plan["card"] and rec["pool_state"] == "active"
    assert rec["variant"]["base"] == plan["card"] and rec["variant"]["name"] == rec["display_name"], "keeps the name it has"
    assert rec["ramp"]["until"] - rec["ramp"]["from"] >= 6 * 3600 and rec["ramp"]["start"] == 0.25    # the short conversion ramp
    assert rec["converted"]["by"] == "pool" and rec["converted"]["from_role"] == "booster" and rec["username"] == plan["username"]
    assert plan["username"] != "b0", "Blue's reporter (lowest id) is never converted"
    assert rec in r.acc.voices() and rec not in r.acc.boosters()
    assert bot.persona_of(rec)["name"] == rec["display_name"] and bot.persona_of(rec)["key"] == plan["card"]
    assert r.on_disk() and next(x for x in r.on_disk() if x["username"] == plan["username"])["role"] == "voice"
    row = r.acts("pool_convert")[0]
    assert row["by"] == "pool" and row["owner"] == "tester" and row["reason"] and row["username"] == plan["username"]
    assert r.platform.registers_called == 0, "a conversion spends no registration"


def test_live_activation_after_warm_up_and_stealth_refresh(tmp_path, monkeypatch):
    refreshed = []
    monkeypatch.setattr(pool_runner.stealth, "refresh", lambda recs, t=None: refreshed.append(len(recs)) or False)
    warm = dict(booster(7), pool_state="warming", warm_until=T0 - 60, variant=variants.make_variant(CARDS[17], [], random.Random(1)),
                display_name="Pat Lee")
    r = rig(tmp_path, records=[voice(i) for i in range(14)] + [booster(0), warm])
    r.runner.st.last_action_ts = 0
    plan = r.tick(advance=1)
    assert plan["act"] == "activate" and plan["username"] == "b7" and plan["card"] == CARDS[17]
    rec = next(x for x in r.acc.records if x["username"] == "b7")
    assert rec["role"] == "voice" and rec["persona"] == CARDS[17] and rec["ramp"] and "warm_until" not in rec
    assert refreshed and refreshed[-1] == 15, "stealth.refresh with the 15 voices after the change"
    assert r.acts("pool_activate")[0]["by"] == "pool"
    assert bot.persona_of(rec)["key"] == CARDS[17]


def test_a_ramping_voice_is_picked_less_often_at_first(tmp_path, monkeypatch):
    acc = bot.Accounts(None, True)
    acc.records = [voice(0, ramp=dict(**{"from": 0.0}, until=1e12, start=0.25)), voice(1)]
    monkeypatch.setattr(bot.time, "time", lambda: 1e6)
    picks = [acc.eligible()["username"] for _ in range(400)]
    assert 0.0 < picks.count("v0") / 400 < 0.45 and picks.count("v1") > 250, "v0 is ready only about a quarter of the time"


# ---- I3 write-ahead and reconcile --------------------------------------------------------------------------------------
def only_register(r):
    for rec in r.acc.records:
        if rec["role"] == "booster":
            rec["pool_state"] = "warming"; rec["warm_until"] = T0 + 10 ** 7; rec["variant"] = dict(base="zz")
    r.acc.save()


def test_crash_after_the_api_call_is_reconciled_by_login(tmp_path):
    r = rig(tmp_path, records=[voice(i) for i in range(14)])
    r.platform.crash_after = True
    r.due()
    with pytest.raises(Crash):
        r.tick(advance=1)
    assert len(r.platform.registered) == 1
    u = r.platform.registered[0]
    pend = next(x for x in r.on_disk() if x["username"] == u)
    assert pend["status"] == "pending" and pend["variant"]["name"] and pend["password"], "the intent survived the crash"
    # the restart: a new Accounts reads the file, a new runner reconciles
    r2 = Rig(tmp_path, r.on_disk(), platform=r.platform)
    r2.clock[0] = r.clock[0] + 5
    r2.tick()
    done = next(x for x in r2.on_disk() if x["username"] == u)
    assert done["status"] == "active" and done["account_id"] and done["token"]
    assert r.platform.registered == [u], "never registered twice"
    assert [x for x in r2.rows if x["act"] == "pool_register"][0].get("reconciled") is True


def test_crash_before_the_account_exists_marks_failed_but_only_after_two_minutes(tmp_path):
    r = rig(tmp_path, records=[voice(i) for i in range(14)])
    r.platform.fail_register = Crash()
    r.due()
    with pytest.raises(Crash):
        r.tick(advance=1)
    assert r.platform.registered == []
    r2 = Rig(tmp_path, r.on_disk(), platform=r.platform)
    r2.clock[0] = r.clock[0] + 30
    r2.tick()
    assert next(x for x in r2.on_disk() if x.get("status") in ("pending", "failed"))["status"] == "pending", "too young to judge"
    r2.clock[0] += 200
    r2.tick()
    failed = [x for x in r2.on_disk() if x.get("status") == "failed"]
    assert len(failed) == 1 and "password" not in failed[0] and failed[0]["failed_reason"].startswith("reconcile")
    s = pool.snapshot(r2.on_disk(), r2.clock[0], P, cards=CARDS)
    assert s["total_used"] == 14, "a failed intent is not a used account"


def test_a_transient_network_error_leaves_the_record_pending_and_does_not_register_again(tmp_path):
    r = rig(tmp_path, records=[voice(i) for i in range(14)])
    r.platform.fail_register = OSError("reset by peer")
    r.due()
    r.tick(advance=1)
    assert r.platform.registered == [] and len([x for x in r.on_disk() if x.get("status") == "pending"]) == 1
    for _ in range(5):
        r.tick(advance=70)
    assert r.platform.registers_called == 1 or len(r.on_disk()) <= 16
    assert len([x for x in r.on_disk() if x.get("status") == "pending"]) <= 1


def test_reconcile_finishes_an_account_that_was_created_late(tmp_path):
    r = rig(tmp_path, records=[voice(i) for i in range(14)])
    r.platform.fail_register = OSError("timeout")
    r.due()
    r.tick(advance=1)
    pend = next(x for x in r.on_disk() if x.get("status") == "pending")
    r.platform.accounts[pend["username"]] = dict(password=pend["password"], id=777, alive=True)     # the server did it after all
    r.tick(advance=130)
    done = next(x for x in r.on_disk() if x["username"] == pend["username"])
    assert done["status"] == "active" and done["account_id"] == 777


# ---- errors: 403 total, 403 active, 429, others -----------------------------------------------------------------------------
def test_403_total_cap_is_terminal_one_alert_no_retry_loop(tmp_path):
    r = rig(tmp_path, records=[voice(i) for i in range(14)])
    r.platform.fail_register = api_error(403, "total account cap reached (200)")
    r.due()
    for _ in range(60):
        r.tick(advance=3600)
        r.runner.st.want_since = r.clock[0] - 10 ** 6
    assert r.platform.registers_called == 1, "one failed call, then never again"
    assert r.runner.st.terminal and len([a for a in r.alerts if "TOTAL" in a]) == 1
    assert all(x.get("status") != "pending" for x in r.on_disk())
    assert r.runner.status()["next_add_in_min"] is None


def test_403_total_cap_still_lets_conversions_run(tmp_path):
    r = rig(tmp_path)
    r.runner.st.terminal = "403"
    r.due()
    assert r.tick(advance=1)["act"] == "convert"


def test_403_active_cap_waits_and_is_not_terminal(tmp_path):
    r = rig(tmp_path, records=[voice(i) for i in range(14)])
    r.platform.fail_register = api_error(403, "active account cap reached (50)")
    r.due()
    r.tick(advance=1)
    assert not r.runner.st.terminal and r.runner.st.blocked_until > r.clock[0]
    for _ in range(3):
        r.tick(advance=300)
    assert r.platform.registers_called == 1, "backed off, no hammering"


def test_429_waits_its_retry_after(tmp_path):
    r = rig(tmp_path, records=[voice(i) for i in range(14)])
    r.platform.fail_register = api_error(429, "slow down", retry=900)
    r.due()
    r.tick(advance=1)
    t_fail = r.clock[0]
    assert r.runner.st.blocked_until >= t_fail + 900
    while r.clock[0] < t_fail + 899:
        r.runner.st.want_since = t_fail - 10 ** 6
        r.tick(advance=60)
        assert r.platform.registers_called == 1, "no call before the Retry-After has passed"
    r.runner.st.want_since, r.runner.st.z = t_fail - 10 ** 6, -2
    r.runner.st.last_action_ts = 0
    r.tick(advance=200)
    assert r.platform.registers_called == 2


def test_repeated_refusals_back_off_and_alert_once(tmp_path):
    r = rig(tmp_path, records=[voice(i) for i in range(14)])
    r.platform.fail_register = lambda: None
    r.platform.fail_register = [api_error(400, "invalid username")] * 50
    calls = []
    for _ in range(40):
        r.runner.st.last_action_ts = 0
        r.runner.st.want_since, r.runner.st.z = r.clock[0] - 10 ** 6, -2
        r.tick(advance=1500)
        calls.append(r.platform.registers_called)
    assert len([a for a in r.alerts if "refused" in a]) == 1
    assert calls[-1] <= 40 and r.platform.registers_called < 40


def test_no_free_card_logs_once_alerts_once_and_waits(tmp_path):
    r = rig(tmp_path, records=[voice(i) for i in range(14)], cards=CARDS[:14])
    r.due()
    for _ in range(30):
        r.tick(advance=1800)
        r.runner.st.want_since = r.clock[0] - 10 ** 6
    assert r.platform.registers_called == 0
    errs = [x for x in r.rows if x["act"] == "pool_error" and x["why"] == "no_free_card"]
    assert len(errs) == 1 and len([a for a in r.alerts if "no free persona card" in a]) == 1
    st = r.runner.status()
    assert st["state"] == "low" and st["next_add_in_min"] is None
    r2 = Rig(tmp_path, [voice(i) for i in range(14)], cards=CARDS[:15])        # a card appears: the flag re-arms
    r2.due()
    assert r2.tick(advance=1)["act"] == "register"


def test_a_slot_freed_by_a_suspension_is_filled_by_a_variant_on_that_card(tmp_path):
    cards = CARDS[:15]
    recs = [voice(i) for i in range(14)] + [suspended(14, card=CARDS[14], at=T0 - 20 * 3600)]
    r = rig(tmp_path, records=recs, cards=cards)
    r.due()
    plan = r.tick(advance=1)
    assert plan["card"] == CARDS[14] and plan["act"] == "register"
    new = next(x for x in r.on_disk() if x["username"] == r.platform.registered[0])
    assert new["variant"]["base"] == CARDS[14]
    assert new["username"].lower() != "s14" and new["display_name"] != "Voice 64"


# ---- I1: the caps, immediately before the call --------------------------------------------------------------------------------
def test_alive_cap_is_checked_before_every_register(tmp_path):
    plat = FakePlatform(swarm=11)
    others = [booster(i, pool_state="other") for i in range(23)]          # plain boosters nothing converts: 14 + 23 + 11 = 48
    r = Rig(tmp_path, [voice(i) for i in range(14)] + others, platform=plat)
    assert pool.snapshot(r.acc.records, T0, P, cards=CARDS, swarm_alive=11)["alive"] == 48
    r.due()
    assert r.tick(advance=1)["act"] == "register"
    assert pool.snapshot(r.acc.records, T0, P, cards=CARDS, swarm_alive=11)["alive"] == 49
    for _ in range(20):
        r.due(); r.runner.st.last_action_ts = 0
        r.tick(advance=3600)
    assert plat.registers_called == 1 and plat.refused == 0, "the 50th is never attempted"
    # and a loss opens exactly one slot
    next(x for x in r.acc.records if x["username"] == "v3")["status"] = "suspended"
    plat.accounts["v3"]["alive"] = False
    for _ in range(5):
        r.due(); r.runner.st.last_action_ts = 0
        r.tick(advance=3600)
    assert plat.registers_called == 2 and plat.refused == 0


def test_total_cap_is_checked_before_every_register(tmp_path):
    recs = [voice(i) for i in range(14)]
    plat = FakePlatform(swarm=11)
    r = Rig(tmp_path, recs, platform=plat, swarm=186)           # 14 + 186 = 200 used
    r.due()
    for _ in range(10):
        r.tick(advance=3600)
        r.due()
    assert plat.registers_called == 0 and not [a for a in r.alerts if "RUNWAY" not in a]


# ---- I4: one registrar -------------------------------------------------------------------------------------------------------
def test_old_registrars_stand_down_while_live_and_run_as_before_when_off(tmp_path, monkeypatch):
    from swan_bot import amplify
    recs = [voice(i) for i in range(3)] + [booster(1)]
    for live_flag in (True, False):
        monkeypatch.setattr(config, "POOL_LIVE", live_flag)
        monkeypatch.setattr(config, "MAX_ACCOUNTS", 99)
        plat = FakePlatform(swarm=0)
        config.ACCOUNTS_FILE.write_text(json.dumps(recs))
        acc = bot.Accounts(plat, True)
        acc.next_register = 0.0
        acc.maybe_register(10, "code", "tester")
        amp = amplify.Amplifier(plat, acc, {}, True, lambda r: None, targeter=None, code="code", owner="tester", boosters=5)
        amp.next_register = 0.0
        amp.maybe_register_booster()
        assert (plat.registers_called == 0) is live_flag, f"POOL_LIVE={live_flag}: {plat.registers_called} registers"
    monkeypatch.setattr(config, "POOL_LIVE", True)
    dry = bot.Accounts(plat, False)                  # a dry-run bot registers fakes as before, whatever the flag
    dry.next_register = 0.0
    assert dry.live is False


def test_convert_boosters_script_refuses_while_the_pool_is_live(monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location("convert_boosters", ROOT / "scripts" / "convert_boosters.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(config, "load_env", lambda *a, **kw: None)
    monkeypatch.setattr(config, "POOL_LIVE", True)
    monkeypatch.setattr(sys, "argv", ["convert_boosters.py", "--apply", "--by", "marc"])
    with pytest.raises(SystemExit) as e:
        mod.main()
    assert "pool orchestrator is live" in str(e.value)
    assert not config.ACCOUNTS_FILE.exists()


def test_only_the_pool_and_the_old_registrars_call_register():
    """I4, statically: the callers of .register( in swan_bot are the two guarded old registrars, the swarm (its own file) and
    the pool runner; nothing else writes new accounts."""
    callers = {}
    for path in (ROOT / "src" / "swan_bot").glob("*.py"):
        n = len(re.findall(r"\.register\(", path.read_text()))
        if n:
            callers[path.name] = n
    assert set(callers) == {"bot.py", "amplify.py", "swarm.py", "pool_runner.py"}, callers
    bot_src = (ROOT / "src" / "swan_bot" / "bot.py").read_text()
    guard = "if self.live and (config.POOL_LIVE or config.HOT_VOICES):"      # hot mode: only the pool refills
    assert bot_src.count(guard) == 1 and guard in (ROOT / "src" / "swan_bot" / "amplify.py").read_text()
    writers = [p.name for p in (ROOT / "src" / "swan_bot").glob("*.py") if "config.ACCOUNTS_FILE" in p.read_text()
               and re.search(r"save_json\(config\.ACCOUNTS_FILE|ACCOUNTS_FILE\.write_text", p.read_text())]
    assert writers == ["bot.py"], writers


# ---- I5 runway ----------------------------------------------------------------------------------------------------------------
def test_runway_tripwire_alerts_once_and_rearms(tmp_path):
    lost = [suspended(i, at=T0 - i * 600) for i in range(30)]
    r = Rig(tmp_path, [voice(i) for i in range(14)] + lost, swarm=170, live=False)   # 14 + 30 + 170 = 214 used: spare 0
    n = lambda: len([a for a in r.alerts if "RUNWAY" in a])
    for _ in range(6):
        r.tick(advance=60)
    assert n() == 1 and len([x for x in r.rows if x["act"] == "pool_error" and x["why"] == "runway"]) == 1
    st = r.runner.status()
    assert st["runway_days"] < st["days_left"] and st["spare_total"] == 0
    r.runner.p = pool.Params(end_iso=pool.iso(r.clock[0] + 3 * 86400))
    for _ in range(4):
        r.tick(advance=60)
    assert n() == 1, "still under the days left: no second alert"
    r.runner.swarm = lambda: (11, 11, set())                    # spare appears (145): 145 / 22 per day = 6.6 d > 1.2 x 3 d
    r.tick(advance=60)
    assert n() == 1 and r.runner.status()["runway_days"] > 3.6
    r.runner.swarm = lambda: (11, 160, set())                   # it falls under again: the tripwire is armed again
    r.tick(advance=60)
    assert n() == 2


# ---- status schema ------------------------------------------------------------------------------------------------------------
def test_status_has_exactly_the_dashboard_schema(tmp_path):
    from swan_dash import build
    r = rig(tmp_path, live=False)
    r.due()
    r.tick(advance=1)
    st = r.runner.status()
    assert set(st) == ROW_KEYS and st["state"] in ("healthy", "sagging", "low")
    for k in ROW_KEYS - {"dry_run", "state", "last_actions", "next_add_in_min"}:
        assert isinstance(st[k], (int, float)) and not isinstance(st[k], bool), k
    assert st["next_add_in_min"] is None or isinstance(st["next_add_in_min"], (int, float))
    assert st["last_actions"] and set(st["last_actions"][0]) == {"ts", "act", "username"}
    json.dumps(st)
    view = build.pool_view(st, __import__("datetime").datetime.fromtimestamp(T0 + 5, __import__("datetime").timezone.utc))
    assert view and view["dry_run"] is True and "Pool" in view["head"]


# ---- lock discipline ----------------------------------------------------------------------------------------------------------
def test_a_slow_register_does_not_block_mu(tmp_path):
    r = rig(tmp_path, records=[voice(i) for i in range(14)])
    r.platform.slow = 0.8
    r.due()
    waits, stop = [], threading.Event()

    def other_thread():
        while not stop.is_set():
            t = time.perf_counter()
            with r.mu:
                waits.append(time.perf_counter() - t)
            time.sleep(0.005)
    th = threading.Thread(target=other_thread)
    th.start()
    t0 = time.perf_counter()
    r.tick(advance=1)
    took = time.perf_counter() - t0
    stop.set()
    th.join()
    assert took >= 0.8 and len(r.platform.registered) == 1
    assert len(waits) > 40, "the other thread kept getting mu while register slept"
    assert max(waits) < 0.1, f"mu waited {max(waits) * 1000:.0f} ms behind the pool worker"


def test_the_worker_step_fails_static(tmp_path):
    r = rig(tmp_path)
    boom = RuntimeError("bug")
    r.runner.tick = lambda now=None: (_ for _ in ()).throw(boom)
    for _ in range(4):
        r.runner.step()                                     # logged, ridden out
    assert len(r.acts("pool_error")) >= 1
    with pytest.raises(RuntimeError):
        r.runner.step()                                     # the 5th in a row ends the thread: the watchdog alerts once


# ---- the simulation -----------------------------------------------------------------------------------------------------------
def simulate(tmp_path, per_day, days=10, seed=7, tick_s=60):
    """31 voices, 4 spare boosters (one is Blue's), 11 swarm; random suspensions at `per_day` among the live voices; the
    fake platform enforces both caps. Returns the facts the assertions need."""
    rng = random.Random(seed)
    recs = [voice(i, card=ALL_CARDS[i]) for i in range(31)] + [booster(i) for i in range(3)]
    plat = FakePlatform(swarm=11)
    r = Rig(tmp_path, recs, platform=plat, cards=ALL_CARDS, seed=seed)
    # (the boosters' ids give b0 as Blue's reporter)
    r.runner.p = pool.Params()
    plans, low_since, longest_low, min_writers, n_low = [], None, 0.0, 99, 0
    spare_left_at, series = None, []
    steps = int(days * 86400 / tick_s)
    for step in range(steps):
        r.clock[0] += tick_s
        now = r.clock[0]
        with r.mu:
            live = [x for x in r.acc.records if x.get("status") == "active" and x["role"] == "voice"]
        # losses: every live voice has the same chance, so the rate per voice is per_day / 31 whatever the pool size
        n_loss = sum(1 for _ in range(len(live)) if rng.random() < per_day / 31.0 / 86400 * tick_s)
        for rec in rng.sample(live, min(n_loss, len(live))):
            with r.mu:
                rec["status"], rec["suspended_at"] = "suspended", pool.iso(now)
                plat.accounts[rec["username"]]["alive"] = False
        p = r.runner.tick()
        if p:
            plans.append((now, p["act"], p["state"]))
        st = r.runner.status()
        w = st["writers"] + st["ramping"]
        min_writers = min(min_writers, w)
        spare = st["spare_total"] > 2 * P.pipeline       # fewer spares than that cannot reach the writers in time
        if w < 0.7 * 31 and spare:
            n_low += 1
            low_since = low_since if low_since is not None else now
            longest_low = max(longest_low, now - low_since)
        else:
            low_since = None
        if step % 360 == 0:
            series.append((now - T0, w, st["warming"], st["state"]))
    return dict(rig=r, plat=plat, plans=plans, longest_low=longest_low, min_writers=min_writers, series=series,
                frac_low=n_low / steps)


# (loss rate per day, label, longest stretch under 70% of the target allowed while spares remain, share of the 10 days)
# observed 13/day: the pool never goes under 70%. Stress 38/day: 38 losses a day on a pool of 31 with a pipeline of 4 and a
# warm-up of hours cannot be held above 70% all the time (it hovers at 70-80% and dips on clusters of losses); the bound is
# what the simulation showed on four seeds (worst 15.7 h) with room, and the 137 spares run out on day 5 or 6 whatever it does.
@pytest.mark.parametrize("per_day, label, longest_h, share", [(13, "observed", 2, 0.01), (38, "stress", 20, 0.25)])
@pytest.mark.parametrize("seed", [7, 11])
def test_ten_day_simulation_holds_the_pool(tmp_path, per_day, label, longest_h, share, seed):
    s = simulate(tmp_path, per_day, seed=seed)
    r, plat = s["rig"], s["plat"]
    assert plat.refused == 0, "I1: the platform never had to refuse a register (caps)"
    assert plat.alive() <= 49 and plat.swarm + len(plat.accounts) <= 200
    # pacing: never closer than the state's floor, never a burst
    for (t1, a1, s1), (t2, a2, s2) in zip(s["plans"], s["plans"][1:]):
        assert t2 - t1 >= pool.floor_s(s2, P) - 1e-6, f"{a1}->{a2} {t2 - t1:.0f} s apart in state {s2}"
    regs = [x for x in r.rows if x["act"] == "pool_register" and x["phase"] == "intent"]
    assert len(regs) >= 5
    # the pool holds: writers (voices incl. ramping) stay >= 0.7 of target except for a few hours while spare remains
    assert s["longest_low"] <= longest_h * 3600, f"{label}: {s['longest_low'] / 3600:.1f} h under 70% (min writers {s['min_writers']})"
    assert s["frac_low"] <= share, f"{label}: {s['frac_low']:.1%} of the time under 70% while spares remained"
    if label == "stress":
        assert len([a for a in r.alerts if "RUNWAY" in a]) == 1, "the runway tripwire fired, once"
    # identities vary: handle shapes and none repeated
    shapes = [x["shape"] for x in regs]
    assert len(set(shapes)) >= 5 if len(shapes) >= 12 else len(set(shapes)) >= 3
    assert all(a != b for a, b in zip(shapes, shapes[1:])), "never the same handle shape twice in a row"
    names = [x["name"] for x in regs]
    assert len(set(names)) == len(names)
    users = [rec["username"] for rec in r.acc.records]
    assert len(users) == len(set(u.lower() for u in users)), "no duplicate username"
    # every action is attributed
    assert all(x["by"] == "pool" and x["owner"] == "tester" and x["reason"] for x in r.rows if x["act"].startswith("pool_")
               and x["act"] != "pool_error")
    # one card per active account
    held = [rec["persona"] for rec in r.acc.voices()]
    assert len(held) == len(set(held)), "two active voices on one card"
    print(f"\n{label}: {per_day}/day: {len(regs)} registrations, min writers {s['min_writers']}, longest <70%: "
          f"{s['longest_low'] / 3600:.1f} h, spare left {r.runner.status()['spare_total']}, "
          f"loss {r.runner.status()['loss_per_day']}/day, runway {r.runner.status()['runway_days']} d")


# ---- bot.main() end to end on the fake world (tests/test_bot_split.py's FakeWorld), pool worker included ----------------------
import test_bot_split as e2e  # noqa: E402


def pool_world(mp, tmp, live):
    """The split-loop world with the pool tuned to act within seconds: a target of 9 writers over the 6 seeded voices."""
    world, spies = e2e.setup_world(mp, tmp, True)
    for attr, val in (("POOL_LIVE", live), ("POOL_WRITERS", 9), ("POOL_PIPELINE", 2), ("POOL_FLOOR_S", 0.3),
                      ("POOL_FLOOR_LOW_S", 0.3), ("POOL_TICK_S", (0.05, 0.1)), ("POOL_DELAY_MAX_S", 0.5),
                      ("POOL_MEDIAN_PTS", ((0.0, 0.3), (1.0, 0.3))), ("POOL_WARM_H", dict(healthy=(0.0003, 0.0004),
                       sagging=(0.0003, 0.0004), low=(0.0003, 0.0004))), ("POOL_RAMP_H", dict(healthy=(0.01, 0.02),
                       sagging=(0.01, 0.02), low=(0.01, 0.02))), ("POOL_OFF_FILE", tmp / "POOL_OFF")):
        mp.setattr(config, attr, val)
    calls = []
    real = e2e.FakeSocial.register

    def spy(self, username, password, code, display_name=None):
        calls.append((username, threading.current_thread().name, display_name))
        return real(self, username, password, code, display_name)
    mp.setattr(e2e.FakeSocial, "register", spy)
    spies["registers"] = calls
    return world, spies


@pytest.mark.slow
def test_bot_main_live_pool_registers_warms_and_activates(tmp_path):
    with pytest.MonkeyPatch.context() as mp:
        e2e.block_network(mp)
        world, spies = pool_world(mp, tmp_path, live=True)
        e2e.run_main(mp, seconds=33)
    acts = e2e.actions(tmp_path)
    regs = spies["registers"]
    assert regs and all(thread == "pool" for _, thread, _ in regs), f"only the pool thread registers: {regs}"
    assert not [a for a in acts if a["act"] == "register"], "the old drip registrar stood down"
    assert [a for a in acts if a["act"] == "pool_register" and a.get("phase") == "done"]
    assert [a for a in acts if a["act"] == "pool_activate"], "a warmed account became a voice"
    recs = json.loads((tmp_path / "secrets" / "swan_accounts.json").read_text())
    assert not [r for r in recs if r.get("status") == "pending"], "no orphan intent left"
    new = [r for r in recs if r.get("pool")]
    assert new and all(r["owner"] == "tester" and r["pool"]["by"] == "pool" for r in new)
    assert {r["variant"]["name"] for r in new if r["username"] in {u for u, _, _ in regs}} >= {n for _, _, n in regs}
    voices = [r for r in recs if r.get("role") == "voice" and r.get("status") == "active"]
    assert len({r["persona"] for r in voices}) == len(voices), "one active voice per card"
    status = json.loads((tmp_path / "data" / "status.json").read_text())      # (written every 30 s: the 2nd write has the pool)
    assert "pool" in status["threads"] and set(status["pool"]) == ROW_KEYS and status["pool"]["dry_run"] is False
    assert all(a["by"] == "pool" and a["owner"] == "tester" and a["reason"] for a in acts if a["act"].startswith("pool_")
               and a["act"] != "pool_error")
    assert not [t for t in spies["alerts"] if "THREAD" in t], spies["alerts"]


@pytest.mark.slow
def test_bot_main_shadow_pool_registers_nothing(tmp_path):
    with pytest.MonkeyPatch.context() as mp:
        e2e.block_network(mp)
        world, spies = pool_world(mp, tmp_path, live=False)
        e2e.run_main(mp, seconds=8)
    acts = e2e.actions(tmp_path)
    assert spies["registers"] == [] or all(thread == "MainThread" for _, thread, _ in spies["registers"]), \
        "the pool thread registered nothing in shadow (the old drip may, as before)"
    assert [a for a in acts if a["act"] == "pool_shadow"], "shadow rows"
    assert not [a for a in acts if a["act"] in ("pool_register", "pool_convert", "pool_activate")]
    assert all(a["dry_run"] is True for a in acts if a["act"] == "pool_shadow")
    recs = json.loads((tmp_path / "secrets" / "swan_accounts.json").read_text())
    assert not [r for r in recs if r.get("pool") or r.get("pool_state")], "the shadow wrote nothing to the records"


def test_a_conversion_ramps_faster_than_an_activation_in_every_state():
    """23 Oct: a converted booster is an aged account, so POOL_CONVERT_RAMP_H (6-12 / 12-24 / 24-36 h by state) applies to
    conversions only; a fresh warmed account keeps POOL_RAMP_H. Every draw stays inside its band."""
    for state, lo, hi in (("low", 6, 12), ("sagging", 12, 24), ("healthy", 24, 36)):
        for seed in range(30):
            got = pool._hours(P.convert_ramp_h, state, random.Random(seed))
            assert lo <= got <= hi, (state, got)
    assert P.convert_ramp_h["low"][1] < P.ramp_h["low"][0], "the conversion band sits wholly under the activation band"


def test_alerts_already_sent_are_not_sent_again_after_a_restart(tmp_path):
    """Every deploy restarts the bot and the in-memory flags with it: sent_file keeps the runway line from going out again."""
    lost = [suspended(i, at=T0 - i * 600) for i in range(30)]
    records = [voice(i) for i in range(14)] + lost
    sent = tmp_path / "pool_alerts.json"
    n = lambda rig: len([a for a in rig.alerts if "RUNWAY" in a])
    first = Rig(tmp_path, records, swarm=170, live=False)
    first.runner.sent_file = sent
    first.tick(advance=60)
    assert n(first) == 1 and sent.exists()
    again = Rig(tmp_path, records, swarm=170, live=False)             # a fresh runner: the flags are empty again
    again.runner.sent_file = sent
    again.clock[0] = first.clock[0] + 600
    again.tick(advance=60)
    assert n(again) == 0, "the same line within the gap stays quiet"
    again.clock[0] += config.BUDGET_ALERT_GAP_S
    again.runner.st.flags.clear()
    again.tick(advance=60)
    assert n(again) == 1, "after the gap it may be said again"
