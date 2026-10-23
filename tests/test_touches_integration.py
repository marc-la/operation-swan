"""Persona touches wired into the live code (todo/37 phase B): content.system_prompt, the desk script, facts_review.
Offline: no network, no .env, no data/ writes; the LLM is a fake.

    python -m pytest tests/test_touches_integration.py -q
"""
import importlib
import json
import pathlib
import random
import sys
import threading
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from swan_bot import config, content, touches  # noqa: E402
from swan_bot import facts as fact_store  # noqa: E402

FACT = "ferry_reduction"
CLAUSE = "the morning run carries the clinic families and it is the first to go"
LIVE = {p["key"]: p for p in content.PERSONAS}
CASES = [("tomasi", "F6_islands", None), ("sione", "F6_islands", None), ("kai", "F8_powers", None),
         ("josh", "F9_parliament", None), ("lani", "F7_livelihoods", None), ("tomasi", "F6_islands", "off_topic")]
COVID = "Your COVID years:"


def stamp(ago=60):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - ago))


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(touches, "FILE", tmp_path / "touches_auto.json")
    monkeypatch.setattr(touches, "LOG_FILE", tmp_path / "touches_auto.jsonl")
    monkeypatch.setattr(touches, "STATE", {"last": {}, "voices": {}})
    monkeypatch.setattr(config, "TOUCH_DICE", {1: 1.0, 2: 1.0, 3: 1.0})
    monkeypatch.setattr(config, "TOUCHES_ON", False)
    assert FACT in fact_store.TEXTS and FACT in fact_store.NOTES, "the test fact left the fact table"


def store_for(*keys, fact=FACT, weight=3):
    rec = {"fact": fact, "note_hash": touches.note_hash(fact_store.NOTES[fact]), "impact": [], "ts": stamp(),
           "touches": {k: {"clause": CLAUSE, "sector": "ferry_islands", "weight": weight, "ts": stamp()} for k in keys}}
    touches.save({fact: rec})


def prompt(key, frame, style=None, seed=7):
    random.seed(seed)
    meta = {"style": style} if style else {}
    text = content.system_prompt(LIVE[key], frame, meta=meta)
    return text, meta, random.random()


class Boom:
    def __getattr__(self, name):
        raise AssertionError(f"touches.{name} used with the flag off")


# ---- (a) flag off: nothing changes -----------------------------------------------------------------------------

@pytest.mark.parametrize("key,frame,style", CASES)
def test_flag_off_prompt_and_random_stream_are_untouched(monkeypatch, key, frame, style):
    store_for("tomasi", "sione", "kai", "josh", "lani")                 # a store that would fire, were the flag on
    with_module, meta_a, after_a = prompt(key, frame, style)
    monkeypatch.setattr(content, "touches", Boom())                     # any use of the module fails the call
    without, meta_b, after_b = prompt(key, frame, style)
    assert with_module == without and after_a == after_b
    assert "News that touches your week" not in with_module and "touch" not in meta_a and meta_a == meta_b


def test_flag_off_never_loads_the_store(monkeypatch):
    monkeypatch.setattr(touches, "load", lambda *a, **k: pytest.fail("store loaded with the flag off"))
    prompt("tomasi", "F6_islands")
    assert touches.STATE == {"last": {}, "voices": {}}


# ---- (b)(c)(d) flag on --------------------------------------------------------------------------------------------

def line_of(key):
    return touches.prompt_line(LIVE[key], fact_store.NOTES[FACT], CLAUSE)


