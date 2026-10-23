"""23 Oct, "no model" made visible and harmless (the 22 Oct 19:13Z incident: the LLM allowance ran down, Kimi was skipped
for the budget without being parked, the free models were out of quota, and 580,780 `lost no_model` rows followed).
Unit level, no network: LLMChain.no_model_wait / next_available_in, bot.defer / lose for every mode (the end-to-end
loop versions are in tests/test_bot_split.py), the amplifier's undo for a deferred thread job, and the dashboard's count
of episode rows."""
import datetime as dt
import json
import pathlib
import sys
import time
import types

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from swan_bot import amplify, bot, config, llm  # noqa: E402
from swan_dash import build  # noqa: E402

KIMI = "moonshotai.kimi-k2.5"


def today():
    return dt.datetime.now(llm.BUDGET_DAY).date().isoformat()


def make_gen(tmp_path, monkeypatch, spent=0.0, chain=None):
    """A Generator over a one-day $10 budget (reserve $2.50) with `spent` USD gone; Kimi (priced) then a free model."""
    monkeypatch.setattr(llm, "SPEND_FILE", tmp_path / "spend.json")
    monkeypatch.setattr(llm, "USAGE_FILE", tmp_path / "usage.json")
    monkeypatch.setattr(config, "LLM_BUDGET_DAYS", [(today(), today(), 1)])
    monkeypatch.setattr(config, "LLM_BUDGET_USD", 10.0)
    monkeypatch.setattr(config, "LLM_DAILY_FLOOR_USD", 0.0)
    monkeypatch.setattr(config, "LLM_AMP_RESERVE_SHARE", 0.25)
    (tmp_path / "spend.json").write_text(json.dumps({today(): spent}))
    gen = llm.Generator("unused")
    gen.chain = chain or [("bedrock", KIMI), ("groq", "free-a"), ("groq", "free-b")]
    return gen


def park_free(gen, seconds):
    for _, m in gen.chain:
        if m not in config.LLM_PRICES:
            gen.parked[m] = time.time() + seconds


# ---- LLMChain.no_model_wait / next_available_in -------------------------------------------------------------
def test_a_free_model_that_is_not_parked_means_zero(tmp_path, monkeypatch):
    gen = make_gen(tmp_path, monkeypatch, spent=10.0)               # allowance spent: Kimi is off, but a free model is free
    assert gen.no_model_wait() == 0.0 and gen.no_model_wait(priority=True) == 0.0 and gen.next_available_in() == 0.0


def test_priced_model_with_budget_means_zero_even_when_the_free_ones_are_parked(tmp_path, monkeypatch):
    gen = make_gen(tmp_path, monkeypatch, spent=1.0)
    park_free(gen, 3600)
    assert gen.no_model_wait() == 0.0 and gen.no_model_wait(priority=True) == 0.0 and gen.next_available_in() == 0.0


def test_reserve_only_is_unavailable_to_an_ordinary_call_not_to_a_priority_one(tmp_path, monkeypatch):
    """left $2.00 <= the $2.50 reserve: complete() skips Kimi (not parked) unless priority."""
    gen = make_gen(tmp_path, monkeypatch, spent=8.0)
    park_free(gen, 6 * 3600)
    assert gen.parked.get(KIMI, 0) == 0, "skipped for the reserve, not parked: the case the old check missed"
    wait = gen.no_model_wait()
    assert 0 < wait <= 24 * 3600 and abs(wait - min(6 * 3600, llm._to_budget_midnight())) < 5, \
        "until the earlier of a free model coming back and Sydney midnight"
    assert gen.no_model_wait(priority=True) == 0.0, "an amplified post (or a draft's second ask) may spend the reserve"
    assert abs(gen.next_available_in(priority=False) - wait) < 1
    assert gen.next_available_in() == 0.0, "a draft asks again with the reserve (bot.draft_checked)"


def test_allowance_spent_and_free_models_parked_waits_for_the_earlier_of_the_two(tmp_path, monkeypatch):
    gen = make_gen(tmp_path, monkeypatch, spent=10.0)
    park_free(gen, 90)
    assert abs(gen.no_model_wait() - 90) < 2 and abs(gen.no_model_wait(priority=True) - 90) < 2
    park_free(gen, 40 * 3600)                                       # the free quota is gone for longer than the day
    midnight = llm._to_budget_midnight()
    assert abs(gen.no_model_wait(priority=True) - midnight) < 5, "the allowance steps up at Sydney midnight"
    assert abs(gen.next_available_in() - midnight) < 5
    assert 0 < gen.next_available_in() <= 24 * 3600


