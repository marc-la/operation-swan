"""The depth test (Marc, 24 Oct): half the reply-backs answer to a deeper thread, every reply-back logs its depth and arm,
and scripts/depth_report.py reads them out. No network."""
import importlib.util
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from swan_bot import bot, config  # noqa: E402
from test_convert import note, poll  # noqa: E402

spec = importlib.util.spec_from_file_location("depth_report", pathlib.Path(__file__).resolve().parents[1] / "scripts" / "depth_report.py")
depth_report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(depth_report)


def test_arm_is_stable_per_post_and_about_half_each(monkeypatch):
    monkeypatch.setattr(config, "THREAD_DEPTH_TEST", True)
    arms = [bot.depth_cap(pid) for pid in range(2000)]
    assert arms == [bot.depth_cap(pid) for pid in range(2000)], "a re-poll or restart keeps the arm"
    deep = sum(a == ("deep", config.THREAD_DEPTH_TEST_CAP) for a in arms)
    assert 900 < deep < 1100 and set(arms) == {("deep", 11), ("base", 8)}


def test_off_is_the_old_cutoff_for_every_post(monkeypatch):
    monkeypatch.setattr(config, "THREAD_DEPTH_TEST", False)
    assert {bot.depth_cap(pid) for pid in range(200)} == {("off", config.THREAD_MAX_DEPTH)}


def chain(n, base=900):
    """A thread of n posts: base is the root, each reply under the one before."""
    return {base + i: dict(post_id=base + i, author_id=500, reply_to_post_id=base + i - 1 if i else None) for i in range(n)}


def pid_with_arm(arm):
    return next(p for p in range(1, 100) if bot.depth_cap(p)[0] == arm)


def test_deep_arm_answers_a_depth_9_thread_and_base_arm_skips_it(monkeypatch):
    monkeypatch.setattr(config, "THREAD_DEPTH_TEST", True)
    deep_pid, base_pid = pid_with_arm("deep"), pid_with_arm("base")
    posts = {**chain(9), deep_pid: dict(post_id=deep_pid, author_id=501, reply_to_post_id=908, body="still here"),
             base_pid: dict(post_id=base_pid, author_id=502, reply_to_post_id=908, body="also here")}
    jobs, acc = poll(posts, [note(1, deep_pid), note(2, base_pid)], monkeypatch)
    assert [j["target"]["post_id"] for j in jobs] == [deep_pid], "only the deep arm answers at depth 9"
    assert jobs[0]["depth"] == 9 and jobs[0]["depth_arm"] == "deep"
    assert acc.resolved == [1, 2], "the skipped one is resolved too, as before"


def test_skip_row_and_job_carry_depth_and_arm(monkeypatch):
    monkeypatch.setattr(config, "THREAD_DEPTH_TEST", True)
    rows = []
    base_pid = pid_with_arm("base")
    posts = {**chain(9), base_pid: dict(post_id=base_pid, author_id=502, reply_to_post_id=908, body="x")}
    acc = types.SimpleNamespace(notifications=lambda unresolved, limit: [note(2, base_pid)], resolve_notification=lambda n: None)
    accounts = types.SimpleNamespace(voices=lambda: [dict(username="v0")], parked=lambda rec: False, session=lambda rec: acc)
    monkeypatch.setattr(bot, "log", rows.append)
    assert bot.reply_back_jobs(types.SimpleNamespace(get_post=lambda p: posts[p]), accounts, None) == []
    assert rows == [dict(act="skip", why="deep_thread", mode="reply_back", target_post=base_pid, target_author=502,
                         username="v0", depth=9, depth_arm="base")]


def test_shallow_thread_logs_its_depth(monkeypatch):
    monkeypatch.setattr(config, "THREAD_DEPTH_TEST", True)
    posts = {**chain(4), 1: dict(post_id=1, author_id=500, reply_to_post_id=903, body="fair, but")}
    jobs, _ = poll(posts, [note(11, 1)], monkeypatch)
    assert jobs[0]["depth"] == 4 and jobs[0]["depth_arm"] in ("base", "deep")


def test_the_report_reads_answers_by_depth_and_arm():
    acts = [dict(act="reply_back", live=True, post_id=i, depth=d, depth_arm=a) for i, (d, a) in enumerate(
        [(3, "base"), (3, "deep"), (9, "deep"), (9, "deep"), (10, "deep"), (6, "base"), (6, "base")], start=1)]
    acts += [dict(act="reply_back", live=True, post_id=99), dict(act="skip", mode="reply_back", why="deep_thread", depth=8,
                                                                  depth_arm="base")]
    outs = [dict(act="outcome", post_id=i, at_h=6.0, citizen_replies=c) for i, c in
            [(1, 1), (2, 0), (3, 1), (4, 0), (5, 0), (6, 1), (7, 0)]]
    outs.append(dict(act="outcome", post_id=3, at_h=1.0, citizen_replies=0))       # an early check does not count
    text = "\n".join(depth_report.report(acts, outs))
    assert "deep  9-10" in text and "base  6-7" in text
    assert "depth 8+: 1/3 answered (33.3%)   depth 4-7: 1/2 (50.0%)" in text, text
    assert "base/8: 1" in text and "1 reply-backs written before the depth was logged" in text