def test_line_appears_once_before_covid_and_is_logged(monkeypatch):
    monkeypatch.setattr(content, "BASE_BUDGET", 5000)
    store_for("sione", "kai")
    for key, frame in (("sione", "F6_islands"), ("kai", "F8_powers")):
        monkeypatch.setattr(touches, "STATE", {"last": {}, "voices": {}})
        monkeypatch.setattr(config, "TOUCHES_ON", False)
        off, _, _ = prompt(key, frame)
        monkeypatch.setattr(config, "TOUCHES_ON", True)
        on, meta, _ = prompt(key, frame)
        line = line_of(key)
        assert on.count(line) == 1 and "News that touches your week" in on
        assert on.replace(" " + line, "") == off                       # warm and plain: everything else is as it was
        assert meta["touch"] == {"fact": FACT, "sector": "ferry_islands", "weight": 3}
        if COVID in on:
            assert on.index(line) < on.index(COVID)
        assert on.index("About you:") < on.index(line) < on.index("Your style:")


def test_covid_line_follows_the_touch_line(monkeypatch):
    monkeypatch.setattr(config, "TOUCHES_ON", True)
    monkeypatch.setattr(content, "BASE_BUDGET", 5000)      # a real prompt can sit near 3200: then the touch is dropped
    store_for("lani")
    for seed in range(40):                                              # find a draw where lani's covid line is in
        monkeypatch.setattr(touches, "STATE", {"last": {}, "voices": {}})
        on, meta, _ = prompt("lani", "F7_livelihoods", seed=seed)
        if COVID in on:
            assert on.index(line_of("lani")) < on.index(COVID)
            return
    pytest.fail("no draw had the covid line")


def test_fed_up_touch_replaces_the_frame_heat_and_never_both(monkeypatch):
    heat = content.FRAMES["F6_islands"]["heat"]
    off, meta_off, _ = prompt("tomasi", "F6_islands")
    assert content.register_of(LIVE["tomasi"]) == "fed_up" and heat in off and meta_off["heat"] is True
    monkeypatch.setattr(config, "TOUCHES_ON", True)
    monkeypatch.setattr(content, "BASE_BUDGET", 5000)      # a real prompt can sit near 3200: then the touch is dropped
    store_for("tomasi")
    on, meta, _ = prompt("tomasi", "F6_islands")
    assert heat not in on and "Your sharpest take" not in on and meta["heat"] is False
    assert on.count(line_of("tomasi")) == 1 and meta["touch"]["fact"] == FACT


def test_nothing_without_a_stored_touch_for_this_persona(monkeypatch):
    monkeypatch.setattr(config, "TOUCHES_ON", True)
    monkeypatch.setattr(content, "BASE_BUDGET", 5000)      # a real prompt can sit near 3200: then the touch is dropped
    store_for("sione")
    on, meta, _ = prompt("kai", "F8_powers")
    assert "News that touches" not in on and "touch" not in meta


def test_paused_fact_gives_no_line(monkeypatch):
    monkeypatch.setattr(config, "TOUCHES_ON", True)
    monkeypatch.setattr(content, "BASE_BUDGET", 5000)      # a real prompt can sit near 3200: then the touch is dropped
    store_for("sione")
    monkeypatch.setattr(fact_store, "PAUSED", {FACT: {"since": stamp()}})
    on, meta, _ = prompt("sione", "F6_islands")
    assert "News that touches" not in on and "touch" not in meta


def test_expired_touch_gives_no_line(monkeypatch):
    monkeypatch.setattr(config, "TOUCHES_ON", True)
    monkeypatch.setattr(content, "BASE_BUDGET", 5000)      # a real prompt can sit near 3200: then the touch is dropped
    store_for("sione")
    store = touches.load()
    store[FACT]["touches"]["sione"]["ts"] = stamp(ago=fact_store.FRESH_S + 3600)
    touches.save(store)
    on, meta, _ = prompt("sione", "F6_islands")
    assert "News that touches" not in on and "touch" not in meta


