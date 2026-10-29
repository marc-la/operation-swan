"""swan_blue (todo/43 item 2): the live-lead scanner. No network, no secrets."""
import json
import re

import capturethenarrative as ctn

from swan_blue import scan
from test_blue import FakeSocial, S, blue, ev

T0 = 1792800000.0                     # a fixed "now" (2026-10-24 ~ 01:20 UTC)


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t


class ScanSocial(FakeSocial):
    """account_posts from {account: [post ids newest first]}, posted one every `step` s ending `idle` s ago;
    get_post answers 404 for `gone` (and for any id no account page still lists, if `strict`)."""

    def __init__(self, clock, pages=None, step=600):
        super().__init__()
        self.clock, self.pages, self.step = clock, pages or {}, step
        self.reads, self.asked, self.idle = [], [], {}
        self.rate_limit = None

    def account_posts(self, aid, limit=50, cursor=None):
        self.reads.append(aid)
        ids = self.pages.get(aid)
        if ids is None:
            raise ctn.APIError("GET", "/accounts/posts", 403, '{"error": "private"}')
        newest = self.clock() - self.idle.get(aid, 300)
        return [dict(post_id=p, created_at=S.iso(newest - k * self.step)) for k, p in enumerate(ids[:limit])]

    def get_post(self, pid):
        self.asked.append(pid)
        return super().get_post(pid)


def ids(first, n):
    return list(range(first + n - 1, first - 1, -1))                  # newest first


