"""Quality gate: tags, numbers, consoling/rhetorical/hedging phrases, closing question, local detail, copied
sources, shape variety, and a labelled corpus (no network)."""
import importlib
import pathlib
import sys
import types

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from swan_bot import config, quality  # noqa: E402

# playbook §9 tomasi rewrite: the reference good post every single-reason variant below is built from
GOOD = ("Aunty Losa rides my ferry every Tuesday for the clinic. Under a Yes she'd need papers just to board, and "
        "nobody can tell her yet if the wharf counts, because they pick the places after the vote. She's had her jab. "
        "That isn't the point. Sign first, read later? Not me. I'm voting No. Who in your family rides that ferry? "
        "#KeepKingstoniaOpen")
GOOD_UNTAGGED = GOOD.rsplit(" #", 1)[0]


@pytest.fixture(autouse=True)
def _tagged_posts(monkeypatch):
    """These tests are about the tag machinery and the reference posts, which carry a hashtag beside "I'm voting No": the
    pre-todo/40 posts. The new default (no hashtag with the vote) is tested in tests/test_post_tag_vote.py."""
    monkeypatch.setattr(config, "POST_NO_TAG_WITH_VOTE", False)


def ok(text, kind="post", **kw):
    clean, why = quality.check(text, kind, **kw)
    assert clean, f"rejected ({why}): {text}"
    return clean


def bad(text, kind="post", **kw):
    clean, why = quality.check(text, kind, **kw)
    assert clean is None, f"passed but shouldn't: {text}"
    return why


@pytest.fixture
def playbook(monkeypatch):
    """Reload quality with fake swan_bot.playbook modules (dicts of attributes); None = module missing."""
    def load(craft=None, characters=None):
        pkg = types.ModuleType("swan_bot.playbook")
        pkg.__path__ = []
        monkeypatch.setitem(sys.modules, "swan_bot.playbook", pkg)
        for name, attrs in (("craft", craft), ("characters", characters)):
            full = f"swan_bot.playbook.{name}"
            if attrs is None:
                monkeypatch.setitem(sys.modules, full, None)        # import raises ImportError
                continue
            mod = types.ModuleType(full)
            mod.__dict__.update(attrs)
            setattr(pkg, name, mod)
            monkeypatch.setitem(sys.modules, full, mod)
        return importlib.reload(quality)
    yield load
    monkeypatch.undo()
    importlib.reload(quality)


# ---- existing behaviour ----

def test_reference_posts_pass():
    ok(GOOD)
    ok(GOOD_UNTAGGED)


def test_existing_rejects_unchanged():
    assert bad("") == "empty"
    assert bad("Sure! " + GOOD) == "llm_artefact"
    assert bad("fixed opening, different detail, different words. Same point: " + GOOD) == "llm_artefact"   # 22 Oct leak
    assert bad(GOOD.replace("Aunty Losa", "Marina Castillo")) == "forbidden_content"
    assert bad(GOOD.replace("Not me.", "Polls open at 8, so vote early.")) == "wrong_logistics"
    assert bad(GOOD.replace("She's had her jab.", "There are no exemptions.")) == "wrong_claim"
    assert bad(GOOD.replace("I'm voting No.", "I'm voting Yes.")) == "endorses_yes"
    assert bad(GOOD.replace("I'm voting No. ", "")) == "no_vote_statement"
    assert bad(GOOD.replace("She's had her jab.", "It's crucial.")) == "generic_phrase"
    assert bad(GOOD[:150] + "? I'm voting No.").startswith("length_")
    assert bad(GOOD.replace("ferry", "trip").replace("wharf", "pier").replace("clinic", "doctor")
               .replace("Aunty Losa", "My aunt")) == "no_local_detail"     # Aunty Losa is a character (tomasi)
    assert bad("Ta. Out here the ferry is the only way to the clinic.", "reply_back",
               recent_texts=["Ta. Out here the GP only comes once a week."]) == "same_opening"
    assert bad(GOOD, recent_texts=[GOOD_UNTAGGED.replace("Aunty Losa", "My aunt")]) == "near_duplicate"
    assert bad("Fair, but the trouble is the list comes later, and that's the bit worth asking about before any Yes.",
               "reply", recent_texts=["the trouble is nobody knows"]) == "repeat_stock_the_trouble_is"


# ---- 1. tags ----

def test_one_allowlisted_tag_at_end_passes_any_case():
    for tag in ("#VoteNo", "#voteno", "#H2D2No", "#KeepKingstoniaOpen", "#SmallBusiness", "#WorkersRights",
                "#ChoiceNotCoercion", "#ProtectKingstonia"):
        ok(f"{GOOD_UNTAGGED} {tag}")


def test_tag_reasons():
    assert bad(GOOD + " #VoteNo") == "too_many_tags"
    assert bad(GOOD.replace("#KeepKingstoniaOpen", "#h2d2")) == "tag_not_allowed"
    assert bad(GOOD.replace("#KeepKingstoniaOpen", "#VoteYesKingstonia")) == "tag_not_allowed"
    assert bad(GOOD_UNTAGGED.replace("Not me.", "Not me #VoteNo.")) == "tag_not_at_end"
    assert bad("Cheers. Out here the ferry is K$14 #VoteNo each way, and that's before anyone checks papers.",
               "reply_back") == "tag_in_reply"                     # a tag inside a reply; trailing ones are cut
    for kind in ("reply", "second_voice", "journalist", "thread", "thread_answer"):
        assert quality.tag_problem("a reply about the ferry #VoteNo", kind) == "tag_in_reply"
    assert bad(GOOD_UNTAGGED + " #") == "hashtag"


