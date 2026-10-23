"""23 Oct: several drafters (config.DRAFTERS) draft at once, so drafting stops being the bottleneck (one drafter held the
bot to ~2 writes/min against the ~2.9 the rate limit allows). Rules they keep, tested end to end on the fake world of
tests/test_bot_split.py with a slow fake LLM: two drafters never hold the same voice or citizen, held() counts every
job under way, ready + inflight stays within DRAFT_AHEAD, a stop puts every job under way back, one drafter at a time
updates the pulse, and the LLM pacing holds with several callers. No network."""
import pathlib
import sys
import threading
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import test_bot_split as e2e  # noqa: E402
from test_bot_split import no_network  # noqa: E402,F401  (the fixture)

from swan_bot import bot, config, llm, pulse, targeting  # noqa: E402

CITIZEN_MODES = ("reply", "reply_back", "second_voice")


def frames_of_drafter():
    """(ready, inflight, held, mu) of the running bot.main(), read from the drafter_step frame that called us: they are its
    closure variables (choose() holds held())."""
    f = sys._getframe(2)
    while f and f.f_code.co_name != "drafter_step":
        f = f.f_back
    assert f is not None, "called from drafter_step"
    choose = f.f_locals["choose"]
    held = dict(zip(choose.__code__.co_freevars, (c.cell_contents for c in choose.__closure__)))["held"]
    return f.f_locals["ready"], f.f_locals["inflight"], held, f.f_locals["mu"]


class Recorder:
    """A slow fake draft (the LLM's 15-30 s, shrunk) that records who is drafting what, when."""

    def __init__(self, seconds=0.5, hold=None):
        self.seconds, self.hold = seconds, hold
        self.lock = threading.Lock()
        self.active = []                    # (thread, persona, citizen) now under way
        self.max_active, self.max_held = 0, 0
        self.clashes, self.not_held, self.over_cap, self.names = [], [], [], set()

    def __call__(self, gen, job, *a, **kw):
        ready, inflight, held, mu = frames_of_drafter()
        me = (threading.current_thread().name, job["rec"]["persona"],
              str((job.get("target") or {}).get("author_id")) if job["mode"] in CITIZEN_MODES else None)
        with mu, self.lock:                 # mu: the drafters' lists don't move while we look
            for other in self.active:
                if other[1] == me[1]:
                    self.clashes.append(("voice", me, other))
                if me[2] and other[2] == me[2]:
                    self.clashes.append(("citizen", me, other))
            self.active.append(me)
            self.names.add(me[0])
            self.max_active = max(self.max_active, len(self.active))
            if job not in held():
                self.not_held.append(("job", me))
            if len(self.active) > len(inflight) or any(j not in held() for j in inflight):
                self.not_held.append(("inflight", me, len(self.active), len(inflight)))
            self.max_held = max(self.max_held, len(held()))
            if len(ready) + len(inflight) > config.DRAFT_AHEAD:
                self.over_cap.append((len(ready), len(inflight)))
        try:
            if self.hold:
                self.hold.wait(30)
            else:
                time.sleep(self.seconds)
            return e2e.fake_draft_checked(gen, job, *a, **kw)
        finally:
            with self.lock:
                self.active.remove(me)


def crowd(world):
    """Several posts by the same citizens, so two drafters would want the same citizen at once."""
    for pid, author in ((211, 502), (212, 502), (213, 505), (214, 505), (215, 501), (216, 501)):
        world.add(pid, author, "Undecided about the referendum, does the pass ever end or is it forever?", 100)


@pytest.mark.slow
def test_drafters_overlap_and_never_share_a_voice_or_a_citizen(tmp_path, monkeypatch, no_network):
    world, spies = e2e.setup_world(monkeypatch, tmp_path, split=True, amp_off=True)
    crowd(world)
    rec = Recorder(0.5)
    monkeypatch.setattr(bot, "draft_checked", rec)
    monkeypatch.setattr(config, "DRAFTERS", 3)
    monkeypatch.setattr(config, "DRAFT_AHEAD", 4)
    e2e.run_main(monkeypatch)
    assert rec.max_active >= 2, "drafts overlapped in time"
    assert rec.names >= {"drafter-1", "drafter-2"}, f"drafts came from several threads: {rec.names}"
    assert not rec.clashes, f"two drafters held the same voice or citizen: {rec.clashes[:3]}"
    assert not rec.not_held, f"held() missed a job under way: {rec.not_held[:3]}"
    assert rec.max_held <= config.DRAFT_AHEAD
    assert not rec.over_cap, f"ready + inflight went past DRAFT_AHEAD: {rec.over_cap[:3]}"
    assert sum(1 for w in world.writes if w["kind"] in ("post", "reply", "repost")) >= 4, "writes still went out"


