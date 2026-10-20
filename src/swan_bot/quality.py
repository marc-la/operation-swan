"""Quality gate: every draft must pass before it can be posted. Returns (clean_text, None) or (None, reason).

Checks, in order: LLM artefacts, forbidden content, voting logistics, format (hashtags/emoji/links/mentions),
length, side (never endorse Yes; posts must say No), generic or bot-like phrasing, made-up numbers,
wrong claims about the Act, specificity (a reply must name the target's point or an in-world fact; a post needs
a local detail), copying the prompt, near-duplicates.
"""
import re

from . import content

# the model must put facts in its own words: any 7-word run copied from the fact list or a frame angle is rejected
_SOURCE_TEXT = " ".join(list(content.FACTS.values()) + [f["angle"] for f in content.FRAMES.values()])

ARTEFACT_START = re.compile(r"^(sure|here'?s|here is|okay|ok,|certainly|of course|as an?\b|i'?d be happy|"
                            r"post:|reply:|title:|absolutely)", re.I)
ARTEFACTS = re.compile(r"(as an ai|language model|\*\*|^#|\bpost:|\breply:|<\|?im_|\[inst\]|assistant:|"
                       r"system prompt|ignore (all|previous)|character count|\(\d+ characters?\)|<<<|>>>)", re.I | re.M)
FORBIDDEN = re.compile(r"(autis|infertil|steril|poison|microchip|toxic|depopulat|genocide|nazi|apartheid|"
                       r"experimental jab|killed by|deaths? from the (vaccine|jab)|side effects? (kill|caus)|"
                       r"https?://|www\.|@\w|castillo|\bkitb\b|tourism board)", re.I)
_WHEN = r"(today|tonight|tomorrow|this week|next week|monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
WRONG_LOGISTICS = re.compile(r"\b(vot\w*|ballot|tick\w* the box|referendum)\s+(no\s+|yes\s+)?(is\s+)?(on\s+|this\s+|next\s+)?"
                             + _WHEN + r"\b|"
                             r"\b" + _WHEN + r"\b[^.?!]{0,15}\b(vote|voting|ballot|referendum)\b|"
                             r"election day|polling (day|place|booth|station)|early voting|polls (open|close)|"
                             r"\b\d{1,2}(st|nd|rd|th)? (oct|nov)|pa'?anga|tala|\b(?<!K)\$\d", re.I)
# claims that contradict the setting: exemptions exist; the certificate is separate from the ID card
WRONG_CLAIMS = re.compile(r"no (medical )?exemptions|without (any )?exemptions|exemptions? (aren'?t|are not|isn'?t)|"
                          r"on (your|the|our) (new )?id card|(linked|tied) to (your|the|our) id|"
                          r"vaccine is (mandatory|compulsory)|forced to (get|have) (the|a) (jab|vaccine)", re.I)
VOTES_NO = re.compile(r"\b(vot(e|ing)|mark(ing)?|tick(ing)?) no\b|\bi'?m a no\b|\bmy vote is no\b|\bsaying no\b|"
                      r"\bit'?s a no\b|\bno from me\b", re.I)
ENDORSES_YES = re.compile(r"\b(i'?m|i am|we'?re|i'?ll be) (voting|marking|ticking) yes\b|"
                          r"\b(please|let'?s|we should|you should|go) vote yes\b", re.I)
GENERIC = re.compile(r"^(exactly|absolutely|great point|good point|well said|i hear you|i understand|totally agree|"
                     r"spot on|agreed|this\b|so true|100%)|\b(delve|foster|navigate|landscape|crucial|vital|"
                     r"it'?s important to|at the end of the day|in today'?s|food for thought|tapestry|testament|"
                     r"fellow (citizens|kingstonians)|dear neighbours|let'?s be clear|make no mistake|"
                     r"slippery slope|fundamental rights?)\b", re.I)
