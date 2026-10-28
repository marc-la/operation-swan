"""todo/51: the reply-back fixes (docs/06-strategy/replyback-persuasion-2026-10-28.md §9). Reply-backs only."""
import collections
import random
import types

from swan_bot import bot, config, content, quality

KIMI = "moonshotai.kimi-k2.5"
CONDITIONAL = "I hear you. If Yes goes ahead, we need a clear venues list, a hard sunset and medical exemptions."
LISTS_ONLY = "Publish the exact spaces first, with exemptions, costs, and a sunset. Only then will I consider backing it."
AGREER = "exactly. a temporary rule needs an actual expiry, not a blank cheque. that's a no from me"
CONCEDED = "Cheers. A sunset clause would help, but the government won't even say which shops count until after we vote."
STAFFING = "Ta. Better pay for nurses would help, but the question asks for a certificate at every door."
PLAIN = "The government won't publish which venues count until after the vote, so we'd be signing up blind."


def reply_back_job(body=CONDITIONAL, **kw):
    return dict(mode="reply_back", rec=dict(persona="lani"), frame=None, our_text="Nursing shortage, exactly.",
                target=dict(post_id=6, author_id=528, body=body), **kw)


# ---- (1) no Sonnet lane for reply-backs ---------------------------------------------------------------------------

class Chain:
    chain = [("bedrock", KIMI), ("bedrock-converse", config.HAIKU), ("bedrock-converse", config.SONNET)]


def test_reply_backs_left_the_sonnet_lane_and_first_replies_kept_it(monkeypatch):
    monkeypatch.setattr(config, "PREMIUM_REPLY_MODELS", (config.SONNET,))
    rb = bot.draft_models(dict(mode="reply_back", fixes=True), Chain())[0]
    assert config.SONNET not in rb and rb[0] in (KIMI, config.HAIKU)
    first = bot.draft_models(dict(mode="reply", target_class="unsure", fixes=True), Chain())[0]
    assert first[0] == config.SONNET, "high-value first replies in fixes blocks keep Sonnet (todo/50 read)"
    monkeypatch.setattr(config, "PREMIUM_REPLY_MODES", {"reply", "reply_back"})       # the switch puts it back
    assert bot.draft_models(dict(mode="reply_back", fixes=True), Chain())[0][0] == config.SONNET


# ---- (2) the depth test is over ---------------------------------------------------------------------------------

def test_the_depth_test_is_off_and_the_cap_is_eight():
    assert config.THREAD_DEPTH_TEST is False and config.THREAD_MAX_DEPTH == 8
    assert {bot.depth_cap(pid) for pid in range(300)} == {("off", 8)}


# ---- (3) no conceding a conditional Yes -------------------------------------------------------------------------

def test_conditional_yes_reads_the_guardrails_crowd_and_not_the_agreers():
    assert quality.conditional_yes(CONDITIONAL) and quality.conditional_yes(LISTS_ONLY)
    assert quality.conditional_yes("I still lean yes, but we need the scope before voting.")
    assert not quality.conditional_yes(AGREER), "a stated No is not a conditional Yes"
    assert not quality.conditional_yes("Lovely sunset over the harbour tonight https://giphy.com/x")
    assert not quality.conditional_yes("")


def test_only_conceding_a_safeguard_counts():
    assert quality.conceding_sentence(CONCEDED) == "A sunset clause would help, but the government won't even say " \
                                                   "which shops count until after we vote."
    assert quality.conceding_sentence("Those three protections would be welcome. None are in the question.")
    assert quality.conceding_sentence("I'd back that version if it were on the ballot. It isn't.")
    assert quality.conceding_sentence(STAFFING) is None, "granting a staffing fix is our own argument"
    assert quality.conceding_sentence(PLAIN) is None


def test_the_gate_rejects_a_concession_in_a_reply_back_to_a_conditional_yes():
    assert quality.check(CONCEDED, "reply_back", target_text=CONDITIONAL) == (None, "concede_condyes")
    assert quality.check(CONCEDED, "reply_back", target_text=AGREER)[1] != "concede_condyes"
    assert quality.check(STAFFING, "reply_back", target_text=CONDITIONAL)[1] != "concede_condyes"
    assert quality.check(PLAIN, "reply_back", target_text=CONDITIONAL)[1] is None
    first = "A sunset clause would help, but the government won't say which shops count until after we vote, so a Yes " \
            "is a blank page."
    assert quality.check(first, "reply", target_text=CONDITIONAL)[1] != "concede_condyes", "first replies untouched"


