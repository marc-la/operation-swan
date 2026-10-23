"""swan_blue (todo/43 item 1): the liveness filter on account reports. No network, no secrets."""
import json
import time

import capturethenarrative as ctn

from test_blue import FakeSocial, Reporter, S, blue, ev, post


class LiveSocial(FakeSocial):
    """account_posts(limit=1) answers from {account: seconds since its newest post}; `fail` raises a 500."""

    def __init__(self, idle=None, fail=False):
        super().__init__()
        self.idle, self.fail, self.reads = idle or {}, fail, []

    def account_posts(self, aid, limit=50, cursor=None):
        self.reads.append(aid)
        if self.fail:
            raise ctn.APIError("GET", "/accounts/posts", 500, '{"error": "boom"}')
        if aid not in self.idle:
            return []
        return [dict(post_id=900 + aid, created_at=S.iso(time.time() - self.idle[aid]))]


def lead(aid, **kw):
    h = dict(hidden_post=aid + 1, checked=time.time(), actions=100, ring_posts=[1], ready=True)
    h.update(kw)
    return h


def acct(aid):
    return dict(key=f"a{aid}", kind="account", target=aid, author=aid, label="cA", detail="x", classes=["hidden_post"],
                ev=13.5, pg=0.0, base=None)


def live_blue(tmp_path, monkeypatch, social):
    b = blue(tmp_path, monkeypatch)
    b.live = True
    b.ours = {3000}
    b.social, b.reporter = social, Reporter()
    monkeypatch.delenv("BLUE_ACCOUNT_LIVE_H", raising=False)
    return b


def log(tmp_path):
    return [json.loads(x) for x in (tmp_path / "reports.jsonl").read_text().splitlines()]


def test_live_account_files_with_its_idle_hours_and_an_idle_one_is_skipped(tmp_path, monkeypatch):
    b = live_blue(tmp_path, monkeypatch, LiveSocial({7001: 25 * 60, 7002: 5 * 3600}))
    b.s["harvest"] = {"7001": lead(7001), "7002": lead(7002)}
    assert b.file(acct(7001))
    assert not b.file(acct(7002)) and b.skip == "idle"
    assert b.reporter.filed == [("account", 7001)]                      # the idle one never reached the platform
    r = b.s["reports"]["a7001"]
    assert r["live"] == "live" and 0.4 < r["idle_h"] < 0.45
    rec = {x["act"]: x for x in log(tmp_path)}
    assert rec["report"]["idle_h"] == r["idle_h"] and rec["report"]["live"] == "live"
    assert rec["skip"]["reason"] == "idle" and rec["skip"]["key"] == "a7002" and rec["skip"]["idle_h"] == 5.0
    assert "a7002" not in b.s["reports"]                                # not refused: it may come back to life
    assert b.live_summary()["idle_skips_today"] == 1


def test_recheck_at_filing_catches_a_lead_that_went_stale(tmp_path, monkeypatch):
    t = time.time()
    b = live_blue(tmp_path, monkeypatch, LiveSocial({7001: 1.7 * 3600 + 25 * 60}))
    # read 25 min ago: its newest post was 1.7 h older than that read, so live then; not posted since
    b.s["harvest"] = {"7001": lead(7001, live_at=t - 25 * 60, last_post=t - 1.7 * 3600 - 25 * 60)}
    assert b.live_state(b.s["harvest"]["7001"])[0] == "live"           # the ranking still sees it live
    assert [c["key"] for c in b.candidates()] == ["a7001"]
    assert not b.file(acct(7001))                                       # the filing-time read says 2.1 h idle
    assert b.social.reads == [7001] and b.reporter.filed == []
    assert b.candidates() == []                                         # and the next ranking drops it


def test_a_read_from_this_very_pass_stands_as_the_recheck(tmp_path, monkeypatch):
    t = time.time()
    b = live_blue(tmp_path, monkeypatch, LiveSocial({7001: 600}))
    b.s["harvest"] = {"7001": lead(7001, live_at=t - 20, last_post=t - 620)}
    assert b.file(acct(7001)) and b.social.reads == []