def scan_blue(tmp_path, monkeypatch, pages, **kw):
    clock = Clock()
    monkeypatch.setattr(S, "now", clock)
    b = blue(tmp_path, monkeypatch)
    b.social = ScanSocial(clock, pages, **kw)
    for k in ("BLUE_SCAN_EVERY_S", "BLUE_SCAN_FILE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("BLUE_SCAN_FILE", "0")       # these tests start from "logged only" (the live default is 1 since 29 Oct)
    return b, clock


def run_pass(b, clock, aids):
    """Make the accounts known as live posters, then run ticks of the scanner until the pass is done."""
    posts = [dict(post_id=1, author_id=int(a), created_at=S.iso(clock() - b.social.idle.get(int(a), 60))) for a in aids]
    scan.observe(b.sc, posts, lambda a: a > 2343, clock())
    for _ in range(100):
        b.scan_step()
        if not b.sc["todo"]:
            return
    raise AssertionError("pass never finished")


def vanish(b, aid, pid):
    b.social.pages[aid] = [p for p in b.social.pages[aid] if p != pid]
    b.social.gone.add(pid)


def log(tmp_path):
    return [json.loads(x) for x in (tmp_path / "reports.jsonl").read_text().splitlines()]


def test_a_post_missing_from_the_page_is_a_candidate_one_pushed_off_the_end_is_not():
    prev = ids(100, 50)                                               # 149 ... 100
    assert scan.vanished(prev, [p for p in prev if p != 140]) == [140]
    newer = list(range(155, 105, -1))                                 # 6 new posts: 100-105 fell off the 50-id page
    assert scan.vanished(prev, newer) == [p for p in range(106, 150) if p not in newer] == []
    assert scan.vanished(prev, [p for p in newer if p != 130] + [105]) == [130]       # the page refills from below
    assert scan.vanished(prev, []) == [] and scan.vanished([], prev) == []
    short = [149, 148]                                                # the whole history fits one page: all gone is gone
    assert scan.vanished([149, 148, 147], short) == [147]


def test_pace_is_stated_only_when_measured():
    assert scan.pace(50, 3600 * 5) == 9.8 and scan.pace(50, 300) is None       # 49 intervals in 5 h
    assert scan.pace_text(50, 5 * 3600) == "50 times in the last 5.0 hours (about 9.8 an hour)"
    assert scan.pace_text(40, 1800) == "40 times in the last 30 minutes"


def test_first_pass_snapshots_second_pass_finds_the_vanished_post(tmp_path, monkeypatch):
    b, clock = scan_blue(tmp_path, monkeypatch, {7001: ids(100, 50), 7002: ids(200, 50)})
    run_pass(b, clock, [7001, 7002])
    assert set(b.sc["snap"]) == {"7001", "7002"} and b.sc["cand"] == {}
    assert all(len(v["ids"]) <= scan.PAGE for v in b.sc["snap"].values())
    vanish(b, 7001, 120)
    clock.t += S.SCAN_EVERY_S + 60
    run_pass(b, clock, [7001, 7002])
    assert list(b.sc["cand"]) == ["7001"] and list(b.sc["cand"]["7001"]) == ["120"]
    assert b.sc["leads"] == {}                                        # one look is not enough
    assert [x for x in log(tmp_path) if x["act"] == "scan"][0]["vanished"] == [120]


def test_a_lead_needs_two_404s_ten_minutes_apart(tmp_path, monkeypatch):
    b, clock = scan_blue(tmp_path, monkeypatch, {7001: ids(100, 50)})
    run_pass(b, clock, [7001])
    vanish(b, 7001, 120)
    clock.t += S.SCAN_EVERY_S + 60
    run_pass(b, clock, [7001])                                        # the pass's own tick already asked once
    assert b.social.asked == [120] and b.sc["cand"]["7001"]["120"][1] > 0 and b.sc["leads"] == {}
    clock.t += 300
    b.scan_step()
    assert b.social.asked == [120]                                    # five minutes on: not due
    clock.t += scan.CONFIRM_GAP_S
    b.scan_step()
    assert b.social.asked == [120, 120]
    lead = b.sc["leads"]["7001"]
    assert lead["vanished"] == [120] and lead["by"] == "scan" and lead["filed"] == "off" and b.sc["cand"] == {}
    rec = [x for x in log(tmp_path) if x["act"] == "lead"][0]
    assert rec["by"] == "scan" and rec["account"] == 7001 and rec["vanished"] == [120] and rec["file"] is False
    assert rec["posts_per_h"] == 6.0 and rec["last_post"]                 # 50 posts, ten minutes apart: 6 an hour


def test_a_post_that_is_still_visible_or_comes_back_is_dropped(tmp_path, monkeypatch):
    b, clock = scan_blue(tmp_path, monkeypatch, {7001: ids(100, 50), 7002: ids(200, 50)})
    run_pass(b, clock, [7001, 7002])
    b.social.pages[7001].remove(120)                                  # off the page but get_post still answers
    b.social.pages[7002].remove(230)
    b.social.gone.add(230)
    clock.t += S.SCAN_EVERY_S + 60
    run_pass(b, clock, [7001, 7002])
    assert b.sc["stats"]["visible"] == 1 and list(b.sc["cand"]) == ["7002"]   # 7001's 120 was visible: dropped
    b.social.gone.discard(230)                                        # a 404 once, then it answers (a glitch)
    clock.t += scan.CONFIRM_GAP_S + 1
    b.scan_step()
    assert b.sc["leads"] == {} and b.sc["cand"] == {} and b.sc["stats"]["visible"] == 2


def test_an_account_that_stopped_posting_or_has_few_posts_is_not_tracked(tmp_path, monkeypatch):
    b, clock = scan_blue(tmp_path, monkeypatch, {7001: ids(100, 50), 7002: ids(200, 20), 7003: ids(300, 50)})
    b.social.idle[7003] = 7 * 3600
    run_pass(b, clock, [7001, 7002, 7003])
    assert set(b.sc["snap"]) == {"7001"}                              # 7002: under 30 posts; 7003: idle over 6 h
    vanish(b, 7001, 120)
    clock.t += S.SCAN_EVERY_S + 60
    b.social.idle[7001] = 7 * 3600                                    # then 7001 goes quiet: nobody to report
    run_pass(b, clock, [7001])
    assert b.sc["snap"] == {} and b.sc["cand"] == {}


def test_a_lead_from_an_account_that_went_quiet_is_not_made(tmp_path, monkeypatch):
    b, clock = scan_blue(tmp_path, monkeypatch, {7001: ids(100, 50)})
    run_pass(b, clock, [7001])
    vanish(b, 7001, 120)
    clock.t += S.SCAN_EVERY_S + 60
    run_pass(b, clock, [7001])
    b.social.idle[7001] = 7 * 3600
    clock.t += scan.CONFIRM_GAP_S + 400
    b.scan_read("7001", clock())                                      # it is read once more: quiet, snapshot dropped
    b.scan_confirm(clock())
    assert b.sc["leads"] == {}


def test_snapshots_stay_bounded(tmp_path, monkeypatch):
    b, clock = scan_blue(tmp_path, monkeypatch, {})
    monkeypatch.setattr(scan, "KEEP_ACCOUNTS", 25)
    for a in range(7001, 7061):
        b.social.pages[a] = ids(a * 1000, 80)                         # pages longer than the limit are cut
        b.social.idle[a] = a - 7000                                   # 7001 posted most recently
    run_pass(b, clock, list(range(7001, 7061)))
    assert len(b.sc["snap"]) <= 25 and "7001" in b.sc["snap"] and "7060" not in b.sc["snap"]
    assert all(len(v["ids"]) <= scan.PAGE for v in b.sc["snap"].values())
    raw = (tmp_path / "scan.dry.json").read_text()
    assert "\n" not in raw and len(raw) < 25 * 600 + 20000             # post ids only, compact


def test_candidates_older_than_a_day_are_forgotten(tmp_path, monkeypatch):
    b, clock = scan_blue(tmp_path, monkeypatch, {7001: ids(100, 50)})
    run_pass(b, clock, [7001])
    b.sc["cand"] = {"7001": {"120": [round(clock() - scan.CAND_KEEP_S - 5), 0, "scan"]}}
    scan.prune(b.sc, clock())
    assert b.sc["cand"] == {}


def test_a_pass_runs_every_three_hours_and_reads_at_most_forty_a_minute(tmp_path, monkeypatch):
    pages = {7000 + i: ids(i * 1000, 50) for i in range(1, 101)}
    b, clock = scan_blue(tmp_path, monkeypatch, pages)
    scan.observe(b.sc, [dict(post_id=1, author_id=a, created_at=S.iso(T0 - 60)) for a in pages], lambda a: True, T0)
    b.scan_step()
    assert len(b.social.reads) == S.SCAN_READS_PER_TICK and len(b.sc["todo"]) == 60
    b.scan_step()
    b.scan_step()
    assert len(b.social.reads) == 100 and b.sc["todo"] == []
    b.scan_step()
    assert len(b.social.reads) == 100                                 # the next pass is three hours on
    clock.t += S.SCAN_EVERY_S + 1
    scan.observe(b.sc, [dict(post_id=1, author_id=a, created_at=S.iso(clock() - 60)) for a in pages], lambda a: True,
                 clock())
    b.scan_step()
    assert len(b.social.reads) == 100 + S.SCAN_READS_PER_TICK
    monkeypatch.setenv("BLUE_SCAN_EVERY_S", "0")                      # off: no reads at all
    n = len(b.social.reads)
    clock.t += 10 * S.SCAN_EVERY_S
    b.scan_step()
    assert len(b.social.reads) == n


def test_the_scan_leaves_the_read_budget_alone(tmp_path, monkeypatch):
    b, clock = scan_blue(tmp_path, monkeypatch, {7001: ids(100, 50)})

    class RL:
        remaining = S.READ_RESERVE - 1
    b.social.rate_limit = RL()
    scan.observe(b.sc, [dict(post_id=1, author_id=7001, created_at=S.iso(T0 - 60))], lambda a: True, T0)
    b.scan_step()
    assert b.social.reads == [] and b.sc["todo"] == ["7001"]


def test_our_accounts_and_citizens_are_never_tracked(tmp_path, monkeypatch):
    b, clock = scan_blue(tmp_path, monkeypatch, {3000: ids(100, 50), 7001: ids(200, 50), 500: ids(300, 50)})
    b.ours = {3000}
    posts = [dict(post_id=1, author_id=a, created_at=S.iso(T0 - 60)) for a in (3000, 7001, 500)]
    scan.observe(b.sc, posts, lambda a: ev.is_team(a, b.ours), T0)
    run_pass(b, clock, [])
    assert set(b.sc["snap"]) == {"7001"}


# ---- filing from the scanner: off by default, truthful detail when on ----
def lead_for(b, clock, aid=7001, pace=6.0):
    snap = dict(t=round(clock()), ids=[1], last=round(clock() - 300), n=50, span=int(49 / pace * 3600), pace=pace)
    b.sc["snap"][str(aid)] = snap
    b.sc["cand"] = {str(aid): {"120": [round(clock()), round(clock()), "scan"]}}
    b.social.gone.add(120)
    clock.t += scan.CONFIRM_GAP_S + 1
    b.scan_confirm(clock())


def test_with_the_flag_off_a_lead_is_logged_and_listed_but_never_enters_the_filing_path(tmp_path, monkeypatch):
    b, clock = scan_blue(tmp_path, monkeypatch, {7001: ids(100, 50)})
    lead_for(b, clock)
    b.scan_promote(clock())
    assert b.s["harvest"] == {} and b.sc["leads"]["7001"]["filed"] == "off"
    st = b.scan_status()
    assert st["file"] is False and st["leads"][0]["account"] == 7001 and st["leads"][0]["vanished"] == [120]
    assert st["leads"][0]["filed"] == "off" and st["leads"][0]["posts_per_h"] == 6.0
    b.status("auto", "x", [])
    assert json.loads((tmp_path / "status.dry.json").read_text())["scan"]["leads"][0]["account"] == 7001


def test_with_the_flag_on_a_lead_joins_the_harvest_and_files_with_a_truthful_detail(tmp_path, monkeypatch):
    b, clock = scan_blue(tmp_path, monkeypatch, {7001: ids(100, 50)})
    monkeypatch.setenv("BLUE_SCAN_FILE", "1")
    lead_for(b, clock)
    b.scan_promote(clock())
    h = b.s["harvest"]["7001"]
    assert h["by"] == "scan" and h["vanished"] and h["hidden_post"] == 120 and b.sc["leads"]["7001"]["filed"] == "queued"
    h.update(ready=True, actions=100, ring_posts=[], live_at=clock(), last_post=clock() - 300)
    c, = b.candidates()
    d = c["detail"]
    assert d.startswith("I think that this account is conducting inauthentic (bot) activity because ")
    assert "its post #120 is no longer available" in d and "it has taken 100+ actions" in d
    assert "50 times in the last 8.2 hours (about 6 an hour)" in d
    assert not re.search(r"moderator|hidden|lockstep|\b(yes|side|vote|voting|referendum)\b|\bno\b(?! longer)", d, re.I)


def test_a_lead_with_nothing_measured_to_state_does_not_file(tmp_path, monkeypatch):
    b, clock = scan_blue(tmp_path, monkeypatch, {7001: ids(100, 50)})
    monkeypatch.setenv("BLUE_SCAN_FILE", "1")
    lead_for(b, clock, pace=1.2)                                       # a slow poster: no pattern to state
    b.scan_promote(clock())
    b.s["harvest"]["7001"].update(ready=True, actions=100, ring_posts=[], live_at=clock(), last_post=clock() - 300)
    assert b.candidates() == []
    b.s["harvest"]["7001"]["ring_posts"] = [4321]                      # we measured a lockstep ring it acted in
    c, = b.candidates()
    assert "lockstep" in c["detail"] and "no longer available" in c["detail"] and "moderator" not in c["detail"]


def test_the_existing_harvest_wording_still_says_the_moderator_hid_it():
    d = ev.account_detail(7, 99, 120, [1, 2])
    assert "the moderator has already hidden its post #99 as inauthentic" in d and "lockstep" in d
    v = ev.account_detail(7, 99, 120, [], vanished=True)
    assert v == ("I think that this account is conducting inauthentic (bot) activity because its post #99 is no longer "
                 "available, and it has taken 120+ actions.")


def test_turning_the_flag_on_later_queues_recent_leads_only(tmp_path, monkeypatch):
    b, clock = scan_blue(tmp_path, monkeypatch, {7001: ids(100, 50)})
    lead_for(b, clock)
    b.sc["leads"]["7002"] = dict(by="scan", account=7002, vanished=[5], found=round(clock() - S.SCAN_PROMOTE_S - 10),
                                 filed="off", pace=5.0, pace_text="x")
    monkeypatch.setenv("BLUE_SCAN_FILE", "1")
    b.scan_promote(clock())
    assert set(b.s["harvest"]) == {"7001"} and b.sc["leads"]["7002"]["filed"] == "off"
    b.s["harvest"]["7003"] = dict(hidden_post=1)                       # already a lead by another route
    b.sc["leads"]["7003"] = dict(by="scan", account=7003, vanished=[6], found=round(clock()), filed="off", pace=5.0,
                                 pace_text="x")
    b.scan_promote(clock())
    assert b.sc["leads"]["7003"]["filed"] == "known" and b.s["harvest"]["7003"] == dict(hidden_post=1)


# ---- scripts/blue_scan_eval.py: the same rule on two census snapshots ----
def _eval_module():
    import importlib.util
    import pathlib
    path = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "blue_scan_eval.py"
    spec = importlib.util.spec_from_file_location("blue_scan_eval", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _rows(accounts, t_newest):
    return {a: dict(account_id=a, err=None, posts=[dict(id=p, t=S.iso(t_newest - k * 600).replace("+00:00", "Z"))
                                                   for k, p in enumerate(plist)]) for a, plist in accounts.items()}


def test_eval_script_lists_candidates_from_two_snapshots():
    m = _eval_module()
    t1, t2 = T0, T0 + 3 * 3600
    snap1 = _rows({5001: ids(1000, 50), 5002: ids(2000, 50), 5003: ids(3000, 50), 5004: ids(4000, 20),
                   3000: ids(6000, 50)}, t1)
    gone = [p for p in ids(1000, 50) if p != 1030]                          # 5001: post 1030 vanished, nothing new
    snap2 = _rows({5001: gone + [999], 5002: ids(2000, 50), 5003: ids(3010, 50), 5004: ids(4000, 20),
                   3000: [p for p in ids(6000, 50) if p != 6010] + [5999]}, t2 - 60)
    leads, summary = m.evaluate(snap1, snap2, t2, ours={3000}, fleet_of={5001: "f5000"})
    assert [(x["account"], x["vanished"], x["fleet"]) for x in leads] == [(5001, [1030], "f5000")]
    assert summary["candidates"] == 1 and summary["live"] == 3               # 5004 has 20 posts; 3000 is ours
    # 5003 posted 10 new posts: its old page is still inside the new one and nothing vanished
    leads2, summary2 = m.evaluate(snap1, _rows({5001: ids(1000, 50)}, t2 - 60), t2 + 7 * 3600)
    assert leads2 == [] and summary2["live"] == 0                            # 7 h on and still quiet: not live


def test_scan_leads_file_by_default_since_29_oct(monkeypatch):
    monkeypatch.delenv("BLUE_SCAN_FILE", raising=False)
    assert S.policy()["scan_file"] == 1
    monkeypatch.setenv("BLUE_SCAN_FILE", "0")
    assert S.policy()["scan_file"] == 0                                   # the .env switch still turns it off