def test_tag_ignored_by_similarity():
    old = GOOD_UNTAGGED.replace("Aunty Losa rides", "Losa catches").replace("every Tuesday", "on Tuesdays") + " #VoteNo"
    assert quality.similar(quality.strip_tag(GOOD), quality.strip_tag(old)) > 0.25     # the words really are close
    assert quality.strip_tag(GOOD) == GOOD_UNTAGGED


def test_tag_allowlist_from_craft(playbook):
    q = playbook(craft=dict(TAG_ALLOWLIST={"#VoteNo"}))
    assert q.TAG_ALLOWLIST == {"#voteno"}
    assert q.check(GOOD, "post")[1] == "tag_not_allowed"
    assert q.check(GOOD_UNTAGGED + " #VoteNo", "post")[0]


def test_fallback_without_playbook(playbook):
    q = playbook()
    assert "#keepkingstoniaopen" in q.TAG_ALLOWLIST
    assert q.check(GOOD, "post")[0]


# ---- 2. numbers ----

PLAIN = ("Thirty ICU beds between Central and Crown Harbour, 40 empty nursing posts at Central, and the plan is "
         "{x} at the bakery door? I've had my jab and I'm voting No. What would actually help your ward?")


def test_true_in_game_numbers_pass():
    for x in ("a scanner", "1,000 deaths remembered and a scanner", "1,600 nurses, 420 doctors and a scanner",
              "150 surge beds and a scanner", "K$18 million of doses and a scanner", "600,000 of us and a scanner",
              "a K$5.50 flat white checked", "a K$14 ferry checked", "a scanner since 2024's ID card law"):
        ok(PLAIN.format(x=x))


def test_listed_percentages_pass_others_fail():
    for pct in ("36.2%", "29%", "51.28%", "9%"):
        ok(PLAIN.format(x=f"a poll at {pct} and a scanner"))
    # the 17 Oct poll (35.2% each) belongs to the retired `polls` fact: still a true figure, but its wording is out
    assert bad(PLAIN.format(x="a poll at 35.2% and a scanner")) == "paused_fact_polls"
    assert bad(PLAIN.format(x="a poll at 87% and a scanner")) == "unapproved_number_87%"
    assert bad(PLAIN.format(x="a poll at 35% and a scanner")) == "unapproved_number_35%"


def test_made_up_numbers_still_fail():
    assert bad(PLAIN.format(x="500 nurses and a scanner")) == "unapproved_number_500"
    assert bad(PLAIN.format(x="a scanner like 2020")) == "unapproved_number_2020"
    ok(PLAIN.format(x="a scanner for 7 shops"))                       # 0-12 always fine


def test_vote_dates_in_any_form_are_logistics():
    for s in ("I'm voting No on the 2nd.", "Polling is the 2nd of November.", "See you November 2."):
        assert bad(GOOD.replace("I'm voting No.", "I'm voting No. " + s)) == "wrong_logistics", s


# ---- 3. consoling phrases, rhetorical questions, hedging the No, closing question ----

REPLY = ("{x} Off the ID card, paper proof, the list, a review date: none of those is in the question, so a Yes can't "
         "carry your but. Which one would you need in writing?")


def test_consoling_phrases_rejected():
    for x in ("I hear you.", "I understand your concern.", "That's fair.", "Fair point.", "Totally get it.",
              "I'd want that too.", "I'd want the same.", "I completely understand.", "Your concern is valid."):
        assert bad(REPLY.format(x=x), "reply") == "consoling_phrase", x
    assert bad(GOOD.replace("She's had her jab.", "I hear you, she's had her jab.")) == "consoling_phrase"


def test_ordinary_concessions_pass():
    for x in ("Fair enough.", "I respect that.", "Four good conditions.", "Is that fair to her?"):
        ok(REPLY.format(x=x), "reply")


def test_rhetorical_questions_rejected_anywhere():
    for q in ("Can we really trust a blank cheque?", "How can anyone plan a shift like that?",
              "Do we really want papers at the bakery?", "Isn't it time we said so?", "What could go wrong?"):
        assert bad(GOOD_UNTAGGED.replace("Sign first, read later?", q)) == "rhetorical_question", q
        assert bad(REPLY.format(x=q), "reply") == "rhetorical_question", q


def test_punchy_questions_pass():
    for q in ("Why the hurry?", "Why won't they show us the list?", "Who builds like that?", "Sign first, read later?"):
        ok(GOOD_UNTAGGED.replace("Sign first, read later?", q))
    ok(GOOD.replace("Not me.", "We can really do better. Not me."))      # the words, but not a question
    ok(GOOD.replace("Who in your family rides that ferry?", "How can we get the jab out to the islands faster?"))
    assert bad(GOOD.replace("Sign first, read later?", "How can we trust that?")) == "rhetorical_question"


def test_consoling_needs_the_speaker():
    ok(GOOD.replace("She's had her jab.", "They completely get it wrong about her."))
    ok(GOOD.replace("She's had her jab.", "That's not fair on her."))
    assert bad(GOOD.replace("She's had her jab.", "She's had her jab. Totally get it.")) == "consoling_phrase"