def test_failed_liveness_read_files_blind_at_most_once_per_ten_minutes(tmp_path, monkeypatch):
    b = live_blue(tmp_path, monkeypatch, LiveSocial(fail=True))
    b.s["harvest"] = {"7001": lead(7001), "7002": lead(7002)}
    assert b.file(acct(7001)) and b.s["reports"]["a7001"]["live"] == "unknown"
    assert b.s["reports"]["a7001"]["idle_h"] is None
    assert not b.file(acct(7002)) and b.skip == "read_failed"
    t0 = time.time()
    monkeypatch.setattr(S, "now", lambda: t0 + S.LIVE_BLIND_GAP_S + 1)
    assert b.file(acct(7002))                                           # ten minutes on: one more blind try
    assert b.reporter.filed == [("account", 7001), ("account", 7002)]


def test_no_liveness_read_left_means_no_blind_filing(tmp_path, monkeypatch):
    b = live_blue(tmp_path, monkeypatch, LiveSocial({7001: 600}))
    b.s["harvest"] = {"7001": lead(7001)}
    monkeypatch.setattr(b, "read_ok", lambda: False)                    # the 300/min bucket is nearly spent
    assert not b.file(acct(7001)) and b.skip == "budget" and b.social.reads == []
    b.file_reads = S.LIVE_FILE_READS_PER_TICK
    monkeypatch.setattr(b, "read_ok", lambda: True)
    assert not b.file(acct(7001)) and b.skip == "budget"
    b.file_reads = 0
    assert b.file(acct(7001))


def test_a_live_account_is_priced_at_point_nine_and_unknown_at_point_five():
    assert ev.account_ev(0) == 0.9 * 15 and ev.account_ev(0, live=False) == ev.ACCOUNT_UPHELD_UNKNOWN * 15
    assert ev.account_ev(5) == 0.9 * 15 * 0.5 and ev.account_ev(10) < S.MIN_EV


def test_live_lead_outranks_a_half_rate_post_and_an_unknown_one_does_not(tmp_path, monkeypatch):
    b = blue(tmp_path, monkeypatch)
    t = time.time()
    b.s["reports"] = {f"p{i}": dict(kind="post", status="pending", filed=t, label="cA") for i in range(5)}
    b.s["posts"]["100"] = post(100, "cA", 5000)                           # team A already has 5 awards: half rate
    b.s["harvest"] = {"7001": lead(7001, live_at=t - 60, last_post=t - 600),            # live, team B
                      "7002": lead(7002, live_err=t - 60)}                               # liveness unknown, team C
    b.s["labels"].update({"7001": "cB", "7002": "cC"})
    order = [c["key"] for c in b.ranked()]
    ev_of = {c["key"]: c["ev"] for c in b.ranked()}
    assert ev_of["a7001"] == 13.5 and ev_of["a7002"] == 7.5 and ev_of["p100"] == 10.6
    assert order == ["a7001", "p100", "a7002"]                           # live 13.5 > half-rate post 10.6 > unknown 7.5


def test_idle_and_unread_leads_are_not_candidates(tmp_path, monkeypatch):
    b = blue(tmp_path, monkeypatch)
    t = time.time()
    b.s["harvest"] = {"1": lead(1, live_at=t - 60, last_post=t - 600),               # live
                      "2": lead(2, live_at=t - 60, last_post=t - 5 * 3600),          # idle
                      "3": lead(3),                                                  # never read
                      "4": lead(4, live_at=t - 3600, last_post=t - 3600),            # read too long ago: unread
                      "5": lead(5, live_err=t - 60),                                 # last read failed
                      "6": lead(6, live_at=t - 60, last_post=None)}                  # never posted
    assert {c["key"]: c["live"] for c in b.candidates()} == {"a1": "live", "a5": "unknown"}
    assert {k: b.live_summary()[k] for k in ("live", "idle", "unread", "unknown")} == dict(live=1, idle=2, unread=2,
                                                                                         unknown=1)


