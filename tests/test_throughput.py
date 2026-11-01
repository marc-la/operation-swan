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


def test_header_gap_uses_the_whole_budget_with_the_swarm_off():
    assert config.WRITE_MARGIN == 0 and config.SWARM_REPOSTS_PER_SCAN == 0
    assert bot.header_gap(None) == 0.0, "no headers: the pace gap alone"
    assert bot.header_gap(RL(3, 2, 20)) == 0.0, "2 left: write"
    assert bot.header_gap(RL(3, 1, 40)) == 0.0, "1 left: our next write takes it (it was 20 s with a margin of 1)"
    assert abs(bot.header_gap(RL(3, 0, 60)) - 20) < 1e-9, "0 left: wait one refill (reset / missing)"
    assert abs(bot.header_gap(RL(3, 0, 60), margin=1) - 40) < 1e-9, "a margin of 1 still keeps one write back for the swarm"
    assert abs(bot.header_gap(RL(6, 0, 50), margin=1) - 16.6666666) < 1e-5, "a scaled limit is read from the headers, not assumed"


def test_write_gap_is_the_larger_and_never_past_the_limit(monkeypatch):
    monkeypatch.setattr(bot.random, "uniform", lambda a, b: (a + b) / 2)
    assert abs(bot.pace_gap(2.9) - 60 / 2.9) < 1e-9, "mean jitter 1.0: aims at per_min"
    assert bot.write_gap(RL(3, 2, 20), 2.9) == bot.pace_gap(2.9)
    assert bot.write_gap(RL(3, 0, 60), 2.9) == max(bot.pace_gap(2.9), 20.0), "0 left: one refill (20 s), or the pace gap if longer"
    assert config.MAX_PER_MIN <= 3.0, "the rules' team limit (posts + replies + reposts)"


def _simulate(per_min, swarm_every=None):
    """The bucket (3 a minute, refilling one every 20 s) with our writer and, if swarm_every, a swarm repost every
    swarm_every s that goes while >= 1 is left. Returns (our writes a minute, swarm reposts tried, swarm reposts sent);
    the bucket never goes below 0 for our writes (no 429)."""
    import random
    random.seed(4)
    limit, refill = 3, 20.0
    tokens, t, nxt, ours, swarm_ok, swarm_try = 3.0, 0.0, 0.0, 0, 0, 0
    rl = None
    step = 0.5
    while t < 3600:
        tokens = min(limit, tokens + step / refill)
        if swarm_every and t % swarm_every < step and t > 0:               # the swarm's run: one repost when a write is left
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
            nxt = t + bot.write_gap(rl, per_min)
        t += step
    return ours / 60, swarm_try, swarm_ok


def test_steady_state_rate_with_the_swarm(monkeypatch):
    """With a margin of 1 (the swarm on): our pace stays 2.6+/min, no 429, and every swarm repost finds a write left."""
    monkeypatch.setattr(config, "WRITE_MARGIN", 1)
    rate, tried, sent = _simulate(2.9, swarm_every=300)
    assert rate >= 2.6, rate
    assert sent == tried


def test_steady_state_rate_with_the_swarm_off():
    """The 25 Oct setting (margin 0, --per-min 3.0, no reposts): no 429, and about 2.9 a minute, up from 2.85 (170-174
    an hour live) with a margin of 1 and per-min 2.9."""
    rate, _, _ = _simulate(3.0)
    assert rate >= 2.9, rate


# ---- 1 Nov (Marc): the next slot from the slot just used (bot.next_slot) ---------------------------------------------
def test_next_slot_counts_from_the_slot_not_the_send(monkeypatch):
    monkeypatch.setattr(bot.random, "uniform", lambda a, b: (a + b) / 2)       # pace gap 20 s at 3.0
    ok = RL(3, 2, 20)
    assert bot.next_slot(100.0, 100.8, ok, 3.0) == 120.0, "the 0.8 s at the slot and in the send are not added"
    assert bot.next_slot(100.0, 160.0, ok, 3.0) == 160.0 - config.WRITE_CATCHUP_S + 20, "an old slot: from now - catch-up"
    assert bot.next_slot(0.0, 50.0, ok, 3.0) == 50.0 - config.WRITE_CATCHUP_S + 20, "the first write after a start"
    assert bot.next_slot(100.0, 100.8, RL(3, 0, 60), 3.0) == 120.8, "0 left: the headers' 20 s from now"
    monkeypatch.setattr(config, "WRITE_CATCHUP_S", 0)
    assert bot.next_slot(100.0, 100.8, ok, 3.0) == 100.8 + bot.write_gap(ok, 3.0), "catch-up 0: from the send, as before"


