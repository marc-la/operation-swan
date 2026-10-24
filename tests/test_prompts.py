"""Prompt assembly (content.py, content v2): playbook data merged at import, post anatomy, shapes, voices, rules,
logging meta, replies and journalist storylines. Offline: prompts are rendered, never sent.

    python -m pytest tests/test_prompts.py -q
"""
import copy
import pathlib
import random
import re
import sys
import types

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from swan_bot import batch, config, content, experiment  # noqa: E402
from swan_bot.playbook import craft, voices  # noqa: E402

try:
    from swan_bot.playbook import characters as real_characters  # noqa: E402
except ImportError:
    real_characters = None

P = content.PERSONA_BY_KEY
FRAME_KEYS = list(content.FRAMES)
HEADLINE = "Schools brace for H2D2 rules"


@pytest.fixture(autouse=True)
def _tagged_posts(monkeypatch):
    """The post anatomy below ends on one hashtag (the pre-todo/40 posts); the default without one is tested in
    tests/test_post_tag_vote.py."""
    monkeypatch.setattr(config, "POST_NO_TAG_WITH_VOTE", False)

# Long, realistic character fields (like L3's drafts) to exercise clipping, the budget and the jab-timing filter.
FAKE = types.SimpleNamespace(CHARACTERS={
    "lani": dict(
        age=38, arc="She meant to stay out of it until Teuila asked whether she'd be the one checking papers.",
        people=["Teuila, her barista, nineteen, an engineering student at Crown Harbour Institute of Technology",
                "Uncle Feleti, a retired ferry engineer who has had the corner table by the window for years",
                "Sina, her mum, who started the cafe and still makes the coconut buns on Sundays"],
        problem="Workplaces are in the question, so under a Yes her two student baristas would need certificates "
                "just to work their shifts, and if cafes make the list they would be the ones checking papers at "
                "the counter, visitors off the boats included.",
        covid="When the borders shut the boats stopped coming; she and her mum kept the doors open on takeaway "
              "coffee for wharf workers while the souvenir shop next door closed for good.",
        lines=["Half my trade walks off the boats."],
        now=["A nurse who'd had one of the first doses that morning stopped in for a flat white.",
             "Drew up the Regatta Week roster: three extra shifts each for Teuila and Wiremu"]),
    "josh": dict(
        age=41, arc=None, people=["Wei-Ling Chen, who owns the noodle bar on Harbour Road"],
        problem="He wires shops for a living, and under a Yes every one of them could need someone on the door.",
        covid="Work dried up for most of a year.", lines=[],
        now=["The midweek squall brings a run of callouts, including a tripped board at Faisal's dairy"]),
})


def merged(chars):
    """Re-merge with `chars` as the characters module; the caller restores the real merge."""
    content.merge_playbook(craft, voices, chars)


def restore():
    content.merge_playbook(craft, voices, real_characters)


def test_merge_frames_have_craft_fields():
    assert len(content.FRAMES) == 12
    for key, f in content.FRAMES.items():
        assert f["pillar"] in content.PILLARS and f["pillar"] == craft.CRAFT[key]["pillar"]
        assert f["stakes"] and f["asks"] and f["heat"], key
        assert f["stakes"] is not craft.CRAFT[key]["stakes"]           # a copy, never the data module's list
        assert {"angle", "facts", "weight", "second"} <= set(f)         # v1 fields kept


def test_merge_personas_have_register_and_character_fields():
    for p in content.PERSONAS:
        assert p["register"] in content.VOICES and p["register"] == voices.VOICE_OF[p["key"]]
        assert p["voice"]                                               # v1 style words stay
        for k in content.CHARACTER_FIELDS:
            assert k in p
        assert isinstance(p["people"], list) and isinstance(p["now"], list)


def test_candidates_stay_out_of_personas():
    keys = {p["key"] for p in content.PERSONAS}
    assert len(keys) == 20 == len(content.PERSONA_BY_KEY)
    for c in getattr(real_characters, "CANDIDATES", []):
        assert c["key"] not in keys


