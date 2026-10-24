"""swan_blue (24 Oct): one report per ring thread, a cap on one cluster label's pending reports and daily awards."""
import time

from swan_blue import service as S
from test_blue import audit, blue, ev, post
from test_blue_order import live_lead


def ring_post(pid, label, author, replies=3):
    p = post(pid, label, author)
    p["audit"]["reply_posts"] = [dict(author=author + 100 + i, post_id=pid * 10 + i,
                                      created=S.iso(time.time() - 600)) for i in range(replies)]
    return p


def pending(n, label, ring=None, t=None):
    t = t or time.time()
    return {f"p{label}{ring}{i}": dict(kind="post", status="pending", filed=t, label=label, author=900 + i, ring=ring)
            for i in range(n)}


def test_a_ring_thread_gives_one_report_not_its_root_and_every_reply(tmp_path, monkeypatch):
    b = blue(tmp_path, monkeypatch)
    b.s["posts"]["100"] = ring_post(100, "cA", 5000)
    keys = [c["key"] for c in b.ranked()]
    assert len(keys) == 1                                   # root + 3 replies would be 4 before
    monkeypatch.setenv("BLUE_THREAD_MAX", "0")
    assert len(b.ranked()) == 4                             # the cap is off with 0


def test_a_thread_already_reported_today_is_not_reported_again(tmp_path, monkeypatch):
    b = blue(tmp_path, monkeypatch)
    b.s["posts"]["100"] = ring_post(100, "cA", 5000)
    b.s["posts"]["200"] = ring_post(200, "cB", 7000)
    b.s["reports"] = pending(1, "cA", ring=100)
    assert {c["ring"] for c in b.ranked()} == {200}


def test_freed_slots_go_to_other_teams_and_account_reports(tmp_path, monkeypatch):
    b = blue(tmp_path, monkeypatch)
    t = time.time()
    b.s["posts"]["100"] = ring_post(100, "cA", 5000)
    b.s["harvest"] = {"7002": live_lead(t)}
    ranked = b.ranked()
    assert sorted(c["kind"] for c in ranked) == ["account", "post"]          # one post for the thread, the account too


def test_a_label_has_at_most_four_reports_pending(tmp_path, monkeypatch):
    b = blue(tmp_path, monkeypatch)
    for i in range(8):
        b.s["posts"][str(100 + i)] = post(100 + i, "cA", 5000 + i)           # 8 separate threads of one cluster
    assert len(b.ranked()) == 4
    b.s["reports"] = pending(3, "cA", ring=1)
    assert len(b.ranked()) == 1                                              # 3 pending + 1 more
    monkeypatch.setenv("BLUE_LABEL_PENDING_MAX", "0")
    assert len(b.ranked()) == 7                                              # then the 10-a-day cap: 3 + 7


def test_a_label_stops_at_ten_awards_a_day(tmp_path, monkeypatch):
    b = blue(tmp_path, monkeypatch)
    for i in range(3):
        b.s["posts"][str(100 + i)] = post(100 + i, "cA", 5000 + i)
    b.s["posts"]["200"] = post(200, "cB", 7000)
    b.s["reports"] = {k: dict(v, status="hidden", ruled_day=S.sydney_day(time.time() + S.RULE_S))
                      for k, v in pending(10, "cA", ring=1).items()}
    assert {c["label"] for c in b.ranked()} == {"cB"}