def test_old_check_said_available_new_one_does_not(tmp_path, monkeypatch):
    """The incident: park times are all 0 for Kimi (never parked), so min(park) - now <= 0."""
    gen = make_gen(tmp_path, monkeypatch, spent=8.0)
    park_free(gen, 3600)
    old = max(0.0, min(gen.parked.get(m, 0) for _, m in gen.chain) - time.time())
    assert old == 0.0 and gen.no_model_wait() > 0


def test_models_restriction_and_empty_chain(tmp_path, monkeypatch):
    gen = make_gen(tmp_path, monkeypatch, spent=10.0)
    park_free(gen, 120)
    assert gen.no_model_wait(models=("free-a",)) > 100 and gen.no_model_wait(models=(KIMI,)) > 3600
    assert gen.no_model_wait(priority=True, models=(KIMI,)) > 3600
    gen.chain = []
    assert gen.no_model_wait() == 3600.0 and gen.next_available_in() == 3600.0


def test_qwen_fallback_counts_as_a_model(tmp_path, monkeypatch):
    gen = make_gen(tmp_path, monkeypatch, spent=10.0)
    park_free(gen, 3600)
    gen.allow_qwen = True
    assert gen.no_model_wait() == 0.0 and gen.no_model_wait(models=("free-a",)) > 0


def test_bot_model_wait_uses_the_helper_and_tolerates_old_fakes():
    class Old:
        def next_available_in(self):
            return 7.0

    class New:
        def no_model_wait(self, priority=False, models=None):
            return 5.0 if priority else 99.0

        def next_available_in(self):
            return 1.0
    assert bot.model_wait(Old()) == 7.0 and bot.model_wait(New()) == 5.0


# ---- bot.defer / bot.lose: every mode is put back, nothing is logged or counted ----------------------------------
class Targeter:
    def __init__(self):
        self.requeued, self.lost = [], []

    def requeue(self, cand, why):
        self.requeued.append((cand, why))

    def lose(self, target, why, source=None):
        self.lost.append((target, why))


@pytest.fixture
def logged(monkeypatch):
    rows = []
    monkeypatch.setattr(bot, "log", rows.append)
    return rows


def test_reply_goes_back_to_the_targeter_with_no_try_and_no_row(logged):
    t, cand = Targeter(), {"post": {"post_id": 5}}
    assert bot.lose(t, [], dict(mode="reply", cand=cand, target={"post_id": 5}), "no_model") == "deferred"
    assert t.requeued == [(cand, "no_model")] and not logged and not t.lost


def test_targeter_requeue_no_model_counts_no_try_and_a_gate_failure_does(monkeypatch):
    from swan_bot import targeting
    rows = []
    tg = targeting.Targeter(None, log=rows.append)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    cand = {"post": dict(post_id=9, author_id=500, body="x", created_at=now), "tries": 0}
    tg.requeue(cand, "no_model")
    assert cand["tries"] == 0 and "not_before" not in cand and tg.candidates[9] is cand
    tg.requeue(cand, "gate:length_400")
    assert cand["tries"] == 1 and cand["not_before"] > time.time()


def test_reply_without_a_candidate_cannot_be_put_back_and_is_logged_lost(logged):
    t = Targeter()
    assert bot.lose(t, [], dict(mode="reply", target={"post_id": 7, "author_id": 500}), "no_model") == "lost"
    assert logged[-1]["act"] == "lost" and logged[-1]["why"] == "no_model"


def test_reply_back_goes_to_the_front_with_its_tries_unchanged(logged):
    queue, other = [], dict(mode="reply_back", target={"post_id": 2})
    queue.append(other)
    job = dict(mode="reply_back", target={"post_id": 1}, tries=1)
    assert bot.lose(Targeter(), queue, job, "no_model") == "deferred"
    assert queue[0] is job and job["tries"] == 1 and not logged
    # ... while a gate failure still counts a try and logs, as before
    job2 = dict(mode="reply_back", target={"post_id": 3}, tries=0)
    assert bot.lose(Targeter(), queue, job2, "gate:length_400") == "requeued" and job2["tries"] == 1 and logged


