"""Prompt assembly (content.py, content v2): playbook data merged at import, post anatomy, shapes, voices, rules,
logging meta, replies and journalist storylines. Offline: prompts are rendered, never sent.

    python -m pytest tests/test_prompts.py -q
"""
import copy
import pathlib
import random
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from swan_bot import batch, content  # noqa: E402
from swan_bot.playbook import craft, voices  # noqa: E402

try:
    from swan_bot.playbook import characters as real_characters  # noqa: E402
except ImportError:
    real_characters = None

P = content.PERSONA_BY_KEY
FRAME_KEYS = list(content.FRAMES)
HEADLINE = "Schools brace for H2D2 rules"
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
    assert len(keys) == 12 == len(content.PERSONA_BY_KEY)
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
    assert all(content.pick_shape("F1_blank_cheque")[0] != "number" for _ in range(200))  # no number in its facts
    assert content.pick_shape("F1_blank_cheque", shape="conversion")[0] == "conversion"
    assert content.pick_shape("F1_blank_cheque", shape=content.POST_SHAPES[1])[0] == "named_loss"
    assert content.pick_shape("F1_blank_cheque", shape="Say something.")[0] == "custom"


def test_post_meta_valid_and_in_prompt():
    random.seed(2)
    catches = 0
    for i in range(300):
        fk = FRAME_KEYS[i % 12]
        meta = {}
        u = content.post_prompt(fk, HEADLINE if i % 3 == 0 else None, meta=meta, persona=content.PERSONAS[i % 12])
        f, pillar = content.FRAMES[fk], content.PILLARS[content.FRAMES[fk]["pillar"]]
        assert meta["shape"] in content.POST_SHAPE_KEYS and meta["hook"] == content.HOOKS[meta["shape"]]
        assert meta["pillar"] == f["pillar"] and meta["frame"] == fk
        assert meta["tag"] in pillar["tags"] and u.rstrip().endswith(f"{meta['tag']}, and nothing after it.")
        assert meta["stake"] in f["stakes"] and meta["ask"] in f["asks"]
        assert meta["catchphrase"] is None or (meta["catchphrase"] in pillar["catchphrases"]
                                               and meta["catchphrase"] in u)
        catches += meta["catchphrase"] is not None
        assert "voting No" in u and "240 and 420" in u
        assert ("8 words or fewer" in u) == meta["concede"] and content.LEVERS[meta["lever"]] in u
        assert u.index("voting No") < u.index("real question") < u.index("hashtag")
    assert 0.2 < catches / 300 < 0.45                                    # about one post in three


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
    assert len(content.OPENERS) == 5
    assert "8 words or fewer" in content.REPLY_RULES and "rhetorical" in content.REPLY_RULES
    for i in range(30):
        meta = {}
        r = content.reply_prompt("only if they publish the list", "F14_no_yes_but", ["list"], meta=meta,
                                 persona=content.PERSONAS[i % 12])
        assert "want the same thing" not in r and "question back about their own life" in r
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
    assert set(keys) == {k for k, _ in content.STORYLINES}


def test_catchphrase_in():
    cp = content.PILLARS["A"]["catchphrases"][0]
    assert content.catchphrase_in(f"Blah blah. {cp} What's yours? #VoteNo") == cp
    assert content.catchphrase_in("Nothing here.") is None


def test_shared_meta_dict_collects_both():
    meta = {}
    content.post_prompt("F9_parliament", meta=meta, persona=P["josh"])
    content.system_prompt(P["josh"], "F9_parliament", meta=meta)
    assert {"shape", "hook", "voice", "pillar", "stake", "tag", "catchphrase", "now", "heat"} <= set(meta)
