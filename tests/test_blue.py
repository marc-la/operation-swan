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
    monkeypatch.setattr(S, "DETECT_FILE", tmp_path / "detect.json")
    monkeypatch.setattr(S, "CAP_PROBE_FILE", tmp_path / "cap_probe.json")
    monkeypatch.setattr(S.config, "ACCOUNTS_FILE", tmp_path / "no_accounts.json")      # the box has real ones
    monkeypatch.setattr(S.config, "SWARM_ACCOUNTS_FILE", tmp_path / "no_swarm.json")
    b = S.Blue(live=False)
    monkeypatch.setattr(b, "alert", lambda *a, **k: None)    # tests that set live=True must never page anyone
    return b


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
    ranked = [dict(key=f"s{i}", kind="post", age_min=120, ev=12, pg=0.02) for i in range(4)]
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


def test_days_count_the_levers_and_split_locks_at_sydney_midnight(tmp_path, monkeypatch):
    import datetime as dt
    b = blue(tmp_path, monkeypatch)
    mid = dt.datetime(2026, 10, 23, tzinfo=S.SYDNEY).timestamp()             # midnight Sydney, 23 Oct
    monkeypatch.setattr(S, "now", lambda: mid + 10 * 3600)
    b.s["reports"] = {"p1": dict(kind="post", status="hidden", filed=mid - 5 * 3600, ruled_day="2026-10-22"),
                      "p2": dict(kind="post", status="genuine", filed=mid - 4 * 3600, ruled_day="2026-10-22"),
                      "p3": dict(kind="post", status="refused", filed=mid - 4 * 3600)}
    b.s["locks"] = [[mid - 2 * 3600, mid + 4 * 3600], [mid - 1 * 3600, mid + 1 * 3600]]   # overlapping: one lock
    d = b.days()
    assert d["2026-10-22"] == dict(filed=2, hidden=1, genuine=1, accounts=0, locked_h=2.0)
    assert d["2026-10-23"]["locked_h"] == 4.0


def test_dashboard_verdict_names_the_weakest_lever():
    import datetime as dt
    from swan_dash import build
    now = dt.datetime(2026, 10, 23, 12, tzinfo=S.SYDNEY)
    days = {"2026-10-22": dict(filed=68, hidden=40, genuine=20, accounts=0, locked_h=9.0),
            "2026-10-23": dict(filed=20, hidden=5, genuine=0, accounts=0, locked_h=0.0)}
    points = [dict(_t=dt.datetime(2026, 10, 22, 20, tzinfo=S.SYDNEY), points=640, type="SCORE_NARRATIVE",
                   message="Moderation: 20 first inauthentic reports and 28 inauthentic reports")]
    rows = build.blue_days(days, points, now.astimezone(dt.timezone.utc))
    assert [r["today"] for r in rows] == [True, False]
    y = rows[1]
    assert y["pct"] == 53 and y["level"] == "down"
    assert y["day"] == "Wed 21 9pm → Thu 22 9pm"                                   # a competition day, in Perth hours
    assert y["lever"] == "moderator: only 67% of rulings hidden (about 90% expected)"   # filed 68 is fine, hit isn't


# ---- todo/26: lock economics, more teams, wider discovery ----
def test_p_genuine_by_evidence_class():
    like = audit(team_replies=0, reply_authors=0, run=3)
    assert ev.p_genuine(like, ["like_ring"]) == ev.PG_BASE
    assert ev.p_genuine(audit(), ["reply_ring", "like_ring"]) < ev.p_genuine(like, ["like_ring", "early_ring"]) \
        < ev.p_genuine(like, ["like_ring"])
    assert ev.p_genuine(like, ["like_ring"], author_hidden=True) == ev.PG_BASE     # 1 of 8: no safer (22 Oct)
    weak = audit(team_likes=22, likes=22, burst60=3, team_replies=0, reply_authors=0, run=3)   # #155963, 21 Oct
    assert ev.p_genuine(weak, ["like_ring"]) > ev.PG_BASE
    assert ev.post_ev(10, False, pg=0.04) > ev.post_ev(10, False, pg=0.14)


