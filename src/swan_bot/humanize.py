"""Typing hands: small, stable writing habits per persona, applied to a draft after it passes the quality gate.

Twelve personas drafted by one model all type like the same careful writer. Each persona here gets a hand: phone or
laptop, how they use capitals and apostrophes, a punctuation habit or two, and how often a typo slips through.
Habits are stable per persona (that is what tells them apart); slips are rare and at most one per text, so most texts
come out with no typo at all. Some texts are typed carefully and keep only the habits.

Never touched: hashtags, numbers and money (K$14, 120,000), acronyms (KU, GP, H2D2), the side words (no, not,
yes, never, vote...), catchphrases, and short words; typos also skip capitalised words, so names stay right. The result must still fit the gate's length bounds, else the
clean text goes out. bot.py logs the clean draft and the changes beside the text that was sent.
"""
import random
import re

from . import content, quality

# lower: share of texts typed all lowercase (hashtags, acronyms and K$ kept); lower_start: first letter left lower;
# small_i: "i" / "i'm" for "I"; apos: share of texts that drop apostrophes (dont, cant, im), per contraction 70%;
# comma: chance each comma before but/so/and/then/because is skipped (paired commas are never touched); amp: chance "and" becomes "&" (once per text); dots: chance one
# ". " becomes "... "; two_space: two spaces after full stops; slip: chance of one typo; careful: share of texts
# typed slowly (habits kept, no slips, no dropped commas or apostrophes).
HANDS = {
    "lani":   dict(device="phone",  lower=0.0,  lower_start=0.05, small_i=0.0,  apos=0.15, comma=0.05, amp=0.25,
                   dots=0.10, two_space=False, slip=0.15, careful=0.25),
    "priya":  dict(device="laptop", lower=0.0,  lower_start=0.0,  small_i=0.0,  apos=0.0,  comma=0.0,  amp=0.0,
                   dots=0.0,  two_space=False, slip=0.04, careful=0.6),
    "isla":   dict(device="phone",  lower=0.85, lower_start=0.10, small_i=0.9,  apos=0.10, comma=0.10, amp=0.0,
                   dots=0.0,  two_space=False, slip=0.15, careful=0.2),
    "josh":   dict(device="phone",  lower=0.0,  lower_start=0.15, small_i=0.10, apos=0.45, comma=0.15, amp=0.10,
                   dots=0.0,  two_space=False, slip=0.20, careful=0.15),
    "ana":    dict(device="phone",  lower=0.0,  lower_start=0.10, small_i=0.0,  apos=0.10, comma=0.10, amp=0.0,
                   dots=0.15, two_space=False, slip=0.20, careful=0.2),
    "mere":   dict(device="tablet", lower=0.0,  lower_start=0.0,  small_i=0.0,  apos=0.0,  comma=0.0,  amp=0.0,
                   dots=0.35, two_space=True,  slip=0.10, careful=0.3),
    "ben":    dict(device="phone",  lower=0.10, lower_start=0.20, small_i=0.15, apos=0.40, comma=0.20, amp=0.0,
                   dots=0.0,  two_space=False, slip=0.15, careful=0.15),
    "sione":  dict(device="phone",  lower=0.0,  lower_start=0.05, small_i=0.0,  apos=0.10, comma=0.05, amp=0.30,
                   dots=0.0,  two_space=False, slip=0.10, careful=0.3),
    "dan":    dict(device="laptop", lower=0.0,  lower_start=0.0,  small_i=0.0,  apos=0.05, comma=0.05, amp=0.0,
                   dots=0.10, two_space=False, slip=0.08, careful=0.4),
    "grace":  dict(device="laptop", lower=0.0,  lower_start=0.0,  small_i=0.0,  apos=0.0,  comma=0.0,  amp=0.0,
                   dots=0.0,  two_space=True,  slip=0.03, careful=0.6),
    "tomasi": dict(device="phone",  lower=0.15, lower_start=0.25, small_i=0.20, apos=0.40, comma=0.20, amp=0.05,
                   dots=0.0,  two_space=False, slip=0.20, careful=0.15),
    "ruth":   dict(device="phone",  lower=0.0,  lower_start=0.0,  small_i=0.0,  apos=0.05, comma=0.05, amp=0.10,
                   dots=0.15, two_space=False, slip=0.10, careful=0.3),
    "esther": dict(device="phone",  lower=0.0,  lower_start=0.0,  small_i=0.0,  apos=0.30, comma=0.25, amp=0.0,
                   dots=0.05, two_space=False, slip=0.12, careful=0.25),
    "paulo":  dict(device="phone",  lower=0.0,  lower_start=0.0,  small_i=0.0,  apos=0.0,  comma=0.10, amp=0.0,
                   dots=0.25, two_space=False, slip=0.06, careful=0.45),
    "ngaire": dict(device="phone",  lower=0.0,  lower_start=0.0,  small_i=0.0,  apos=0.20, comma=0.30, amp=0.0,
                   dots=0.0,  two_space=False, slip=0.12, careful=0.2),
    "wally":  dict(device="tablet", lower=0.0,  lower_start=0.0,  small_i=0.0,  apos=0.0,  comma=0.0,  amp=0.25,
                   dots=0.0,  two_space=False, slip=0.08, careful=0.5),
    "kai":    dict(device="laptop", lower=0.0,  lower_start=0.0,  small_i=0.0,  apos=0.0,  comma=0.15, amp=0.15,
                   dots=0.0,  two_space=False, slip=0.07, careful=0.35),
}

