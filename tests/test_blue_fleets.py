"""swan_blue (todo/43 item 4): fleets as the team proxy, and awards counted per fleet. No network, no secrets."""
import json
import time

import capturethenarrative as ctn

from swan_blue import fleets as F
from test_blue import S, blue, ev, post


def acc(i, t=None, **kw):
    """A platform account dict; t = seconds after 2026-10-21T00:00:00Z (None = private: no created_at)."""
    created = None if t is None else S.iso(1792540800 + t).replace("+00:00", "Z")
    return dict(account_id=i, created_at=created, **kw)


def burst(first, n, t0, step=2):
    return [acc(first + k, t0 + k * step) for k in range(n)]


def test_a_registration_burst_is_one_fleet_and_a_pause_or_an_id_jump_starts_another():
    a = burst(5000, 10, 0) + burst(5010, 5, 400) + [acc(5100, 410)]      # a pause of 340 s; then a jump of 85 ids
    f = F.fleets(a)
    assert {f[i] for i in range(5000, 5010)} == {"f5000"}                # key = the lowest id
    assert {f[i] for i in range(5010, 5015)} == {"f5010"}
    assert f[5100] == "f5100"
    assert len(set(f.values())) == 3


def test_neighbours_a_few_ids_apart_still_link_when_another_team_sits_between():
    a = [acc(5000, 0), acc(5003, 10), acc(5008, 20)]                     # gaps of 3 and 5 ids, 10 s each
    assert len(set(F.fleets(a).values())) == 1
    assert len(set(F.fleets(a, id_gap=2).values())) == 3
    assert len(set(F.fleets([acc(5000, 0), acc(5006, 10)]).values())) == 2   # 6 ids apart: over FLEET_ID_GAP


def test_time_gap_is_the_cut():
    a = [acc(5000, 0), acc(5001, F.FLEET_GAP_S), acc(5002, 2 * F.FLEET_GAP_S + 1)]
    f = F.fleets(a)
    assert f[5000] == f[5001] != f[5002]


def test_private_accounts_have_no_time_and_ride_with_their_neighbours():
    a = [acc(5000, 0), acc(5001), acc(5002, 12), acc(5003), acc(5004, 400)]      # 5001 and 5003 are private
    f = F.fleets(a)
    assert f[5000] == f[5001] == f[5002] == f[5003] != f[5004]
    assert F.fleets([acc(5000, 0), acc(5004)])[5004] == "f5000"          # up to FLEET_ID_GAP ids on


def test_citizens_organisers_verified_and_ours_are_left_out():
    a = [acc(5, 0, verified=True), acc(100, 1), acc(2343, 2), acc(5000, 3), acc(5001, 5, verified=True),
         acc(5002, 7), acc(5003, 9)]
    f = F.fleets(a, skip={5002})
    assert set(f) == {5000, 5003}                                         # 5002 (ours) is skipped: 5000 and 5003 link
    assert f[5000] == f[5003]


def test_a_chain_longer_than_a_teams_allowance_is_cut_at_its_biggest_gap():
    a = burst(5000, 150, 0) + burst(5150, 100, 150 * 2 + 25)              # a 25 s pause inside one long chain of 250
    f = F.fleets(a)
    assert len(a) > F.FLEET_MAX and max(len(v) for v in F.members(f).values()) <= F.FLEET_MAX
    assert f[5149] != f[5150] and f[5000] == f[5149]
    big = F.fleets(burst(5000, 450, 0))                                   # no gap at all: still cut, every piece <= 200
    assert max(len(v) for v in F.members(big).values()) <= F.FLEET_MAX


def test_a_late_registration_joins_the_top_and_leaves_the_key_alone():
    a = burst(5000, 6, 0)
    before = F.fleets(a)
    after = F.fleets(a + [acc(5006, 12)])
    assert after[5006] == before[5000] == after[5000]


# ---- the service: the cache, the team key, awards counted per fleet ----
class AccountsSocial:
    """client.accounts(): 100 a page, cursor 'n' = index of the next page."""

    def __init__(self, accounts, fail_on=None):
        self.accounts_, self.fail_on, self.pages = accounts, fail_on, 0
        self.rate_limit = None

    def accounts(self, limit=50, cursor=None, **kw):
        if self.fail_on is not None and self.pages == self.fail_on:
            self.fail_on = None
            raise ctn.APIError("GET", "/accounts", 500, "{}")
        self.pages += 1
        i = int(cursor or 0)
        nxt = i + limit if i + limit < len(self.accounts_) else None
        return ctn.Page(self.accounts_[i:i + limit], str(nxt) if nxt is not None else None)


def fleet_blue(tmp_path, monkeypatch, accounts=None, **kw):
    b = blue(tmp_path, monkeypatch)
    b.fl = dict(rows=F.rows(accounts or []), built=time.time())
    b.make_fleets()
    for k, v in kw.items():
        setattr(b, k, v)
    return b


def test_team_key_is_the_fleet_then_the_cluster_label(tmp_path, monkeypatch):
    b = fleet_blue(tmp_path, monkeypatch, burst(5000, 6, 0) + [acc(5100, 5000)])   # a fleet of 6 and a singleton
    b.s["labels"].update({"5001": "c8701", "5100": "cX", "9999": "c8701"})
    assert b.team_key(5001, "c8701") == "f5000"                           # in a fleet: the fleet, whatever the cluster
    assert b.team_key(5100) == "cX"                                       # alone, with a cluster label: the label
    assert b.team_key(5200) == "c5200"                                    # unknown account, no label
    assert b.team_key(9999, "c8701") == "c8701"                           # no account list entry: the label
    monkeypatch.setenv("BLUE_FLEET_EVERY_S", "0")
    assert b.team_key(5001, "c8701") == "c8701"                           # fleets off: Blue's clusters, as before
    monkeypatch.delenv("BLUE_FLEET_EVERY_S")
    b.ours = {5003}
    b.make_fleets()
    assert 5003 not in b.fleet_map