def test_merge_never_mutates_data_modules():
    before = copy.deepcopy((craft.PILLARS, craft.CRAFT, voices.VOICES, voices.VOICE_OF, FAKE.CHARACTERS))
    try:
        merged(FAKE)
        for p in content.PERSONAS:
            for fk in FRAME_KEYS:
                content.system_prompt(p, fk, meta={})
                content.post_prompt(fk, HEADLINE, meta={}, persona=p)
        content.PERSONA_BY_KEY["lani"]["people"].append("x")
        content.FRAMES["F1_blank_cheque"]["stakes"].append("x")
    finally:
        restore()
    assert before == (craft.PILLARS, craft.CRAFT, voices.VOICES, voices.VOICE_OF, FAKE.CHARACTERS)


def test_fallback_without_playbook():
    try:
        content.merge_playbook(None, None, None)
        assert all(p["register"] == "warm" and p["people"] == [] for p in content.PERSONAS)
        s = content.system_prompt(P["lani"], "F7_livelihoods")
        assert "cheerful and reasonable" in s and "People in your life" not in s
        u = content.post_prompt("F7_livelihoods")
        assert "#KeepKingstoniaOpen" in u or "#SmallBusiness" in u or "#WorkersRights" in u
    finally:
        restore()


def test_post_shapes_contract():
    assert len(content.POST_SHAPES) == len(content.POST_SHAPE_KEYS) == 9
    assert len(set(content.POST_SHAPE_KEYS)) == 9 and content.POST_SHAPE_KEYS[-1] == "news"
    assert "{headline}" in content.POST_SHAPES[-1]
    assert not any("{" in s for s in content.POST_SHAPES[:-1])
    assert set(content.HOOKS) == set(content.POST_SHAPE_KEYS)
    for s in content.POST_SHAPES[:-1]:                                   # no scenery openings left
        assert "scenery" not in s and "cheerful bit of island life" not in s
    p = batch.pack([dict(mode="post", rec={"persona": "ben"}, frame="F5_not_here_yet")], headline=HEADLINE,
                   rng=random.Random(0))
    assert "Shape: " in p.user                                           # batch.py still reads the list


def test_shape_selection_rules():
    random.seed(1)
    seen = {k: set() for k in ("none", "lani", "josh")}
    for _ in range(400):
        seen["none"].add(content.pick_shape("F10_staff_and_livelihoods")[0])
        seen["lani"].add(content.pick_shape("F10_staff_and_livelihoods", persona=P["lani"])[0])
        seen["josh"].add(content.pick_shape("F10_staff_and_livelihoods", persona=P["josh"])[0])
    assert "fed_up" not in seen["none"] | seen["lani"] and "fed_up" in seen["josh"]
    assert "defiance" not in seen["josh"] and "news" not in seen["none"]
    assert len(seen["lani"]) == 7
    assert all(content.pick_shape("F8_powers")[0] != "number" for _ in range(200))  # no number in its facts
    assert content.pick_shape("F1_blank_cheque", shape="conversion")[0] == "conversion"
    assert content.pick_shape("F1_blank_cheque", shape=content.POST_SHAPES[1])[0] == "named_loss"
    assert content.pick_shape("F1_blank_cheque", shape="Say something.")[0] == "custom"


