"""todo/33 engagement per write: the free-lever cells (follow, like), their limits, engagers_first, the report.

Writes are off everywhere: engage_actions runs against fakes, and a dry run (live=False) calls nothing."""
import collections
import datetime as dt
import importlib.util
import json
import pathlib
import sys
import time
import types

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import capturethenarrative as ctn  # noqa: E402

from swan_bot import bot, config, engage, experiment, followup, jsonl, stealth, targeting  # noqa: E402


def load_report():
    spec = importlib.util.spec_from_file_location("engagement_report", ROOT / "scripts" / "engagement_report.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def citizen_in(cell_name, start=1000):
    return next(i for i in range(start, start + 1000) if engage.cell(i) == cell_name)


# ---- the cell is a pure function of the citizen's id ----
def test_cell_is_pure_stable_and_balanced():
    assert [engage.cell(i) for i in range(50)] == [engage.cell(i) for i in range(50)]
    assert engage.cell(1234) == engage.cell("1234")               # ids come as int or str
    assert engage.cell(77, cells=("a", "b")) in ("a", "b")
    n = collections.Counter(engage.cell(i) for i in range(100_000, 102_000))
    assert set(n) == set(config.ENG_CELLS) and min(n.values()) > 0.2 * 2000


def test_the_cell_pin_is_the_same_on_every_machine():
    """sha256, not hash(): a change here moves citizens between cells in the middle of the experiment."""
    import hashlib
    for i in (3, 500, 90_001):
        want = config.ENG_CELLS[int(hashlib.sha256(f"eng:{i}".encode()).hexdigest()[:12], 16) % 4]
        assert engage.cell(i) == want


# ---- what each cell does ----
def rec_for(**kw):
    return dict(dict(username="u1", persona="mere", account_id=3001, owner="tester", followed=[]), **kw)


def kinds(entries):
    return sorted(e["kind"] for e in entries)


@pytest.mark.parametrize("cell_name,reply,reply_back", [("none", [], ["follow"]), ("follow", ["follow"], ["follow"]),
                                                        ("like", ["like"], ["follow", "like"]),
                                                        ("follow+like", ["follow", "like"], ["follow", "like"])])
def test_each_cell_does_exactly_its_actions(cell_name, reply, reply_back):
    cit = citizen_in(cell_name)
    job = dict(mode="reply", draft_id="d1")
    assert kinds(engage.plan(job, rec_for(), cit, 55)) == reply
    assert kinds(engage.plan(dict(job, mode="reply_back"), rec_for(), cit, 56)) == reply_back   # answered: always follow


def test_other_modes_and_switches_touch_nothing(monkeypatch):
    cit = citizen_in("follow+like")
    for mode in ("second_voice", "post", "journalist", "thread"):
        assert engage.plan(dict(mode=mode), rec_for(), cit, 55) == []
    monkeypatch.setattr(config, "ENG_FOLLOW", False)
    assert kinds(engage.plan(dict(mode="reply"), rec_for(), cit, 55)) == ["like"]
    monkeypatch.setattr(config, "ENG_LIKE", False)
    assert engage.plan(dict(mode="reply"), rec_for(), cit, 55) == []
    monkeypatch.setattr(config, "ENG_FOLLOW_ANSWERED", False)
    assert engage.plan(dict(mode="reply_back"), rec_for(), citizen_in("none"), 55) == []


def test_no_second_follow_of_a_citizen_already_followed():
    cit = citizen_in("follow")
    assert engage.plan(dict(mode="reply"), rec_for(followed=[cit]), cit, 55) == []


def test_a_follow_lands_seconds_after_the_reply_and_a_like_minutes_after():
    cit, t = citizen_in("follow+like"), 1000.0
    follow, like = sorted(engage.plan(dict(mode="reply", draft_id="d"), rec_for(), cit, 55, now=t), key=lambda e: e["kind"])
    lo, hi = config.ENG_FOLLOW_DELAY_S
    assert like["kind"] == "like" and follow["kind"] == "follow"
    assert t + lo <= follow["due"] <= t + hi and t + config.ENG_LIKE_DELAY_S[0] <= like["due"]
    assert like["due"] - follow["due"] >= config.ENG_PAIR_GAP_S or config.ENG_LIKE_DELAY_S[0] - hi >= 0
    assert (follow["username"], follow["citizen"], follow["cell"], follow["mode"]) == ("u1", cit, "follow+like", "reply")
    assert like["post_id"] == 55 and follow["why"] == "first_reply" and like["why"] == "reply"


def test_the_delays_keep_a_like_a_minute_after_a_follow_by_construction():
    assert config.ENG_LIKE_DELAY_S[0] - config.ENG_FOLLOW_DELAY_S[1] >= 0
    assert config.ENG_FOLLOWS_PER_DAY <= 40 and config.ENG_FOLLOW_GAP_S >= 60


# ---- the limits ----
def test_follow_block_rules():
    t = 100_000.0
    assert engage.follow_block(rec_for(), 9, {}, t) is None
    assert engage.follow_block(rec_for(followed=[9]), 9, {}, t) == "already"
    day = rec_for(follow_times=[t - 3600 - i for i in range(config.ENG_FOLLOWS_PER_DAY)])
    assert engage.follow_block(day, 9, {}, t) == "day_cap"
    assert engage.follow_block(day, 9, {}, t + 24 * 3600) is None, "the day rolls: a follow an hour old no longer counts"
    assert engage.follow_block(rec_for(follow_times=[t - 30]), 9, {}, t) == "gap"
    assert engage.follow_block(rec_for(follow_times=[t - 90]), 9, {}, t) is None
    assert engage.follow_block(rec_for(), 9, {"9": {"like": t - 20}}, t) == "pair"
    assert engage.follow_block(rec_for(), 9, {"9": {"like": t - 90}}, t) is None
    assert engage.like_block(9, {"9": {"follow": t - 20}}, t) == "pair"
    assert engage.like_block(9, {"9": {"follow": t - 90}}, t) is None and engage.like_block(9, {}, t) is None


def test_note_follow_keeps_the_last_day_only():
    rec, t = rec_for(follow_times=[1.0, 100_000.0 - 5]), 100_000.0
    engage.note_follow(rec, 9, t)
    assert rec["followed"] == [9] and rec["follow_times"] == [t - 5, t] and engage.follows_today(rec, t) == 2
    engage.note_follow(rec, 9, t)                                  # the same citizen twice: listed once
    assert rec["followed"] == [9]


def test_budget_wait_reads_the_route_headers():
    rl = lambda limit, remaining, reset: types.SimpleNamespace(limit=limit, remaining=remaining, reset=reset)
    assert engage.budget_wait(None) == 0.0 and engage.budget_wait(rl(0, 0, 0)) == 0.0
    assert engage.budget_wait(rl(30, 20, 30)) == 0.0                                  # room to spare
    assert engage.budget_wait(rl(30, config.ENG_BUDGET_MARGIN + 1, 30)) == 0.0
    wait = engage.budget_wait(rl(30, 0, 30))                                          # empty: margin + 1 calls come back
    assert wait == pytest.approx((config.ENG_BUDGET_MARGIN + 1) * 30 / 30)


# ---- bot.engage_actions ----
class Acc:
    """A signed-in account: records its calls, reports a budget like the real client."""
    def __init__(self, calls, raises=None, rate_limit=None):
        self.calls, self.raises = calls, raises or {}
        self.rate_limit = rate_limit or ctn.RateLimit(30, 29, 60)

    def _do(self, what, arg):
        if what in self.raises:
            raise self.raises[what]
        self.calls.append((what, arg))

    def view(self, pid):
        self._do("view", pid)

    def like(self, pid):
        self._do("like", pid)

    def follow(self, aid):
        self._do("follow", aid)


def world(monkeypatch, recs=None, **acc_kw):
    logged, calls = [], []
    monkeypatch.setattr(bot, "log", logged.append)
    monkeypatch.setattr(bot, "_ROUTE_RL", {})
    monkeypatch.setattr(stealth, "asleep", lambda key, t=None: False)
    recs = recs or [rec_for()]
    saved = []
    accounts = types.SimpleNamespace(voices=lambda: recs, parked=lambda r: r.get("parked", False),
                                     session=lambda r: Acc(calls, **acc_kw), relogin=lambda r: Acc(calls, **acc_kw),
                                     save=lambda: saved.append(1))
    return accounts, logged, calls, saved


def entry(kind, citizen=900, due=0.0, **kw):
    return dict(dict(kind=kind, due=due, username="u1", citizen=citizen, post_id=55, cell="follow+like", mode="reply",
                     draft_id="d1", tries=0, why="first_reply"), **kw)


def test_live_follow_and_like_go_from_the_replying_persona(monkeypatch):
    accounts, logged, calls, saved = world(monkeypatch)
    state = {"eng_queue": [entry("follow"), entry("like", citizen=901, post_id=56)]}
    bot.engage_actions(state, accounts, live=True, now=1000.0)
    assert calls == [("follow", 900), ("view", 56), ("like", 56)]
    rec = accounts.voices()[0]
    assert rec["followed"] == [900] and rec["follow_times"] == [1000.0] and saved
    assert state["eng_queue"] == []
    follow, like = logged
    assert (follow["act"], follow["live"], follow["username"], follow["owner"], follow["eng_cell"], follow["citizen_id"],
            follow["account_id"], follow["purpose"], follow["voice_id"]) == (
        "follow", True, "u1", "tester", "follow+like", 900, 900, "eng_follow", 3001)
    assert (like["act"], like["post_id"], like["purpose"], like["voice_id"], like["draft_id"]) == ("like", 56, "eng_like", 3001, "d1")
    assert "persona" not in follow and "persona" not in like        # followup.py reads persona rows as voices


def test_a_dry_run_calls_nothing_and_keeps_the_record_clean(monkeypatch):
    accounts, logged, calls, saved = world(monkeypatch)
    state = {"eng_queue": [entry("follow"), entry("like", citizen=901)]}
    bot.engage_actions(state, accounts, live=False, now=1000.0)
    assert calls == [] and saved == [] and accounts.voices()[0]["followed"] == []
    assert [x["live"] for x in logged] == [False, False] and state["eng_queue"] == []


def test_nothing_due_nothing_done(monkeypatch):
    accounts, logged, calls, _ = world(monkeypatch)
    state = {"eng_queue": [entry("follow", due=2000.0)]}
    bot.engage_actions(state, accounts, live=True, now=1000.0)
    assert calls == [] and logged == [] and len(state["eng_queue"]) == 1


def test_follow_and_like_for_one_citizen_are_never_within_a_minute(monkeypatch):
    accounts, logged, calls, _ = world(monkeypatch)
    state = {"eng_queue": [entry("follow"), entry("like")]}                      # both due together
    bot.engage_actions(state, accounts, live=True, now=1000.0)
    assert calls == [("follow", 900)] and [x["act"] for x in logged] == ["follow"]
    (later,) = state["eng_queue"]
    assert later["kind"] == "like" and later["tries"] == 1 and later["due"] >= 1000.0 + config.ENG_PAIR_GAP_S
    bot.engage_actions(state, accounts, live=True, now=later["due"])
    assert calls[-2:] == [("view", 55), ("like", 55)] and state["eng_queue"] == []
    assert logged[-1]["act"] == "like"


def test_a_persona_follows_at_most_once_a_minute_and_forty_a_day(monkeypatch):
    accounts, logged, calls, _ = world(monkeypatch)
    state = {"eng_queue": [entry("follow", 901), entry("follow", 902)]}
    bot.engage_actions(state, accounts, live=True, now=1000.0)
    assert calls == [("follow", 901)] and state["eng_queue"][0]["citizen"] == 902      # the second waits its minute
    bot.engage_actions(state, accounts, live=True, now=1000.0 + config.ENG_RETRY_S + 1)
    assert calls == [("follow", 901), ("follow", 902)]
    rec = accounts.voices()[0]
    rec["follow_times"] = [1000.0 + 200 + i for i in range(config.ENG_FOLLOWS_PER_DAY - 1)] + [1000.0 + 100]
    state = {"eng_queue": [entry("follow", 950)]}
    bot.engage_actions(state, accounts, live=True, now=1000.0 + 500)
    assert ("follow", 950) not in calls and state["eng_queue"] == []                  # the day's cap ends it, no retry
    assert [x for x in logged if x["act"] == "eng_skip"][-1]["why"] == "day_cap"


def test_a_follow_already_made_is_dropped_and_other_voices_are_not_asked(monkeypatch):
    accounts, logged, calls, _ = world(monkeypatch, recs=[rec_for(followed=[900])])
    state = {"eng_queue": [entry("follow")]}
    bot.engage_actions(state, accounts, live=True, now=1000.0)
    assert calls == [] and logged[0]["why"] == "already" and state["eng_queue"] == []


def test_parked_gone_and_sleeping_voices_do_nothing(monkeypatch):
    accounts, logged, calls, _ = world(monkeypatch, recs=[rec_for(parked=True)])
    state = {"eng_queue": [entry("follow"), dict(entry("like"), username="nobody")]}
    bot.engage_actions(state, accounts, live=True, now=1000.0)
    assert calls == [] and [x["why"] for x in logged] == ["parked", "gone"]
    accounts, logged, calls, _ = world(monkeypatch)
    monkeypatch.setattr(stealth, "asleep", lambda key, t=None: True)
    state = {"eng_queue": [entry("follow")]}
    bot.engage_actions(state, accounts, live=True, now=1000.0)
    assert calls == [] and logged[0]["why"] == "asleep"


def test_a_429_puts_the_action_back_then_gives_up(monkeypatch):
    boom = ctn.RateLimited("POST", "/follow", 429, "slow", retry_after=120)
    accounts, logged, calls, _ = world(monkeypatch, raises={"follow": boom})
    state = {"eng_queue": [entry("follow")]}
    t = 1000.0
    for n in range(config.ENG_RETRIES):
        bot.engage_actions(state, accounts, live=True, now=t)
        (x,) = state["eng_queue"]
        assert x["tries"] == n + 1 and x["due"] >= t + 120
        t = x["due"]
    bot.engage_actions(state, accounts, live=True, now=t)
    assert state["eng_queue"] == [] and logged[-1]["why"] == "rate_limited_gave_up"
    assert accounts.voices()[0]["followed"] == [], "a follow that never went is not recorded"


def test_another_error_is_logged_and_not_retried(monkeypatch):
    accounts, logged, calls, _ = world(monkeypatch, raises={"follow": ctn.APIError("POST", "/follow", 404, "gone")})
    state = {"eng_queue": [entry("follow")]}
    bot.engage_actions(state, accounts, live=True, now=1000.0)
    assert state["eng_queue"] == [] and logged[0]["act"] == "follow_failed" and logged[0]["error"] == 404


def test_an_empty_route_budget_waits_for_the_headers(monkeypatch):
    empty = ctn.RateLimit(30, 0, 30)
    accounts, logged, calls, _ = world(monkeypatch, rate_limit=empty)
    state = {"eng_queue": [entry("follow", 901), entry("follow", 902, due=0.0)]}
    bot.engage_actions(state, accounts, live=True, now=1000.0)         # the first goes; its answer says the budget is gone
    assert calls == [("follow", 901)]
    accounts.voices()[0]["follow_times"] = []                            # (the per-persona gap is not what holds 902)
    bot.engage_actions(state, accounts, live=True, now=1000.0 + 61)
    assert calls == [("follow", 901)] and state["eng_queue"][0]["tries"] >= 1, "held back by the route's budget"


def test_at_most_a_few_actions_a_tick(monkeypatch):
    accounts, logged, calls, _ = world(monkeypatch, recs=[rec_for(), dict(rec_for(), username="u2")])
    state = {"eng_queue": [entry("like", 900 + i) for i in range(bot.ENG_PER_TICK + 3)]}
    bot.engage_actions(state, accounts, live=True, now=1000.0)
    assert len([c for c in calls if c[0] == "like"]) == bot.ENG_PER_TICK and len(state["eng_queue"]) == 3


def test_eng_last_is_trimmed(monkeypatch):
    accounts, _, _, _ = world(monkeypatch)
    state = {"eng_queue": [], "eng_last": {"1": {"like": 10.0}, "2": {"follow": 9000.0}}}
    bot.engage_actions(state, accounts, live=True, now=10_000.0)
    assert list(state["eng_last"]) == ["2"]


# ---- the arm: build_prompt logs it, the live switchback runs it, engagers_first orders by it ----
LIVE_SWITCHBACK = list(config.SWITCHBACK)          # read at import: conftest clears it for each test


def test_the_live_switchback_runs_the_engagement_arms_and_not_the_conversion_arms():
    assert LIVE_SWITCHBACK == [("arm_eng", config.ENG_ARMS, config.ENG_BLOCK_S),
                               ("arm_queue", config.QUEUE_ARMS, config.QUEUE_BLOCK_S),      # 26 Oct: the send-queue arms
                               ("arm_npc", config.NPC_ARMS, config.NPC_BLOCK_S)]            # todo/48: rotates only with NPC_EXTRA_ARM
    assert config.ENG_ARMS == ["mention"] and "arm_eng" in bot.ARMS      # engagers_first killed 25 Oct (todo/46)


def test_blocks_rotate_through_the_engagement_arms(monkeypatch):
    monkeypatch.setattr(config, "SWITCHBACK", [("arm_eng", config.ENG_ARMS, config.ENG_BLOCK_S)])
    assert {experiment.block("arm_eng", t=h * 3600)[1] for h in range(0, 24, 2)} == set(config.ENG_ARMS)


def test_build_prompt_logs_the_block_arm(monkeypatch):
    monkeypatch.setattr(config, "SWITCHBACK", [("arm_eng", ["engagers_first"], 7200)])
    job = dict(mode="reply", rec=dict(persona="lani"), frame=None, arm=None, wants=[], context=None,
               target=dict(post_id=5, author_id=500, body="Not sure how I'll vote on the referendum yet."))
    bot.build_prompt(job, types.SimpleNamespace(headline=None))
    assert job["meta"]["arm_eng"] == "engagers_first" and job["meta"]["block_id"].startswith("arm_eng:7200:")
    assert job["meta"]["arm_conv"] == "base"                      # the conversion arms are off the switchback
    monkeypatch.setattr(config, "SWITCHBACK", [])
    job["meta"] = {}
    bot.build_prompt(job, types.SimpleNamespace(headline=None))
    assert job["meta"]["arm_eng"] == "base" and "block_id" not in job["meta"]


def _order(monkeypatch, arm, engaged=()):
    monkeypatch.setattr(config, "SWITCHBACK", [("arm_eng", [arm], 7200)])
    monkeypatch.setattr(config, "TURNOUT_ARM", False)
    t = targeting.Targeter(None, log=lambda r: None)

    def post(pid, minutes):
        return dict(post_id=pid, author_id=1000 + pid, body="the referendum",
                    created_at=(dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes)).isoformat())
    for pid, cls, minutes in ((1, "lean_no", 30), (2, "yes_reason", 30), (3, "unsure", 30), (4, "lean_no", 2),
                              (5, "yes_reason", 30), (6, "unclear", 30)):
        t._queue(post(pid, minutes), "latest", None, None, 0, cls)
    out = []
    while (c := t.next_target(set(), set(), {}, engaged)) is not None:
        out.append(c["post"]["post_id"])
    return out


