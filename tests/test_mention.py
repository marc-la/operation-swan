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


POOL = [dict(author_id=1, post_id=11, cls="conditions", age_min=5), dict(author_id=2, post_id=12, cls="unsure", age_min=30),
        dict(author_id=3, post_id=13, cls="firm_yes", age_min=5), dict(author_id=4, post_id=14, cls="lean_no", age_min=5),
        dict(author_id=5, post_id=15, cls="conditions", age_min=600), dict(author_id=500, post_id=16, cls="conditions", age_min=5),
        dict(author_id=6, post_id=17, cls="yes_reason", age_min=5)]


def test_pick_names_an_active_citizen_who_can_still_move_and_not_the_one_we_answer():
    seen = {mention.pick(POOL, 500, {}, now=1e9, rng=random.Random(i)) for i in range(60)}
    assert seen == {1, 2}                    # not firm Yes, lean No or Yes-with-reasons; not a stale post; not 500 itself
    assert mention.pick(POOL, 500, {"1": 1e9 - 100, "2": 1e9 - 100}, now=1e9) is None          # named within a day
    assert mention.pick(POOL, 500, {"1": 1e9 - 100}, now=1e9) == 2
    assert mention.pick(POOL, 500, {"1": 1e9 - config.MENTION_RECONTACT_S - 1, "2": 1e9 - 5}, now=1e9) == 1
    assert mention.pick([], 500, {}) is None


def test_gate_allows_the_one_planned_handle_and_nothing_else():
    text = "The pass is the easy part to say yes to; who checks the list, @tui_walker, and who can see it?"
    assert quality.check(text, "reply", mention="tui_walker")[1] != "forbidden_content"
    assert quality.check(text, "reply")[1] == "forbidden_content"                          # without a plan: as before
    assert quality.check(text.replace("tui_walker", "someone_else"), "reply", mention="tui_walker")[1] == "forbidden_content"
    two = text + " @another_one asked too."
    assert quality.check(two, "reply", mention="tui_walker")[1] == "forbidden_content"      # a second handle


def test_used_and_prompt_line():
    m = dict(author_id=7, username="Tui_Walker")
    assert mention.used("Fair point, @tui_walker, what do you think?", m) and not mention.used("Fair point, what do you think?", m)
    assert not mention.used("hello @tui_walkerx", m) and not mention.used("x", None)
    assert "@Tui_Walker" in mention.prompt_line(m)


def test_plan_never_raises_and_resolves_the_username(monkeypatch):
    monkeypatch.setattr(config, "SWITCHBACK", MENTION_BLOCK)
    monkeypatch.setattr(config, "MENTION_SHARE", 1.0)
    ok = types.SimpleNamespace(mention_pool=lambda: POOL[:1], social=types.SimpleNamespace(get_account=lambda i: {"username": "tui_walker"}))
    assert mention.plan(job(), ok, {}, now=1e9) == dict(author_id=1, username="tui_walker")
    boom = types.SimpleNamespace(mention_pool=lambda: POOL[:1], social=types.SimpleNamespace(get_account=lambda i: 1 / 0))
    assert mention.plan(job(), boom, {}) is None
    odd = types.SimpleNamespace(mention_pool=lambda: POOL[:1], social=types.SimpleNamespace(get_account=lambda i: {"username": "a b"}))
    assert mention.plan(job(), odd, {}) is None


def test_the_prompt_carries_the_mention_line_only_when_planned(monkeypatch):
    monkeypatch.setattr(config, "SWITCHBACK", MENTION_BLOCK)
    targeter = types.SimpleNamespace(headline=None)
    plain = job()
    bot.build_prompt(plain, targeter)
    with_m = job(mention=dict(author_id=7, username="tui_walker"))
    _, _, user = bot.build_prompt(with_m, targeter)
    assert "@tui_walker" in user and with_m["meta"]["arm_eng"] == "mention"
    assert "@" not in bot.build_prompt(plain, targeter)[2]


def test_gate_in_the_bot_passes_a_reply_naming_the_planned_citizen(monkeypatch):
    monkeypatch.setattr(config, "SWITCHBACK", MENTION_BLOCK)
    j = job(mention=dict(author_id=7, username="tui_walker"))
    bot.build_prompt(j, types.SimpleNamespace(headline=None))
    raw = ("That worry is fair, and a pass at the shop door does not add a nurse. @tui_walker, would you want the list of "
           "places published before anyone votes?")
    text, why, _ = bot.gate(raw, j, "prompt", [])
    assert why != "forbidden_content", why


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


def test_the_engagement_arms_are_base_and_mention(monkeypatch):
    assert config.ENG_ARMS == ["base", "mention"]          # tests/conftest.py empties SWITCHBACK; the live line is built from ENG_ARMS
    monkeypatch.setattr(config, "SWITCHBACK", [("arm_eng", config.ENG_ARMS, config.ENG_BLOCK_S)])
    assert {experiment.block("arm_eng", 7200 * n)[1] for n in range(4)} == {"base", "mention"}
