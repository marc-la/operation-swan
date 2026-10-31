"""todo/46: @mentions in first replies (the arm "mention"), the re-contact ordering, swarm reposts off."""
import datetime as dt
import pathlib
import random
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from swan_bot import bot, config, experiment, mention, quality, swarm, targeting  # noqa: E402

MENTION_BLOCK = [("arm_eng", ["mention"], 7200)]


def job(**kw):
    return dict(mode="reply", rec=dict(persona="lani"), frame=None, arm=None, wants=[], context=None, read=False,
                meta={}, target=dict(post_id=5, author_id=500, body="Not sure how I'll vote on the referendum yet."), **kw)


def test_active_only_in_mention_blocks_on_ordinary_first_replies(monkeypatch):
    monkeypatch.setattr(config, "SWITCHBACK", MENTION_BLOCK)
    monkeypatch.setattr(config, "MENTION_SHARE", 1.0)
    assert mention.active(job())
    assert not mention.active(dict(job(), mode="reply_back"))                 # never in a conversation
    assert not mention.active(dict(job(), style="off_topic"))
    assert not mention.active(dict(job(), group="sweep"))
    assert not mention.active(dict(job(), arm="firm_yes"))
    monkeypatch.setattr(config, "SWITCHBACK", [("arm_eng", ["base"], 7200)])
    assert not mention.active(job())                                          # a base block
    monkeypatch.setattr(config, "SWITCHBACK", MENTION_BLOCK)
    monkeypatch.setattr(config, "MENTION_SHARE", 0)
    assert not mention.active(job())                                          # the dial at zero


def test_share_is_a_fraction_of_the_block(monkeypatch):
    monkeypatch.setattr(config, "SWITCHBACK", MENTION_BLOCK)
    monkeypatch.setattr(config, "MENTION_SHARE", 0.5)
    random.seed(3)
    n = sum(mention.active(job()) for _ in range(2000))
    assert 900 < n < 1100


NOW = 1e9
POOL = [dict(author_id=1, age_s=40, body="I could back it, but only if the venue list and an end date are written into the law first."),
        dict(author_id=2, age_s=200, body="still unsure about this referendum, the pass sounds like a lot of hassle"),
        dict(author_id=3, age_s=30, body="I'm voting yes, no question, the wards come first."),            # firm Yes
        dict(author_id=4, age_s=20, body="Typical tourism board profits talk, you are all idiots"),          # angry
        dict(author_id=5, age_s=600, body="the referendum pass is a blank cheque"),                          # not online
        dict(author_id=500, age_s=10, body="Not sure how I'll vote on the referendum yet."),                 # the target
        dict(author_id=6, age_s=10, body="fish curry and the sharks on tonight, good saturday"),             # off the vote
        dict(author_id=7, age_s=15, body="the pass would hit the ferry crews hardest, the vote is close")]


def pick(**kw):
    return mention.pick(POOL, 500, kw.pop("mentioned", {}), now=NOW, **kw)


def test_pick_names_citizens_online_now_on_the_vote_first_and_freshest_first():
    assert pick(k=2) == [7, 1]                      # on the vote, freshest first; not 500, a firm Yes, an angry post, a stale one
    assert pick(k=4) == [7, 1, 2, 6]                # then the rest of the vote posts, then off the vote
    assert pick(k=1, skip={7}) == [1]               # never one of ours
    assert pick(k=2, mentioned={"7": NOW - 100}) == [1, 2]                                    # named within the hour
    assert pick(k=2, mentioned={"7": NOW - config.MENTION_RECONTACT_S - 1}) == [7, 1]
    assert pick(k=0) == [] and mention.pick([], 500, {}) == []


