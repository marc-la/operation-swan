"""scripts/news_story.py (todo/52 WS5): a news.toml block drafted from one article and run through the news file tests."""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import news_story  # noqa: E402
from swan_bot import news  # noqa: E402

SITE, SLUG = "daily-kingstonia", "close-contacts-of-first-h2d2-case-test-negative"       # no_spread's source
ARTICLE = dict(title="Close contacts of first H2D2 case test negative", published_at="2026-10-26T12:30:00Z",
               summary="Health officials say every identified contact of the traveller has returned a negative test.",
               body="All close contacts of the country's first H2D2 case have tested negative.")


@pytest.fixture(autouse=True)
def _fresh():
    news.reset()
    yield
    news.reset()


def test_the_papers_sydney_stamp_becomes_real_utc_on_the_hour():
    assert news_story.utc_published("2026-10-29T18:00:00Z") == "2026-10-29T07:00:00Z"
    assert news_story.utc_published("2026-10-30T16:30:00Z") == "2026-10-30T05:00:00Z"


def test_key_impact_and_keywords_from_the_headline():
    slug = "cyclone-watch-issued-for-outer-islands-as-ferry-operators-review-services"
    assert news_story.key_of(slug) == "cyclone_watch_issued_outer" and len(news_story.key_of(slug * 3)) <= 31
    assert news_story.impact_guess("Yes lead narrows as undecided voters remain decisive") == 3
    assert news_story.impact_guess("Electoral Commission discloses K$1.6 million in referendum campaign spending") == 2
    assert news_story.impact_guess("Cyclone watch issued for outer islands") == 1
    assert news_story.keywords_of("Cyclone watch issued for outer islands")[:2] == [r"\bcyclo", r"\bislan"]
    kw = news_story.keywords_of("Electoral Commission discloses K$1.6 million in referendum campaign spending")
    assert not any("referend" in k or "campai" in k for k in kw) and r"\bcommissi" in kw     # not words every post has


def test_a_draft_rests_on_the_article_s_facts_and_waits_for_its_words():
    text, notes = news_story.draft(ARTICLE, SITE, SLUG)
    assert "no_spread" in notes["from_article"] and "published = 2026-10-26T01:00:00Z" in text
    assert news.parse(text.replace(news_story.TODO, "x"))
    assert any("still TODO" in f for f in news_story.run_news_tests(text))


def test_a_good_block_passes_the_news_tests_and_the_file_is_untouched():
    before = news.FILE.read_text()
    text, _ = news_story.draft(ARTICLE, SITE, SLUG, line="Every close contact of the first case has now tested negative.",
                               reading="Testing and tracing caught it early, and none of that needed a pass at anyone's door.",
                               requires=["no_spread", "contacts_negative_results"])
    assert news_story.run_news_tests(text) == []
    assert news.FILE.read_text() == before and news.FILE.name == "news.toml"


@pytest.mark.parametrize("line,why", [
    ("1,234 contacts tested negative.", "unapproved"),                         # a figure no fact has
    ("Results are in before voting on Monday.", "logistics"),                  # voting logistics
])
def test_a_bad_block_fails_the_news_tests(line, why):
    text, _ = news_story.draft(ARTICLE, SITE, SLUG, line=line, reading="Nothing changes.", requires=["no_spread"])
    assert news_story.run_news_tests(text), why


def test_a_block_whose_words_state_a_fact_it_doesn_t_rest_on_fails():
    text, _ = news_story.draft(ARTICLE, SITE, SLUG, line="The first case was isolated and every contact tested negative.",
                               reading="Caught early.", requires=["contacts_negative_results"])
    assert any("states_only" in f for f in news_story.run_news_tests(text))     # "isolated" is no_spread's


def test_staged_blocks_are_commented_out_and_pass_once_filled():
    staged = [line for line in news.FILE.read_text().splitlines() if line.startswith("# [")]
    assert len(staged) >= 3, "the staged stories: the retest either way, the campaign's close"
    keys = set(news.stories())
    assert not any(line[3:-1] in keys for line in staged)                   # none live
