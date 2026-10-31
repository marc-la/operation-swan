"""content/facts.toml and the fact pauses (todo/16). This is the validator an edit has to pass before it deploys
(deploy/check.sh runs it): the file parses and every fact is valid, every key the code names exists, nothing anywhere
states a known-false claim, and a paused fact (in the file or at runtime) reaches no prompt, by key or by wording."""
import datetime as dt
import json
import pathlib
import random
import re
import time
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from swan_bot import content, factdesk, quality, targeting, themes  # noqa: E402
from swan_bot import facts as fact_store  # noqa: E402
from swan_bot.playbook import characters, craft  # noqa: E402

NEUTRAL = "What do you all reckon about the vote?"


@pytest.fixture
def pause(tmp_path, monkeypatch):
    """pause(*keys): pause those facts at runtime, as the desk does (back to none after the test)."""
    path = tmp_path / "facts_paused.json"
    monkeypatch.setattr(fact_store, "PAUSED_FILE", path)

    def go(*keys, since="2099-01-01T00:00:00Z"):
        path.write_text(json.dumps({k: {"since": since, "slug": "test/article", "quote": "q"} for k in keys}))
        fact_store.refresh(force=True)
    yield go
    monkeypatch.undo()
    fact_store.refresh(force=True)
    assert not fact_store.pauses()


# ---- the file -----------------------------------------------------------------------------------------------------

def test_file_parses_and_every_fact_is_valid():
    table, claims = fact_store.load()
    assert table == fact_store.TABLE and len(table) >= 15 and claims
    for key, fact in table.items():
        assert not factdesk.problems(key, fact), (key, factdesk.problems(key, fact))


def test_the_desks_in_process_check_agrees(tmp_path):
    """factdesk.validate is what the autopilot runs on the box (no pytest there): the file passes it, and it catches
    a broken fact and a key the code names going missing. An overlay table merges over its key."""
    assert factdesk.validate(fact_store.TABLE) == []
    broken = dict(fact_store.TABLE, no_spread=dict(fact_store.TABLE["no_spread"], text=""))
    assert any("no_spread" in p for p in factdesk.validate(broken))
    assert any("named in content.py" in p for p in factdesk.validate(
        {k: v for k, v in fact_store.TABLE.items() if k != "no_end"}))
    overlay = tmp_path / "auto.toml"
    overlay.write_text(factdesk.render_tables({"no_spread": dict(fact_store.TABLE["no_spread"], status="paused",
                                                                 checked=factdesk.stamp(time.time()))}))
    assert fact_store.load(auto=overlay)[0]["no_spread"]["status"] == "paused"


def test_validator_rejects_broken_edits():
    good = dict(fact_store.TABLE["no_spread"])
    assert not factdesk.problems("no_spread", good)
    for bad in (dict(good, status="on"), dict(good, text=""), dict(good, text="x" * 201), dict(good, note="x" * 121),
                dict(good, checked="2026-10-21"), dict(good, staus="active"), dict(good, numbers=[36.2]),
                dict(good, says=["(unclosed"]), dict(good, says=["nothing like it"]), dict(good, frames=["F99"]),
                dict(good, text="There are no cases of H2D2 in Kingstonia."),          # a known-false claim
                dict(good, text="Vote on 2 Nov at your local school."),                  # voting logistics
                dict(good, note="Marina Castillo says so")):
        assert factdesk.problems("no_spread", bad), bad
    assert factdesk.problems("No Spread", good)
    assert factdesk.problems("no_spread", dict(good, note=" ".join(good["text"].split()[:8])))      # 7+ words of the text


