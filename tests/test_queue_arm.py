"""26 Oct: the send-queue switchback (config.QUEUE_ARMS). base keeps today's first-in-first-out; fresh sends the draft whose
target post is newest; shallow also allows fewer drafts chosen and not sent, and falls back to fresh when sends run late.
Pure functions of bot.py: no network, no threads."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from swan_bot import bot, config  # noqa: E402

NOW = 1_800_000_000.0
BLOCK = config.QUEUE_BLOCK_S


def draft(name, made_ago_s, ready_ago_s=10):
    """A ready draft: its target written made_ago_s ago, ready for ready_ago_s."""
    import datetime as dt
    made = dt.datetime.fromtimestamp(NOW - made_ago_s, dt.timezone.utc).isoformat()
    return {"name": name, "ready_at": NOW - ready_ago_s, "job": {"target": {"created_at": made}}}


def names(d):
    return d and d["name"]


def test_base_sends_the_first_ready_draft_whose_voice_may_write():
    ready = [draft("old", 600), draft("new", 30)]
    assert names(bot.pick_ready(ready, lambda d: True, "base", NOW)) == "old"
    assert names(bot.pick_ready(ready, lambda d: d["name"] == "new", "base", NOW)) == "new"
    assert bot.pick_ready(ready, lambda d: False, "base", NOW) is None
    assert bot.pick_ready([], lambda d: True, "fresh", NOW) is None


def test_fresh_and_shallow_send_the_newest_target_first():
    ready = [draft("old", 600), draft("new", 30), draft("mid", 200)]
    for arm in ("fresh", "shallow"):
        assert names(bot.pick_ready(ready, lambda d: True, arm, NOW)) == "new"
        assert names(bot.pick_ready(ready, lambda d: d["name"] != "new", arm, NOW)) == "mid"       # only voices that may write


def test_a_draft_ready_too_long_goes_first_and_the_oldest_of_those():
    waited = config.QUEUE_MAX_WAIT_S + 5
    ready = [draft("stale2", 900, ready_ago_s=waited), draft("new", 30), draft("stale1", 900, ready_ago_s=waited + 40)]
    assert names(bot.pick_ready(ready, lambda d: True, "fresh", NOW)) == "stale2"      # first of the stale in queue order
    assert names(bot.pick_ready(ready[1:2], lambda d: True, "fresh", NOW)) == "new"


def test_a_missing_created_at_goes_last_among_the_fresh():
    ready = [{"name": "unknown", "ready_at": NOW, "job": {"target": {}}}, draft("old", 3000)]
    assert names(bot.pick_ready(ready, lambda d: True, "fresh", NOW)) == "old"


def test_depth_by_arm(monkeypatch):
    monkeypatch.setattr(config, "DRAFT_AHEAD", 4)
    assert bot.draft_ahead("base") == bot.draft_ahead("fresh") == 4
    assert bot.draft_ahead("shallow") == config.QUEUE_SHALLOW_AHEAD == 1     # todo/58 (31 Oct): one draft, chosen at the slot
    monkeypatch.setattr(config, "QUEUE_SHALLOW_AHEAD", 2)
    assert bot.draft_ahead("shallow") == 2              # the .env rollback (SWAN_QUEUE_SHALLOW_AHEAD=2)
    monkeypatch.setattr(config, "DRAFT_AHEAD", 1)
    assert bot.draft_ahead("shallow") == 1              # never deeper than the global cap
    monkeypatch.setattr(config, "QUEUE_SHALLOW_AHEAD", 0)
    assert bot.draft_ahead("shallow") == 1              # an .env 0 can't stop drafting


# ---- todo/58 (31 Oct): the next job is chosen JIT_LEAD_S before the writer's slot, so it answers the freshest post ----
def test_jit_holds_a_drafter_until_the_slot_is_near():
    assert config.JIT_LEAD_S == 7
    assert bot.jit_hold(NOW + 20, NOW, "shallow")             # the slot is 20 s away: wait
    assert bot.jit_hold(NOW + 7.5, NOW, "shallow")
    assert not bot.jit_hold(NOW + 7, NOW, "shallow")          # 7 s away: choose now
    assert not bot.jit_hold(NOW - 5, NOW, "shallow")          # the slot has passed (a late send): choose at once


def test_jit_never_holds_off_shallow_before_the_first_send_or_when_off(monkeypatch):
    for arm in ("fresh", "base"):
        assert not bot.jit_hold(NOW + 20, NOW, arm)           # fresh is the late-send guard's fill-ahead
    assert not bot.jit_hold(0.0, NOW, "shallow")              # nothing sent yet (and a dry run never sets next_write)
    assert not bot.jit_hold(NOW + 20, NOW, "shallow", lead=0)
    monkeypatch.setattr(config, "JIT_LEAD_S", 0)
    assert not bot.jit_hold(NOW + 20, NOW, "shallow")         # SWAN_JIT_LEAD_S=0: today's fill-ahead
    monkeypatch.setattr(config, "JIT_LEAD_S", 30)
    assert not bot.jit_hold(NOW + 20, NOW, "shallow")         # a longer lead chooses earlier


def test_the_drafter_checks_the_hold_before_and_after_it_waits():
    src = pathlib.Path(bot.__file__).read_text()
    assert src.count("jit_hold(next_write, time.time(), arm)") == 2      # full() and the race guard under mu


def test_the_queue_settings_are_env_switches(monkeypatch):
    names = ("JIT_LEAD_S", "QUEUE_SHALLOW_AHEAD", "REFRESH_S", "TRENDING_EVERY", "LEAD_HAIKU_SHARE")
    for name in names:
        assert name in config.STEALTH_ENV
        monkeypatch.setattr(config, name, getattr(config, name))       # stealth_from_env sets globals: restored after
    monkeypatch.setattr(config, "LEAD_HAIKU_SHARE", 0.5)                # the live value's type (conftest sets an int 0)
    assert config.stealth_from_env({"SWAN_JIT_LEAD_S": "0", "SWAN_QUEUE_SHALLOW_AHEAD": "2",
                                    "SWAN_LEAD_HAIKU_SHARE": "0.3"}) == dict(JIT_LEAD_S=0, QUEUE_SHALLOW_AHEAD=2,
                                                                            LEAD_HAIKU_SHARE=0.3)


def test_off_a_switchback_the_arm_is_base(monkeypatch):
    monkeypatch.setattr(config, "SWITCHBACK", [])
    assert bot.queue_arm(NOW) == "base"


def test_the_three_arms_rotate_through_a_day(monkeypatch):
    arms = ["base", "fresh", "shallow"]                     # the 26 Oct test, kept so it can be run again
    monkeypatch.setattr(config, "SWITCHBACK", [("arm_queue", arms, BLOCK)])
    day0 = NOW // 86400 * 86400
    seen = [bot.queue_arm(day0 + i * BLOCK) for i in range(3)]
    assert sorted(seen) == sorted(arms)                     # three consecutive blocks: one of each
    assert bot.queue_arm(day0) == bot.queue_arm(day0 + BLOCK - 1)       # one arm for a whole block


def test_live_queue_is_shallow_in_every_block(monkeypatch):
    assert config.QUEUE_ARMS == ["shallow"]                 # 27 Oct (Marc): the test ended, shallow everywhere
    monkeypatch.setattr(config, "SWITCHBACK", [("arm_queue", config.QUEUE_ARMS, BLOCK)])
    assert {bot.queue_arm(NOW + i * BLOCK) for i in range(8)} == {"shallow"}


def test_shallow_falls_back_to_fresh_after_late_sends_and_recovers(monkeypatch):
    monkeypatch.setattr(config, "SWITCHBACK", [("arm_queue", ["shallow"], BLOCK)])
    assert bot.queue_arm(NOW) == "shallow"
    late = [NOW - 60, NOW - 120, NOW - 200]
    assert bot.queue_arm(NOW, late) == "fresh"
    assert bot.queue_arm(NOW, late[:2]) == "shallow"                       # two late sends are not enough
    assert bot.queue_arm(NOW + config.QUEUE_GUARD_S + 300, late) == "shallow"   # they age out
    monkeypatch.setattr(config, "SWITCHBACK", [("arm_queue", ["base"], BLOCK)])
    assert bot.queue_arm(NOW, late) == "base"                              # the guard only touches shallow


def test_the_arm_is_logged_on_every_send():
    src = pathlib.Path(bot.__file__).read_text()
    assert '("queue_arm", "ready_n", "ready_s")' in src


# ---- the pick: the newest post under FRESH_MIN first in the fresh and shallow blocks (26 Oct) ----
def _pick_order(monkeypatch, arm, ages_min, scores=None, classes=None):
    """Post ids in the order next_target hands them out, for posts of these ages (minutes), queued oldest first."""
    import datetime as dt
    from swan_bot import targeting
    monkeypatch.setattr(config, "SWITCHBACK", [("arm_queue", [arm], BLOCK)] if arm else [])
    monkeypatch.setattr(config, "UNSURE_FIRST", False)
    monkeypatch.setattr(config, "TURNOUT_ARM", False)
    t = targeting.Targeter(None, log=lambda r: None)
    for pid, minutes in enumerate(ages_min, 1):
        created = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes)).isoformat()
        t._queue(dict(post_id=pid, author_id=1000 + pid, body="the referendum", created_at=created), "latest", None, None, 0,
                 (classes or {}).get(pid, "conditions"))
        t.candidates[pid]["score"] = (scores or {}).get(pid, 8.0)           # equal scores: priority ties at the fresh bonus
    out = []
    while (c := t.next_target(set(), set(), {}, set())):
        out.append(c["post"]["post_id"])
        t.candidates.pop(c["post"]["post_id"], None)
    return out


def test_equal_priority_fresh_posts_go_oldest_first_in_base_blocks(monkeypatch):
    assert _pick_order(monkeypatch, None, [8, 5, 2, 0.5]) == [1, 2, 3, 4]       # the tie sorted() keeps in arrival order
    assert _pick_order(monkeypatch, "base", [8, 5, 2, 0.5]) == [1, 2, 3, 4]


def test_fresh_and_shallow_blocks_pick_the_newest_post_first(monkeypatch):
    for arm in ("fresh", "shallow"):
        assert _pick_order(monkeypatch, arm, [8, 5, 2, 0.5]) == [4, 3, 2, 1], arm


def test_newest_first_only_orders_posts_under_fresh_min_and_keeps_the_rest_by_priority(monkeypatch):
    # posts 1 and 2 are older than FRESH_MIN: no bonus, the stronger read first. 3 and 4 are fresh: newest first, ahead of them.
    order = _pick_order(monkeypatch, "fresh", [90, 40, 6, 1], scores={1: 5.0, 2: 9.0})
    assert order == [4, 3, 2, 1]


def test_a_stronger_read_no_longer_beats_a_newer_fresh_post_in_fresh_blocks(monkeypatch):
    assert _pick_order(monkeypatch, "fresh", [9, 1], scores={1: 10.0, 2: 1.5}) == [2, 1]
    assert _pick_order(monkeypatch, "base", [9, 1], scores={1: 10.0, 2: 1.5}) == [1, 2]


def test_the_flag_turns_the_new_pick_order_off(monkeypatch):
    monkeypatch.setattr(config, "QUEUE_PICK_NEWEST", False)
    assert _pick_order(monkeypatch, "fresh", [8, 5, 2, 0.5]) == [1, 2, 3, 4]


# ---- todo/47 (27 Oct): the weak classes count as DOWNRANK_MIN minutes older in the newest-first pick ----
def test_a_fresh_conditions_post_goes_before_a_slightly_newer_unclear_one(monkeypatch):
    assert config.DOWNRANK_MIN == 2.5 and set(config.DOWNRANK_CLASSES) == {"unclear", "unsure", "off_topic"}
    assert _pick_order(monkeypatch, "shallow", [2, 1], classes={2: "unclear"}) == [1, 2]


def test_a_much_newer_weak_post_still_beats_an_older_strong_one(monkeypatch):
    assert _pick_order(monkeypatch, "shallow", [4, 0.5], classes={2: "unsure"}) == [2, 1]


def test_downrank_off_restores_newest_first(monkeypatch):
    monkeypatch.setattr(config, "DOWNRANK_MIN", 0)
    assert _pick_order(monkeypatch, "shallow", [2, 1], classes={2: "unclear"}) == [2, 1]
