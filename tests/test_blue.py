"""swan_blue: evidence, greedy ranking, rulings and locks. No network, no secrets."""
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import capturethenarrative as ctn  # noqa: E402

from swan_blue import evidence as ev  # noqa: E402
from swan_blue import service as S  # noqa: E402


def audit(**kw):
    a = dict(post_id=1, author=5000, created="2026-10-21T10:00:00Z", root=None, likes=45, team_likes=45, early=0.9,
             first2m=40, burst60=22, replies=18, team_replies=18, reply_authors=18, reply_span_min=33, run=12,
             liker_ids=list(range(6000, 6045)), reply_posts=[])
    a.update(kw)
    return a


def test_classes_need_ring_evidence():
    assert ev.classes(audit()) == ["reply_ring", "like_ring"]
    assert ev.classes(audit(team_replies=2, reply_authors=2)) == ["like_ring"]
    assert ev.classes(audit(team_likes=10, team_replies=0, reply_authors=0)) == []      # too few
    assert ev.classes(audit(likes=100, team_likes=40, team_replies=0, reply_authors=0)) == []   # 40% team: citizens too


def test_detail_opens_as_the_platform_requires_and_states_numbers():
    d = ev.post_detail(audit())
    assert d.startswith("I think that this content is inauthentic (bot) activity because ")
    assert "45 of its 45 likes" in d and "22 inside a single 60-second window" in d
    assert ev.account_detail(7, 99, 120, [1, 2]).startswith(
        "I think that this account is conducting inauthentic (bot) activity because")


def test_rates_and_first_reporter_value():
    assert [ev.rate(n) for n in (0, 4, 5, 9, 10)] == [1.0, 1.0, 0.5, 0.5, 0.1]
    assert ev.post_ev(10, False) > ev.post_ev(10, True) > ev.post_ev(300, True)   # fresh, off Trending: likely first


def test_labels_stick_to_a_team():
    labels = {}
    a = audit(author=5000, liker_ids=[6001, 6002, 6003])
    assert ev.label_for(a, labels) == "c5000"
    b = audit(author=5100, liker_ids=[6001, 6002, 6003, 6004])                    # same likers, other author
    assert ev.label_for(b, labels) == "c5000"
    c = audit(author=7000, liker_ids=[8001, 8002])
    assert ev.label_for(c, labels) == "c7000"


class FakeSocial:
    def __init__(self, gone=()):
        self.gone = set(gone)

    def get_post(self, pid):
        if pid in self.gone:
            raise ctn.APIError("GET", "/posts", 404, '{"error": "post not found"}')
        return {"post_id": pid}