def test_every_key_the_code_names_exists():
    keys = set(fact_store.TABLE)
    for name, f in content.FRAMES.items():
        assert set(f["facts"]) | set(f["requires"]) <= keys, name
        assert set(f["facts"]) & keys, name
    for _, line, req in content.REBUTTALS:
        assert set(req) <= keys, line
    for key, _, req in content.STORYLINES + [content.STORYLINE_FALLBACK]:
        assert set(req) <= keys, key
    for _, req, _ in content.WORLD_PARTS:
        assert set(req) <= keys
    assert set(content.EXEMPT_REQUIRES) <= keys and set(content.LEVER_REQUIRES) <= set(content.LEVERS)
    assert all(set(r) <= keys for r in content.LEVER_REQUIRES.values())


def test_notes_and_texts_cover_the_same_facts():
    active = {k for k, f in fact_store.TABLE.items() if f["status"] == "active"}
    assert set(content.FACT_NOTES) == set(content.FACTS) == active
    assert content.FACTS is fact_store.TEXTS and content.FACT_NOTES is fact_store.NOTES


def test_every_figure_in_an_active_fact_passes_the_number_gate():
    for key, f in fact_store.TABLE.items():
        if f["status"] == "active":
            assert not quality.unapproved_number(f["text"]), key
            assert not factdesk.new_numbers(f["text"], f.get("numbers")), key


# ---- nothing anywhere states a known-false claim ----------------------------------------------------------------------

def _all_prompt_texts():
    out = []
    for k, f in fact_store.TABLE.items():
        out += [(k, f["text"]), (k, f["note"])]
    for k, f in content.FRAMES.items():
        out += [(k, f["angle"]), (k, f["gist"]), (k, f.get("heat") or "")] + [(k, s) for s in f["stakes"] + f["asks"]]
    out += [("rebuttal", line) for _, line, _ in content.REBUTTALS]
    out += [(k, s) for k, s, _ in content.STORYLINES + [content.STORYLINE_FALLBACK]]
    out += [(k, v) for k, v in content.LEVERS.items()] + [("world", content.WORLD)]
    out += [(f"theme {k}", x) for k, t in craft.THEMES.items()
            for x in [t["belief"], t["slogan"]] + t["echo"] + list(t.get("echo_speaker") or [])]
    for key, c in characters.CHARACTERS.items():
        for field in content.CHARACTER_FIELDS:
            v = c.get(field)
            out += [(key, x) for x in (v if isinstance(v, list) else [v]) if isinstance(x, str)]
    out += [(p["key"], d) for p in content.PERSONAS for d in p["details"]]
    out += [("rules", t) for t in (content.JAB_RULE, content.JAB_FIRST_LOT, content.JAB_RULE_PAUSED,
                                   content.EXEMPT_NOTE)]
    return out


def test_false_claims_catch_what_they_should():
    rx = fact_store.FALSE_CLAIMS
    for t in ("There are no cases of H2D2 here.", "Zero cases in Kingstonia so far", "H2D2 hasn't even arrived here",
              "the virus isn't here yet", "No confirmed cases on the island."):
        assert rx.search(t), t
    for t in ("one case, a traveller in isolation; no community spread yet", "the jab hasn't arrived yet",
              "in most cases people recover", "Not here yet. Not this far."):
        assert not rx.search(t), t


def test_nothing_states_a_false_claim():
    for where, text in _all_prompt_texts():          # an instruction against the claim ("never say ...") is fine
        assert not fact_store.FALSE_CLAIMS.search(re.sub(r"never say[^.;)]*", "", text, flags=re.I)), (where, text)


# ---- requires and says agree ------------------------------------------------------------------------------------------

def _requiring():
    """(where, text, the facts it says it requires) for every structure with a requires list."""
    out = []
    for k, f in content.FRAMES.items():
        for t in [f["angle"], f["gist"], f.get("heat") or ""] + f["stakes"] + f["asks"]:
            out.append((k, t, f["requires"]))
    out += [("rebuttal", line, req) for _, line, req in content.REBUTTALS]
    out += [(k, s, req) for k, s, req in content.STORYLINES + [content.STORYLINE_FALLBACK]]
    out += [(k, v, content.LEVER_REQUIRES.get(k, [])) for k, v in content.LEVERS.items()]
    out += [("world", t, req) for t, req, _ in content.WORLD_PARTS]
    out += [("world (paused)", instead, []) for _, _, instead in content.WORLD_PARTS]
    out += [(f"theme {k}", x, t["requires"]) for k, t in craft.THEMES.items()
            for x in [t["belief"], t["slogan"]] + t["echo"] + list(t.get("echo_speaker") or [])]
    out += [("exempt", content.EXEMPT_NOTE, content.EXEMPT_REQUIRES), ("jab", content.JAB_RULE, ["first_doses"]),
            ("jab", content.JAB_FIRST_LOT, ["first_doses"]), ("jab (paused)", content.JAB_RULE_PAUSED, [])]
    return out