@pytest.mark.parametrize("mode", ["post", "journalist"])
def test_post_and_journalist_consumed_nothing_so_they_are_just_deferred(mode, logged):
    state = dict(journalist_any=5, journalist_last={"3": 5})
    assert bot.lose(Targeter(), [], dict(mode=mode, target={"post_id": 4}), "no_model") == "deferred"
    assert state == dict(journalist_any=5, journalist_last={"3": 5}) and not logged


def test_unknown_mode_without_a_way_back_is_still_logged_lost(logged):
    assert bot.lose(Targeter(), [], dict(mode="mystery", target={"post_id": 4}), "no_model") == "lost"
    assert logged and logged[0]["act"] == "lost"


def test_gate_failures_are_still_lost_for_the_modes_that_never_requeued(logged):
    assert bot.lose(Targeter(), [], dict(mode="journalist", target={"post_id": 4}), "gate:length_400") == "lost"
    assert logged[0]["act"] == "lost" and logged[0]["why"] == "gate:length_400"


def test_second_voice_is_put_back_in_the_schedule_once(logged):
    state = {"second_voice": []}
    sv = dict(post_id=4, due=0, author=9, frame="f", first_persona="p")
    job = dict(mode="second_voice", target={"post_id": 4},
               defer=lambda sv=sv: sv in state["second_voice"] or state["second_voice"].append(sv))
    assert bot.lose(Targeter(), [], job, "no_model") == "deferred" and state["second_voice"] == [sv]
    assert bot.lose(Targeter(), [], job, "no_model") == "deferred" and state["second_voice"] == [sv], "never twice"
    assert not logged


@pytest.mark.parametrize("kind,mode", [("thread", "thread"), ("repost", "repost"), ("answer", "thread_answer")])
def test_thread_jobs_are_handed_back_to_the_amplifier(kind, mode, tmp_path, monkeypatch, logged):
    monkeypatch.setattr(config, "AMP_OFF_FILE", tmp_path / "AMPLIFY_OFF")
    rec = dict(persona="p1", username="u1", role="voice", last_write=0)
    accounts = types.SimpleNamespace(
        boosters=lambda: [], voices=lambda: [rec], hidden=lambda: {}, reserved=set(),
        by_persona=lambda p: rec, rest=lambda r, t, citizen=True: None, eligible=lambda *a, **kw: rec)
    social = types.SimpleNamespace(get_post=lambda pid: dict(post_id=pid, author_id=7, body="b"))
    th = dict(kind=kind, post_id=900, due=time.time() - 1, author="p0", frame="F14_no_yes_but", parent=901)
    state = {"amp_threads": [th], "amp_posts": {"900": dict(text="our post")}}
    amp = amplify.Amplifier(social, accounts, state, False, lambda r: None)
    job = amp.next_write_job()
    assert job and job["mode"] == mode and state["amp_threads"] == []
    used = state["amp_posts"]["900"].get({"thread": "touched", "repost": "reposted"}.get(kind, "-"), [])
    assert used == (["p1"] if kind != "answer" else []), "the pick used the voice's turn"
    assert bot.lose(Targeter(), [], job, "no_model") == "deferred"
    assert state["amp_threads"] == [th], "the thread entry is back"
    assert state["amp_posts"]["900"].get("touched", []) == [] and state["amp_posts"]["900"].get("reposted", []) == []
    assert amp.next_write_job()["mode"] == mode, "and can be picked again"
    assert not logged


# ---- the dashboard counts the episode rows ----------------------------------------------------------------------
def test_dashboard_banner_counts_the_attempts_in_episode_rows(tmp_path):
    now = dt.datetime(2026, 10, 23, 5, 0, tzinfo=dt.timezone.utc)
    rows = [dict(act="no_model", phase="start", n=1, new=1, _t=now - dt.timedelta(minutes=25)),
            dict(act="no_model", phase="ongoing", n=40, new=39, _t=now - dt.timedelta(minutes=5)),
            dict(act="no_model", phase="end", n=45, new=5, _t=now - dt.timedelta(minutes=1)),
            dict(act="lost", why="expired:no_model", _t=now - dt.timedelta(minutes=2))]
    b = build.drafting_state(rows, tmp_path, now)
    assert b["level"] in ("amber", "red") and "45 drops in 10 min, 46 in 30" in b["text"], b["text"]
