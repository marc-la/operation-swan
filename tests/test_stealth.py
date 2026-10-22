"""todo/31 stealth, the behaviour half: each voice keeps a human day (no network, no real files).

One test (or more) per rule: the daily and hourly budgets, the sleep window, jittered gaps and breaks, one voice per
citizen per day, staggered starts, the status.json numbers, the read-back of the last day on start; then bot.main()
end to end on test_bot_split's fake world with every rule on and the limits shrunk to seconds."""
import datetime as dt
import json
import pathlib
import sys
import time
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from swan_bot import bot, config, content, stealth, targeting, watch  # noqa: E402

KEYS = [p["key"] for p in content.PERSONAS]
SYD = ZoneInfo("Australia/Sydney")
RULES = ("VOICE_DAY_CAP", "VOICE_HOUR_CAP", "VOICE_SLEEP", "VOICE_JITTER", "VOICE_STAGGER", "ONE_VOICE_PER_CITIZEN")


def at(hour, day=22):
    """A Sydney time on 22 Oct 2026 (hour may be fractional, or past 24 for the next day)."""
    base = dt.datetime(2026, 10, day, tzinfo=SYD).timestamp()
    return base + hour * 3600


@pytest.fixture(autouse=True)
def rules_on(monkeypatch, tmp_path):
    """Every rule on with the shipped numbers, whatever config says; no real file is read."""
    for attr in RULES:
        monkeypatch.setattr(config, attr, True)
    monkeypatch.setattr(config, "LOCAL_TZ", "Australia/Sydney")
    monkeypatch.setattr(config, "ACTIONS_LOG", tmp_path / "actions.jsonl")
    monkeypatch.setattr(config, "LOGS", tmp_path)
    monkeypatch.setattr(watch, "WATCH_FILE", tmp_path / "watch.json")
    bot._REST_LOGGED.clear()


def voice(key, user=None, **kw):
    return {**dict(persona=key, username=user or f"u_{key}", status="active", last_write=0, writes=0, role="voice"),
            **kw}


def accounts(*recs, live=True):
    acc = bot.Accounts(None, live)
    acc.records = list(recs)
    return acc


def awake_time(key):
    """A Sydney time when this persona is surely awake (12 h after its window starts)."""
    start, _ = stealth.sleep_window(key)
    return at(start + 12)


# ---- the sleep window ------------------------------------------------------------------------------------------------
def test_sleep_window_is_fixed_per_persona_and_staggered():
    windows = {k: stealth.sleep_window(k) for k in KEYS}
    assert windows == {k: stealth.sleep_window(k) for k in KEYS}, "the same after a restart"
    assert all(7.0 <= length <= 8.0 for _, length in windows.values())
    starts = [s for s, _ in windows.values()]
    assert len(set(starts)) >= len(KEYS) - 1, "the voices don't all go to sleep at the same time"
    for k, (start, _) in windows.items():
        lo, hi = config.VOICE_SLEEP_STARTS[config.VOICE_SLEEP_KIND.get(k, "night")]
        assert (start - lo) % 24 <= hi - lo + 1e-6, (k, start)
    assert 8 <= windows["ana"][0] <= 10.5, "the night-shift nurse sleeps in the day"


def test_asleep_inside_its_window_only():
    key = "dan"
    start, length = stealth.sleep_window(key)
    assert stealth.asleep(key, at(start + 0.1))
    assert stealth.asleep(key, at(start + length - 0.1))
    assert not stealth.asleep(key, at(start + length + 0.1))
    assert not stealth.asleep(key, at(start - 0.5))
    assert stealth.wakes_in(key, at(start + 1)) == pytest.approx((length - 1) * 3600, abs=2)
    assert stealth.wakes_in(key, at(start + length + 1)) == 0


def test_sleep_switch(monkeypatch):
    start, _ = stealth.sleep_window("dan")
    monkeypatch.setattr(config, "VOICE_SLEEP", False)
    assert not stealth.asleep("dan", at(start + 1))


