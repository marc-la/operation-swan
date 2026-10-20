"""Craft data (playbook/craft.py): shape, counts and content rules from the message playbook §2-5 (no network)."""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from swan_bot import content  # noqa: E402
from swan_bot.playbook import craft  # noqa: E402

PILLAR_FRAMES = {
    "A": {"F14_no_yes_but", "F1_blank_cheque", "F2_no_end", "F9_parliament", "F8_powers"},
    "B": {"F7_livelihoods", "F13_age12", "F6_islands", "F10_staff_and_livelihoods", "F12_open_island"},
    "C": {"F3_provax_antipass", "F5_not_here_yet"},
}
DEAD = ["venue list", "designated", "regulation", "review point", "ballot question", "safeguard", "as written",
        "as it stands", "binding", "hospitals stretched", "exemptions are covered", "i hear you", "i'd want that too",
        "fair point", "blank page", "sensible", "just feels wrong"]
BANNED = ["tyranny", "sheep", "wake up", "sinister", "side effect", "side-effect", "injur", "experimental", "rushed",
          "long-term effect", "unsafe", "can we really", "how can anyone", "do we really want", "isn't it time"]


def all_text():
    for p in craft.PILLARS.values():
        yield p["name"]
        yield p["claim"]
        yield from p["catchphrases"]
    for c in craft.CRAFT.values():
        yield from c["stakes"]
        yield c["heat"]
        yield from c["asks"]


def test_every_frame_has_craft():
    assert set(craft.CRAFT) == set(content.FRAMES)


def test_frames_per_pillar_match_contract():
    assert set(craft.PILLARS) == set(PILLAR_FRAMES)
    for key, c in craft.CRAFT.items():
        assert c["pillar"] in craft.PILLARS, key
    got = {p: {k for k, c in craft.CRAFT.items() if c["pillar"] == p} for p in craft.PILLARS}
    assert got == PILLAR_FRAMES


def test_frame_fields():
    for key, c in craft.CRAFT.items():
        assert 2 <= len(c["stakes"]) <= 3, key
        assert all(isinstance(s, str) and s.strip() for s in c["stakes"]), key
        assert isinstance(c["heat"], str) and c["heat"].strip(), key
        assert 2 <= len(c["asks"]) <= 4, key
        assert all(a.strip().endswith("?") for a in c["asks"]), key


def test_stakes_not_repeated_across_frames():
    stakes = [s.lower() for c in craft.CRAFT.values() for s in c["stakes"]]
    assert len(stakes) == len(set(stakes))


def test_pillar_fields_and_catchphrases():
    for key, p in craft.PILLARS.items():
        assert p["name"] and p["claim"], key
        assert 5 <= len(p["catchphrases"]) <= 8, key
        for cp in p["catchphrases"]:
            assert len(cp.split()) <= 7, cp
            assert "#" not in cp, cp
    phrases = [cp.lower() for p in craft.PILLARS.values() for cp in p["catchphrases"]]
    assert len(phrases) == len(set(phrases))
    assert 0 < craft.CATCHPHRASE_SHARE <= 0.34


def test_tags_in_allowlist():
    assert all(t == t.lower() and t.startswith("#") and " " not in t for t in craft.TAG_ALLOWLIST)
    for key, p in craft.PILLARS.items():
        assert p["tags"], key
        assert all(t.lower() in craft.TAG_ALLOWLIST for t in p["tags"]), key


def test_no_dead_words_or_banned_content():
    for text in all_text():
        low = text.lower().replace("’", "'")
        for w in DEAD + BANNED:
            assert w not in low, (w, text)
        assert "#" not in text, text


def test_no_stale_dates_or_logistics():
    for text in all_text():
        assert not re.search(r"\blast week\b|\bnext week\b|\byesterday\b|\btomorrow\b", text, re.I), text
        assert not re.search(r"\b(2|28) Nov|\b28 Oct|polling|early voting|polls (open|close)", text, re.I), text


def test_pure_data_module():
    src = pathlib.Path(craft.__file__).read_text()
    assert not re.search(r"^\s*(from|import)\s+\S*(content|quality)\b", src, re.M)
