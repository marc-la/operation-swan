"""scripts/convert_boosters.py and bot.persona_of: boosters turned voices on a suspended voice's card (no network)."""
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from swan_bot import bot, config, content, stealth  # noqa: E402

spec = importlib.util.spec_from_file_location("convert_boosters", ROOT / "scripts" / "convert_boosters.py")
cb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cb)


def records():
    return [dict(role="booster", username="rep", display_name="Rep", account_id=1, status="active", persona=None),
            dict(role="booster", username="owen_bakes", display_name="Owen Faleafa", account_id=5, status="active",
                 persona=None, owner="marc"),
            dict(role="booster", username="ivy76", display_name="Ivy F.", account_id=6, status="active", persona=None),
            dict(username="wally_old", persona="wally", account_id=3, status="suspended"),
            dict(username="kai_live", persona="kai", account_id=4, status="active")]


def converted(username="owen_bakes", key="wally", style="mere"):
    recs = records()
    ok, _ = cb.plan(recs, 10, [(username, key, style)])
    cb.convert(recs, ok, "marc", now="2026-10-22T11:00:00+00:00")
    return next(r for r in recs if r["username"] == username)


def test_plan_skips_the_reporter_held_cards_borrowed_styles_and_missing_accounts():
    pairs = [("rep", "dan", "ben"), ("owen_bakes", "wally", "mere"), ("ivy76", "kai", "ben"),
             ("ghost", "priya", "ben")]
    ok, skipped = cb.plan(records(), 10, pairs)
    assert [(r["username"], k, s) for r, k, s in ok] == [("owen_bakes", "wally", "mere")]
    assert dict(skipped) == {"rep": "Blue's reporter", "ivy76": "card held by an active voice",
                             "ghost": "no such account"}
    _, skipped = cb.plan(records(), 10, [("ivy76", "priya", "kai"), ("owen_bakes", "wally", "wally")])
    assert dict(skipped) == {"ivy76": "style of an active voice", "owen_bakes": "style is the card's own"}


def test_plan_stops_at_n_and_never_gives_one_card_twice():
    pairs = [("owen_bakes", "wally", "mere"), ("ivy76", "wally", "ben")]
    ok, skipped = cb.plan(records(), 10, pairs)
    assert len(ok) == 1 and dict(skipped) == {"ivy76": "card held by an active voice"}
    ok, skipped = cb.plan(records(), 0, pairs[:1])
    assert ok == [] and dict(skipped) == {"owen_bakes": "enough"}


def test_convert_makes_a_voice_that_keeps_its_name_and_owner_and_logs_who():
    recs = records()
    ok, _ = cb.plan(recs, 10, [("owen_bakes", "wally", "mere")])
    lines = cb.convert(recs, ok, "marc", now="2026-10-22T11:00:00+00:00")
    rec = recs[1]
    assert rec["role"] == "voice" and rec["persona"] == "wally" and rec["owner"] == "marc"
    assert rec["converted"] == dict(at="2026-10-22T11:00:00+00:00", by="marc", from_role="booster",
                                    card_of="wally_old", style_of="mere")
    assert lines[0]["act"] == "convert" and lines[0]["username"] == "owen_bakes" and lines[0]["by"] == "marc"


def test_a_converted_voice_drops_the_old_voices_people_lines_and_style():
    card, mere = content.PERSONA_BY_KEY["wally"], content.PERSONA_BY_KEY["mere"]
    p = bot.persona_of(converted())
    assert p["name"] == "Owen Faleafa" and p["role"] == card["role"] and p["frames"] == card["frames"]
    assert p["voice"] == mere["voice"] and p["hand"] == "mere" and p["voice"] != card["voice"]
    assert p["people"] == [] and p["lines"] == [] and p["now"] == [] and p["arc"] is None
    flat = " ".join(p["details"] + [p.get("covid") or "", p.get("problem") or ""])
    for who in ("Unaisi", "Elenoa", "Hector", "Noeline"):
        assert who not in flat
    assert card["name"] == "Wally Koroi" and card["people"]                     # the card itself is untouched


def test_an_original_voice_drafts_under_its_card():
    assert bot.persona_of(dict(persona="kai", display_name="whatever")) is content.PERSONA_BY_KEY["kai"]


def test_a_converted_voice_sleeps_its_own_hours_and_keeps_the_caps(monkeypatch):
    rec = converted()
    assert stealth.key_of(rec) == "owen_bakes" and stealth.key_of(dict(persona="wally", username="x")) == "wally"
    monkeypatch.setattr(config, "VOICE_SLEEP", False, raising=False)
    t = 1_800_000_000.0
    rec["day_writes"] = [t - 60 * i for i in range(config.VOICE_WRITES_PER_H)]
    assert stealth.rest(rec, t) == "voice_capped"


def test_the_plan_names_real_cards_once_each_and_never_their_own_style():
    keys = [k for _, k, _ in cb.PLAN]
    styles = [s for _, _, s in cb.PLAN]
    assert len(set(keys)) == len(keys) and set(keys) | set(styles) <= set(content.PERSONA_BY_KEY)
    assert all(k != s for _, k, s in cb.PLAN) and len(set(styles)) == len(styles)
    assert not {"mere", "paulo", "ben"} & set(keys)


def test_a_converted_voices_prompt_names_it_and_none_of_the_old_voices_people():
    import types
    for mode in ("reply", "post"):
        for _ in range(20):
            job = dict(mode=mode, rec=converted(), frame=None, wants=[], context=None,
                       target=dict(post_id=5, author_id=500, body="Not sure how I'll vote on the referendum yet."))
            _, system, user = bot.build_prompt(job, types.SimpleNamespace(headline=None))
            text = system + user
            assert "Owen Faleafa" in text and "Wally" not in text
            for who in ("Unaisi", "Elenoa", "Hector", "Noeline"):
                assert who not in text