def test_post_meta_valid_and_in_prompt():
    random.seed(2)
    beats, closes = {}, {}
    for i in range(300):
        fk = FRAME_KEYS[i % 12]
        meta = {}
        u = content.post_prompt(fk, HEADLINE if i % 3 == 0 else None, meta=meta, persona=content.PERSONAS[i % 12])
        f, pillar = content.FRAMES[fk], content.PILLARS[content.FRAMES[fk]["pillar"]]
        assert meta["shape"] in content.POST_SHAPE_KEYS and meta["hook"] == content.HOOKS[meta["shape"]]
        assert meta["pillar"] == f["pillar"] and meta["frame"] == fk
        assert meta["tag"] in pillar["tags"] and u.rstrip().endswith(f"{meta['tag']}, and nothing after it.")
        assert meta["stake"] in f["stakes"] and (meta["ask"] in f["asks"]) == (meta["ask_kind"] == "frame")
        assert meta["slogan"] is None                                      # no theme given, no slogan
        assert not any(s in u for s in content.SLOGANS)
        _, lo, hi = experiment.LENGTH_BANDS["post"][meta["length_band"]]
        assert "voting No" in u and f"between {lo} and {hi} words" in u and "characters" not in u
        assert ("8 words or fewer" in u) == meta["concede"]
        # one beat of stake / lever / turning point (todo/14); the lever is logged only when it is in the prompt
        assert (meta["lever"] is not None) == (meta["beat"] == "lever")
        assert meta["lever"] is None or content.LEVERS[meta["lever"]] in u
        assert ("turning point" in u) == (meta["beat"] == "turn") and ("never these words" in u) == (meta["beat"] == "stake")
        beats[meta["beat"]] = beats.get(meta["beat"], 0) + 1
        assert ("Use one fact" in u) == (not meta["concede"] and meta["shape"] not in content.NO_FACT_SHAPES)
        if meta["ask_kind"] == "none":
            assert meta["close"] is None and not meta["closing_question"] and "real question" not in u
            continue
        end = "real question" if meta["ask_kind"] == "frame" else experiment.ASK_KINDS[meta["ask_kind"]][len("End with one "):]
        if meta["shape"] == "confession":                                # its opening carries the No
            assert "say plainly" not in u and "voting No anyway" in u
            continue
        if meta["close"] == "verdict_last":
            assert not meta["closing_question"] and u.index(end) < u.index("say plainly") < u.index("hashtag")
        else:
            assert meta["closing_question"] and u.index("say plainly") < u.index(end) < u.index("hashtag")
        closes[meta["close"]] = closes.get(meta["close"], 0) + 1
    assert set(beats) == {"stake", "lever", "turn"} and beats["lever"] > 60, beats
    assert 0.1 < closes["verdict_last"] / sum(closes.values()) < 0.4, closes


def test_resort_stake_never_offered():
    for _ in range(100):
        meta = {}
        content.post_prompt("F1_blank_cheque", meta=meta)
        assert "resort" not in meta["stake"].lower()


def test_old_callers_work_untouched():
    for p in content.PERSONAS:
        for fk in FRAME_KEYS:
            assert content.system_prompt(p, fk)
    for fk in FRAME_KEYS:
        assert content.post_prompt(fk)
        assert content.post_prompt(fk, HEADLINE, ask=True)
        assert content.reply_prompt("need an end date first", fk, ["end date"], "Some news")
        assert content.second_voice_prompt("which places are on the list?", fk, [], None)
        assert content.post_prompt(fk, shape=content.POST_SHAPES[0]).count("Open with a question") == 1
    assert content.journalist_prompt(3, "a story") and content.journalist_prompt(99, "a story")
    assert content.reply_back_prompt("ours", "theirs")
    assert content.reply_prompt("x", "F1_blank_cheque", [], opener=content.OPENERS[0])


def test_system_prompt_rules():
    for p in content.PERSONAS:
        s = content.system_prompt(p, "F3_provax_antipass")
        assert "vaccine safety or side effects" in s and "never at voters" in s
        assert content.JAB_RULE in s and "nobody has had it" in s
        assert (content.JAB_FIRST_LOT in s) == (p["key"] in {"ana", "sione", "ruth", "priya"})
        assert (content.JAB_WAIT in s) == (p["key"] not in {"ana", "sione", "ruth", "priya"})
        assert "Never name a day or date for the vote or say how or where to vote." in s
        assert "No hashtags, emojis" not in s and content.TAG_RULE in s
        assert "Don't open with" in s and "Exactly" in s
        assert "cheerful and reasonable, never angry" not in s
        assert content.VOICES[p["register"]]["instruction"] in s
        for ex in content.VOICES[p["register"]].get("examples", []):
            assert ex["text"][:40] not in s                              # gold examples never pasted


def test_fed_up_gets_heat_and_others_dont():
    for fk in FRAME_KEYS:
        heat = content.FRAMES[fk]["heat"]
        for key in ("josh", "ben", "tomasi"):
            meta = {}
            assert heat in content.system_prompt(P[key], fk, meta=meta) and meta["heat"] is True
        for key in ("lani", "priya", "isla", "ana"):
            meta = {}
            assert heat not in content.system_prompt(P[key], fk, meta=meta) and meta["heat"] is False


