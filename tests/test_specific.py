"""The reply specificity gate (quality.check -> not_specific) and the tala false positive (23 Oct 2026).

content.WORN_PHRASES keeps drafts off "end date", "venue list", "sunset", "after the vote" and "blank cheque", the
words quality.FACT_ANCHORS used to look for, so good replies were rejected as not_specific (316 of 721 rejects in 24 h,
19% of those jobs ever sent). The gate now also takes the same facts in other words (FACT_PARAPHRASES) and a reply
that picks up a distinctive word of the citizen's post and brings the rule to it (touches_target). Vague replies must
still fail. Texts below are from the live reject log (swan_actions.jsonl, act == reject)."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from swan_bot import quality  # noqa: E402


def check(reply, target, wants=()):
    return quality.check(reply, "reply", target_text=target, wants=wants)


# (reply, target): were rejected as not_specific on 22-23 Oct, and say the fact in other words or answer their point
NOW_PASS = [
    ("Another card to carry. They're deciding which doors need it after you've already said yes. I wire shops all over "
     "Kingstonia City, some weeks in six different sites. I don't even know which ones would turn me away.",
     "true... it's just another thing to carry in your wallet"),
    ("Hall key queues I know. The places aren't set until after the vote. I'm on the city loop past the hospital, and "
     "I'll be the one checking. They want the signature first, the rooms later.",
     "Exactly, the hall queues will be a mess."),
    ("Staged rollout makes sense for health workers. Daily Kingstonia says IHO data on real-world prevention and "
     "boosters is still coming. Why rush papers for shops and buses before we know how long protection lasts?",
     "exactly, and that staged rollout is the only way to do it right."),
    ("The stallholders and early bus lads. My daughter's kids start school in a few years, and this pass could still "
     "be at their gate with no switch-off date built in.",
     "exactly. even if you're okay with the jab, you shouldn't have to vote for a rule that lets them decide the "
     "details whenever they feel like it."),
    ("A trust-us vote, you called it. They won't say which doors until you've already said yes. I've been fixing utes "
     "all week for people who need their vehicles to work, not to fill out forms.",
     "Exactly. It's basically a 'trust us' vote with no actual details provided."),
    # no fact word at all, but it takes up their words (skeleton crew) and brings the rule to them
    ("Those clinics are stretched thin all year, and a door check at every shop will not put one more pair of hands "
     "in them. My depot is stretched too, and I'd be the one turning people away.",
     "It's a struggle everywhere we go. The clinics are always short of people."),
    ("Shop staff on doors, that's the mess. I've watched two cafes close since COVID; now they want my bus run with "
     "paper checks. A rule that puts workers on guard duty instead of doing their job isn't ready.",
     "Exactly, they haven't even told us how the staff would do it without it being a total mess"),
]

# vague: no fact, nothing of theirs brought to the rule. These must keep failing.
STILL_VAGUE = [
    ("We all want what is best for our community, and I think we can do better together if we try.",
     "Doesn't matter if it's the card or a separate cert, they don't ever go away."),
    ("Wallet clutter is annoying. I love this town and the people in it. Who do you know that feels the same way?",
     "true... it's just another thing to carry in your wallet"),
    # the reply echoes "rules" but says nothing about the rule: "rules" is not a policy word
    ("I hear the worry about rules changing halfway through. That would be unsettling for many people around here.",
     "politely asking nicely wont stop them from changing the rules halfway through tho"),
    # a policy word but no word of theirs and no fact
    ("My weekends are busy. I check the tide tables and the door of the shed twice a day.",
     "The weather is lovely and the harbour looks great this morning."),
    # bare topic words are on every reply: "pass", "papers" prove nothing on their own
    ("It is a pass and it is papers and everyone knows it, which is why people feel the way they feel about this.",
     "Morning coffee at the cafe. Espresso, croissant, a quiet moment."),
]


@pytest.mark.parametrize("reply,target", NOW_PASS)
def test_replies_that_state_the_fact_in_other_words_pass(reply, target):
    clean, why = check(reply, target)
    assert clean, f"rejected ({why}): {reply}"


@pytest.mark.parametrize("reply,target", STILL_VAGUE)
def test_vague_replies_still_fail(reply, target):
    clean, why = check(reply, target)
    assert clean is None and why == "not_specific", (why, reply)


def test_the_old_anchors_and_wants_still_pass():
    assert check("A Yes leaves no review date written anywhere, and my niece starts school in a year.", "x")[0]
    assert check("Rugby clubs matter. Someone has to stand at the door of every ground on a Saturday.",
                 "keep the rugby clubs open", wants=("rugby",))[0]


def test_a_bare_echo_without_the_rule_fails():
    target = "The elderly and those with existing health conditions, definitely. We have to protect them."
    reply = "Protecting the elderly and those with existing health conditions matters to me. I think of my mum often."
    assert check(reply, target) == (None, "not_specific")


def test_which_shops_as_a_closing_question_is_not_a_fact():
    reply = "My mum loves her Saturdays out and about. Which shops would you miss most if the weather turned?"
    assert check(reply, "Nice morning for it")[1] == "not_specific"


def test_touches_target_needs_a_policy_word_and_a_shared_word():
    assert quality.touches_target("Total mess at the shop door, checking papers.", "That is a total mess for everyone")
    assert not quality.touches_target("Total mess, I think.", "That is a total mess for everyone")       # no policy word
    assert not quality.touches_target("Checking papers at the door.", "That is a total mess for everyone")  # nothing shared
    assert not quality.touches_target("Checking papers at the door.", None)


# ---- wrong_logistics: Tala is a girl's name here, tala is the currency of Samoa ----
@pytest.mark.parametrize("text", [
    "My niece Tala, 13, walks to netball at the Crown Harbour courts. Will she need proof for the bus, the shops?",
    "My cousin in Talau Village already pays K$14 each way for her daughter's asthma check.",
    "My granddaughter Tala starts at Henderson High next year; if schools are on the list, she stays home.",
])
def test_names_are_not_currency(text):
    assert not quality.WRONG_LOGISTICS.search(text)


@pytest.mark.parametrize("text", [
    "It costs 20 tala to cross.", "That's 5 pa'anga a ride.", "Vote on Tuesday.",
    "Polling day is soon.",
])
def test_wrong_currency_and_logistics_still_rejected(text):
    assert quality.WRONG_LOGISTICS.search(text)


def test_the_repair_note_says_what_the_gate_wants():
    note = quality.repair_note("not_specific", "x", "reply")
    assert "which places the question doesn't name" in note and "word or two of theirs" in note   # no target given