def test_text_that_states_a_fact_requires_it():
    """If a fact's `says` wording appears in a frame, rebuttal, storyline, lever or rule, that structure must list
    the fact in `requires`, or pausing the fact would leave the claim in the prompts."""
    for where, text, req in _requiring():
        for key, rx in fact_store.SAYS.items():
            if rx.search(text):
                assert key in req, f"{where} states {key} ({rx.search(text).group(0)!r}) without requiring it: {text}"


# ---- pauses ---------------------------------------------------------------------------------------------------------

TARGET = NEUTRAL + " Exemptions? The hospital, covid, act now."      # triggers the exemption note and rebuttals


def _prompts(persona, frame, seed):
    """Every prompt kind, with the neighbour's own words masked (theirs, not a claim of ours)."""
    random.seed(seed)
    out = [content.system_prompt(persona, frame), content.post_prompt(frame, persona=persona),
           content.post_prompt(frame, headline="Ferry cut", persona=persona),
           content.reply_prompt(TARGET, frame, [], persona=persona),
           content.second_voice_prompt(TARGET, frame, [], persona=persona),
           content.journalist_prompt(3, NEUTRAL, persona=persona)]
    fx = dict(colour=True, spent=(), history=(0, []), register=None)        # todo/50: the fixes block and the lean prompt
    out += [content.system_prompt(persona, frame, fixes=fx, mode="reply"),
            content.reply_prompt(TARGET, frame, [], persona=persona, fixes=fx),
            content.reply_prompt(TARGET, frame, [], persona=persona, fixes=fx, read=True, hint=frame),
            content.lean_system_prompt(persona, frame, fixes=fx),
            content.lean_reply_prompt(TARGET, frame, [], persona=persona, fixes=fx),
            content.lean_reply_prompt(TARGET, frame, [], persona=persona, fixes=fx, read=True, hint=frame)]
    for key, t in themes.live().items():                 # a theme whose fact is paused is not live
        for level in ("implicit", "echo", "attributed", "verbatim"):
            theme = dict(key=key, level=level, belief=t["belief"], echo=t["echo"][0], position="middle",
                         slogan=t["slogan"] if level == "verbatim" else None)
            out.append(content.post_prompt(frame, persona=persona, theme=theme))
    return [p.replace(TARGET, "").replace(NEUTRAL, "") for p in out]


@pytest.mark.slow
@pytest.mark.parametrize("key", list(fact_store.TABLE))
def test_a_paused_fact_reaches_no_prompt(pause, key):
    """Every persona x every live frame, several draws: neither the fact nor its wording is in any prompt."""
    pause(key)
    assert key not in content.FACTS and key not in content.FACT_NOTES
    live = content.live_frames()
    assert len(live) >= 4, f"pausing {key} leaves only {live}"
    rx, text, note = fact_store.SAYS.get(key), fact_store.TABLE[key]["text"], fact_store.TABLE[key]["note"]
    for p in content.PERSONAS:
        for f in live:
            for seed in range(3):
                for prompt in _prompts(p, f, seed):
                    assert text not in prompt and note not in prompt, (key, p["key"], f)
                    hit = rx.search(prompt) if rx else None
                    assert not hit, (key, p["key"], f, hit and hit.group(0), prompt)


