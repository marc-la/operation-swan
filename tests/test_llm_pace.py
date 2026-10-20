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
