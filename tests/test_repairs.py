"""23 Oct 2026: targeted repairs and the phrase budgets (quality.py, content.worn_line, bot.draft_checked).

A third of drafts were rejected, 105 of them in 24 h for phrase_sunset, and a repair re-failed not_specific 155 times
because the note never named the citizen's words. 114 of the 118 phrase_sunset rejects answered a citizen who had
written "sunset" first. What is pinned here: an echo of the citizen's word is allowed up to ECHO_CEILING x the budget and
no further (the global frequency of every phrase stays bounded, whoever wrote it); the tells and the vote line are never
echo-exempt; the drafting prompt says which budgeted words are used up; the code fixes drop a sentence only when what
is left still reads; and a repair note quotes the citizen's words, the wording that repeats, and whose word it was.
No network, no LLM."""
import pathlib
import random
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from swan_bot import bot, content, quality  # noqa: E402

SUNSET_ASK = "I'd back a Yes if there is a clear sunset and a published list, and the exemptions are real."
ECHO = ("You want a sunset, and the question on the ballot has none. A Yes leaves the shop checks running for "
        "good, and my cafe would be the one doing them.")
NO_SUNSET_ASK = "Hospitals are stretched and I think a pass could help us through the winter."


def window(n_sunset, size=99):
    """The last `size` texts we sent, n_sunset of them saying "sunset"."""
    return ["A sunset clause is missing."] * n_sunset + ["Plain text about the ovens."] * (size - n_sunset)


def check(text, target, win, **kw):
    return quality.check(text, "reply", target_text=target, phrase_texts=win, **kw)


# ---- the echo allowance --------------------------------------------------------------------------------------------
def test_a_citizens_own_word_is_allowed_past_the_budget_but_ours_is_not():
    over = window(10)                                    # sunset is at its 10% budget
    assert check(ECHO, NO_SUNSET_ASK, over)[1] == "phrase_sunset"         # our word: rejected, as before
    assert check(ECHO, SUNSET_ASK, over)[0], "they wrote it first: an echo, not a template"


def test_the_allowance_stops_at_the_ceiling():
    full = window(15)
    assert check(ECHO, SUNSET_ASK, full)[1] == "phrase_sunset"
    assert check(ECHO, SUNSET_ASK, window(14))[0], "the 15th use still fits"
    assert quality.ECHO_CEILING * quality.PHRASE_BUDGETS["sunset"][1] * quality.PHRASE_WINDOW == pytest.approx(15)


def test_the_tells_and_the_vote_line_are_never_echo_exempt():
    concede = "Sunset clauses would help, but the question carries none, and the door check stays."
    assert quality.echoed("a fair ask would help, sunset too") == ("sunset",)        # tells never appear in echoed()
    assert "vote" not in quality.ECHO_KEYS and not set(quality.TELL_KEYS) & set(quality.ECHO_KEYS)
    assert "concede_open" in quality.over_budget(concede, window(0), echo=quality.echoed(concede))
    ask = "I'm voting No this time because the question names no places and nobody will staff the door checks."
    assert "vote" in quality.over_budget(ask, ["I'm voting No."] * 15, echo=("vote",))


def test_three_worn_phrases_in_one_text_get_no_allowance():
    stack = ("You want a sunset and an end date. The question has no review, and a Yes binds us to the list "
             "that comes after the vote.")
    assert len(quality.phrases_in(stack)) >= 3
    over = ["a sunset clause, an end date, no review, binds us"] * 10
    target = "sunset, end date, no review, binds us, venue list"
    assert quality.over_budget(stack, over, echo=quality.echoed(target))
    assert not quality.over_budget(ECHO, window(10), echo=quality.echoed(SUNSET_ASK))


