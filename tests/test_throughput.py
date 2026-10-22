"""todo/24: throughput to ~3/min and no wasted drafts (no network)."""
import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from swan_bot import bot, config, targeting  # noqa: E402


def ago(minutes):
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes)).isoformat()


def job(mode, persona, author, post_id=1):
    return dict(mode=mode, rec=dict(persona=persona), target=dict(post_id=post_id, author_id=author))


# ---- 4. no draft for a capped citizen ------------------------------------------------------------------------------
def test_held_drafts_count_as_sent():
    contacted = {}
    targeting.contact(contacted, 914, "grace")
    held = [job("reply", "kai", 914), job("post", "dan", None), job("reply", "ben", 700)]
    held[1]["target"] = None
    now = bot.contacted_now(contacted, held)
    assert now["914"] == {"grace", "kai"} and now["700"] == {"ben"}
    assert len(now) == 2, "a post has no citizen"
    assert bot.contacted_now(contacted) == targeting.sessions(contacted), "nothing held: as before"


def test_drafter_skips_a_citizen_a_held_draft_will_cap():
    """The night of 21 Oct: grace answered citizen 914, kai's draft to them waited for the writer, and josh was
    drafted too (the cap counted grace only); josh's draft was thrown away at send. Now josh isn't drafted."""
    t = targeting.Targeter(None, log=lambda r: None)
    t.is_citizen = lambda aid: True
    contacted = {}
    targeting.contact(contacted, 914, "grace")
    t._consider(dict(post_id=168865, author_id=914, created_at=ago(1), body="still not sure about this referendum"),
                "latest")
    assert 168865 in t.candidates
    held = [job("reply", "kai", 914, post_id=168807)]
    assert t.next_target(set(), set(), bot.contacted_now(contacted, held)) is None
    assert t.items[168865]["why"] == "session_cap", "it waits for the next session; it isn't dropped"
    assert t.next_target(set(), set(), bot.contacted_now(contacted, []))["post"]["post_id"] == 168865
    j = job("reply", "josh", 914, post_id=168865)
    targeting.contact(contacted, 914, "kai")
    assert bot.gone_at_send(j, dict(replied_posts=[], contacted=contacted)) == "session_cap", "the send check agrees"
    assert config.SESSION_VOICES == 2


# ---- 1. pace to ~2.9/min from the headers --------------------------------------------------------------------------
class RL:
    def __init__(self, limit, remaining, reset):
        self.limit, self.remaining, self.reset = limit, remaining, reset


def test_header_gap_keeps_one_write_for_the_swarm():
    assert config.WRITE_MARGIN == 1
    assert bot.header_gap(None) == 0.0, "no headers: the pace gap alone"
    assert bot.header_gap(RL(3, 2, 20)) == 0.0, "2 left: our next write still leaves 1"
    assert abs(bot.header_gap(RL(3, 1, 40)) - 20) < 1e-9, "1 left: wait one refill (reset / missing)"
    assert abs(bot.header_gap(RL(3, 0, 60)) - 40) < 1e-9, "0 left (the swarm took the spare): two refills"
    assert abs(bot.header_gap(RL(6, 1, 50)) - 10) < 1e-9, "a scaled limit is read from the headers, not assumed"


def test_write_gap_is_the_larger_and_never_past_the_limit(monkeypatch):
    monkeypatch.setattr(bot.random, "uniform", lambda a, b: (a + b) / 2)
    assert abs(bot.pace_gap(2.9) - 60 / 2.9) < 1e-9, "mean jitter 1.0: aims at per_min"
    assert bot.write_gap(RL(3, 2, 20), 2.9) == bot.pace_gap(2.9)
    assert bot.write_gap(RL(3, 0, 60), 2.9) == 40.0
    assert config.MAX_PER_MIN <= 3.0, "the rules' team limit (posts + replies + reposts)"


def test_steady_state_rate_with_the_swarm():
    """Simulate the bucket (3 a minute, refilling one every 20 s) with our writer and a swarm repost every 5 min that
    goes while >= 1 is left: our pace stays 2.8+/min, the bucket never goes below 0 (no 429), and the swarm's
    reposts find a write left."""
    import random
    random.seed(4)
    limit, refill = 3, 20.0
    tokens, t, nxt, ours, swarm_ok, swarm_try = 3.0, 0.0, 0.0, 0, 0, 0
    rl = None
    step = 0.5
    while t < 3600:
        tokens = min(limit, tokens + step / refill)
        if t % 300 < step and t > 0:               # the swarm's run: one repost when a write is left
            swarm_try += 1
            if tokens >= 1:
                tokens -= 1
                swarm_ok += 1
        if t >= nxt:
            assert tokens >= 1, f"a write at {t:.0f} s would be rate-limited"
            tokens -= 1
            ours += 1
            missing = limit - int(tokens)
            rl = RL(limit, int(tokens), round(missing * refill - (tokens - int(tokens)) * refill))
            nxt = t + bot.write_gap(rl, 2.9)
        t += step
    assert ours / 60 >= 2.6, ours / 60
    assert swarm_ok == swarm_try


# ---- 3. near-duplicates: strict to the same citizen or thread, looser across citizens --------------------------------
OURS = ("The question has no end date and no review built in, so whatever list they write after the vote stays. "
        "I'm voting No.")
CLOSE = ("The question has no end date and no review, so the list they write after the ballot is there for good. "
         "I'm voting No on it.")


def test_near_duplicate_thresholds():
    from swan_bot import quality
    sim = quality.similar(CLOSE, OURS)
    assert quality.NEAR_DUP_SAME < sim <= quality.NEAR_DUP_OTHER, sim
    assert not quality.near_duplicate(CLOSE, "reply", recent_texts=[OURS]), "another citizen: loose"
    assert quality.near_duplicate(CLOSE, "reply", recent_texts=[OURS], same=[OURS]), "same citizen or thread: strict"
    assert quality.near_duplicate(CLOSE, "post", recent_texts=[OURS]), "posts stay strict against everything"
    assert quality.near_duplicate(OURS, "reply", recent_texts=[OURS]), "a copy is caught everywhere"


def test_same_target_texts():
    sent = [[500, 10, "to 500 in thread 10"], [501, 10, "to 501 in thread 10"], [502, 20, "to 502 elsewhere"]]
    ready = [dict(job=dict(target=dict(post_id=30, author_id=500)), text="waiting, to 500"),
             dict(job=dict(target=None), text="a post")]
    got = bot.same_target_texts(sent, ready, dict(post_id=11, root_post_id=10, author_id=500))
    assert got == ["to 500 in thread 10", "to 501 in thread 10", "waiting, to 500"]
    assert bot.same_target_texts(sent, [], dict(post_id=21, root_post_id=20, author_id=999)) == ["to 502 elsewhere"]


def test_gate_passes_the_same_texts(monkeypatch):
    seen = {}
    monkeypatch.setattr(bot.quality, "check", lambda raw, mode, recent, **kw: (seen.update(kw), (raw, None))[1])
    bot.gate("draft", dict(mode="reply", same_texts=["x"]), "user", [])
    assert seen["same"] == ["x"]
