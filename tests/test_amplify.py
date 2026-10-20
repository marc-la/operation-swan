"""Amplifier: the schedule's shape and the role rules (no network)."""
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from swan_bot import amplify, config, content, quality  # noqa: E402
from swan_bot.bot import Accounts  # noqa: E402


def make_accounts(n_voices=12, n_boosters=30):
    acc = Accounts(None, live=False)
    acc.records = [dict(username=f"v{i}", persona=content.PERSONAS[i]["key"], status="active", last_write=0)
                   for i in range(n_voices)]
    acc.records += [dict(username=f"b{i}", role="booster", persona=None, status="active", sleep_start=(i * 0.8) % 24)
                    for i in range(n_boosters)]
    return acc


def make_amp(acc, state=None):
    amp = amplify.Amplifier(None, acc, {} if state is None else state, live=False, log=lambda r: None)
    amp.scale = 1.0
    return amp


def test_boosters_never_write():
    acc = make_accounts()
    assert all(r.get("role") != "booster" for r in acc.voices())
    for _ in range(50):
        assert acc.eligible().get("role") != "booster"
    assert acc.by_persona("lani")["username"] == "v0"


def test_like_plan_is_organic_shaped():
    acc = make_accounts()
    amp = make_amp(acc)
    author = acc.records[0]
    t = time.time()
    plan = amp.on_post(None, author, "text", "F1_blank_cheque", "heavy")
    users = [a["username"] for a in plan]
    assert len(users) == len(set(users)), "one like per account per post"
    assert author["username"] not in users
    assert all(a["due"] - t >= 45 for a in plan), "never within 45 s of posting"
    assert all(a["due"] - t <= 120 * 60 + 1 for a in plan)
    assert 10 <= len(plan) <= 42
    early = sum(a["due"] - t < 15 * 60 for a in plan)
    assert early >= len(plan) / 2, "front-loaded: most likes in the first 15 min"
    assert not any(amp.asleep(next(r for r in acc.records if r["username"] == a["username"]), a["due"]) for a in plan)


def test_none_level_schedules_nothing():
    acc = make_accounts()
    amp = make_amp(acc)
    assert amp.on_post(None, acc.records[0], "text", "F1_blank_cheque", "none") == []
    assert amp.state["amp_threads"] == []


def test_thread_jobs_come_from_other_voices():
    acc = make_accounts()
    amp = make_amp(acc)
    amp.on_post(None, acc.records[0], "our post", "F1_blank_cheque", "heavy")
    for th in amp.state["amp_threads"]:
        th["due"] = 0
    seen = []
    while True:
        job = amp.next_write_job()
        if not job:
            break
        assert job["rec"]["persona"] != "lani"
        assert job["rec"].get("role") != "booster"
        assert job["mode"] in ("thread", "repost")
        seen.append(job["rec"]["persona"])
    assert len(seen) == len(set(seen)), "each voice touches a post once"


def test_paused_by_file(tmp_path, monkeypatch):
    acc = make_accounts()
    amp = make_amp(acc)
    monkeypatch.setattr(config, "AMP_OFF_FILE", tmp_path / "AMPLIFY_OFF")
    assert not amp.paused()
    (tmp_path / "AMPLIFY_OFF").touch()
    assert amp.paused() and not amp.amp_post_due() and amp.next_write_job() is None


def test_booster_identity_reads_human():
    for _ in range(200):
        user, name = amplify.booster_identity()
        assert user and len(user) <= 32 and user == user.lower() and user != name.lower()


def test_side_of():
    assert amplify.side_of("I'm voting no #keepkingstoniaopen") == "no"
    assert amplify.side_of("vote yes to protect us #voteyes") == "yes"
    assert amplify.side_of("what does the referendum list cover?") == "neutral"
    assert amplify.side_of("lovely evening at the beach") == "off"


def test_bandit_prefers_measured_best():
    acc = make_accounts()
    state = {"amp_stats": {"heavy": [5, 500.0], "light": [5, 100.0], "none": [5, 50.0]}}
    amp = make_amp(acc, state)
    picks = [amp.choose_level() for _ in range(400)]
    assert picks.count("heavy") > 300


def test_thread_lengths_known_to_quality():
    assert "thread" in quality.LENGTHS and "thread_answer" in quality.LENGTHS
    for style in content.THREAD_STYLES:
        assert content.thread_reply_prompt("a post", "F1_blank_cheque", style)


def test_tick_runs_own_and_filler_likes_never_on_yes():
    acc = make_accounts()
    logged = []

    class Stub:
        feed_posts = [dict(post_id=1000 + i, author_id=5000 + i, reply_to_post_id=None, kind="post",
                           body=["voting no on this #keepkingstoniaopen", "vote yes #voteyes", "nice day at the market"][i % 3])
                      for i in range(30)]
        trending_ids = []

    amp = amplify.Amplifier(None, acc, {}, live=False, log=logged.append, targeter=Stub())
    amp.on_post(None, acc.records[0], "text", "F1_blank_cheque", "heavy")
    for a in amp.state["amp_actions"]:
        a["due"] = 0
    for _ in range(200):
        amp.next_filler = 0
        amp.like_times.clear()
        amp._tick()
    likes = [r for r in logged if r["act"] == "like"]
    own = [r for r in likes if r["own"]]
    filler = [r for r in likes if not r["own"]]
    assert own and len(own) == len({r["username"] for r in own})
    assert len(filler) >= len(own), "at least half of all likes go to posts that aren't ours"
    yes_ids = {p["post_id"] for p in Stub.feed_posts if "#voteyes" in p["body"]}
    assert not any(r["post_id"] in yes_ids for r in filler)
