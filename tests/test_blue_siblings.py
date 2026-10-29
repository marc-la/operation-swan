"""swan_blue (todo/43 item 5): sibling checks when one account of a live fleet has a vanished post. No network."""
import json

from swan_blue import fleets as F
from swan_blue import scan
from test_blue import S, blue
from test_blue_fleets import acc, burst
from test_blue_scan import T0, Clock, ScanSocial, ids


def sib_blue(tmp_path, monkeypatch, pages):
    clock = Clock()
    monkeypatch.setattr(S, "now", clock)
    b = blue(tmp_path, monkeypatch)
    b.social = ScanSocial(clock, pages)
    b.fl = dict(rows=F.rows(burst(5000, 12, 0) + burst(6000, 5, 3000)), built=clock())
    b.make_fleets()
    for k in ("BLUE_SCAN_EVERY_S", "BLUE_SCAN_FILE", "BLUE_SIBLINGS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("BLUE_SCAN_FILE", "0")       # these tests start from "logged only" (the live default is 1 since 29 Oct)
    return b, clock


def log(tmp_path):
    return [json.loads(x) for x in (tmp_path / "reports.jsonl").read_text().splitlines()]


def test_a_live_lead_queues_its_fleet_mates_once_det_seen_ones_first_ours_and_leads_left_out(tmp_path, monkeypatch):
    b, clock = sib_blue(tmp_path, monkeypatch, {})
    b.ours = {5002}
    b.make_fleets()
    b.s["harvest"]["5003"] = dict(hidden_post=1)                         # already a lead
    b.det["posts"]["5001"] = [[111, T0 - 4000]]                          # the bot saw 5001 post lately
    b.queue_siblings(5000, clock())
    assert b.sc["sib"][0] == "5001" and "5002" not in b.sc["sib"] and "5003" not in b.sc["sib"]
    assert "5000" not in b.sc["sib"] and set(b.sc["sib"]) <= {str(i) for i in range(5001, 5012)}
    assert len(b.sc["sib"]) == 9 and [x for x in log(tmp_path) if x["act"] == "siblings"][0]["fleet"] == "f5000"
    b.sc["sib"].clear()
    b.queue_siblings(5004, clock())                                      # same fleet again: not within six hours
    assert b.sc["sib"] == []
    clock.t += 6 * 3600 + 1
    b.queue_siblings(5004, clock())
    assert b.sc["sib"]
    b.queue_siblings(7777, clock())                                      # no fleet known: nothing
    monkeypatch.setenv("BLUE_SIBLINGS", "0")
    b.sc["sib"].clear()
    b.queue_siblings(6000, clock())
    assert b.sc["sib"] == []                                             # switched off


def test_the_queue_is_capped(tmp_path, monkeypatch):
    b, clock = sib_blue(tmp_path, monkeypatch, {})
    b.fl = dict(rows=F.rows(burst(5000, 90, 0)), built=clock())
    b.make_fleets()
    b.queue_siblings(5000, clock())
    assert len(b.sc["sib"]) == S.SIB_MAX


def test_refreshing_a_live_lead_queues_siblings_an_idle_lead_does_not(tmp_path, monkeypatch):
    from test_blue_live import LiveSocial, lead
    b, clock = sib_blue(tmp_path, monkeypatch, {})
    monkeypatch.setattr(S, "now", __import__("time").time)               # LiveSocial answers in real time
    b.social = LiveSocial({5000: 300, 6000: 9 * 3600})
    b.s["harvest"] = {"5000": lead(5000), "6000": lead(6000)}
    b.refresh_live()
    assert len(b.sc["sib"]) == 11 and all(int(a) in range(5001, 5012) for a in b.sc["sib"])   # fleet f5000; 6000 idle
    assert b.s["harvest"]["5000"]["sib"] and "sib" not in b.s["harvest"]["6000"]


def test_siblings_are_read_first_a_few_a_tick_and_a_remembered_post_gone_from_the_page_is_a_candidate(tmp_path,
                                                                                                    monkeypatch):
    pages = {5001: ids(100, 50), 5002: ids(200, 50), 5003: ids(300, 50), 7001: ids(700, 50)}
    b, clock = sib_blue(tmp_path, monkeypatch, pages)
    clock.t += 3000
    b.det["posts"]["5001"] = [[130, T0 + 100], [140, T0 + 2900], [149, T0 + 2000]]       # three posts the bot saw
    pages[5001].remove(130)
    pages[5001].append(99)                                               # 130 hidden: the page refills from below
    b.social.gone.add(130)
    b.sc["sib"] = ["5001", "5002", "5003"]
    scan.observe(b.sc, [dict(post_id=1, author_id=7001, created_at=S.iso(clock() - 60))], lambda a: True, clock())
    monkeypatch.setattr(S, "SIB_PER_TICK", 2)
    b.scan_step()
    assert b.social.reads[:2] == [5001, 5002]                            # siblings before the scan's own list
    assert b.sc["sib"] == ["5003"] and b.sc["stats"]["siblings"] == 2
    cand = b.sc["cand"]["5001"]
    assert list(cand) == ["130"] and cand["130"][2] == "sibling"         # 140 was seen <30 min ago, 149 is on the page
    assert b.social.reads.count(7001) == 1                               # the scan pass went on after them


def test_a_sibling_lead_needs_the_same_two_404s_and_is_logged_not_filed_with_the_flag_off(tmp_path, monkeypatch):
    pages = {5001: ids(100, 50)}
    b, clock = sib_blue(tmp_path, monkeypatch, pages)
    clock.t += 3000
    b.det["posts"]["5001"] = [[130, T0 + 100]]
    pages[5001].remove(130)
    pages[5001].append(99)
    b.social.gone.add(130)
    b.sc["sib"] = ["5001"]
    b.scan_step()
    assert b.sc["leads"] == {} and b.social.asked == [130]               # one 404 so far
    clock.t += scan.CONFIRM_GAP_S + 1
    b.scan_step()
    lead = b.sc["leads"]["5001"]
    assert lead["by"] == "sibling" and lead["vanished"] == [130] and lead["filed"] == "off"
    b.scan_promote(clock())
    assert b.s["harvest"] == {}                                          # BLUE_SCAN_FILE=0: logged only
    monkeypatch.setenv("BLUE_SCAN_FILE", "1")
    b.scan_promote(clock())
    h = b.s["harvest"]["5001"]
    assert h["by"] == "sibling" and h["vanished"] and h["hidden_post"] == 130


def test_sibling_reads_stay_inside_the_read_budget(tmp_path, monkeypatch):
    b, clock = sib_blue(tmp_path, monkeypatch, {5001: ids(100, 50)})
    b.sc["sib"] = ["5001"]

    class RL:
        remaining = S.READ_RESERVE - 1
    b.social.rate_limit = RL()
    assert b.sibling_step(clock()) == 0 and b.sc["sib"] == ["5001"]
