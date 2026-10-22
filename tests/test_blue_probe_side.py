"""swan_blue (todo/28 addendum): the one-off cap probe, and Yes-side targets first. No network, no secrets."""
import json
import re
import time

import capturethenarrative as ctn

from test_blue import S, blue, post

# the platform's answer when full (403, 22 Oct 14:26 UTC)
FULL = ('{"error": "your team already has 30 reports awaiting a moderator\'s ruling; more can be filed once some are '
        'ruled on"}')


def probe_blue(tmp_path, monkeypatch):
    b = blue(tmp_path, monkeypatch)
    b.live = True
    alerts, filed = [], []
    monkeypatch.setattr(b, "alert", lambda kind, msg, gap_s=0: alerts.append((kind, msg)))
    t = time.time()
    b.s["reports"] = {f"p{i}": dict(kind="post", status="pending", filed=t) for i in range(25)}
    b.s["reports"].update({f"a{i}": dict(kind="account", status="pending", filed=t) for i in range(5)})
    return b, alerts, filed


def probe(tmp_path):
    return json.loads((tmp_path / "cap_probe.dry.json").read_text())


def test_cap_probe_taken_means_accounts_file_beyond_the_cap(tmp_path, monkeypatch):
    b, alerts, filed = probe_blue(tmp_path, monkeypatch)

    def take(c):
        filed.append(c["key"])
        b.s["reports"][c["key"]] = dict(kind=c["kind"], status="pending", filed=time.time())
        return True
    monkeypatch.setattr(b, "file", take)
    ranked = [dict(key=f"a{100 + i}", kind="account", ev=14, pg=0.0) for i in range(3)] + \
        [dict(key="p500", kind="post", ev=20, pg=0.02, age_min=10)]
    b.fill(ranked, "auto")
    assert filed == ["a100"]                                         # one probe, nothing else that tick
    assert probe(tmp_path)["result"] == "accounts_dont_count" and probe(tmp_path)["pending"] == 30
    assert "do NOT count" in alerts[0][1] and "not confirmed by organisers" in alerts[0][1]
    b.fill(ranked[1:], "auto")
    assert filed == ["a100", "a101", "a102", "p500"]   # accounts beyond 30; posts by their own count (25 of 30)
    assert not b.probe_due()


def test_cap_probe_refused_naming_the_cap_means_accounts_count(tmp_path, monkeypatch):
    b, alerts, filed = probe_blue(tmp_path, monkeypatch)

    def refuse(c):
        filed.append(c["key"])
        return b.refused(c, ctn.APIError("POST", "/report", 400, FULL))
    monkeypatch.setattr(b, "file", refuse)
    b.fill([dict(key="a100", kind="account", ev=14, pg=0.0)], "auto")
    assert probe(tmp_path)["result"] == "accounts_count" and "30 reports awaiting" in probe(tmp_path)["why"]
    assert not b.locked() and "a100" not in b.s["reports"]             # no lock, and the lead stays for later
    assert "DO count" in alerts[0][1]
    b.fill([dict(key="a100", kind="account", ev=14, pg=0.0)], "auto")
    assert filed == ["a100"]                                         # asked once only


def test_cap_probe_lock_is_no_answer(tmp_path, monkeypatch):
    b, alerts, filed = probe_blue(tmp_path, monkeypatch)
    until = S.iso(time.time() + 3600).replace("+00:00", "Z")
    monkeypatch.setattr(b, "file", lambda c: b.refused(c, ctn.APIError(
        "POST", "/report", 403, '{"error": "reporting is suspended for your team until ' + until + '"}')))
    b.fill([dict(key="a100", kind="account", ev=14, pg=0.0)], "auto")
    assert "result" not in probe(tmp_path) and probe(tmp_path)["tries"] == 0 and b.locked() and not alerts


def test_side_of_a_ring_post():
    from swan_blue.side import side
    assert side("I favour YES because scarce hospital staff matter. #VoteYes") == "yes"
    assert side("I'm for the free jab and against the venue rule, so my mark goes NO. #H2D2No") == "no"
    assert side("Today I fixed a tiny accessibility bug in our dashboard.") == "unclear"