def test_no_lock_mode_files_accounts_then_only_the_lowest_risk_posts(tmp_path, monkeypatch):
    b = blue(tmp_path, monkeypatch)
    b.live = True
    filed = []
    monkeypatch.setattr(b, "file", lambda c: filed.append(c["key"]) or True)
    monkeypatch.delenv("BLUE_POST_PG_MAX", raising=False)
    monkeypatch.delenv("BLUE_PG_PER_DAY", raising=False)
    like = [dict(key=f"l{i}", kind="post", ev=20, pg=0.1, age_min=10) for i in range(3)]       # like ring alone
    reply = [dict(key=f"r{i}", kind="post", ev=18, pg=0.02, age_min=10) for i in range(8)]     # reply ring
    cheap = [dict(key="c0", kind="post", ev=2.3, pg=0.02, age_min=10)]                          # a 10%-rate report
    b.fill(like + reply + cheap + [dict(key="a1", kind="account", ev=14, pg=0.0)], "auto")
    assert filed == ["a1", "r0", "r1", "r2", "r3", "r4"]      # the bucket holds 0.1: five 2% reports, then accounts
    assert b.bucket()["level"] < 0.02
    filed.clear()
    monkeypatch.setattr(S, "now", lambda: time.time() + 6 * 3600)          # a quarter of a day later: full again
    b.fill(reply[5:] + [dict(key="a2", kind="account", ev=14, pg=0.0)], "auto")
    assert filed == ["a2", "r5", "r6", "r7"]
    monkeypatch.setenv("BLUE_POST_PG_MAX", "0.1")                           # a setting in .env on the box
    mid = [dict(key="m0", kind="post", ev=20, pg=0.05, age_min=10)]
    filed.clear()
    b.fill(mid, "auto")
    assert filed == []                                     # allowed now, but 0.04 left in the bucket: it waits
    monkeypatch.setattr(S, "now", lambda: time.time() + 12 * 3600)
    b.fill(like + mid, "auto")
    assert filed == ["m0"]                                 # a 10% report risks more than its 20 points are worth


def test_ranking_puts_new_clusters_first_at_equal_value(tmp_path, monkeypatch):
    b = blue(tmp_path, monkeypatch)
    t = time.time()
    b.s["reports"] = {f"p{i}": dict(kind="post", status="pending", filed=t, label="cA") for i in range(3)}
    b.s["posts"]["100"] = post(100, "cA", 5000)
    b.s["posts"]["200"] = post(200, "cB", 7000)
    assert [c["label"] for c in b.ranked()][:2] == ["cB", "cA"]       # same evidence, cA already has 3 today


def test_platform_lock_message_sets_the_exact_end(tmp_path, monkeypatch):
    b = blue(tmp_path, monkeypatch)
    until = time.time() + 2 * 3600
    b.s["locks"] = [[time.time() - 3600, time.time() + 5 * 3600]]          # our estimate ran too long
    c = dict(key="p9", kind="post", target=9, author=5000, label="cA", detail="x")
    b.refused(c, ctn.APIError("POST", "/report", 403, '{"error": "reporting is suspended for your team until '
                              + S.iso(until).replace("+00:00", "Z") + '"}'))
    assert b.locked() and abs(b.s["lock_until"] - until) < 1 and b.s["lock_src"] == "server"
    assert max(e for _, e in b.s["locks"]) <= until + 1                     # locked hours end where the platform says


def test_genuine_we_detect_is_confirmed_by_one_report(tmp_path, monkeypatch):
    b = blue(tmp_path, monkeypatch)
    b.live = True
    old = time.time() - S.RULE_S - S.RULE_GRACE_S - 60
    b.s["reports"] = {"p2": dict(kind="post", target=2, author=5001, label="cA", filed=old, status="pending")}
    b.social = FakeSocial()
    b.rulings()
    assert b.locked() and b.s["lock_src"] == "estimate" and b.s["lock_confirm"]
    tries = []
    real = time.time() + 3600                                              # ruled sooner: the lock ends sooner

    def refuse(c):
        tries.append(c["key"])
        return b.refused(c, ctn.APIError("POST", "/report", 403, '{"error": "reporting is suspended for your team '
                                         'until ' + S.iso(real).replace("+00:00", "Z") + '"}'))
    monkeypatch.setattr(b, "file", refuse)
    ranked = [dict(key="a1", kind="account", ev=14, pg=0.0), dict(key="p5", kind="post", ev=20, pg=0.04)]
    b.fill(ranked, "auto")
    b.fill(ranked, "auto")
    assert tries == ["a1"]                                                 # one try, then it waits
    assert abs(b.s["lock_until"] - real) < 1 and b.s["lock_why"] == "#2 ruled genuine"