def test_file_status_paused_works_like_a_runtime_pause(monkeypatch):
    monkeypatch.setitem(fact_store.TABLE, "no_spread", dict(fact_store.TABLE["no_spread"], status="paused"))
    fact_store.refresh(force=True)
    try:
        assert "no_spread" not in content.FACTS and fact_store.PAUSED["no_spread"] == "file"
        assert "F5_not_here_yet" not in content.live_frames()
    finally:
        monkeypatch.undo()
        fact_store.refresh(force=True)
    assert "no_spread" in content.FACTS


def test_every_frame_paused_is_a_named_error(pause):
    pause(*fact_store.TABLE)
    with pytest.raises(content.AllPaused):
        content.pick_frame(content.PERSONAS[0])


def test_no_pause_means_everything_is_live():
    retired = [k for k in content.FRAMES if content.frame_scale(k) <= 0]       # config.FRAME_SCALE 0 (todo/59, 31 Oct)
    assert retired == ["F5_not_here_yet"]
    assert not fact_store.pauses() and content.live_frames() == [k for k in content.FRAMES if k not in retired]
    assert set(fact_store.PAUSED) == {k for k, f in fact_store.TABLE.items() if f["status"] != "active"}
    assert content.world() == content.WORLD and content.live_levers() == list(content.LEVERS)


def test_a_pause_holds_until_the_fact_is_rechecked():
    rec = {"since": "2026-10-21T10:00:00Z"}
    table = {"x": {"checked": dt.date(2026, 10, 21)}}
    assert fact_store.holds("x", rec, table)                       # a date is its midnight: older than the pause
    table["x"]["checked"] = dt.datetime(2026, 10, 21, 11, 0, tzinfo=dt.timezone.utc)
    assert not fact_store.holds("x", rec, table)                   # re-checked after it: the pause is over
    assert fact_store.holds("x", {}, {"x": {"checked": dt.date(2030, 1, 1)}})   # no since: holds until removed
    assert not fact_store.holds("gone", rec, table)


def test_an_unreadable_pause_file_keeps_the_last_pauses(pause, capsys):
    pause("no_spread")
    fact_store.PAUSED_FILE.write_text("{not json")
    assert fact_store.refresh() is False
    assert "no_spread" in fact_store.PAUSED and "unreadable" in capsys.readouterr().out


def test_routing_skips_a_paused_frame(pause):
    pause("no_spread")
    ben, ruth = content.PERSONA_BY_KEY["ben"], content.PERSONA_BY_KEY["ruth"]
    random.seed(1)
    assert "F5_not_here_yet" not in {content.pick_frame(p) for p in (ben, ruth) for _ in range(300)}
    assert content.live_frame("F5_not_here_yet", ben) in {"F1_blank_cheque", "F12_open_island"}
    assert content.live_frame("F1_blank_cheque", ben) == "F1_blank_cheque"
    overreach = "Isn't a pass at every single shop too far? I'm not sure."
    assert targeting.classify(overreach)[0] != "F5_not_here_yet"
    assert content.rebuttal_for("I remember covid, so many died")   # the COVID rebuttal no longer states no_spread


def test_a_retired_frame_is_never_picked_offered_or_classified():
    """todo/59 (31 Oct): F5_not_here_yet is retired (FRAME_SCALE 0) with every fact live, everywhere a frame comes from."""
    assert not fact_store.pauses() and content.frame_scale("F5_not_here_yet") == 0
    ben, ruth = content.PERSONA_BY_KEY["ben"], content.PERSONA_BY_KEY["ruth"]
    random.seed(2)
    assert "F5_not_here_yet" not in {content.pick_frame(p) for p in content.PERSONAS for _ in range(40)}
    assert content.live_frame("F5_not_here_yet", ben) in {"F1_blank_cheque", "F12_open_island"}
    assert "F5_not_here_yet" not in content.frame_menu()[1]              # the light read's list
    assert "F5_not_here_yet" not in content.read_block()
    assert targeting.classify("Isn't a pass at every single shop too far? Total overreach.")[0] != "F5_not_here_yet"
    for p in content.PERSONAS:                                          # every persona keeps a live home frame or a fallback
        assert content.live_frame(None, p) in content.live_frames()
    assert len(content.live_frames()) >= 4                              # the paused-fact sweep needs at least 4
    assert content.live_frame("F5_not_here_yet", ruth) in content.live_frames()


