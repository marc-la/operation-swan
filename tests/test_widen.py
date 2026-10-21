"""Widen the net (todo/23): every citizen group that can't cost us points, as capped arms below ordinary candidates."""
import datetime as dt
import json
import pathlib
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from swan_bot import config, targeting  # noqa: E402

ctn = targeting.ctn


def ago(minutes):
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes)).isoformat()


class _Citizens:
    """account_posts per citizen (403 for the private ones), likers, followers and get_post from dicts."""
    def __init__(self, posts=None, private=(), likers=None, followers=None, by_id=None):
        self.by_author, self.private = posts or {}, set(private)
        self.likers_of, self.followers_of, self.by_id = likers or {}, followers or {}, by_id or {}
        self.rate_limit, self.calls = None, []

    def account_posts(self, aid, limit=50, cursor=None):
        self.calls.append(("account_posts", aid))
        if aid in self.private:
            raise ctn.APIError("GET", f"/accounts/{aid}/posts", 403, "private")
        return self.by_author.get(aid, [])

    def likers(self, pid, limit=50, cursor=None):
        self.calls.append(("likers", pid))
        return [dict(account_id=a) for a in self.likers_of.get(pid, [])]

    def followers(self, aid, limit=50, cursor=None):
        self.calls.append(("followers", aid))
        return [dict(account_id=a) for a in self.followers_of.get(aid, [])]

    def get_post(self, pid):
        self.calls.append(("get_post", pid))
        return self.by_id[pid]


def post(pid, author, body, minutes=60, **kw):
    return dict(post_id=pid, author_id=author, created_at=ago(minutes), body=body, **kw)


@pytest.fixture
def only(monkeypatch):
    """Sweep from a short list of citizen ids, every arm on, no caps unless a test sets one."""
    def setup(ids, **flags):
        monkeypatch.setattr(targeting, "citizen_ids", lambda: list(ids))
        for k, v in dict(SWEEP_ARM=True, ENGAGED_ARM=True, OFF_TOPIC_ARM=True, OLDER_ARM=True, **flags).items():
            monkeypatch.setattr(config, k, v)
    return setup


def tgt(social=None, logged=None):
    return targeting.Targeter(social, log=(logged.append if logged is not None else lambda r: None))


def test_the_sweep_queues_each_citizens_latest_post_on_the_vote(only):
    only([100, 101, 102, 103])
    social = _Citizens({100: [post(1, 100, "lunch was great"), post(2, 100, "not sure about the referendum", 3000),
                              post(3, 100, "still torn on the vote", 4000)],
                        101: [post(4, 101, "my cat is asleep"), post(6, 101, "watched the sunset from the porch")],
                        103: [post(5, 103, "the referendum needs a sunset clause", 9000)]}, private={102})
    t = tgt(social)
    t._widen()
    assert set(t.candidates) == {2, 5}, "the most recent post on the vote, any age; nothing for off-topic-only 101"
    c = t.candidates[2]
    assert (c["group"], c["net"]) == ("sweep", "sweep") and t.items[2]["g"] == "sweep"
    assert t.swept["102"] > time.time() + 86400, "a private account is left for days"
    assert t.sweep_next == 0 and len(social.calls) == 4, "every id read once, then the cursor wraps"


def test_the_sweep_leaves_alone_citizens_we_wrote_to_this_week(only):
    only([100, 101])
    social = _Citizens({100: [post(1, 100, "the referendum")], 101: [post(2, 101, "the referendum")]})
    t = tgt(social)
    t.answered(post(99, 100, "the referendum"), "reply")
    t._widen()
    assert set(t.candidates) == {2} and ("account_posts", 100) not in social.calls


