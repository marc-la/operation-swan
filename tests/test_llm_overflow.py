"""23 Oct: load spreading across reply models (llm.Generator.complete_in_order, config.LLM_OVERFLOW_*). With several
drafters the reply model's pacing slots fill; a call whose lead model is busy for more than LLM_OVERFLOW_AT_S goes to a
free model of the overflow set instead of sleeping, nothing waits longer than LLM_MAX_WAIT_S, and models the code
excludes (REPLY_NEVER, models outside the draft's own list) are never reached this way. Fake LLM, no network."""
import datetime as dt
import pathlib
import sys
import threading
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from swan_bot import bot, config, llm  # noqa: E402

KIMI, HAIKU = config.REPLY_MODELS
LITE = "gemini-3.5-flash-lite"                    # left REPLY_MODELS on 31 Oct; the mechanism tests keep it in their set
LIVE_OVERFLOW = config.LLM_OVERFLOW_MODELS        # before the fixture swaps it
GLM, FREE = "zai.glm-5", "openai/gpt-oss-120b"
GAP, AT, MAXW = 0.5, 0.1, 0.8                     # seconds: shrunk from 6 s, 2.5 s and 20 s


def today():
    return dt.datetime.now(llm.BUDGET_DAY).date().isoformat()


@pytest.fixture
def gen(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "SPEND_FILE", tmp_path / "spend.json")
    monkeypatch.setattr(llm, "USAGE_FILE", tmp_path / "usage.json")
    monkeypatch.setattr(config, "LLM_BUDGET_DAYS", [(today(), today(), 1)])
    monkeypatch.setattr(config, "LLM_BUDGET_USD", 1000.0)
    monkeypatch.setattr(config, "LLM_OVERFLOW_AT_S", AT)
    monkeypatch.setattr(config, "LLM_MAX_WAIT_S", MAXW)
    monkeypatch.setattr(config, "LLM_OVERFLOW_MODELS", (KIMI, HAIKU, LITE))       # the mechanism, on three models
    g = llm.Generator("unused")
    g.min_gap = GAP
    g.chain = [("gemini", LITE), ("bedrock", KIMI), ("bedrock", GLM), ("bedrock-converse", HAIKU), ("groq", FREE)]
    g.sent = []                                    # (model, time) of every request that reached the "provider"
    g.fail = {}                                    # model -> exception to raise instead of answering

    def fake_call(prov, model, system, user, *a, **kw):
        g._pace(model)
        g.sent.append((model, time.time()))
        if model in g.fail:
            raise g.fail[model]
        return f"from {model}"
    g._call = fake_call
    return g


ORDER = [KIMI, HAIKU, LITE]                        # the draft's own list (REPLY_MODELS, then flash-lite from the chain)


def test_live_overflow_set_waits_for_kimi_or_haiku_and_keeps_flash_lite_as_the_last_resort(gen, monkeypatch):
    """31 Oct (Marc): flash-lite out of REPLY_MODELS and so out of the overflow set: busy leads are waited for, and
    flash-lite drafts only when both fail or are parked (the day's budget)."""
    assert LITE not in config.REPLY_MODELS and LIVE_OVERFLOW == config.REPLY_MODELS
    monkeypatch.setattr(config, "LLM_OVERFLOW_MODELS", LIVE_OVERFLOW)
    gen.last_call.update({KIMI: time.time() + 0.3, HAIKU: time.time() + 0.3})
    assert gen.complete_in_order("s", "u", ORDER)[1] == KIMI, "both busy: wait for the lead, not flash-lite"
    assert LITE not in {m for m, _ in gen.sent}
    gen.parked[KIMI] = gen.parked[HAIKU] = time.time() + 100
    assert gen.complete_in_order("s", "u", ORDER)[1] == LITE, "both parked: flash-lite still drafts"


def test_free_lead_model_is_used_and_nothing_overflows(gen):
    assert gen.complete_in_order("s", "u", ORDER) == (f"from {KIMI}", KIMI)
    assert gen.overflowed_from is None and gen.overflow_in == {}


