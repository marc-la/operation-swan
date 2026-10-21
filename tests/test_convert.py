"""todo/20: replies that convert. G9 first: a citizen may not be lost to the gate (code fixes, repairs, model switch)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from swan_bot import bot, config, quality  # noqa: E402

# Kimi's drafts that were rejected live on 21 Oct (logs/swan_actions.jsonl on swan-ec2)
KIMI_404 = ("Aroha's 12 this month, same age your safeguards would need to reach. Medical exemptions are covered, but "
            "there's no end date, no list of venues, no review built in, just a binding Yes that lets them decide the "
            "details later. My girl could be turned away at her own school gate with no date when the rule lifts. Do "
            "you know anyone who's shifted from Yes to No once they saw what's actually on the ballot?")
AGE_81 = ("Sunset clauses and oversight sound sensible. The question has no end date, no review, and the list of "
          "venues comes after the vote. Mrs Florence Tuilagi, 81, would need papers for the ferry to see her sister.")


def test_too_long_is_trimmed_at_a_sentence_boundary():
    assert quality.check(KIMI_404, "reply")[1].startswith("length_")
    cut = quality.fix(KIMI_404, quality.check(KIMI_404, "reply")[1], "reply")
    assert cut and len(cut) <= quality.LENGTHS["reply"][1] and cut.startswith("Aroha's 12")
    assert quality.check(cut, "reply")[0]


def test_trim_keeps_the_opening_and_the_no():
    text = ("No end date anywhere in the question. " + "The list of places comes later, after the vote is done. " * 4 +
            "So I'm voting No.")
    cut = quality.trim(text, "reply")
    assert cut.startswith("No end date") and cut.endswith("I'm voting No.") and len(cut) <= 290
    assert quality.trim("x" * 400 + ".", "reply") is None          # one sentence too long: nothing to cut


def test_a_characters_age_is_not_a_statistic():
    assert quality.check(AGE_81, "reply")[0]
    assert quality.check("Aroha at 15, still showing papers at the school gate because nothing ends it. I'm voting No.",
                         "reply")[0]
    assert quality.unapproved_number("a poll at 87.3% says so") == "87.3%"


def test_an_unapproved_number_loses_its_sentence():
    text = ("The list of places comes after the vote, so a Yes is signing first. 37 venues are already pencilled in. "
            "That's why I'm voting No.")
    why = quality.check(text, "reply")[1]
    assert why == "unapproved_number_37"
    fixed = quality.fix(text, why, "reply")
    assert "37" not in fixed and quality.check(fixed, "reply")[0]


def test_same_opening_drops_the_first_clause():
    old = "Medical exemptions are in the plan, but nothing in the question says when it ends."
    new = ("Medical exemptions are in the plan, but the list of places only comes after the vote, and that's a "
           "blank cheque for the ferry and the market. I'm voting No.")
    why = quality.check(new, "reply", recent_texts=[old])[1]
    assert why == "same_opening"
    fixed = quality.fix(new, why, "reply")
    assert fixed.startswith("The list of places") and quality.check(fixed, "reply", recent_texts=[old])[0]


def test_short_reply_passes_when_it_says_no():
    assert quality.check("No end date in the question, so I'm voting No.", "reply")[1].startswith("length_")
    assert quality.check("No end date anywhere in the question, so I'm voting No on it.", "reply")[0]


class Gen:
    """Answers each call from a list of drafts and records which models it was allowed."""
    chain = [("bedrock", "moonshotai.kimi-k2.5"), ("bedrock", "zai.glm-5"), ("gemini", "gemini-3.8-flash")]

    def __init__(self, drafts):
        self.drafts, self.calls = list(drafts), []

    def complete(self, system, user, models=None, **kw):
        self.calls.append((models, user))
        allowed = [m for _, m in self.chain if not models or m in models]
        return self.drafts.pop(0), allowed[0]


BAD = "I hear you, and the list of places only comes after the vote, which is the whole trouble with a Yes."  # no code fix


def test_reply_gets_three_repairs_and_switches_model(monkeypatch):
    gen = Gen([BAD, BAD, BAD, "No end date anywhere in the question, and nobody can say which places count. I'm voting No."])
    job = dict(mode="reply", target=dict(body="only if there is an end date"))
    rejects = []
    text, backend, repair = bot.draft_checked(gen, job, "sys", "user", [], on_reject=lambda *a: rejects.append(a))
    assert text and backend == "zai.glm-5" and len(gen.calls) == 4 and len(rejects) == 3
    assert "moonshotai.kimi-k2.5" not in gen.calls[2][0]               # Kimi failed twice: left out after that
    assert "Cut «I hear you»" in gen.calls[1][1]                          # the repair names the exact problem
    assert job["meta"]["llm_calls"] == 4 and job["meta"]["repairs"] == 3


def test_a_long_draft_costs_one_call(monkeypatch):
    gen = Gen([KIMI_404])
    job = dict(mode="reply", target=dict(body="safeguards first"))
    text, _, _ = bot.draft_checked(gen, job, "sys", "user", [])
    assert text and len(gen.calls) == 1 and job["meta"]["fixes"] == ["length"]


def test_other_modes_keep_two_calls():
    gen = Gen([BAD, BAD, BAD])
    text, _, _ = bot.draft_checked(gen, dict(mode="thread_answer"), "sys", "user", [])
    assert text is None and len(gen.calls) == 2 and config.GATE_TRIES.get("thread_answer") is None


# ---- G8: a failed draft is requeued or logged as lost, never dropped silently ----
class Targeter:
    def __init__(self):
        self.requeued = []

    def requeue(self, cand, why):
        cand["tries"] = cand.get("tries", 0) + 1
        self.requeued.append((cand["post"]["post_id"], why))


def test_failed_reply_is_requeued(monkeypatch):
    logged = []
    monkeypatch.setattr(bot, "log", logged.append)
    t, queue = Targeter(), []
    cand = dict(post=dict(post_id=7, author_id=500))
    assert bot.lose(t, queue, dict(mode="reply", target=cand["post"], cand=cand), "gate:copied_fact") == "requeued"
    assert t.requeued == [(7, "gate:copied_fact")] and logged[-1]["act"] == "requeue"
    # without the candidate (or a targeter without requeue) the loss is logged with its reason
    assert bot.lose(t, queue, dict(mode="reply", target=cand["post"]), "no_model") == "lost"
    assert logged[-1] == dict(act="lost", why="no_model", mode="reply", target_post=7, target_author=500, draft_id=None)


def test_failed_reply_back_goes_round_the_queue_then_is_lost(monkeypatch):
    logged = []
    monkeypatch.setattr(bot, "log", logged.append)
    queue, job = [], dict(mode="reply_back", target=dict(post_id=8, author_id=501))
    outcomes = [bot.lose(None, queue, job, "gate:near_duplicate") for _ in range(bot.REPLY_BACK_TRIES)]
    assert outcomes == ["requeued"] * (bot.REPLY_BACK_TRIES - 1) + ["lost"]
    assert len(queue) == bot.REPLY_BACK_TRIES - 1


# ---- G7: reply-backs (and mentions), resolved only once dealt with; turn cap and thread depth ----
class Acc:
    def __init__(self, notes):
        self.notes, self.resolved = notes, []

    def notifications(self, unresolved, limit):
        return self.notes

    def resolve_notification(self, nid):
        self.resolved.append(nid)


def poll(posts, notes, monkeypatch, **kw):
    import types
    monkeypatch.setattr(bot, "log", lambda rec: None)
    acc = Acc(notes)

    def get_post(pid):
        p = posts[pid]
        if isinstance(p, Exception):
            raise p
        return p

    accounts = types.SimpleNamespace(voices=lambda: [dict(username="v0")], session=lambda rec: acc)
    return bot.reply_back_jobs(types.SimpleNamespace(get_post=get_post), accounts, None, **kw), acc


def note(nid, pid, kind="reply"):
    return dict(kind=kind, post=dict(post_id=pid), notification_id=nid)


def test_mentions_are_answered_and_failed_reads_stay_unresolved(monkeypatch):
    import capturethenarrative as ctn
    posts = {1: dict(post_id=1, author_id=500, body="what does @lani think?"),
             2: ctn.APIError("GET", "/posts/2", 503, "busy"), 3: ctn.APIError("GET", "/posts/3", 404, "gone"),
             4: dict(post_id=4, author_id=9000, reply_to_post_id=900, body="a team bot")}
    jobs, acc = poll(posts, [note(11, 1, "mention"), note(12, 2), note(13, 3), note(14, 4)], monkeypatch)
    assert [(j["target"]["post_id"], j["via"], j["our_text"]) for j in jobs] == [(1, "mention", "")]
    assert acc.resolved == [11, 13, 14], "a 503 stays unresolved for the next poll"
    assert "mentioned you" in bot.content.reply_back_prompt("", "what does @lani think?")


def test_turn_cap_and_deep_threads(monkeypatch):
    import time
    chain = {900 + i: dict(post_id=900 + i, author_id=500, reply_to_post_id=899 + i if i else None) for i in range(10)}
    posts = {**chain, 1: dict(post_id=1, author_id=500, reply_to_post_id=901, body="fair, but"),
             2: dict(post_id=2, author_id=502, reply_to_post_id=909, body="deep down"),
             3: dict(post_id=3, author_id=503, reply_to_post_id=901, body="third time")}
    now = time.time()
    turns = {"503": [now - 60, now - 120, now - 180]}
    jobs, acc = poll(posts, [note(11, 1), note(12, 2), note(13, 3)], monkeypatch, turns=turns)
    assert [j["target"]["post_id"] for j in jobs] == [1] and acc.resolved == [11, 12, 13]
    assert bot.turns_left({"503": [now - 3600] * 3}, 503), "an old session doesn't count"


# ---- step 1: followup.py counted posts we only liked as ours ----
def test_followup_our_ids_are_posts_we_wrote(tmp_path, monkeypatch):
    from swan_bot import feeds, followup
    monkeypatch.setattr(feeds, "FEED_LOG", tmp_path / "feed_reads.jsonl")
    rows = [dict(act="like", live=True, post_id=1, own=False), dict(act="repost", live=True, post_id=2),
            dict(act="amp_plan", live=True, post_id=3), dict(act="reply", live=True, post_id=4),
            dict(act="thread_answer", live=True, post_id=5), dict(act="post", live=False, post_id=6)]
    assert followup.our_post_ids(rows) == {4, 5}

    class Social:                     # a citizen replied to a post we only liked: not a reply to us
        def account_posts(self, aid, limit):
            return [dict(post_id=10, kind="post", created_at="2026-10-21T12:00:00+00:00", reply_to_post_id=1,
                         body="I'm still not sure about the referendum")]

        def feed_trending(self, limit):
            return [dict(post_id=1), dict(post_id=4)]

    reader = followup.Reader(Social(), max_reads=10, gap=0)
    write = dict(post_id=4, target_author=500, ts="2026-10-21T11:00:00+00:00", act="reply", target_text="unsure")
    rec = reader.followup(write, 0, 1_790_000_000, followup.our_post_ids(rows))
    assert rec["replied_to_us"] is False
    assert reader.trending(followup.our_post_ids(rows)) == {4: 2}
    assert '"proc": "swan-followup"' in (tmp_path / "feed_reads.jsonl").read_text()


# ---- step 5: levers, frames, no vaccine advocacy ----
def test_levers_and_frames_reweighted():
    import collections
    import random
    from swan_bot import content
    random.seed(1)
    assert "fear_answer" not in content.lever_weights() and content.lever_weights()["in_group"] == 2.0
    meta = {}
    for _ in range(200):
        content.reply_prompt("only if there's an end date", "F14_no_yes_but", ["end date"], meta=meta)
        assert meta["lever"] != "fear_answer"
    picks = collections.Counter(content.weighted_frame(["F14_no_yes_but", "F2_no_end"]) for _ in range(2000))
    assert 0.1 < picks["F2_no_end"] / 2000 < 0.3                       # 0.25 / 1.25 = 0.2


def test_vaccine_advocacy_is_off():
    from swan_bot import content, themes
    for text in ("Get the jab. Vote No.", "My answer: get the jab, it's free.", "You should get vaccinated first.",
                 "The vaccine is safe and it works.", "When your turn comes, who are you taking with you?"):
        assert content.advocacy(text), text
    for text in ("I'm vaccinated and I'm voting No.", "A No doesn't stop anyone getting the jab.",
                 "I'll get my jab when my turn comes, and I'm still voting No.", "The jab is free either way."):
        assert not content.advocacy(text), text
    assert "get_jab" not in themes.live()
    text = ("A pass at every shop door is the trouble, not the jab. Get the jab, it's free either way. "
            "But nobody can say which places count, so I'm voting No.")
    assert quality.check(text, "reply")[1] == "vaccine_advocacy"
    fixed = quality.fix(text, "vaccine_advocacy", "reply")
    assert "Get the jab" not in fixed and quality.check(fixed, "reply")[0]
    assert "Never urge anyone to get vaccinated" in content.system_prompt(content.PERSONAS[1], "F3_provax_antipass")


# ---- step 2: the light read; step 4: the style arm ----
def test_parse_read_is_lenient():
    from swan_bot import content
    good = content.parse_read('```json\n{"stance": "yes_but", "doubt": "wants an end date", '
                              '"frame": "F14_no_yes_but", "reply": "No end date in it."}\n```')
    assert good == dict(ok=True, stance="yes_but", doubt="wants an end date", frame="F14_no_yes_but",
                        reply="No end date in it.", skip=None)
    broken = content.parse_read('Here: {"stance": "Unsure", "frame": "F99", "reply": "Line one \\"quoted\\" ok", }')
    assert broken["ok"] and broken["stance"] == "unsure" and broken["frame"] is None
    assert broken["reply"] == 'Line one "quoted" ok'
    assert content.parse_read('{"skip": "about reef restoration"}')["skip"] == "about reef restoration"
    plain = content.parse_read("Just a reply, no JSON.")
    assert plain["ok"] is False and plain["reply"] == "Just a reply, no JSON."


def test_read_and_mirror_prompts():
    from swan_bot import content
    meta = {}
    u = content.reply_prompt("only if there's an end date", "F14_no_yes_but", ["end date"], meta=meta, read=True,
                             hint="F14_no_yes_but")
    assert '"stance"' in u and "- F1_blank_cheque:" in u and "keyword match suggests F14_no_yes_but" in u
    assert "They haven't fully decided" not in u and meta["style"] == "current"
    assert "They haven't fully decided" in content.reply_prompt("x", "F14_no_yes_but", [])
    meta = {}
    m = content.reply_prompt("only if there's an end date", "F14_no_yes_but", [], meta=meta, style="mirror_concede")
    assert "150 to 280 characters" in m and "No question anywhere" in m and "JSON" not in m
    assert meta["style"] == "mirror_concede" and meta["lever"] is None and meta["ask_kind"] == "none"
    assert "grant what is fair" in content.reply_back_prompt("ours", "theirs", style="mirror_concede")


def test_styles_alternate():
    from swan_bot import experiment
    arms = [experiment.alternate("style_t", ["a", "b"]) for _ in range(6)]
    assert arms in (["a", "b"] * 3, ["b", "a"] * 3)


def job_for(frame=None, arm=None):
    return dict(mode="reply", rec=dict(persona="lani"), frame=frame, arm=arm, wants=[], context=None,
                target=dict(post_id=5, author_id=500, body="Not sure how I'll vote on the referendum yet."))


def test_build_prompt_takes_no_frame_and_the_firm_yes_arm():
    import types
    targeter = types.SimpleNamespace(headline=None)
    job = job_for(frame=None, arm="firm_yes")
    _, system, user = bot.build_prompt(job, targeter)
    assert job["frame_in"] is None and job["frame"] in bot.content.FRAMES and job["style"] == "mirror_concede"
    assert job["read"] and '"stance"' in user and job["theme"] is None


READ = ('{"stance": "unsure", "doubt": "which places count", "frame": "F1_blank_cheque", "reply": '
        '"Which places count is the whole question, and nobody will say until after the vote. I\'m voting No."}')


def test_draft_checked_reads_the_json(monkeypatch):
    gen = Gen([READ])
    job = dict(job_for(), read=True, meta={})
    text, _, _ = bot.draft_checked(gen, job, "sys", "user", [])
    assert text.startswith("Which places count") and job["frame"] == "F1_blank_cheque"
    assert job["meta"]["read_stance"] == "unsure" and job["meta"]["read_ok"]


def test_draft_checked_read_skip_and_plain_repair(monkeypatch):
    gen = Gen(['{"skip": "a comment about reef restoration"}'])
    job = dict(job_for(), read=True, meta={})
    assert bot.draft_checked(gen, job, "sys", "user", [])[0] is None
    assert job["read_skip"] == "a comment about reef restoration" and len(gen.calls) == 1
    bad = READ.replace("whole question", "whole question. I hear you")          # consoling: a repair, answered plainly
    gen = Gen([bad, "Which places count is the whole question, and nobody says until after the vote. I'm voting No."])
    job = dict(job_for(), read=True, meta={})
    text, _, repair = bot.draft_checked(gen, job, "sys", "user", [])
    assert text and repair == "consoling_phrase" and "not JSON" in gen.calls[1][1]
    assert "I hear you" in gen.calls[1][1] and '"stance"' not in gen.calls[1][1].split("Your draft was:")[1]
    assert job["meta"]["read_stance"] == "unsure"


# ---- steps 7 and 8: the second-voice delay arm, one own like on alternate replies ----
def test_own_likes_are_logged_with_owner_and_retried_on_rate_limit(monkeypatch):
    import types
    import capturethenarrative as ctn
    logged = []
    monkeypatch.setattr(bot, "log", logged.append)
    calls = []

    class Acc:
        def view(self, pid):
            calls.append(("view", pid))

        def like(self, pid):
            if pid == 2:
                raise ctn.RateLimited("POST", "/like", 429, "slow down", retry_after=30)
            calls.append(("like", pid))

    booster = dict(username="b1", account_id=7001, role="booster", owner="marc")
    accounts = types.SimpleNamespace(boosters=lambda: [booster], voices=lambda: [], parked=lambda r: False,
                                     session=lambda r: Acc())
    state = {"own_likes": [dict(post_id=1, due=0, author="v1", draft_id="d1"), dict(post_id=2, due=0, author="v1"),
                           dict(post_id=3, due=10 ** 12, author="v1")]}
    bot.own_likes(state, accounts, live=True, now=100)
    assert calls == [("view", 1), ("like", 1), ("view", 2)]
    assert logged == [dict(act="like", live=True, post_id=1, username="b1", account_id=7001, role="booster",
                           owner="marc", own=True, purpose="reply_like", draft_id="d1")]
    assert sorted(x["post_id"] for x in state["own_likes"]) == [2, 3]       # 2 retried in a minute, 3 not due


def test_arm_settings():
    assert set(config.SECOND_VOICE_ARMS) == {"fast", "slow"} and config.SECOND_VOICE_ARMS["fast"][1] <= 4 * 60
    assert config.OWN_LIKE_DELAY_S[0] >= 60


# ---- todo/23 hook: group_style, and the off-topic reply ----
def test_group_style_hook():
    import types
    from swan_bot import content
    assert content.group_style({}) == "" and content.group_style(dict(group=None)) == ""
    assert "Never say when, where or how" in content.group_style(dict(group="turnout"))
    targeter = types.SimpleNamespace(headline=None)
    job = dict(job_for(frame="F14_no_yes_but"), group="turnout")
    _, _, user = bot.build_prompt(job, targeter)
    assert content.GROUP_STYLES["turnout"] in user.split("First read them")[0]
    job = dict(job_for(), group="off_topic",
               target=dict(post_id=6, author_id=500, body="Reef restoration day at the lagoon was brilliant"))
    _, _, user = bot.build_prompt(job, targeter)
    assert job["style"] == "off_topic" and not job["read"] and "Don't steer it to the referendum" in user
    gen = Gen(["Brilliant to hear the lagoon got a hand, my nephew still talks about the coral nursery."])
    text, _, _ = bot.draft_checked(gen, dict(job, meta={}), "sys", user, [])
    assert text, "no fact anchor needed off topic"


# ---- step 1: the conversion report ----
def test_conversion_report_on_a_tiny_log(tmp_path):
    import json
    import subprocess
    import time
    from datetime import datetime, timezone
    iso = lambda t: datetime.fromtimestamp(t, timezone.utc).isoformat()
    now = time.time()
    (tmp_path / "logs").mkdir()
    (tmp_path / "data").mkdir()
    rows = [dict(ts=iso(now - 7200), act="reply", live=True, post_id=1, target_author=500, style="mirror_concede",
                 read_ok=True, read_stance="yes_but", target_class="conditions", backend="k", llm_calls=1),
            dict(ts=iso(now - 5400), act="reply", live=True, post_id=2, target_author=501, style="current",
                 read_ok=True, read_stance="unsure", target_class="unsure", backend="k", llm_calls=3, fixes=["length"]),
            dict(ts=iso(now - 5000), act="skip", why="read", detail="about the reef", target_post=3,
                 target_class="off_topic"),
            dict(ts=iso(now - 4000), act="reply", live=True, post_id=4, target_author=9999)]          # a team bot
    (tmp_path / "logs" / "swan_actions.jsonl").write_text("\n".join(map(json.dumps, rows)))
    (tmp_path / "logs" / "swan_outcomes.jsonl").write_text(json.dumps(
        dict(act="outcome", post_id=1, check=0, citizen_replies=1, citizen_likes=2)))
    (tmp_path / "data" / "portal.json").write_text(json.dumps(dict(events=[dict(
        ts=iso(now - 1800), type="SCORE_NARRATIVE", message="NPC engagement: 1 like and 1 primary contribution to a "
        "change of mind towards your side")])))
    out = subprocess.run([sys.executable, "scripts/conversion_report.py", "--root", str(tmp_path), "--hours", "6"],
                         capture_output=True, text=True, cwd=pathlib.Path(__file__).resolve().parents[1]).stdout
    assert "Citizen-facing writes: **2**" in out and "towards **1** (primary 1)" in out
    assert "| mirror_concede | 1 | 1 | 100% [" in out and "Skipped by the read: **1** (33%" in out
    assert "| k | 2 | 2.00 | 50% |" in out


def test_first_call_rules_in_reply_prompts():
    from swan_bot import content
    recent = ["Sunset dates and venue lists are what you want", "Tania came off her early shift", "A blunt tool"]
    for style in ("current", "mirror_concede"):
        u = content.reply_prompt("only if there's an end date", "F14_no_yes_but", [], style=style, recent=recent)
        assert content.FIRST_CALL_RULES in u and "«Sunset dates and venue lists»" in u and "«A blunt tool»" in u
    assert "Don't open the way" not in content.reply_prompt("x", "F14_no_yes_but", [])
    assert content.FIRST_CALL_RULES in content.second_voice_prompt("x", "F6_islands", [], recent=recent)
