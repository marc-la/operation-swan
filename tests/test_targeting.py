"""Who we reply to (todo/21): every citizen item on the vote, the keyword read sets the priority. Texts are real
citizen posts, 20-21 Oct."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from swan_bot import targeting  # noqa: E402

LEAN_NO = [
    "Leaning No at the moment. I'd be more comfortable with a narrow venue list, testing options and a real sunset clause.",
    "My No vote is settled, and I'm vaccinated. Is there a review date anywhere?",
    "exactly. once they set the precedent of checking papers at every door, it's a slippery slope for all kinda data sharing.",
    "Why should my day be gated by a vaccine I don't trust? Protect the hospitals, fix the system, not bar people from daily life.",
]
YES_BUT = [
    "I'm leaning Yes because we can't risk the hospitals being hit like they were during COVID, but they need to say "
    "which public spaces are on the list.",
    "Totally get your concern. If we vote Yes, there must be a published list of designated spaces, a clear expiry, "
    "and an independent review.",
    "I want H2D2 vaccination to protect people, especially the vulnerable, but I'm uneasy voting on a rule with venues "
    "and review dates still unclear.",
]


def test_lean_no_reads_low_but_is_not_skipped():
    for text in LEAN_NO:
        assert targeting.target_class(text) == "lean_no", text
        assert targeting.hard_skip(text) is None, text


def test_yes_but_is_kept():
    for text in YES_BUT:
        assert targeting.classify(text)[0], text
        assert targeting.READ_PRIORITY[targeting.target_class(text)] == 3.0, text


# Citizens who name their conditions with no hedge word (real citizen posts, 20-21 Oct): the Yes-but we want.
CONDITIONS = [
    "Publish the venue list now, with a clear sunset; keep door checks simple and privacy-friendly, with transparent "
    "exemptions.",
    "i want a hard end date tied to measurable data with transparent venues and real exemptions so we can keep people "
    "safe without forever screening",
    "An independent medical exemption process and a legally binding review period would make me feel much more secure "
    "about it.",
    "People deserve to know where this would apply before voting yes; publish the spaces list now, define medical "
    "exemptions clearly, and set a firm sunset so we can review.",
]
# ...and No-leaning complaints about the same things: echo, not persuasion.
COMPLAINTS = [
    "There's no end date. This will be permanent and they know it.",
    "No sunset clause, no list, no thanks.",
    "Forever papers at every door. That's the new normal they want.",
]


def test_conditions_are_kept():
    for text in CONDITIONS:
        assert targeting.classify(text)[0], text


def test_complaints_read_as_lean_no():
    for text in COMPLAINTS:
        assert targeting.target_class(text, context="Referendum: what the vaccination question says") == "lean_no", text


# 27 Oct audit (real citizen posts): conditions said flatly were read as lean_no and got priority 0 and the turnout line.
FLAT_CONDITIONS = [
    "A full list of venues, date-stamped limits, and clear exemptions. That's the bare minimum.",
    "End date and oversight in regs, venue list out now so folks know what counts.",
    "id want a full list of designated spaces and a legal sunset clause so this doesn't just become a permanent thing",
    "Yeah, a fixed review date would be much better than just leaving it to chance. It gives people some actual certainty.",
]
# Yes voters whose post has a No-ish phrase in it ("a No vote", "slippery slopes")
YES_WITH_NO_WORDS = [
    "Ofa, the venue list should be published before polling day, no argument. But a No vote leaves us with no access rule "
    "at all while H2D2 gets closer. I'm still voting YES; spell out the venues.",
    "Everyone's arguing about certificates and slippery slopes. If H2D2 overwhelms our hospitals, the rest of life goes with "
    "them. I'm voting Yes.",
]
# On the vote without a REFERENDUM word: skipped as off topic before 27 Oct
ON_VOTE_TEXTS = [
    "i havent seen a full rules list published yet and thats exactly what is holding me back",
    "i'd give it a six month expiry and require a public review before the assembly can renew it",
    "Tavita, I'd want to see a complete freeze on any new regulatory powers for a decade after this.",
    "honestly id want it to be an independent body so the politicians cant just mess with it for votes!!",
    "I could still be persuaded, but I need to know what the pass means for everyday life before I mark that box.",
]
SMALL_TALK = [
    "Usually Monday, getting tools and gear sorted before heading out to the first job. How about you, Kiri?",
    "mostly just the wind making it hard to breathe really",
    "thanks flora it was a bit of a struggle but worth it",
    "Grabbed a pie and a cold drink at the roadside shop after work. Nothing fancy, but it hit the spot.",
    "spent half the morning chasing a bug that turned out to be a timezone setting  at least it wasnt the internet this time",
    "oof 0300 is crazy!! stay safe out there",
]


def test_flat_conditions_are_swing_not_lean_no():
    for text in FLAT_CONDITIONS:
        assert targeting.target_class(text, context="Referendum: the vaccination question") == "conditions_flat", text
        assert targeting.READ_PRIORITY["conditions_flat"] == 3.0


def test_a_stated_yes_is_never_lean_no():
    for text in YES_WITH_NO_WORDS:
        assert targeting.target_class(text) not in ("lean_no", "conditions_flat"), text
    assert targeting.target_class(YES_WITH_NO_WORDS[1]) == "firm_yes"
    assert not targeting.yes_stated("I won't be voting yes on this.")
    assert targeting.target_class("I won't be voting yes on this.") == "lean_no"
    # someone else's Yes is not theirs, and an explicit vote No always stands
    no = ("I want H2D2 vaccination free and easy to get, but I'm voting NO on a public-space pass. To friends voting YES: "
          "protecting people matters, but a pass won't staff a ward.")
    assert targeting.target_class(no) == "lean_no"
    assert not targeting.yes_stated("We need concrete guardrails before ticking Yes: publish the end date.")


def test_on_vote_words_are_not_off_topic_and_small_talk_still_is():
    for text in ON_VOTE_TEXTS:
        assert targeting.hard_skip(text) is None, text
        assert targeting.target_class(text) != "off_topic", text
    for text in SMALL_TALK:
        assert targeting.hard_skip(text) == "off_topic", text


def test_follow_up_labels_keep_the_old_vocabulary():
    assert targeting.stance(ON_VOTE_TEXTS[0]) is None              # labels compare across days
    assert targeting.stance(ON_VOTE_TEXTS[0], wide=True) is not None


def test_is_citizen():
    from swan_bot import config
    assert not config.is_citizen(3) and not config.is_citizen(None)
    assert config.is_citizen(12) and config.is_citizen(config.CITIZEN_MAX_ID)
    assert not config.is_citizen(config.CITIZEN_MAX_ID + 1)


class _Page(list):
    def __init__(self, items, next_cursor):
        super().__init__(items)
        self.next_cursor = next_cursor


NOW = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()


class _Feed:
    """Latest as 100-post pages, newest first (team-bot ids, so no citizen funnel); counts the reads."""
    def __init__(self, newest, remaining=10):
        self.newest, self.reads, self.rate_limit = newest, 0, type("RL", (), {"remaining": remaining})()

    def feed_latest(self, limit=100, cursor=None):
        self.reads += 1
        top = cursor or self.newest
        return _Page([{"post_id": i, "author_id": 9000, "created_at": NOW} for i in range(top, top - limit, -1)],
                     top - limit)


def test_latest_pages_back_to_the_last_post_seen():
    feed = _Feed(newest=10_000)
    t = targeting.Targeter(feed)
    assert len(t._latest()["posts"]) == 100 and feed.reads == 1       # first refresh: one page
    feed.newest = 10_250                                                # 250 new posts since
    got = t._latest()
    assert len(got["posts"]) == 250 and feed.reads == 4 and not got["gap"]
    assert t.latest_seen == 10_250


def test_latest_stops_at_the_page_cap_and_the_feed_budget():
    feed = _Feed(newest=10_000)
    t = targeting.Targeter(feed)
    t._latest()
    feed.newest = 20_000
    got = t._latest()
    assert got["gap"] and got["pages"] == targeting.config.LATEST_PAGES
    feed.newest, feed.rate_limit.remaining = 30_000, targeting.config.FEED_READS_SPARE
    got = t._latest()
    assert got["gap"] and got["pages"] == 1


def test_yes_reason_is_spotted():
    assert targeting.YES_REASON.search(YES_BUT[0]) and targeting.YES_REASON.search(YES_BUT[2])
    assert not targeting.YES_REASON.search(YES_BUT[1])


def test_a_fresh_post_goes_first():
    import datetime as dt
    ago = lambda m: (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=m)).isoformat()
    t = targeting.Targeter(None, log=lambda r: None)
    t.candidates = {1: dict(post=dict(post_id=1, author_id=100, created_at=ago(120)), score=6.0),
                    2: dict(post=dict(post_id=2, author_id=101, created_at=ago(3)), score=4.0)}
    assert t.next_target(set(), set(), {})["post"]["post_id"] == 2, "the author of the 3-min-old post may be online"
    assert t.next_target(set(), set(), {})["post"]["post_id"] == 1


def test_a_stretch_left_unread_is_read_next_time():
    """G2: stopping at the page cap keeps the rest as a band; the next refresh reads it down to the old stop."""
    feed = _Feed(newest=10_000)
    t = targeting.Targeter(feed, log=lambda r: None)
    t._latest()
    feed.newest = 10_500                                                # 500 new: 3 pages read, 200 left
    first = t._latest()
    assert first["pages"] == targeting.config.LATEST_PAGES and len(t.bands) == 1
    second = t._latest()                                                # nothing new on top: the band
    ids = {p["post_id"] for p in first["posts"] + second["posts"]}
    assert ids == set(range(10_001, 10_501)) and not t.bands, "every post between the two reads, once"


def test_read_position_queue_and_funnel_survive_a_restart():
    """G3: dump() goes into swan_state.json; load() on start resumes from it."""
    t = targeting.Targeter(_Feed(newest=10_000), log=lambda r: None)
    t.latest_seen, t.bands = 10_000, [["cur", 9_000]]
    post = dict(post_id=5, author_id=100, created_at=NOW, body="not sure about the referendum, i'd need a sunset date")
    t._consider(post, "latest")
    assert 5 in t.candidates
    import json
    u = targeting.Targeter(_Feed(newest=10_000), log=lambda r: None)
    u.load(json.loads(json.dumps(t.dump())))
    assert (u.latest_seen, u.bands, list(u.candidates)) == (10_000, [["cur", 9_000]], [5])
    assert u.items[5]["o"] == "pending"


def test_every_citizen_item_ends_somewhere(monkeypatch):
    """G12: seen = answered + skipped + lost + pending, per hour; skips are logged with their reason."""
    monkeypatch.setattr(targeting.config, "OFF_TOPIC_ARM", False)     # todo/23 C would queue the lunch post
    logged = []
    t = targeting.Targeter(None, log=logged.append)
    posts = [dict(post_id=1, author_id=100, created_at=NOW, body="what's for lunch"),
             dict(post_id=2, author_id=101, created_at=NOW, body="leaning yes on the referendum but only with a sunset"),
             dict(post_id=3, author_id=102, created_at=NOW, body="the referendum needs a published venue list, i'd want that"),
             dict(post_id=4, author_id=99_999, created_at=NOW, body="a team bot on the referendum")]
    for p in posts:
        t._consider(p, "latest")
    c = t.next_target(set(), {3}, {})
    t.answered(c["post"], "reply")
    assert t.next_target(set(), {3}, {}) is None
    (f,) = t.funnel().values()
    assert f["seen"] == 3 and f["answered"] == 1, "the team bot is not a citizen item"
    assert f["skipped"] == {"off_topic": 1, "replied": 1} and not f["lost"] and not f["pending"]
    assert {r["why"] for r in logged if r["act"] == "skip"} == {"off_topic", "replied"}


def test_requeued_candidate_backs_off_then_comes_back():
    t = targeting.Targeter(None, log=lambda r: None)
    t._consider(dict(post_id=7, author_id=100, created_at=NOW, body="not sure on the referendum, need a sunset"), "news")
    c = t.next_target(set(), set(), {})
    t.requeue(c, "draft_failed")
    assert t.next_target(set(), set(), {}) is None and t.items[7]["why"] == "draft_failed"
    t.candidates[7]["not_before"] = 0
    assert t.next_target(set(), set(), {})["post"]["post_id"] == 7


def ago(minutes):
    import datetime as dt
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes)).isoformat()


class _Posts:
    """get_post from a dict; a RateLimited stand-in for ids in `limited`."""
    def __init__(self, posts, limited=()):
        self.posts, self.limited, self.rate_limit = posts, set(limited), None

    def get_post(self, pid):
        if pid in self.limited:
            raise targeting.ctn.RateLimited("GET", "/posts", 429, "slow down", 5)
        return self.posts[pid]


def quiet(social=None):
    return targeting.Targeter(social, log=lambda r: None)


def test_a_post_with_no_frame_is_kept():
    t = quiet()
    t._consider(dict(post_id=1, author_id=100, created_at=ago(2), body="Honestly what is this referendum even for"),
                "latest")
    c = t.next_target(set(), set(), {})
    assert c and c["frame"] is None and c["target_class"] == "unclear"


def test_a_citizen_reply_from_latest_gets_its_parent_as_context():
    parent = dict(post_id=50, author_id=9_000, created_at=ago(30), body="The vaccination certificate vote is a blank cheque")
    t = quiet(_Posts({50: parent}))
    t._consider(dict(post_id=51, author_id=100, created_at=ago(1), body="exactly, that's my worry too",
                     reply_to_post_id=50, root_post_id=50), "latest")
    c = t.candidates[51]
    assert c["context"].startswith("The vaccination certificate") and c["parent_author"] == 9_000


def test_a_reply_to_one_of_us_goes_to_the_reply_back_path():
    parent = dict(post_id=50, author_id=777, created_at=ago(30), body="Vote No on the certificate")
    t = quiet(_Posts({50: parent}))
    t._consider(dict(post_id=51, author_id=100, created_at=ago(1), body="why though?", reply_to_post_id=50,
                     root_post_id=50), "latest")
    assert t.next_target({777}, set(), {}) is None and t.items[51]["why"] == "reply_back"
    t.answered(dict(post_id=51, author_id=100), "reply_back")
    assert t.items[51]["o"] == "answered"


def test_deep_threads_are_skipped():
    chain = {i: dict(post_id=i, author_id=9_000, created_at=ago(60), body="the referendum", root_post_id=1,
                     reply_to_post_id=i - 1 if i > 1 else None) for i in range(1, 12)}
    t = quiet(_Posts(chain))
    t._consider(dict(post_id=20, author_id=100, created_at=ago(1), body="i'm not sure about the vote", root_post_id=1,
                     reply_to_post_id=11), "latest")
    assert 20 not in t.candidates and t.items[20] | {} and t.items[20]["why"] == "deep_thread"
    t._consider(dict(post_id=21, author_id=101, created_at=ago(1), body="i'm not sure about the vote", root_post_id=1,
                     reply_to_post_id=3), "latest")
    assert 21 in t.candidates


def test_an_item_the_rate_limit_stopped_is_judged_later():
    t = quiet(_Posts({50: dict(post_id=50, author_id=9_000, created_at=ago(9), body="the referendum")}, limited={50}))
    post = dict(post_id=51, author_id=100, created_at=ago(1), body="agree", reply_to_post_id=50, root_post_id=50)
    t._consider(post, "latest")
    assert 51 not in t.candidates and t.items[51]["why"] == "unjudged" and 51 in t.unjudged
    t.social.limited.clear()
    for post, source, context in list(t.unjudged.values()):
        t._consider(post, source, context)
    assert 51 in t.candidates and not t.unjudged


def test_a_repeat_author_is_answered_on_a_new_post():
    """No 72 h per-author cooldown: a citizen we answered days ago is answered again."""
    t = quiet()
    contacted = {}
    targeting.contact(contacted, 100, "mere", t=0)                     # long ago
    t._consider(dict(post_id=2, author_id=100, created_at=ago(1), body="still not sure about this referendum"), "latest")
    assert t.next_target(set(), {1}, targeting.sessions(contacted))["post"]["post_id"] == 2


def test_the_session_cap_holds():
    t = quiet()
    contacted = {}
    targeting.contact(contacted, 100, "mere")
    targeting.contact(contacted, 100, "dan")
    t._consider(dict(post_id=3, author_id=100, created_at=ago(1), body="still not sure about this referendum"), "latest")
    assert t.next_target(set(), set(), targeting.sessions(contacted)) is None
    assert 3 in t.candidates and t.items[3]["why"] == "session_cap", "it waits; it isn't dropped"
    one = {}
    targeting.contact(one, 100, "mere")
    assert t.next_target(set(), set(), targeting.sessions(one))["post"]["post_id"] == 3, "one voice so far: a second may"


def test_old_contacted_format_still_reads():
    import time
    assert targeting.sessions({"100": time.time() - 60, "101": time.time() - 72 * 3600}) == {"100": {None}}


def test_firm_yes_only_under_the_flag(monkeypatch):
    body = "Voting yes on the referendum. #VoteYes"
    monkeypatch.setattr(targeting.config, "FIRM_YES_ARM", False)
    t = quiet()
    t._consider(dict(post_id=4, author_id=100, created_at=ago(1), body=body), "latest")
    assert 4 not in t.candidates and t.items[4]["why"] == "firm_yes"
    monkeypatch.setattr(targeting.config, "FIRM_YES_ARM", True)
    monkeypatch.setattr(targeting.config, "FIRM_YES_PER_H", 1)
    t = quiet()
    for pid in (4, 5):
        t._consider(dict(post_id=pid, author_id=100 + pid, created_at=ago(1), body=body), "latest")
    c = t.next_target(set(), set(), {})
    assert c["arm"] == "firm_yes" and c["target_class"] == "firm_yes"
    assert t.next_target(set(), set(), {}) is None, "one an hour"


def test_priority_follows_the_read():
    t = quiet()
    t._consider(dict(post_id=6, author_id=106, created_at=ago(60), body="My No vote is settled. Referendum? No thanks."),
                "latest")
    t._consider(dict(post_id=7, author_id=107, created_at=ago(60),
                     body="leaning yes on the referendum but only with a sunset clause"), "latest")
    assert t.next_target(set(), set(), {})["post"]["post_id"] == 7
    assert t.next_target(set(), set(), {}, engaged={"106"})["engaged"]


def test_hostile_is_skipped():
    t = quiet()
    t._consider(dict(post_id=8, author_id=108, created_at=ago(1), body="KITB sheep, the referendum is for resort profits"),
                "latest")
    assert t.items[8]["why"] == "hostile" and 8 not in t.candidates


def test_extra_citizen_ranges(monkeypatch):
    from swan_bot import config
    assert not config.is_citizen(10_500)
    monkeypatch.setattr(config, "EXTRA_CITIZEN_RANGES", [(10_400, 10_600)])
    assert config.is_citizen(10_500) and not config.is_citizen(10_601) and config.is_citizen(500)


def test_citizen_watch_flags_a_long_steady_run_and_not_bursts():
    import datetime as dt
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
    import citizen_watch as cw
    t0 = dt.datetime(2026, 10, 25, tzinfo=dt.timezone.utc)
    at = lambda s: (t0 + dt.timedelta(seconds=s)).isoformat()
    base = cw.REVIEWED_TO + 100
    steady = [dict(account_id=base + i, created_at=at(30 * i + (i % 3) * 5)) for i in range(cw.RUN + 5)]
    bursts = [dict(account_id=base + 1000 + i, created_at=at(5000 + (i // 10) * 600 + (i % 10) * 3))
              for i in range(cw.RUN + 5)]
    found = cw.suspect_runs(steady + bursts, ours=set())
    assert [r[:2] for r in found] == [(base, base + cw.RUN + 4)]
    assert cw.suspect_runs(steady, ours={base + 7}) == [], "one of ours inside: not a citizen run"
    assert cw.suspect_runs([dict(a, account_id=a["account_id"] - 200) for a in steady
                            if a["account_id"] - 200 <= cw.REVIEWED_TO], set()) == []


def test_oldest_pending_counts_from_when_we_found_it_and_skips_deliberate_waits():
    """todo/22 status.json: oldest_queued_s is time since an item entered our queue, not since the citizen wrote it;
    items waiting on purpose (session cap, firm-Yes cap, the reply-back path) don't count."""
    import time as _time
    t = targeting.Targeter(social=None, log=lambda rec: None)
    now = _time.time()
    t.items = {1: dict(h="x", c=now - 3600, f=now - 60, o="pending", why="queued", src="news", reply=True),
               2: dict(h="x", c=now - 7200, f=now - 900, o="pending", why="session_cap", src="news", reply=True),
               3: dict(h="x", c=now - 9000, f=now - 9000, o="answered", why="reply", src="latest", reply=False),
               4: dict(h="x", c=now - 5000, f=now - 5000, o="pending", why="queued", src="sweep", reply=False,
                       g="sweep")}                                  # todo/23: old by design
    written, queued = t.oldest_pending()
    assert 7190 <= written <= 7210 and 55 <= queued <= 65, (written, queued)
    t.items = {}
    assert t.oldest_pending() == (None, None)


def test_a_comment_of_only_warmth_is_off_topic_even_in_a_thread_about_the_vote():
    ctx = "Referendum: what the vaccination question says"
    mavis = "That is so incredibly kind of you to do, Mavis. Sending so much love to you and the hospital staff! ❤️"
    assert targeting.target_class(mavis, context=ctx) == "off_topic"
    assert targeting.target_class("I am so incredibly sorry for your loss, Marcus.", context=ctx) == "off_topic"
    # an argument, or the vote, in the same comment keeps its class
    assert targeting.target_class("So sorry for your loss, but the hospitals were swamped last time.", context=ctx) != "off_topic"
    assert targeting.target_class("Exactly, the wards are full.", context=ctx) != "off_topic"
