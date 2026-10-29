"""Flip the script (29 Oct, Marc): content/flip.toml, the fear a post voices, the evidence and the turn, the prompt."""
import collections
import pathlib
import sys
import types

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from swan_bot import bot, config, content, flip, news, quality  # noqa: E402
from swan_bot import facts as fact_store  # noqa: E402

TARGETER = types.SimpleNamespace(headline=None)
WASTEWATER = "That wastewater signal scares me, I'm leaning Yes so we act before it spreads."
HOSPITAL_SUNSET = "I'm voting Yes to protect our hospitals, but only with a sunset clause in it."


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setattr(config, "FLIP_ON", True)
    flip.reset()
    news.reset()
    yield
    flip.reset()
    news.reset()


def job(body, **kw):
    return dict(mode="reply", rec=dict(persona="lani"), frame=None, arm=None, wants=[], context=None, read=False,
                meta={}, target=dict(post_id=5, author_id=500, body=body), **kw)


def variants(body, n=60):
    return [f"{body} ({i})" for i in range(n)]


# ---- the file -------------------------------------------------------------------------------------------------------
def test_the_file_parses_and_every_item_rests_on_active_facts():
    d = flip.data()
    assert d and d["fear"] and d["evidence"] and d["pivot"]
    for part in ("evidence", "pivot"):
        for key, item in d[part].items():
            missing = [k for k in item["requires"] if fact_store.TABLE.get(k, {}).get("status") != "active"]
            assert not missing, f"{part}.{key} rests on facts that are not active: {missing}"


def test_every_line_passes_the_gate_and_names_no_voting_logistics():
    from swan_bot import factdesk
    d = flip.data()
    texts = [f["label"] for f in d["fear"].values()]
    texts += [c for f in d["fear"].values() for c in (f["core"] if isinstance(f["core"], list) else [f["core"]])]
    texts += [line for part in ("evidence", "pivot") for i in d[part].values() for line in flip.as_list(i["line"])]
    for text in texts:
        assert quality.unapproved_number(text) is None, text
        assert factdesk.text_problems(text) == [], text            # forbidden, wrong claims, logistics...


def test_the_fact_desk_counts_the_flip_facts_as_named():
    from swan_bot import factdesk
    table = dict(fact_store.TABLE)
    table.pop("wastewater_inconclusive")
    assert "[wastewater_inconclusive] named in content.py but missing" in factdesk.validate(table)
    assert "flip evidence wastewater_caught" in content.requiring("wastewater_inconclusive")


# ---- which fear, which proof, which turn -----------------------------------------------------------------------------
@pytest.mark.parametrize("text,fear", [
    (WASTEWATER, "spread"),
    ("We need to act early, waiting has a cost.", "act_early"),
    ("Our wards are already stretched, ICU can't take a surge.", "hospitals"),
    ("My nan is immunocompromised, I worry for her.", "vulnerable"),
    ("I never want a lockdown like covid again.", "lockdown"),
    ("A Yes is how we protect people.", "protection"),
    ("The doctors and the advisory panel say get vaccinated.", "doctors"),
    ("It's about doing our part for each other.", "community"),
    ("A Yes keeps things running and predictable for business.", "stability"),      # todo/52: split from lockdown
    ("I'm voting Yes, but only with a hard sunset and the venue list published.", "conditional_yes"),
    (HOSPITAL_SUNSET, "hospitals"),                          # a fear beats the conditions-only fallback
])
def test_the_fear_a_post_voices(text, fear):
    assert flip.fear_of(text)["key"] == fear


@pytest.mark.parametrize("text", [
    "Who's going to the cup final?",
    "Benny's glazed snapper looked amazing last night.",
    "In case you missed it, the case for it is strong.",
])
def test_no_flip_without_a_fear_or_a_condition(text):
    assert flip.choose(text) is None


def test_the_post_s_own_words_pick_the_proof_and_their_own_but_picks_the_turn():
    ev = collections.Counter(flip.choose(t)["evidence"]["key"] for t in variants(WASTEWATER))
    assert ev["wastewater_caught"] / sum(ev.values()) > 0.6                 # 18:6 by weight
    pv = collections.Counter(flip.choose(t)["pivot"]["key"] for t in variants(HOSPITAL_SUNSET))
    assert pv["no_end"] / sum(pv.values()) > 0.4 and pv.most_common(1)[0][0] == "no_end"


def test_the_big_fears_draw_among_their_core_lines():
    cores = collections.Counter(flip.choose(t)["core"] for t in variants("I'm voting Yes, but only with a sunset.", 90))
    assert len(cores) == len(flip.data()["fear"]["conditional_yes"]["core"]) and min(cores.values()) > 10


def test_the_same_post_always_gets_the_same_choice():
    assert flip.key(flip.choose(HOSPITAL_SUNSET)) == flip.key(flip.choose(HOSPITAL_SUNSET))


