"""todo/27: stop the fingerprint (phrase budgets, the vote-statement code fix) (no network)."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from swan_bot import bot, quality  # noqa: E402

REPLY = ("My cafe runs on trust and the regulars know my face. A pass at the door with no finish date is a different "
         "shop. I'm voting No.")
VOTE = "So I'm voting No."
PLAIN = "Our ferry crew talk about the weather."


def window(n_with, text=VOTE, total=99):
    return [text] * n_with + [PLAIN] * (total - n_with)


# ---- phrase budgets ---------------------------------------------------------------------------------------------
def test_vote_budget_is_15_in_100():
    assert quality.over_budget(REPLY, window(14)) == []
    assert quality.over_budget(REPLY, window(15)) == ["vote"]


def test_topic_budget_is_10_in_100():
    t = "The question has no end date, and my stall at the market would carry the pass for years."
    assert quality.over_budget(t, window(9, "There is no end date.")) == []
    assert quality.over_budget(t, window(10, "There is no end date.")) == ["end_date"]


def test_only_the_last_100_count_and_a_short_window_counts_as_full():
    assert quality.over_budget(REPLY, [VOTE] * 40 + window(10)) == []
    assert quality.over_budget(REPLY, [VOTE] * 14) == []
    assert quality.over_budget(REPLY, []) == []


def test_the_template_phrases_are_found():
    t = ("The venue list comes out after the vote, and the question sets no end date or review, with no sunset. "
         "A Yes binds us. I'm a No.")
    assert set(quality.phrases_in(t)) == set(quality.PHRASE_BUDGETS) - set(quality.TELL_KEYS)


def test_check_budgets_citizen_facing_kinds_only():
    full = window(30)
    assert quality.check(REPLY, "reply", phrase_texts=full) == (None, "phrase_vote")
    assert quality.check(REPLY, "reply_back", phrase_texts=full)[1] == "phrase_vote"
    assert quality.check(REPLY, "reply", phrase_texts=None)[1] is None          # not tracked: no budget
    assert quality.check(REPLY, "journalist", phrase_texts=full)[1] != "phrase_vote"


def test_all_phrases_over_budget_are_named():
    t = "The question has no end date, and my stall at the market would carry the pass for years. I'm voting No."
    w = [VOTE] * 15 + ["There is no end date."] * 10 + [PLAIN] * 74
    assert quality.check(t, "reply", phrase_texts=w)[1] == "phrase_vote+end_date"
    note = quality.repair_note("phrase_vote+end_date", t, "reply")
    assert "«voting No»" in note and "«end date»" in note and "without them" in note
    assert "Don't state your vote" in note


# ---- the code fix: drop the statement of the vote ---------------------------------------------------------------
def test_only_states_vote():
    assert quality.only_states_vote("That's why I'm voting No.")
    assert quality.only_states_vote("I am voting No on this one.")
    assert not quality.only_states_vote("I'm voting No because the ferry crew would check papers.")
    assert not quality.only_states_vote("The ferry is late again.")


def test_drop_vote_cuts_the_closing_sentence_or_clause():
    pre = "My cafe runs on trust and the regulars know my face, and a pass at the door changes that. "
    assert quality.drop_vote(pre + "That's why I'm voting No.", "reply") == pre.strip()
    assert quality.drop_vote(pre + "A Yes can't carry your conditions; I'm voting No.", "reply") == \
        pre + "A Yes can't carry your conditions."
    assert quality.drop_vote(pre + "That's a blank cheque, so I'm voting No.", "reply") == pre + "That's a blank cheque."
    assert quality.drop_vote(pre + "I'm voting No because the rule never ends.", "reply") == pre + "The rule never ends."


def test_drop_vote_gives_up_when_too_short_or_nothing_to_cut():
    assert quality.drop_vote("Ferries matter. I'm voting No.", "reply") is None           # under the floor
    assert quality.drop_vote("My cafe runs on trust and the regulars know my face, and a pass at the door changes "
                             "that for good.", "reply") is None                             # no vote to cut


def test_gate_fixes_a_vote_close_over_budget():
    job = dict(mode="reply", phrase_texts=window(30), target=dict(body="what about the cafes"))
    text, why, fixes = bot.gate(REPLY, job, "user", [])
    assert why is None and fixes == ["phrase_vote"]
    assert text == "My cafe runs on trust and the regulars know my face. A pass at the door with no finish date is a " \
                   "different shop."


def test_gate_passes_the_phrase_texts(monkeypatch):
    seen = {}
    monkeypatch.setattr(bot.quality, "check", lambda raw, mode, recent, **kw: (seen.update(kw), (raw, None))[1])
    bot.gate("draft", dict(mode="reply", phrase_texts=["x"]), "user", [])
    assert seen["phrase_texts"] == ["x"]


def test_citizen_texts_are_the_citizen_facing_ones():
    sent = [[500, 10, "to a citizen"], [9000, 11, "to our own thread"], [3, 12, "to a journalist"]]
    ready = [dict(job=dict(target=dict(author_id=501)), text="waiting, to a citizen"),
             dict(job=dict(target=None), text="a post")]
    assert bot.citizen_texts(sent, ready) == ["to a citizen", "waiting, to a citizen"]
    assert len(bot.citizen_texts([[500, 1, "x"]] * 300)) == quality.PHRASE_WINDOW


# ---- 23 Oct hidden-post audit: three tells with no share at all ---------------------------------------------------
TELLS = {
    "switch_close": "A pass at the door adds no bed. Do you know anyone who's moved from Yes to No?",
    "switch_story": "My cousin Mele was Yes for the hospital's sake till she saw that, now she's No. The list is secret.",
    "concede_open": "A sunset clause makes sense. But the question has none, and the places stay secret.",
}


@pytest.mark.parametrize("key", quality.TELL_KEYS)
def test_a_tell_is_rejected_whatever_the_window_holds(key):
    assert key in quality.over_budget(TELLS[key], []), "no window needed: the share is 0"
    assert key in quality.over_budget(TELLS[key], ["something else entirely"] * 99)


def test_plain_replies_and_plain_relatives_are_not_tells():
    for t in ("Central's 40 nurses short. A pass at the shop door adds no bed, and nobody has said who checks it.",
              "My mate Faisal opens at six and doesn't know yet if his dairy counts. Who checks the door then?",
              "What would you miss if your bus home needed papers?"):
        assert not set(quality.over_budget(t, [])) & set(quality.TELL_KEYS), t


def test_the_firm_yes_arm_may_concede_but_nothing_else_is_exempt():
    assert quality.over_budget(TELLS["concede_open"], [], exempt=("concede_open",)) == []
    assert "switch_close" in quality.over_budget(TELLS["switch_close"], [], exempt=("concede_open",))


def test_the_repair_note_for_a_tell_says_what_to_drop():
    note = quality.repair_note("phrase_switch_close", TELLS["switch_close"], "reply")
    assert "know anyone" in note and "Change nothing else" in note


def test_prompts_and_weights_no_longer_ask_for_the_tells():
    import random
    from swan_bot import config, content, experiment
    assert not any("concession" in o for o in content.OPENERS)
    assert "know anyone" in content.REPLY_RULES and "never open by granting" in content.REPLY_RULES.lower()
    assert "switching" not in content.lever_weights() and config.LEVER_WEIGHTS["switching"] == 0.0
    rng = random.Random(1)
    assert {experiment.draw("ask_kind", experiment.ASK_WEIGHTS, rng=rng) for _ in range(400)} \
        == {"frame", "people", "loss", "status_quo", "none"}
