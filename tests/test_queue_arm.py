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
    assert bot.draft_ahead("shallow") == config.QUEUE_SHALLOW_AHEAD == 2
    monkeypatch.setattr(config, "DRAFT_AHEAD", 1)
    assert bot.draft_ahead("shallow") == 1              # never deeper than the global cap


def test_off_a_switchback_the_arm_is_base(monkeypatch):
    monkeypatch.setattr(config, "SWITCHBACK", [])
    assert bot.queue_arm(NOW) == "base"


def test_the_three_arms_rotate_through_a_day(monkeypatch):
    monkeypatch.setattr(config, "SWITCHBACK", [("arm_queue", config.QUEUE_ARMS, BLOCK)])
    day0 = NOW // 86400 * 86400
    seen = [bot.queue_arm(day0 + i * BLOCK) for i in range(3)]
    assert sorted(seen) == sorted(config.QUEUE_ARMS)       # three consecutive blocks: one of each
    assert bot.queue_arm(day0) == bot.queue_arm(day0 + BLOCK - 1)       # one arm for a whole block


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
def _pick_order(monkeypatch, arm, ages_min, scores=None):
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
                 "conditions")
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