@pytest.mark.slow
def test_ready_plus_inflight_respects_a_small_cap(tmp_path, monkeypatch, no_network):
    """DRAFT_AHEAD counts drafts waiting for the writer and drafts under way: with 2, three drafters never run three."""
    world, spies = e2e.setup_world(monkeypatch, tmp_path, split=True, amp_off=True)
    crowd(world)
    rec = Recorder(0.4)
    monkeypatch.setattr(bot, "draft_checked", rec)
    monkeypatch.setattr(config, "DRAFTERS", 3)
    monkeypatch.setattr(config, "DRAFT_AHEAD", 2)
    e2e.run_main(monkeypatch)
    assert rec.max_held <= 2 and not rec.over_cap, (rec.max_held, rec.over_cap[:3])
    assert rec.max_active <= 2


@pytest.mark.slow
def test_a_stop_puts_every_job_under_way_back(tmp_path, monkeypatch, no_network):
    """SIGTERM while three drafts are under way: each citizen goes back to the targeter ("held"), no voice stays
    reserved, nothing is lost."""
    import os
    import signal
    world, spies = e2e.setup_world(monkeypatch, tmp_path, split=True, amp_off=True)
    crowd(world)
    hold = threading.Event()
    rec = Recorder(hold=hold)
    monkeypatch.setattr(bot, "draft_checked", rec)
    monkeypatch.setattr(config, "DRAFTERS", 3)
    monkeypatch.setattr(config, "DRAFT_AHEAD", 4)
    requeued, real = [], targeting.Targeter.requeue

    def requeue(self, cand, why):
        requeued.append((cand["post"]["post_id"], why))
        return real(self, cand, why)

    monkeypatch.setattr(targeting.Targeter, "requeue", requeue)
    monkeypatch.setattr(bot, "JOIN_S", 0.5)                  # the drafters are still "drafting" when the stop comes
    timer = threading.Timer(3.0, lambda: os.kill(os.getpid(), signal.SIGTERM))
    timer.start()
    try:
        e2e.run_main(monkeypatch, seconds=60)
        under_way = list(rec.active)
        held_back = [r for r in requeued if r[1] == "held"]
    finally:
        timer.cancel()
        hold.set()
    replies = [a for a in under_way if a[2]]
    assert len(under_way) >= 2, f"{under_way}: several drafts were under way at the stop"
    assert len(held_back) >= len(replies) >= 1, (held_back, replies)
    assert len({r[0] for r in held_back}) == len(held_back), "each citizen post put back once"
    assert not [a for a in e2e.actions(tmp_path) if a["act"] == "lost" and a.get("why") == "held"]


@pytest.mark.slow
def test_drafters_never_run_the_pulse_the_pulse_thread_does(tmp_path, monkeypatch, no_network):
    """23 Oct: pulse.update (an LLM call) is off the drafting path: only the "pulse" thread calls it, a slow call does
    not hold the drafters up, and the drafters read the stored pulse."""
    world, spies = e2e.setup_world(monkeypatch, tmp_path, split=True, amp_off=True)
    crowd(world)
    monkeypatch.setattr(bot, "draft_checked", Recorder(0.3))
    monkeypatch.setattr(config, "DRAFTERS", 3)
    callers, seen = [], []

    def update(state, targeter, ids, gen, log, t=None):
        callers.append(threading.current_thread().name)
        time.sleep(2.0)                                          # a slow LLM call
        state["pulse_next"] = time.time() + config.PULSE_EVERY_S
        state["pulse"] = dict(id="p1", ts=time.time(), hooks=[], no_shapes=["x"], yes_lines=[], avoid=[])
        return pulse.current(state, t)

    real_build = bot.build_prompt

    def build_prompt(job, targeter, recent_shapes=(), pulse_now=None, *a, **kw):
        seen.append((time.time(), pulse_now and pulse_now["id"]))
        return real_build(job, targeter, recent_shapes, pulse_now, *a, **kw)

    monkeypatch.setattr(pulse, "update", update)
    monkeypatch.setattr(bot, "build_prompt", build_prompt)
    t0 = time.time()
    e2e.run_main(monkeypatch)
    assert callers and set(callers) == {"pulse"}, callers
    assert len(callers) == 1, "refreshed on its own cadence, not once per drafter step"
    assert sum(1 for w in world.writes if w["kind"] in ("post", "reply", "repost")) >= 4
    early = [x for x in seen if x[0] - t0 < 1.5]
    assert early, "drafting began while the first (slow) pulse update was still running"
    assert any(pid == "p1" for _, pid in seen), "later drafts picked up the refreshed pulse"