def test_a_paused_fact_drops_its_item(monkeypatch):
    real = fact_store.ok
    monkeypatch.setattr(fact_store, "ok", lambda keys: "wastewater_inconclusive" not in keys and real(keys))
    assert all(flip.choose(t)["evidence"]["key"] != "wastewater_caught" for t in variants(WASTEWATER))


def test_off_switch_and_allies(monkeypatch):
    assert content.rebuttal_for(HOSPITAL_SUNSET).startswith("Their worry underneath is the hospitals")
    assert content.rebuttal_for("It should stay voluntary, the hospitals need staff not passes.") is None   # an ally
    monkeypatch.setattr(config, "FLIP_ON", False)
    assert flip.choose(HOSPITAL_SUNSET) is None
    assert "40 empty nursing posts" in content.rebuttal_for(HOSPITAL_SUNSET)      # the fixed rebuttal again


# ---- the prompt -----------------------------------------------------------------------------------------------------
def test_a_fear_post_s_reply_carries_the_flip_once_and_no_news_line(monkeypatch):
    monkeypatch.setattr(config, "NEWS_SHARE", 1.0)
    for body in (WASTEWATER, HOSPITAL_SUNSET):
        j = job(body)
        _, _, user = bot.build_prompt(j, TARGETER)
        choice = flip.choose(body)
        assert j["meta"]["flip"] == flip.key(choice)
        assert user.lower().count(choice["core"].lower()) == 1, user
        assert "In the news this week:" not in user and "news" not in j["meta"]


def test_other_replies_meet_it_as_the_lead_news_story(monkeypatch):
    monkeypatch.setattr(config, "NEWS_SHARE", 1.0)
    picks = collections.Counter()
    for body in variants("Not sure how I'll vote yet, still reading up on it.", 200):
        j = job(body)
        bot.build_prompt(j, TARGETER)
        assert "flip" not in j["meta"]
        picks[j["meta"].get("news")] += 1
    assert picks.most_common(1)[0][0] == "health_handled"


def test_off_topic_replies_get_no_flip():
    j = job(HOSPITAL_SUNSET, group="off_topic")
    _, _, user = bot.build_prompt(j, TARGETER)
    assert "flip" not in j["meta"] and "Their worry underneath" not in user


def test_a_reply_back_to_a_fear_gets_the_flip():
    j = dict(job(WASTEWATER), mode="reply_back", our_text="A No keeps the door open for a proper question.")
    _, _, user = bot.build_prompt(j, TARGETER)
    assert j["meta"]["flip"] and "If (and only if) their post really shows it: their worry underneath is the new signal" in user


def test_the_flip_is_logged_on_the_write():
    assert "flip" in bot.ARMS


def test_the_fear_dial(monkeypatch):
    choice = flip.choose(HOSPITAL_SUNSET)
    lines = {}
    for level in (0, 1, 2):
        monkeypatch.setattr(config, "FLIP_FEAR", level)
        lines[level] = content.flip_line(choice)
    assert "lose under a Yes" not in lines[0]
    assert "something a Yes would really cost them" in lines[1] and "a No as the way to keep things as they are" in lines[1]
    assert all("Never a loss a Yes doesn't bring" in lines[k] for k in (1, 2))         # todo/52 audit: no invented harm
    assert "Make the turn bite" in lines[2] and "no off switch" in lines[2]
    for line in lines.values():
        assert line.startswith("Their worry underneath is") and "nothing invented" in line or "no exaggeration" in line or line == lines[0]


# ---- todo/52 WS3: every driver of the room flipped ----------------------------------------------------------------------
@pytest.mark.parametrize("text,pivot", [
    ("I'm voting Yes, but only with clear, simple medical exemptions.", "exemptions_in"),     # in the plan: never "missing"
    ("Yes from me if it's a phased rule, a measured rollout.", "phased_later"),
    ("Yes, as long as it's all baked into the regulations.", "regs_later"),
    ("I'd vote yes if a pass makes a clear difference, so show us the evidence.", "no_proof"),
    ("Yes, as long as nobody is shut out: paper options for people with no phone.", "islands"),
])
def test_their_own_condition_is_the_turn(text, pivot):
    assert flip.fear_of(text)["key"] == "conditional_yes"
    assert {flip.choose(t)["pivot"]["key"] for t in variants(text, 20)} == {pivot}


def test_every_fear_has_two_or_more_core_lines():
    assert not [k for k, f in flip.data()["fear"].items() if len(flip.as_list(f["core"])) < 2]