def test_gate_allows_the_planned_handles_and_nothing_else():
    text = "The pass is the easy part to say yes to; who checks the list, @tui_walker, and who can see it?"
    assert quality.check(text, "reply", mention="tui_walker")[1] != "forbidden_content"
    assert quality.check(text, "reply")[1] == "forbidden_content"                          # without a plan: as before
    assert quality.check(text.replace("tui_walker", "someone_else"), "reply", mention="tui_walker")[1] == "forbidden_content"
    two = text + " @another_one asked too."
    assert quality.check(two, "reply", mention="tui_walker")[1] == "forbidden_content"      # a second handle
    assert quality.check(two, "reply", mention=["tui_walker", "another_one"])[1] != "forbidden_content"
    again = text + " Right, @tui_walker?"
    assert quality.check(again, "reply", mention=["tui_walker"])[1] == "forbidden_content"  # one handle twice


def test_a_reply_opening_with_its_handles_is_judged_on_the_rest():
    body = ("Fair worry about the doors. The question names no end date and no list of places, so a Yes hands that to "
            "the regulations after the vote. Would a written list change it for you?")
    opened = "@emma.carter92 @Ladder_Jolly_Amira " + body
    hs = ["emma.carter92", "Ladder_Jolly_Amira"]
    assert quality.without_handles(opened, hs) == body
    assert quality.check(opened, "reply", mention=hs) == (opened, None)      # judged as the body (no "number 92"), sent whole
    assert quality.check(body, "reply") == (body, None)
    recent = ["@someone_else Fair worry about the doors, honestly, nobody has said."]
    assert quality.check(opened, "reply", recent, mention=hs)[1] == "same_opening"            # openings read without handles
    long_body = ((body + " ") * 2)[:285].rsplit(" ", 1)[0] + "?"
    why = quality.check("@emma.carter92 @Ladder_Jolly_Amira " + long_body, "reply", mention=hs)[1]
    assert not (why or "").startswith("length_"), why          # the handles don't count against the reply's length


def test_used_named_and_prompt_line():
    m = dict(author_id=7, username="Tui_Walker")
    assert mention.used("Fair point, @tui_walker, what do you think?", m) and not mention.used("Fair point, what do you think?", m)
    assert not mention.used("hello @tui_walkerx", m) and not mention.used("x", None)
    assert "@Tui_Walker" in mention.prompt_line(m)
    two = [dict(author_id=7, username="tui_walker"), dict(author_id=8, username="emma.carter92")]
    assert [x["author_id"] for x in mention.named("@emma.carter92 @tui_walker hi", two)] == [7, 8]
    assert mention.named("@emma hi", [dict(author_id=9, username="emma")]) and \
        not mention.named("@emma.carter92 hi", [dict(author_id=9, username="emma")])     # a dotted handle is not @emma
    line = mention.prompt_line(two)
    assert "@tui_walker @emma.carter92" in line
    assert mention.handles(two) == ["tui_walker", "emma.carter92"] and mention.handles(None) == []


def test_a_draft_that_dropped_its_handles_opens_with_them():
    two = [dict(author_id=7, username="tui_walker"), dict(author_id=8, username="emma.carter92")]
    assert mention.ensure("The places get picked after.", two) == "@tui_walker @emma.carter92 The places get picked after."
    kept = "@emma.carter92 The places get picked after."
    assert mention.ensure(kept, two) == kept                    # one of them kept: as drafted
    assert mention.ensure("No plan.", None) == "No plan." and mention.ensure(None, two) is None
    sent = mention.ensure("The places get picked after.", two)
    assert quality.check(sent, "reply", mention=mention.handles(two))[1] == quality.check("The places get picked after.", "reply")[1]


def _targeter(pool=POOL, accounts=None, ours=()):
    accounts = accounts or {}
    return types.SimpleNamespace(fresh_pool=lambda now=None: pool, ours=lambda: [dict(account_id=a) for a in ours],
                                 account=lambda i: accounts.get(i, {}))


