"""The overnight experiments (todo/13): arms are drawn, pinned and switched back as configured, logged, and read back
into follow-up labels, portal counts and report tables."""
import collections
import datetime as dt
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from swan_bot import analysis, config, content, experiment, followup, targeting  # noqa: E402

DAY = 86400


def iso(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat()


def test_draw_is_spread_and_respects_weights(monkeypatch):
    monkeypatch.setattr(config, "PIN", {})
    monkeypatch.setattr(config, "SWITCHBACK", [])
    rng = random.Random(1)
    got = collections.Counter(experiment.draw("ask_kind", experiment.ASK_WEIGHTS, rng=rng) for _ in range(5000))
    assert set(got) == set(experiment.ASK_WEIGHTS)
    assert 0.07 < got["none"] / 5000 < 0.13 and 0.15 < got["loss"] / 5000 < 0.21


def test_pin_wins_over_switchback(monkeypatch):
    monkeypatch.setattr(config, "SWITCHBACK", [("lever", ["loss", "switching"], 7200)])
    monkeypatch.setattr(config, "PIN", {"lever": "in_group"})
    meta = {}
    assert experiment.draw("lever", list(content.LEVERS), meta) == "in_group" and "block_id" not in meta


def test_switchback_blocks_rotate_and_shift_daily(monkeypatch):
    monkeypatch.setattr(config, "PIN", {})
    monkeypatch.setattr(config, "SWITCHBACK", [("reply_mode", list(experiment.REPLY_MODES), 7200)])
    t0 = 1000 * DAY                                   # midnight UTC
    day1 = [experiment.block("reply_mode", t0 + h * 3600 + 1)[1] for h in range(0, 24, 2)]
    day2 = [experiment.block("reply_mode", t0 + DAY + h * 3600 + 1)[1] for h in range(0, 24, 2)]
    assert day1.count("reason_first") == 6 and all(a != b for a, b in zip(day1, day1[1:]))
    assert all(a != b for a, b in zip(day1, day2))    # the same clock hour gets the other arm the next day
    meta = {}
    arm = experiment.draw("reply_mode", experiment.REPLY_MODES, meta, t=t0 + 1)
    assert meta["block_id"] == f"reply_mode:7200:{(t0 + 1) // 7200:.0f}" and meta["reply_mode"] == arm
    assert analysis.block_window(meta["block_id"]) == (t0, t0 + 7200)


def test_reply_modes_differ_only_in_the_reason(monkeypatch):
    text = "I'm leaning Yes because of the hospitals last time, but only if they publish the list."
    out = {}
    for mode in experiment.REPLY_MODES:
        monkeypatch.setattr(config, "PIN", {"reply_mode": mode})
        meta = {}
        out[mode] = content.reply_prompt(text, "F14_no_yes_but", ["the list"], meta=meta, persona=content.PERSONAS[0])
        assert meta["reply_mode"] == mode and meta["lever"] in content.LEVERS
        assert experiment.ASK_KINDS[meta["ask_kind"]] in out[mode]
    assert "Answer WHY they lean Yes" in out["reason_first"] and "Don't argue about these" in out["reason_first"]
    assert "Answer WHY" not in out["conditions_first"] and "Use their terms" in out["conditions_first"]
    assert "answer the reason above" in out["reason_first"]
    assert content.FRAMES["F14_no_yes_but"]["angle"] in out["conditions_first"]


def test_length_bands_fit_the_quality_gate():
    from swan_bot import quality
    for mode, bands in experiment.LENGTH_BANDS.items():
        lo, hi = quality.LENGTHS[mode]
        for _, a, b in bands.values():
            assert lo <= a < b <= hi, (mode, a, b)
    assert experiment.LENGTH_BANDS["post"]["long"][2] + 30 <= quality.LENGTHS["post"][1]


def test_no_ask_drops_the_question(monkeypatch):
    monkeypatch.setattr(config, "PIN", {"ask_kind": "none"})
    meta = {}
    u = content.reply_prompt("not sure about the mandate", "F1_blank_cheque", [], meta=meta)
    assert meta["ask_kind"] == "none" and experiment.ASK_KINDS["none"] in u
    # posts never end without a question yet: quality.check would reject them (no_closing_question)
    for _ in range(200):
        meta = {}
        content.post_prompt("F1_blank_cheque", meta=meta, persona=content.PERSONAS[0])
        assert meta["ask_kind"] != "none"


def test_stance_and_target_class():
    assert targeting.stance("Lovely day at the beach") is None
    assert targeting.stance("I'm voting No on the referendum") == "no"
    assert targeting.stance("Leaning No on the vaccine pass") == "no"
    assert targeting.stance("Voting yes. Protect the hospitals from H2D2.") == "yes"
    assert targeting.stance("Voting yes, but only if there's an end date for the mandate") == "unsure"
    assert targeting.target_class("I'll vote yes on the mandate only if the ICU is protected, hospitals overflowed last time") == "yes_reason"
    assert targeting.target_class("I'd vote yes on the mandate but only with a sunset clause") == "conditions"
    assert targeting.target_class("Not sure about the referendum yet") == "unsure"


def test_followup_labels():
    assert followup.label("unsure", []) == "silent"
    assert followup.label("unsure", [None, None]) == "silent"
    assert followup.label("unsure", ["unclear"]) == "unclear"
    assert followup.label("unsure", ["yes", "no"]) == "moved_no"
    assert followup.label("unsure", ["no", "yes"]) == "moved_yes"
    assert followup.label("no", ["no"]) == "no_change"
    assert followup.label("unsure", ["unsure", "unclear"]) == "no_change"


def test_due_checks(monkeypatch):
    monkeypatch.setattr(config, "OUTCOME_AT_S", (3600, 6 * 3600))
    monkeypatch.setattr(config, "FOLLOWUP_AT_S", (2 * 3600, 12 * 3600))
    now = 2000 * DAY
    rows = [dict(ts=iso(now - 3 * 3600), act="reply", live=True, post_id=1, target_author=50),
            dict(ts=iso(now - 3 * 3600), act="post", live=True, post_id=2),
            dict(ts=iso(now - 3 * 3600), act="repost", live=True, post_id=3),
            dict(ts=iso(now - 3 * 3600), act="reply", live=False, post_id=None, target_author=50)]
    state = {"outcome": {"2": [0]}, "followup": {}}
    got = {(kind, r["post_id"], i) for _, kind, i, r in followup.due(rows, state, now)}
    assert got == {("outcome", 1, 0), ("followup", 1, 0)}


class FakeSocial:
    def __init__(self, posts):
        self.posts = posts

    def account_posts(self, aid, limit=30, cursor=None):
        return self.posts

    def counters(self, pid):
        return {"view_count": 9, "like_count": 2, "reply_count": 1, "repost_count": 0}

    def likers(self, pid, limit=100, cursor=None):
        return [{"account_id": 40}, {"account_id": 5000}]

    def replies(self, pid, limit=100, cursor=None):
        return [{"author_id": 40, "post_id": 77}]

    def feed_trending(self, limit=50, cursor=None):
        return [{"post_id": 99}, {"post_id": 2}]


def test_reader_records(monkeypatch):
    now = 3000 * DAY
    r = dict(ts=iso(now - 3 * 3600), act="reply", live=True, post_id=2, target_author=40,
             target_text="Leaning yes on the mandate, but I'm not sure")
    posts = [dict(post_id=10, created_at=iso(now - 5 * 3600), body="voting yes on the referendum", kind="post"),
             dict(post_id=11, created_at=iso(now - 3600), body="ok you've convinced me, I'm voting no",
                  kind="reply", reply_to_post_id=2)]
    reader = followup.Reader(FakeSocial(posts), gap=0)
    f = reader.followup(r, 0, now, {2})
    assert f["label"] == "moved_no" and f["replied_to_this"] and f["posts_after"] == 1
    o = reader.outcome(r, 0, now, reader.trending({2}))
    assert o["citizen_likes"] == 1 and o["citizen_replies"] == 1 and o["trending_rank"] == 2
    reader.max_reads = reader.reads
    try:
        reader.outcome(r, 1, now, {})
        assert False, "budget not enforced"
    except StopIteration:
        pass


def test_parse_activity_lines():
    a = analysis.parse_activity("NPC engagement (×2 points): 8 views, 2 likes and 1 primary contribution to a "
                                "change of mind towards your side")
    assert a["category"] == "NPC engagement" and a["multiplier"] == 2.0
    assert a["views"] == 8 and a["likes"] == 2 and a["mind_primary_towards"] == 1 and a["towards"] == 1
    b = analysis.parse_activity("NPC engagement (×2 points): 1 contribution to a change of mind away from your side "
                                "and 1 unfollow")
    assert b["away"] == 1 and b["unfollows"] == 1 and "follows" not in b
    c = analysis.parse_activity("NPC engagement: 3 changes of mind towards neither side, 4 views")
    assert c["neither"] == 3 and c["views"] == 4 and c["multiplier"] is None


def test_wilson_and_tables():
    rate, lo, hi = analysis.wilson(5, 50)
    assert rate == 0.1 and 0.04 < lo < 0.1 < hi < 0.2
    assert analysis.wilson(0, 0) == (None, None, None)
    writes = [dict(post_id=i, lever="loss" if i % 2 else "switching") for i in range(80)]
    outcomes = {i: dict(post_id=i, citizen_likes=i % 3, views=10) for i in range(80)}
    followups = {i: dict(post_id=i, label="moved_no" if (i % 2 and i % 4 == 1) else "no_change") for i in range(80)}
    rows = {r["arm"]: r for r in analysis.arm_rows(writes, "lever", outcomes, followups)}
    assert rows["loss"]["n"] == 40 and rows["loss"]["moved_no"] == 20 and rows["switching"]["moved_no"] == 0
    assert analysis.separated(list(rows.values())) == [("loss", "above"), ("switching", "below")]


def test_report_builds(monkeypatch):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
    import experiment_report
    now = 4000 * DAY
    writes = [dict(ts=iso(now - 3600 * (i % 10)), mode="reply", post_id=i, lever=list(content.LEVERS)[i % 6],
                   reply_mode=experiment.REPLY_MODES[i % 2], block_id=f"reply_mode:7200:{(now - 3600 * (i % 10)) // 7200:.0f}",
                   target_class="yes_reason", persona="lani", opener=content.OPENERS[i % 2]) for i in range(40)]
    followups = [dict(post_id=i, check=1, citizen_id=100 + i, label="moved_no" if i % 7 == 0 else "silent",
                      texts=["voting no now"]) for i in range(40)]
    outcomes = [dict(act="outcome", post_id=i, check=0, citizen_likes=1, views=5) for i in range(40)]
    portal = [dict(ts=iso(now - 3600 * h), towards=1, neither=2, away=0) for h in range(10)]
    text = experiment_report.report(writes, followups, outcomes, portal, now - DAY, now, 1800)
    assert "## H1 switchback" in text and "### lever" in text and "moved_no" in text and "O1" in text