def test_off_topic_style_skips_the_line_and_the_dice(monkeypatch):
    monkeypatch.setattr(config, "TOUCHES_ON", True)
    monkeypatch.setattr(content, "BASE_BUDGET", 5000)      # a real prompt can sit near 3200: then the touch is dropped
    store_for("tomasi")
    on, meta, after = prompt("tomasi", "F6_islands", style="off_topic")
    monkeypatch.setattr(config, "TOUCHES_ON", False)
    off, _, after_off = prompt("tomasi", "F6_islands", style="off_topic")
    assert on == off and after == after_off and "touch" not in meta
    assert touches.STATE == {"last": {}, "voices": {}}


def test_a_failing_touches_module_never_breaks_a_draft(monkeypatch):
    monkeypatch.setattr(config, "TOUCHES_ON", True)
    monkeypatch.setattr(content, "BASE_BUDGET", 5000)      # a real prompt can sit near 3200: then the touch is dropped

    def boom(*a, **k):
        raise OSError("disk")
    monkeypatch.setattr(touches, "load", boom)
    on, meta, _ = prompt("sione", "F6_islands")
    assert "News that touches" not in on and "touch" not in meta


def test_a_touch_never_squeezes_the_other_lines_at_the_real_budget(monkeypatch):
    """Phase C: real prompts sit near BASE_BUDGET (3200), so a touch that was dropped first almost never survived
    (0.6% of 795 drafts at dice 1.0). The touch line now adds its own length to the budget: every other line (and a
    fed_up persona's heat) is exactly as the flag-off prompt has it, and the touch stays and is logged."""
    assert content.BASE_BUDGET == 3200
    monkeypatch.setattr(config, "TOUCH_DICE", {1: 1.0, 2: 1.0, 3: 1.0})
    survived = 0
    for key, frame in (("sione", "F6_islands"), ("lani", "F7_livelihoods"), ("tomasi", "F6_islands"),
                       ("dan", "F1_blank_cheque")):
        store_for(key)
        for seed in range(6):
            monkeypatch.setattr(touches, "STATE", {"last": {}, "voices": {}})
            monkeypatch.setattr(config, "TOUCHES_ON", False)
            off, meta_off, _ = prompt(key, frame, seed=seed)
            monkeypatch.setattr(config, "TOUCHES_ON", True)
            on, meta, _ = prompt(key, frame, seed=seed)
            line = line_of(key)
            assert line in on and meta["touch"]["fact"] == FACT
            survived += 1
            if content.register_of(LIVE[key]) == "fed_up":
                heat = content.FRAMES[frame]["heat"]
                assert heat in off and heat not in on and meta["heat"] is False
                continue
            assert on.replace(" " + line, "") == off and meta["heat"] == meta_off["heat"]
    assert survived == 24


# ---- (e) threads -------------------------------------------------------------------------------------------------

def test_concurrent_drafts_keep_state_whole_and_the_team_cap(monkeypatch):
    monkeypatch.setattr(config, "TOUCHES_ON", True)
    monkeypatch.setattr(content, "BASE_BUDGET", 5000)      # a real prompt can sit near 3200: then the touch is dropped
    keys = ["sione", "tomasi", "kai", "josh", "lani", "dan", "esther", "rafa"]
    store_for(*keys)
    gate, results, errors = threading.Barrier(8), [], []

    def work(key):
        try:
            gate.wait()
            for _ in range(6):
                meta = {}
                text = content.system_prompt(LIVE[key], "F6_islands", meta=meta)
                results.append((key, "News that touches your week" in text, "touch" in meta))
        except Exception as e:                                          # noqa: BLE001
            errors.append(e)
    threads = [threading.Thread(target=work, args=(k,)) for k in keys]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors and len(results) == 48
    voices = touches.STATE["voices"][FACT]
    assert len(voices) <= config.TOUCH_TEAM_CAP and set(voices) <= set(keys)
    assert {k for k, line, _ in results if line} <= set(voices)         # only a voice the state recorded used the line
    assert all(line == meta for _, line, meta in results)
    assert len({k for k, line, _ in results if line}) == len(voices) == config.TOUCH_TEAM_CAP
    assert all(isinstance(v, str) for v in touches.STATE["last"].values())


