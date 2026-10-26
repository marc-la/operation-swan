"""swan_blue (todo/43 item 3): slot value ordering per target team. No network, no secrets."""
import time

from swan_blue import fleets as F
from test_blue import S, blue, ev, post
from test_blue_fleets import acc, burst


def live_lead(t, **kw):
    h = dict(hidden_post=1, ready=True, actions=100, ring_posts=[1], live_at=t, last_post=t - 60)
    h.update(kw)
    return h


def two_teams(tmp_path, monkeypatch):
    """Fleets f5000 (team A) and f6000 (team B), and a fleet f7000 (team C), counted per fleet."""
    monkeypatch.setenv("BLUE_TEAM_BY", "fleet")           # the default counts per cluster label
    b = blue(tmp_path, monkeypatch)
    b.fl = dict(rows=F.rows(burst(5000, 30, 0) + burst(6000, 30, 5000) + burst(7000, 30, 9000)), built=time.time())
    b.make_fleets()
    return b, time.time()


def award(n, author, t, kind="post"):
    return {f"{kind[0]}{author}x{i}": dict(kind=kind, status="pending", filed=t, label="cX", author=author)
            for i in range(n)}


def test_a_fresh_ring_post_goes_before_a_live_account_report_of_the_same_team(tmp_path, monkeypatch):
    b, t = two_teams(tmp_path, monkeypatch)
    b.s["posts"]["100"] = post(100, "cA", 5001)
    b.s["harvest"] = {"5002": live_lead(t)}
    ranked = {c["key"]: c for c in b.ranked()}
    assert ranked["p100"]["team"] == ranked["a5002"]["team"] == "f5000"
    assert ranked["p100"]["ev"] > 20 > ranked["a5002"]["ev"] == 13.5
    assert [c["key"] for c in b.ranked()] == ["p100", "a5002"]
    # the post pays for its lock (ev >= pg x LOCK_COST), the account has no lock to pay for: both can file
    accounts, posts = b.fileable(b.ranked())
    assert [c["key"] for c in accounts] == ["a5002"] and [c["key"] for c in posts] == ["p100"]


def test_after_five_full_awards_a_post_no_longer_pays_for_its_lock_the_account_still_files(tmp_path, monkeypatch):
    b, t = two_teams(tmp_path, monkeypatch)
    b.s["reports"] = award(5, 5001, t)
    b.s["posts"]["100"] = post(100, "cA", 5003)
    b.s["harvest"] = {"5002": live_lead(t)}
    ranked = b.ranked()
    assert {c["key"]: c["n_today"] for c in ranked} == {"p100": 5, "a5002": 6}      # the count moves up after each pick
    accounts, posts = b.fileable(ranked)
    assert [c["key"] for c in accounts] == ["a5002"] and posts == []        # 6th-10th award: half rate (6.75 for the account)
    assert accounts[0]["ev"] == 6.8


def test_from_the_sixth_award_another_team_comes_first_and_past_ten_the_team_drops_out(tmp_path, monkeypatch):
    b, t = two_teams(tmp_path, monkeypatch)
    b.s["reports"] = award(5, 5001, t)                                      # team A: 5 awards, team B: none
    b.s["harvest"] = {"5002": live_lead(t), "6002": live_lead(t), "7002": live_lead(t)}
    assert {c["key"] for c in b.ranked()[:2]} == {"a6002", "a7002"}         # B and C at 13.5 before A at 6.75
    assert b.ranked()[-1]["key"] == "a5002"
    b.s["reports"] = award(10, 5001, t)                                     # 11th award would pay 10%
    assert "a5002" not in {c["key"] for c in b.ranked()}


def test_full_awards_are_spent_one_team_after_another_not_all_on_one(tmp_path, monkeypatch):
    b, t = two_teams(tmp_path, monkeypatch)
    b.s["harvest"] = {str(5000 + i): live_lead(t) for i in range(1, 9)}
    b.s["harvest"].update({str(6000 + i): live_lead(t) for i in range(1, 9)})
    order = [c["team"] for c in b.ranked()]
    assert order[:4] == ["f5000", "f6000", "f5000", "f6000"]               # SPREAD alternates the teams while both are full
    assert [c["n_today"] for c in b.ranked()][:6] == [0, 0, 1, 1, 2, 2]


def test_an_account_other_teams_are_reporting_ranks_ahead_at_equal_value(tmp_path, monkeypatch):
    b, t = two_teams(tmp_path, monkeypatch)
    b.s["harvest"] = {"5002": live_lead(t),                                 # plain lead, team A
                      "6002": live_lead(t, by="other", found=t - 600),       # another team's hide found 10 min ago
                      "7002": live_lead(t, co=True)}                         # our report on its ring was ruled in <2 h
    ranked = b.ranked()
    assert [c["key"] for c in ranked][-1] == "a5002"
    assert {c["key"]: c["co"] for c in ranked} == {"a5002": False, "a6002": True, "a7002": True}
    assert {c["ev"] for c in ranked} == {13.5}                              # the points are the same ...
    assert abs(ranked[0]["rank"] - 13.5 * ev.ACCOUNT_CO_BOOST) < 1e-9       # ... the rank weight is not
    b.s["harvest"]["6002"]["found"] = t - S.CO_RECENT_S - 10                # found too long ago: it is not "minutes ago"
    assert {c["key"]: c["co"] for c in b.ranked()}["a6002"] is False


def test_a_co_reported_account_does_not_jump_a_fresh_post_or_a_team_past_its_full_awards(tmp_path, monkeypatch):
    b, t = two_teams(tmp_path, monkeypatch)
    b.s["posts"]["100"] = post(100, "cA", 5003)
    b.s["harvest"] = {"6002": live_lead(t, co=True), "7002": live_lead(t)}
    assert [c["key"] for c in b.ranked()] == ["p100", "a6002", "a7002"]     # 21 > 13.5 x 1.3 = 17.6 > 13.5
    b.s["reports"] = award(5, 6001, t)                                      # team B at half rate: 6.75 x 1.3 < 13.5
    assert [c["key"] for c in b.ranked()] == ["p100", "a7002", "a6002"]


def test_the_ledger_reports_co_signals_set_where_leads_are_found(tmp_path, monkeypatch):
    from test_blue import FakeSocial
    b, t = two_teams(tmp_path, monkeypatch)
    ring = post(300, "cA", 5300)
    ring["post"]["created_at"] = ring["audit"]["created"] = S.iso(t - 2 * 3600)
    ring["audit"]["reply_posts"] = [dict(post_id=301, author=5301, created=S.iso(t - 2 * 3600))]
    b.s["posts"]["300"] = ring
    class Social(FakeSocial):
        account_posts = account_likes = None

        def iterate(self, fn, *a, max_items=100):
            return iter([{}] * max_items)
    b.social = Social(gone={301})
    b.harvest()
    assert b.s["harvest"]["5301"]["by"] == "other" and abs(b.s["harvest"]["5301"]["found"] - t) < 5
    b.s["reports"] = {"p401": dict(kind="post", target=401, author=5401, label="cA", filed=t - 1.4 * 3600,
                                   status="pending", ring=300, classes=["reply_ring"], pg=0.08)}
    b.social = Social(gone={401})
    b.rulings()
    assert b.s["harvest"]["5401"]["co"] and abs(b.s["harvest"]["5401"]["found"] - t) < 5
