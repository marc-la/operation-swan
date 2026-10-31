"""todo/50: the prompt critique's fixes 1-5 (docs/06-strategy/prompt-critique-2026-10-28.md), behind arm_style."""
import random
import types

import pytest

from swan_bot import bot, config, content, humanize, memory, quality, register

P = content.PERSONA_BY_KEY
CONDOLENCE = "so sorry to hear about your dad (it really shows why we can't let the hospitals reach that point again)"
SCEPTIC = ("Does a pass help the ward if there aren't enough nurses? I'd want evidence it meaningfully reduces severe "
           "cases, alongside a real staffing plan.")


@pytest.fixture
def fixes_on(monkeypatch):
    monkeypatch.setattr(config, "STYLE_FIXES", True)
    monkeypatch.setattr(config, "SWITCHBACK", [("arm_style", ["fixes"], config.STYLE_BLOCK_S)])
    monkeypatch.setattr(config, "ARMS_FREEZE", None)


def job(body=SCEPTIC, **kw):
    kw.setdefault("memory", dict(spent=set(), voice_texts=[], history=(0, [])))
    return dict(mode="reply", rec=dict(persona="paulo", username="uptown83", account_id=13222),
                frame="F10_staff_and_livelihoods", target=dict(post_id=1, author_id=500, body=body), **kw)


# ---- arm ------------------------------------------------------------------------------------------------------------

def test_the_arm_is_base_while_style_fixes_is_off(monkeypatch):
    monkeypatch.setattr(config, "STYLE_FIXES", False)
    assert memory.arm() == "base"


def test_the_arm_follows_the_switchback_and_freezes_to_the_pin(monkeypatch):
    monkeypatch.setattr(config, "STYLE_FIXES", True)
    monkeypatch.setattr(config, "SWITCHBACK", [("arm_style", ["base", "fixes"], 9000)])
    monkeypatch.setattr(config, "ARMS_FREEZE", None)
    arms = {memory.arm(t=9000 * n + 1) for n in range(6)}
    assert arms == {"base", "fixes"}
    monkeypatch.setattr(config, "ARMS_FREEZE", 1.0)
    assert memory.arm(t=5.0) == config.FREEZE_PIN["arm_style"] == "fixes"


def test_the_arm_freezes_to_fixes_and_its_blocks_line_up_with_no_other_arm():
    """28 Oct: STYLE_FIXES is on (the offline A/B passed) and pinned to fixes for the freeze; LEAN_PROMPT stays off (it
    repeats our worn phrases)."""
    assert config.FREEZE_PIN["arm_style"] == "fixes"
    assert config.STYLE_BLOCK_S % 3600 and config.STYLE_BLOCK_S % (2 * 3600)


# ---- fix 1: memory per voice -----------------------------------------------------------------------------------------

def test_memory_keeps_the_voice_texts_items_and_citizen_history(monkeypatch):
    monkeypatch.setattr(config, "VOICE_MEMORY_N", 3)
    monkeypatch.setattr(config, "CITIZEN_HISTORY_N", 2)
    monkeypatch.setattr(config, "ITEM_MAX_PER_DAY", 2)
    state = {}
    for i in range(5):
        memory.record(state, "v1", 500, f"text {i}", items=["talia"], t=1000.0 + i)
    assert memory.voice_texts(state, "v1") == ["text 2", "text 3", "text 4"]
    assert memory.history(state, 500) == (5, [("v1", "text 3"), ("v1", "text 4")])
    assert memory.spent_items(state, "v1", t=1010.0) == {"talia"}
    assert memory.spent_items(state, "v1", t=1000.0 + memory.ITEM_WINDOW_S + 10) == set()   # a day later it's back
    assert memory.history(state, 999) == (0, [])


def test_memory_drops_the_least_recent_citizens(monkeypatch):
    monkeypatch.setattr(config, "CITIZEN_HISTORY_MAX", 2)
    state = {}
    for a, t in ((1, 1.0), (2, 2.0), (3, 3.0)):
        memory.record(state, "v", a, "x", t=t)
    assert set(state["citizen_sent"]) == {"2", "3"} and set(state["citizen_n"]) == {"2", "3"}


def test_voice_repeat_finds_the_story_not_the_template():
    texts = ["Jacqui starts high school in March.", "My Jacqui starts high school soon.",
             "Jacqui starts high school, and then what?", "Jacqui starts high school next year.",
             "The question doesn't say when it ends."]
    draft = "Jacqui starts high school in February and needs papers."
    assert memory.voice_repeat(draft, texts) == "jacqui starts high"
    # stop-word runs ("the question doesn't") are templates for the phrase budgets, not this check
    assert memory.voice_repeat("The question doesn't say when.", ["The question doesn't say it."] * 5) is None
    # their own words are an echo
    assert memory.voice_repeat(draft, texts, target_text="when jacqui starts high school") is None
    # three uses in the last 50 is fine
    assert memory.voice_repeat(draft, texts[1:]) is None