# ---- (f) the desk script ------------------------------------------------------------------------------------------

@pytest.fixture
def desk(monkeypatch):
    table = {"ferry_cut": {"text": "The outer-island ferry is cut to three sailings a week from Monday, the paper "
                           "reports.", "note": "ferry runs cut to three a week from Monday", "source": "x/ferry",
                           "status": "active", "added": stamp(ago=3600)}}
    monkeypatch.setattr(fact_store, "refresh", lambda *a, **k: False)
    monkeypatch.setattr(fact_store, "TABLE", table)
    monkeypatch.setattr(fact_store, "NOTES", {k: v["note"] for k, v in table.items()})
    monkeypatch.setattr(fact_store, "PAUSED", {})


class FakeGen:
    """gen.complete answers the three touches calls in order (impact, clauses, check) as JSON text."""
    chain = [("x", "model-a"), ("x", "model-b")]

    def __init__(self):
        self.calls = []

    def complete(self, system, user, json_mode=False, models=None, schema=None, temperature=0.9, **kw):
        assert json_mode and schema is None and models and temperature == 0.2
        self.calls.append(user)
        answers = [{"impact": [{"sector": "ferry_islands", "weight": 3}]}, {"tomasi": CLAUSE}, {"tomasi": "no"}, {"tomasi": "yes"}]
        return json.dumps(answers[len(self.calls) - 1]), models[0]


def desk_script():
    return importlib.import_module("swan_factdesk")


def test_run_touches_dry_generates_but_writes_nothing(desk):
    alerts, gen = [], FakeGen()
    out = desk_script().run_touches(gen, True, alerts.append)
    assert len(gen.calls) == 4 and len(out) == 1 and alerts == out and "dry run" in out[0]
    assert not touches.FILE.exists() and not touches.LOG_FILE.exists()


def test_run_touches_stores_logs_and_alerts_once_per_fact(desk):
    alerts = []
    desk_script().run_touches(FakeGen(), False, alerts.append)
    assert len(alerts) == 1 and "touches ferry_cut" in alerts[0] and "--undo-touches 1" in alerts[0]
    assert list(touches.load()["ferry_cut"]["touches"]) == ["tomasi"]
    assert len(touches.LOG_FILE.read_text().splitlines()) == 1


def test_run_touches_asks_the_desk_models_in_order(desk, monkeypatch):
    monkeypatch.setattr(config, "FACTDESK_MODELS", ["model-b"])
    gen = FakeGen()
    seen = []
    orig = gen.complete
    gen.complete = lambda *a, **k: (seen.append(k["models"]), orig(*a, **k))[1]
    desk_script().run_touches(gen, True, lambda s: None)
    assert seen[0] == ["model-b"]


def test_a_touches_exception_never_fails_the_run(desk, monkeypatch, capsys):
    def boom(*a, **k):
        raise RuntimeError("model fell over")
    monkeypatch.setattr(touches, "refresh", boom)
    assert desk_script().run_touches(FakeGen(), False, print) == []
    assert "touches: RuntimeError" in capsys.readouterr().out


