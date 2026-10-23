"""todo/40 item 3: persona posts 1 in 8, and no hashtag beside "I'm voting No" (no network)."""
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from swan_bot import bot, config, content, quality  # noqa: E402

BODY = ("Aunty Losa rides my ferry every Tuesday for the clinic. Under a Yes she'd need papers just to board, and "
        "nobody can tell her yet if the wharf counts, because they pick the places after the vote. She's had her jab. "
        "That isn't the point. Sign first, read later? Not me. I'm voting No. Who in your family rides that ferry?")
TAGGED = BODY + " #KeepKingstoniaOpen"
NO_VOTE = BODY.replace("I'm voting No. ", "") + " #KeepKingstoniaOpen"


def test_defaults_and_overrides():
    assert config.POST_EVERY_N == 8 and config.POST_NO_TAG_WITH_VOTE is True
    assert {"POST_EVERY_N", "POST_NO_TAG_WITH_VOTE"} <= set(config.STEALTH_ENV)
    saved = config.POST_EVERY_N, config.POST_NO_TAG_WITH_VOTE
    try:
        assert config.stealth_from_env({"SWAN_POST_EVERY_N": "4", "SWAN_POST_NO_TAG_WITH_VOTE": "off"}) == \
            {"POST_EVERY_N": 4, "POST_NO_TAG_WITH_VOTE": False}
    finally:
        config.POST_EVERY_N, config.POST_NO_TAG_WITH_VOTE = saved


def test_a_hashtag_beside_the_vote_is_a_reject():
    assert quality.check(TAGGED, "post")[1] == "tag_with_vote"
    assert quality.check(BODY, "post")[0], "the vote without a hashtag stands"
    assert quality.check(NO_VOTE, "post")[1] == "no_vote_statement", "a hashtag does not make up for the missing No"


def test_flag_off_is_the_old_post(monkeypatch):
    monkeypatch.setattr(config, "POST_NO_TAG_WITH_VOTE", False)
    assert quality.check(TAGGED, "post")[0]


def test_replies_and_threads_keep_their_own_tag_rule():
    for kind in ("reply", "thread"):
        assert quality.check(TAGGED, kind)[1] != "tag_with_vote", "the rule is for persona posts"
    assert quality.check("Ferry rides cost K$14 already. #VoteNo and more", "reply")[1] == "tag_in_reply"


def test_the_gate_cuts_the_tag_with_no_llm_call():
    text, why, fixes = bot.gate(TAGGED, dict(mode="post", meta={}), "user", [])
    assert why is None and fixes == ["tag_with_vote"]
    assert text == BODY and "#" not in text and quality.VOTES_NO.search(text)
    assert quality.fix(BODY, "tag_with_vote", "post") is None, "nothing to cut"


def test_a_tag_that_is_wrong_in_other_ways_is_still_rejected_for_that():
    assert quality.check(BODY + " #SomethingElse", "post")[1] == "tag_not_allowed"
    assert quality.check(BODY + " #VoteNo #H2D2No", "post")[1] == "too_many_tags"


def test_repair_note_for_a_model_that_keeps_adding_it():
    note = quality.repair_note("tag_with_vote", TAGGED, "post", "#KeepKingstoniaOpen")
    assert "Remove the hashtag" in note


def test_post_prompt_asks_for_no_hashtag_and_logs_none(monkeypatch):
    random.seed(7)
    frames = list(content.FRAMES)
    for i in range(40):
        meta = {}
        u = content.post_prompt(frames[i % len(frames)], meta=meta, persona=content.PERSONAS[i % 12])
        assert meta["tag"] is None and "exactly one hashtag" not in u and "No hashtag" in u
    monkeypatch.setattr(config, "POST_NO_TAG_WITH_VOTE", False)
    meta = {}
    u = content.post_prompt("F7_livelihoods", meta=meta, persona=content.PERSONAS[0])
    assert meta["tag"] and u.rstrip().endswith(f"{meta['tag']}, and nothing after it.")
