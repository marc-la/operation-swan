"""LLM client pacing (no network)."""
import pathlib
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from swan_bot import llm  # noqa: E402


def test_pace_spaces_calls_per_model():
    g = llm.Generator.__new__(llm.Generator)            # no clients needed: only the pacing state
    g._lock, g.last_call, g.min_gap = threading.Lock(), {}, 0.05
    t0 = time.time()
    for _ in range(3):
        g._pace("m")
    g._pace("other")                                     # another model has its own clock
    assert 0.1 <= time.time() - t0 < 0.3


def test_reasoning_model_empty_at_cap_is_asked_again_uncapped():
    """gpt-oss-120b spends max_tokens on thinking and answers "" with finish "length": retry without the cap, and
    remember the model so later calls skip the cap."""
    import types
    sent = []

    def create(**kw):
        sent.append(kw["max_tokens"])
        empty = kw["max_tokens"] == 600
        msg = types.SimpleNamespace(content="" if empty else "a draft")
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg, finish_reason="length" if empty else "stop")])

    g = llm.Generator.__new__(llm.Generator)
    g._lock, g.last_call, g.min_gap, g._local, g.calls = threading.Lock(), {}, 0.0, threading.local(), {}
    g.no_cap, g.no_reasoning, g.no_schema, g.no_json_mode = set(), set(), set(), set()
    g._count = lambda model: None
    g.clients = {"groq": types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))}
    assert g._call("groq", "gpt-oss", "s", "u", False, max_tokens=600) == "a draft"
    assert sent == [600, 4096] and g.no_cap == {"gpt-oss"}
    assert g._call("groq", "gpt-oss", "s", "u", False, max_tokens=600) == "a draft" and sent[-1] == 4096


def test_a_response_without_choices_parks_the_model_instead_of_raising_typeerror():
    """28 Oct 00:02 UTC: a provider answered with choices=None; r.choices[0] killed a drafter thread and so the bot."""
    import types
    g = llm.Generator.__new__(llm.Generator)
    g._lock, g.last_call, g.min_gap, g._local, g.calls = threading.Lock(), {}, 0.0, threading.local(), {}
    g.no_cap, g.no_reasoning, g.no_schema, g.no_json_mode = set(), set(), set(), set()
    g._count = lambda model: None
    create = lambda **kw: types.SimpleNamespace(choices=None, error={"message": "upstream"})
    g.clients = {"groq": types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))}
    try:
        g._call("groq", "m", "s", "u", False)
        raise AssertionError("expected Unavailable")
    except llm.Unavailable as e:
        assert e.why == "empty response" and e.seconds == 120


def test_park_records_why_and_status_hides_expired():
    g = llm.Generator.__new__(llm.Generator)
    g.chain = [("gemini", "a"), ("groq", "b"), ("groq", "c")]
    g.parked, g.park_why, seen = {}, {}, []
    g.on_park = lambda model, until, why: seen.append((model, why))
    g._park("a", 3600, "daily quota")
    g._park("b", -1, "per-minute limit")                  # already expired
    st = {m["model"]: m for m in g.status()}
    assert st["a"]["why"] == "daily quota" and st["a"]["parked_until"] > time.time()
    assert st["b"]["parked_until"] is None and st["b"]["why"] is None and st["c"]["parked_until"] is None
    assert seen == [("a", "daily quota"), ("b", "per-minute limit")]


def test_quota_parks_survive_a_restart_but_error_parks_do_not(tmp_path):
    def gen():
        g = llm.Generator.__new__(llm.Generator)
        g.chain = [("gemini", "a"), ("groq", "b"), ("groq", "c"), ("groq", "gone")]
        g.parked, g.park_why, g.on_park = {}, {}, None
        g.park_file = tmp_path / "llm_parks.json"
        return g
    first = gen()
    first._park("a", 3600, "daily quota")
    first._park("b", 300, "bad request")                  # a deploy may be the fix: probed again
    first._park("c", -1, "daily quota")                   # already over
    second = gen()
    second.load_parks()
    assert list(second.parked) == ["a"] and second.park_why == {"a": "daily quota"}
    assert second.status()[0]["parked_until"] > time.time()
    second.chain = [("groq", "b")]                        # a model dropped from the chain is not brought back
    third = gen()
    third.chain = [("groq", "b")]
    third.load_parks()
    assert third.parked == {}
    plain = gen()
    plain.park_file = None                                # not opted in (scripts, tests): nothing read or written
    plain.load_parks()
    plain._park("a", 3600, "daily quota")
    assert plain.parked["a"] and not (tmp_path / "llm_parks.tmp").exists()
