"""Themes (themes.py, playbook §3): who carries which wedge slogan, the level drawn per draft, the team-wide slogan
budget, and how the prompts and the gate treat each level. Offline: prompts are rendered, never sent.

    python -m pytest tests/test_themes.py -q
"""
import datetime as dt
import json
import pathlib
import random
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from swan_bot import bot, content, themes  # noqa: E402

SYD = ZoneInfo("Australia/Sydney")
NOW = dt.datetime(2026, 10, 22, 12, tzinfo=SYD).timestamp()
SLOGAN = {k: t["slogan"] for k, t in themes.THEMES.items()}
POST = ("Teuila asked me last week if she'd be checking tourists' papers at the counter. She's nineteen. She came "
        "to make coffee. {x} What would your barista say? #SmallBusiness")


def ts(day, hour=12):
    return dt.datetime(2026, *day, hour, tzinfo=SYD).timestamp()


class Always:
    """rng stand-in: every share draw passes; choices/choice take the first option."""
    def random(self):
        return 0.0

    def choices(self, keys, weights=None, k=1):
        return [keys[0]]

    def choice(self, seq):
        return seq[0]


def theme(key, level, position="end"):
    t = themes.THEMES[key]
    return dict(key=key, level=level, belief=t["belief"], echo=t["echo"][0] if level == "echo" else None,
                slogan=t["slogan"] if level == "verbatim" else None, position=position if level == "verbatim" else None,
                thread=None)


def said(ledger, key, persona, at, thread=None):
    ledger.record(f"Something from my week. {SLOGAN[key]} Who else?", persona, theme(key, "verbatim"), thread,
                  "post", now=at)


# ---- data and detection ----

def test_share_rises_with_the_multiplier():
    assert themes.post_share(ts((10, 19), 20)) == 0.40
    assert themes.post_share(ts((10, 25), 23)) == 0.40
    assert themes.post_share(ts((10, 26), 0)) == 0.55          # x2 from 26 Oct, Sydney time
    assert themes.post_share(ts((11, 1), 9)) == 0.70           # x4 from 1 Nov


def test_slogans_found_whatever_the_punctuation():
    assert themes.slogans_in("ok so. don't know, vote no!") == ["dont_know"]
    assert themes.slogans_in("Don’t know? Vote No.") == ["dont_know"]           # curly apostrophe
    assert themes.slogans_in("I don't know anyone who'll vote no") == []
    assert themes.slogans_in("No list, no yes. Get the jab. Vote No.") == ["no_list", "get_jab"]


def test_position():
    verdict = POST.format(x=f"I hired baristas. {SLOGAN['staff']}")
    assert themes.position(verdict, "staff") == "end"           # just before the closing question: the verdict
    mid = (f"{SLOGAN['staff']} That's what I told Teuila when she asked about the counter, and what I told my mum "
           f"over the coconut buns on Sunday, and what I'll tell the crews at Regatta Week. I'm voting No.")
    assert themes.position(mid, "staff") == "middle"
    assert themes.position("Nothing here.", "staff") is None


# ---- who carries what ----

def test_pick_respects_personas_frames_and_modes():
    led = themes.Ledger()
    posts = {(led.pick("tomasi", "F6_islands", "post", now=NOW) or {}).get("key") for _ in range(400)}
    assert posts == {None, "dont_know", "staff"}        # a post: any theme Tomasi carries (not no_list)
    for _ in range(200):
        t = led.pick("tomasi", "F6_islands", "reply", now=NOW)
        assert t is None or t["key"] == "dont_know"     # a reply: the frame must fit (staff's frames lack F6)
    assert led.pick("josh", "F9_parliament", "thread", now=NOW, rng=Always()) is None      # never in our own threads
    assert led.pick("josh", "F9_parliament", "second_voice", now=NOW, rng=Always()) is None
    assert led.pick("josh", "F9_parliament", "journalist", now=NOW, rng=Always()) is None


def test_only_josh_says_voted_hawthorne():
    random.seed(1)
    for persona in ("dan", "wally", "kai", "isla"):
        for _ in range(300):
            t = themes.Ledger().pick(persona, "F9_parliament", "post", now=NOW)
            if t and t["key"] == "own_party":
                assert t["slogan"] is None
                assert t["echo"] is None or t["echo"] in themes.THEMES["own_party"]["echo"]
    levels = set()
    for _ in range(400):
        t = themes.Ledger().pick("josh", "F9_parliament", "post", now=NOW)
        if t and t["key"] == "own_party":
            levels.add(t["level"])
            assert t["slogan"] in (None, SLOGAN["own_party"])
    assert "verbatim" in levels