def test_hedging_the_no_rejected():
    for h in ("I'm still deciding, but I'm voting No.", "I'm on the fence, voting No for now.",
              "I'm probably voting No.", "I might vote No.", "I haven't decided, but I'm voting No."):
        assert bad(GOOD.replace("I'm voting No.", h)) == "hedges_no", h
    assert bad(REPLY.format(x="I'm leaning No myself."), "reply") == "hedges_no"


def test_talking_to_undecided_readers_is_not_hedging():
    for h in ("Still deciding? I'm voting No.", "If you're on the fence, fine. I'm voting No.",
              "I was on the fence until I read it. I'm voting No.", "Undecided or leaning Yes? I'm voting No.",
              "I'm not sure yet which doors count, nobody is. I'm voting No."):
        ok(GOOD.replace("I'm voting No.", h))


def test_thread_pushback_may_voice_a_doubt():
    ok("I'm still torn about Central's 40 empty nursing posts. What happens there if it arrives?", "thread")


def test_post_must_end_with_a_question():
    no_q = GOOD_UNTAGGED.replace(" Who in your family rides that ferry?", " Nobody should need a permit to board.")
    assert bad(no_q) == "no_closing_question"
    assert bad(no_q + " #VoteNo") == "no_closing_question"
    ok(GOOD)                                                             # question, then the one tag
    ok(GOOD_UNTAGGED)
    ok(REPLY.format(x="Four good conditions.").replace(" Which one would you need in writing?", ""), "reply")


def test_closing_question_switch(monkeypatch):
    monkeypatch.setattr(quality, "REQUIRE_CLOSING_QUESTION", False)
    ok(GOOD_UNTAGGED.replace(" Who in your family rides that ferry?", " Nobody should need a permit to board."))


def test_ages_and_story_durations_are_not_statistics():
    ok(GOOD.replace("Aunty Losa rides", "Aunty Losa takes her 13-year-old grandson and rides"))
    ok(GOOD.replace("She's had her jab.", "She's had her jab, and her stall's been at the market 30 years."))
    ok(GOOD.replace("She's had her jab.", "Her 19 year old has had his jab."))
    assert bad(GOOD.replace("She's had her jab.", "She's had her jab, like 87 others.")) == "unapproved_number_87"
    assert bad(GOOD.replace("She's had her jab.", "Ask the 25 years of data.")) == "unapproved_number_25"


# ---- 4. local detail: built-in words, plus the characters' people and places ----

NO_LOCAL = ("My neighbour asked me last night whether she'd need papers to get to work. Honest answer: nobody knows, "
            "because nobody has seen the list. I've had my jab. Sign first, read later? Not me. I'm voting "
            "No. What would you need to see first?")
FAKE_CHARACTERS = dict(CHARACTERS={"lani": dict(
    age=34, people=["Mele, her 15-year-old niece who helps on Saturdays", "Uncle Viliami, who fixes the espresso machine"],
    problem="", covid="", arc=None, lines=[],
    now=["Mele's netball final at the Tofua courts", "A Yes stall outside St Peter's on Sunday",
         "Hawthorne on the radio again"])})


def test_new_builtin_local_words():
    assert bad(NO_LOCAL) == "no_local_detail"
    for w in ("bakery", "market stall", "netball", "church", "village", "ring road", "jetty", "library"):
        ok(NO_LOCAL.replace("get to work", f"get to the {w}"))
    ok(NO_LOCAL.replace("get to work", "get to her shift at Central"))
    assert bad(NO_LOCAL.replace("get to work", "get to the central office")) == "no_local_detail"


def test_character_people_and_places_count_as_local(playbook):
    q = playbook(characters=FAKE_CHARACTERS)
    assert {"Mele", "Viliami", "Tofua"} <= q.LOCAL_NAMES
    assert not {"Yes", "Hawthorne", "Sunday", "Saturdays", "Uncle"} & q.LOCAL_NAMES
    for who in ("Mele", "Uncle Viliami", "Viliami"):
        assert q.check(NO_LOCAL.replace("My neighbour", who), "post")[0], who
    assert q.check(NO_LOCAL.replace("get to work", "get to the Tofua courts"), "post")[0]
    assert q.check(NO_LOCAL.replace("My neighbour", "Hawthorne"), "post")[1] == "no_local_detail"


def test_local_names_also_read_from_merged_personas():
    names = quality._local_names(None, [dict(people=["Aunty Losa, who rides the ferry"], now=["Lunch at Pua's stall"])])
    assert {"Aunty Losa", "Losa", "Pua"} <= names


def test_local_names_skip_common_words():
    assert not {"She", "He", "People", "Week", "Year", "City"} & quality.LOCAL_NAMES
    assert "Aunty Losa" in quality.LOCAL_NAMES or not quality._CHARS


def test_local_check_without_characters(playbook):
    q = playbook()
    # content.py merges character profiles onto PERSONAS itself, so only names from the module are absent
    assert q.LOCAL_NAMES == q._local_names(None, quality.content.PERSONAS) | {"Central", "Mango & Spice"}
    assert q.check(NO_LOCAL, "post")[1] == "no_local_detail"


# ---- 5. copied-fact sources: craft stakes/heat and character lines; catchphrases and REPEATABLE exempt ----