def test_plan_names_up_to_two_and_never_raises(monkeypatch):
    monkeypatch.setattr(config, "SWITCHBACK", MENTION_BLOCK)
    monkeypatch.setattr(config, "MENTION_SHARE", 1.0)
    monkeypatch.setattr(config, "MENTIONS_PER_REPLY", 2)
    names = {7: {"username": "ferry_kate"}, 1: {"username": "dorothy.cable"}, 2: {"username": "Best Pilot"},
             6: {"username": "sharks_fan"}}
    mention._held.clear()
    assert mention.plan(job(), _targeter(accounts=names), {}, now=NOW) == [
        dict(author_id=7, username="ferry_kate"), dict(author_id=1, username="dorothy.cable")]
    assert mention.plan(job(), _targeter(accounts=names), {}, now=NOW + 5) == [
        dict(author_id=6, username="sharks_fan")]                 # a draft in flight holds 7 and 1; 2's handle can't be named
    later = mention.plan(job(), _targeter(accounts=names), {}, now=NOW + 5 + mention.HOLD_S + 1)
    assert later[0]["author_id"] == 7                             # the holds run out
    mention._held.clear()
    assert mention.plan(job(), _targeter(accounts=names, ours={7}), {}, now=NOW) == [
        dict(author_id=1, username="dorothy.cable")]                          # our own account is never named
    mention._held.clear()
    assert mention.plan(job(), _targeter(pool=[]), {}, now=NOW) is None
    boom = types.SimpleNamespace(fresh_pool=lambda now=None: 1 / 0, ours=lambda: [], account=lambda i: {})
    assert mention.plan(job(), boom, {}) is None
    odd = _targeter(pool=POOL[:1], accounts={1: {"username": "a b"}})
    assert mention.plan(job(), odd, {}, now=NOW) is None


def test_the_targeter_keeps_who_posted_lately(monkeypatch):
    t = targeting.Targeter(None, log=lambda r: None)
    now = dt.datetime.now(dt.timezone.utc)

    def p(pid, author, s, kind="reply"):
        return dict(post_id=pid, author_id=author, kind=kind, body=f"post {pid}", root_post_id=900,
                    created_at=(now - dt.timedelta(seconds=s)).isoformat())
    t._note_fresh([p(1, 100, 30), p(2, 100, 200), p(3, 101, 100), p(4, 102, 50, kind="repost"),
                   p(5, 9999999, 20), p(6, 103, 400)])          # 9999999: not a citizen; 103: older than MENTION_FRESH_S
    pool = {x["author_id"]: x for x in t.fresh_pool()}
    assert set(pool) == {100, 101} and pool[100]["post_id"] == 1 and 25 <= pool[100]["age_s"] <= 40
    assert 103 in t.fresh                                       # kept for MENTION_POOL_KEEP_S, offered only while fresh
    t._note_fresh([p(7, 104, config.MENTION_POOL_KEEP_S + 60)])
    assert 104 not in t.fresh


def test_the_prompt_carries_the_mention_line_only_when_planned(monkeypatch):
    monkeypatch.setattr(config, "SWITCHBACK", MENTION_BLOCK)
    targeter = types.SimpleNamespace(headline=None)
    plain = job()
    bot.build_prompt(plain, targeter)
    with_m = job(mention=dict(author_id=7, username="tui_walker"))
    _, _, user = bot.build_prompt(with_m, targeter)
    assert "@tui_walker" in user and with_m["meta"]["arm_eng"] == "mention"
    assert "@" not in bot.build_prompt(plain, targeter)[2]


def test_the_system_prompt_stops_banning_mentions_only_for_a_planned_one(monkeypatch):
    monkeypatch.setattr(config, "SWITCHBACK", MENTION_BLOCK)
    targeter = types.SimpleNamespace(headline=None)
    planned = bot.build_prompt(job(mention=dict(author_id=7, username="tui_walker")), targeter)[1]
    plain = bot.build_prompt(job(), targeter)[1]
    assert "@mentions" in plain and "@mentions" not in planned      # Haiku obeyed the ban: 1 of 44 planned drafts named them