def test_world_jab_rule_and_storylines_follow_pauses(pause):
    pause("polls", "first_doses", "free_either_way")
    w = content.world()
    assert "polls are level" not in w and "either way" not in w and w.endswith("did to the hospitals.")
    s = content.system_prompt(content.PERSONA_BY_KEY["ana"], "F10_staff_and_livelihoods")
    assert content.JAB_RULE_PAUSED in s and content.JAB_RULE not in s and content.JAB_FIRST_LOT not in s
    assert "status_quo" not in content.live_levers() and "fear_answer" not in content.live_levers()
    keys = set()
    for _ in range(12):
        meta = {}
        content.journalist_prompt(3, NEUTRAL, meta=meta)
        keys.add(meta["storyline"])
    assert "vaxxed_no" not in keys and keys


def test_the_gate_rejects_paused_wording_and_false_claims(pause):
    post = ("Ben here, selling tuna at the New Haven market. There's no community spread on the island, and they "
            "want a pass at my stall. I'm voting No. Who on your street sells at the market?")
    assert quality.check(post, "post")[1] != "paused_fact_no_spread"
    pause("no_spread")
    assert quality.check(post, "post")[1] == "paused_fact_no_spread"
    false = post.replace("There's no community spread on the island", "There are no cases on the island")
    assert quality.check(false, "post")[1] == "false_claim"


def test_an_auto_accepted_fact_reaches_a_frame_prompt_without_a_restart(tmp_path, monkeypatch):
    """The desk writes its overlay mid-run; the next refresh() re-reads the table, content.sync_frames joins the fact
    to its frame, and the frame's system prompt can state it, newest first (2026-10-22: no restart on a facts change)."""
    import datetime as dt
    overlay = tmp_path / "facts_auto.toml"
    monkeypatch.setattr(fact_store, "AUTO_FILE", overlay)
    try:
        fact_store.refresh()
        assert "harbour_clinic_hours" not in content.FRAMES["F2_no_end"]["facts"]
        now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        overlay.write_text(
            '[harbour_clinic_hours]\ntext = "The Crown Harbour clinic now opens on Saturdays for H2D2 doses."\n'
            'note = "Crown Harbour clinic opens Saturdays"\nstatus = "active"\n'
            'source = "daily-kingstonia/clinic-saturday-hours"\n'
            f'checked = {now}\nadded = {now}\nnumbers = ["37"]\nsays = []\nframes = ["F2_no_end"]\n')
        from swan_bot import quality
        assert quality.unapproved_number("the clinic takes 37 a day") == "37"
        fact_store.refresh()
        assert quality.unapproved_number("the clinic takes 37 a day") is None     # the gate learns its figures too
        assert "harbour_clinic_hours" in content.FRAMES["F2_no_end"]["facts"]
        assert fact_store.active(content.FRAMES["F2_no_end"]["facts"])[0] == "harbour_clinic_hours"
        system = content.system_prompt(content.PERSONAS[0], "F2_no_end")
        assert "Crown Harbour clinic opens Saturdays" in system
    finally:
        monkeypatch.undo()
        fact_store.refresh(force=True)
        assert "harbour_clinic_hours" not in content.FRAMES["F2_no_end"]["facts"]


def test_the_nurses_note_keeps_the_cause():
    """2026-10-24: a draft read "pay about double in Australia or NZ" as "nobody's coming back from Australia". The
    note says nurses LEAVE for Australia/NZ, which is why the posts are empty."""
    note = fact_store.NOTES["nurses"]
    assert "because nurses leave for Australia or NZ" in note and "double" in note
