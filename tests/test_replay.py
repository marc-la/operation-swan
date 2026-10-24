"""Replay metrics (src/swan_bot/replay.py): pure scoring of drafted replies, no network."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from swan_bot import replay  # noqa: E402

ASK = "Tight safeguards and a sunset date written in would change my mind."


def test_one_flags_the_motifs_the_openers_and_the_unanswered_ask():
    f = replay.one("You want a sunset, yet a pass at my bakery door - papers at half past four - adds no nurse.", ASK, "F14_no_yes_but")
    assert f["motif_door"] and f["motif_bakery"] and f["motif_papers"] and f["motif_half_four"] and f["motif_spaced_dash"]
    assert f["echo_open"] and f["has_condition"] and f["answers_condition"] and f["f14"] and not f["question"]
    g = replay.one("They're choosing the places after. Who in your street checks?", ASK, "F10_staff_and_livelihoods")
    assert g["bare_they"] and g["motif_who_in_your"] and g["question"] and not g["answers_condition"] and not g["f14"]
    assert replay.one("You're right that the wards are stretched.", "x", None)["concedes"]
    assert replay.one("Those are good things to want, but the ballot is silent.", "x", None)["concedes"]


def test_score_shares_and_stream_clash():
    items = [dict(reply="A pass at my bakery door adds no nurse and no bed at all.", target_text=ASK, frame="F10_x"),
             dict(reply="A pass at my bakery door adds no nurse and no bed at all, mate.", target_text=ASK, frame="F10_x"),
             dict(reply="The question names no end date, so the sunset you want is not in it.", target_text=ASK, frame="F14_no_yes_but")]
    s = replay.score(items)
    assert s["n"] == 3 and s["motif_door"] == 2 / 3 and s["asked_n"] == 3
    assert s["asks_answered"] == 1 / 3 and s["f14_when_asked"] == 1 / 3
    assert s["clash"] > 0.2 and s["distinct_open"] < 1
    fresh = replay.score(items, window=[items[0]["reply"]])["clash"]
    assert fresh > s["clash"]                                   # the window of real texts counts as "said before"


def test_compare_marks_the_better_direction():
    a = {"n": 10, "motif_door": 0.5, "distinct_open": 0.5, "asks_answered": None}
    b = {"n": 10, "motif_door": 0.2, "distinct_open": 0.8, "asks_answered": None}
    out = replay.compare(a, b, ("old", "new"))
    assert "-30 pt -" in out.replace("  ", " ").replace("  ", " ") or "-30 pt" in out
    assert "n/a" in out and replay.score([]) == {"n": 0}
