"""Swarm: who counts as Vote No, the per-run caps, registration against the team cap, live writes (no network)."""
import datetime as dt
import json
import pathlib
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import capturethenarrative as ctn  # noqa: E402
from swan_bot import config, swarm  # noqa: E402


def post(pid, body, author=3000, hours=1, **kw):
    t = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
    return {**dict(post_id=pid, body=body, author_id=author, created_at=t.isoformat(), kind="post"), **kw}


@pytest.fixture(autouse=True)
def tmp_paths(tmp_path, monkeypatch):
    for name, sub in (("SECRETS", "secrets"), ("DATA", "data"), ("LOGS", "logs")):
        (tmp_path / sub).mkdir()
        monkeypatch.setattr(config, name, tmp_path / sub)
    monkeypatch.setattr(config, "ACCOUNTS_FILE", tmp_path / "secrets/swan_accounts.json")
    monkeypatch.setattr(config, "SWARM_ACCOUNTS_FILE", tmp_path / "secrets/swarm_accounts.json")
    monkeypatch.setattr(config, "SWARM_STATE_FILE", tmp_path / "data/swarm_state.json")
    monkeypatch.setattr(config, "ACTIONS_LOG", tmp_path / "logs/swan_actions.jsonl")
    monkeypatch.setattr(config, "SWARM_OFF_FILE", tmp_path / "SWARM_OFF")
    monkeypatch.setattr(swarm.Swarm, "team_active", lambda self: len(self.active()))
    monkeypatch.setattr(swarm.feeds, "SNAPSHOT_FILE", tmp_path / "data/latest_snapshot.json")
    monkeypatch.setattr(swarm.feeds, "FEED_LOG", tmp_path / "logs/feed_reads.jsonl")
    return tmp_path


class FakeAccount:
    def __init__(self, social, name):
        self.social, self.name = social, name
        self.rate_limit = SimpleNamespace(remaining=25, limit=30)

    def view(self, pid):
        self.social.calls.append(("view", self.name, pid))

    def like(self, pid):
        self.social.calls.append(("like", self.name, pid))

    def repost(self, pid):
        self.social.calls.append(("repost", self.name, pid))
        self.rate_limit = SimpleNamespace(remaining=self.social.write_left, limit=3)
        return {"post_id": 90000 + pid}


class FakeSocial:
    def __init__(self, trending=(), latest=(), tags=None, write_left=3):
        self.trending, self.latest, self.tags = list(trending), list(latest), tags or {}
        self.calls, self.write_left, self.n = [], write_left, 0

        swarm.feeds.write_snapshot(self.latest, self.trending, swarm.feeds.now_iso())

    def feed_trending(self, limit=50):
        raise AssertionError("the swarm must not read feeds live")

    feed_latest = feed_trending

    def tag_posts(self, tag_id, limit=50, sort=None):
        return self.tags.get(tag_id, [])

    def account_from_token(self, token):
        return FakeAccount(self, token)

    def register(self, username, password, code, display_name=None):
        self.n += 1
        return SimpleNamespace(token=username, account_id=5000 + self.n)


def test_supports_no():
    assert swarm.supports_no(post(1, "Voting No on the referendum. Keep the beaches open."))
    assert swarm.supports_no(post(2, "Show us the venue list first #choicenotcoercion"), from_tag=True)
    assert swarm.supports_no(post(3, "Long day at the market #keepkingstoniaopen"))
    assert not swarm.supports_no(post(4, "Mandate now, protect Kingstonia #voteyes"))
    assert not swarm.supports_no(post(5, "The #voteno crowd should just vote yes and protect kingstonia"))
    assert not swarm.supports_no(post(6, "I'm voting No on the referendum", kind="repost"))
    assert not swarm.supports_no(post(7, "Nice weather at the reef today"))


def test_no_snapshot_means_tags_only():
    social = FakeSocial(trending=[post(1, "Voting No on the referendum")], tags={113: [post(2, "No. #voteno")]})
    swarm.feeds.SNAPSHOT_FILE.unlink()
    assert set(swarm.scan(social, say=lambda *_: None)) == {2}


def test_scan_merges_sources_and_drops_old():
    good = post(10, "Voting No on the referendum, the venue list isn't even out")
    tagged = post(11, "Who decides which shops? #choicenotcoercion")
    old = post(12, "Voting No on the referendum", hours=30)
    social = FakeSocial(trending=[good, old], tags={193: [tagged, good]})
    found = swarm.scan(social, say=lambda *_: None)
    assert set(found) == {10, 11}
    assert found[10]["rank"] == 0 and found[10]["tags"] == {"choicenotcoercion"}


