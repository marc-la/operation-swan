"""Greedy job order (todo/19): a waiting citizen reply goes before the amplifier's own-thread jobs (no network)."""
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from swan_bot import bot  # noqa: E402

THREAD = dict(mode="thread", rec=dict(username="v1"))


def amp(post_due=False):
    return types.SimpleNamespace(next_write_job=lambda: dict(THREAD), amp_post_due=lambda: post_due,
                                 pick_author=lambda: None)


def candidate(pid=7, author=500):
    return dict(post=dict(post_id=pid, author_id=author, body="b"), frame="F14_no_yes_but", wants=["sunset"],
                context=None, source="latest", identity=None, score=1.0)


class Targeter:
    def __init__(self, *cands):
        self.candidates = {c["post"]["post_id"]: c for c in cands}

    def next_target(self, our_ids, replied, contacted):
        return self.candidates.pop(next(iter(self.candidates))) if self.candidates else None


def test_citizen_candidate_beats_a_due_thread_job():
    accounts = types.SimpleNamespace(eligible=lambda frame, prefer=(): dict(username="v2"))
    citizen = lambda: bot.citizen_reply(Targeter(candidate()), accounts, set(), [], {})
    job = bot.pick_job(None, citizen, amp())
    assert job["mode"] == "reply" and job["target"]["post_id"] == 7


def test_thread_job_when_no_citizen_waits():
    accounts = types.SimpleNamespace(eligible=lambda frame, prefer=(): dict(username="v2"))
    assert bot.pick_job(None, lambda: bot.citizen_reply(Targeter(), accounts, set(), [], {}), amp())["mode"] == "thread"


def test_candidate_kept_when_no_voice_is_free():
    t = Targeter(candidate())
    accounts = types.SimpleNamespace(eligible=lambda frame, prefer=(): None)
    job = bot.pick_job(None, lambda: bot.citizen_reply(t, accounts, set(), [], {}), amp())
    assert job["mode"] == "thread" and 7 in t.candidates, "the citizen waits for the next free voice"


def test_queued_reply_back_goes_first():
    queued = dict(mode="reply_back", rec=dict(username="v3"))
    assert bot.pick_job(queued, lambda: 1 / 0, amp()) is queued
