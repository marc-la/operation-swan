"""todo/48: citizens above id 2343 (swan_bot/npc.py, config.likely_citizen, the extra arm, Blue's guard, npc_scan).
No network, no secrets: posts are made up in the shapes the platform returns."""
import datetime as dt
import json
import pathlib
import sys
import time

import pytest

import capturethenarrative as ctn
from swan_bot import config, experiment, followup, npc, targeting

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

T0 = 1793000000.0                     # 2026-10-26 ~ (any fixed clock)
LIVE_SWITCH = (list(config.SWITCHBACK), dict(config.FREEZE_PIN))        # read at import: conftest clears them per test
LIVE_FLAGS = (config.NPC_EXTRA_ARM, config.BLUE_NPC_GUARD)


def iso(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat().replace("+00:00", "Z")


def citizen_posts(t0=T0, sessions=4, per=4, every_h=30):
    """A seeded citizen's page: a few posts inside a minute, every day or so; lowercase, a giphy now and then."""
    out, pid = [], 1000
    for s in range(sessions):
        for k in range(per):
            pid += 1
            body = "exactly. the rules list still isnt out" + (" https://giphy.com/gifs/x" if k == 0 else "")
            out.append(dict(post_id=pid, author_id=4580, kind="reply" if k else "post", body=body,
                            created_at=iso(t0 - s * every_h * 3600 + k * 20), embed=None))
    return out


def bot_posts(t0=T0, n=100, every_min=20):
    """A team bot's page: one reply every 20 minutes, all day (one every few minutes is a single session: no score)."""
    return [dict(post_id=5000 + k, author_id=9000, kind="reply" if k % 4 else "repost",
                 body="As a nurse I see the strain on our wards every week. Vote Yes for safer hospitals.",
                 created_at=iso(t0 - k * every_min * 60), embed=None) for k in range(n)]


CIT = dict(username="virginia.kunkel61", display_name="Virginia Kunkel")
BOT = dict(username="calvin_dunn48", display_name="Calvin Dunn")


# ---- the score -----------------------------------------------------------------------------------------------------
def test_a_citizen_rhythm_scores_high_and_a_bot_rhythm_low():
    c, b = npc.features(CIT, citizen_posts()), npc.features(BOT, bot_posts())
    assert c["burst"] > 0.5 and c["sess_per_day"] < 1.5 and b["sess_per_day"] >= 4
    assert npc.score(c) >= config.NPC_TARGET_MIN
    assert npc.score(b) < config.NPC_BLUE_MIN
    assert "sess" in npc.explain(b) or "hours" in npc.explain(b) or "gap" in npc.explain(b)


def test_too_few_posts_or_one_sitting_is_no_score_and_pull_rows_read_like_platform_posts():
    assert npc.features(CIT, citizen_posts()[:npc.LIVE_MIN_POSTS - 1]) is None
    assert npc.features(CIT, citizen_posts(sessions=1)) is None                 # one session shows no rhythm
    assert npc.features(BOT, bot_posts(every_min=6)) is None                   # nor does a bot that never stops
    assert npc.score(None) is None
    posts = citizen_posts()
    rows = [dict(id=p["post_id"], k=p["kind"], t=p["created_at"], b=p["body"],
                 e="giphy" if "giphy" in p["body"] else None) for p in posts]
    assert npc.features(CIT, posts) == npc.features(CIT, rows)


def test_the_model_uses_the_listed_features_and_the_cuts_are_ordered():
    assert set(npc.MODEL["w"]) == set(npc.FEATURES) and npc.MODEL.get("date")
    assert 0 < config.NPC_BLUE_MIN < config.NPC_TARGET_MIN < 1        # Blue favours recall, writing favours precision


def test_fit_finds_the_separating_feature():
    xs = [dict(a=float(i % 2) + 0.1 * (i % 3), b=float(i % 5)) for i in range(60)]
    ys = [i % 2 for i in range(60)]
    m = npc.fit(xs, ys, ["a", "b"], l2=0.1)
    assert m["w"]["a"] > 2 and abs(m["w"]["b"]) < 0.5
    assert npc.score(dict(a=1.0, b=2.0), m) > 0.9 > 0.1 > npc.score(dict(a=0.0, b=2.0), m)


# ---- config: the cached scores, the switches -----------------------------------------------------------------------
@pytest.fixture
def scores(tmp_path, monkeypatch):
    path = tmp_path / "npc_scores.json"
    monkeypatch.setattr(config, "NPC_SCORES_FILE", path)

    def write(sc, built=None):
        built = time.time() if built is None else built
        path.write_text(json.dumps(dict(built_ts=built, scores={str(k): dict(s=v) for k, v in sc.items()})))
        config._NPC["mtime"] = None                    # same-second rewrites: force a re-read
    return write


def test_no_file_changes_nothing(scores):
    assert config.npc_score(4580) is None and not config.likely_citizen(4580) and config.likely_citizen(100)
    assert config.npc_target(4580) is None and config.blue_citizen(4580) is None


def test_likely_citizen_reads_the_cut_and_is_citizen_stays_the_id_rule(scores, monkeypatch):
    scores({4580: 0.97, 4464: 0.5, 100: 0.0})
    assert config.likely_citizen(4580) and not config.likely_citizen(4464)
    assert not config.is_citizen(4580) and config.is_citizen(100)           # every metric keeps the id rule
    assert config.npc_score(100) is None                                    # seeded ids are never scored
    scores({4580: 0.97}, built=time.time() - config.NPC_SCORES_MAX_AGE_S - 60)
    assert not config.likely_citizen(4580)                                  # a stale file: targeting ignores it
    monkeypatch.setattr(config, "BLUE_NPC_GUARD", True)
    assert config.blue_citizen(4580) == 0.97                                # ...Blue never does (recall)


def test_both_switches_are_on_in_every_block_and_through_the_freeze():   # on 27 Oct, off 28 Oct, on for good 29 Oct
    assert LIVE_FLAGS == (True, True)
    switchback, pins = LIVE_SWITCH
    assert ("arm_npc", ["extra"], 3 * 3600) in switchback and pins["arm_npc"] == "extra"
    assert ("arm_style", ["fixes"], config.STYLE_BLOCK_S) in switchback and pins["arm_style"] == "fixes"
    assert {"NPC_EXTRA_ARM", "BLUE_NPC_GUARD"} <= set(config.STEALTH_ENV)       # SWAN_NPC_EXTRA_ARM=0 still turns it off


def test_npc_target_needs_the_arm(scores, monkeypatch):
    scores({4580: 0.97, 4464: 0.2})
    assert config.npc_target(4580) is None and not config.writes_to_citizen(4580)
    monkeypatch.setattr(config, "NPC_EXTRA_ARM", True)
    assert config.npc_target(4580) == 0.97 and config.writes_to_citizen(4580)
    assert config.npc_target(4464) is None and config.npc_target(100) is None and config.writes_to_citizen(100)


# ---- targeting: the extra arm ----------------------------------------------------------------------------------------
def ago(minutes):
    return iso(time.time() - minutes * 60)


def post(pid, author, body="i still havent seen the venue list for the vote, publish it"):
    return dict(post_id=pid, author_id=author, created_at=ago(2), body=body)


def arm(monkeypatch, which):
    monkeypatch.setattr(config, "SWITCHBACK", [("arm_npc", [which], 3 * 3600)])


def test_consider_admits_a_likely_citizen_only_in_an_extra_block(scores, monkeypatch):
    scores({4580: 0.97, 4464: 0.3})
    t = targeting.Targeter(None, log=lambda r: None)
    arm(monkeypatch, "extra")
    t._consider(post(1, 4580), "latest")
    assert 1 not in t.candidates                                            # the arm is off
    monkeypatch.setattr(config, "NPC_EXTRA_ARM", True)
    t._consider(post(2, 4580), "latest")
    t._consider(post(3, 4464), "latest")                                    # under NPC_TARGET_MIN: a team bot
    assert t.candidates[2]["npc_score"] == 0.97 and 3 not in t.candidates
    arm(monkeypatch, "base")
    t._consider(post(4, 4580), "latest")
    assert 4 not in t.candidates                                            # a base block is today's behaviour
    t._consider(post(5, 100), "latest")
    assert "npc_score" not in t.candidates[5]                               # seeded citizens as always


def test_an_extra_candidate_left_when_the_block_ends_is_dropped_and_answered_ends_it(scores, monkeypatch):
    scores({4580: 0.97, 4581: 0.95})
    monkeypatch.setattr(config, "NPC_EXTRA_ARM", True)
    logged = []
    t = targeting.Targeter(None, log=logged.append)
    arm(monkeypatch, "extra")
    t._consider(post(1, 4580), "latest")
    t._consider(post(2, 4581), "latest")
    c = t.next_target(set(), set(), {})
    assert c["npc_score"] >= config.NPC_TARGET_MIN
    t.answered(c["post"], "reply")
    assert t.items[c["post"]["post_id"]]["o"] == "answered"
    arm(monkeypatch, "base")
    assert t.next_target(set(), set(), {}) is None
    assert any(r.get("why") == "npc_block_over" for r in logged)


def test_the_arm_is_logged_on_citizen_writes_only_when_on(monkeypatch):
    from swan_bot import bot
    assert {"arm_npc", "npc_block"} <= set(bot.ARMS)
    monkeypatch.setattr(config, "SWITCHBACK", [("arm_npc", ["extra"], 3 * 3600)])
    assert experiment.block("arm_npc")[1] == "extra"


# ---- outcomes count the extra citizens' replies ----------------------------------------------------------------------
class _Social:
    def counters(self, pid):
        return dict(like_count=2, reply_count=3, view_count=10, repost_count=0)

    def likers(self, pid, limit=100):
        return [dict(account_id=4580), dict(account_id=9000)]

    def replies(self, pid, limit=100):
        return [dict(author_id=4580), dict(author_id=100), dict(author_id=9000)]


def test_outcome_counts_likely_citizens_apart(scores):
    scores({4580: 0.97, 9000: 0.1})
    r = dict(post_id=7, act="reply", ts=iso(time.time() - 7200), target_author=4580)
    o = followup.Reader(_Social(), gap=0).outcome(r, 0, time.time(), {})
    assert o["cit_def"] == "likely"                                             # 29 Oct: citizen_* include them
    assert o["citizen_replies"] == 2 and o["citizen_likes"] == 1 and o["citizen_repliers"] == [100, 4580]
    assert o["npc_replies"] == 1 and o["npc_likes"] == 1 and o["npc_repliers"] == [4580]   # still apart
    assert o["target_replied"] == 1


def test_the_report_counts_a_likely_citizen_once():
    import engagement_report as er
    w = dict(post_id=1)
    old = {1: dict(citizen_replies=1, citizen_likes=0, npc_replies=1, npc_likes=1)}          # before 29 Oct: id rule
    new = {1: dict(cit_def="likely", citizen_replies=2, citizen_likes=1, npc_replies=1, npc_likes=1)}
    assert er.proxy(w, old) == er.proxy(w, new) == 2 * 15 + 1 * 5


def test_engagement_report_reads_the_arm_out_with_the_npc_writes_apart():
    import engagement_report as er
    blk = lambda n: f"arm_npc:10800:{n}"                                      # noqa: E731
    t = 10800 * 166000 + 60
    rows = [dict(act="reply", post_id=1, target_author=100, arm_npc="base", npc_block=blk(166000), ts=iso(t)),
            dict(act="reply", post_id=2, target_author=4580, npc_score=0.97, arm_npc="extra", npc_block=blk(166001),
                 ts=iso(t + 10800)),
            dict(act="reply", post_id=3, target_author=9000, arm_npc="extra", npc_block=blk(166001), ts=iso(t + 10800))]
    assert [r["post_id"] for r in er.citizen_writes(rows)] == [1, 2]          # 9000: neither a citizen nor scored
    outcomes = {1: dict(citizen_replies=1, citizen_likes=0), 2: dict(npc_replies=1, npc_likes=1, target_replied=1)}
    text = "\n".join(er.npc_section(rows, [], outcomes))
    assert "arm_npc" in text and "| extra | 1 | 1 | 1 |" in text and "20.00 (1)" in text
    assert er.npc_section([dict(act="reply", post_id=1, target_author=100)], [], {}) == []


# ---- Blue's guard ----------------------------------------------------------------------------------------------------
def test_blue_never_counts_a_likely_citizen_as_a_team_when_guarded(scores, monkeypatch):
    from swan_blue import evidence as ev
    from swan_blue import fleets
    scores({4580: 0.4, 9000: 0.05})
    assert ev.is_team(4580, set()) and fleets.is_team_row(4580)             # off: as before
    monkeypatch.setattr(config, "BLUE_NPC_GUARD", True)
    assert not ev.is_team(4580, set()) and not fleets.is_team_row(4580)     # 0.4 >= NPC_BLUE_MIN: maybe a citizen
    assert ev.is_team(9000, set()) and ev.is_team(9001, set())              # low or unscored: a team account


def test_blue_skips_a_report_on_a_likely_citizen_and_logs_the_score(scores, monkeypatch, tmp_path):
    from test_blue import FakeSocial, Reporter, blue
    scores({4580: 0.6})
    monkeypatch.setattr(config, "BLUE_NPC_GUARD", True)
    b = blue(tmp_path, monkeypatch)
    (tmp_path / "acc.json").write_text(json.dumps([dict(account_id=3000)]))
    monkeypatch.setattr(config, "ACCOUNTS_FILE", tmp_path / "acc.json")
    b.reporter = Reporter()

    class Social(FakeSocial):
        def get_post(self, pid):
            return {"post_id": pid, "author_id": 4580}
    b.social = Social()
    c = dict(key="p1", kind="post", target=1, author=4580, label="cA", detail="x", classes=["reply_ring"], ev=20,
             pg=0.02, base=(10, False, 1))
    assert not b.file(c) and b.skip == "npc" and b.reporter.filed == []
    assert b.s["reports"]["p1"]["status"] == "refused" and b.s["reports"]["p1"]["why"] == "npc"
    log = [json.loads(x) for x in (tmp_path / "reports.jsonl").read_text().splitlines()]
    assert [x for x in log if x.get("reason") == "npc"][0]["npc_score"] == 0.6
    b.note(dict(post_id=2, author_id=4580), "latest")
    assert "2" not in b.s["posts"]                                          # never noted for an audit either


# ---- npc_scan (no network) -------------------------------------------------------------------------------------------
def test_scan_takes_the_snapshot_authors_above_2343_not_ours():
    import npc_scan
    snap = dict(posts=[dict(author_id=a) for a in (100, 4580, 4580, 9000, 3000)])
    assert npc_scan.snapshot_authors(snap, ours={3000}) == [4580, 9000]


def test_scan_reader_paces_and_stops_on_two_429s():
    import npc_scan
    slept = []

    class S:
        rate_limit = None

        def __init__(self):
            self.n = 0

        def account_posts(self, aid, limit=100):
            self.n += 1
            if self.n in (2, 3):
                raise ctn.RateLimited("GET", "/x", 429, "slow", 7)
            return []
    s = S()
    read = npc_scan.Reader(s, rate=60, sleep=slept.append, clock=lambda: 0.0)
    assert read(s.account_posts, 1) == []
    with pytest.raises(RuntimeError):
        read(s.account_posts, 2)
    assert 10 in slept and read.calls == 3                                  # waited its Retry-After (at least 10 s) once


def test_scan_scores_an_account_and_merges_the_file(monkeypatch):
    import npc_scan

    class S:
        rate_limit = None

        def get_account(self, aid):
            return CIT

        def account_posts(self, aid, limit=100):
            return citizen_posts()
    s = S()
    rec = npc_scan.score_account(npc_scan.Reader(s, rate=6000, sleep=lambda x: None), s, 4580, {})
    assert rec["s"] >= config.NPC_TARGET_MIN and rec["n"] == 16 and rec["why"]
    out = npc_scan.merge(dict(scores={"9000": dict(s=0.1)}), {4580: rec}, t=T0)
    assert set(out["scores"]) == {"9000", "4580"} and out["built_ts"] == T0
    assert npc_scan.cut_table([(0.95, 1), (0.6, 1), (0.4, 0), (0.05, 0)], cuts=(0.5,)) == [(0.5, 1.0, 1.0, 0.0, 2, 0, 0)]


# ---- todo/63: first sight (the bot scores a new author above 2343 itself, then answers the post) ----------------------
class _Live:
    """The reader's client for first-sight reads: a profile and a page per account, every read counted; an account in
    `limited` answers 429."""
    rate_limit = None

    def __init__(self, pages, profiles=None, limited=()):
        self.pages, self.profiles, self.limited, self.calls = pages, profiles or {}, set(limited), []

    def get_account(self, aid):
        self.calls.append(("get_account", aid))
        if aid in self.limited:
            raise ctn.RateLimited("GET", "/accounts", 429, "slow", 7)
        return self.profiles.get(aid, CIT)

    def account_posts(self, aid, limit=100):
        self.calls.append(("account_posts", aid))
        return list(self.pages.get(aid, []))


def first_sight(monkeypatch):
    monkeypatch.setattr(config, "NPC_EXTRA_ARM", True)
    arm(monkeypatch, "extra")


def test_the_file_wins_and_a_first_sight_score_fills_in(scores):
    scores({4580: 0.2})
    config.npc_live_put(4580, dict(s=0.99, n=10))
    config.npc_live_put(4581, dict(s=0.97, n=10))
    assert config.npc_score(4580) == 0.2 and config.npc_score(4581) == 0.97
    assert config.likely_citizen(4581) and not config.is_citizen(4581)              # metrics keep the id rule
    config.npc_live_put(4582, dict(s=0.97, n=10), t=time.time() - config.NPC_SCORES_MAX_AGE_S - 60)
    assert config.npc_score(4582) == 0.97 and config.npc_score(4582, config.NPC_SCORES_MAX_AGE_S) is None
    assert not config.npc_unscored(4580) and not config.npc_unscored(4581) and config.npc_unscored(4583)
    assert not config.npc_unscored(100)                                              # seeded: never read


def test_a_file_entry_with_too_few_posts_is_tried_again_and_a_failed_read_never(tmp_path, monkeypatch):
    path = tmp_path / "npc_scores.json"
    monkeypatch.setattr(config, "NPC_SCORES_FILE", path)
    old = iso(time.time() - config.NPC_LIVE_RETRY_S - 60)
    path.write_text(json.dumps(dict(built_ts=time.time(), scores={
        "4580": dict(s=None, n=2, at=old), "4581": dict(s=None, n=0, at=old, err=403),
        "4582": dict(s=None, n=2, at=iso(time.time()))})))
    assert config.npc_unscored(4580) and not config.npc_unscored(4581) and not config.npc_unscored(4582)


def test_first_sight_scores_a_new_author_and_queues_the_post_in_the_same_refresh(scores, monkeypatch):
    scores({9000: 0.1})                                                     # the file knows a team bot, not 4580 or 9001
    first_sight(monkeypatch)
    logged = []
    s = _Live({4580: citizen_posts(), 9001: bot_posts()}, {9001: BOT})
    t = targeting.Targeter(s, log=logged.append)
    latest = [post(11, 4580), post(12, 9001), post(13, 9000), dict(post(14, 4580), kind="repost")]
    for p in latest:
        t._consider(p, "latest")
    assert not t.candidates                                                 # nobody above 2343 is known yet
    assert t._score_new(latest) == 2
    assert t.candidates[11]["npc_score"] >= config.NPC_TARGET_MIN and 12 not in t.candidates and 13 not in t.candidates
    assert {a for _, a in s.calls} == {4580, 9001}                          # 9000 is in the file
    rows = [r for r in logged if r.get("act") == "npc_live"]
    assert {r["author_id"] for r in rows} == {4580, 9001} and all(r.get("n") for r in rows)
    assert all("account_id" not in r for r in rows)                         # account_id is the acting account of ours
    n = len(s.calls)
    t._consider(post(15, 4580), "latest")
    assert t._score_new([post(15, 4580)]) == 0 and len(s.calls) == n        # read once
    assert 15 in t.candidates


def test_first_sight_never_reads_ours_late_accounts_seeded_ones_or_with_a_switch_off(scores, monkeypatch):
    scores({})
    first_sight(monkeypatch)
    config.ACCOUNTS_FILE.write_text(json.dumps([dict(account_id=4464, persona="x")]))
    s = _Live({})
    t = targeting.Targeter(s, log=lambda r: None)
    assert t._score_new([post(1, 4464), post(2, config.NPC_LIVE_MAX_ID + 1), post(3, 100)]) == 0
    monkeypatch.setattr(config, "NPC_LIVE_SCORE", False)
    t._score_new([post(4, 4580)])
    monkeypatch.setattr(config, "NPC_LIVE_SCORE", True)
    monkeypatch.setattr(config, "NPC_EXTRA_ARM", False)
    t._score_new([post(5, 4580)])
    assert s.calls == [] and not t.npc_wait


def test_first_sight_reads_a_few_authors_a_refresh_newest_first_and_waits_out_a_429(scores, monkeypatch):
    scores({})
    first_sight(monkeypatch)
    monkeypatch.setattr(config, "NPC_LIVE_PER_REFRESH", 2)
    s = _Live({a: citizen_posts() for a in (4581, 4582, 4583)}, limited={4582})
    t = targeting.Targeter(s, log=lambda r: None)
    assert t._score_new([post(30, 4583), post(20, 4582), post(10, 4581)]) == 1      # 4583, then a 429: stop
    assert 30 in t.candidates and set(t.npc_wait) == {20, 10} and config.npc_unscored(4582)
    s.limited.clear()
    assert t._score_new([]) == 2 and {20, 10} <= set(t.candidates) and not t.npc_wait
    stale = dict(post(40, 4584), created_at=ago(config.NPC_LIVE_WAIT_S / 60 + 1))
    t._score_new([stale])
    assert not t.npc_wait and ("get_account", 4584) not in s.calls          # past its best: not worth a read


def test_first_sight_reads_a_private_account_once_and_a_thin_page_again_later(scores, monkeypatch):
    scores({})
    first_sight(monkeypatch)
    s = _Live({4590: citizen_posts()[:2]}, {4591: dict(CIT, private=True)})
    t = targeting.Targeter(s, log=lambda r: None)
    t._score_new([post(1, 4590), post(2, 4591)])
    assert ("account_posts", 4591) not in s.calls                           # a private account's posts answer 403
    assert config._NPC_LIVE[4591]["err"] == "private" and config._NPC_LIVE[4590]["s"] is None
    assert not config.npc_unscored(4591, time.time() + 10 * 86400)
    assert not config.npc_unscored(4590) and config.npc_unscored(4590, time.time() + config.NPC_LIVE_RETRY_S + 1)
    assert not t.candidates


def test_refresh_scores_first_sight_authors_after_the_known_ones(scores, monkeypatch):
    scores({})
    first_sight(monkeypatch)
    s = _Live({4580: citizen_posts()})
    t = targeting.Targeter(s, log=lambda r: None)
    monkeypatch.setattr(targeting.feeds, "read", lambda *a, **k: [])         # no Trending
    monkeypatch.setattr(t, "_widen", lambda: None)
    order = []
    real = t._consider
    monkeypatch.setattr(t, "_consider", lambda p, src, *a, **k: (order.append(p["post_id"]), real(p, src, *a, **k)))
    monkeypatch.setattr(t, "_latest", lambda: dict(posts=[post(2, 4580), post(1, 100)], pages=1, gap=False, error=None,
                                                    remaining=None))
    assert t.refresh(force=True)
    assert {1, 2} <= set(t.candidates) and t.candidates[2]["npc_score"] >= config.NPC_TARGET_MIN
    assert order == [2, 1, 2]                       # every post judged at once; the new author's again once scored