def test_character_profile_and_jab_filter():
    random.seed(4)
    try:
        merged(FAKE)
        for _ in range(40):
            meta = {}
            s = content.system_prompt(P["lani"], "F7_livelihoods", meta=meta)
            assert s.startswith(f"{content.WORLD}\nYou are Lani Moana, 38 (") and "People in your life: " in s
            assert "This fortnight: Drew up the Regatta Week roster" in s and "first doses that morning" not in s
            assert meta["now"].startswith("Drew up") and meta["voice"] == "warm" and meta["people"]
            assert all(name in ("Teuila", "Uncle Feleti", "Sina") for name in meta["people"])
            assert len(s) <= content.SYSTEM_BUDGET + 200
        u = content.post_prompt("F14_no_yes_but", shape="conversion", persona=P["lani"])
        assert "Your own turning point: She meant to stay out of it" in u
        assert content.usable(["A nurse who'd had one of the first doses.", "Fine."]) == ["Fine."]
        assert content.usable(["The first doses landed this week.", "He and Salote had theirs.", "Fine."], now=True) \
            == ["Fine."]
        assert content.usable(["The first doses landed this week."]) == ["The first doses landed this week."]
        for p in content.PERSONAS:                                       # personas without data still render
            assert content.system_prompt(p, "F1_blank_cheque")
    finally:
        restore()


def test_real_now_events_respect_jab_timing():
    random.seed(6)
    for p in content.PERSONAS:
        for _ in range(30):
            meta = {}
            s = content.system_prompt(p, "F7_livelihoods", meta=meta)
            assert meta["now"] is None or not content._NOW_OFF.search(meta["now"])
            assert "resort" not in s.split("\n")[0].lower()


def test_system_prompt_length():
    """Real data, every persona x frame: within the budget (the fixed rules + voice part is ~2,200 on its own)."""
    random.seed(5)
    for p in content.PERSONAS:
        for fk in FRAME_KEYS:
            assert len(content.system_prompt(p, fk)) <= content.SYSTEM_BUDGET + 200, (p["key"], fk)


def test_clip():
    assert content.clip("Short one", 75) == "Short one."
    assert content.clip("One sentence here. Then a much longer second one that will not fit at all.", 30) == \
        "One sentence here."
    out = content.clip("Uncle Feleti, a retired ferry engineer who has had the corner table by the window", 60)
    assert len(out) <= 61 and out.endswith(".") and not out.endswith(" the.")


def test_replies_new_shape():
    assert not any("same thing" in o for o in content.OPENERS)
    assert len(content.OPENERS) == 4, "the concession opener went on 23 Oct (hidden 3.9% vs 1.4%)"
    assert "8 words or fewer" in content.REPLY_RULES and "rhetorical" in content.REPLY_RULES
    for i in range(30):
        meta = {}
        r = content.reply_prompt("only if they publish the list", "F14_no_yes_but", ["list"], meta=meta,
                                 persona=content.PERSONAS[i % 12])
        ask = content.REPLY_ASK_NONE if meta["ask_kind"] == "none" else experiment.ASK_KINDS[meta["ask_kind"]]
        assert "want the same thing" not in r and ask in r
        assert meta["reply_mode"] in experiment.REPLY_MODES and meta["length_band"] in ("short", "medium", "long")
        assert content.VOICES[content.PERSONAS[i % 12]["register"]]["reply_instruction"] in r
        assert meta["opener"] in content.OPENERS and meta["pillar"] == "A"
        meta = {}
        sv = content.second_voice_prompt("x", "F6_islands", [], meta=meta, persona=P["josh"])
        assert voices.VOICES["fed_up"]["reply_instruction"] in sv and meta["pillar"] == "B"
    bare = content.reply_prompt("x", "F1_blank_cheque", [])                              # no persona: no voice
    assert not any(v["reply_instruction"] in bare for v in content.VOICES.values())


def test_journalist_storylines_rotate():
    assert 4 <= len(content.STORYLINES) <= 6 and content.STORYLINE == content.STORYLINES[0][1]
    keys = []
    for _ in range(len(content.STORYLINES) * 2):
        meta = {}
        j = content.journalist_prompt(4, "Many locals are confused about what it covers.", meta=meta)
        assert "Muzhi" in j and "quote" in j and "12 words or fewer" in j
        keys.append(meta["storyline"])
    assert all(a != b for a, b in zip(keys, keys[1:]))
    assert set(keys) == {k for k, *_ in content.STORYLINES}