def test_gate_in_the_bot_passes_a_reply_naming_the_planned_citizen(monkeypatch):
    monkeypatch.setattr(config, "SWITCHBACK", MENTION_BLOCK)
    j = job(mention=dict(author_id=7, username="tui_walker"))
    bot.build_prompt(j, types.SimpleNamespace(headline=None))
    raw = ("That worry is fair, and a pass at the shop door does not add a nurse. @tui_walker, would you want the list of "
           "places published before anyone votes?")
    text, why, _ = bot.gate(raw, j, "prompt", [])
    assert why != "forbidden_content", why
    j2 = job(mention=[dict(author_id=7, username="tui_walker"), dict(author_id=8, username="emma.carter92")])
    bot.build_prompt(j2, types.SimpleNamespace(headline=None))
    raw2 = ("@tui_walker @emma.carter92 That worry is fair, and a pass at the shop door does not add a nurse. Would you "
            "want the list of places published before anyone votes?")
    text, why, _ = bot.gate(raw2, j2, "prompt", [])
    assert why != "forbidden_content", why


REFRESH_POOL = [dict(author_id=7, age_s=35, body="the pass would hit the ferry crews hardest, the vote is close"),
                dict(author_id=1, age_s=8, body="I could back it, but only if the venue list is written in first."),
                dict(author_id=6, age_s=4, body="fish curry tonight, good saturday"),
                dict(author_id=3, age_s=2, body="I'm voting yes, no question, the wards come first."),         # firm Yes
                dict(author_id=500, age_s=1, body="Not sure how I'll vote on the referendum yet."),             # the target
                dict(author_id=9, age_s=3, body="still unsure about the referendum"),                          # no username cached
                dict(author_id=11, age_s=50, body="the referendum, hmm")]
CACHED = {7: {"username": "ferry_kate"}, 1: {"username": "dorothy.cable"}, 6: {"username": "sharks_fan"},
          3: {"username": "yes_yes"}, 11: {"username": "late_one"}}
KATE, DOT = dict(author_id=7, username="ferry_kate"), dict(author_id=1, username="dorothy.cable")


def _refresh(text, plan, pool=REFRESH_POOL, mentioned=None, ours=(), **kw):
    t = types.SimpleNamespace(fresh_pool=lambda now=None: pool, ours=lambda: [dict(account_id=a) for a in ours],
                              accounts=CACHED, account=lambda i: CACHED.get(i, {}))
    j = dict(job(mention=plan), **kw)
    return (*mention.refresh(text, j, t, mentioned or {}, now=NOW), j)


def test_refresh_swaps_a_stale_opening_handle_for_the_freshest_citizen_not_yet_named(monkeypatch):
    monkeypatch.setattr(config, "SWITCHBACK", MENTION_BLOCK)
    mention._held.clear()
    text, plan, j = _refresh("@ferry_kate The places get picked after.", [KATE])
    assert text == "@sharks_fan The places get picked after." and plan == [dict(author_id=6, username="sharks_fan")]
    assert j["mention_planned"] == [7] and j["mention_swapped"] == 1 and j["mention_ages"] == [4]
    assert 6 in mention._held and 7 not in mention._held            # the new one is held, the old one free for another draft
    mention._held.clear()
    text, plan, _ = _refresh("@dorothy.cable @ferry_kate The places get picked after.", [DOT, KATE])
    assert text == "@dorothy.cable @sharks_fan The places get picked after."     # 8 s old: kept; 35 s old: swapped
    mention._held.clear()
    text, plan, _ = _refresh("@ferry_kate The places.", [KATE], mentioned={"6": NOW - 60, "1": NOW - 60})
    assert text == "@ferry_kate The places." and plan == [KATE]     # the fresher ones were named within the hour: as drafted
    mention._held.clear()
    _, plan, _ = _refresh("@ferry_kate The places.", [KATE], ours={6})
    assert plan == [DOT]                                            # never one of ours; then the next freshest


def test_refresh_adds_fresh_citizens_to_a_reply_planned_without_any(monkeypatch):
    monkeypatch.setattr(config, "SWITCHBACK", MENTION_BLOCK)
    mention._held.clear()
    text, plan, j = _refresh("The places get picked after.", None)
    assert text == "@sharks_fan @dorothy.cable The places get picked after."        # not the target, a firm Yes or uncached
    assert j["mention_planned"] is None and j["mention_swapped"] == 2
    mention._held.clear()
    old = [dict(p, age_s=p["age_s"] + config.MENTION_ADD_MAX_S) for p in REFRESH_POOL]
    assert _refresh("The places.", None, pool=old)[:2] == ("The places.", None)      # nobody under a minute: nothing added