def test_the_sweep_keeps_to_its_read_budget_and_queue(only, monkeypatch):
    only(range(100, 200))
    monkeypatch.setattr(config, "SWEEP_READS_PER_REFRESH", 5)
    social = _Citizens({a: [post(a, a, "the referendum")] for a in range(100, 200)})
    t = tgt(social)
    t._widen()
    assert len(social.calls) == 5 and t.sweep_next == 5
    monkeypatch.setattr(config, "SWEEP_READS_PER_REFRESH", 50)
    monkeypatch.setattr(config, "SWEEP_QUEUE", 8)
    t._widen()
    assert t.queued("sweep") == 8 and len(social.calls) == 8, "reads stop once the queue is full"


def test_the_sweep_skips_hostile_deep_ours_and_firm_yes(only, monkeypatch):
    only([100, 101, 102])
    ours = dict(post_id=50, author_id=5000, created_at=ago(90), body="Vote No")
    social = _Citizens({100: [post(1, 100, "KITB sheep and their referendum")],
                        101: [post(2, 101, "why though on the referendum?", reply_to_post_id=50, root_post_id=50)],
                        102: [post(3, 102, "Voting yes on the referendum. #VoteYes")]}, by_id={50: ours})
    t = tgt(social)
    monkeypatch.setattr(t, "ours", lambda: [dict(account_id=5000, persona="mere", role="voice", status="active")])
    t._widen()
    assert not t.candidates
    assert {pid: t.items[pid]["why"] for pid in (1, 2, 3)} == {1: "hostile", 2: "reply_to_us", 3: "firm_yes"}
    assert all(t.items[pid]["o"] == "skipped" and t.items[pid]["g"] == "sweep" for pid in (1, 2, 3))


def test_groups_go_only_after_ordinary_candidates_and_within_their_cap(only, monkeypatch):
    only([100, 101, 102])
    monkeypatch.setattr(config, "SWEEP_PER_H", 1)
    monkeypatch.setattr(config, "SWEEP_NIGHT_PER_H", 1)
    social = _Citizens({100: [post(1, 100, "leaning yes on the referendum but only with a sunset clause", 5)],
                        101: [post(2, 101, "leaning yes on the referendum but only with a sunset clause", 5)]})
    t = tgt(social)
    t._widen()
    t._consider(post(3, 102, "honestly what is this referendum even for", 600), "latest")
    assert t.next_target(set(), set(), {})["post"]["post_id"] == 3, "an ordinary candidate first, whatever the score"
    c = t.next_target(set(), set(), {})
    assert c["group"] == "sweep" and c["post"]["post_id"] in (1, 2)
    assert t.next_target(set(), set(), {}) is None, "one an hour"
    left = ({1, 2} - {c["post"]["post_id"]}).pop()
    assert t.items[left]["why"] == "sweep_cap"
    t.requeue(c, "no_voice")                       # no voice free: the hand-out doesn't count
    assert t.next_target(set(), set(), {})["post"]["post_id"] == c["post"]["post_id"]


def test_a_group_switched_off_ends_its_candidates(only, monkeypatch):
    only([100])
    t = tgt(_Citizens({100: [post(1, 100, "the referendum")]}))
    t._widen()
    monkeypatch.setattr(config, "SWEEP_ARM", False)
    assert t.next_target(set(), set(), {}) is None
    assert t.items[1]["o"] == "skipped" and t.items[1]["why"] == "sweep_off"


def test_older_posts_stay_queued_at_low_priority(monkeypatch):
    monkeypatch.setattr(config, "OLDER_ARM", True)
    t = tgt()
    t._consider(post(1, 100, "not sure about the referendum, i'd need a sunset", 40 * 60), "news")
    t._consider(post(2, 101, "honestly what is this referendum even for", 30 * 60), "news")
    t._expire()
    assert set(t.candidates) == {1, 2}, "a 40 h post is kept with the older arm"
    assert t.next_target(set(), set(), {})["post"]["post_id"] == 2, "the 30 h one goes first, though it reads lower"
    c = t.next_target(set(), set(), {})
    assert c["group"] == "older" and t.items[1]["g"] == "older"
    monkeypatch.setattr(config, "OLDER_ARM", False)
    u = tgt()
    u._consider(post(3, 100, "not sure about the referendum", 30 * 60), "news")
    u.items[3]["c"] -= 8 * 3600                    # now 38 h old
    u._expire()
    assert not u.candidates and u.items[3]["o"] == "lost", "without the arm it ages out at 36 h, as before"