@pytest.mark.slow
def test_a_failing_pulse_refresh_does_not_stop_the_bot(tmp_path, monkeypatch, no_network):
    """The pulse is not vital: an error in the refresh is logged once (retry after a third of PULSE_EVERY_S), the thread
    lives, drafting goes on, and the watchdog does not exit."""
    world, spies = e2e.setup_world(monkeypatch, tmp_path, split=True, amp_off=True)
    crowd(world)
    monkeypatch.setattr(bot, "draft_checked", Recorder(0.2))

    def update(*a, **kw):
        raise RuntimeError("injected pulse failure")

    monkeypatch.setattr(pulse, "update", update)
    e2e.run_main(monkeypatch)                                    # no SystemExit
    acts = e2e.actions(tmp_path)
    errs = [a for a in acts if a["act"] == "pulse_error"]
    assert len(errs) == 1 and errs[0]["why"] == "RuntimeError", errs
    assert not [a for a in acts if a["act"] == "thread_died"]
    assert not spies["alerts"], spies["alerts"]
    assert sum(1 for w in world.writes if w["kind"] in ("post", "reply", "repost")) >= 4


@pytest.mark.slow
def test_a_silent_pulse_thread_alerts_once_but_does_not_stop_the_bot(tmp_path, monkeypatch, no_network):
    world, spies = e2e.setup_world(monkeypatch, tmp_path, split=True, amp_off=True)
    crowd(world)
    monkeypatch.setattr(bot, "draft_checked", Recorder(0.2))
    monkeypatch.setattr(config, "PULSE_SILENT_S", 1)
    hang = threading.Event()
    monkeypatch.setattr(pulse, "update", lambda *a, **kw: hang.wait(30))      # an LLM call that never answers
    try:
        e2e.run_main(monkeypatch)                                # no SystemExit
    finally:
        hang.set()
    alerts = [a for a in spies["alerts"] if "pulse" in a]
    assert len(alerts) == 1 and "not fatal" in alerts[0], spies["alerts"]
    died = [a for a in e2e.actions(tmp_path) if a["act"] == "thread_died"]
    assert len(died) == 1 and died[0]["thread"] == "pulse" and died[0]["fatal"] is False, died
    assert sum(1 for w in world.writes if w["kind"] in ("post", "reply", "repost")) >= 4


def test_worker_is_critical_unless_said_otherwise():
    stop = threading.Event()
    assert bot.Worker("reader", lambda: None, stop, {}, 10).critical
    assert not bot.Worker("pulse", lambda: None, stop, {}, 10, critical=False).critical


def test_drafter_names_are_unique_and_each_has_a_heartbeat():
    """The watchdog reads beats[name] per worker: N drafters need N names, and each one's silence is its own."""
    stop, beats = threading.Event(), {}
    ws = [bot.Worker(f"drafter-{i}", lambda: stop.wait(0.02), stop, beats, silent_s=10) for i in range(1, 4)]
    for w in ws:
        w.start()
    time.sleep(0.2)
    assert sorted(beats) == ["drafter-1", "drafter-2", "drafter-3"]
    assert all(w.problem() is None for w in ws)
    beats["drafter-2"] -= 60                                     # one drafter goes silent, the others do not
    assert ws[1].problem() and ws[0].problem() is None and ws[2].problem() is None
    stop.set()
    for w in ws:
        w.join(2)


def test_a_concurrent_draft_that_repeats_a_waiting_one_is_dropped():
    ready = [dict(text="Look, my partner runs a cafe and this pass would sink her. I'm voting No.")]
    assert bot.clashes_with_ready("Look, my partner runs a cafe and this pass would sink her. I'm voting No.", "reply", ready)
    assert bot.clashes_with_ready("Look, my partner runs a gym and he'd close the doors.", "reply", ready), "same opening"
    assert not bot.clashes_with_ready("Three weeks of queues at the clinic taught me plenty.", "reply", ready)
    assert not bot.clashes_with_ready("", "repost", ready) and not bot.clashes_with_ready("anything", "repost", ready)
    assert not bot.clashes_with_ready("Anything at all", "post", [])


def test_llm_pacing_holds_with_several_drafters_calling():
    """llm._pace books each caller's slot under a lock and sleeps outside it: concurrent drafters on one model are
    still spaced min_gap apart (and another model has its own clock)."""
    g = llm.Generator.__new__(llm.Generator)
    g._lock, g.last_call, g.min_gap = threading.Lock(), {}, 0.05
    stamps, lock = [], threading.Lock()

    def call():
        g._pace("kimi")
        with lock:
            stamps.append(time.time())

    threads = [threading.Thread(target=call) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    stamps.sort()
    assert len(stamps) == 6
    assert all(b - a >= g.min_gap * 0.9 for a, b in zip(stamps, stamps[1:])), [round(b - a, 3) for a, b in zip(stamps, stamps[1:])]
