"""Character profiles (playbook/characters.py): schema, consistency with PERSONAS, and the content rules."""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from swan_bot import content, quality  # noqa: E402
from swan_bot.playbook import characters  # noqa: E402
from swan_bot.playbook.characters import CANDIDATES, CHARACTERS  # noqa: E402

PERSONA_KEYS = {p["key"] for p in content.PERSONAS}
PROFILE = dict(age=int, people=list, problem=str, covid=str, lines=list, now=list)
COUNTS = dict(people=(3, 5), lines=(3, 5), now=(5, 8))
REGISTERS = {"warm", "fed_up", "plain"}
# digits allowed in profile text: true in-game numbers only (the gate's own list, which includes every active fact's
# figures); everything else is written in words
ALLOWED_NUMBERS = quality.ALLOWED_NUMBERS | quality.ALLOWED_PERCENTS
BANNED = re.compile(r"side.?effect|safety|unsafe|injur|adverse|untested|experimental|too new|trial|"
                    r"tyrann|sheep|wake up|sinister|early voting|polling|ballot box|on the 2nd|2 Nov|"
                    r"Hawthorne|Castillo|Singh|Whitlock|Reyes-Hale|Brotherston|Abernathy", re.I)
# Hawthorne may be named only as the man someone voted for, never as an acquaintance
HAWTHORNE_OK = re.compile(r"voted (for )?Hawthorne|Hawthorne voter|Hawthorne's (own )?(party|people|government)", re.I)


def _profiles():
    return list(CHARACTERS.items()) + [(c["key"], c) for c in CANDIDATES]


def _texts(p):
    return [p["problem"], p["covid"], p.get("arc") or ""] + p["people"] + p["lines"] + p["now"]


def _shingles(text, n=7):
    words = re.findall(r"[a-z']+", text.lower())
    return {" ".join(words[i:i + n]) for i in range(max(0, len(words) - n + 1))}


def test_one_profile_per_persona():
    assert set(CHARACTERS) == PERSONA_KEYS and len(CHARACTERS) == 12


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
    owner = {}
    persona_names = {p["name"].split()[0].lower() for p in content.PERSONAS} | {"dan"}
    for key, p in _profiles():
        for person in p["people"]:
            name = person.split(",")[0].strip()
            assert name and name[0].isupper(), (key, person)
            assert not ({w.lower() for w in name.split()} & persona_names), (key, name)
            assert name not in owner, f"{name} in both {owner.get(name)} and {key}"
            owner[name] = key


def test_content_rules():
    for key, p in _profiles():
        for t in _texts(p):
            hit = BANNED.search(HAWTHORNE_OK.sub("", t))
            assert not hit, (key, hit.group(0), t)
            for num in re.findall(r"\d[\d,.]*\d|\d", t.replace("Year 8", "")):  # Year 8: grace's own detail
                assert num in ALLOWED_NUMBERS, (key, num, t)


def test_lines_not_copied_from_facts_or_angles():
    source = " ".join([f["text"] for f in content.fact_store.TABLE.values()] + [f["angle"] for f in content.FRAMES.values()])
    try:
        from swan_bot.playbook import craft
        source += " " + " ".join(c for pl in craft.PILLARS.values() for c in pl["catchphrases"])
    except ImportError:
        pass
    src = _shingles(source)
    for key, p in _profiles():
        for line in p["lines"]:
            assert not (_shingles(line) & src), (key, line)


def test_candidates_are_new_and_valid():
    assert len(CANDIDATES) == 3
    handles = {p["handle"] for p in content.PERSONAS}
    names = {p["name"] for p in content.PERSONAS}
    keys = [c["key"] for c in CANDIDATES]
    assert len(set(keys)) == 3 and not set(keys) & PERSONA_KEYS
    for c in CANDIDATES:
        assert re.fullmatch(r"[a-z0-9_]{3,20}", c["handle"]) and c["handle"] not in handles, c["handle"]
        assert c["name"] not in names
        for field in ("name", "role", "place", "voice"):
            assert isinstance(c[field], str) and c[field].strip(), (c["key"], field)
        assert c["details"] and all(isinstance(d, str) for d in c["details"])
        assert c["frames"] and set(c["frames"]) <= set(content.FRAMES), c["frames"]
        assert c["register"] in REGISTERS
    assert len({c["handle"] for c in CANDIDATES}) == 3


def test_data_module_stays_pure():
    src = pathlib.Path(characters.__file__).read_text()
    assert not re.search(r"^\s*(from|import)\s+.*\b(content|quality)\b", src, re.M)