# Hands for the todo/17 candidates (characters.CANDIDATES): moved into HANDS when a candidate joins content.PERSONAS.
CANDIDATE_HANDS = {}
_DEFAULT = dict(device="phone", lower=0.0, lower_start=0.0, small_i=0.0, apos=0.0, comma=0.0, amp=0.0, dots=0.0,
                two_space=False, slip=0.05, careful=0.5)

# Only these lose their apostrophe: none of them turns into another word (unlike we'll, I'll, she'd).
_CONTRACTIONS = re.compile(r"\b(don|can|won|isn|doesn|didn|wasn|aren|couldn|wouldn|shouldn|haven)'t\b|"
                           r"\b(I)'(m|ve)\b|\b(that|there|what)'s\b", re.I)
_CONJ_COMMA = re.compile(r",(?= (but|so|and|then|because)\b)")
_PROTECTED = {"no", "not", "yes", "never", "vote", "voting", "voted", "voter", "voters", "against", "without"}
_WORD = re.compile(r"(?<![\w#$'])[A-Za-z]{5,}(?![\w'$])")
_KEEP_CASE = re.compile(r"#\w+|\bK\$|\b[A-Z][A-Z0-9]+\b")     # tags, K$, acronyms (KU, GP, H2D2)
_NEIGHBOURS = {r: c for row in ("qwertyuiop", "asdfghjkl", "zxcvbnm") for r, c in
               ((row[i], row[max(i - 1, 0)] + row[min(i + 1, len(row) - 1)]) for i in range(len(row)))}


def _protected_spans(text):
    """(start, end) of catchphrases and hashtags: no typos or dropped commas in there."""
    spans = [m.span() for m in re.finditer(r"#\w+", text)]
    low = text.lower()
    for p in content.PILLARS.values():
        for c in p["catchphrases"]:
            i = low.find(c.lower().rstrip(".?!"))
            if i >= 0:
                spans.append((i, i + len(c)))
    return spans


def _inside(i, spans):
    return any(a <= i < b for a, b in spans)


def _lowercase(text):
    keep = {m.start(): m.group(0) for m in _KEEP_CASE.finditer(text)}
    out, i = [], 0
    for start in sorted(keep):
        out += [text[i:start].lower(), keep[start]]
        i = start + len(keep[start])
    return "".join(out + [text[i:].lower()])


