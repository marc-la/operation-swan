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