def test_one_big_cluster_no_longer_says_saturated_when_it_holds_several_teams(tmp_path, monkeypatch):
    accounts = burst(5000, 20, 0) + burst(6000, 20, 5000) + burst(7000, 20, 9000)    # three fleets
    b = fleet_blue(tmp_path, monkeypatch, accounts)
    t = time.time()
    b.s["labels"].update({str(a["account_id"]): "c8701" for a in accounts})            # Blue calls them one cluster
    b.s["reports"] = {f"p{i}": dict(kind="post", status="pending", filed=t, label="c8701", author=5000 + i)
                      for i in range(12)}                                              # 12 awards, all on fleet f5000
    counts = b.counts_today()
    assert counts == {"f5000": 12}
    p1, p2 = post(100, "c8701", 6001), post(200, "c8701", 5019)
    b.s["posts"].update({"100": p1, "200": p2})
    by = {c["key"]: c for c in b.ranked()}
    assert by["p100"]["n_today"] == 0 and by["p200"]["n_today"] == 12      # fleet f6000 is fresh, f5000 is at 12
    assert by["p100"]["ev"] > by["p200"]["ev"] and by["p100"]["team"] == "f6000"
    b2 = fleet_blue(tmp_path, monkeypatch)                                 # no account list: the cluster counts, as before
    b2.s["labels"].update({str(a["account_id"]): "c8701" for a in accounts})
    b2.s["reports"] = b.s["reports"]
    assert b2.counts_today() == {"c8701": 12}


def test_awards_pay_full_then_half_then_a_tenth_per_fleet(tmp_path, monkeypatch):
    b = fleet_blue(tmp_path, monkeypatch, burst(5000, 30, 0) + burst(6000, 30, 5000))
    t = time.time()
    b.s["reports"] = {f"p{i}": dict(kind="post", status="pending", filed=t, label="cA", author=5000 + i)
                      for i in range(11)}
    b.s["reports"].update({"a5020": dict(kind="account", status="pending", filed=t, label="cA", author=5020),
                           "p0": dict(kind="post", status="pending", filed=t, label="cA", author=5000)})
    # 12 awards on f5000 (the account counts together with the posts); none on f6000
    assert b.counts_today() == {"f5000": 12}
    rates = [ev.rate(n) for n in (0, 4, 5, 9, 10, 11)]
    assert rates == [1.0, 1.0, 0.5, 0.5, 0.1, 0.1]
    live = dict(ready=True, actions=100, ring_posts=[1], live_at=t, last_post=t - 60)
    b.s["harvest"] = {"5025": dict(hidden_post=1, **live), "6001": dict(hidden_post=2, **live)}
    ranked = {c["key"]: c for c in b.ranked()}
    assert "a5025" not in ranked                                           # 11+ awards: 10% of 13.5 is under MIN_EV
    assert ranked["a6001"]["ev"] == 13.5 and ranked["a6001"]["n_today"] == 0   # move to another team


def test_fleet_pass_reads_pages_over_ticks_writes_a_compact_cache_and_backs_off(tmp_path, monkeypatch):
    accounts = [acc(i, 0) for i in range(1, 12)] + burst(2344, 30, 0) + burst(2400, 400, 100)
    b = blue(tmp_path, monkeypatch)
    b.social = AccountsSocial(accounts, fail_on=2)
    monkeypatch.setattr(S, "FLEET_PAGES_PER_TICK", 2)
    for _ in range(3):
        b.refresh_fleets()
    assert b.social.pages == 2 and "pass" in b.fl and not b.fleet_map      # a page failed: backs off, no hammering
    b.fl["pass"]["err"] = time.time() - S.FLEET_ERR_S - 1
    for _ in range(4):
        b.refresh_fleets()
    assert "pass" not in b.fl and b.fl["built"] > 0 and len(b.fleet_map) > 400
    assert max(len(v) for v in F.members(b.fleet_map).values()) <= F.FLEET_MAX
    raw = (tmp_path / "fleets.dry.json").read_text() if (tmp_path / "fleets.dry.json").exists() else \
        (tmp_path / "fleets.json").with_suffix(".dry.json").read_text()
    assert "\n" not in raw and json.loads(raw)["built"] == b.fl["built"]
    pages = b.social.pages
    b.refresh_fleets()
    assert b.social.pages == pages                                        # built: not again before BLUE_FLEET_EVERY_S
    b.fl["built"] = time.time() - S.FLEET_EVERY_S - 1
    b.refresh_fleets()
    assert "pass" in b.fl and b.fleet_status()["reading"]


def test_fleets_off_reads_nothing(tmp_path, monkeypatch):
    b = blue(tmp_path, monkeypatch)
    b.social = AccountsSocial(burst(2400, 10, 0))
    monkeypatch.setenv("BLUE_FLEET_EVERY_S", "0")
    b.refresh_fleets()
    assert b.social.pages == 0 and not b.fleet_status()["on"]