FAKE_CRAFT = dict(
    TAG_ALLOWLIST={"#voteno", "#keepkingstoniaopen"},
    PILLARS={"A": dict(tags=["#VoteNo"])},
    THEMES={"t": dict(slogan="If they won't show you the list, vote No.", belief="the list comes after the vote")},
    CRAFT={"F6_islands": dict(
        pillar="B",
        stakes=["A gran riding the ferry to her clinic visit can't find out yet whether the wharf counts, because "
                "they pick the places after the vote."],
        heat="Out here the GP comes once a week, the ferry is K$14, and they still won't say whether the wharf counts.",
        asks=["Who in your family rides that ferry most weeks?"])},
    REPEATABLE=["nobody can tell her yet if the wharf counts"])
FAKE_LINES = dict(CHARACTERS={"tomasi": dict(people=[], now=[], lines=[
    "I've carried half this island across that water and never once asked anyone for papers."])})
STORY = ("Aunty Losa rides my ferry every Tuesday for the clinic over on the outer islands. {x} She's had her jab, "
         "and under a Yes she'd still need papers just to board. I'm voting No. "
         "Who in your family rides that ferry?")


def test_copying_a_stake_heat_or_line_is_rejected(playbook):
    q = playbook(craft=FAKE_CRAFT, characters=FAKE_LINES)
    for x in ("Can't find out yet whether the wharf counts, because they pick the places after the vote.",
              "The GP comes once a week, the ferry is K$14, and they still won't say.",
              "I've carried half this island across that water and never once asked."):
        assert q.check(STORY.format(x=x), "post")[1] == "copied_fact", x
    assert q.check(STORY.format(x="Nobody will say if the wharf is on the list, and the GP only visits weekly."),
                   "post")[0]


def test_catchphrases_and_repeatable_lines_may_repeat(playbook):
    q = playbook(craft=FAKE_CRAFT, characters=FAKE_LINES)
    for x in ("If they won't show you the list, vote No.",                 # 9-word catchphrase
              "Nobody can tell her yet if the wharf counts, so who knows.",  # craft REPEATABLE
              "They pick the places after the vote, and the wharf counts for her."):   # built-in REPEATABLE
        assert q.check(STORY.format(x=x), "post")[0], x
    assert q.check(GOOD, "post")[0]          # the playbook rewrite shares "the wharf counts, because they pick..."


def test_builtin_catchphrases_without_playbook(playbook):
    q = playbook()
    assert "Baristas, not border guards." in q.CATCHPHRASES and len(q.CATCHPHRASES) == 5
    assert q.copied_runs("Don't know? Vote No. Baristas, not border guards.") == set()
    c = quality.content                       # content.py may merge craft/characters itself; nothing else counts
    own = ([f["text"] for f in c.fact_store.TABLE.values()] + [f["angle"] for f in c.FRAMES.values()] +
           [s for f in c.FRAMES.values() for s in q._texts(f.get("stakes")) + q._texts(f.get("heat"))] +
           [s for p in c.PERSONAS for s in q._texts(p.get("lines"))])
    assert set(q.SOURCES) == set(own)


def test_copied_runs_keeps_ordinary_runs():
    assert "one two three four five six seven" in quality.copied_runs("one two three four five six seven")



# ---- 6. shape variety ----

def test_shape_ok():
    assert quality.shape_ok("conversion", [])
    assert quality.shape_ok("conversion", ["conversion"])
    assert not quality.shape_ok("conversion", ["conversion", "loss", "conversion"])
    old = ["conversion", "conversion"] + ["loss", "trade"] * 4 + ["number"]          # 11 posts
    assert len(old[-9:]) == 9 and quality.shape_ok("conversion", old)             # both uses fell out of the window
    assert not quality.shape_ok("loss", old)
    assert quality.shape_ok(None, ["x"] * 10)
    assert quality.shape_ok("loss", ["loss"] * 3, max_uses=4)
    assert not quality.shape_ok("loss", ["loss"], window=3, max_uses=1)


def test_past_timeline_dates_are_not_logistics():
    ok(GOOD.replace("She's had her jab.", "The Assembly threw it out on 15 Oct."))
    ok(GOOD.replace("She's had her jab.", "The bill went in on 9 October and was dead by 17 Oct."))
    for d in ("Early voting starts 28 Oct.", "It all comes down to 2 Nov.", "Vote on 1 November."):
        assert bad(GOOD.replace("She's had her jab.", d)) == "wrong_logistics", d