def test_genuine_after_the_platform_named_its_lock_does_not_extend_it(tmp_path, monkeypatch):
    b = blue(tmp_path, monkeypatch)
    old = time.time() - S.RULE_S - S.RULE_GRACE_S - 60
    until = time.time() + 3600
    b.s.update(lock_until=until, lock_src="server", server_lock=dict(at=time.time() - 60, until=until))
    b.s["reports"] = {"p2": dict(kind="post", target=2, author=5001, label="cA", filed=old, status="pending")}
    b.social = FakeSocial()
    b.rulings()
    assert b.s["reports"]["p2"]["status"] == "genuine" and b.s["lock_until"] == until


class WidenSocial(FakeSocial):
    def __init__(self, posts):
        super().__init__()
        self.posts, self.asked = posts, []

    def get_post(self, pid):
        self.asked.append(pid)
        return self.posts[pid]


def test_widen_from_the_snapshot_reaudits_and_looks_up_roots(tmp_path, monkeypatch):
    b = blue(tmp_path, monkeypatch)
    t = S.iso(time.time() - 2 * 3600)
    plain = post(100, "cA", 5000)
    plain.update(classes=[], audits=2)
    b.s["posts"]["100"] = plain
    b.social = WidenSocial({300: dict(post_id=300, author_id=8000, created_at=t, reply_to_post_id=None),
                            400: dict(post_id=400, author_id=500, created_at=t, reply_to_post_id=None)})
    snap = [dict(post_id=1000 + 10 * root + i, author_id=6000 + i, root_post_id=root, reply_to_post_id=root,
                 created_at=S.iso()) for root in (100, 300, 400) for i in range(5)]
    snap += [dict(post_id=2000, author_id=6100, root_post_id=500, reply_to_post_id=500, created_at=S.iso())]
    b.widen(snap)
    assert plain["reaudit"] is True                                        # known, no ring yet: one more audit
    assert sorted(b.social.asked) == [300, 400]                            # 500 has one reply: not looked up
    assert "300" in b.s["posts"] and "400" not in b.s["posts"]             # 400 is a citizen's post
    b.widen(snap)
    assert sorted(b.social.asked) == [300, 400]                            # looked up once
    seen = []
    monkeypatch.setattr(S.ev, "audit", lambda social, p, ours: seen.append(p["post_id"]) or audit(
        post_id=p["post_id"], author=p["author_id"], liker_ids=list(range(6000, 6045))))
    b.audit_some()
    assert 100 in seen and b.s["posts"]["100"]["classes"] and b.s["widen"]["rings"] >= 1


def test_leads_include_ring_replies_other_teams_got_hidden(tmp_path, monkeypatch):
    b = blue(tmp_path, monkeypatch)
    ring = post(100, "cA", 5000)
    ring["post"]["created_at"] = ring["audit"]["created"] = S.iso(time.time() - 2 * 3600)
    ring["audit"]["reply_posts"] = [dict(post_id=101, author=6001, created=S.iso(time.time() - 2 * 3600)),
                                    dict(post_id=102, author=6002, created=S.iso(time.time() - 2 * 3600))]
    b.s["posts"]["100"] = ring
    assert {p for p, _, _ in b.hide_targets()} == {100, 101, 102}

    class Social(FakeSocial):
        account_posts = account_likes = None

        def iterate(self, fn, *a, max_items=100):
            return iter([{}] * max_items)
    b.social = Social(gone={102})
    b.harvest()
    assert b.s["harvest"]["6002"]["hidden_post"] == 102 and b.s["harvest"]["6002"]["ready"]
    assert "5000" not in b.s["harvest"] and b.hide_targets() == []         # checked: not again for 2 h