def test_catchphrase_in():
    cp = content.SLOGANS[0]
    assert content.catchphrase_in(f"Blah blah. {cp} What's yours? #VoteNo") == cp
    assert content.catchphrase_in("blah. don't know, vote no! what's yours") == "Don't know? Vote No."
    assert content.catchphrase_in("I don't know who'd vote no on that.") is None
    assert content.catchphrase_in("Nothing here.") is None


def test_shared_meta_dict_collects_both():
    meta = {}
    content.post_prompt("F9_parliament", meta=meta, persona=P["josh"])
    content.system_prompt(P["josh"], "F9_parliament", meta=meta)
    assert {"shape", "hook", "voice", "pillar", "stake", "tag", "slogan", "now", "heat"} <= set(meta)


def test_one_length_and_ending_instruction_per_prompt():
    """todo/14 contradiction audit: the voices carry no sentence counts, fact counts or endings, so the prompt's own
    length band and ending are the only ones (the fed-up reply said "two or three", second voices 1 or 2)."""
    counts = re.compile(r"\b(one|two|three|four|1|2|3|4) (or \w+ )?(short )?sentences?\b|\bone or two more\b", re.I)
    for name, v in content.VOICES.items():
        for field in ("instruction", "reply_instruction"):
            assert not counts.search(v[field]), (name, field)
            assert "question" not in v[field].lower(), (name, field)
    assert not re.search(r"\d", content.WORLD.replace("H2D2", ""))
    for p in content.PERSONAS[:12]:
        s = content.system_prompt(p, p["frames"][0])
        u = content.reply_prompt("not sure, the hospitals scare me", p["frames"][0], [], persona=p)
        v = content.second_voice_prompt("not sure, the hospitals scare me", p["frames"][0], [], persona=p)
        for prompt in (u, v):
            assert len(counts.findall(prompt)) == 1, (p["key"], counts.findall(prompt))
        # todo/20 G9 (2026-10-22): one cap in characters as well (Kimi keeps to characters, not word counts)
        assert u.count("characters") == 1 and f"{content.CHAR_CAP['reply']} characters at most" in u
        assert v.count("characters") == 1 and f"({content.CHAR_CAP['second_voice']} characters at most)" in v
        assert "one to three" not in s


PULSE = dict(id="abc12345", ts=1_790_000_000.0,
             hooks=[dict(text="Dr Singh calling gate checks a small hassle", ts=None)],
             no_shapes=["named worker + concrete inconvenience + the official's own words"],
             yes_lines=["memories of goodbyes over video call"], avoid=["blank cheque"])


def test_pulse_block_in_system_prompt_and_budget():
    """With a pulse: the block right after WORLD, within SYSTEM_BUDGET, its id in meta. Without: as before."""
    big = dict(PULSE, hooks=[dict(text="h" * 99, ts=None)] * 3, no_shapes=["n" * 139] * 3, yes_lines=["y" * 139] * 3,
               avoid=["a" * 39] * 3)
    for p in content.PERSONAS:
        for fk in FRAME_KEYS:
            random.seed(7)
            plain_meta = {}
            plain = content.system_prompt(p, fk, meta=plain_meta)
            random.seed(7)
            meta = {}
            s = content.system_prompt(p, fk, meta=meta, pulse=PULSE)
            block = content.pulse_block(PULSE)
            assert s.startswith(f"{content.WORLD}\n{block}\n") and s.replace(f"{block}\n", "", 1) == plain
            assert meta["pulse"] == "abc12345" and "pulse" not in plain_meta
            random.seed(7)
            assert len(content.system_prompt(p, fk, pulse=big)) <= content.SYSTEM_BUDGET + 200, (p["key"], fk)
    random.seed(7)
    assert content.system_prompt(P["lani"], "F1_blank_cheque", pulse=None) == \
        (random.seed(7) or content.system_prompt(P["lani"], "F1_blank_cheque"))