def _simulate_slots(slot_fn, delay, hours=4):
    """Continuous time: the bucket (3, one back every 20 s; headers as the server gives them: whole writes left and the
    seconds until whole, rounded) and a writer whose sends leave delay(rng) s after their slot (live 31 Oct-1 Nov: the
    state save at the slot, ~0.45 s and sometimes twice, and 3% late drafts) and return 0.3 s later, when slot_fn(slot,
    now, rl) sets the next slot. Returns (writes a minute, sends the bucket would have refused with a 429)."""
    import random
    random.seed(4)
    rng = random.Random(11)
    limit, refill, http = 3, 20.0, 0.3
    tokens, last, slot, back, n, refused = 3.0, 0.0, 0.0, 0.0, 0, 0
    while True:
        sent = max(slot, back) + delay(rng)
        if sent > hours * 3600:
            return n / (hours * 60), refused
        tokens, last = min(limit, tokens + (sent - last) / refill), sent
        if tokens < 1:
            refused += 1
        else:
            tokens, n = tokens - 1, n + 1
        back = sent + http
        slot = slot_fn(slot, back, RL(limit, int(tokens), round((limit - tokens) * refill)))


def _live_delay(rng):
    return 0.45 + (0.45 if rng.random() < 0.4 else 0) + (rng.uniform(1, 8) if rng.random() < 0.03 else 0)


def test_slots_from_the_slot_reach_the_limit_without_a_429():
    """The live delays cost ~4% at 3.0 counted from the send (2.85-2.87 a minute: 171-172 an hour, as live 31 Oct-1 Nov);
    counted from the slot they cost nothing, and the headers still keep every send inside the bucket."""
    old, old_refused = _simulate_slots(lambda slot, now, rl: now + bot.write_gap(rl, 3.0), _live_delay)
    new, new_refused = _simulate_slots(lambda slot, now, rl: bot.next_slot(slot, now, rl, 3.0), _live_delay)
    assert old < 2.90 and new >= 2.97, (old, new)
    assert old_refused == new_refused == 0
    still, refused = _simulate_slots(lambda slot, now, rl: bot.next_slot(slot, now, rl, 3.0), lambda rng: 0.0)
    assert still >= 2.97 and refused == 0, (still, refused)




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


def test_latest_every_5_s_but_the_papers_and_journalists_every_15_s(monkeypatch, tmp_path):
    """todo/58 (31 Oct): REFRESH_S 5 reads Latest every refresh; the papers' and journalists' account_posts stay every
    ACCOUNT_READS_S (15 s), so the faster Latest read doesn't triple them."""
    from swan_bot import feeds
    from test_targeting import _Page
    assert config.REFRESH_S == 5 and config.ACCOUNT_READS_S == 15 and config.TRENDING_EVERY == 9
    monkeypatch.setattr(feeds, "FEED_LOG", tmp_path / "feed_reads.jsonl")
    calls = []

    class Social:
        rate_limit = None

        def account_posts(self, aid, limit=50, cursor=None):
            calls.append(("account_posts", aid))
            return _Page([], None)

        def __getattr__(self, name):
            def read(*a, **kw):
                calls.append((name,))
                return _Page([], None)
            return read

    t = targeting.Targeter(Social(), log=lambda r: None)
    clock = [1_000_000.0]
    monkeypatch.setattr(targeting.time, "time", lambda: clock[0])
    for _ in range(6):                                             # 30 s of 5 s refreshes
        t.refresh(force=True)
        clock[0] += config.REFRESH_S
    accounts = [c for c in calls if c[0] == "account_posts"]
    assert len(accounts) == 2 * (len(config.NEWS_IDS) + len(config.JOURNALIST_IDS)), "at 0 s and 15 s only"
    assert sum(1 for c in calls if c[0] == "feed_latest") == 6, "Latest every refresh"