def test_dry_run_plans_within_caps_and_writes_nothing():
    posts = [post(100 + i, f"Voting No on the referendum, reason {i}") for i in range(20)]
    social = FakeSocial(trending=posts)
    s = swarm.Swarm(social, live=False, say=lambda *_: None)
    out = s.run_once()
    assert out["likes"] <= config.SWARM_LIKES_PER_SCAN and out["reposts"] == config.SWARM_REPOSTS_PER_SCAN
    assert social.calls == [] and social.n == 0
    assert not config.SWARM_ACCOUNTS_FILE.exists() and not config.SWARM_STATE_FILE.exists()


def live_swarm(social, n=5):
    recs = [dict(role="swarm", username=f"s{i}", token=f"s{i}", password="x", account_id=7000 + i,
                 status="active") for i in range(n)]
    config.SWARM_ACCOUNTS_FILE.write_text(json.dumps(recs))
    return swarm.Swarm(social, live=True, code="X" * 16, say=lambda *_: None, sleep=lambda s: None)


def test_live_likes_reposts_and_never_repeats():
    p1 = post(200, "Voting No on the referendum", author=7001)    # written by swarm account s1
    p2 = post(201, "No from me, the venue list is missing", reply_to_post_id=5)  # a reply: like, never repost
    social = FakeSocial(trending=[p1, p2])
    s = live_swarm(social)
    s.state["next_register"] = 1e12
    s.run_once()
    likes = [c for c in social.calls if c[0] == "like"]
    assert likes and not any(name == "s1" and pid == 200 for _, name, pid in likes)   # never likes its own post
    assert [c[2] for c in social.calls if c[0] == "repost"] == [200]
    assert all(("view", n, p) in social.calls for _, n, p in likes)                    # a view before each like
    log = [json.loads(line) for line in config.ACTIONS_LOG.read_text().splitlines()]
    assert all(r["owner"] == "minhnguyenhoang" for r in log)
    assert {r["role"] for r in log if r["act"] in ("like", "repost")} == {"swarm"}
    social.calls.clear()
    s2 = swarm.Swarm(social, live=True, code="X" * 16, say=lambda *_: None, sleep=lambda s: None)
    s2.run_once(register=False)
    assert social.calls == []                                   # same posts next run: nothing repeated


def test_reposts_stop_when_write_budget_is_low():
    posts = [post(300 + i, f"Voting No on the referendum {i}") for i in range(5)]
    social = FakeSocial(trending=posts, write_left=1)
    s = live_swarm(social)
    s.state["next_register"] = 1e12
    s.run_once()
    assert len([c for c in social.calls if c[0] == "repost"]) == 1


def test_registration_respects_team_cap_and_size(monkeypatch):
    social = FakeSocial()
    s = swarm.Swarm(social, live=True, code="X" * 16, say=lambda *_: None)
    monkeypatch.setattr(swarm.Swarm, "team_active", lambda self: config.MAX_ACTIVE)
    assert s.maybe_register() is None and social.n == 0
    monkeypatch.setattr(swarm.Swarm, "team_active", lambda self: 10)
    s.state["next_register"] = 0
    name = s.maybe_register()
    rec = json.loads(config.SWARM_ACCOUNTS_FILE.read_text())[0]
    assert rec["username"] == name and rec["owner"] == "minhnguyenhoang" and rec["role"] == "swarm"
    assert s.maybe_register() is None                           # 4-9 min gap before the next one
    s.records = [dict(username=f"u{i}") for i in range(config.SWARM_SIZE)]
    s.state["next_register"] = 0
    assert s.maybe_register() is None                           # 20 is the lifetime size


def test_register_403_backs_off():
    class Full(FakeSocial):
        def register(self, *a, **k):
            raise ctn.APIError("POST", "/auth/register", 403, '{"error": "account allowance used up"}')
    s = swarm.Swarm(Full(), live=True, code="X" * 16, say=lambda *_: None)
    s.team_active = lambda: 0
    assert s.maybe_register() is None and s.state["next_register"] > 3000


def test_swarm_off_pauses():
    config.SWARM_OFF_FILE.touch()
    social = FakeSocial(trending=[post(1, "Voting No on the referendum")])
    assert swarm.Swarm(social, live=True, say=lambda *_: None).run_once() == {}
    assert social.calls == []


def test_bot_counts_swarm_against_cap():
    config.SWARM_ACCOUNTS_FILE.write_text(json.dumps([dict(status="active"), dict(status="suspended")]))
    assert config.swarm_active() == 1