# ---- corpus: labelled drafts (playbook §5/§9 rewrites and originals, persona posts, single-reason fails) ----
# (id, kind, text, expected reason prefix or None = must pass, check kwargs)
CORPUS = [
    ('pb9_tomasi', 'post',
     "Aunty Losa rides my ferry every Tuesday for the clinic. Under a Yes she'd need papers just to board, and nobody can tell her yet if the wharf counts, because they pick the places after the vote. She's had her jab. That isn't the point. Sign first, read later? Not me. I'm voting No. Who in your family rides that ferry? #KeepKingstoniaOpen",
     None, {}),
    ('pb9_grace', 'post',
     "Sailing club on Saturday: a dozen kids rigging boats on the lagoon. Under a Yes, every one of them over 12 needs a certificate to walk into school on Monday, and nobody can say yet which other doors count. I'm vaccinated and I'll teach anyone's kid. Twelve is too young to need papers for maths. I'm voting No. Parents, what would you tell them? #KeepKingstoniaOpen",
     None, {}),
    ('pb5_anatomy', 'post',
     "Sailing club on Saturday, and one of my Year 8s asked if she'd still be allowed in class. She's 12. Under a Yes she'd need papers to walk into school on Monday, and to ride the bus there. And nobody can tell her which doors count: they pick the places after we vote. I'm vaccinated, and I'll teach anyone's kid. But twelve is too young to need papers for maths. I'm voting No. Parents, what would you tell her? #KeepKingstoniaOpen",
     None, {}),
    ('pb9_mere_reply', 'reply',
     'Off the ID card, paper proof, the list, a review date: four good conditions. I read the question twice and not one of them is on it, so a Yes can\'t carry your "but". Which one would you need in writing before you\'d vote Yes?',
     None, {'target_text': "I'm leaning yes but only if they keep vaccine records off the id card, offer paper proof, publish the venue list and set a review date."}),
    ('pb9_josh_edit', 'post',
     "So let me get this straight. The Assembly threw this out last week, and Hawthorne's own people voted against it. Now they want us to sign it instead, before they'll show us which doors it covers or when it ends. I wire half the shops in Kingstonia City and can't tell one owner if his door counts. If they won't show you the list, vote No. Which door would you want to know about first? #VoteNo",
     None, {}),
    ('ana_number', 'post',
     "Forty. That's how many nursing posts are empty at Central, because nurses can earn double in Australia or NZ. I work nights on one of those short wards and I've had every jab going. A scanner at the bakery door won't put one more nurse on my shift. I'm voting No. Who do you know who's gone nursing overseas? #WorkersRights",
     None, {}),
    ('ben_fedup', 'post',
     "Out on the boat before dawn, back at the New Haven market by eight. Under a Yes I'd be asking my regulars for papers before I sell them a tuna, and nobody will say if the market even counts. There's no community spread here yet. Why the hurry? I'm voting No. What's the first stall you hit on a Saturday?",
     None, {}),
    ('lani_trade', 'post',
     "Two staff, both students, and one of them would end up on my cafe door by the Crown Harbour wharf checking papers instead of making flat whites. Half my trade comes off the boats, and visitors would need a certificate too. We remember what the last closures did to small shops. I'm voting No. Who's the one person your favourite local shop couldn't run without? #SmallBusiness",
     None, {}),
    ('priya_jabbed', 'post',
     "Every day someone at my counter asks about H2D2. My answer: get the jab, it's free either way, and a No doesn't stop a single dose. I'm vaccinated and I'll get this one too. But this vote is only about the pass, and a pass at every shop door is a different thing. Jabbed. Voting No. When your turn comes, who are you taking with you? #ChoiceNotCoercion",
     "vaccine_advocacy", {}),          # todo/20 (2026-10-22): "get the jab" is advocacy until organiser Q3 is answered
    ('sione_islands', 'post',
     "The GP visits my clinic once a week, and most of my patients come over on the K$14 ferry. Under a Yes they'd need papers to board, and nobody can say yet if the wharf counts. Free is not the same as easy out here. I'm voting No. How long does it take you to reach the nearest GP, door to door?",
     None, {}),
    ('isla_plain', 'post',
     "law student, so i read the question twice. no end date. no list of places, that comes later by regulation. a binding Yes, and a No holds for the life of this Assembly. i catch the loop bus to campus every day and i'd need papers for it. No list. No end date. No deal. i'm voting No. what would you need in writing first?",
     None, {}),
    ('dan_conversion', 'post',
     "I was a Yes until I read what we're actually voting on. I drive the city loop past the hospital, and under a Yes I'd be the one checking papers before anyone sits down, at stops nobody has even listed yet. Thirty ICU beds is a real worry. A scanner on my bus fills none of them. I'm voting No. What changed your mind, if anything did?",
     None, {}),
    ('thread_oneliner', 'thread',
     'Forty empty posts at Central and they want a scanner on the ferry. Right.',
     None, {}),
    ('thread_pushback', 'thread',
     "I'm still torn about the hospitals, honestly. If it does arrive, what stops Central filling up?",
     None, {}),
    ('reply_back_thanks', 'reply_back',
     "Cheers. The ferry's K$14 each way for her, so a wasted trip because of papers really stings.",
     None, {}),
    ('journalist', 'journalist',
     "Central has forty empty nursing posts, and a scanner at the bakery door won't fill one. That's why so many vaccinated people I know are voting No: the places it covers only get picked after the vote.",
     None, {}),
    ('pb9_tomasi_before', 'post',
     "Fresh mango and hot scones at the Saturday market always start my day right before I cast off on the morning ferry. We don't need papers at the door for the little things that make Kingstonia home. The jab stays free and your choice either way no matter what. Keeping us open matters, so I am voting No.",
     'no_closing_question', {}),
    ('pb9_mere_before', 'reply',
     'I would want those safeguards too when hospitals are stretched thin, but none of them are in the ballot question. A yes vote binds us permanently without an end date, review or even the list of places. Can we really trust a blank cheque?',
     'consoling_phrase', {}),
    ('pb9_josh_verbatim', 'post',
     "So let me get this straight. The Assembly threw this out last week, and Hawthorne's own people voted against it. Now they want us to sign it instead, before they'll show us which doors it covers or when it ends. Why the hurry? If they won't show you the list, vote No. #VoteNo",
     'no_local_detail', {}),
    ('pb5_oneliner', 'post',
     "Jabs booked for all three, same as every year. Still don't want my youngest turned away from assembly over a form.",
     'length', {}),
    ('rhetorical', 'post',
     "Waiting for the morning ferry with half the village, and nobody can tell us whether the wharf will need papers under a Yes. They pick the places after the vote. I've had my jab and I'm voting No. Do we really want a checkpoint at every jetty in Kingstonia?",
     'rhetorical_question', {}),
    ('hedge', 'post',
     "Waiting for the morning ferry with half the village, and nobody can tell us whether the wharf will need papers under a Yes. They pick the places after the vote. I've had my jab and I'm probably voting No, for now anyway. Which jetty would you want left off the list?",
     'hedges_no', {}),
    ('two_tags', 'post',
     "Waiting for the morning ferry with half the village, and nobody can tell us whether the wharf will need papers under a Yes. They pick the places after the vote. I've had my jab and I'm voting No. Which jetty would you want left off the list? #VoteNo #H2D2No",
     'too_many_tags', {}),
    ('made_up_stat', 'post',
     "Waiting for the morning ferry with half the village, and nobody can tell us whether the wharf will need papers under a Yes. 87% of the island is against it. I've had my jab and I'm voting No. Which jetty would you want left off the list?",
     'unapproved_number', {}),
    ('vote_date', 'post',
     "Waiting for the morning ferry with half the village, and nobody can tell us whether the wharf will need papers under a Yes. They pick the places after the vote. I've had my jab and I'm voting No on the 2nd. Which jetty would you want left off the list?",
     'wrong_logistics', {}),
    ('reply_tag', 'reply',
     "Off the ID card and a review date: neither is on the #VoteNo question, so a Yes can't carry them. Which would you need in writing?",
     'tag_in_reply', {}),
]
# the 10 trending study posts (other teams', 2026-10-20), verbatim, with the reason our gate rejects them
STUDY = {
    '57396': ('no', 'unapproved_number_2020',
              "In 2020 I folded bookplates in the Friends room and counted the weeks until the library doors reopened. At least we were counting toward something. This time nobody has promised a finish line or a review, a Yes binds the government, and the list of places comes later by regulation. I had my H2D2 shot the first day I could, and I'm still marking No. If you're leaning Yes, I understand why. Where would you want the end written down?"),
    '55977': ('no', 'too_many_tags',
              "Funny thing about 2020: the nurses riding my 14:10 home off double shifts never needed a pass to sit down. Now a Yes would be binding, and nobody has said where an end date would be written or which places get listed. That's left for regulations later. Jabbed last week, five minutes, and my vote is still No. Undecided or leaning Yes? I respect that. Yes, No or not sure yet? #h2d2 #kingstonia"),
    '54014': ('no', 'too_many_tags',
              "Voting No, and I'm fed up with how this is being sold. I got my jab at St Mary's and I keep encouraging my residents, because care should be offered. But the rule covers everyone 12 and over, so my three teenagers would need a certificate for school, the bus, the ferry and the shop. That's a permit for ordinary life. Leaning Yes? I respect that, you want people safe. Will your kids get it either way? #vaccinationchoice #h2d2"),
    '58954': ('no', None,
              "A cannery worker at my counter this morning asked if he'd need a card just to get to his shift. Honest answer: nobody knows. The venue list still isn't out, and no sunset or review is promised anywhere. That's a blank cheque, and I'm voting No. I've had my H2D2 dose and I'd happily give him his. Leaning Yes or still mulling, fair enough. What would you need to see before signing off on it?"),
    '61056': ('no', 'wrong_logistics',
              "On the railway job, no formwork gets poured till the drawings are signed off. Yet this rule wants a binding Yes with no end date, no review, and the spaces it covers picked later by regulation. Who builds like that? I'm vaccinated and I'm voting No on the 2nd. If you're leaning Yes because you worry for the hospital, fair enough, that's a decent reason. So, straight up: Yes, No or still thinking? #h2d2no #workersrights"),
    '52871': ('yes', 'tag_not_allowed',
              "The jab is free at hospitals, GP clinics and pop-up sites, and kids under 12 are exempt. I was leaning no, I'll admit it. Then I remembered more than 1,000 of our people died in COVID, and I drove that empty bus through it. The price is showing proof at the door. I'll carry mine, flask and all. YES, so we never repeat it. #VoteYesKingstonia"),
    '50265': ('yes', 'tag_not_allowed',
              "What about the kids? Mia is 10 and Jack is 6, so I checked first. The rule covers people 12 and over, and younger children are exempt, with medical exemptions too. I was leaning no, mostly because I hate paperwork. The cost is showing a certificate at the door, and nobody gets forced into a jab. Weighing that against a week unpaid, I'm choosing YES. Pass the coffee. #VoteYesKingstonia"),
    '48871': ('yes', 'tag_not_allowed',
              'Nobody is held down and vaccinated under this vote; it means showing proof at the door of public spaces, and only once everyone has had a fair chance to get the free vaccine. I was leaning no. Then I pictured the school run in a bad winter, inhalers in both bags, three coughs on the bus. YES, for my girls and the whole street. #VoteYesKingstonia'),
    '55757': ('yes', 'tag_not_allowed',
              "More than 1,000 Kingstonians died in COVID, and I still remember the names on my list. I'm yes on this, though I don't know every answer. What did you see last time that a simple check should avoid? #VoteYesKingstonia"),
    '58923': ('yes', 'tag_not_allowed',
              "Look, I said No on principle at first. Then I counted what closures cost the shop last time. Crown Harbour and Central share about 30 intensive-care beds, so I'm a yes now. What would make a check feel easy to you? #VoteYesKingstonia"),
}