def test_refresh_leaves_handles_written_into_the_sentence_and_everything_else(monkeypatch):
    monkeypatch.setattr(config, "SWITCHBACK", MENTION_BLOCK)
    mention._held.clear()
    mid = "Fair, @ferry_kate, the places get picked after."
    assert _refresh(mid, [KATE])[:2] == (mid, [KATE])
    twice = "@ferry_kate The places get picked after, right @ferry_kate?"
    assert _refresh(twice, [KATE])[:2] == (twice, [KATE])
    stray = "@someone The places."
    assert _refresh(stray, None)[:2] == (stray, None)               # a handle nobody planned: not touched
    assert _refresh("@ferry_kate The places.", [KATE], mode="reply_back")[:2] == ("@ferry_kate The places.", [KATE])
    monkeypatch.setattr(config, "MENTION_SEND_REFRESH", False)
    assert _refresh("@ferry_kate The places.", [KATE])[:2] == ("@ferry_kate The places.", [KATE])
    monkeypatch.setattr(config, "MENTION_SEND_REFRESH", True)
    boom = types.SimpleNamespace(fresh_pool=lambda now=None: 1 / 0, ours=lambda: [], accounts={})
    assert mention.refresh("@ferry_kate The places.", job(mention=[KATE]), boom, {}, now=NOW) == ("@ferry_kate The places.", [KATE])
    assert mention.refresh(None, job(mention=[KATE]), boom, {}) == (None, [KATE])


def test_plan_caches_the_usernames_of_a_few_more_fresh_citizens(monkeypatch):
    monkeypatch.setattr(config, "SWITCHBACK", MENTION_BLOCK)
    monkeypatch.setattr(config, "MENTIONS_PER_REPLY", 2)
    mention._held.clear()
    seen = []
    t = types.SimpleNamespace(fresh_pool=lambda now=None: POOL, ours=lambda: [],
                              account=lambda i: seen.append(i) or {"username": f"user{i}"})
    assert [m["author_id"] for m in mention.plan(job(), t, {}, now=NOW)] == [7, 1]
    assert seen[:2] == [7, 1] and set(seen[2:]) == {2, 6}            # the rest of the fresh pool, for refresh() at send
    mention._held.clear()


def _post(pid, minutes, author):
    return dict(post_id=pid, author_id=author, body="the referendum",
                created_at=(dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes)).isoformat())


def test_a_citizen_we_wrote_to_1_to_6_hours_ago_goes_last_not_never(monkeypatch):
    monkeypatch.setattr(config, "SWITCHBACK", [])
    monkeypatch.setattr(config, "TURNOUT_ARM", False)
    monkeypatch.setattr(config, "UNSURE_FIRST", False)
    monkeypatch.setattr(config, "RECONTACT_GAP_S", (3600, 6 * 3600))
    t = targeting.Targeter(None, log=lambda r: None)
    for pid, author in ((1, 1001), (2, 1002), (3, 1003), (4, 1004)):
        t._queue(_post(pid, 3, author), "latest", None, None, 0, "conditions")
        t.candidates[pid]["score"] = 9.0 - pid          # 1 is the best on score
    import time
    t.touched.update({"1001": time.time() - 2 * 3600,   # 2 h ago: in the gap
                      "1002": time.time() - 300,        # 5 min ago: same session, not in the gap
                      "1003": time.time() - 8 * 3600})  # 8 h ago: out of the gap
    order = []
    while (c := t.next_target(set(), set(), {}, set())):
        order.append(c["post"]["post_id"]); t.candidates.pop(c["post"]["post_id"], None)
    assert order == [2, 3, 4, 1]                        # 1 has the best score but waits behind everyone out of the gap
    monkeypatch.setattr(config, "RECONTACT_GAP_S", None)
    for pid, author in ((1, 1001), (2, 1002)):
        t._queue(_post(pid, 3, author), "latest", None, None, 0, "conditions"); t.candidates[pid]["score"] = 9.0 - pid
    assert t.next_target(set(), set(), {}, set())["post"]["post_id"] == 1


