"""scripts/convert_boosters.py and bot.persona_of: boosters turned voices on a suspended voice's card (no network)."""
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from swan_bot import bot, content  # noqa: E402

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


def test_plan_skips_the_reporter_held_cards_and_missing_accounts():
    pairs = [("rep", "dan"), ("owen_bakes", "wally"), ("ivy76", "kai"), ("ghost", "priya")]
    ok, skipped = cb.plan(records(), 10, pairs)
    assert [(r["username"], k) for r, k in ok] == [("owen_bakes", "wally")]
    assert dict(skipped) == {"rep": "Blue's reporter", "ivy76": "card held by an active voice",
                             "ghost": "no such account"}


def test_plan_stops_at_n_and_never_gives_one_card_twice():
    pairs = [("owen_bakes", "wally"), ("ivy76", "wally")]
    ok, skipped = cb.plan(records(), 10, pairs)
    assert len(ok) == 1 and dict(skipped) == {"ivy76": "card held by an active voice"}
    ok, skipped = cb.plan(records(), 0, pairs[:1])
    assert ok == [] and dict(skipped) == {"owen_bakes": "enough"}


def test_convert_makes_a_voice_that_keeps_its_name_and_owner():
    recs = records()
    ok, _ = cb.plan(recs, 10, [("owen_bakes", "wally")])
    lines = cb.convert(recs, ok, "marc", now="2026-10-22T11:00:00+00:00")
    rec = recs[1]
    assert rec["role"] == "voice" and rec["persona"] == "wally" and rec["owner"] == "marc"
    assert rec["converted"] == dict(at="2026-10-22T11:00:00+00:00", by="marc", from_role="booster",
                                    card_of="wally_old")
    assert lines[0]["act"] == "convert" and lines[0]["username"] == "owen_bakes" and lines[0]["by"] == "marc"
    p = bot.persona_of(rec)
    assert p["name"] == "Owen Faleafa" and p["role"] == content.PERSONA_BY_KEY["wally"]["role"]
    assert content.PERSONA_BY_KEY["wally"]["name"] == "Wally Koroi"          # the card itself is untouched


def test_an_original_voice_drafts_under_its_card_name():
    assert bot.persona_of(dict(persona="kai", display_name="whatever")) is content.PERSONA_BY_KEY["kai"]


def test_the_plan_names_real_cards_once_each():
    keys = [k for _, k in cb.PLAN]
    assert len(set(keys)) == len(keys) and set(keys) <= set(content.PERSONA_BY_KEY)
    assert not {"mere", "paulo", "ben"} & set(keys)
