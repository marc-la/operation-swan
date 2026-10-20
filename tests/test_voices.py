"""Voices (playbook §6): three registers, their shares, the persona assignment and the gold examples (no network)."""
import ast
import math
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from swan_bot import content  # noqa: E402
from swan_bot.playbook import voices  # noqa: E402

V = voices.VOICES
# Never in an instruction: conspiracy words (playbook §6) and dead words the model would copy (playbook §3).
BANNED = ["tyranny", "sheep", "wake up", "sinister", "agenda", "plandemic", "big pharma", "puppet",
          "venue list", "designated", "regulation", "review point", "ballot question", "safeguards", "as written",
          "as it stands", "binding", "hospitals stretched", "i hear you", "i'd want that too", "fair point",
          "sensible", "just feels wrong", "cheerful and reasonable", "never angry"]
# Never in a gold example either (the conspiracy words plus vaccine safety and the dead civics words).
EXAMPLE_BANNED = ["tyranny", "sheep", "wake up", "sinister", "agenda", "plandemic", "big pharma", "puppet",
                  "side effect", "unsafe", "untested", "experimental", "injur", "venue list", "designated",
                  "regulation", "ballot question", "safeguards", "as written", "as it stands", "binding",
                  "i hear you", "i'd want that too", "fair point", "castillo", "kitb", "resort"]
TAGS = {"#voteno", "#h2d2no", "#keepkingstoniaopen", "#smallbusiness", "#workersrights", "#choicenotcoercion",
        "#protectkingstonia"}


def test_three_voices_and_shares():
    assert set(V) == {"warm", "fed_up", "plain"}
    assert math.isclose(sum(v["share"] for v in V.values()), 1.0)
    assert (V["warm"]["share"], V["fed_up"]["share"], V["plain"]["share"]) == (0.60, 0.25, 0.15)


def test_voice_of_covers_every_persona():
    assert set(voices.VOICE_OF) == {p["key"] for p in content.PERSONAS}
    assert set(voices.VOICE_OF.values()) <= set(V)
    assert {v for v in voices.VOICE_OF.values()} == set(V)  # every voice has at least one messenger


def test_instructions_are_clean():
    for name, v in V.items():
        for field, lo, hi in (("instruction", 60, 130), ("reply_instruction", 30, 70)):
            text = v[field]
            words = len(text.split())
            assert lo <= words <= hi, (name, field, words)
            low = text.lower()
            assert not [w for w in BANNED if w in low], (name, field, [w for w in BANNED if w in low])
            assert not re.search(r"[\"“”]|'[A-Z][^']{3,}'", text), (name, field, "quoted text the model could copy")
            assert not re.search(r"\d", text), (name, field, "numbers belong in the facts, not the voice")
            assert "#" not in text and "http" not in low, (name, field)
            assert text.startswith("You "), (name, field, "second person")


def test_voices_are_distinct():
    def words(t):
        return set(re.findall(r"[a-z']+", t.lower())) - {"you", "your", "the", "a", "and", "of", "to", "it", "or", "not",
                                                          "in", "is", "for", "on", "at", "no", "never", "one", "with"}
    names = list(V)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            wa, wb = words(V[a]["instruction"]), words(V[b]["instruction"])
            assert len(wa & wb) / len(wa | wb) < 0.4, (a, b)


def test_examples_follow_the_anatomy():
    seen = 0
    for name, v in V.items():
        exs = v.get("examples", [])
        assert 2 <= len(exs) <= 3, name
        authors = [e["persona"] for e in exs]
        assert len(set(authors)) == len(authors), (name, "one example per persona")
        for e in exs:
            assert voices.VOICE_OF[e["persona"]] == name, (name, e["persona"])
            assert e["frame"] in content.FRAMES, e["frame"]
            text = e["text"]
            assert 240 <= len(text) <= 460, (e["persona"], len(text))
            assert "voting No" in text, e["persona"]
            tags = re.findall(r"#\w+", text)
            assert len(tags) <= 1 and all(t.lower() in TAGS for t in tags), (e["persona"], tags)
            body = re.sub(r"\s*#\w+\s*$", "", text).rstrip()
            assert body.endswith("?"), (e["persona"], "ends with a question before the tag")
            assert "#" not in body, (e["persona"], "tag only at the end")
            low = text.lower()
            assert not [w for w in EXAMPLE_BANNED if w in low], (e["persona"], [w for w in EXAMPLE_BANNED if w in low])
            seen += 1
    assert seen >= 6


def test_only_health_workers_have_the_jab():
    """The first H2D2 doses land in late October for health workers and the high-risk: nobody else has had it yet."""
    health = {"ana", "sione", "ruth", "priya"}
    had = re.compile(r"\bI'm (jabbed|vaccinated)\b|\bI've had (my|the) (jab|shot|dose|H2D2)|^Jabbed\b", re.I | re.M)
    for v in V.values():
        for e in v.get("examples", []):
            if e["persona"] not in health:
                assert not had.search(e["text"]), e["persona"]


def test_examples_never_reach_the_instructions():
    """Gold posts are for tests and review only: no run of 6+ words from an example appears in any instruction."""
    def runs(t, n=6):
        w = re.findall(r"[a-z0-9']+", t.lower())
        return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}
    prompts = " | ".join(v["instruction"] + " | " + v["reply_instruction"] for v in V.values())
    for v in V.values():
        for e in v.get("examples", []):
            assert not runs(e["text"]) & runs(prompts), e["persona"]


def test_pure_data_module():
    """voices.py must not import content.py or quality.py (they import it)."""
    tree = ast.parse(pathlib.Path(voices.__file__).read_text())
    names = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not ({"content", "quality"} & (names | mods)), names | mods