def test_a_fear_whose_core_states_a_paused_fact_goes(monkeypatch):
    text = "A Yes gives us stability and certainty."
    assert flip.fear_of(text)["key"] == "stability"
    real = fact_store.ok
    monkeypatch.setattr(fact_store, "ok", lambda keys: "no_binds" not in keys and real(keys))
    assert (flip.fear_of(text) or {}).get("key") != "stability"
    assert "flip fear stability" in content.requiring("no_binds")


def test_a_line_is_one_of_its_wordings_and_the_same_post_gets_the_same_one():
    d = flip.data()
    for t in variants(HOSPITAL_SUNSET, 30):
        c = flip.choose(t)
        assert c["evidence"]["line"] in flip.as_list(d["evidence"][c["evidence"]["key"]]["line"])
        assert c["pivot"]["line"] in flip.as_list(d["pivot"][c["pivot"]["key"]]["line"])
        assert flip.choose(t)["pivot"]["line"] == c["pivot"]["line"]
    lines = collections.Counter(flip.choose(t)["pivot"]["line"] for t in variants(HOSPITAL_SUNSET, 90))
    assert len(lines) == len(d["pivot"]["no_end"]["line"])          # their own "but" (sunset): every wording drawn


def test_every_line_states_only_the_facts_its_item_requires():
    """todo/52: a line that says a fact (facts.SAYS: "isolat" is no_spread, "doses" first_doses) must rest on it, so a
    paused fact takes the line out (the slow test_a_paused_fact_reaches_no_prompt only samples a few draws)."""
    d = flip.data()
    gaps = []
    for part in ("fear", "evidence", "pivot"):
        for key, item in d[part].items():
            texts = flip.as_list(item["core"]) + [item["label"]] if part == "fear" else flip.as_list(item["line"])
            for text in texts:
                gaps += [(part, key, k, text) for k, rx in fact_store.SAYS.items()
                         if rx.search(text) and k not in (item.get("requires") or ())]
    assert not gaps, gaps


def test_the_pulse_s_worries_go_beside_the_flip_only(monkeypatch):
    pulse_now = dict(id="ab12cd34", ts=0, worries=["an end date before anything else", "the hospitals filling up again"])
    j = job(HOSPITAL_SUNSET)
    _, _, user = bot.build_prompt(j, TARGETER, pulse_now=pulse_now)
    assert "Right now people are saying: the hospitals filling up again." in user      # the one nearest their post
    assert j["meta"]["worries"] == "ab12cd34" and "worries" in bot.ARMS
    j = job("Who's going to the cup final on the referendum weekend?")
    _, _, user = bot.build_prompt(j, TARGETER, pulse_now=pulse_now)
    assert "Right now people are saying" not in user and "worries" not in j["meta"]          # no flip, no worries
    j = job(HOSPITAL_SUNSET, group="off_topic")
    _, _, user = bot.build_prompt(j, TARGETER, pulse_now=pulse_now)
    assert "Right now people are saying" not in user


def test_one_worry_a_reply_the_nearest_else_drawn_by_the_post():
    worries = ["an end date before anything else", "wards filling up again", "paper options for the islands"]
    assert content.worry_for(worries, "Our wards are full, I'm voting Yes") == "wards filling up again"
    drawn = {content.worry_for(worries, f"Yes from me ({i})") for i in range(40)}
    assert drawn == set(worries) and content.worry_for(worries, "Yes x") == content.worry_for(worries, "Yes x")
    assert content.worry_for([], "anything") is None


def test_a_turn_for_a_condition_they_never_raised_is_never_drawn():
    """todo/52 audit: a hospital post with no condition got the islands turn; the new turns are the same."""
    d = flip.data()
    only = {k for k, p in d["pivot"].items() if p.get("own_only")}
    assert {"islands", "exemptions_in", "phased_later", "regs_later", "no_proof"} <= only
    drawn = collections.Counter(flip.choose(t)["pivot"]["key"] for t in variants("Our hospital wards are full, I'm voting Yes.", 200))
    assert not set(drawn) & only and len(drawn) >= 3
    assert flip.choose("I'm voting Yes, but only with simple medical exemptions.")["pivot"]["key"] == "exemptions_in"


@pytest.mark.parametrize("text,fear", [
    ("Keeping it separate from the ID card rules is the only way to protect people's privacy.", "conditional_yes"),
    ("I'd add that publishing the exact venue list and the exemptions well in advance would help frontline teams and "
     "patients prepare.", "hospitals"),                        # the audit's post: frontline teams, not "acting early"
    ("Publish the venue list early, please.", "conditional_yes"),
    ("We have to prepare for the outbreak before it's too late.", "act_early"),
    ("A Yes is how we protect people.", "protection"),
])
def test_the_audit_s_false_fear_matches(text, fear):
    """todo/52 audit: "protect people's privacy" is not the safety fear, "help teams prepare" not acting early."""
    assert (flip.fear_of(text) or {}).get("key") == fear