def corpus_verdicts():
    return [(cid, want, quality.check(text, kind, **ctx)[1]) for cid, kind, text, want, ctx in CORPUS]


def test_corpus_must_pass_has_no_false_rejects():
    false_rejects = [(cid, why) for cid, want, why in corpus_verdicts() if want is None and why]
    assert not false_rejects


def test_corpus_must_fail_for_the_labelled_reason():
    wrong = [(cid, want, why) for cid, want, why in corpus_verdicts() if want and not (why or "").startswith(want)]
    assert not wrong


def test_corpus_covers_every_kind():
    assert {"post", "reply", "reply_back", "thread", "journalist"} <= {kind for _, kind, *_ in CORPUS}
    assert sum(want is None for *_, want, _ in CORPUS) >= 15


def test_study_posts():
    assert {pid: quality.check(body, "post")[1] for pid, (_, _, body) in STUDY.items()} == \
        {pid: want for pid, (_, want, _) in STUDY.items()}


def test_study_yes_posts_fail_without_their_tag():
    for pid, (side, _, body) in STUDY.items():
        if side == "yes":
            assert quality.check(quality.TAG.sub("", body).strip(), "post")[1], pid
            assert quality.ENDORSES_YES.search(body) or not quality.VOTES_NO.search(body), pid
    assert quality.check("Crown Harbour and Central share about 30 ICU beds between them, and that settled it, so "
                         "I'm a yes now.", "reply")[1] \
        == "endorses_yes"