# ---- the daily and hourly budgets ------------------------------------------------------------------------------------
def test_daily_budget_with_a_reserve_for_citizens():
    t = awake_time("dan")
    rec = voice("dan", day_writes=[t - 3 * 3600 - i * 600 for i in range(config.VOICE_WRITES_PER_DAY - 1)])
    assert stealth.rest(rec, t, citizen=True) is None, "one more to a citizen"
    assert stealth.rest(rec, t, citizen=False) == "voice_capped", "the last writes of the day are for citizens"
    rec["day_writes"].append(t - 2 * 3600)
    assert stealth.rest(rec, t, citizen=True) == "voice_capped"
    assert stealth.rest(rec, t + 25 * 3600, citizen=True) is None, "a rolling 24 h"


def test_hourly_cap():
    t = awake_time("dan")
    rec = voice("dan", day_writes=[t - i * 300 for i in range(1, config.VOICE_WRITES_PER_H + 1)])
    assert stealth.rest(rec, t) == "voice_capped"
    assert stealth.rest(rec, t + 3600) is None
    assert 0 < stealth.free_in(rec, t) <= 3600


def test_budget_switches(monkeypatch):
    t = awake_time("dan")
    rec = voice("dan", day_writes=[t - i * 60 for i in range(1, 60)])
    monkeypatch.setattr(config, "VOICE_DAY_CAP", False)
    monkeypatch.setattr(config, "VOICE_HOUR_CAP", False)
    assert stealth.rest(rec, t) is None


def test_asleep_beats_the_budget():
    start, _ = stealth.sleep_window("dan")
    assert stealth.rest(voice("dan"), at(start + 1)) == "voice_asleep"


