"""The 12 staged base persona cards (playbook/new_cards.py, todo/36): the rules test_characters.py applies to the live
cards, plus the mix table and cross-checks from the todo. The cards are not promoted: none is in content.PERSONAS."""
import collections
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from swan_bot import content, humanize  # noqa: E402
from swan_bot.playbook import characters, new_cards  # noqa: E402
from swan_bot.playbook.new_cards import NEW_CARDS  # noqa: E402
from test_characters import (ALLOWED_NUMBERS, BANNED, COUNTS, HAWTHORNE_OK, PROFILE, REGISTERS,  # noqa: E402
                             _shingles)

CARD_TEXT = ("key", "name", "handle", "role", "place", "voice", "register")
PLACES = {"the outer islands", "New Haven", "Kingstonia City", "Crown Harbour"}
HAND_KEYS = {"device", "lower", "lower_start", "small_i", "apos", "comma", "amp", "dots", "two_space", "slip",
             "careful"}
LIVE_NAMES = {p["name"].split()[0].lower() for p in content.PERSONAS} | {"dan"}


def _cards():
    return [c["card"] for c in NEW_CARDS]


def _profiles():
    return [(c["card"]["key"], c["profile"]) for c in NEW_CARDS]


def _texts(c):
    p = c["profile"]
    return ([p["problem"], p["covid"], p.get("arc") or ""] + p["people"] + p["lines"] + p["now"]
            + [c["card"]["role"], c["card"]["voice"]] + c["card"]["details"])


def test_twelve_entries_with_three_parts():
    assert len(NEW_CARDS) == 12
    assert all(set(c) == {"card", "profile", "hand"} for c in NEW_CARDS)


def test_keys_names_handles_unique_and_new():
    for field in ("key", "name", "handle"):
        values = [c[field] for c in _cards()]
        assert len(set(values)) == 12, field
        assert not set(values) & {p[field] for p in content.PERSONAS}, field
    first = [c["name"].split()[0].lower() for c in _cards()]
    assert len(set(first)) == 12 and not set(first) & LIVE_NAMES
    for c in _cards():
        assert re.fullmatch(r"[a-z0-9_]{3,20}", c["key"]), c["key"]
        assert re.fullmatch(r"[a-z0-9_]{3,20}", c["handle"]), c["handle"]


def test_card_fields():
    for c in _cards():
        for field in CARD_TEXT:
            assert isinstance(c[field], str) and c[field].strip(), (c["key"], field)
        assert c["place"] in PLACES, c["key"]
        assert c["register"] in REGISTERS, c["key"]
        assert c["details"] and all(isinstance(d, str) and d.strip() for d in c["details"]), c["key"]
        assert 2 <= len(c["frames"]) <= 3 and set(c["frames"]) <= set(content.FRAMES), c["key"]


def test_profile_fields_and_counts():
    for key, p in _profiles():
        for field, typ in PROFILE.items():
            assert isinstance(p.get(field), typ), (key, field)
        assert p.get("arc") is None or (isinstance(p["arc"], str) and p["arc"].strip()), key
        assert 16 <= p["age"] <= 90, key
        for field, (lo, hi) in COUNTS.items():
            assert lo <= len(p[field]) <= hi, (key, field, len(p[field]))
            assert all(isinstance(s, str) and s.strip() for s in p[field]), (key, field)
        assert all(len(s.split()) <= 25 for s in p["lines"]), key


def test_people_named_and_not_shared():
    live = list(characters.CHARACTERS.items()) + [(c["key"], c) for c in characters.CANDIDATES]
    owner = {person.split(",")[0].strip(): key for key, p in live for person in p["people"]}
    persona_names = LIVE_NAMES | {c["name"].split()[0].lower() for c in _cards()}
    for key, p in _profiles():
        for person in p["people"]:
            name = person.split(",")[0].strip()
            assert name and name[0].isupper(), (key, person)
            assert not ({w.lower() for w in name.split()} & persona_names), (key, name)
            assert name not in owner, f"{name} in both {owner.get(name)} and {key}"
            owner[name] = key


TITLES = {"mr", "mrs", "ms", "dr", "uncle", "auntie", "old", "nurse", "the", "family"}