def test_off_topic_posts_under_the_arm(only):
    only([])
    t = tgt()
    t._consider(post(1, 100, "the ferry was late again, third time this week", 5), "latest")
    t._consider(post(2, 101, "WHAT A JOKE THIS FERRY SERVICE IS, ABSOLUTELY USELESS", 5), "latest")
    assert t.candidates[1]["group"] == "off_topic" and t.items[2]["why"] == "off_topic"
    c = t.next_target(set(), set(), {})
    assert c["group"] == "off_topic" and c["net"] == "off_topic"


def test_lean_no_goes_out_with_the_turnout_line(monkeypatch):
    monkeypatch.setattr(config, "TURNOUT_ARM", True)
    t = tgt()
    t._consider(post(1, 100, "My No vote is settled. Referendum? No thanks.", 5), "latest")
    c = t.next_target(set(), set(), {})
    assert c["group"] == "turnout" and t.items[1]["g"] == "turnout"
    monkeypatch.setattr(config, "TURNOUT_ARM", False)
    u = tgt()
    u._consider(post(1, 100, "My No vote is settled. Referendum? No thanks.", 5), "latest")
    assert "group" not in u.next_target(set(), set(), {})


def test_engaged_citizens_are_answered_from_the_voice_they_liked(only, monkeypatch):
    only([])
    social = _Citizens({5000: [dict(post_id=60, author_id=5000, created_at=ago(120), body="Vote No")],
                        100: [post(1, 100, "the ferry was late again", 30), post(2, 100, "the referendum", 900)],
                        101: [post(3, 101, "the ferry was late again", 30)]},
                       likers={60: [100, 9999]}, followers={5000: [101]})
    t = tgt(social)
    monkeypatch.setattr(t, "ours", lambda: [dict(account_id=5000, persona="mere", role="voice", status="active")])
    t._widen()
    assert t.engaged_pool == {}, "the team bot 9999 is not a citizen; both citizens read"
    assert t.candidates[2]["prefer"] == "mere" and t.candidates[2]["group"] == "engaged", "their post on the vote first"
    assert t.candidates[3]["group"] == "off_topic" and t.candidates[3]["net"] == "engaged"
    c = t.next_target(set(), set(), {})
    assert c["net"] == "engaged" and c["prefer"] == "mere"


def test_touched_comes_from_the_action_log_once(tmp_path):
    now = dt.datetime.now(dt.timezone.utc)
    rows = [dict(ts=now.isoformat(), act="reply", live=True, target_author=100),
            dict(ts=(now - dt.timedelta(days=9)).isoformat(), act="reply", live=True, target_author=101),
            dict(ts=now.isoformat(), act="reply", live=False, target_author=102),
            dict(ts=now.isoformat(), act="thread", live=True, target_author=103)]
    path = tmp_path / "actions.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    t = tgt()
    t.seed_touched(path)
    assert set(t.touched) == {"100"}
    u = tgt()
    u.load(json.loads(json.dumps(t.dump())))
    assert set(u.touched) == {"100"}, "kept with the state, not read again"


def test_the_refresh_record_has_a_line_per_group(only):
    only([100])
    t = tgt(_Citizens({100: [post(1, 100, "the referendum")]}))
    t._widen()
    g = t.groups()
    assert set(g) == {"sweep", "older", "off_topic", "engaged", "turnout"}
    assert g["sweep"]["queued"] == 1 and g["sweep"]["funnel"] and g["sweep"]["of"] == 1