def test_a_repeated_template_cannot_get_through_the_allowance():
    """Replay: 300 drafts in a row, every one saying "sunset" to a citizen who did. However many arrive, no 100
    consecutive texts we send hold more than 15 of them (10 without the allowance)."""
    rng = random.Random(7)
    sent = []
    for i in range(300):
        text = f"{rng.choice(['You want', 'Your ask for', 'Asking for'])} a sunset matters, but the question has none ({i})."
        if not quality.over_budget(text, sent[-99:], echo=quality.echoed(SUNSET_ASK)):
            sent.append(text)
    peak = max(sum("sunset" in t for t in sent[max(0, i - 99):i + 1]) for i in range(len(sent)))
    assert peak == 15 and len(sent) < 300
    sent = []
    for i in range(300):
        text = f"Asking for a sunset matters, but the question has none ({i})."
        if not quality.over_budget(text, sent[-99:]):
            sent.append(text)
    assert max(sum("sunset" in t for t in sent[max(0, i - 99):i + 1]) for i in range(len(sent))) == 10


def test_sunsets_and_end_hyphen_date_count_as_their_words():
    assert quality.echoed("we need sunsets for this") == ("sunset",)
    assert quality.echoed("a firm end-date please") == ("end_date",)
    assert quality.echoed("Publish the venue list now") == ("venue_list",)
    assert quality.echoed("nothing here") == ()


# ---- the drafting prompt names what is used up -----------------------------------------------------------------------
def test_spent_phrases_lists_what_the_gate_would_reject():
    assert quality.spent_phrases(window(9), SUNSET_ASK) == []
    assert quality.spent_phrases(window(10), NO_SUNSET_ASK) == [("sunset", "sunset")]
    assert quality.spent_phrases(window(10), SUNSET_ASK) == [], "their word has room up to the ceiling"
    assert quality.spent_phrases(window(15), SUNSET_ASK) == [("sunset", "sunset")]
    assert quality.spent_phrases(None, SUNSET_ASK) == []


def test_the_prompt_says_a_used_up_word_is_out_even_if_they_used_it():
    spent = quality.spent_phrases(window(15), SUNSET_ASK)
    line = content.worn_line(SUNSET_ASK, spent)
    assert "used up 'sunset'" in line and "even if they used that word" in line
    assert "'sunset'" in line.split("worn phrases:")[1].split(".")[0], "and it is back on the worn list"
    assert "used up" not in content.worn_line(SUNSET_ASK)
    assert "sunset" not in content.worn_line(SUNSET_ASK), "unspent and theirs: still allowed"
    for p in (content.reply_prompt(SUNSET_ASK, "F14_no_yes_but", [], spent=spent),
              content.reply_prompt(SUNSET_ASK, "F14_no_yes_but", [], style="mirror_concede", spent=spent),
              content.second_voice_prompt(SUNSET_ASK, "F6_islands", [], spent=spent),
              content.reply_back_prompt("ours", SUNSET_ASK, spent=spent)):
        assert "used up 'sunset'" in p


# ---- code fixes ------------------------------------------------------------------------------------------------------
def test_a_conceding_opener_is_dropped_when_the_rest_stands():
    text = ("Narrow scoping sounds fair, but the question has none. The IHO said this week booster data is still "
            "coming in, per Daily Kingstonia. Which of your own would still be checking papers for a booster we "
            "don't yet need?")
    assert quality.check(text, "reply", target_text="x", phrase_texts=[])[1] == "phrase_concede_open"
    fixed = quality.fix(text, "phrase_concede_open", "reply")
    assert fixed.startswith("The IHO said") and "sounds fair" not in fixed
    assert quality.check(fixed, "reply", target_text="x", phrase_texts=[])[0] == fixed