def test_engagers_first_orders_answered_then_unsure_then_fresh_then_the_rest(monkeypatch):
    got = _order(monkeypatch, "engagers_first", engaged={"1005"})
    assert got[0] == 5, "a citizen who answered us before goes first"
    assert set(got[1:3]) == {3, 6}, "then unsure / unclear"
    assert got[3] == 4, "then the freshest post (a reply within minutes)"
    assert set(got[4:]) == {1, 2}


# ---- the follow-back reads (followup.py) ----
def ago_iso(seconds):
    return dt.datetime.fromtimestamp(time.time() - seconds, dt.timezone.utc).isoformat()


class FollowerSocial:
    """followers(voice) in pages of 2, from a dict; counts reads."""
    def __init__(self, followers):
        self.followers_of, self.reads = followers, 0

    def followers(self, account_id, limit=50, cursor=None):
        self.reads += 1
        ids = self.followers_of[account_id]
        i = int(cursor or 0)
        page = ctn.Page([{"account_id": a} for a in ids[i:i + 2]], str(i + 2) if i + 2 < len(ids) else None)
        return page


def test_cohort_and_follow_back_checks(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ACTIONS_LOG", tmp_path / "actions.jsonl")
    monkeypatch.setattr(config, "ENGAGE_LOG", tmp_path / "engagement.jsonl")
    now = time.time()
    rows = [dict(ts=ago_iso(7 * 3600), act="reply", live=True, post_id=1, account_id=3001, username="u1", target_author=900,
                 eng_cell="follow"),
            dict(ts=ago_iso(7 * 3600), act="follow", live=True, citizen_id=900, eng_cell="follow", purpose="eng_follow"),
            dict(ts=ago_iso(7 * 3600), act="reply", live=True, post_id=2, account_id=3001, username="u1", target_author=901,
                 eng_cell="none"),
            dict(ts=ago_iso(3600), act="reply", live=True, post_id=3, account_id=3002, username="u2", target_author=902,
                 eng_cell="like"),                                  # too recent for the 6 h read
            dict(ts=ago_iso(7 * 3600), act="reply", live=True, post_id=4, account_id=3001, target_author=903),   # no cell
            dict(ts=ago_iso(7 * 3600), act="reply", live=False, post_id=5, account_id=3001, target_author=904,
                 eng_cell="none")]                                  # a dry run
    (tmp_path / "actions.jsonl").write_text("\n".join(map(json.dumps, rows)) + "\n")
    state = {}
    social = FollowerSocial({3001: [800, 801, 900], 3002: []})
    n = followup.engage_pass(followup.Reader(social, gap=0), state, now)
    assert n == 2
    assert sorted(state["engage_pending"]) == ["900", "901", "902"]
    got = {c["citizen_id"]: c for c in jsonl.Reader(config.ENGAGE_LOG)}
    assert got[900]["followed_back"] is True and got[901]["followed_back"] is False
    assert got[900]["check"] == 0 and got[900]["cell"] == "follow" and got[900]["voice_id"] == 3001
    assert social.reads == 2, "one voice's followers are read once for all its due citizens"
    assert followup.engage_pass(followup.Reader(social, gap=0), state, now) == 0     # nothing new, nothing re-read
    assert social.reads == 2
    # 24 h later the second check is due; the cursor means the log is not read again from the start
    assert followup.engage_pass(followup.Reader(social, gap=0), state, now + 18 * 3600) == 3


def test_an_unfinished_follower_read_is_unknown_not_no(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ACTIONS_LOG", tmp_path / "actions.jsonl")
    monkeypatch.setattr(config, "ENGAGE_LOG", tmp_path / "engagement.jsonl")
    (tmp_path / "actions.jsonl").write_text(json.dumps(dict(
        ts=ago_iso(7 * 3600), act="reply", live=True, post_id=1, account_id=3001, username="u1", target_author=900,
        eng_cell="none")) + "\n")
    social = FollowerSocial({3001: list(range(10, 40))})
    reader = followup.Reader(social, gap=0)
    monkeypatch.setattr(reader, "follower_ids", lambda a, cap=1500: (set(range(10, 20)), False))
    assert followup.engage_pass(reader, {}, time.time()) == 1
    (rec,) = jsonl.Reader(config.ENGAGE_LOG)
    assert rec["followed_back"] is None


def test_the_outcome_read_names_the_citizens_who_liked(monkeypatch):
    social = types.SimpleNamespace(
        counters=lambda pid: dict(view_count=3, like_count=2, reply_count=0, repost_count=0),
        likers=lambda pid, limit=100: [dict(account_id=a) for a in (900, 3500, 901)], replies=lambda *a, **kw: [])
    monkeypatch.setattr(followup, "is_citizen_id", lambda a: a < 3000)
    out = followup.Reader(social, gap=0).outcome(dict(post_id=1, ts=ago_iso(3600), act="reply"), 0, time.time(), {})
    assert out["citizen_likers"] == [900, 901] and out["citizen_likes"] == 2


# ---- the report ----
def portal(ts, msg, points):
    return dict(ts=dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat(), type="SCORE_NARRATIVE", message=msg,
                points=points)


def test_portal_lines_split_into_kinds():
    rep = load_report()
    t = 1_760_000_000
    rows = rep.portal_points([
        portal(t, "NPC engagement (×2 points): 9 views, 3 likes, 2 replies and 1 follow", 130),
        portal(t + 3600, "NPC engagement: 1 unfollow and 1 primary contribution to a change of mind away from your side", -100),
        portal(t + 7200, "NPC engagement: 1 primary contribution to a change of mind towards your side", 160),
        dict(portal(t, "x", 0), type="OTHER")])
    assert len(rows) == 3
    assert (rows[0]["likes"], rows[0]["replies"], rows[0]["follows"], rows[0]["views"]) == (3, 2, 1, 9)
    assert rows[0]["engagement"] == 2 * (3 * 5 + 2 * 15 + 20) and rows[0]["gain"] == rows[0]["engagement"]
    assert (rows[1]["unfollows"], rows[1]["away"], rows[1]["penalty"]) == (1, 1, 20 + 80)
    assert rows[1]["persuasion"] == -80 and rows[2]["toward"] == 1 and rows[2]["persuasion"] == 160


def block_rows(arm, n_blocks, writes_each, start_n, period=7200):
    out = []
    for b in range(n_blocks):
        n = start_n + b
        for k in range(writes_each):
            ts = n * period + 60 * k
            out.append(dict(ts=dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat(), act="reply", live=True,
                            post_id=10_000 * n + k, target_author=500 + k, arm_eng=arm,
                            block_id=f"arm_eng:{period}:{n}", eng_cell="none"))
    return out


def test_per_arm_split_on_a_fixture_portal_log():
    rep = load_report()
    period = 7200
    rows = block_rows("base", 2, 4, 1000) + block_rows("engagers_first", 2, 4, 1002)
    pts = []
    for n, kind in ((1000, "base"), (1001, "base"), (1002, "engagers_first"), (1003, "engagers_first")):
        t = (n + 1) * period + 3000                        # inside the block's lag window (1 h after its end)
        likes = 4 if kind == "base" else 12
        pts.append(portal(t, f"NPC engagement: {likes} likes, 2 replies", likes * 5 + 30))
    table = rep.arm_table(rows, rep.portal_points([dict(e) for e in pts]))
    assert table["base"]["writes"] == 8 and table["base"]["blocks"] == 2 and table["base"]["hours"] == 4
    assert table["base"]["likes"] == 8 and table["engagers_first"]["likes"] == 24
    assert table["base"]["points"] == 100 and table["engagers_first"]["points"] == 180
    verdicts = rep.arm_verdicts(table)
    assert verdicts["engagers_first"].startswith("promote") and "thin" in verdicts["engagers_first"]
    out = "\n".join(rep.render(rows, rep.portal_points(pts), {}, [], 0, time.time()))
    assert "| base | 2 | 8 | 4 | 100 |" in out and "| engagers_first | 2 | 8 | 4 | 180 |" in out


def test_an_arm_with_more_away_events_is_killed_whatever_its_points():
    rep = load_report()
    base = dict(blocks=6, writes=100, hours=12, points=1000, gain=1000, penalty=0, away=1, unfollows=0)
    worse = dict(base, points=2000, gain=2000, away=3)
    assert rep.arm_verdicts({"base": base, "engagers_first": worse})["engagers_first"].startswith("**kill**")
    costly = dict(base, points=1500, gain=300, penalty=400)
    assert "unfollows" in rep.arm_verdicts({"base": base, "engagers_first": costly})["engagers_first"]
    better = dict(base, points=1500, gain=1500)
    assert rep.arm_verdicts({"base": base, "engagers_first": better})["engagers_first"] == "promote (points per write beat base)"


def citizen_row(cell_name, cit, **kw):
    return dict(citizen=str(cit), cell=cell_name, did=set(), liked=False, replied=False, back=None, unfollowed=False,
                hidden=False, **kw)


def test_cell_table_and_verdicts():
    rep = load_report()
    cits = ([citizen_row("none", i) for i in range(400)]
            + [citizen_row("follow", 1000 + i, ) for i in range(400)])
    for c in cits:
        c["back"] = False
    for c in cits[400:]:
        c["did"] = {"follow"}
    for c in cits[400:440]:
        c["back"] = True                                   # 10% follow back: 2 points a citizen over none
    table = rep.cell_table(cits)
    assert table["none"]["mean"] == 0 and table["follow"]["mean"] == pytest.approx(2.0)
    assert table["follow"]["back"] == (40, 400) and table["follow"]["followed"] == 400
    assert rep.cell_verdicts(table)["follow"] == "promote (beats none)"
    thin = rep.cell_table(cits[:50] + cits[400:450])
    assert "thin" in rep.cell_verdicts(thin)["follow"]
    for c in cits[400:440]:
        c["unfollowed"] = True                              # all of them unfollow again: +20 then -20, net nothing
    table = rep.cell_table(cits)
    assert table["follow"]["mean"] == 0 and rep.cell_verdicts(table)["follow"].startswith("**kill**") is False
    for c in cits[400:410]:
        c["back"] = False                                   # ten whose follow-back was never seen: their -20 stands alone
    assert rep.cell_verdicts(rep.cell_table(cits))["follow"].startswith("**kill**")


def test_unfollowing_after_a_follow_back_nets_zero_not_minus_twenty():
    rep = load_report()
    c = citizen_row("follow", 5)
    c.update(back=True, unfollowed=True)
    assert rep.points_each(c) == 0
    c.update(liked=True, replied=True, unfollowed=False)
    assert rep.points_each(c) == 5 + 15 + 20


def test_report_end_to_end_on_a_tiny_log(tmp_path):
    import subprocess
    rep = load_report()
    now = time.time()
    (tmp_path / "logs").mkdir()
    (tmp_path / "data").mkdir()
    cits = {cell_name: citizen_in(cell_name, 1100) for cell_name in config.ENG_CELLS}
    rows = []
    for i, (cell_name, cit) in enumerate(cits.items()):
        rows.append(dict(ts=ago_iso(7 * 3600 - i), act="reply", live=True, post_id=100 + i, account_id=3001, username="u1",
                         target_author=cit, eng_cell=cell_name, arm_eng="base", block_id="arm_eng:7200:1"))
        if "follow" in cell_name:
            rows.append(dict(ts=ago_iso(7 * 3600 - i), act="follow", live=True, citizen_id=cit, eng_cell=cell_name,
                             purpose="eng_follow", username="u1"))
    (tmp_path / "logs" / "swan_actions.jsonl").write_text("\n".join(map(json.dumps, rows)) + "\n")
    outs = [dict(act="outcome", post_id=100 + i, check=1, citizen_likers=[cit], citizen_repliers=[], citizen_replies=0)
            for i, cit in enumerate(cits.values())]
    (tmp_path / "logs" / "swan_outcomes.jsonl").write_text("\n".join(map(json.dumps, outs)) + "\n")
    (tmp_path / "logs" / "swan_engagement.jsonl").write_text(json.dumps(dict(
        act="engage", citizen_id=cits["follow"], check=0, followed_back=True)) + "\n")
    (tmp_path / "data" / "portal.json").write_text(json.dumps(dict(events=[])))
    out = subprocess.run([sys.executable, "scripts/engagement_report.py", "--root", str(tmp_path), "--hours", "24"],
                         capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0, out.stderr
    text = out.stdout
    assert "### Free levers (eng_cell, per citizen)" in text and "Citizen-facing writes: **4**" in text
    assert "| follow | 1 | 1 | 0 | 100% [" in text and "| none | 1 | 0 | 0 | – |" in text
    assert "| like | 1 | 0 | 0 | – |" in text
