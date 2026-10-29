"""Today's news in replies (29 Oct, Marc): content/news.toml, salience with decay and the trend, the prompt line."""
import datetime as dt
import pathlib
import random
import sys
import types

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from swan_bot import bot, config, news, quality  # noqa: E402
from swan_bot import facts as fact_store  # noqa: E402

HOUR = 3600


@pytest.fixture(autouse=True)
def _fresh():
    news.reset()
    yield
    news.reset()


def job(body="Not sure how I'll vote on the referendum yet.", **kw):
    return dict(mode="reply", rec=dict(persona="lani"), frame=None, arm=None, wants=[], context=None, read=False,
                meta={}, target=dict(post_id=5, author_id=500, body=body), **kw)


def story(key="s", impact=3, age_h=1.0, keywords=(r"\bsunset\b",), turnout=False, requires=(), now=None):
    now = now or 1_800_000_000
    return dict(key=key, impact=impact, t=now - age_h * HOUR, line="x", reading="y", requires=list(requires),
                turnout=turnout, rx=[news.re.compile(k, news.re.I) for k in keywords])


# ---- the file -------------------------------------------------------------------------------------------------------
def test_every_story_parses_and_rests_on_active_facts():
    stories = news.stories()
    assert stories, "content/news.toml has stories"
    for key, s in stories.items():
        assert s["requires"], f"{key}: names the facts it rests on"
        missing = [k for k in s["requires"] if fact_store.TABLE.get(k, {}).get("status") != "active"]
        assert not missing, f"{key}: rests on facts that are not active: {missing}"


def test_story_text_passes_the_gate_and_names_no_voting_logistics():
    from swan_bot import factdesk
    for key, s in news.stories().items():
        for text in (s["line"], s["reading"]):
            assert quality.unapproved_number(text) is None, (key, text)
            assert factdesk.text_problems(text) == [], (key, text)          # forbidden, wrong claims, logistics...


def test_published_times_are_real_utc_not_the_papers_sydney_stamp():
    for key, s in news.stories().items():
        published = dt.datetime.fromtimestamp(s["t"], dt.timezone.utc)
        assert published < dt.datetime(2026, 11, 3, tzinfo=dt.timezone.utc), key
        assert published.minute == 0 and published.hour in range(24), key


# ---- salience ---------------------------------------------------------------------------------------------------------
def test_salience_halves_by_impact_and_ends_at_max_age():
    now = 1_800_000_000
    big, small = story(impact=3, age_h=30, now=now), story(impact=1, age_h=6, now=now)
    assert news.salience(big, now, n_trend=0) == pytest.approx(news.WEIGHT[3] / 2)
    assert news.salience(small, now, n_trend=0) == pytest.approx(news.WEIGHT[1] / 2)
    assert news.salience(story(impact=1, age_h=24, now=now), now, n_trend=0) < news.salience(
        story(impact=3, age_h=24, now=now), now, n_trend=0) / 5            # a passing item fades, a big story stays
    assert news.salience(story(age_h=news.MAX_AGE_H + 1, now=now), now, n_trend=0) == 0
    assert news.salience(story(age_h=-1, now=now), now, n_trend=0) == 0     # not out yet


def test_a_story_on_a_paused_fact_drops_out(monkeypatch):
    now = 1_800_000_000
    monkeypatch.setattr(fact_store, "ok", lambda keys: "no_end" not in keys)
    assert news.salience(story(requires=["no_end"], now=now), now, n_trend=0) == 0
    assert news.salience(story(requires=["first_doses"], now=now), now, n_trend=0) > 0


def test_what_citizens_talk_about_lifts_a_story_for_six_hours(monkeypatch):
    s = story(keywords=(r"\bsunset\b",))
    monkeypatch.setattr(news, "stories", lambda path=None: {"s": s})
    t0 = 1_800_000_000
    for i in range(news.TREND_CAP):
        news.observe(i, "i want a sunset clause", t0)
    news.observe(0, "i want a sunset clause", t0)                           # the same post once only
    news.observe(999, "the ferry was late again", t0)
    assert news.trend("s", t0) == news.TREND_CAP
    lifted, flat = news.salience(s, t0), news.salience(s, t0, n_trend=0)
    assert lifted == pytest.approx(flat * (1 + news.TREND_GAIN))
    assert news.trend("s", t0 + news.TREND_WINDOW_S + 1) == 0


# ---- the pick -------------------------------------------------------------------------------------------------------
def test_the_pick_favours_the_story_the_post_is_about(monkeypatch):
    now = 1_800_000_000
    poll = story("poll", keywords=(r"\bpoll\b",), now=now)
    sunset = story("sunset", keywords=(r"\bsunset\b",), now=now)
    monkeypatch.setattr(news, "stories", lambda path=None: {"poll": poll, "sunset": sunset})
    rng = random.Random(4)
    picks = [news.pick("I'd vote yes with a sunset clause", now, rng)["key"] for _ in range(600)]
    assert 0.6 < picks.count("sunset") / 600 < 0.73                        # 2:1 by weight
    assert news.pick("anything", now + (news.MAX_AGE_H + 2) * HOUR, rng) is None


def test_a_turnout_reply_prefers_the_turnout_story(monkeypatch):
    now = 1_800_000_000
    monkeypatch.setattr(news, "stories", lambda path=None: {
        "poll": story("poll", turnout=True, keywords=(r"\bpoll\b",), now=now),
        "ids": story("ids", keywords=(r"\bid\b",), now=now)})
    rng = random.Random(5)
    picks = [news.pick("I'm voting No", now, rng, turnout=True)["key"] for _ in range(600)]
    assert picks.count("poll") / 600 > 0.6


# ---- the prompt -----------------------------------------------------------------------------------------------------
def test_a_share_of_replies_and_every_turnout_reply_get_the_line(monkeypatch):
    targeter = types.SimpleNamespace(headline=None)
    monkeypatch.setattr(config, "FLIP_ON", False)                 # a flip takes the news line's place (test_flip.py)
    monkeypatch.setattr(config, "NEWS_ON", True)
    monkeypatch.setattr(config, "NEWS_SHARE", 1.0)
    j = job(body="I'd only vote yes with a sunset clause in it.")
    _, _, user = bot.build_prompt(j, targeter)
    assert "In the news this week:" in user and j["meta"]["news"] in news.stories()
    monkeypatch.setattr(config, "NEWS_SHARE", 0.0)
    j = job()
    assert "In the news this week:" not in bot.build_prompt(j, targeter)[2] and "news" not in j["meta"]
    j = job(group="turnout")                                                 # NEWS_TURNOUT_SHARE: every one
    assert "In the news this week:" in bot.build_prompt(j, targeter)[2]
    monkeypatch.setattr(config, "NEWS_SHARE", 1.0)
    j = job(group="off_topic")                                               # off-topic replies are by group
    assert "In the news this week:" not in bot.build_prompt(j, targeter)[2]  # their topic only
    monkeypatch.setattr(config, "NEWS_ON", False)
    assert "In the news this week:" not in bot.build_prompt(job(group="turnout"), targeter)[2]


def test_the_news_key_is_logged_on_the_write():
    assert "news" in bot.ARMS