def test_voice_repeat_leaves_our_case_to_the_phrase_budgets():
    """A run made only of the argument's own words (facts, gists, levers) is our case, not a voice's story."""
    case = ["A pass at the door adds no nurse and no bed, and Central has 40 empty nursing posts."] * 6
    assert memory.voice_repeat("It adds no nurse; Central has 40 empty nursing posts still.", case) is None
    assert {"nurse", "nursing", "empty"} <= memory.argument_vocab()


def test_the_gate_rejects_the_voice_repeat_and_the_fix_drops_that_sentence():
    texts = ["Jacqui starts high school in March, so the gate needs papers."] * 4
    draft = ("Nobody at my warehouse knows if the loading dock counts. Jacqui starts high school in March and would "
             "need papers too. The list of places only comes after the vote.")
    text, why = quality.check(draft, "reply", target_text=SCEPTIC, voice_texts=texts, known_caps=("Jacqui",))
    assert text is None and why.startswith(quality.VOICE_REPEAT)
    fixed = quality.fix(draft, why, "reply")
    assert fixed and "Jacqui" not in fixed
    assert quality.check(draft, "reply", target_text=SCEPTIC, known_caps=("Jacqui",))[1] is None   # base: no voice check
    assert quality.repair_note(why, draft, "reply", None).startswith("You have said")


def test_the_system_prompt_without_colour_names_nobody(fixes_on):
    meta = {}
    text = content.system_prompt(P["paulo"], "F13_age12", meta=meta, mode="reply", fixes=dict(colour=False, spent=()))
    assert "Talia" not in text and "People in your life" not in text and "This fortnight" not in text
    assert "About you" not in text and meta["items"] == [] and meta["colour"] is False
    assert content.STRANGER_RULE in text
    assert "one named person or moment from your week" not in text


def test_the_system_prompt_leaves_out_spent_items_and_logs_the_rest():
    p = P["paulo"]
    spent = {memory.item_key(x) for x in p["people"] + p["now"] + p["details"] + [p["problem"], p["covid"]]}
    random.seed(1)
    meta = {}
    text = content.system_prompt(p, "F13_age12", meta=meta, mode="reply", fixes=dict(colour=True, spent=spent))
    assert "Talia" not in text and meta["items"] == []
    random.seed(1)
    meta = {}
    content.system_prompt(p, "F13_age12", meta=meta, mode="reply", fixes=dict(colour=True, spent=()))
    assert meta["items"] and meta["colour"] is True


def test_the_base_system_prompt_is_unchanged_but_logs_its_items():
    random.seed(2)
    meta = {}
    text = content.system_prompt(P["paulo"], "F13_age12", meta=meta, mode="reply")
    assert content.STRANGER_RULE not in text and "colour" not in meta and meta["items"]


# ---- fix 2: the conversation ------------------------------------------------------------------------------------------

def test_conversation_lines_say_what_we_told_them_and_who_they_talk_to():
    fx = dict(history=(4, [("uptown83", "Jacqui starts high school."), ("other7", "No end date in it.")]),
              me="uptown83", register=register.read("Rex, you're right about the staffing angle."),
              addressed="Rex", addressed_me=False, personal=None)
    line = content.conversation_lines(fx, "uptown83")
    assert "4 times before" in line and "you said «Jacqui" in line and "another neighbour said «No end" in line
    assert "talking to Rex, not you" in line
    assert content.conversation_lines(None) == ""


def test_a_personal_remark_is_answered_first_and_not_taken_as_ours():
    to_other = dict(personal="sorry to hear", own_parent=False, addressed_me=False)
    assert "meant for the person they answered" in content.conversation_lines(to_other)
    to_me = dict(personal="sorry to hear", own_parent=True)
    assert "answer that first" in content.conversation_lines(to_me)


def test_register_reads_case_stop_names_and_personal():
    r = register.read("yeah solid guardrails matter but theyre real and public publish the exact list")
    assert r["lower"] and r["no_stop"] and r["casual"] and r["addressed"] is None
    assert register.read("Rex, you're right about the staffing angle.")["addressed"] == "Rex"
    assert register.read("Kai's point lands for me.")["addressed"] == "Kai"
    assert register.read("Fair point, Jordy. If Yes passes...")["addressed"] == "Jordy"
    assert register.read("Yes, but only with a sunset.")["addressed"] is None
    assert register.personal(CONDOLENCE) == "sorry to hear"
    assert register.personal("The list comes after the vote.") is None
    assert register.is_me("Paulo", P["paulo"]) and not register.is_me("Rex", P["paulo"])
    assert register.is_me("uptown83", dict(P["paulo"], username="uptown83"))