def test_our_swarm_accounts_count_as_ours(tmp_path, monkeypatch):
    import json
    b = blue(tmp_path, monkeypatch)
    (tmp_path / "acc.json").write_text(json.dumps([dict(account_id=3000, username="v", role="voice")]))
    (tmp_path / "swarm.json").write_text(json.dumps([dict(account_id=9100, username="s")]))
    monkeypatch.setattr(S.config, "ACCOUNTS_FILE", tmp_path / "acc.json")
    monkeypatch.setattr(S.config, "SWARM_ACCOUNTS_FILE", tmp_path / "swarm.json")
    b.load_ours()
    assert b.ours == {3000, 9100} and not ev.is_team(9100, b.ours) and ev.is_team(9101, b.ours)
    monkeypatch.setattr(S.config, "EXTRA_CITIZEN_RANGES", [(9200, 9300)])
    assert not ev.is_team(9250, b.ours)                                    # a citizen added mid-game


def test_portal_awards_split_by_rate():
    msgs = ["NPC engagement and moderation: 53 views, 4 first inauthentic reports and 1 upheld account report",
            "Moderation (×0.5 points): 1 first inauthentic report and 3 upheld account reports",
            "Moderation (×0.1 points): 1 inauthentic report"]
    assert ev.awards_by_rate(msgs) == (5, 5)


def test_dashboard_says_locked_until_perth_why_and_ready(tmp_path):
    import datetime as dt
    import json
    from swan_dash import build
    until = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)
    (tmp_path / "blue_status.json").write_text(json.dumps(dict(
        ts=S.iso(), mode="auto", why="x", pending=0, cap=25, today={}, locked_until=until.isoformat(),
        lock_why="#155963 ruled genuine", lock_src="server", ready=43, ready_ok=30, ready_accounts=2)))
    now = dt.datetime.now(dt.timezone.utc)
    b = build.blue_panel(tmp_path, now, [], now - dt.timedelta(hours=1))
    assert f"locked until {build.hm(until)} Perth (#155963 ruled genuine)" in b["summary"]
    assert "30 ready" in b["summary"] and b["ready"] == 30 and not b["lock_estimate"]


# ---- todo/28: Blue without locks ----
def test_cap_30_leaves_the_last_slot_to_an_account_report(tmp_path, monkeypatch):
    b = blue(tmp_path, monkeypatch)
    b.live = True
    filed = []
    monkeypatch.setattr(b, "file", lambda c: filed.append(c["key"]) or b.s["reports"].setdefault(
        c["key"], dict(kind=c["kind"], status="pending", filed=time.time())))
    assert S.CAP == 30
    b.s["reports"] = {f"p{i}": dict(kind="post", status="pending", filed=time.time()) for i in range(S.CAP - 2)}
    ranked = [dict(key=f"s{i}", kind="post", ev=20, pg=0.02, age_min=10) for i in range(3)]
    b.fill(ranked, "auto")
    assert filed == ["s0"]                       # 28 posts pending: one more post, the 30th slot waits
    b.fill(ranked[1:] + [dict(key="a1", kind="account", ev=14, pg=0.0)], "auto")
    assert filed == ["s0", "a1"]                 # ...for an account report


class Reporter:
    rate_limit = None

    def __init__(self):
        self.filed = []

    def report_post(self, pid, reason, detail):
        self.filed.append(("post", pid))
        return {}

    def report_account(self, aid, reason, detail):
        self.filed.append(("account", aid))
        return {}


