"""1 Nov (Marc): the "30 Oct draft" call-out (content/flip.toml no_draft), the Herald columns and the columnist's ask
(swan_bot/oped.py)."""
import collections
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from swan_bot import bot, config, flip, news, oped, quality  # noqa: E402

# citizens' own words, 31 Oct-1 Nov (the draft as the Yes side's Trending posts tell it)
QUOTES = ["the 30 oct draft sets a may 31 2027 sunset and needs a public hearing plus a fresh panel report to extend it "
          "that makes yes workable for me though the venues and exemptions still need work",
          "i get why nobody wants another rule with no finish line. the draft now has a may end date and a public review "
          "before any extension so i'm voting yes",
          "The draft's better than campaign slogans: there's a sunset, review panel and venue list in writing. Still "
          "leaning limited Yes."]
DRAFT_POST = ("Stuck on this one. Who does the door checks? Yeah nah, the 30 Oct draft gives shops under 10 staff a "
              "one-off K$500 grant and free signage. That's what got me to yes")
AFTER_IT = "Grants for small shops help, but the law still needs real guardrails: publish the venue list, set a hard sunset."


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setattr(config, "FLIP_ON", True)
    monkeypatch.setattr(config, "DRAFT_CALLOUT_ON", True)
    monkeypatch.setattr(config, "OPED_LINK_ON", True)
    monkeypatch.setattr(config, "JOURNALIST_TAG_ON", True)
    flip.reset()
    news.reset()
    yield
    flip.reset()
    news.reset()


def variants(body, n=60):
    return [f"{body} ({i})" for i in range(n)]


def turns(texts, **kw):
    return collections.Counter(flip.choose(t, **kw)["pivot"]["key"] for t in texts)


class Fixed:
    """A random source that always draws the same: random() -> r, randrange(n) -> 0, choice(seq) -> seq[0]."""
    def __init__(self, r):
        self.r = r

    def random(self):
        return self.r

    def randrange(self, n):
        return 0

    def choice(self, seq):
        return seq[0]


# ---- the call-out -----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", QUOTES + [DRAFT_POST])
def test_a_post_that_quotes_the_draft_gets_the_call_out(text):
    drawn = turns(variants(text, 40))
    assert drawn["no_draft"] >= 32, drawn               # its weight: nearly always, with the odd other turn of theirs


def test_a_reply_to_a_draft_post_gets_it_from_the_post_it_answers():
    assert turns(variants(AFTER_IT), context=DRAFT_POST)["no_draft"] >= 45
    assert "no_draft" not in turns(variants(AFTER_IT))                     # without that post: their own turns only
    assert "no_draft" not in turns(variants(AFTER_IT), context="Lovely sunny day at the market.")


def test_a_post_that_never_mentions_a_draft_never_gets_it():
    assert "no_draft" not in turns(variants("I'm voting Yes, but only with a hard sunset and the venue list published."))
    assert "no_draft" not in turns(variants("Our hospital wards are full, I'm voting Yes."))


def test_the_call_out_switch(monkeypatch):
    monkeypatch.setattr(config, "DRAFT_CALLOUT_ON", False)
    assert "no_draft" not in turns(variants(QUOTES[0]), context=DRAFT_POST)
    assert flip.choose(QUOTES[0])                                          # the post still gets its flip


def test_the_call_out_names_no_figure_date_or_paper():
    lines = flip.as_list(flip.data()["pivot"]["no_draft"]["line"])
    assert len(lines) >= 3
    for line in lines:
        assert not any(ch.isdigit() for ch in line), line
        assert quality.unapproved_number(line) is None and not quality.WRONG_LOGISTICS.search(line)
        assert "Herald" not in line and "Daily" not in line                # invented_name: "neither paper", no names


def test_flip_choice_reads_the_post_they_answer():
    meta = {}
    job = dict(mode="reply", style=None, context=DRAFT_POST)
    texts = variants(AFTER_IT, 20)
    keys = []
    for t in texts:
        meta = {}
        bot.flip_choice(job, t, meta)
        keys.append(oped.pivot_of(meta.get("flip")))
    assert keys.count("no_draft") >= 15


# ---- the ask and the columns ------------------------------------------------------------------------------------------
NOW = 1_000_000.0
REPLY = "@tui_k That draft with the end date hasn't appeared in either paper, and the question itself has no end date."


def test_a_call_out_asks_the_columnist():
    text, extra = oped.finish(REPLY, "conditional_yes/surge_drill/no_draft", [], NOW, Fixed(0.9))
    assert text.startswith(REPLY) and "@julio_morales" in text and extra == {"journalist_tag": 0}
    assert len(oped.HANDLE.findall(text)) <= oped.MAX_HANDLES and len(text) <= oped.MAX_LEN