def test_yes_side_ranks_first_but_no_side_still_fills_and_never_reaches_the_detail(tmp_path, monkeypatch):
    b = blue(tmp_path, monkeypatch)
    b.live = True
    yes, no = post(100, "cA", 5000), post(200, "cB", 7000)
    yes["post"]["body"] = "I'm voting YES on the referendum. #VoteYes"
    no["post"]["body"] = "Keep Kingstonia open: vote no. #H2D2No"
    b.s["posts"] = {"100": yes, "200": no}
    ranked = b.ranked()
    roots = [c for c in ranked if c["key"] in ("p100", "p200")]
    assert [c["side"] for c in roots] == ["yes", "no"] and roots[0]["ev"] == roots[1]["ev"]
    for c in ranked:
        assert not re.search(r"\b(yes|no|side|vote|voting|referendum)\b", c["detail"], re.I)
    filed = []

    def take(c):
        filed.append(c["key"])
        b.s["reports"][c["key"]] = dict(kind=c["kind"], status="pending", filed=time.time(), side=c.get("side"),
                                        target=c["target"], label=c["label"])
        return True
    monkeypatch.setattr(b, "file", take)
    monkeypatch.setattr(S, "policy", lambda: dict(pg_max=0.1, per_day=10.0))
    b.fill(ranked, "auto")
    assert "p100" in filed and "p200" in filed and filed.index("p100") < filed.index("p200")
    b.status("auto", "x", [])
    sides = json.loads((tmp_path / "status.dry.json").read_text())["today"]["sides"]
    assert sides["yes"] >= 1 and sides["no"] >= 1


def test_a_full_platform_corrects_a_wrong_probe_and_holds_without_a_lock(tmp_path, monkeypatch):
    """22 Oct 14:18: the probe was taken with 30 pending in our ledger (account reports ruled early that we still
    counted), then at 14:26 the platform refused with 30 awaiting while we held 5 post reports: accounts count."""
    b, alerts, filed = probe_blue(tmp_path, monkeypatch)
    (tmp_path / "cap_probe.dry.json").write_text(json.dumps(dict(tries=1, result="accounts_dont_count",
                                                                 why="a5215 taken with 30 pending")))
    for k in list(b.s["reports"])[5:25]:
        del b.s["reports"][k]                                         # 5 posts and 5 accounts left pending
    b.s["reports"].update({f"a{50 + i}": dict(kind="account", status="pending", filed=time.time()) for i in range(30)})

    def refuse(c):
        filed.append(c["key"])
        return b.refused(c, ctn.APIError("POST", "/report", 403, FULL))
    monkeypatch.setattr(b, "file", refuse)
    b.fill([dict(key="a100", kind="account", ev=14, pg=0.0)], "auto")
    d = probe(tmp_path)
    assert d["result"] == "accounts_count" and d["corrected"] and "5 post reports pending" in d["why"]
    assert not b.locked() and b.s["cap_hold"] > time.time() and "CORRECTED" in alerts[0][1]
    b.fill([dict(key="a100", kind="account", ev=14, pg=0.0)], "auto")
    assert filed == ["a100"]                                           # holding: no retry inside 10 min


def test_full_by_our_ledger_still_tries_one_report_per_hold(tmp_path, monkeypatch):
    b, alerts, filed = probe_blue(tmp_path, monkeypatch)
    (tmp_path / "cap_probe.dry.json").write_text(json.dumps(dict(tries=1, result="accounts_count")))
    monkeypatch.setattr(b, "file", lambda c: filed.append(c["key"]) or True)
    ranked = [dict(key=f"a{100 + i}", kind="account", ev=14, pg=0.0) for i in range(3)]
    b.fill(ranked, "auto")
    b.fill(ranked[1:], "auto")
    assert filed == ["a100"]                       # 30 pending by our ledger: one try, then one per CAP_HOLD_S
    later = time.time() + S.CAP_HOLD_S + 1
    monkeypatch.setattr(S, "now", lambda: later)
    b.fill(ranked[1:], "auto")
    assert filed == ["a100", "a101"]