# connector phrases the model leans on; one is fine, the same one in consecutive posts is a template fingerprint
STOCK = re.compile(r"the (trouble|catch|problem|thing) is|as (it'?s )?written|as it stands|set in stone|strictly|locks? (it|this|that|the \w+) in|"
                   r"(makes|is) sense|at the end of|which is why|the reality is|here'?s the (thing|catch)|i get (wanting|why)", re.I)
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?%?")
ALLOWED_NUMBERS = {"12", "40", "120,000", "120000", "14", "5.50", "2"}
# a reply must touch the target's point or one in-world fact; a post must carry a local detail
FACT_ANCHORS = re.compile(r"ballot|question|regulation|list|designated|end date|sunset|review|exemption|binding|certificate|"
                          r"\bjab|vaccinat|vaxx|papers at|finish date|stop date|expiry|temporary|permanent|"
                          r"stages|120,000|40 empty|nurs|ferry|K\$|age 12|12 and over|school gate|free|voluntary|"
                          r"ID card|biometric|Assembly|community spread|visitors|in writing|written down", re.I)
LOCAL = re.compile(r"Crown Harbour|New Haven|Kingstonia City|outer island|wharf|ferry|market|harbour|reef|beach|"
                   r"regatta|lagoon|ward|clinic|bus|loop|campus|KU\b|counter|shop|cafe|boat|tuna|school|K\$|"
                   r"grandkids?|grandson|granddaughter|residents|Year 8|sailing", re.I)
LENGTHS = {"post": (200, 470), "reply": (80, 290), "second_voice": (60, 270), "reply_back": (25, 240),
           "journalist": (90, 290)}


def _shingles(text, n=5):
    words = re.findall(r"[a-z']+", text.lower())
    return {" ".join(words[i:i + n]) for i in range(max(0, len(words) - n + 1))}


def similar(a, b, n=5):
    sa, sb = _shingles(a, n), _shingles(b, n)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / min(len(sa), len(sb))


_SOURCE_SHINGLES = _shingles(_SOURCE_TEXT, 7)


def normalise(text):
    t = (text or "").strip().strip('"“”').strip()
    t = t.replace("—", " - ").replace("–", "-").replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", t).strip()


def check(text, kind, recent_texts=(), prompt_text="", target_text="", wants=()):
    """kind: 'post' | 'reply' | 'second_voice' | 'reply_back' | 'journalist'."""
    t = normalise(text)
    if not t:
        return None, "empty"
    if ARTEFACT_START.search(t) or ARTEFACTS.search(t):
        return None, "llm_artefact"
    if FORBIDDEN.search(t):
        return None, "forbidden_content"
    if WRONG_LOGISTICS.search(t):
        return None, "wrong_logistics"
    if WRONG_CLAIMS.search(t):
        return None, "wrong_claim"
    if "#" in t:
        return None, "hashtag"
    if any(ord(ch) > 0x2600 for ch in t):        # emoji and other symbols
        return None, "emoji"
    lo, hi = LENGTHS[kind]
    if not lo <= len(t) <= hi:
        return None, f"length_{len(t)}"
    if ENDORSES_YES.search(t):
        return None, "endorses_yes"
    if kind == "post" and not VOTES_NO.search(t):
        return None, "no_vote_statement"
    if GENERIC.search(t):
        return None, "generic_phrase"
    for num in NUMBER.findall(t):
        bare = num.rstrip("%").rstrip(",")
        if num.endswith("%") or (bare not in ALLOWED_NUMBERS and not (bare.isdigit() and int(bare) <= 12)):
            return None, f"unapproved_number_{num}"
    if kind in ("reply", "journalist"):            # second voices always carry a set angle, so not checked
        if not (FACT_ANCHORS.search(t) or any(w.lower() in t.lower() for w in wants)):
            return None, "not_specific"
    if kind == "post" and not LOCAL.search(t):
        return None, "no_local_detail"
    if _shingles(t, 7) & _SOURCE_SHINGLES:
        return None, "copied_fact"
    if prompt_text and similar(t, prompt_text) > 0.5:
        return None, "copied_prompt"
    if target_text and similar(t, target_text, n=4) > 0.35:
        return None, "parrots_target"
    opening = " ".join(re.findall(r"[a-z']+", t.lower())[:4])
    if any(" ".join(re.findall(r"[a-z']+", o.lower())[:4]) == opening for o in list(recent_texts)[-30:]):
        return None, "same_opening"
    for m in STOCK.finditer(t):
        phrase = re.sub(r"\s+", " ", m.group(0).lower())
        if any(phrase in old.lower() for old in list(recent_texts)[-6:]):
            return None, f"repeat_stock_{phrase.replace(' ', '_')}"
    for old in recent_texts:
        if similar(t, old) > 0.25:
            return None, "near_duplicate"
    return t, None