# ---- jittered gaps, breaks, staggered starts ---------------------------------------------------------------------------
def test_gaps_are_jittered_with_occasional_breaks(monkeypatch):
    gaps = [stealth.next_gap() for _ in range(2000)]
    median, _, lo, hi = config.VOICE_GAP
    plain = [g for g in gaps if g <= hi]
    breaks = [g for g in gaps if g > hi]
    assert len(set(round(g) for g in plain)) > 100, "no fixed cadence"
    assert all(lo <= g <= hi for g in plain)
    assert all(config.VOICE_BREAK_S[0] <= g <= config.VOICE_BREAK_S[1] for g in breaks)
    assert 0.03 < len(breaks) / len(gaps) < 0.15, "a break now and then"
    assert 0.6 * median < sorted(plain)[len(plain) // 2] < 1.4 * median


def test_on_write_keeps_a_day_and_sets_the_next_gap(monkeypatch):
    t = 1_000_000.0
    rec = voice("dan", day_writes=[t - 30 * 3600, t - 3600])
    stealth.on_write(rec, t)
    assert rec["day_writes"] == [t - 3600, t]
    assert config.VOICE_GAP[2] <= rec["next_ok"] - t <= config.VOICE_BREAK_S[1]
    monkeypatch.setattr(config, "VOICE_JITTER", False)
    rec.pop("next_ok")
    stealth.on_write(rec, t + 1)
    assert "next_ok" not in rec


def test_staggered_start():
    t = 1_000_000.0
    recs = [voice(k) for k in KEYS]
    stealth.stagger(recs, t)
    waits = [r["next_ok"] - t for r in recs]
    assert all(0 <= w <= config.VOICE_STAGGER_S for w in waits)
    assert len({round(w) for w in waits}) >= len(recs) - 1, "not on the same minute"
    late = voice("dan", next_ok=t + 99_999)
    stealth.stagger([late], t)
    assert late["next_ok"] == t + 99_999, "a longer wait (a break) is kept"


# ---- Accounts: who may write now ---------------------------------------------------------------------------------------
def test_eligible_skips_asleep_capped_and_in_gap_voices(monkeypatch):
    t = awake_time("dan")
    monkeypatch.setattr(time, "time", lambda: t)
    sleeper = next(k for k in KEYS if stealth.asleep(k, t))
    capped = voice("mere", day_writes=[t - i * 60 for i in range(1, 7)])
    in_gap = voice("ruth", next_ok=t + 600)
    acc = accounts(voice(sleeper), capped, in_gap, voice("dan"))
    assert acc.eligible()["persona"] == "dan"
    assert acc.ready(acc.records[3]) and not acc.ready(acc.records[0]) and not acc.ready(capped)
    assert acc.eligible(gap=config.REPOST_MIN_GAP_S, exclude={"dan"})["persona"] == "ruth", \
        "a repost keeps its own short gap"
    assert acc.status(acc.records[0]) == "voice_asleep" and acc.status(capped) == "voice_capped"
    assert acc.status(in_gap) == "gap" and acc.status(acc.records[3]) is None
    acc.records[3]["next_ok"] = t + 60
    assert acc.eligible() is None and acc.resting() is None, "a voice in its gap: not resting, just waiting"
    acc.records.remove(in_gap)
    acc.records[2]["day_writes"] = list(capped["day_writes"])
    assert acc.resting() == "voice_capped"


def test_dry_runs_rotate_freely(monkeypatch):
    t = awake_time("dan")
    monkeypatch.setattr(time, "time", lambda: t)
    sleeper = next(k for k in KEYS if stealth.asleep(k, t))
    acc = accounts(voice(sleeper, next_ok=t + 999, day_writes=[t - 1] * 50), live=False)
    assert acc.eligible()["persona"] == sleeper and acc.rest(acc.records[0]) is None


def test_voice_wait_includes_the_jittered_gap():
    t = time.time()
    rec = voice("dan", last_write=t - 3600, next_ok=t + 300)
    assert bot.voice_wait(dict(mode="reply", rec=rec), None, True, t) == pytest.approx(300)
    assert bot.voice_wait(dict(mode="reply_back", rec=rec), None, True, t) == 0, "a reply-back keeps its short gap"
    assert bot.voice_wait(dict(mode="repost", rec=rec), None, True, t) == 0


# ---- one voice per citizen per day ---------------------------------------------------------------------------------------
CIT, OTHER = 600, 601


def post(pid, author, parent=None, root=None):
    return dict(post_id=pid, author_id=author, reply_to_post_id=parent, root_post_id=root, body="b")


def test_one_voice_per_citizen_and_per_citizen_thread():
    state, t = {}, 1_000_000.0
    stealth.record(state, post(10, CIT), "dan", "reply", t)
    job = lambda persona, target, mode="reply": dict(mode=mode, rec=voice(persona), target=target)
    assert stealth.owner_problem(state, job("mere", post(11, CIT)), t + 60) == "voice_owner"
    assert stealth.owner_problem(state, job("dan", post(11, CIT)), t + 60) is None
    # another citizen under that citizen's post: the same voice
    under = post(12, OTHER, parent=10, root=10)
    assert stealth.owner_problem(state, job("mere", under), t + 60) == "voice_owner"
    assert stealth.owner_problem(state, job("dan", under), t + 60) is None
    # the citizen addressed another voice: its reply-back goes
    assert stealth.owner_problem(state, job("mere", post(13, CIT, 99, 99), "reply_back"), t + 60) is None
    # a day later anyone may
    assert stealth.owner_problem(state, job("mere", post(11, CIT)), t + config.ONE_VOICE_S + 1) is None
    # not a citizen (a journalist, another team): no rule
    assert stealth.owner_problem(state, job("mere", post(14, 3)), t + 60) is None


def test_a_reply_inside_a_news_thread_does_not_hold_the_thread():
    state, t = {}, 1_000_000.0
    stealth.record(state, post(20, CIT, parent=1, root=1), "dan", "reply", t)      # under a paper's article post
    assert stealth.owners(state, post(21, OTHER, parent=1, root=1), t) == set()


def test_rule_switch(monkeypatch):
    state, t = {}, 1_000_000.0
    stealth.record(state, post(10, CIT), "dan", "reply", t)
    monkeypatch.setattr(config, "ONE_VOICE_PER_CITIZEN", False)
    assert stealth.owner_problem(state, dict(mode="reply", rec=voice("mere"), target=post(11, CIT)), t) is None


def test_gone_at_send_holds_another_voice():
    state = dict(replied_posts=[], contacted={})
    stealth.record(state, post(10, CIT), "dan", "reply")
    assert bot.gone_at_send(dict(mode="reply", rec=voice("mere"), target=post(11, CIT)), state) == "voice_owner"
    assert bot.gone_at_send(dict(mode="reply", rec=voice("dan"), target=post(11, CIT)), state) is None


class Targeter:
    """next_target / requeue / skip like targeting.Targeter: a requeued candidate waits for its not_before."""

    def __init__(self, *cands):
        self.candidates = {c["post"]["post_id"]: c for c in cands}
        self.waits, self.skips = [], []

    def next_target(self, our_ids, replied, contacted, engaged=()):
        now = time.time()
        for pid, c in list(self.candidates.items()):
            if c.get("not_before", 0) <= now:
                return self.candidates.pop(pid)
        return None

    def requeue(self, cand, why):
        self.waits.append(why)
        self.candidates[cand["post"]["post_id"]] = cand

    def skip(self, post, why, source=None):
        self.skips.append(why)


def cand(pid, author):
    return dict(post=post(pid, author), frame="F14_no_yes_but", source="latest", identity=None, score=1.0)


def test_citizen_reply_goes_to_the_citizens_voice(monkeypatch):
    t = awake_time("dan")
    monkeypatch.setattr(time, "time", lambda: t)
    state = {}
    stealth.record(state, post(10, CIT), "dan", "reply", t - 3600)
    acc = accounts(voice("mere", last_write=0), voice("dan", last_write=t - 1800))
    job = bot.citizen_reply(Targeter(cand(11, CIT)), acc, set(), [], {}, state=state)
    assert job["rec"]["persona"] == "dan", "the voice that has them today, not the one that wrote longest ago"


def test_citizen_waits_for_its_voice_and_the_next_one_goes(monkeypatch):
    t = awake_time("mere")
    monkeypatch.setattr(time, "time", lambda: t)
    state = {}
    sleeper = next(k for k in KEYS if stealth.asleep(k, t) and k != "mere")
    stealth.record(state, post(10, CIT), sleeper, "reply", t - 3600)
    targeter = Targeter(cand(11, CIT), cand(12, OTHER))
    acc = accounts(voice("mere"), voice(sleeper))
    job = bot.citizen_reply(targeter, acc, set(), [], {}, state=state)
    assert job["target"]["post_id"] == 12 and job["rec"]["persona"] == "mere"
    assert targeter.waits == ["voice_asleep"]
    held = targeter.candidates[11]
    assert t + 60 <= held["not_before"] <= t + 1800, "backed off until its voice is free (at most 30 min)"
    assert targeting.VOICE_WAITS and "voice_asleep" in targeting.DELIBERATE_WAITS
    log = [json.loads(line) for line in config.ACTIONS_LOG.read_text().splitlines()]
    assert any(r["act"] == "skip" and r["why"] == "voice_asleep" for r in log)


def test_two_voices_already_means_no_third(monkeypatch):
    t = awake_time("mere")
    monkeypatch.setattr(time, "time", lambda: t)
    state = {}
    stealth.record(state, post(10, CIT), "dan", "reply", t - 3600)
    stealth.record(state, post(13, CIT, 99, 99), "ruth", "reply_back", t - 1800)     # they mentioned ruth
    targeter = Targeter(cand(11, CIT))
    assert bot.citizen_reply(targeter, accounts(voice("mere")), set(), [], {}, state=state) is None
    assert targeter.skips == ["voice_owner"]


def test_targeter_requeue_for_a_voice_wait_counts_no_try():
    t = targeting.Targeter.__new__(targeting.Targeter)
    import threading
    t.lock, t.group_out, t.candidates, t.items, t.log = threading.RLock(), {}, {}, {}, lambda r: None
    c = dict(post=dict(post_id=5, author_id=CIT, created_at=dt.datetime.now(dt.timezone.utc).isoformat()),
             not_before=123.0)
    t.requeue(c, "voice_capped")
    assert c.get("tries", 0) == 0 and c["not_before"] == 123.0
    assert t.items[5]["why"] == "voice_capped"


def test_rest_skips_are_logged_at_most_every_stealth_log_s(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    monkeypatch.setattr(bot, "now_iso", lambda: "2026-10-22T00:00:00+00:00")
    for _ in range(5):
        bot.log_rest("voice_capped")
    clock[0] += config.STEALTH_LOG_S + 1
    bot.log_rest("voice_capped")
    lines = [json.loads(line) for line in config.ACTIONS_LOG.read_text().splitlines()]
    assert [(r["why"], r["n"]) for r in lines] == [("voice_capped", 1), ("voice_capped", 5)]


# ---- the numbers and the read-back -----------------------------------------------------------------------------------------
def test_metrics_per_voice_and_team():
    t = at(15)
    a = voice("dan", day_writes=[t - 30 * 3600, at(1), at(9), at(9.5), t - 60])
    b = voice("mere", day_writes=[])
    state = {}
    stealth.record(state, post(10, CIT), "dan", "reply", t - 600)
    stealth.record(state, post(13, CIT, 99, 99), "mere", "reply_back", t - 300)
    stealth.record(state, post(14, OTHER), "dan", "reply", t - 300)
    m = stealth.metrics([a, b], {"u_dan": 1}, state, t, status=lambda r: "voice_capped" if r is a else None)
    d = m["voices"]["u_dan"]
    assert (d["writes_24h"], d["writes_today"], d["writes_1h"], d["hours_active_24h"], d["hidden"]) == (4, 4, 1, 3, 1)
    assert d["sleep"] == stealth.window_text("dan") and d["now"] == "voice_capped"
    assert m["voices"]["u_mere"]["now"] == "free"
    team = m["team"]
    assert (team["citizens_24h"], team["citizens_two_voices_24h"], team["two_voice_share"]) == (2, 1, 0.5)
    assert team["max_writes_24h"] == 4 and m["targets"]["two_voice_share"] == 0.0
    json.dumps(m)


def test_seed_reads_the_last_day_back_from_the_log(tmp_path):
    t = time.time()
    iso = lambda x: dt.datetime.fromtimestamp(x, dt.timezone.utc).isoformat()
    rows = [dict(ts=iso(t - 30 * 3600), act="reply", live=True, post_id=1, username="u_dan", persona="dan",
                 target_post=9, target_author=CIT),
            dict(ts=iso(t - 3600), act="reply", live=True, post_id=2, username="u_dan", persona="dan",
                 target_post=10, target_author=CIT, parent_post=None),
            dict(ts=iso(t - 1800), act="repost", live=True, post_id=3, username="u_dan", persona="dan"),
            dict(ts=iso(t - 900), act="reply", live=False, post_id=None, username="u_mere", persona="mere",
                 target_post=11, target_author=OTHER),
            dict(ts=iso(t - 600), act="skip", why="read", username="u_mere")]
    path = tmp_path / "log.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    a, b, kept = voice("dan"), voice("mere"), voice("ruth", day_writes=[t - 5])
    state = {}
    stealth.seed([a, b, kept], state, path, t)
    assert len(a["day_writes"]) == 2 and b["day_writes"] == [] and kept["day_writes"] == [t - 5]
    assert stealth.owners(state, post(11, CIT), t) == {"dan"}
    assert stealth.owners(state, post(12, OTHER, 10, 10), t) == {"dan"}, "their post's thread too"
    assert stealth.recent_writes(path, t, nbytes=len(json.dumps(rows[-1])) + 5) == [], "only the tail is read"


# ---- end to end: bot.main() on the fake world with every rule on ----------------------------------------------------------
@pytest.mark.parametrize("split", [True, False], ids=["split", "serial"])
def test_main_keeps_a_human_day(split, tmp_path, monkeypatch):
    import test_bot_split as e2e
    e2e.block_network(monkeypatch)
    world, spies = e2e.setup_world(monkeypatch, tmp_path, split)
    personas = [p["key"] for p in content.PERSONAS[:e2e.VOICES]]
    now_h = stealth.local_hour()
    for attr in RULES:
        monkeypatch.setattr(config, attr, True)
    monkeypatch.setattr(config, "VOICE_SLEEP_KIND", {personas[1]: "now"})
    monkeypatch.setattr(config, "VOICE_SLEEP_STARTS", {"night": (now_h + 3, now_h + 3), "now": (now_h - 1, now_h - 1)})
    monkeypatch.setattr(config, "VOICE_SLEEP_H", (7.0, 7.0))
    for attr, val in (("VOICE_WRITES_PER_DAY", 2), ("VOICE_CITIZEN_RESERVE", 1), ("VOICE_WRITES_PER_H", 6),
                      ("VOICE_GAP", (0.6, 0.3, 0.5, 1.0)), ("VOICE_BREAK_P", 0.0), ("VOICE_STAGGER_S", 1.0),
                      ("STEALTH_LOG_S", 0)):
        monkeypatch.setattr(config, attr, val)
    # u2 wrote twice in the last day before this start (read back from the log): nothing left today
    iso = lambda x: dt.datetime.fromtimestamp(x, dt.timezone.utc).isoformat()
    (tmp_path / "logs" / "actions.jsonl").write_text("".join(json.dumps(dict(
        ts=iso(time.time() - 3600 * h), act="post", live=True, post_id=h, username="u2", persona=personas[2])) + "\n"
        for h in (2, 3)))
    t0 = time.time()
    e2e.run_main(monkeypatch)
    assert time.time() - t0 < e2e.RUN_S + 15, "the writer waits when every voice is capped: it isn't stuck"

    acts = e2e.actions(tmp_path)[2:]                    # after the two read back
    writes = [a for a in acts if a.get("act") in stealth.WRITE_MODES and a.get("post_id")]
    assert writes, "it still writes"
    per = {}
    for a in writes:
        per[a["username"]] = per.get(a["username"], 0) + 1
    assert max(per.values()) <= 2, per
    assert "u2" not in per, "the read-back counts the last day's writes"
    assert "u1" not in per, "the voice in its sleep window doesn't write"
    assert "u5" not in per, "the parked voice doesn't write"
    assert not [a for a in writes if a["act"] == "second_voice"], "no second voice under one voice per citizen"
    voices_of = {}
    for a in writes:
        if a["act"] == "reply" and config.is_citizen(a.get("target_author")):
            voices_of.setdefault(a["target_author"], set()).add(a["persona"])
    assert all(len(v) == 1 for v in voices_of.values()), voices_of
    skips = {a["why"] for a in acts if a.get("act") == "skip"}
    assert "voice_capped" in skips, skips

    status = json.loads((tmp_path / "data" / "status.json").read_text())["stealth"]
    assert set(status["voices"]) >= {f"u{i}" for i in range(e2e.VOICES)}
    assert status["voices"]["u5"]["hidden"] == 2 and status["voices"]["u1"]["now"] == "voice_asleep"
    assert status["team"]["two_voice_share"] == 0.0 and status["rules"]["ONE_VOICE_PER_CITIZEN"] is True