def _slip(word, device, rng):
    """One typo in a word: a neighbouring key (phones), two letters swapped (fast typing), a letter dropped or doubled."""
    kinds = ["neighbour", "neighbour", "drop", "double"] if device == "phone" else ["swap", "swap", "drop", "double"]
    kind = rng.choice(kinds)
    i = rng.randrange(1, len(word) - 1)                         # never the first or last letter
    ch = word[i]
    if kind == "neighbour" and ch.lower() in _NEIGHBOURS:
        new = rng.choice(_NEIGHBOURS[ch.lower()].replace(ch.lower(), "") or ch.lower())
        return word[:i] + (new.upper() if ch.isupper() else new) + word[i + 1:]
    if kind == "swap" and i < len(word) - 2 and word[i] != word[i + 1]:
        return word[:i] + word[i + 1] + word[i] + word[i + 2:]
    if kind == "double":
        return word[:i] + ch + word[i:]
    return word[:i] + word[i + 1:]


def apply(text, persona_key, kind="post", rng=random):
    """(text as this persona types it, list of what changed). Unknown personas get a light default hand."""
    if not text:
        return text, []
    h, out, changes = HANDS.get(persona_key, _DEFAULT), text, []
    careful = rng.random() < h["careful"]
    if not careful and rng.random() < h["slip"]:
        spans = _protected_spans(out)
        words = [m for m in _WORD.finditer(out) if m.group(0).lower() not in _PROTECTED
                 and not _inside(m.start(), spans) and not m.group(0)[0].isupper()]
        if words:
            m = rng.choice(words)
            typo = _slip(m.group(0), h["device"], rng)
            if typo != m.group(0):
                out = out[:m.start()] + typo + out[m.end():]
                changes.append(f"slip:{m.group(0)}>{typo}")
    if not careful and rng.random() < h["apos"]:
        before = out
        out = _CONTRACTIONS.sub(lambda m: m.group(0).replace("'", "") if rng.random() < 0.7 else m.group(0), out)
        if out != before:
            changes.append("apos")
    if not careful and h["comma"]:
        spans = _protected_spans(out)
        drop = [m.start() for m in _CONJ_COMMA.finditer(out) if not _inside(m.start(), spans) and rng.random() < h["comma"]]
        for i in reversed(drop):
            out = out[:i] + out[i + 1:]
        if drop:
            changes.append(f"comma-{len(drop)}")
    if rng.random() < h["amp"]:
        ands = list(re.finditer(r"(?<=\w) and (?=\w)", out))
        if ands:
            m = rng.choice(ands)
            out, changes = out[:m.start()] + " & " + out[m.end():], changes + ["amp"]
    if rng.random() < h["dots"]:
        spans = _protected_spans(out)
        stops = [m for m in re.finditer(r"(?<=[a-z])\. (?=[A-Za-z])", out) if not _inside(m.start(), spans)]
        if stops:
            m = rng.choice(stops[:-1] or stops)                # not the stop before the closing question
            out, changes = out[:m.start()] + "... " + out[m.end():], changes + ["dots"]
    if h["two_space"]:
        out = re.sub(r"(?<=[a-z0-9])([.?!]) (?=[A-Z])", r"\1  ", out)
    if rng.random() < h["lower"]:
        out, changes = _lowercase(out), changes + ["lower"]
    else:
        if rng.random() < h["small_i"]:
            before = out
            out = re.sub(r"\bI\b", "i", out)
            if out != before:
                changes.append("small_i")
        if rng.random() < h["lower_start"] and out[:1].isupper() and not _KEEP_CASE.match(out):
            out, changes = out[0].lower() + out[1:], changes + ["lower_start"]
    lo, hi = quality.LENGTHS.get(kind, (0, 10 ** 6))
    if not lo <= len(out) <= hi:
        return text, []
    return out, changes