def test_never_files_against_our_own_accounts(tmp_path, monkeypatch):
    import json
    b = blue(tmp_path, monkeypatch)
    (tmp_path / "acc.json").write_text(json.dumps([dict(account_id=3000, username="v", role="voice")]))
    (tmp_path / "swarm.json").write_text(json.dumps([dict(account_id=9100, username="s")]))
    monkeypatch.setattr(S.config, "ACCOUNTS_FILE", tmp_path / "acc.json")
    monkeypatch.setattr(S.config, "SWARM_ACCOUNTS_FILE", tmp_path / "swarm.json")
    alerts = []
    monkeypatch.setattr(b, "alert", lambda kind, msg, gap_s=0: alerts.append(kind))
    b.reporter = Reporter()

    class Social(FakeSocial):
        def get_post(self, pid):
            return {"post_id": pid, "author_id": {1: 9100, 2: 7000}[pid]}
    b.social = Social()

    def c(key, kind, target, author):
        return dict(key=key, kind=kind, target=target, author=author, label="cA", detail="x", classes=["reply_ring"],
                    ev=20, pg=0.02, base=(10, False, 1))
    assert not b.file(c("a3000", "account", 3000, 3000))                    # one of our voices
    assert not b.file(c("p1", "post", 1, 7000))       # the candidate says 7000; the platform says our swarm wrote it
    (tmp_path / "acc.json").write_text(json.dumps([dict(account_id=3000), dict(account_id=3001)]))
    assert not b.file(c("a3001", "account", 3001, 3001))                    # a voice added since: read fresh
    assert b.reporter.filed == [] and alerts == ["own:a3000", "own:p1", "own:a3001"]
    assert b.s["reports"]["p1"]["status"] == "refused"
    log = [json.loads(x) for x in (tmp_path / "reports.jsonl").read_text().splitlines()]
    assert [x["key"] for x in log if x.get("refused") == "own account"] == ["a3000", "p1", "a3001"]
    assert b.file(c("p2", "post", 2, 7000)) and b.reporter.filed == [("post", 2)]   # another team's: files
    b.status("auto", "x", [])
    st = json.loads((tmp_path / "status.dry.json").read_text())
    assert st["own_ids"] == [3000, 3001, 9100]                              # ids only, for the dashboard


def test_no_post_report_where_our_boosters_acted(tmp_path, monkeypatch):
    b = blue(tmp_path, monkeypatch)
    b.s["posts"]["100"] = post(100, "cA", 5000)
    b.s["posts"]["100"]["audit"]["ours"] = 3                                # 3 of ours liked another team's post
    b.s["posts"]["200"] = post(200, "cB", 7000)
    b.s["posts"]["200"]["audit"]["ours"] = 2
    assert {c["target"] for c in b.candidates()} == {200}


def test_co_reported_ruling_puts_its_ring_first_for_leads(tmp_path, monkeypatch):
    b = blue(tmp_path, monkeypatch)
    t = time.time()
    for pid, author in ((100, 5000), (300, 5300)):
        ring = post(pid, "cA", author)
        ring["post"]["created_at"] = ring["audit"]["created"] = S.iso(t - 3 * 3600)
        ring["audit"]["reply_posts"] = [dict(post_id=pid + 1, author=author + 1, created=S.iso(t - 3 * 3600))]
        b.s["posts"][str(pid)] = ring
    b.s["reports"] = {"p301": dict(kind="post", target=301, author=5301, label="cA", filed=t - 1.4 * 3600,
                                   status="pending", ring=300, classes=["reply_ring"], pg=0.02)}
    # a reply of ring #300, hidden 1.4 h after we filed it: 2+ teams reported it
    b.social = FakeSocial(gone={301})
    b.rulings()
    r = b.s["reports"]["p301"]
    assert r["status"] == "hidden" and r["co"] and b.s["harvest"]["5301"]["co"]
    assert b.s["posts"]["300"]["co"] and b.s["last"]["harvest"] == 0
    assert [x[0] for x in b.hide_targets()][:1] == [300]        # its ring checked first (301 is ours to rule)


def test_genuine_ruling_alerts_with_its_evidence_class_and_platform_time(tmp_path, monkeypatch):
    b = blue(tmp_path, monkeypatch)
    alerts = []
    monkeypatch.setattr(b, "alert", lambda kind, msg, gap_s=3600: alerts.append((kind, msg, gap_s)))
    t = time.time()
    filed = t - S.RULE_S - S.RULE_GRACE_S - 60
    ruled_at = filed + 1.5 * 3600                                   # 2 teams: ruled at 1.5 h, the platform says
    b.s.update(lock_until=ruled_at + S.LOCK_S, lock_src="server",
               server_lock=dict(at=ruled_at + 600, until=ruled_at + S.LOCK_S))
    b.s["reports"] = {"p2": dict(kind="post", target=2, author=5001, label="cA", filed=filed, status="pending",
                                 classes=["like_ring"], pg=0.1, age_min=12)}
    b.social = FakeSocial()
    b.rulings()
    r = b.s["reports"]["p2"]
    assert r["status"] == "genuine" and abs(r["ruled"] - ruled_at) < 1 and r["co"]
    (kind, msg, gap), = alerts
    assert kind == "genuine:p2" and gap == 0 and "like_ring" in msg and "10%" in msg and "1.5 h" in msg
