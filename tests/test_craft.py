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
    for t in craft.THEMES.values():
        yield t["belief"]
        yield t["slogan"]
        yield from t["echo"] + list(t.get("echo_speaker") or [])
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


def test_pillar_fields():
    for key, p in craft.PILLARS.items():
        assert p["name"] and p["claim"], key


def test_theme_fields():
    """Playbook §3: five themes, each a short slogan on a belief, carried by real personas on frames that exist."""
    assert len(craft.THEMES) == 5
    personas = set(content.PERSONA_BY_KEY)
    slogans = [t["slogan"].lower() for t in craft.THEMES.values()]
    assert len(slogans) == len(set(slogans))
    for key, t in craft.THEMES.items():
        assert t["belief"].strip() and t["echo"], key
        assert 2 <= len(t["slogan"].split()) <= 5, t["slogan"]       # punch: 2-5 words
        assert t["personas"] is None or set(t["personas"]) <= personas, key
        assert t["verbatim"] is None or set(t["verbatim"]) <= set(t["personas"] or personas), key
        assert t["frames"] is None or set(t["frames"]) <= set(content.FRAMES), key
        assert set(t["requires"]) <= set(content.fact_store.TABLE), key
        assert re.search(t["marks"], t["slogan"], re.I), key           # the key words are in the slogan
        assert t["weight"] > 0, key
    assert craft.THEMES["own_party"]["verbatim"] == ["josh"]          # only Josh voted Hawthorne


def test_no_jabbed_claims_in_themes():
    """The jab isn't out until the last week of October: no theme text says anyone has had it."""
    for t in craft.THEMES.values():
        for text in [t["belief"], t["slogan"]] + t["echo"] + list(t.get("echo_speaker") or []):
            said = re.sub(r"\bnever [^.;)]*", "", text, flags=re.I)            # an instruction against it is fine
            assert not re.search(r"\bjabbed\b|\b(had|got) (the|my|our|their) (jab|dose)", said, re.I), text


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