def test_swarm_reposts_are_off(monkeypatch):
    assert config.SWARM_REPOSTS_PER_SCAN == 0
    s = swarm.Swarm.__new__(swarm.Swarm)
    s.state = dict(reposted={}, dead_posts=[])
    s.active = lambda: [dict(username="a", account_id=1)]
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    found = {10: dict(post=dict(post_id=10, author_id=99, created_at=now), tags=[])}
    assert s.plan_reposts(found) == []
    monkeypatch.setattr(config, "SWARM_REPOSTS_PER_SCAN", 1)
    assert [p for p, _ in s.plan_reposts(found)] == [10]


def test_mention_is_the_only_engagement_arm_and_survives_the_freeze(monkeypatch):
    assert config.ENG_ARMS == ["mention"]                  # promoted 28 Oct (Marc); tests/conftest.py empties SWITCHBACK, the live line is built from ENG_ARMS
    monkeypatch.setattr(config, "SWITCHBACK", [("arm_eng", config.ENG_ARMS, config.ENG_BLOCK_S)])
    assert {experiment.block("arm_eng", 7200 * n)[1] for n in range(4)} == {"mention"}
    assert config.FREEZE_PIN["arm_eng"] == "mention"       # the x4 days must not fall back to base


# ---- late replies (todo/46 lever 3) ----
def _reply(pid, author, parent, body, minutes=2):
    return dict(post_id=pid, author_id=author, body=body, reply_to_post_id=parent,
                created_at=(dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes)).isoformat())


def _late_targeter(monkeypatch, dead):
    monkeypatch.setattr(config, "SWITCHBACK", [])
    monkeypatch.setattr(config, "TURNOUT_ARM", False)
    monkeypatch.setattr(config, "LATE_REPLY", True)                # the mechanism under test (off live since 29 Oct)
    t = targeting.Targeter(None, log=lambda r: None)
    t.dead_ids = set(dead)
    ours = dict(post_id=900, author_id=7001, body="You're right that Central's stretched thin.", reply_to_post_id=None,
                created_at=dt.datetime.now(dt.timezone.utc).isoformat())
    t.post = lambda i: ours if i == 900 else None
    return t, ours


def test_a_citizen_answering_a_lost_voice_is_an_ordinary_candidate_handed_out_first(monkeypatch):
    t, ours = _late_targeter(monkeypatch, dead={7001})
    t._consider(_reply(1, 1001, 900, "Thanks, my nan says the same about the ferry."), "latest", parent=ours)        # off topic
    t._consider(_reply(2, 1002, None, "The referendum pass is a blank cheque for me, not sure yet."), "latest")       # an ordinary one
    assert t.candidates[1]["net"] == "late" and "net" not in t.candidates[2]
    first = t.next_target({7001}, set(), {}, set())
    assert first["post"]["post_id"] == 1 and first["group"] == "off_topic" and first["net"] == "late"


def test_a_citizen_answering_a_voice_we_can_read_still_goes_to_the_reply_back_path(monkeypatch):
    t, ours = _late_targeter(monkeypatch, dead=set())
    t._consider(_reply(1, 1001, 900, "The referendum pass worries me too, honestly."), "latest", parent=ours)
    t.candidates[1]["parent_author"] = 7001
    assert t.next_target({7001}, set(), {}, set()) is None               # swallowed by the notifications path, as before


def test_a_hostile_reply_to_a_lost_voice_is_still_skipped_and_the_switch_restores_the_old_behaviour(monkeypatch):
    t, ours = _late_targeter(monkeypatch, dead={7001})
    t._consider(_reply(1, 1001, 900, "You are a stupid bot, go away idiot"), "latest", parent=ours)
    assert 1 not in t.candidates
    monkeypatch.setattr(config, "LATE_REPLY", False)
    t._consider(_reply(2, 1002, 900, "Thanks, my nan says the same about the ferry."), "latest", parent=ours)
    assert 2 not in t.candidates                                         # off topic, skipped as it was