def test_a_sentence_with_a_worn_phrase_is_dropped_but_never_a_reply_gutted():
    text = ("You want a hard sunset. A pass at the shop door adds no nurse and no bed, and Central has 40 empty "
            "nursing posts. Who in your house works a door or rides a bus to shift?")
    fixed = quality.fix(text, "phrase_sunset", "reply")
    assert fixed and "sunset" not in fixed and fixed.startswith("A pass at the shop door")
    # the rest would be 28 characters of a 200-character reply: no fix, the model repairs it
    gutted = "You want a sunset, and the question has none. It is a promise. It is not on the ballot paper."
    assert quality.fix(gutted, "phrase_sunset", "reply") is None
    assert quality.fix("A sunset is missing from the question and nothing else is said here at all.",
                       "phrase_sunset", "reply") is None, "one sentence: nothing left to keep"


def test_a_sentence_leaning_on_the_dropped_one_blocks_the_fix():
    text = ("You want a sunset on it, which is fair. That is why the question matters so much to my cafe, where "
            "a door check would fall on me. Who would you ask to stand there all day on a Saturday?")
    assert quality.drop_phrase_sentences(text, ["sunset"], "reply") is None


def test_the_fix_only_runs_for_citizen_facing_kinds_and_the_vote_fix_is_unchanged():
    post = "A sunset is missing. " * 12
    assert quality.fix(post, "phrase_sunset", "post") is None
    said = "Nobody has named the places yet, so I'll wait to see. That's why I'm voting No."
    assert quality.fix(said, "phrase_vote", "reply") == quality.drop_vote(said, "reply")


def test_near_duplicate_drops_the_sentence_we_already_sent():
    old = ["A pass at the shop door adds no nurse and no bed. Central already has 40 empty nursing posts."]
    text = ("Care homes and hospitals first, agreed. A pass at the shop door adds no nurse and no bed; Central "
            "already has 40 empty nursing posts. My bakery would need someone on the door from 4:30am, and that "
            "someone is me or Sateki, not a hire.")
    assert quality.near_duplicate(text, "reply", old)
    fixed = quality.fix(text, "near_duplicate", "reply", recent=old)
    assert fixed and "no nurse and no bed" not in fixed and "bakery" in fixed
    assert not quality.near_duplicate(fixed, "reply", old)
    assert quality.fix(text, "near_duplicate", "reply") is None, "no recent texts, nothing to be close to"


def test_a_leading_sure_is_stripped_and_a_real_artefact_is_not():
    text = "Sure, writing it down sounds safer. But the places come after, and nobody has named one."
    assert quality.check(text, "reply")[1] == "llm_artefact"
    assert quality.fix(text, "llm_artefact", "reply") == ("Writing it down sounds safer. But the places come after, "
                                                          "and nobody has named one.")
    assert quality.fix("Here's the reply: no places are named.", "llm_artefact", "reply") is None


# ---- repair notes ----------------------------------------------------------------------------------------------------
TARGET = ("Exemptions gotta be fast and clear, with a real person at the desk to sort glitches, and a paper backup "
          "so urgent care never gets blocked.")


def test_not_specific_names_their_words_and_their_wants():
    note = quality.repair_note("not_specific", "A real person at every desk is a fair ask.", "reply", target_text=TARGET)
    assert "«glitches»" in note and "which places the question doesn't name" in note
    assert "xemption" not in note, "never steer the model onto exemptions"
    with_wants = quality.repair_note("not_specific", "x", "reply", target_text=TARGET, wants=["appeals", "oversight"])
    assert "«appeals» or «oversight»" in with_wants
    assert quality.repair_note("not_specific", "x", "reply")           # no target given: still a note


def test_not_specific_does_not_send_the_model_to_a_used_up_word():
    note = quality.repair_note("not_specific", "x", "reply", target_text=SUNSET_ASK, wants=["sunset"],
                               phrase_texts=window(15))
    assert "«sunset»" not in note
    assert "«sunset»" in quality.repair_note("not_specific", "x", "reply", target_text=SUNSET_ASK, wants=["sunset"],
                                             phrase_texts=window(2))