def test_the_ask_waits_its_turn(monkeypatch):
    monkeypatch.setattr(config, "JOURNALIST_TAG_PER_H", 3)
    monkeypatch.setattr(config, "JOURNALIST_TAG_GAP_S", 900)
    assert not oped.may_ask([NOW - 899], NOW)                              # too soon after the last
    assert oped.may_ask([NOW - 900], NOW)
    assert not oped.may_ask([NOW - 3500, NOW - 2600, NOW - 1700], NOW)     # the hour's three, all far enough apart
    assert oped.may_ask([NOW - 3700, NOW - 2600, NOW - 1700], NOW)         # one of them is over an hour old
    text, extra = oped.finish(REPLY, "x/y/no_draft", [NOW - 60], NOW, Fixed(0.99))
    assert "@julio_morales" not in text and extra == {"oped": "blank_cheque"}     # no ask: the column, whatever the share
    assert oped.finish(REPLY, "x/y/no_end", [NOW - 60], NOW, Fixed(0.99)) == (REPLY, {})   # other turns: the share


def test_the_ask_and_the_link_follow_a_finished_sentence():
    text, _ = oped.finish("That's the change", "x/y/no_draft", [], NOW, Fixed(0.9))
    assert text.startswith("That's the change. @julio_morales, ")
    assert oped.finish("Fair enough?", "x/y/no_end", [], NOW, Fixed(0.0))[0].startswith("Fair enough? https://")


def test_no_ask_on_a_reply_that_already_names_three():
    three = "@a1 @b2 @c3 " + REPLY[7:]
    text, extra = oped.finish(three, "x/y/no_draft", [], NOW, Fixed(0.0))
    assert "@julio_morales" not in text and extra.get("oped") == "blank_cheque"


def test_no_ask_or_link_past_the_length_limit():
    long = "x" * 470
    assert oped.finish(long, "x/y/no_draft", [], NOW, Fixed(0.0)) == (long + ".", {})


def test_the_columns_go_with_the_end_date_turns(monkeypatch):
    monkeypatch.setattr(config, "JOURNALIST_TAG_ON", False)
    text, extra = oped.finish(REPLY, "x/y/no_end", [], NOW, Fixed(0.0))
    assert text == f"{REPLY} {oped.COLUMNS['blank_cheque']}" and extra == {"oped": "blank_cheque"}
    assert oped.finish(REPLY, "x/y/no_draft", [], NOW, Fixed(0.0))[1] == {"oped": "blank_cheque"}
    assert oped.finish(REPLY, "x/y/promises", [], NOW, Fixed(0.0))[1] == {"oped": "perpetual_emergency"}
    assert oped.finish(REPLY, "x/y/no_list", [], NOW, Fixed(0.0))[1] == {"oped": "voting_in_the_dark"}
    assert oped.finish(REPLY, "x/y/who_checks", [], NOW, Fixed(0.0))[1] == {"oped": "good_intentions"}
    assert oped.finish(REPLY, "x/y/islands", [], NOW, Fixed(0.0))[1] == {"oped": "guardrails"}
    assert oped.finish(REPLY, "x/y/no_end", [], NOW, Fixed(config.OPED_LINK_SHARE)) == (REPLY, {})    # the share
    assert oped.finish(REPLY, "x/y/no_staff", [], NOW, Fixed(0.0)) == (REPLY, {})     # a turn the columns don't make
    assert oped.finish(REPLY, None, [], NOW, Fixed(0.0)) == (REPLY, {})               # no flip


def test_the_switches(monkeypatch):
    monkeypatch.setattr(config, "JOURNALIST_TAG_ON", False)
    monkeypatch.setattr(config, "OPED_LINK_ON", False)
    assert oped.finish(REPLY, "x/y/no_draft", [], NOW, Fixed(0.0)) == (REPLY, {})


def test_the_asks_state_no_figure_and_the_links_are_the_papers_columns():
    for ask in oped.ASKS:
        assert not any(ch.isdigit() for ch in ask) and ask.startswith("@{h},")
    assert all(u.startswith((oped.HERALD, oped.DAILY)) for u in oped.COLUMNS.values())


def test_every_linked_turn_has_its_columns_and_every_column_a_turn():
    assert set(config.OPED_PIVOTS) <= set(oped.FOR_PIVOT)
    assert {k for keys in oped.FOR_PIVOT.values() for k in keys} == set(oped.COLUMNS)