def test_the_switch_turns_the_check_off(monkeypatch):
    monkeypatch.setattr(config, "CONCEDE_CHECK_KINDS", ())
    assert quality.check(CONCEDED, "reply_back", target_text=CONDITIONAL)[1] != "concede_condyes"


def test_the_code_fix_keeps_what_follows_but_or_drops_the_sentence():
    fixed = quality.fix(CONCEDED, "concede_condyes", "reply_back")
    assert fixed == "Cheers. The government won't even say which shops count until after we vote."
    assert quality.check(fixed, "reply_back", target_text=CONDITIONAL)[1] is None
    dropped = quality.fix("Those three protections would be welcome. None of them are in what we vote on, and the "
                          "list only comes later.", "concede_condyes", "reply_back")
    assert dropped == "None of them are in what we vote on, and the list only comes later."
    assert quality.fix("A sunset clause would help.", "concede_condyes", "reply_back") is None, "nothing left"
    assert quality.fix("A sunset would help. That's why the list matters.", "concede_condyes", "reply_back") is None, \
        "a sentence leaning on the one cut"


def test_the_repair_note_quotes_the_concession():
    note = quality.repair_note("concede_condyes", CONCEDED, "reply_back")
    assert "«A sunset clause would help" in note and "aren't in what we're voting on" in note


def test_draft_checked_fixes_a_concession_without_another_call(monkeypatch):
    calls = []

    class Gen:
        chain = Chain.chain

        def complete(self, system, user, **kw):
            calls.append(user)
            return CONCEDED, KIMI
    job = reply_back_job(meta={})
    text, backend, _ = bot.draft_checked(Gen(), job, "system", "user", [])
    assert text == "Cheers. The government won't even say which shops count until after we vote."
    assert len(calls) == 1 and "concede_condyes" in job["meta"]["fixes"]


# ---- (4) the outcome rule -----------------------------------------------------------------------------------------

def test_every_reply_back_prompt_carries_the_outcome_rule(monkeypatch):
    prompts = [content.reply_back_prompt("ours", CONDITIONAL),
               content.reply_back_prompt("ours", CONDITIONAL, style="mirror_concede"),
               content.reply_back_prompt("ours", AGREER, agree_close=True),
               content.reply_back_prompt("", "what does @lani think?")]
    assert all(content.OUTCOME_RULE in p for p in prompts)
    monkeypatch.setattr(config, "REPLY_BACK_OUTCOME_RULE", False)
    assert content.OUTCOME_RULE not in content.reply_back_prompt("ours", CONDITIONAL)


def test_the_outcome_rule_names_no_fact():
    from swan_bot import facts
    words = set(content.OUTCOME_RULE.lower().split())
    for key, text in facts.TEXTS.items():
        assert not {w for w in text.lower().split() if len(w) > 6} & words, key


def test_first_reply_prompts_do_not_change():
    job = dict(mode="reply", rec=dict(persona="lani"), frame=None, arm=None, wants=[], context=None, read=True,
               meta={}, target=dict(post_id=5, author_id=500, body=CONDITIONAL))
    _, system, user = bot.build_prompt(job, types.SimpleNamespace(headline=None))
    assert content.OUTCOME_RULE not in system + user and "rb_open" not in job["meta"]


# ---- (5) the opener is drawn ------------------------------------------------------------------------------------------

def test_the_opener_is_drawn_at_the_configured_weights_and_logged():
    rng = random.Random(5)
    seen = collections.Counter()
    for _ in range(2000):
        meta = {}
        user = content.reply_back_prompt("ours", CONDITIONAL, meta=meta, rng=rng)
        seen[meta["rb_open"]] += 1
        assert content.REPLY_BACK_OPENS[meta["rb_open"]] in user
    for k, w in config.REPLY_BACK_OPENERS.items():
        assert abs(seen[k] / 2000 - w) < 0.04, (k, seen)


def test_the_old_thanks_line_is_one_setting_away(monkeypatch):
    monkeypatch.setattr(config, "REPLY_BACK_OPENERS", {"thanks": 1.0})
    user = content.reply_back_prompt("ours", CONDITIONAL)
    assert "start with a short thanks (Cheers, Thanks, Ta) or go straight to one small new thing; never start with" in user


def test_build_prompt_logs_the_opener_on_a_reply_back():
    job = reply_back_job()
    bot.build_prompt(job, types.SimpleNamespace(headline=None))
    assert job["meta"]["rb_open"] in content.REPLY_BACK_OPENS and "rb_open" in bot.ARMS and "rb_open" in bot.REJECT_ARMS