def test_build_prompt_in_a_fixes_block_carries_the_conversation(fixes_on):
    j = job(CONDOLENCE, context="I lost my dad in COVID.", parent_author=999)
    j["memory"]["history"] = (3, [("uptown83", "Jacqui starts high school in March.")])
    _, system, user = bot.build_prompt(j, types.SimpleNamespace(headline=None))
    assert j["fixes"] is True and j["meta"]["arm_style"] == "fixes"
    assert "meant for the person they answered" in user and "3 times before" in user
    assert "They write all lowercase" in user and content.STRANGER_RULE in system


def test_build_prompt_marks_our_own_parent(fixes_on):
    j = job(CONDOLENCE, context="I lost my dad in COVID.", parent_author=13222)
    _, _, user = bot.build_prompt(j, types.SimpleNamespace(headline=None))
    assert "your own earlier post" in user and "answer that first" in user


def test_build_prompt_in_a_base_block_is_today_s(monkeypatch):
    monkeypatch.setattr(config, "STYLE_FIXES", False)
    j = job()
    _, system, user = bot.build_prompt(j, types.SimpleNamespace(headline=None))
    assert j["fixes"] is False and j["meta"]["arm_style"] == "base"
    assert content.STRANGER_RULE not in system and "People on your side" not in user


# ---- fix 3: the rebuttal is a condition -------------------------------------------------------------------------------

def test_the_rebuttal_is_conditional_in_a_fixes_block(monkeypatch):
    monkeypatch.setattr(config, "PIN", {"reply_mode": "reason_first"})
    monkeypatch.setattr(config, "FLIP_ON", False)                 # the fixed rebuttals (29 Oct: the flip replaces them)
    fx = dict(colour=False, history=(0, []), register=register.read(SCEPTIC))
    user = content.reply_prompt(SCEPTIC, "F10_staff_and_livelihoods", [], persona=P["paulo"], fixes=fx, meta={})
    assert "If (and only if) their post really shows it: they are worried" in user
    assert "Answer WHY they lean Yes" not in user and "If they lean Yes, answer WHY" in user
    base = content.reply_prompt(SCEPTIC, "F10_staff_and_livelihoods", [], persona=P["paulo"], meta={})
    assert "They are worried about the hospitals" in base and "Answer WHY they lean Yes" in base
    monkeypatch.setattr(config, "FLIP_ON", True)
    user = content.reply_prompt(SCEPTIC, "F10_staff_and_livelihoods", [], persona=P["paulo"], fixes=fx, meta={})
    assert "If (and only if) their post really shows it: their worry underneath is the hospitals" in user


# ---- fix 4: shape, register and typing --------------------------------------------------------------------------------

def test_fixes_replies_end_on_a_question_at_the_set_share_and_drop_the_echo_opener_and_lever():
    random.seed(3)
    fx = dict(colour=False, history=(0, []), register=register.read(SCEPTIC))
    asks, openers = [], set()
    for _ in range(400):
        meta = {}
        user = content.reply_prompt(SCEPTIC, "F1_blank_cheque", [], persona=P["josh"], fixes=fx, meta=meta)
        asks.append(meta["ask_kind"] != "none")
        openers.add(meta["opener"])
        assert "Make it land through this" not in user and meta["lever"] is None
    share = config.REPLY_QUESTION_SHARE           # 0.40 since 31 Oct (0.10 from 28 Oct; rival-strategies-2026-10-31 §3.3)
    assert share - 0.08 < sum(asks) / len(asks) < share + 0.08
    assert openers <= set(content.FIXES_OPENERS) and not openers & set(content.OPENERS[:2])


def test_fixes_length_follows_what_they_wrote():
    assert content.fixes_length("short one")[3] == 120
    assert content.fixes_length("x" * 600)[3] == content.CHAR_CAP["reply"]


def test_the_gate_rejects_an_echo_opener_only_when_asked():
    draft = "You want it written down. The question gives no end date and the places come after the vote."
    assert quality.check(draft, "reply", target_text=SCEPTIC, echo_open=True)[1] == "echo_open"
    assert quality.check(draft, "reply", target_text=SCEPTIC)[1] != "echo_open"
    assert not quality.fix(draft, "echo_open", "reply").lower().startswith("you want")


def test_the_floor_lets_a_short_reply_through_in_a_fixes_block():
    short = "A pass at the door adds no nurse to the ward."
    assert quality.check(short, "reply", target_text=SCEPTIC)[1].startswith("length_")
    assert quality.check(short, "reply", target_text=SCEPTIC, floor=40)[1] is None


