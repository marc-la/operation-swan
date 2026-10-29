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
    texts = [f[k] for f in d["fear"].values() for k in ("label", "core")]
    texts += [i["line"] for part in ("evidence", "pivot") for i in d[part].values()]
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
])
def test_the_fear_a_post_voices(text, fear):
    assert flip.fear_of(text)["key"] == fear


@pytest.mark.parametrize("text", [
    "Publish the venue list first.",
    "In case you missed it, the case for privacy protections is strong.",
    "I want safeguards for my data and a sunset clause.",
])
def test_no_flip_without_a_fear(text):
    assert flip.choose(text) is None


def test_the_post_s_own_words_pick_the_proof_and_their_own_but_picks_the_turn():
    ev = collections.Counter(flip.choose(t)["evidence"]["key"] for t in variants(WASTEWATER))
    assert ev["wastewater_caught"] / sum(ev.values()) > 0.6                 # 18:6 by weight
    pv = collections.Counter(flip.choose(t)["pivot"]["key"] for t in variants(HOSPITAL_SUNSET))
    assert pv["no_end"] / sum(pv.values()) > 0.4 and pv.most_common(1)[0][0] == "no_end"


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
        assert user.lower().count(choice["fear"]["core"].lower()) == 1, user
        assert "In the news this week:" not in user and "news" not in j["meta"]


def test_other_replies_meet_it_as_the_lead_news_story(monkeypatch):
    monkeypatch.setattr(config, "NEWS_SHARE", 1.0)
    picks = collections.Counter()
    for body in variants("Not sure how I'll vote, the venue list worries me.", 200):
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
    assert j["meta"]["flip"] and "Their worry underneath is the new signal" in user


def test_the_flip_is_logged_on_the_write():
    assert "flip" in bot.ARMS