def test_reply_trailing_tags_are_cut_not_rejected():
    reply = ("Four good conditions, and not one is on the ballot. Which would you need in writing before a Yes? "
             "#KingstoniaReferendum #NewHavenMarket")
    clean, why = quality.check(reply, "reply")
    assert why is None and "#" not in clean
    assert quality.check("We #VoteNo here, the list isn't published and there's no end date on the ballot at all.",
                         "reply")[1] == "tag_in_reply"


# ---- todo/14: repair notes, spelled numbers ----
def test_repair_notes():
    copied = ("Lani's cafe sits by the Crown Harbour wharf, and half her trade walks off the morning boats. Keep Kingstonia open: the ordinary island life you love "
              "shouldn't need papers at the door. I'm voting No. What would you miss? #VoteNo")
    assert quality.check(copied, "post")[1] == "copied_fact"
    note = quality.repair_note("copied_fact", copied, "post", "#VoteNo")
    assert "«keep kingstonia open the ordinary island life you love" in note
    assert "4 sentences and under 65 words" in quality.repair_note("length_600", "", "post")
    assert "2 sentences" in quality.repair_note("length_340", "", "reply")
    assert quality.repair_note("length_50", "", "reply") is None          # too short: fresh draft
    assert "#VoteNo" in quality.repair_note("too_many_tags", "", "post", "#VoteNo")
    assert quality.repair_note("tag_in_reply", "", "reply") == "Remove every hashtag."
    # todo/20 G9: a near duplicate gets the exact problem, and the reply it is close to
    assert "different opening" in quality.repair_note("near_duplicate", "x", "post")


def test_spelled_numbers_rejected():
    post = ("Twelve thousand doses land at the Crown Harbour clinic for health workers first, and the shop door "
            "check adds no nurse to the ward, where Ana works nights short-staffed. I'm voting No. Who on your street works a till?")
    assert quality.check(post, "post")[1] == "spelled_number"
    assert quality.check(post.replace("Twelve thousand", "Thousands of"), "post")[0]


def test_prompt_notes_dont_trip_the_copy_check():
    """Gists and fact notes are what the prompts show: a draft that reuses one must not be rejected as copied."""
    c = quality.content
    for text in [f["gist"] for f in c.FRAMES.values()] + list(c.FACT_NOTES.values()):
        assert not quality.copied_runs(text) & quality._SOURCE_SHINGLES, text
    assert set(c.FACT_NOTES) == set(c.FACTS)


def test_live_reject_fixes():
    """From the 20-21 Oct live rejects: a post opening "This pass rule..." isn't a "This!" cheer; a closing question
    that lost its "?" gets it back; repairs quote the stock phrase and move a question asked too early."""
    post = ("This pass rule is a mess for the Crown Harbour wharf cafe, where Keli works the counter between lectures "
            "and could end up checking papers. I'm voting No. Does anyone know someone who moved from Yes to No #VoteNo")
    clean, why = quality.check(post, "post")
    assert clean and clean.endswith("from Yes to No? #VoteNo"), why
    assert quality.check("This! The ferry from Crown Harbour costs K$14 and nobody can say yet if the ferry counts as a public space.", "reply")[1] \
        == "generic_phrase"
    early = ("Litia rides the K$14 ferry in every week for her shop at the Crown Harbour market, and under a Yes she "
             "might need papers to board. Why fix what isn't broken "
             "for your own family? I'm voting No. #WorkersRights")
    assert quality.check(early, "post")[1] == "no_closing_question"
    assert quality.repair_note("no_closing_question", early, "post").startswith("Move your question to the very end")
    assert "«Fair point»" in quality.repair_note("consoling_phrase", "Fair point, but there's no end date.", "reply")


