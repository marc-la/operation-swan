"""Who we reply to: skip citizens who already lean No (echo), keep the Yes-but. Texts are real citizen posts, 20 Oct."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from swan_bot import targeting  # noqa: E402

LEAN_NO = [
    "Leaning No at the moment. I'd be more comfortable with a narrow venue list, testing options and a real sunset clause.",
    "My No vote is settled, and I'm vaccinated. Is there a review date anywhere?",
    "exactly. once they set the precedent of checking papers at every door, it's a slippery slope for all kinda data sharing.",
    "Why should my day be gated by a vaccine I don't trust? Protect the hospitals, fix the system, not bar people from daily life.",
]
YES_BUT = [
    "I'm leaning Yes because we can't risk the hospitals being hit like they were during COVID, but they need to say "
    "which public spaces are on the list.",
    "Totally get your concern. If we vote Yes, there must be a published list of designated spaces, a clear expiry, "
    "and an independent review.",
    "I want H2D2 vaccination to protect people, especially the vulnerable, but I'm uneasy voting on a rule with venues "
    "and review dates still unclear.",
]


def test_lean_no_is_skipped():
    for text in LEAN_NO:
        assert targeting.classify(text) == (None, None), text


def test_yes_but_is_kept():
    for text in YES_BUT:
        assert targeting.classify(text)[0], text


def test_yes_reason_is_spotted():
    assert targeting.YES_REASON.search(YES_BUT[0]) and targeting.YES_REASON.search(YES_BUT[2])
    assert not targeting.YES_REASON.search(YES_BUT[1])