def test_pulse_parts():
    full = content.pulse_block(PULSE)
    assert "reacting to Dr Singh" in full and "what lands is named worker" in full
    assert "Yes side is pushing memories" in full and "don't use: blank cheque" in full
    hooks = content.pulse_block(PULSE, ("hooks",))
    assert "Dr Singh" in hooks and "Yes side" not in hooks and "what lands" not in hooks
    yes = content.pulse_block(PULSE, ("yes_lines",))
    assert "Yes side is pushing" in yes and "Dr Singh" not in yes
    assert content.pulse_block(None) == "" and content.pulse_block(dict(PULSE, yes_lines=[]), ("yes_lines",)) == ""
    meta = {}
    content.system_prompt(P["lani"], "F1_blank_cheque", meta=meta, pulse=dict(PULSE, yes_lines=[]),
                          pulse_parts=("yes_lines",))
    assert "pulse" not in meta                                           # nothing used: no id logged


def test_build_prompt_passes_recent_openings_to_replies_and_second_voices():
    """todo/20 via todo/22: our last openings reach the reply and second-voice prompts, so the model avoids them."""
    import types
    from swan_bot import bot
    recent = ["Honestly the sunset clause is the whole problem here.", "My nan ran a bakery for forty years."]
    tg = types.SimpleNamespace(headline=None)
    for mode in ("reply", "second_voice"):
        job = dict(mode=mode, rec=dict(persona=content.PERSONAS[0]["key"]), frame="F14_no_yes_but",
                   target=dict(post_id=1, author_id=500, body="Not sure about the vaccine pass, what about exemptions?"))
        _, _, user = bot.build_prompt(job, tg, recent_texts=recent)
        assert "Don't open the way our latest replies did" in user, mode
        _, _, plain = bot.build_prompt(dict(job, meta=None), tg)
        assert "Don't open the way our latest replies did" not in plain, mode


# ---- 2026-10-24 audit: a reply as Esther argued hospitals with a citizen who already opposed the pass ----------------
ALLY = ("Appreciate the hospital angle, but gating access isn't the fix. Vaccination should stay voluntary; we need "
        "testing and targeted protections plus better hospital support to keep Kingstonia safe.")
PCR = "The launch briefing put PCR capacity at a few hundred tests a day, so I wouldn't rely on the official numbers."


@pytest.mark.parametrize("mode", experiment.REPLY_MODES)
def test_a_citizen_who_opposes_the_pass_is_not_answered_as_a_yes_leaner(monkeypatch, mode):
    monkeypatch.setattr(config, "PIN", {"reply_mode": mode})
    meta = {}
    out = content.reply_prompt(ALLY, "F10_staff_and_livelihoods", [], PCR, meta=meta, persona=P["esther"], read=True,
                               hint="F10_staff_and_livelihoods")
    assert "fear for the hospitals" not in out and "Answer WHY they lean Yes" not in out
    assert "They haven't fully decided" not in out and content.ALLY_WHY in out
    assert meta["ally"] is True and meta["rebuttal"] is False
    other = {}
    yes = content.reply_prompt("I'm unsure, the hospitals were swamped last time.", "F10_staff_and_livelihoods", [],
                               meta=other, persona=P["esther"])
    assert "ally" not in other and content.ALLY_WHY not in yes


def test_the_mirror_reply_drops_the_fear_rebuttal_for_an_ally_and_keeps_it_for_the_rest():
    ally = content.mirror_prompt(ALLY, "F10_staff_and_livelihoods", [])
    other = content.mirror_prompt("I'm leaning Yes, the hospitals were swamped last time.", "F10_staff_and_livelihoods", [])
    assert "their reason is fear" not in ally and "their reason is fear" in other


@pytest.mark.parametrize("text,ally", [
    (ALLY, True), ("Nobody shouldn't be required to show papers for a bus ride.", True),
    ("I'm against the pass.", True), ("The choice stays yours, so a certificate is fine.", False),
    ("'No loss of choice' is a stretch if you can't get into your workplace or the gym.", True),
    ("We can't base policy on hypothetical benefits while ignoring the concrete costs.", True),
    ("I'm worried people get locked out of shops before the jabs arrive.", False),
    ("Vaccination is voluntary anyway, so I'm fine with it.", False), ("We need better hospitals.", False)])
def test_opposes_pass(text, ally):
    assert content.opposes_pass(text) is ally