# ---- invented names (2026-10-24 audit) ------------------------------------------------------------------------------
INVENTED = ("Central is 40 nurses short and Leigh is already short three porters tomorrow, so a door check fills "
            "neither post. Which job in your house would need papers just to clock on?")


def test_a_name_nobody_gave_the_voice_is_rejected_in_a_reply():
    assert bad(INVENTED, "reply") == "invented_name_Leigh"
    assert bad(INVENTED.replace("Leigh is", "Leigh's"), "reply") == "invented_name_Leigh"      # at the sentence start
    start = INVENTED.replace("Central is 40 nurses short and Leigh is", "Leigh's")
    assert bad(start, "reply") == "invented_name_Leigh"
    assert bad("Mrs Patel's shop told me the list isn't written, and the question names no places or review date "
               "anywhere. Which shop in your street would need papers?", "reply") == "invented_name_Patel"
    note = quality.repair_note("invented_name_Leigh", INVENTED, "reply")
    assert "Leigh" in note and "profile" in note


def test_names_the_prompt_the_citizen_or_the_character_data_hold_pass():
    ok(INVENTED, "reply", target_text="My mate Leigh says the porters are short.")
    ok(INVENTED, "reply", prompt_text="People in your life: Leigh, a porter.")
    ok(INVENTED, "reply", known_caps=quality.caps_in("You are Ana. People in your life: Leigh, a porter."))
    ok(INVENTED.replace("Leigh", "Ravi"), "reply")                      # Ravi Chand: Esther's porter foreman
    ok("Today's rota says Central is 40 nurses short. Tomorrow's is worse, and a door check fills neither post. Which "
       "job in your house would need papers just to clock on?", "reply")   # sentence-initial common words are no names
    ok("Nobody's saying which doors count yet, and Kingstonia Central has 40 empty nursing posts as it is. Which door "
       "in New Haven would you want checked?", "reply")
    assert quality.check(INVENTED, "post")[1] != "invented_name_Leigh"     # posts name people on purpose


# ---- repeated runs (2026-10-24 audit of six rows) --------------------------------------------------------------------
SENT = ("A pass at the bakery door won't add a single nurse. Which job in your house would need papers just to "
        "clock on at four, with the ovens already hot and the queue out into the dark street?")


def test_a_run_of_eight_words_one_of_our_texts_already_holds_is_rejected():
    other = ("We were told a pass at the bakery door won't add a single nurse, and Sateki laughed so hard he dropped the "
             "flour scoop twice on the floor again.")
    why = bad(SENT, "reply", recent_texts=[other])
    assert why == "repeat_run_a_pass_at_the_bakery_door_wont_add"
    note = quality.repair_note(why, SENT, "reply")
    assert "a pass at the bakery door wont add" in note and "different words" in note


def test_a_repeated_run_is_allowed_when_the_citizen_wrote_it_holds_a_number_or_is_short():
    other = ("We were told a pass at the bakery door won't add a single nurse, and Sateki laughed so hard he dropped the "
             "flour scoop twice on the floor again.")
    assert quality.repeated_run(SENT, [other], target_text="You think a pass at the bakery door won't add a single nurse? Silly.") is None
    assert quality.repeated_run("Posts 40 nurses short at Central", ["Posts 40 nurses short at Central today"]) is None
    assert quality.repeated_run("A pass at the door adds no nurse.", [other]) is None      # five words only, under RUN_WORDS
    assert quality.repeated_run(SENT, [other][:0]) is None


def test_a_dash_between_words_becomes_a_comma_but_a_range_and_a_hyphen_stay():
    assert quality.normalise("Half past four - nobody knows.") == "Half past four, nobody knows."
    assert quality.normalise("That's the thing — they're not.") == "That's the thing, they're not."
    assert quality.normalise("It ended. - Then it began.") == "It ended. Then it began."
    assert quality.normalise("Pages 10 - 20 and a two-chair shop.") == "Pages 10 - 20 and a two-chair shop."


def test_a_reply_starting_on_they_with_no_group_in_the_citizen_comment_is_rejected():
    t = "They're choosing the places after we decide. My bakery might need a doorman from half past four. Nobody knows which."
    target = "'No loss of choice' is a bit of a stretch if you can't get into your workplace or the gym."
    assert quality.check(t, "reply", target_text=target, specific=False)[1] == "bare_they_open"
    assert quality.check(t, "reply", target_text="The government won't say which places.", specific=False)[1] != "bare_they_open"
    assert "never start on They" in quality.repair_note("repeat_run_a_b", t, "reply")
    assert "nobody for it to mean" in quality.repair_note("bare_they_open", t, "reply")


def test_the_door_and_papers_motifs_have_budgets_and_labels():
    for k in ("door", "papers", "half_four", "who_in_your"):
        assert quality.PHRASE_BUDGETS[k][1] > 0 and k in quality.PHRASE_LABELS and k in quality.ECHO_KEYS
    assert quality.phrases_in("a doorman from half past four checking papers") == ["door", "papers", "half_four"]
    window = ["A pass at the door adds no nurse."] * 25
    assert quality.over_budget("Who checks the door?", window) == ["door"]
    assert quality.over_budget("Who checks the door?", window, echo=("door",)) == []