def test_three_concurrent_drafters_spread_over_models_without_sleeping(gen):
    out, t0 = [], time.time()
    barrier = threading.Barrier(3)

    def drafter():
        barrier.wait()
        t = time.time()
        text, model = gen.complete_in_order("s", "u", ORDER)
        out.append((model, gen.overflowed_from, time.time() - t))
    ts = [threading.Thread(target=drafter) for _ in range(3)]
    [t.start() for t in ts]
    [t.join(10) for t in ts]
    assert sorted(m for m, _, _ in out) == sorted(ORDER), "one call each: Kimi, then the overflow to Haiku and flash-lite"
    assert sorted(f for _, f, _ in out if f) == [KIMI, KIMI], "the audit field names the busy lead"
    assert max(w for _, _, w in out) < AT + 0.1, "nobody slept (the pacing gap is %s s)" % GAP
    assert gen.overflow_in == {HAIKU: 1, LITE: 1}
    st = {m["model"]: m for m in gen.status()}
    assert st[HAIKU]["overflow_in"] == 1 and st[LITE]["overflow_in"] == 1 and st[KIMI]["overflow_in"] == 0


def test_lead_is_back_in_use_once_its_slot_is_free(gen):
    assert gen.complete_in_order("s", "u", ORDER)[1] == KIMI
    assert gen.complete_in_order("s", "u", ORDER)[1] == HAIKU, "Kimi was used a moment ago: overflow"
    assert gen.overflowed_from == KIMI
    time.sleep(GAP + 0.05)
    assert gen.complete_in_order("s", "u", ORDER)[1] == KIMI and gen.overflowed_from is None


def test_excluded_models_are_never_used_for_overflow(gen):
    gen.last_call.update({KIMI: time.time() + 100, HAIKU: time.time() + 100, LITE: time.time() + 100})
    t0 = time.time()
    # GLM-5 (REPLY_NEVER) and a free model outside the overflow set sit in the list; the busy lead is waited for
    text, model = gen.complete_in_order("s", "u", [KIMI, GLM, HAIKU, LITE, FREE])
    assert model == KIMI and time.time() - t0 < MAXW + 0.5
    assert {m for m, _ in gen.sent} == {KIMI}
    gen.sent.clear()
    gen.parked[KIMI] = gen.parked[HAIKU] = gen.parked[LITE] = time.time() + 100       # the overflow set is out
    assert gen.complete_in_order("s", "u", [KIMI, GLM, HAIKU, LITE, FREE])[1] == FREE, "plain fall-through still works"
    assert GLM not in {m for m, _ in gen.sent}
    assert gen.complete_in_order("s", "u", [GLM]) == (None, None)


def test_a_model_outside_the_draft_list_is_not_borrowed(gen):
    gen.last_call[KIMI] = time.time() + 100
    assert gen.complete_in_order("s", "u", [KIMI, LITE])[1] == LITE, "flash-lite is in the list and free"
    assert gen.complete_in_order("s", "u", [KIMI])[1] == KIMI, "Haiku is in the overflow set but not in this list"


def test_parked_and_over_budget_models_are_skipped(gen, monkeypatch):
    gen.last_call[KIMI] = time.time() + 100
    gen.parked[HAIKU] = time.time() + 100
    assert gen.complete_in_order("s", "u", ORDER)[1] == LITE
    gen.parked.clear()
    gen.sent.clear()
    monkeypatch.setattr(gen, "budget_left", lambda: 0.0)              # today's allowance is spent: priced models park
    assert gen.complete_in_order("s", "u", ORDER) == (f"from {LITE}", LITE)
    assert gen.park_why[KIMI] == "daily budget" and gen.park_why[HAIKU] == "daily budget"
    assert {m for m, _ in gen.sent} == {LITE}


