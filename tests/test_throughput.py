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
CLOSE = ("The question has no end date and no review, so the list they draw up after the ballot is there for good. "
         "I'm voting No on it.")
# todo/27: 0.32 to OURS, under todo/24's 0.4 across citizens, now caught at 0.3
OLD_BAND = ("The question has no end date and no review, so the list they write after the ballot is there for good. "
            "I'm voting No on it.")


def test_near_duplicate_thresholds():
    from swan_bot import quality
    sim = quality.similar(CLOSE, OURS)
    assert quality.NEAR_DUP_SAME < sim <= quality.NEAR_DUP_OTHER, sim
    assert not quality.near_duplicate(CLOSE, "reply", recent_texts=[OURS]), "another citizen: loose"
    assert quality.near_duplicate(CLOSE, "reply", recent_texts=[OURS], same=[OURS]), "same citizen or thread: strict"
    assert quality.near_duplicate(CLOSE, "post", recent_texts=[OURS]), "posts stay strict against everything"
    assert quality.near_duplicate(OURS, "reply", recent_texts=[OURS]), "a copy is caught everywhere"
    assert 0.3 < quality.similar(OLD_BAND, OURS) <= 0.4
    assert quality.near_duplicate(OLD_BAND, "reply", recent_texts=[OURS]), "todo/27: 0.3 across citizens"


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


# ---- 5. no Latest band dropped at peak ------------------------------------------------------------------------------
def test_peak_bands_are_kept_and_read_back(monkeypatch, tmp_path):
    """21 Oct 23:40-23:52 UTC: one page a refresh (feed budget at the spare), > 100 new posts each time, 6 bands in
    12 min and 3 dropped. Now an hour of that keeps every band, and off-peak reads them all back, each post once."""
    from swan_bot import feeds
    from test_targeting import _Feed
    monkeypatch.setattr(feeds, "FEED_LOG", tmp_path / "feed_reads.jsonl")
    lost = []
    feed = _Feed(newest=10_000)
    t = targeting.Targeter(feed, log=lambda r: lost.append(r) if r.get("act") == "lost" else None)
    seen = [p["post_id"] for p in t._latest()["posts"]]
    feed.rate_limit.remaining = config.FEED_READS_SPARE           # peak: one page, then the spare is reached
    for _ in range(30):                                            # an hour of 2-min refreshes at 130 posts each
        feed.newest += 130
        seen += [p["post_id"] for p in t._latest()["posts"]]
    assert len(t.bands) == 30 and not lost
    feed.rate_limit.remaining = 10                                 # off-peak
    for _ in range(40):
        seen += [p["post_id"] for p in t._latest()["posts"]]
        if not t.bands:
            break
    assert not t.bands and not lost
    assert sorted(seen) == list(range(9_901, feed.newest + 1)), "every post read once"


# ---- 6. lighter refresh: news threads every 30 min, the papers' headlines every refresh -----------------------------
def test_news_threads_every_30_min(monkeypatch, tmp_path):
    from swan_bot import feeds
    monkeypatch.setattr(config, "REFRESH_S", 120)       # the test steps a clock in 2 min refreshes; the live value is 30 s since 25 Oct
    monkeypatch.setattr(config, "NEWS_THREADS_S", 30 * 60)   # live 10 min since 25 Oct (todo/46); the test is written for 30
    from test_targeting import _Page
    monkeypatch.setattr(feeds, "FEED_LOG", tmp_path / "feed_reads.jsonl")
    calls = []

    class Social:
        rate_limit = None

        def account_posts(self, aid, limit=50, cursor=None):
            calls.append(("account_posts", aid))
            if aid not in config.NEWS_IDS:
                return _Page([], None)
            return _Page([dict(post_id=aid * 100, author_id=aid, created_at=ago(30), kind="post",
                               body="Referendum: what the vaccination pass question means for venues")], None)

        def replies(self, post_id, limit=50, cursor=None):
            calls.append(("replies", post_id))
            return _Page([], None)

        def __getattr__(self, name):
            return lambda *a, **kw: _Page([], None)

    logged = []
    t = targeting.Targeter(Social(), log=logged.append)
    clock = [1_000_000.0]
    monkeypatch.setattr(targeting.time, "time", lambda: clock[0])
    for _ in range(16):                                            # 32 min of 2-min refreshes
        t.refresh(force=True)
        clock[0] += config.REFRESH_S
    news_replies = [c for c in calls if c[0] == "replies" and c[1] in (100, 200)]
    papers = [c for c in calls if c[0] == "account_posts" and c[1] in config.NEWS_IDS]
    assert len(papers) == 16 * len(config.NEWS_IDS), "the headlines every refresh (pulse, persona posts)"
    assert len(news_replies) == 2 * len(config.NEWS_IDS), "the threads at 0 and 30 min"
    assert t.headline.startswith("Referendum")
    refreshes = [r for r in logged if r.get("act") == "refresh"]
    assert [r["news_threads_read"] for r in refreshes].count(True) == 2