def test_filter_off_prices_as_before_and_reads_nothing(tmp_path, monkeypatch):
    b = live_blue(tmp_path, monkeypatch, LiveSocial({7001: 9 * 3600}))
    monkeypatch.setenv("BLUE_ACCOUNT_LIVE_H", "0")
    b.s["harvest"] = {"7001": lead(7001)}
    cands = b.candidates()
    assert [c["key"] for c in cands] == ["a7001"] and cands[0]["live"] == "off"
    assert b.ranked()[0]["ev"] == 7.5                                    # the old 0.5
    b.refresh_live()
    assert b.file(acct(7001)) and b.social.reads == [] and b.reporter.filed == [("account", 7001)]


def test_refresh_reads_unread_first_a_few_a_tick_and_idle_ones_rarely(tmp_path, monkeypatch):
    t = time.time()
    b = live_blue(tmp_path, monkeypatch, LiveSocial({1: 600, 2: 5 * 3600, 3: 600, 4: 600, 5: 600}))
    monkeypatch.setattr(S, "LIVE_REFRESH_PER_TICK", 3)
    b.s["harvest"] = {"1": lead(1, live_at=t - 20 * 60, last_post=t - 25 * 60),     # live, read 20 min ago: due
                      "2": lead(2, live_at=t - 25 * 60, last_post=t - 6 * 3600),    # idle 5.6 h, read 25 min ago: not due
                      "3": lead(3), "4": lead(4),                                    # never read: first
                      "5": lead(5, ready=False),                                     # under 100 actions: not read
                      "6": lead(6, live_at=t - 120, last_post=t - 120)}              # fresh
    b.s["reports"]["a6"] = dict(kind="account", status="pending", filed=t)
    b.refresh_live()
    assert sorted(b.social.reads) == [1, 3, 4]
    assert b.live_state(b.s["harvest"]["3"])[0] == "live" and b.live_state(b.s["harvest"]["1"])[0] == "live"
    assert b.live_state(b.s["harvest"]["2"])[0] == "idle"
    b.social.reads.clear()
    b.refresh_live()
    assert b.social.reads == []                                          # all fresh now


def test_refresh_backs_off_after_a_failed_read(tmp_path, monkeypatch):
    b = live_blue(tmp_path, monkeypatch, LiveSocial(fail=True))
    b.s["harvest"] = {"1": lead(1)}
    b.refresh_live()
    b.refresh_live()
    assert b.social.reads == [1]                                         # not hammered
    assert b.live_state(b.s["harvest"]["1"])[0] == "unknown"


def test_an_idle_skip_does_not_use_up_the_confirming_try_after_a_genuine_ruling(tmp_path, monkeypatch):
    b = live_blue(tmp_path, monkeypatch, LiveSocial({7001: 5 * 3600, 7002: 600}))
    b.s["harvest"] = {"7001": lead(7001), "7002": lead(7002)}
    b.s.update(lock_until=time.time() + 3600, lock_src="estimate", lock_confirm=True)
    b.fill([dict(acct(7001), kind="account"), acct(7002)], "auto")
    assert b.reporter.filed == [("account", 7002)] and b.s["lock_confirm"] is False
    assert not b.locked()                                                # the platform took it: the lock is over


def test_harvest_takes_the_newest_post_time_from_the_read_it_already_makes(tmp_path, monkeypatch):
    b = blue(tmp_path, monkeypatch)
    t = time.time()

    class Social(FakeSocial):
        account_posts = account_likes = None

        def iterate(self, fn, *a, max_items=100):
            return iter([dict(created_at=S.iso(t - 900))] + [dict(created_at=S.iso(t - 9000))] * (max_items - 1))
    b.social = Social()
    b.s["harvest"]["7001"] = dict(hidden_post=5, checked=0)
    b.harvest()
    h = b.s["harvest"]["7001"]
    assert h["ready"] and abs(h["last_post"] - (t - 900)) < 2 and b.live_state(h)[0] == "live"
