"""Who we reply to: skip citizens who already lean No (echo), keep the Yes-but. Texts are real citizen posts, 20 Oct."""
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


def test_lean_no_is_skipped():
    for text in LEAN_NO:
        assert targeting.classify(text) == (None, None), text


def test_yes_but_is_kept():
    for text in YES_BUT:
        assert targeting.classify(text)[0], text


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


def test_complaints_are_skipped():
    for text in COMPLAINTS:
        assert targeting.classify(text) == (None, None), text


def test_is_citizen():
    from swan_bot import config
    assert not config.is_citizen(3) and not config.is_citizen(None)
    assert config.is_citizen(12) and config.is_citizen(config.CITIZEN_MAX_ID)
    assert not config.is_citizen(config.CITIZEN_MAX_ID + 1)


class _Page(list):
    def __init__(self, items, next_cursor):
        super().__init__(items)
        self.next_cursor = next_cursor


class _Feed:
    """Latest as 100-post pages, newest first; counts the reads."""
    def __init__(self, newest, remaining=10):
        self.newest, self.reads, self.rate_limit = newest, 0, type("RL", (), {"remaining": remaining})()

    def feed_latest(self, limit=100, cursor=None):
        self.reads += 1
        top = cursor or self.newest
        return _Page([{"post_id": i} for i in range(top, top - limit, -1)], top - limit)


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
    t.undecided = lambda aid: True
    t.candidates = {1: dict(post=dict(post_id=1, author_id=100, created_at=ago(120)), score=6.0),
                    2: dict(post=dict(post_id=2, author_id=101, created_at=ago(3)), score=4.0)}
    assert t.next_target(set(), set(), {})["post"]["post_id"] == 2, "the author of the 3-min-old post may be online"
    assert t.next_target(set(), set(), {})["post"]["post_id"] == 1