class Rng:
    """random() returns the values in turn (then 0.99); choice / randrange take the first."""
    def __init__(self, *vals):
        self.vals = list(vals)

    def random(self):
        return self.vals.pop(0) if self.vals else 0.99

    def choice(self, xs):
        return xs[0]

    def randrange(self, a, b=None):
        return a if b is not None else 0


def test_mirror_types_lowercase_without_a_stop_when_they_do():
    text = "The question gives no end date. A pass adds no nurse."
    out, changes = humanize.apply(text, "priya", "reply", rng=Rng(0.99, 0.99, 0.99, 0.99, 0.0, 0.0),
                                  target_text="yeah but nobody says when it ends or where it applies", mirror=True)
    assert out == out.lower() and not out.endswith(".") and "lower" in changes and "no_stop" in changes


def test_mirror_never_makes_a_keyboard_slip_and_drops_semicolons():
    text = "Nobody is checking anything yet; the list comes later. Nothing is decided."
    for seed in range(200):
        out, changes = humanize.apply(text, "josh", "reply", rng=random.Random(seed), target_text="Fine.", mirror=True)
        assert not any(c.startswith("slip:") or c == "dots" for c in changes)
        assert ";" not in out
        assert all(w in ("checkin", "nothin") or w in text.lower() for w in
                   (w.strip(".,").lower() for w in out.replace("&", "and").split()))


def test_humanize_without_mirror_is_unchanged():
    text = "The question gives no end date. A pass adds no nurse."
    for seed in range(20):
        a = humanize.apply(text, "josh", "reply", rng=random.Random(seed))
        b = humanize.apply(text, "josh", "reply", rng=random.Random(seed), target_text="whatever", mirror=False)
        assert a == b


# ---- fix 5: the lean prompt -------------------------------------------------------------------------------------------

def test_the_lean_prompt_is_short_and_keeps_the_read(fixes_on, monkeypatch):
    monkeypatch.setattr(config, "LEAN_PROMPT", True)
    random.seed(4)
    j = job(CONDOLENCE, context="I lost my dad in COVID.", parent_author=999)
    _, system, user = bot.build_prompt(j, types.SimpleNamespace(headline=None))
    assert j["meta"]["lean"] is True and j["meta"]["style"] == "lean" and j.get("theme") is None
    assert len(system) + len(user) < 4000
    assert "\n\nFirst read them" in user and user.count("\n- F") <= 3
    assert "worn phrases" not in user and "Don't open the way our latest replies did" not in user
    assert content.STRANGER_RULE in system
    r = content.parse_read('{"stance": "unsure", "doubt": "x", "frame": "F10_staff_and_livelihoods", "reply": "ok"}')
    assert r["ok"] and r["frame"] == "F10_staff_and_livelihoods"


def test_the_lean_prompt_needs_style_fixes(monkeypatch):
    monkeypatch.setattr(config, "STYLE_FIXES", False)
    monkeypatch.setattr(config, "LEAN_PROMPT", True)
    j = job()
    bot.build_prompt(j, types.SimpleNamespace(headline=None))
    assert "lean" not in j["meta"]


def test_lean_shapes_draw_about_ten_percent_questions():
    random.seed(5)
    shapes = []
    for _ in range(500):
        meta = {}
        content.lean_reply_prompt(SCEPTIC, "F10_staff_and_livelihoods", [], meta=meta, persona=P["kai"],
                                  fixes=dict(register=register.read(SCEPTIC)))
        shapes.append(meta["lean_shape"])
    assert 0.05 < shapes.count("question_back") / len(shapes) < 0.16


def test_the_lean_mention_line_goes_before_the_read(fixes_on, monkeypatch):
    monkeypatch.setattr(config, "LEAN_PROMPT", True)
    j = job(mention=dict(author_id=7, username="tui_walker"))
    _, _, user = bot.build_prompt(j, types.SimpleNamespace(headline=None))
    if j.get("read"):
        assert user.index("@tui_walker") < user.index("First read them")


# ---- the bot's gate gets the voice's texts in a fixes block -----------------------------------------------------------

def test_the_bot_gate_checks_the_voice_texts_only_in_a_fixes_block():
    draft = ("Nobody at my warehouse knows if the loading dock counts. Jacqui starts high school in March and would "
             "need papers too. The list of places only comes after the vote.")
    texts = ["Jacqui starts high school in March, so the gate needs papers."] * 4
    j = job(memory=dict(spent=(), voice_texts=texts, history=(0, [])))
    j["fixes"], j["meta"], j["system_caps"] = True, {}, {"Jacqui"}
    text, why, fixes = bot.gate(draft, j, "", [])
    assert text and "Jacqui" not in text and fixes and fixes[0].startswith(quality.VOICE_REPEAT)
    j["fixes"] = False
    text, _, _ = bot.gate(draft, j, "", [])
    assert text and "Jacqui" in text