def test_levels_roughly_as_weighted():
    random.seed(4)
    led, got = themes.Ledger(), {}
    for _ in range(3000):
        meta = {}
        t = led.pick("lani", "F7_livelihoods", "post", now=NOW, meta=meta)
        if t:
            got[meta["theme_level"]] = got.get(meta["theme_level"], 0) + 1
            assert meta["theme"] == t["key"]
    n = sum(got.values())
    assert 0.3 < n / 3000 < 0.5                                 # ~40% of posts carry a theme on 22 Oct
    assert 0.42 < got["implicit"] / n < 0.58 and 0.06 < got["verbatim"] / n < 0.14
    replies = [themes.Ledger().pick("lani", "F7_livelihoods", "reply", now=NOW) for _ in range(600)]
    assert {t["level"] for t in replies if t} == {"implicit", "echo"}


def test_no_list_is_for_posts_only():
    led = themes.Ledger()
    assert "no_list" in led.candidates("grace", "F14_no_yes_but", NOW, "post")
    assert "no_list" not in led.candidates("grace", "F14_no_yes_but", NOW, "reply")
    assert "dont_know" in led.candidates("grace", "F14_no_yes_but", NOW, "reply")


def test_no_theme_more_than_twice_an_hour():
    led = themes.Ledger()
    for i in range(2):
        led.record("x", "lani", theme("staff", "implicit"), None, "post", now=NOW - 600 * i)
    assert "staff" not in led.candidates("isla", "F7_livelihoods", NOW)
    assert "staff" in led.candidates("isla", "F7_livelihoods", NOW + 3600)


# ---- the slogan budget ----

def test_one_slogan_per_account_per_day():
    led = themes.Ledger()
    said(led, "staff", "lani", NOW - 3 * 3600)
    assert led.verbatim_problem("no_list", "lani", now=NOW) == "slogan_account_day"
    assert led.verbatim_problem("no_list", "lani", now=NOW + 22 * 3600) is None


def test_team_cap_per_day():
    led = themes.Ledger()
    for i, (k, p) in enumerate([("staff", "lani"), ("no_list", "grace"), ("get_jab", "ana"), ("dont_know", "ben")]):
        said(led, k, p, NOW - 5 * 3600 * (i + 1))
    assert led.verbatim_problem("own_party", "josh", now=NOW) == "slogan_team_day"


def test_same_slogan_two_hours_apart_and_never_twice_in_a_thread():
    led = themes.Ledger()
    said(led, "dont_know", "ben", NOW - 3600, thread=77)
    assert led.verbatim_problem("dont_know", "grace", now=NOW) == "slogan_gap"
    assert led.verbatim_problem("no_list", "grace", now=NOW) is None
    assert led.verbatim_problem("dont_know", "grace", thread=77, now=NOW + 3 * 3600) == "slogan_thread"
    assert led.verbatim_problem("dont_know", "grace", thread=78, now=NOW + 3 * 3600) is None


def test_over_budget_verbatim_becomes_echo():
    led = themes.Ledger()
    said(led, "staff", "lani", NOW - 600)
    meta = {}
    t = led.pick("lani", "F7_livelihoods", "post", now=NOW, meta=meta, rng=FixedLevel("verbatim"))
    assert t["level"] == "echo" and t["slogan"] is None
    assert meta["theme_level"] == "echo" and meta["theme_level_drawn"] == "verbatim"


class FixedLevel(Always):
    """Always, but the level draw lands on `level` (experiment.draw uses rng.choices over the level keys)."""
    def __init__(self, level):
        self.level = level

    def choices(self, keys, weights=None, k=1):
        return [self.level] if self.level in keys else [keys[0]]


def test_after_three_endings_the_next_goes_mid_post():
    led = themes.Ledger()
    for i, p in enumerate(("lani", "grace", "ben")):
        led.record(f"A long week at the stall and the wharf and the school gate, all of it. {SLOGAN['no_list']}", p,
                   theme("no_list", "verbatim"), None, "post", now=NOW - 3 * 3600 * (i + 1))
    assert led.next_position(NOW) == "middle"