def test_person_name_words_not_shared_across_cards():
    """'Mr Penrose' must not sit beside another card's 'Mr Arthur Penrose': no name word (titles aside) is used by two
    cards, new or live."""
    live = list(characters.CHARACTERS.items()) + [(c["key"], c) for c in characters.CANDIDATES]
    used = {}
    for key, p in live:
        for person in p["people"]:
            for w in person.split(",")[0].lower().split():
                used.setdefault(w, key)
    for key, p in _profiles():
        mine = set()
        for person in p["people"]:
            mine |= {w for w in person.split(",")[0].lower().split() if w not in TITLES}
        for w in mine:
            assert used.get(w, key) == key, f"{w} is in {used[w]} and {key}"
        for w in mine:
            used.setdefault(w, key)


def test_content_rules():
    for c in NEW_CARDS:
        for t in _texts(c):
            hit = BANNED.search(HAWTHORNE_OK.sub("", t))
            assert not hit, (c["card"]["key"], hit.group(0), t)
            for num in re.findall(r"\d[\d,.]*\d|\d", t):
                assert num in ALLOWED_NUMBERS, (c["card"]["key"], num, t)


def test_lines_not_copied_from_facts_or_angles():
    source = " ".join([f["text"] for f in content.fact_store.TABLE.values()]
                      + [f["angle"] for f in content.FRAMES.values()])
    try:
        from swan_bot.playbook import craft
        source += " " + " ".join(t["slogan"] + " " + t["belief"] for t in craft.THEMES.values())
    except ImportError:
        pass
    src = _shingles(source)
    for key, p in _profiles():
        for line in p["lines"]:
            assert not (_shingles(line) & src), (key, line)


def test_mix_table():
    cards, ages = _cards(), [c["profile"]["age"] for c in NEW_CARDS]
    assert collections.Counter(c["place"] for c in cards) == {
        "the outer islands": 4, "New Haven": 3, "Kingstonia City": 3, "Crown Harbour": 2}
    assert sum(a < 30 for a in ages) == 3 and sum(a > 55 for a in ages) == 4 and sum(30 <= a <= 54 for a in ages) == 5
    assert collections.Counter(c["register"] for c in cards) == {"plain": 5, "fed_up": 4, "warm": 3}
    assert collections.Counter(c["hand"]["device"] for c in NEW_CARDS) == {"phone": 7, "laptop": 3, "tablet": 2}
    frames = collections.Counter(f for c in cards for f in c["frames"])
    for frame, least in {"F6_islands": 4, "F8_powers": 3, "F10_staff_and_livelihoods": 3, "F9_parliament": 3,
                         "F5_not_here_yet": 3, "F7_livelihoods": 3}.items():
        assert frames[frame] >= least, (frame, frames[frame])


def _shape(handle):
    head = handle.split("_")[0]
    return ("_" in handle, any(ch.isdigit() for ch in handle), len(handle) <= 6, "_" in handle and len(head) <= 3)


def test_handle_shapes_vary():
    handles = [c["handle"] for c in _cards()]
    assert len({_shape(h) for h in handles}) >= 4, handles
    # the live 20 are all firstname_surname-or-job: at most half of the new ones may be word_word
    assert sum(bool(re.fullmatch(r"[a-z]+_[a-z]+", h)) for h in handles) <= 6, handles


def test_hands():
    seen = []
    for c in NEW_CARDS:
        hand = c["hand"]
        assert set(hand) == HAND_KEYS, c["card"]["key"]
        assert hand["device"] in {"phone", "laptop", "tablet"}
        assert isinstance(hand["two_space"], bool)
        for k in HAND_KEYS - {"device", "two_space"}:
            assert 0 <= hand[k] <= 1, (c["card"]["key"], k)
        seen.append(tuple(sorted(hand.items())))
    assert len(set(seen)) == 12
    assert not set(seen) & {tuple(sorted(h.items())) for h in humanize.HANDS.values()}


def test_not_promoted_and_pure():
    keys = {c["key"] for c in _cards()}
    assert not keys & {p["key"] for p in content.PERSONAS}
    assert not keys & set(characters.CHARACTERS) and not keys & set(humanize.HANDS)
    src = pathlib.Path(new_cards.__file__).read_text()
    assert not re.search(r"^\s*(from|import)\s+.*\b(content|quality)\b", src, re.M)