def test_near_duplicate_quotes_what_repeats_and_the_opening():
    old = ["A pass at the shop door adds no nurse and no bed. My home already has 40 empty nursing posts."]
    raw = "A pass at the shop door adds no nurse and no bed. I run the morning ferry."
    note = quality.repair_note("near_duplicate", raw, "reply", recent=old)
    assert "«a pass at the shop door adds no nurse and no bed»" in note
    assert "Don't open with «a pass at the»" in note
    assert "different opening" in note
    only_same = quality.repair_note("near_duplicate", raw, "reply", recent=["Zebra crossing ahead, mind the step."],
                                    same=old)
    assert "no nurse and no bed" in only_same, "texts to this citizen count too"
    assert "repeated wording" not in quality.repair_note("near_duplicate", "x", "reply")


def test_a_phrase_note_says_whose_word_it_was_and_only_mentions_the_vote_when_it_is_over():
    note = quality.repair_note("phrase_sunset", ECHO, "reply", target_text=SUNSET_ASK)
    assert "«sunset»" in note and "wrote that word themselves" in note and "vote" not in note
    mine = quality.repair_note("phrase_sunset", ECHO, "reply", target_text=NO_SUNSET_ASK)
    assert "themselves" not in mine
    assert "Don't state your vote" in quality.repair_note("phrase_vote", "That's why I'm voting No.", "reply")


def test_a_draft_that_is_the_models_own_notes_gets_a_fresh_draft_not_a_repair():
    assert quality.repair_note("llm_artefact", "The user wants me to fix a draft reply...", "reply") is None
    assert quality.repair_note("llm_artefact", '{"stance": "unsure", "reply": "Sure, ..."}', "reply") is None
    assert quality.repair_note("llm_artefact", "Reply: they won't say which places.", "reply")


def test_the_old_call_still_works():
    assert quality.repair_note("near_duplicate", "x", "post")
    assert quality.repair_note("not_specific", "x", "reply", None, ())


# ---- draft_checked: the repair goes out with the target and the text the reason is about -----------------------------
class Gen:
    chain = [("bedrock", "m1")]

    def __init__(self, *answers):
        self.answers, self.prompts = list(answers), []

    def complete(self, system, user, models=None, **kw):
        self.prompts.append(user)
        return (self.answers.pop(0), "m1") if self.answers else (None, None)


def job(**kw):
    return dict(mode="reply", rec=dict(persona="lani"), frame=None, arm=None, wants=[], context=None, read=False,
                meta={}, target=dict(post_id=5, author_id=500, body=TARGET), phrase_texts=[], same_texts=[], **kw)


def test_the_repair_prompt_carries_their_word_and_the_draft_after_the_code_fixes():
    vague = "We all want what is best for our community, and I think we can do better together if we try."
    good = ("A real person at the desk costs a wage, and the glitches land on the shop that has to check papers "
            "at the door. Who would you ask to cover that on a Saturday?")
    gen = Gen(vague, good)
    text, backend, repair = bot.draft_checked(gen, job(), "sys", "user", [])
    assert text == good and repair == "not_specific"
    assert len(gen.prompts) == 2
    assert "«glitches»" in gen.prompts[1] and vague in gen.prompts[1]


def test_a_repair_for_a_trimmed_draft_shows_the_trimmed_text():
    long_vague = ("We all want what is best for our community and our families, and I believe we can do better "
                  "together if we try. " * 2 + "It is a big deal for all of us in the end. " * 4)
    gen = Gen(long_vague, "Nothing usable.")
    bot.draft_checked(gen, job(), "sys", "user", [])
    shown = gen.prompts[1].split("<<<")[1].split(">>>")[0]
    assert len(shown) <= quality.LENGTHS["reply"][1], "the repair shows the draft the reason is about, not the raw"


def test_an_echoed_sunset_is_sent_when_the_citizen_wrote_it(monkeypatch):
    gen = Gen(ECHO)
    j = job()
    j["target"]["body"] = SUNSET_ASK
    j["phrase_texts"] = window(11)
    text, _, _ = bot.draft_checked(gen, j, "sys", "user", [])
    assert text == ECHO and len(gen.prompts) == 1