def test_send_problem_and_record_only_keep_themed_or_slogan_writes():
    led = themes.Ledger()
    led.record("Plain reply about the ferry.", "tomasi", None, 5, "reply", now=NOW)
    assert led.entries == []
    said(led, "staff", "lani", NOW)
    assert led.send_problem(POST.format(x=SLOGAN["staff"]), "isla", now=NOW + 60) == "slogan_gap"
    assert led.send_problem(POST.format(x="I'm voting No."), "isla", now=NOW + 60) is None


def test_old_entries_pruned():
    led = themes.Ledger()
    said(led, "staff", "lani", NOW - 4 * 86400)
    said(led, "no_list", "grace", NOW)
    assert [e["persona"] for e in led.entries] == ["grace"]


# ---- the gate ----

def test_draft_problem():
    staff = SLOGAN["staff"]
    assert themes.draft_problem(POST.format(x=staff), None, "post") == "unplanned_slogan"
    assert themes.draft_problem(POST.format(x=staff), theme("staff", "echo"), "post") == "unplanned_slogan"
    assert themes.draft_problem(POST.format(x=staff), theme("staff", "verbatim"), "post") is None
    assert themes.draft_problem(POST.format(x="I'm voting No."), theme("staff", "verbatim"), "post") == "slogan_missing"
    assert themes.draft_problem(POST.format(x=staff), theme("no_list", "verbatim"), "post") == "unplanned_slogan"
    bare = "Nobody can say which places count, so if you can't see it, the safe vote is No. Would you sign that?"
    assert themes.draft_problem(bare, theme("dont_know", "implicit"), "reply") == "theme_without_reason"
    assert themes.draft_problem(bare.replace("Would", "My bus loop alone has six stops. Would"),
                                theme("dont_know", "implicit"), "reply") is None


def test_echo_lines_must_not_repeat_across_drafts():
    led = themes.Ledger()
    old = "Esther here, ovens on at four. I bake bread, I'm not a border guard. Voting No."
    led.record(old, "esther", theme("staff", "echo"), None, "post", now=NOW)
    again = "Dan on the city loop. I drive the bus, I'm not a border guard. Voting No."
    fresh = "Dan on the city loop. I'm paid to get you to work on time, not to check your papers. Voting No."
    assert themes.draft_problem(again, theme("staff", "echo"), "post", led) == "theme_echo_repeat"
    assert themes.draft_problem(fresh, theme("staff", "echo"), "post", led) is None
    assert themes.draft_problem(again, theme("no_list", "echo"), "post", led) is None     # another theme's lines


def test_repair_notes():
    assert SLOGAN["no_list"] in themes.repair_note("slogan_missing", theme("no_list", "verbatim"))
    assert themes.repair_note("unplanned_slogan")
    assert themes.repair_note("something_else") is None


# ---- prompts ----

def test_slogan_only_in_the_prompt_on_a_verbatim_draw():
    p = content.PERSONA_BY_KEY["lani"]
    random.seed(3)
    for level in ("implicit", "echo", "attributed"):
        for _ in range(30):
            meta = {}
            u = content.post_prompt("F7_livelihoods", persona=p, theme=theme("staff", level), meta=meta)
            assert SLOGAN["staff"] not in u and meta["slogan"] is None
            assert themes.THEMES["staff"]["belief"] in u or meta["concede"]
    for pos in ("end", "middle"):
        hits = 0
        for _ in range(30):
            meta = {}
            u = content.post_prompt("F7_livelihoods", persona=p, theme=theme("staff", "verbatim", pos), meta=meta)
            if not meta["concede"]:
                hits += 1
                assert SLOGAN["staff"] in u and meta["slogan"] == SLOGAN["staff"]
                assert ("as its own sentence" in u) == (pos == "middle")
        assert hits


def test_concession_turns_the_theme_implicit():
    p = content.PERSONA_BY_KEY["lani"]
    random.seed(5)
    seen = 0
    for _ in range(80):
        meta = {"theme": "staff", "theme_level": "verbatim"}
        u = content.post_prompt("F7_livelihoods", persona=p, theme=theme("staff", "verbatim"), meta=meta)
        if meta["concede"]:
            seen += 1
            assert SLOGAN["staff"] not in u and meta["theme_level"] == "implicit"
            assert meta["theme_level_drawn"] == "verbatim" and "with no slogan" in u
    assert seen