def blue(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(S, "STATUS_FILE", tmp_path / "status.json")
    monkeypatch.setattr(S, "REPORTS_LOG", tmp_path / "reports.jsonl")
    monkeypatch.setattr(S, "APPROVALS", tmp_path / "approved.jsonl")
    return S.Blue(live=False)


def post(pid, label, author):
    a = audit(post_id=pid, author=author, created=S.iso(time.time() - 1200))
    return dict(post=dict(post_id=pid, author_id=author, created_at=a["created"]), first_seen=time.time(), audits=1,
                trending=False, audit=a, classes=ev.classes(a), label=label)


def test_greedy_spreads_over_teams(tmp_path, monkeypatch):
    b = blue(tmp_path, monkeypatch)
    for i in range(8):
        b.s["posts"][str(100 + i)] = post(100 + i, "cA", 5000 + i)
    for i in range(3):
        b.s["posts"][str(200 + i)] = post(200 + i, "cB", 7000 + i)
    first8 = [c["label"] for c in b.ranked() if c["key"] in {f"p{100 + i}" for i in range(8)} | {"p200", "p201", "p202"}][:8]
    assert first8.count("cB") == 3          # team B's full-rate reports come before team A's half-rate ones


def test_rulings_hidden_and_genuine_lock(tmp_path, monkeypatch):
    b = blue(tmp_path, monkeypatch)
    old = time.time() - S.RULE_S - S.RULE_GRACE_S - 60
    b.s["reports"] = {"p1": dict(kind="post", target=1, author=5000, label="cA", filed=old, status="pending"),
                      "p2": dict(kind="post", target=2, author=5001, label="cA", filed=old, status="pending"),
                      "p3": dict(kind="post", target=3, author=5002, label="cA", filed=time.time(), status="pending")}
    b.social = FakeSocial(gone={1})
    b.rulings()
    st = {k: r["status"] for k, r in b.s["reports"].items()}
    assert st == {"p1": "hidden", "p2": "genuine", "p3": "pending"}
    assert b.locked() and b.s["lock_until"] == old + S.RULE_S + S.LOCK_S
    assert "5000" in b.s["harvest"]          # its author now has a hidden post: an account-report lead
    assert b.precision() == dict(n=2, hidden=1, genuine=1, rate=0.5)


def test_refused_report_backs_off(tmp_path, monkeypatch):
    b = blue(tmp_path, monkeypatch)
    c = dict(key="p9", kind="post", target=9, author=5000, label="cA", detail="x")
    b.refused(c, ctn.APIError("POST", "/report", 403, '{"error": "reporting suspended"}'))
    assert b.locked()
    b.s["lock_until"] = 0
    b.refused(c, ctn.APIError("POST", "/report", 404, '{"error": "post not found"}'))
    assert not b.locked() and b.s["reports"]["p9"]["status"] == "refused"


def test_mode_gate(tmp_path, monkeypatch):
    b = blue(tmp_path, monkeypatch)
    b.live = True
    monkeypatch.setattr(S.config, "BLUE_OFF_FILE", tmp_path / "BLUE_OFF")
    assert b.mode()[0] == "auto"                                                   # auto from the start
    b.s["reports"] = {f"p{i}": dict(kind="post", status="hidden" if i < 9 else "genuine") for i in range(12)}
    assert b.mode()[0] == "auto"
    b.s["reports"] = {f"p{i}": dict(kind="post", status="hidden" if i < 6 else "genuine") for i in range(12)}
    assert b.mode()[0] == "approve"                                                # under 70% over 10+: a person
    (tmp_path / "BLUE_OFF").touch()
    assert b.mode()[0] == "off"


def test_account_leads_fill_every_slot_without_post_reports(tmp_path, monkeypatch):
    b = blue(tmp_path, monkeypatch)
    b.live = True
    filed = []
    monkeypatch.setattr(b, "file", lambda c: filed.append(c["key"]) or True)
    b.s["reports"] = {f"p{i}": dict(kind="post", status="pending", filed=time.time()) for i in range(S.CAP - 2)}
    ranked = [dict(key="p1", kind="post", ev=20), dict(key="a1", kind="account", ev=14),
              dict(key="a2", kind="account", ev=14)]
    b.fill(ranked, "auto")
    assert filed == ["a1", "a2"]             # 2 free slots, 2 account leads: the post waits


def test_approval_rows_are_one_per_ring():
    cands = [dict(key="p11", ring=10, ring_why="ring A", label="cA", ev=19.7),
             dict(key="p12", ring=10, ring_why="ring A", label="cA", ev=19.7),
             dict(key="p20", ring=20, ring_why="ring B", label="cB", ev=15.0),
             dict(key="a7", ring=None, ring_why="post #3 already hidden", label="cB", ev=14.3)]
    rows = S.rings(cands)
    assert [(r["post"], r["reports"], r["ev"]) for r in rows] == [(10, 2, 39.4), (20, 1, 15.0), (None, 1, 14.3)]


def test_dashboard_reads_an_older_status_file(tmp_path):
    import datetime as dt
    import json
    from swan_dash import build
    (tmp_path / "blue_status.json").write_text(json.dumps(dict(ts=S.iso(), mode="approve", why="x", pending=2, cap=25,
                                                                today={"filed": 2}, waiting=[], rings=[])))
    now = dt.datetime.now(dt.timezone.utc)
    b = build.blue_panel(tmp_path, now, [], now - dt.timedelta(hours=1))
    assert b["today"]["refused"] == 0 and b["queued"] == 0 and b["rows"] == [] and not b["stale"]



def test_early_ring_needs_repeat_accounts_and_says_so():
    a = audit(likes=14, team_likes=14, early=1.0, burst60=3, team_replies=0, reply_authors=0, run=2)
    assert ev.classes(a) == []                                                     # too small for a like ring
    a.update(overlap=11, prior_post=4321)
    assert ev.classes(a) == ["early_ring"]
    assert "11 of these accounts also liked or replied to its author's earlier post #4321" in ev.post_detail(a)
    a.update(likes=40)                                                             # mostly other likers: not a ring
    assert ev.classes(a) == []


def test_known_ring_author_is_audited_early_and_compared(tmp_path, monkeypatch):
    b = blue(tmp_path, monkeypatch)
    b.s["author_ring"]["5000"] = dict(post=900, members=list(range(6000, 6012)), t=time.time())
    b.note(dict(post_id=950, author_id=5000, created_at=S.iso(time.time() - 5 * 60)), "author")
    b.note(dict(post_id=951, author_id=7777, created_at=S.iso(time.time() - 5 * 60)), "latest")
    seen = []

    def fake_audit(social, post, ours):
        seen.append(post["post_id"])
        return audit(post_id=post["post_id"], author=post["author_id"], likes=14, team_likes=14, team_replies=0,
                     reply_authors=0, liker_ids=list(range(6000, 6014)))
    monkeypatch.setattr(S.ev, "audit", fake_audit)
    b.audit_some()
    assert seen == [950]                         # 5 min old: only the known author's post is due (4 min, not 10)
    p = b.s["posts"]["950"]
    assert p["audit"]["overlap"] == 12 and p["classes"] == ["early_ring"]


def test_stale_posts_leave_the_last_slots_for_fresh_ones(tmp_path, monkeypatch):
    b = blue(tmp_path, monkeypatch)
    filed = []
    monkeypatch.setattr(b, "file", lambda c: filed.append(c["key"]) or True)
    b.s["reports"] = {f"p{i}": dict(kind="post", status="pending", filed=time.time()) for i in range(S.CAP - 6)}
    ranked = [dict(key=f"s{i}", kind="post", age_min=120, ev=12) for i in range(4)]
    b.fill(ranked, "auto")
    assert filed == ["s0"]                       # 6 free: one stale fills, the last 5 wait for fresh ring posts


def test_first_reporter_share_from_the_portal():
    msgs = ["Moderation: 1 first inauthentic report", "NPC engagement: 30 views",
            "Moderation (\u00d70.5 points): 2 first inauthentic reports and 1 inauthentic report"]
    assert ev.first_later(msgs) == (3, 1)


def test_calibration_scales_first_estimates(tmp_path, monkeypatch):
    import json
    b = blue(tmp_path, monkeypatch)
    t0 = time.time() - 3600
    b.s["reports"] = {f"p{i}": dict(kind="post", status="hidden", filed=t0, pf=0.9) for i in range(10)}
    (tmp_path / "portal.json").write_text(json.dumps({"events": [
        {"ts": S.iso(t0 + 600), "message": "Moderation: 5 first inauthentic reports and 5 inauthentic reports"}]}))
    monkeypatch.setattr(S, "PORTAL_FILE", tmp_path / "portal.json")
    b.calibrate()
    assert b.s["first"] == dict(first=5, later=5) and b.s["pf_scale"] == round(0.5 / 0.9, 2)
    assert round(ev.p_first(30, False, b.s["pf_scale"]), 2) == 0.5


def test_reads_the_bots_snapshot_and_falls_back(tmp_path, monkeypatch):
    import json
    b = blue(tmp_path, monkeypatch)
    snap = tmp_path / "latest_snapshot.json"
    monkeypatch.setattr(S, "SNAPSHOT_FILE", snap)
    assert b.snapshot("latest") is None                                            # missing: fall back to the feed
    post = dict(post_id=1, author_id=5000, created_at=S.iso())
    snap.write_text(json.dumps(dict(read_at=S.iso(), posts=[post], trending=dict(read_at=S.iso(time.time() - 3600),
                                                                                   posts=[post]))))
    assert b.snapshot("latest") == [post] and b.snapshot("trending") is None       # stale Trending: fall back


def test_plain_posts_are_dropped_after_their_audits(tmp_path, monkeypatch):
    b = blue(tmp_path, monkeypatch)
    old = S.iso(time.time() - 4 * 3600)
    b.s["posts"] = {"1": dict(post=dict(created_at=old), first_seen=time.time(), classes=[]),
                    "2": dict(post=dict(created_at=old), first_seen=time.time(), classes=["like_ring"]),
                    "3": dict(post=dict(created_at=S.iso()), first_seen=time.time(), classes=[])}
    b.prune()
    assert sorted(b.s["posts"]) == ["2", "3"]
