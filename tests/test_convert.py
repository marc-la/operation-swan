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
    from swan_bot import followup
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
