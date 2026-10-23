"""swan_blue (todo/43): the whole tick against a fake platform, writes off (a dry run). No network, no secrets."""
import json
import time

import capturethenarrative as ctn

from swan_blue import fleets as F
from test_blue import S, blue
from test_blue_fleets import burst
from test_blue_scan import ids


class Platform:
    """Just enough of LegitSocial for one Blue tick: no feed, a few accounts, pages and posts."""
    rate_limit = None

    def __init__(self):
        self.accounts_ = burst(5000, 40, 0) + burst(6000, 40, 4000)
        self.pages = {5001: ids(100, 50), 5002: ids(200, 50), 6001: ids(300, 50)}
        self.gone, self.calls = set(), []

    def feed_trending(self, limit=50):
        return ctn.Page([])

    feed_latest = feed_trending

    def accounts(self, limit=50, cursor=None, **kw):
        i = int(cursor or 0)
        self.calls.append("accounts")
        return ctn.Page(self.accounts_[i:i + limit], str(i + limit) if i + limit < len(self.accounts_) else None)

    def account_posts(self, aid, limit=50, cursor=None):
        self.calls.append("account_posts")
        if aid not in self.pages:
            raise ctn.APIError("GET", "/accounts/posts", 403, "{}")
        newest = time.time() - 300
        return ctn.Page([dict(post_id=p, created_at=S.iso(newest - 600 * k), kind="post")
                         for k, p in enumerate(self.pages[aid][:limit])])

    def account_likes(self, aid, limit=50, cursor=None):
        return ctn.Page([])

    def iterate(self, method, *args, max_items=None, **kw):
        return iter(list(method(*args, limit=max_items or 50, **kw)))

    def get_post(self, pid):
        if pid in self.gone:
            raise ctn.APIError("GET", "/posts", 404, "{}")
        return {"post_id": pid, "author_id": 5001}


def test_a_dry_tick_runs_the_new_reads_and_writes_the_status(tmp_path, monkeypatch):
    b = blue(tmp_path, monkeypatch)
    b.social = Platform()
    for k in ("BLUE_SCAN_EVERY_S", "BLUE_SCAN_FILE", "BLUE_ACCOUNT_LIVE_H", "BLUE_FLEET_EVERY_S", "BLUE_SIBLINGS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(S, "SNAPSHOT_FILE", tmp_path / "latest_snapshot.json")
    monkeypatch.setattr(S, "PORTAL_FILE", tmp_path / "portal.json")
    monkeypatch.setattr(S, "FEED_LOG", tmp_path / "feed.jsonl")
    # a live lead with a hidden post, and Latest showing 5002 and 6001 posting
    t = time.time()
    b.s["harvest"]["5001"] = dict(hidden_post=1, checked=t, actions=100, ring_posts=[9], ready=True)
    (tmp_path / "latest_snapshot.json").write_text(json.dumps(dict(read_at=S.iso(), posts=[
        dict(post_id=1, author_id=5002, created_at=S.iso(t - 60), body="x"),
        dict(post_id=2, author_id=6001, created_at=S.iso(t - 90), body="y")])))
    b.tick()
    b.tick()
    st = json.loads((tmp_path / "status.dry.json").read_text())
    assert st["fleets"]["on"] and st["fleets"]["accounts"] == 80 and st["fleets"]["fleets"] == 2
    assert st["leads_live"]["live"] == 1 and st["ready_accounts"] == 1        # 5001 was read live, ready to file
    assert st["scan"]["tracked"] == 2 and st["scan"]["stats"]["reads"] >= 2 and st["scan"]["leads"] == []
    assert st["clusters"]["today"] == 0 and st["mode"] == "off"                # a dry run files nothing
    assert b.s["reports"] == {}
    assert (tmp_path / "scan.dry.json").exists() and (tmp_path / "fleets.dry.json").exists()
    assert not (tmp_path / "scan.json").exists() and not (tmp_path / "fleets.json").exists()   # the live files
    # sibling queue: the live lead's fleet mates were read after its liveness read
    assert b.sc["stats"]["siblings"] > 0 and b.s["harvest"]["5001"]["sib"]
    n = b.social.calls.count("accounts")
    b.tick()
    assert b.social.calls.count("accounts") == n                              # the account list is built: not again
