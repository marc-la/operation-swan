"""swan_blue.detect (todo/28 step 5): account leads from one wording, round-the-clock cadence, registration blocks.
No network, no secrets."""
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import capturethenarrative as ctn  # noqa: E402

from swan_blue import detect as D  # noqa: E402
from swan_blue import service as S  # noqa: E402

TEMPLATE = "Common sense and public hospital investment are the only viable path forward for our community"


def team(a):
    return a > 2343


def page(rows, t0=None):
    t0 = t0 or time.time()
    return [dict(post_id=1000 + i, author_id=a, body=b, created_at=S.iso(t0)) for i, (a, b) in enumerate(rows)]


def test_one_wording_from_five_accounts_is_watched_with_its_words(monkeypatch):
    monkeypatch.setattr(D, "_SOURCE", set())
    d, t = D.empty(), time.time()
    rows = [(6600 + i, f"@someone {TEMPLATE} #H2D2No") for i in range(5)]
    rows += [(7000, "My own words about the ferry and the market this morning, nothing like the others at all.")]
    rows += [(500, TEMPLATE)]                                          # a citizen: never counted
    D.observe(d, page(rows), team, t)
    new = D.find(d, t, ours={6604})
    assert sorted(new) == ["6600", "6601", "6602", "6603"]             # ours (6604) is never watched
    fp = d["watch"]["6600"]["kinds"]["fingerprint"]
    assert fp["n"] == 5 and fp["words"] in TEMPLATE.lower()
    text = D.evidence_text(d["watch"]["6600"]["kinds"])[0]
    assert text.startswith("it is one of 5 accounts registered after the campaign launch that posted the same 6-word")


def test_four_accounts_or_the_settings_own_words_are_no_fingerprint(monkeypatch):
    monkeypatch.setattr(D, "_SOURCE", set())
    d, t = D.empty(), time.time()
    D.observe(d, page([(6600 + i, TEMPLATE) for i in range(4)]), team, t)
    assert D.find(d, t) == []
    monkeypatch.setattr(D, "_SOURCE", set(D.grams(TEMPLATE)))         # a phrase every team quotes from the setting
    d = D.empty()
    D.observe(d, page([(6600 + i, TEMPLATE) for i in range(8)]), team, t)
    assert D.find(d, t) == []


def test_round_the_clock_and_bursts_are_cadence(monkeypatch):
    monkeypatch.setattr(D, "_SOURCE", set())
    d, t = D.empty(), time.time()
    for h in range(22):                                                 # 2 posts an hour for 22 hours
        D.observe(d, [dict(post_id=10 * h + k, author_id=8000, body=f"post {h} {k}") for k in range(2)], team,
                  t - h * 3600)
    D.observe(d, [dict(post_id=5000 + k, author_id=8100, body=f"x {k}") for k in range(25)], team, t)
    D.observe(d, [dict(post_id=6000 + k, author_id=8200, body=f"y {k}") for k in range(3)], team, t)
    D.find(d, t)
    assert d["watch"]["8000"]["kinds"]["cadence"] == dict(hours=22, posts=44, peak=2)
    assert d["watch"]["8100"]["kinds"]["cadence"]["peak"] == 25 and "8200" not in d["watch"]
    assert "posted in 22 of the last 24 hours" in D.evidence_text(d["watch"]["8000"]["kinds"])[0]


def test_a_registration_block_inside_a_fingerprint_group(monkeypatch):
    monkeypatch.setattr(D, "_SOURCE", set())
    d, t = D.empty(), time.time()
    D.observe(d, page([(6600 + i, TEMPLATE) for i in range(6)]), team, t)
    assert D.need_profiles(d, 10) == [str(6600 + i) for i in range(6)]
    for i in range(6):
        d["profiles"][str(6600 + i)] = dict(u=f"name{i}_surname_kc", c=S.iso(t - 86400 + 120 * i + (9e4 if i == 5 else 0)))
    D.find(d, t)
    b = d["watch"]["6600"]["kinds"]["block"]
    assert b["n"] == 5 and b["span_min"] == 8 and b["shape"] == "w_w_2" and b["shape_n"] == 5
    assert "block" not in d["watch"]["6605"]["kinds"]                  # registered a day apart
    assert D.shape("mira_solis_kc") == "w_w_2" and D.shape("dr.lena.voss") == "2.w.w"


def test_memory_drops_lone_sequences_and_old_hours(monkeypatch):
    monkeypatch.setattr(D, "_SOURCE", set())
    d, t = D.empty(), time.time()
    D.observe(d, page([(7000, "a long enough sentence that only one account ever wrote on this platform today")]),
              team, t - 4 * 3600)
    assert d["grams"]
    D.prune(d, t)
    assert d["grams"] == {} and d["hours"]                             # one account, 4 h ago: gone; its hour stays
    D.prune(d, t + 21 * 3600)
    assert d["hours"] == {} and d["posts"] == {}


class Social:
    def __init__(self, gone):
        self.gone = gone

    def get_post(self, pid):
        if pid in self.gone:
            raise ctn.APIError("GET", "/posts", 404, '{"error": "post not found"}')
        return {"post_id": pid}


def test_watched_account_with_a_hidden_post_becomes_an_account_lead_never_a_post_report(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "_SOURCE", set())
    for k, v in dict(STATE_FILE="state.json", STATUS_FILE="status.json", REPORTS_LOG="r.jsonl",
                     APPROVALS="a.jsonl", DETECT_FILE="detect.json").items():
        monkeypatch.setattr(S, k, tmp_path / v)
    b = S.Blue(live=False)
    t = time.time()
    D.observe(b.det, page([(6600 + i, TEMPLATE) for i in range(5)], t - 3600), team, t - 3600)
    D.find(b.det, t)
    b.social = Social(gone={1000})                                     # 6600's post, hidden by someone
    b.harvest_watched()
    h = b.s["harvest"]["6600"]
    assert h["by"] == "watch" and h["hidden_post"] == 1000 and h["kinds"] == ["fingerprint"]
    h.update(ready=True, actions=100, ring_posts=[], live_at=t, last_post=t - 600)     # read live a moment ago
    cands = b.candidates()
    assert [c["kind"] for c in cands] == ["account"]                   # nothing from a detector is a post report
    assert "posted the same 6-word sequence" in cands[0]["detail"] and "lockstep" not in cands[0]["detail"]
    assert b.detect_status()["by"]["fingerprint"] == dict(watched=5, hidden=1, reported=0)