def test_context_is_called_a_news_item_only_when_it_is_one():
    for build in (lambda **kw: content.reply_prompt("a worry about jobs", "F7_livelihoods", [], PCR, **kw),
                  lambda **kw: content.mirror_prompt("a worry about jobs", "F7_livelihoods", [], PCR, **kw),
                  lambda **kw: content.second_voice_prompt("a worry about jobs", "F7_livelihoods", [], PCR, **kw)):
        assert "this news item: <<<The launch briefing" in build()                 # the default: as before
        post = build(news=False)
        assert "news item" not in post and "by another neighbour" in post and PCR[:40] in post


def test_what_the_neighbour_post_says_happened_is_theirs_not_the_citizens():
    """2026-10-24 audit: "I know what you saw in the ward" to a citizen who had only answered the post's writer."""
    post = content.reply_prompt("having seen that struggle must be heavy", "F10_staff_and_livelihoods", [], PCR, news=False)
    assert "happened to its writer, never to the person you answer" in post
    assert "happened to its writer" not in content.reply_prompt("a worry", "F7_livelihoods", [], PCR)    # a news item: no


def test_replies_end_in_a_question_about_two_times_in_three_not_nine_in_ten():
    """Audit: 43% -> 67% of replies ended in a question after the asks were reworded; "none" now has weight 0.4."""
    none = 0
    for _ in range(600):
        meta = {}
        content.reply_prompt("only if they publish the list", "F14_no_yes_but", ["list"], meta=meta, persona=content.PERSONAS[0])
        none += meta["ask_kind"] == "none"
    assert 0.28 < none / 600 < 0.44


def test_a_reply_is_not_told_to_state_its_vote_but_a_post_is():
    for key in ("lani", "ana", "esther", "dan"):
        persona = P[key]
        post = content.system_prompt(persona, persona["frames"][0], mode="post")
        assert content.VOTE_SENTENCE.search(post)                            # a post still states its vote
        for mode in content.NO_VERDICT_MODES:
            reply = content.system_prompt(persona, persona["frames"][0], mode=mode)
            assert "as a settled fact" not in reply and "Say plainly that you're voting No" not in reply
    for register, voice in content.VOICES.items():
        assert content.VOTE_SENTENCE.search(voice["instruction"]), register       # every register has it to strip
        assert "voting No" not in content.VOTE_SENTENCE.sub("", voice["instruction"]), register


# ---- the reply answers the citizen first (2026-10-24 audit of six rows) -------------------------------------------
def _reply(target, **kw):
    meta = {}
    return content.reply_prompt(target, "F10_staff_and_livelihoods", [], meta=meta, persona=P["esther"], **kw), meta


def test_a_reply_is_told_to_take_up_the_citizens_point_before_its_angle():
    user, _ = _reply("I'd want the plan to show how access and safeguards work together.")
    assert content.ANSWER_FIRST in user and user.index(content.ANSWER_FIRST) > user.index("<<<")


def test_the_answer_why_line_needs_a_reason_to_answer():
    for _ in range(20):                                       # reply_mode is drawn: look at the reason_first draws
        plain, meta = _reply("I want the plan published before the vote.")
        if meta.get("reply_mode") == "reason_first":
            assert "Answer WHY they lean Yes" not in plain
            break
    for _ in range(40):
        fear, meta = _reply("I'm leaning Yes, the hospitals were swamped last time.")
        if meta.get("reply_mode") == "reason_first":
            assert "Answer WHY they lean Yes" in fear
            break


def test_an_ally_is_never_asked_a_closing_question():
    for _ in range(30):
        user, meta = _reply(ALLY)
        assert meta["ask_kind"] == "none" and content.REPLY_ASK_NONE in user


def test_no_ask_hands_the_model_a_sentence_to_copy():
    for kind, line in content.experiment.ASK_KINDS.items():
        assert "as they are today" not in line, kind
    assert not any("connects directly" in o for o in content.OPENERS)
    assert "relative, job, age or past that isn't in your profile" in content.REPLY_RULES


def test_the_read_is_told_to_stay_on_f14_when_the_keywords_say_it_and_the_rest_are_still_suggestions():
    f14 = content.read_block("F14_no_yes_but")
    assert "pick F14_no_yes_but" in f14 and "Hospitals coming up" in f14
    other = content.read_block("F10_staff_and_livelihoods")
    assert "A keyword match suggests F10_staff_and_livelihoods; pick another" in other and "pick F14" not in other
    assert "keyword match" not in content.read_block(None) and "pick F14" not in content.read_block(None)
