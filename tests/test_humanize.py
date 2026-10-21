"""Typing hands (humanize.py): habits stay subtle and never touch the words that carry the message (no network)."""
import pathlib
import random
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from swan_bot import content, humanize, quality  # noqa: E402
from swan_bot.playbook import voices  # noqa: E402

EXAMPLES = [e["text"] for v in voices.VOICES.values() for e in v["examples"]]
TOKENS = re.compile(r"#\w+|K\$\d+(?:\.\d+)?|\d+(?:,\d{3})*|\b[A-Z][A-Z0-9]+\b")    # tags, money, numbers, acronyms


def runs(n=300, seed=1):
    rng = random.Random(seed)
    for key in humanize.HANDS:
        for i in range(n):
            text = EXAMPLES[i % len(EXAMPLES)]
            yield key, text, *humanize.apply(text, key, "post", rng)


def test_every_persona_has_a_hand():
    assert set(humanize.HANDS) == {p["key"] for p in content.PERSONAS}


def test_candidate_hands_are_new_and_complete():
    from swan_bot.playbook.characters import CANDIDATES
    assert set(humanize.CANDIDATE_HANDS) <= {c["key"] for c in CANDIDATES}
    assert not set(humanize.CANDIDATE_HANDS) & set(humanize.HANDS)
    hands = list(humanize.HANDS.values()) + list(humanize.CANDIDATE_HANDS.values())
    for h in humanize.CANDIDATE_HANDS.values():
        assert set(h) == set(humanize._DEFAULT) and hands.count(h) == 1


def test_tags_numbers_acronyms_and_side_words_survive():
    for key, text, out, _ in runs():
        assert TOKENS.findall(out) == TOKENS.findall(text), (key, out)
        assert re.search(r"\bvoting no\b", out, re.I), (key, out)


def test_at_most_one_typo_and_it_is_one_letter():
    for key, text, out, changes in runs():
        slips = [c for c in changes if c.startswith("slip:")]
        assert len(slips) <= 1
        for c in slips:
            before, after = c[5:].split(">")
            assert abs(len(before) - len(after)) <= 1 and before[0] == after[0] and before[-1] == after[-1]
            assert before.lower() not in humanize._PROTECTED and not before[0].isupper()


def test_subtle_typos_are_rare_and_careful_hands_are_clean():
    rates = {}
    for key, _, _, changes in runs(n=500):
        rates.setdefault(key, []).append(any(c.startswith("slip:") for c in changes))
    for key, hits in rates.items():
        assert sum(hits) / len(hits) <= 0.25, key
    assert sum(rates["priya"]) / 500 < 0.05 and sum(rates["grace"]) / 500 < 0.05


def test_catchphrases_kept_whole():
    rng = random.Random(2)
    assert len(content.SLOGANS) == 5
    for c in content.SLOGANS:
        text = f"Mrs Taufa buys tuna off my stall, and I'm out before dawn. {c} I'm voting No. What do you buy?"
        for key in humanize.HANDS:
            for _ in range(40):
                out, _ = humanize.apply(text, key, "post", rng)
                assert c.lower().rstrip(".?!") in out.lower(), (key, out)


def test_paired_commas_untouched():
    rng = random.Random(4)
    text = "Keli, who works my counter, asked me, but nobody knows. I'm voting No. What would you do?"
    for key in humanize.HANDS:
        for _ in range(50):
            out, _ = humanize.apply(text, key, "reply", rng)
            assert re.match(r"keli, who \w+ my \w+, \w+ me", out, re.I), (key, out)


def test_stays_inside_gate_length():
    rng = random.Random(5)
    lo, hi = quality.LENGTHS["post"]
    long_text = ("Mrs Taufa buys tuna. " * 30)[:hi - 1] + "?"
    for key in humanize.HANDS:
        for _ in range(30):
            assert lo <= len(humanize.apply(long_text, key, "post", rng)[0]) <= hi


def test_unknown_persona_and_empty_text():
    assert humanize.apply("", "lani") == ("", [])
    out, _ = humanize.apply("A plain sentence about the ferry. I'm voting No.", "nobody", "reply_back", random.Random(0))
    assert "voting No" in out