def test_all_busy_waits_a_bounded_time_on_the_best_model(gen):
    far = time.time() + 1000
    gen.last_call.update({KIMI: far, HAIKU: far, LITE: far})
    t0 = time.time()
    text, model = gen.complete_in_order("s", "u", ORDER)
    waited = time.time() - t0
    assert model == KIMI and MAXW * 0.8 <= waited < MAXW + 0.4, waited


def test_an_overflow_model_that_fails_falls_through_and_the_draft_is_kept(gen):
    gen.last_call[KIMI] = time.time() + 100
    gen.fail[HAIKU] = llm.Unavailable("per-minute limit", 60, "Too many requests")
    text, model = gen.complete_in_order("s", "u", ORDER)
    assert (text, model) == (f"from {LITE}", LITE) and gen.overflowed_from == KIMI
    assert gen.park_why[HAIKU] == "per-minute limit" and gen.parked[HAIKU] > time.time()
    # and when the whole overflow set fails the busy lead is waited for, not lost
    gen.fail[LITE] = llm.Unavailable("daily quota", 600)
    gen.parked.pop(LITE, None)
    gen.parked.pop(HAIKU, None)
    gen.last_call[KIMI] = time.time() + 0.3
    assert gen.complete_in_order("s", "u", ORDER)[1] == KIMI and gen.overflowed_from is None


def test_cap_applies_to_the_first_request_only_so_a_retry_never_loses_the_draft(gen):
    """_call may ask twice (cut off at max_tokens, JSON mode refused): the second _pace must wait, not raise."""
    gen.last_call[KIMI] = time.time() + 0.3
    gen._local.pace_cap = 0.05
    with pytest.raises(llm.Saturated):
        gen._pace(KIMI)
    assert gen._local.pace_cap is None
    gen._local.pace_cap = 0.05
    gen.last_call[KIMI] = 0
    gen._pace(KIMI)                                  # free: booked
    t0 = time.time()
    gen._pace(KIMI)                                  # second request of the same call: no cap, waits its gap
    assert time.time() - t0 >= GAP * 0.9


def test_per_model_rpm_and_switches(gen, monkeypatch):
    monkeypatch.setitem(config.LLM_MODEL_RPM, KIMI, 60)           # a model with a known higher cap: 1 s gap
    assert gen._gap(KIMI) == 1.0 and gen._gap(HAIKU) == GAP
    gen.last_call[KIMI] = time.time() + 100
    monkeypatch.setattr(config, "LLM_OVERFLOW_AT_S", 0)           # off: strict order, waits for Kimi (bounded)
    t0 = time.time()
    assert gen.complete_in_order("s", "u", ORDER)[1] == KIMI and time.time() - t0 >= MAXW * 0.8
    assert gen.overflowed_from is None


def test_bot_complete_in_order_delegates_and_plain_fakes_keep_the_old_loop(gen):
    assert bot.complete_in_order(gen, "s", "u", ORDER) == (f"from {KIMI}", KIMI)

    class Plain:
        def complete(self, system, user, models=None, **kw):
            return (None, None) if models[0] == KIMI else (f"from {models[0]}", models[0])
    assert bot.complete_in_order(Plain(), "s", "u", ORDER) == (f"from {HAIKU}", HAIKU)


def test_a_premium_reply_model_is_called_only_when_named(gen, monkeypatch):
    """28 Oct: Sonnet sits in the chain file so bot.draft_models can name it; an unrestricted call never reaches it."""
    monkeypatch.setattr(config, "PREMIUM_REPLY_MODELS", (config.SONNET,))     # the lane as it ran 28 Oct (off 29 Oct)
    sonnet = config.SONNET
    gen.chain = gen.chain + [("bedrock-converse", sonnet)]
    for m in (LITE, KIMI, GLM, HAIKU, FREE):
        gen.parked[m] = time.time() + 3600
    assert gen.complete("s", "u")[0] is None and not gen.sent, "everything else parked: nothing falls back to Sonnet"
    assert gen.complete("s", "u", models=(sonnet,))[1] == sonnet and [m for m, _ in gen.sent] == [sonnet]