def test_a_vote_no_slogan_is_the_verdict():
    p = content.PERSONA_BY_KEY["josh"]
    random.seed(6)
    for _ in range(40):
        meta = {}
        u = content.post_prompt("F9_parliament", persona=p, theme=theme("own_party", "verbatim", "end"), meta=meta)
        if not meta["concede"] and meta["shape"] != "confession":
            assert f"voting No with this line, word for word: {SLOGAN['own_party']}" in u
            assert "say plainly that you're voting No" not in u


def test_reply_prompt_carries_the_theme_without_its_slogan():
    p = content.PERSONA_BY_KEY["grace"]
    for level in ("implicit", "echo"):
        u = content.reply_prompt("Leaning yes but which places?", "F14_no_yes_but", [], persona=p,
                                 theme=theme("dont_know", level))
        assert themes.THEMES["dont_know"]["belief"] in u and SLOGAN["dont_know"] not in u
    assert "detail of your own life" in content.reply_prompt("x", "F14_no_yes_but", [], persona=p,
                                                              theme=theme("dont_know", "echo"))


# ---- the bot ----

class StubGen:
    def __init__(self, drafts):
        self.drafts, self.users = list(drafts), []

    def complete(self, system, user, **kw):
        self.users.append(user)
        return self.drafts.pop(0), "stub"


def test_draft_checked_repairs_a_missing_slogan(monkeypatch):
    monkeypatch.setattr(bot.quality, "check", lambda raw, *a, **kw: (raw, None))
    gen = StubGen([POST.format(x="I'm voting No."), POST.format(x=f"{SLOGAN['staff']} I'm voting No.")])
    job = dict(mode="post", meta={}, theme=theme("staff", "verbatim"))
    text, _, repair = bot.draft_checked(gen, job, "sys", "user", [], ledger=themes.Ledger())
    assert SLOGAN["staff"] in text and repair == "slogan_missing"
    assert f"word for word, as its own sentence, and change nothing else: {SLOGAN['staff']}" in gen.users[1]


def test_draft_checked_rejects_a_slogan_in_our_own_thread(monkeypatch):
    monkeypatch.setattr(bot.quality, "check", lambda raw, *a, **kw: (raw, None))
    gen = StubGen([f"Love this. {SLOGAN['dont_know']}", f"Love this. {SLOGAN['dont_know']}"])
    text, _, _ = bot.draft_checked(gen, dict(mode="thread", meta={}), "sys", "user", [], ledger=themes.Ledger())
    assert text is None


def test_pick_theme_only_for_posts_and_citizen_replies():
    led = themes.Ledger()
    job = dict(mode="reply", rec=dict(persona="grace"), frame="F14_no_yes_but",
               target=dict(post_id=9, reply_to_post_id=3))
    random.seed(0)
    for _ in range(50):
        meta = {}
        t = bot.pick_theme(job, led, meta)
        assert t is None or t["thread"] == 3
        assert job["theme"] is t and "theme" in meta
    assert bot.pick_theme(dict(job), None, {}) is None


# ---- the audit script ----

def _audit(tmp_path, recs, *flags):
    import importlib.util
    spec = importlib.util.spec_from_file_location("theme_audit", pathlib.Path(__file__).resolve().parents[1]
                                                  / "scripts" / "theme_audit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    log = tmp_path / "actions.jsonl"
    log.write_text("".join(json.dumps(r) + "\n" for r in recs))
    sys.argv = ["theme_audit.py", "--log", str(log), "--strict", *flags]
    return mod.main()


def _rec(minutes_ago, persona, text, **kw):
    t = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes_ago)
    return dict(ts=t.isoformat(), act="post", live=True, persona=persona, text=text, **kw)


def test_audit_flags_the_same_slogan_from_two_accounts(tmp_path, capsys):
    recs = [_rec(90, "ben", f"Fish were biting at the wharf. {SLOGAN['dont_know']} Who else?", theme="dont_know",
                 theme_level="verbatim"),
            _rec(30, "grace", f"Year 8 asked me about it in class. {SLOGAN['dont_know']} What did yours say?",
                 theme="dont_know", theme_level="verbatim")]
    assert _audit(tmp_path, recs) == 1
    assert "dont_know from ben and grace under 2 h apart" in capsys.readouterr().out


def test_audit_clean_log_passes(tmp_path, capsys):
    recs = [_rec(200, "ben", "Mrs Taufa buys tuna off my stall every Saturday, and nobody asks her for papers."),
            _rec(20, "grace", "My Year 8 sailing club meets Thursdays and I'd hate to check certificates at the jetty.")]
    assert _audit(tmp_path, recs) == 0
    assert "no flags" in capsys.readouterr().out