def run_main(monkeypatch, argv, refresh):
    sd = desk_script()
    calls = []
    monkeypatch.setattr(sys, "argv", ["swan_factdesk.py"] + argv)
    monkeypatch.setattr(sd.config, "load_env", lambda: None)
    monkeypatch.setattr(sd.ctn, "NewsSites", lambda: None)
    monkeypatch.setattr(sd.llm, "Generator", lambda _x: FakeGen())
    monkeypatch.setattr(sd.factdesk, "load_state", lambda: {"mirror_pending": []})
    monkeypatch.setattr(sd.factdesk, "run", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(sd.factdesk, "write_json", lambda *a, **k: calls.append("state written"))
    monkeypatch.setattr(sd.touches, "refresh", lambda ask, **kw: calls.append(("refresh", kw)) or refresh())
    sd.main()
    return calls


def test_main_dry_runs_touches_with_dry_and_writes_no_state(desk, monkeypatch):
    calls = run_main(monkeypatch, ["--dry", "--no-auto"], lambda: [])
    assert [c[0] for c in calls] == ["refresh"] and calls[0][1]["dry"] is True


def test_main_survives_a_touches_exception(desk, monkeypatch):
    def boom():
        raise RuntimeError("x")
    calls = run_main(monkeypatch, ["--no-auto"], boom)
    assert [c if isinstance(c, str) else c[0] for c in calls] == ["refresh", "state written"]   # still wrote its state


def test_main_no_touches_skips_the_step(desk, monkeypatch):
    calls = run_main(monkeypatch, ["--dry", "--no-auto", "--no-touches"], lambda: [])
    assert calls == []


# ---- (g) facts_review --undo-touches -------------------------------------------------------------------------------

def test_facts_review_undo_touches_parses_and_calls_undo(monkeypatch, capsys):
    fr = importlib.import_module("facts_review")
    seen = []
    monkeypatch.setattr(fr.config, "load_env", lambda: None)
    monkeypatch.setattr(fr.touches, "undo", lambda n: seen.append(n) or {"id": n, "status": "undone", "removed": ["vika"]})
    monkeypatch.setattr(fr, "MongoStore", lambda: pytest.fail("the undo must not open Mongo"))
    monkeypatch.setattr(sys, "argv", ["facts_review.py", "--undo-touches", "5"])
    fr.main()
    assert seen == [5] and "'removed': ['vika']" in capsys.readouterr().out


def test_facts_review_undo_touches_end_to_end(monkeypatch, tmp_path, capsys):
    store_for("sione", "kai")
    touches.log_record(touches.load()[FACT])
    fr = importlib.import_module("facts_review")
    monkeypatch.setattr(fr.config, "load_env", lambda: None)
    monkeypatch.setattr(sys, "argv", ["facts_review.py", "--undo-touches", "1"])
    fr.main()
    assert "undone" in capsys.readouterr().out and touches.load()[FACT]["touches"] == {}


# ---- phase C ---------------------------------------------------------------------------------------------------

def test_a_corrupt_store_never_breaks_a_draft_and_is_reported_once(monkeypatch, capsys):
    monkeypatch.setattr(config, "TOUCHES_ON", True)
    store_for("sione")
    prompt("sione", "F6_islands")
    touches.FILE.write_text('{"ferry_reduction": {"touches": {"sione": {"cla')       # half a write, by hand
    for _ in range(3):
        on, meta, _ = prompt("sione", "F6_islands")
        assert "touch" not in meta or "News that touches" in on                  # last good copy or none: never an error
    assert capsys.readouterr().out.count("unreadable") == 1                      # not once per draft
    touches.FILE.write_text("[1, 2]")
    on, meta, _ = prompt("sione", "F6_islands")
    assert on and "touch" not in meta or "News that touches" in on


def test_a_malformed_record_is_a_draft_without_a_touch(monkeypatch):
    monkeypatch.setattr(config, "TOUCHES_ON", True)
    rec = {"note_hash": touches.note_hash(fact_store.NOTES[FACT]),
           "touches": {"sione": {"clause": CLAUSE, "weight": "x", "ts": stamp()}}}
    touches.save({FACT: rec, "junk": "text", "junk2": [1]})
    on, meta, _ = prompt("sione", "F6_islands")
    assert "News that touches" not in on and "touch" not in meta


def test_a_touch_written_for_an_older_note_is_not_used(monkeypatch):
    monkeypatch.setattr(config, "TOUCHES_ON", True)
    store_for("sione")
    store = touches.load()
    store[FACT]["note_hash"] = touches.note_hash("an earlier wording of the note")
    touches.save(store)
    on, meta, _ = prompt("sione", "F6_islands")
    assert "News that touches" not in on and "touch" not in meta
