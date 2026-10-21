"""Quality gate: every draft must pass before it can be posted. Returns (clean_text, None) or (None, reason).

Checks, in order: LLM artefacts, forbidden content, voting logistics, wrong claims about the Act, claims false
in-game and the wording of paused facts (content/facts.toml, data/facts_paused.json), format (tags,
emoji, links, mentions), length, side (never endorse Yes; posts must say No, without hedging), consoling, generic
or bot-like phrasing, rhetorical questions, made-up numbers, specificity (a reply must name the target's point or
an in-world fact; a post needs a local detail and ends on a question), copying sources or the prompt,
near-duplicates. shape_ok() is the separate variety check on post shapes.
Content v2 data (src/swan_bot/playbook/: craft tags/stakes/themes, character people/lines) is optional:
without it the built-in defaults below apply.
"""
import re

from . import content
from . import facts as fact_store

try:
    from .playbook import craft as _craft
except ImportError:
    _craft = None
try:
    from .playbook import characters as _characters
except ImportError:
    _characters = None

# the model must put facts in its own words: any 7-word run copied from the fact list, a frame angle, a craft stake
# or heat line, a theme's belief, or a character's past lines (gist only) is rejected
_CRAFT = getattr(_craft, "CRAFT", None) or {}
_CHARS = getattr(_characters, "CHARACTERS", None) or {}


def _texts(value):
    return [value] if isinstance(value, str) else [v for v in value or () if isinstance(v, str)]


SOURCES = ([f["text"] for f in fact_store.TABLE.values()] + [f["angle"] for f in content.FRAMES.values()] +
           [s for f in list(_CRAFT.values()) + list(content.FRAMES.values())
            for s in _texts(f.get("stakes")) + _texts(f.get("heat"))] +
           [s for c in list(_CHARS.values()) + content.PERSONAS for s in _texts(c.get("lines"))] +
           [t["belief"] for t in (getattr(_craft, "THEMES", None) or {}).values()])
_SOURCE_TEXT = " ".join(SOURCES)
# ...except lines meant to repeat verbatim across accounts: the five theme slogans (playbook §3; how often they may
# go out is themes.py's job) and REPEATABLE
_BUILTIN_CATCHPHRASES = ["Don't know? Vote No.", "No list, no Yes.", "Get the jab. Vote No.",
                         "Voted Hawthorne. Voting No.", "Baristas, not border guards."]
CATCHPHRASES = [t["slogan"] for t in (getattr(_craft, "THEMES", None) or {}).values()] or _BUILTIN_CATCHPHRASES
REPEATABLE = ["they pick the places after the vote"] + _texts(getattr(_craft, "REPEATABLE", None))
_EXEMPT_RUNS = {tuple(re.findall(r"[a-z']+", p.lower())) for p in CATCHPHRASES + REPEATABLE} - {()}

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
                             r"\b\d{1,2}(st|nd|rd|th)? (of )?(oct|nov)|\b(oct|nov)(ober|ember)? \d{1,2}\b|"
                             r"\b(vot\w*|ballot|referendum|polls?)\b[^.?!]{0,25}\b(on|by|before) the (1st|2nd|28th)\b|"
                             r"pa'?anga|tala|\b(?<!K)\$\d", re.I)
# claims that contradict the setting: exemptions exist; the certificate is separate from the ID card
WRONG_CLAIMS = re.compile(r"no (medical )?exemptions|without (any )?exemptions|exemptions? (aren'?t|are not|isn'?t)|"
                          r"on (your|the|our) (new )?id card|(linked|tied) to (your|the|our) id|"
                          r"vaccine is (mandatory|compulsory)|forced to (get|have) (the|a) (jab|vaccine)", re.I)
VOTES_NO = re.compile(r"\b(vot(e|ing)|mark(ing)?|tick(ing)?) no\b|\bi'?m a no\b|\bmy vote('?s| is) (still )?no\b|\bsaying no\b|"
                      r"\bit'?s a no\b|\bno from me\b", re.I)
ENDORSES_YES = re.compile(r"\b(i'?m|i am|we'?re|i'?ll be) (voting|marking|ticking) yes\b|"
                          r"\b(please|let'?s|we should|you should|go) vote yes\b|"
                          r"\bi'?m (a )?yes (now|on this)\b|\bmy vote('?s| is) yes\b|\byes from me\b|"
                          r"\bi'?m (choosing|going) yes\b", re.I)
GENERIC = re.compile(r"^(exactly|absolutely|great point|good point|well said|i hear you|i understand|totally agree|"
                     r"spot on|agreed|this[.!]|this is (so )?(true|it)\b|so true|100%)|\b(delve|foster|navigate|landscape|crucial|vital|"
                     r"it'?s important to|at the end of the day|in today'?s|food for thought|tapestry|testament|"
                     r"fellow (citizens|kingstonians)|dear neighbours|let'?s be clear|make no mistake|"
                     r"slippery slope|fundamental rights?)\b", re.I)
# playbook §1/§3 dead words: consoling stock lines that concede the Yes frame ("fair enough", "I respect that" are fine)
CONSOLING = re.compile(r"\bi hear you\b|\bi (completely |totally |fully )?understand (your|the|that|those) "
                       r"(concern|worr|fear|point)|\bi (completely|totally|fully) understand\b|\bthat'?s (so |totally |"
                       r"completely |very )?fair\b(?! to| enough)|\bfair point\b|\bi (totally|completely) get (it|that|why)\b|"
                       r"(^|[.!?] )totally get it\b|"
                       r"\bi( would|'?d) want (that|those|it|the same)( \w+)? too\b|\bi( would|'?d) want the same\b|"
                       r"\bi get where you'?re coming from\b|\byour concerns? (is|are) (valid|understandable)\b|"
                       r"\bvalid concerns?\b", re.I)
# questions nobody answers (playbook §1 #5); a question the reader answers from their own life is the goal
RHETORICAL = re.compile(r"\b(can|could) we really\b|\bhow can (anyone|anybody|a yes)\b|"
                        r"\bhow can we (really |possibly )?(trust|sign|accept|justify|say yes)\b|\bdo we really (want|need)\b|"
                        r"\bisn'?t it time\b|\bare we really\b|\bwhat could (possibly )?go wrong\b|\bwhy would anyone\b|"
                        r"\bwho in their right mind\b|\bis (this|that) really (what|the kingstonia)\b|"
                        r"\bshouldn'?t we all\b|\bsurely we\b", re.I)
# our speaker hedging their own No (talking to undecided readers, or "I was on the fence until...", is fine)
HEDGES = re.compile(r"\bi'?m (still )?(deciding|undecided|on the fence|torn|not sure how (i'?ll|to) vote)\b|"
                    r"\bi am (still )?(deciding|undecided|on the fence|torn)\b|"
                    r"\bi'?m (probably|maybe|leaning( towards)?|tempted to) (vote |voting |go )?no\b|"
                    r"\bi (might|may|could|think i'?ll|probably will) (vote|be voting|go) no\b|"
                    r"\bi haven'?t (decided|made up my mind)\b|\bi'?m still (thinking it over|mulling it over|making up my mind)\b|"
                    r"\b(voting|vote) no,? for now\b|\bprobably (a )?no from me\b", re.I)
CLOSING_QUESTION = re.compile(r"\?['\")]*$")
# a closing question that lost its "?" ("...moved from Yes to No yet #VoteNo"): the mark is added, not rejected
UNMARKED_QUESTION = re.compile(r"(?:^|[.!?]\s+)((?:what|who|which|where|when|why|how|does|do|did|is|are|was|have|has|"
                               r"would|could|will|can|should)\b[^.!?]{8,})$", re.I)
REQUIRE_CLOSING_QUESTION = True                 # posts end on a question the reader can answer (todo/05, playbook §5)
# connector phrases the model leans on; one is fine, the same one in consecutive posts is a template fingerprint
STOCK = re.compile(r"the (trouble|catch|problem|thing) is|as (it'?s )?written|as it stands|set in stone|strictly|locks? (it|this|that|the \w+) in|"
                   r"(makes|is) sense|at the end of|which is why|the reality is|here'?s the (thing|catch)|i get (wanting|why)", re.I)
# tags (playbook §4): a post carries 0 or 1, from the No set, as its last word; every other kind carries none
TAG_ALLOWLIST = {t.lower() for t in getattr(_craft, "TAG_ALLOWLIST", None) or
                 {"#voteno", "#h2d2no", "#keepkingstoniaopen", "#smallbusiness", "#workersrights",
                  "#choicenotcoercion", "#protectkingstonia"}}
TAG = re.compile(r"#\w+")
TAG_AT_END = re.compile(r"\s*#\w+[.!]?$")
TRAILING_TAGS = re.compile(r"(\s*#\w+[.!]?)+\s*$")   # replies: tags the model tacks on at the end are cut, not rejected
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?%?")
# a figure written in words dodges the number check ("Twelve thousand doses" for 120,000): numbers go as digits.
# Plurals ("hundreds of", "thousands of") are vague, not figures, and pass, and so does a digit before the word
# ("K$18 million", checked as 18 by the number rules)
SPELLED_NUMBER = re.compile(r"(?<![\d.] )\b(hundred|thousand|million)\b", re.I)
# true in-game numbers only, each checked in docs/01-competition/setting.md (whole numbers 0-12 always pass):
# Supply: 120,000 first doses, K$18 million for the rest. COVID legacy: >1,000 deaths. Health system: Central ≈450
# beds, Crown Harbour ≈220, ≈30 ICU beds, ≈40 ventilators, ≈1,600 nurses, 420 doctors, 40 unfilled nursing posts,
# surge plan ≈150 extra respiratory patients, 9% of GDP. Demographics: ≈600,000 people, ≈500,000 on the main
# island, Kingstonia City ≈300,000, Crown Harbour ≈150,000, New Haven ≈50,000, ≈100,000 elsewhere. Prices: wage
# K$75,000, nurse K$68,000, engineer K$120,000, flat white K$5.50, ferry K$14, resort room K$300, house K$640,000.
# Law: age 12 and over, voting 18+, pension at 67, 12% GST. Politics: Hawthorne 51.28% to 48.72% (2025), Assembly
# elected 2023, next 2027, ID card legislated 2024, today 2026. Starting poll (17 Oct): 35.2% / 35.2% / 29% unsure.
ALLOWED_NUMBERS = {
    "12", "14", "18", "30", "40", "67", "75", "68", "150", "220", "300", "420", "450", "5.50",
    "1,000", "1000", "1,600", "1600", "50,000", "50000", "68,000", "68000", "75,000", "75000", "100,000", "100000",
    "120,000", "120000", "640", "150,000", "150000", "300,000", "300000", "500,000", "500000", "600,000", "600000",
    "640,000", "640000", "2023", "2024", "2025", "2026", "2027"}
ALLOWED_PERCENTS = {"35.2", "29", "51.28", "48.72", "9", "12"}
# a person's age or how long something has gone on in their own story is not a statistic ("her 13-year-old",
# "at the market 30 years")
# 2026-10-22 (todo/20 G9): also an age after a name ("Mrs Tuilagi, 81, would need papers") or "at 15" / "aged 81"
# (4 of 11 non-length reply rejects on 21 Oct were a character's age)
LIFE_SPAN = re.compile(r"\b\d{1,2}(-| )years?(-| )olds?\b|\b\d{1,2} years\b(?! (from|after|before|of))|"
                       r"(?<=[A-Za-z]), \d{1,3}(?=,)|\b(aged|turns?|turning) \d{1,2}\b(?![%\d])|"
                       r"\bat \d{1,2}(?=[,;!?]|\.(?!\d)| and | or )", re.I)
# dates already past in the timeline (setting.md): bill introduced 9 Oct, voted down 15 Oct, question confirmed
# 17 Oct. Not voting logistics; every other day-and-month date still is
HISTORY_DATES = re.compile(r"\b(9|15|17)(th)? oct(ober)?\b", re.I)


def figures(text):
    """(numbers, percents) that text states, read the way the number gate reads drafts (ages, spans of years and
    past dates aside); a number with thousands commas comes with and without them."""
    nums, pcts = set(), set()
    for num in NUMBER.findall(LIFE_SPAN.sub(" ", HISTORY_DATES.sub(" ", text or ""))):
        bare = num.rstrip("%").rstrip(",")
        if num.endswith("%"):
            pcts.add(bare)
        else:
            nums |= {bare, bare.replace(",", "")}
    return nums, pcts


# ...plus every figure an active fact in content/facts.toml states (text and numbers), so a fact approved through
# scripts/facts_review.py can't be blocked by this gate. A paused fact adds none; the hand-checked ones above stay.
for _fact in fact_store.TABLE.values():
    if _fact.get("status") == "active":
        _nums, _pcts = figures(" ".join([_fact["text"], *map(str, _fact.get("numbers") or [])]))
        ALLOWED_NUMBERS |= _nums
        ALLOWED_PERCENTS |= _pcts
# a reply must touch the target's point or one in-world fact; a post must carry a local detail
FACT_ANCHORS = re.compile(r"ballot|question|regulation|list|designated|end date|sunset|review|exemption|binding|certificate|"
                          r"\bjab|vaccinat|vaxx|papers at|finish date|stop date|expiry|temporary|permanent|"
                          r"stages|120,000|40 empty|nurs|ferry|K\$|age 12|12 and over|school gate|free|voluntary|"
                          r"ID card|biometric|Assembly|community spread|visitors|in writing|written down", re.I)
LOCAL = re.compile(r"Crown Harbour|New Haven|Kingstonia City|outer island|wharf|ferry|market|harbour|reef|beach|"
                   r"regatta|lagoon|ward|clinic|bus|loop|campus|KU\b|counter|shop|cafe|boat|tuna|school|K\$|"
                   r"grandkids?|grandson|granddaughter|residents|Year 8|sailing|stall|bakery|netball|footy|church|"
                   r"village|ring road|mango|jetty|library", re.I)
# ...plus the names of the characters' people and the places in their fortnight (playbook.characters, or the same
# fields once merged into content.PERSONAS); public figures, days and campaign words don't count as local
_NOT_LOCAL = set("I I'm I've I'd Yes No The A An Under But And So If Now Then H2D2 Dolphin Flu COVID Kingstonia "
                 "Monday Tuesday Wednesday Thursday Friday Saturday Sunday Mondays Tuesdays Wednesdays Thursdays "
                 "Fridays Saturdays Sundays October November Oct Nov Hawthorne Castillo "
                 "Singh Whitlock Reyes-Hale Brotherston Abernathy Assembly People's Alliance Democratic-Republicans "
                 "IHO MOUK KITB KBC Legit Social Herald Daily Australia NZ New Zealand President Parliament "
                 # sentence-initial words and generic nouns from the real character data ("She", "Week")
                 "He She Her His They Their We Our My Your It Its This That People Week Year Festival Institute "
                 "Technology City June July Philippines".split())
_TITLES = set("Uncle Aunty Auntie Mrs Mr Ms Miss Nana Nan Papa Grandpa Grandma Church Hospital Market School Club "
               "Street Road Court Courts Park".split())
_CAPS = re.compile(r"[A-Z][\w'&-]*(?: (?:& )?[A-Z][\w'-]*)*")


def _local_names(characters, personas):
    names = set()
    profiles = list((getattr(characters, "CHARACTERS", None) or {}).values()) + list(personas)
    for c in profiles:
        for person in c.get("people") or []:
            names.update(m.group(0) for m in _CAPS.finditer(person))
        for event in c.get("now") or []:
            for m in _CAPS.finditer(event):  # (a sentence-initial word is usually not a name)
                if m.start() > 0:
                    names.add(m.group(0))
    out = set()
    for n in names:
        n = re.sub(r"'s$", "", n)
        words = [re.sub(r"'s$", "", w) for w in n.split()]
        for part in [n] + (words if len(words) > 1 else []):    # "Uncle Viliami" counts as "Viliami" too
            if len(part) > 2 and part not in _TITLES and not all(w in _NOT_LOCAL for w in part.split()):
                out.add(part)
    return out


LOCAL_NAMES = _local_names(_characters, content.PERSONAS) | {"Central", "Mango & Spice"}
LOCAL_NAME = re.compile(r"\b(" + "|".join(sorted(map(re.escape, LOCAL_NAMES), key=len, reverse=True)) + r")\b") \
    if LOCAL_NAMES else None
LENGTHS = {"post": (200, 495), "reply": (80, 290), "second_voice": (60, 270), "reply_back": (25, 240),
           "journalist": (90, 290), "thread": (18, 250), "thread_answer": (50, 250)}
SHORT_OK = 60               # a reply under its kind's floor still passes from here when it states our No (todo/20 G9)


def _shingles(text, n=5):
    words = re.findall(r"[a-z']+", text.lower())
    return {" ".join(words[i:i + n]) for i in range(max(0, len(words) - n + 1))}


def similar(a, b, n=5):
    sa, sb = _shingles(a, n), _shingles(b, n)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / min(len(sa), len(sb))


_SOURCE_SHINGLES = set().union(*(_shingles(s, 7) for s in SOURCES))


def copied_phrases(text, n=7):
    """The copied runs of text (see copied_runs) merged into the longest phrases, in order: what a repair quotes."""
    words = re.findall(r"[a-z']+", strip_tag(normalise(text)).lower())
    hit = copied_runs(" ".join(words), n) & _SOURCE_SHINGLES
    covered = [False] * len(words)
    for i in range(len(words) - n + 1):
        if " ".join(words[i:i + n]) in hit:
            covered[i:i + n] = [True] * n
    phrases, cur = [], []
    for w, c in zip(words + [""], covered + [False]):
        if c:
            cur.append(w)
        elif cur:
            phrases.append(" ".join(cur))
            cur = []
    return phrases


def copied_runs(text, n=7):
    """The n-word runs of text, leaving out any run with 3+ words inside a catchphrase or REPEATABLE line."""
    words = re.findall(r"[a-z']+", text.lower())
    covered = [False] * len(words)
    for run in _EXEMPT_RUNS:
        for i in range(len(words) - len(run) + 1):
            if tuple(words[i:i + len(run)]) == run:
                covered[i:i + len(run)] = [True] * len(run)
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1) if sum(covered[i:i + n]) < 3}


def unapproved_number(t):
    """The first number in t that isn't a true in-game figure (ALLOWED_NUMBERS / _PERCENTS, 0-12), or None."""
    for num in NUMBER.findall(LIFE_SPAN.sub(" ", HISTORY_DATES.sub(" ", t))):
        bare = num.rstrip("%").rstrip(",")
        if num.endswith("%"):
            if bare not in ALLOWED_PERCENTS:
                return num
        elif bare not in ALLOWED_NUMBERS and not (bare.isdigit() and int(bare) <= 12):
            return num
    return None


def normalise(text):
    t = (text or "").strip().strip('"“”').strip()
    t = t.replace("—", " - ").replace("–", "-").replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", t).strip()


def shape_ok(shape, recent_shapes, window=10, max_uses=2):
    """Variety across accounts (todo/05): True if posting `shape` now keeps it to max_uses in any `window` posts.
    recent_shapes: the shapes of our latest posts, oldest first (None entries are ignored)."""
    if shape is None:
        return True
    return list(recent_shapes)[-(window - 1):].count(shape) < max_uses if window > 1 else max_uses > 0


def tag_problem(t, kind):
    """Why t's tags don't fit this kind, or None."""
    tags = TAG.findall(t)
    if not tags:
        return "hashtag" if "#" in t else None
    if kind != "post":
        return "tag_in_reply"
    if len(tags) > 1:
        return "too_many_tags"
    if tags[0].lower() not in TAG_ALLOWLIST:
        return "tag_not_allowed"
    if t.count("#") > 1 or not TAG_AT_END.search(t):
        return "tag_not_at_end"
    return None


def strip_tag(t):
    """t without its closing tag (the question, copy and similarity checks look at the words only)."""
    return TAG_AT_END.sub("", t)


def check(text, kind, recent_texts=(), prompt_text="", target_text="", wants=(), closing_question=True):
    """kind: 'post' | 'reply' | 'second_voice' | 'reply_back' | 'journalist' | 'thread' | 'thread_answer'.
    closing_question=False lets a post end on its verdict instead (a draft told to end without a question)."""
    t = normalise(text)
    if kind != "post":
        t = TRAILING_TAGS.sub("", t).strip()
    if not t:
        return None, "empty"
    if ARTEFACT_START.search(t) or ARTEFACTS.search(t):
        return None, "llm_artefact"
    if FORBIDDEN.search(t):
        return None, "forbidden_content"
    if WRONG_LOGISTICS.search(HISTORY_DATES.sub("that day", t)):
        return None, "wrong_logistics"
    if WRONG_CLAIMS.search(t):
        return None, "wrong_claim"
    if fact_store.FALSE_CLAIMS and fact_store.FALSE_CLAIMS.search(t):
        return None, "false_claim"
    paused = fact_store.paused_in(t)
    if paused:
        return None, f"paused_fact_{paused}"
    why = tag_problem(t, kind)
    if why:
        return None, why
    if any(ord(ch) > 0x2600 for ch in t):        # emoji and other symbols
        return None, "emoji"
    lo, hi = LENGTHS[kind]
    short_ok = kind != "post" and len(t) >= SHORT_OK and VOTES_NO.search(t)     # todo/20 G9: short but says No
    if len(t) > hi or (len(t) < lo and not short_ok):
        return None, f"length_{len(t)}"
    if ENDORSES_YES.search(t):
        return None, "endorses_yes"
    if kind == "post" and not VOTES_NO.search(t):
        return None, "no_vote_statement"
    if kind != "thread" and HEDGES.search(t):   # a thread pushback voices a doubt on purpose
        return None, "hedges_no"
    if CONSOLING.search(t):
        return None, "consoling_phrase"
    if GENERIC.search(t):
        return None, "generic_phrase"
    if any(RHETORICAL.search(q) for q in re.findall(r"[^.!?]*\?", t)):
        return None, "rhetorical_question"
    if SPELLED_NUMBER.search(t):
        return None, "spelled_number"
    num = unapproved_number(t)
    if num:
        return None, f"unapproved_number_{num}"
    if kind in ("reply", "journalist"):            # second voices always carry a set angle, so not checked
        if not (FACT_ANCHORS.search(t) or any(w.lower() in t.lower() for w in wants)):
            return None, "not_specific"
    if kind == "post" and not (LOCAL.search(t) or (LOCAL_NAME and LOCAL_NAME.search(t))):
        return None, "no_local_detail"
    body = strip_tag(t)                            # a shared tag is not a shared sentence
    if kind == "post" and closing_question and UNMARKED_QUESTION.search(body):
        t, body = f"{body}?{t[len(body):]}", f"{body}?"
    if kind == "post" and REQUIRE_CLOSING_QUESTION and closing_question and not CLOSING_QUESTION.search(body):
        return None, "no_closing_question"
    if copied_runs(body) & _SOURCE_SHINGLES:
        return None, "copied_fact"
    if prompt_text and similar(body, prompt_text) > 0.5:
        return None, "copied_prompt"
    if target_text and similar(body, target_text, n=4) > 0.35:
        return None, "parrots_target"
    opening = " ".join(re.findall(r"[a-z']+", t.lower())[:4])
    if any(" ".join(re.findall(r"[a-z']+", o.lower())[:4]) == opening for o in list(recent_texts)[-30:]):
        return None, "same_opening"
    for m in STOCK.finditer(t):
        phrase = re.sub(r"\s+", " ", m.group(0).lower())
        if any(phrase in old.lower() for old in list(recent_texts)[-6:]):
            return None, f"repeat_stock_{phrase.replace(' ', '_')}"
    for old in recent_texts:
        if similar(body, strip_tag(old.strip())) > 0.25:
            return None, "near_duplicate"
    return t, None


# ---- code fixes (todo/20 G9: "we cannot afford a rejection"): a soft failure, or a made-up number, is fixed here with
# no LLM call when what's left still stands; bot.draft_checked runs the gate again on the result.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def sentences(text):
    return [s for s in _SENTENCE_END.split(normalise(text)) if s]


def trim(text, kind):
    """text cut at sentence boundaries to fit the kind's cap, or None: the last sentences go first, but never the
    opening one or one that says we're voting No; what's left must be over the floor and, if the draft said No,
    still say it."""
    lo, hi = LENGTHS[kind]
    parts = sentences(TRAILING_TAGS.sub("", normalise(text)) if kind != "post" else text)
    keep = [i == 0 or bool(VOTES_NO.search(s)) for i, s in enumerate(parts)]
    while len(" ".join(parts)) > hi:
        drop = next((i for i in range(len(parts) - 1, -1, -1) if not keep[i]), None)
        if drop is None:
            return None
        del parts[drop], keep[drop]
    out = " ".join(parts)
    return out if len(out) >= min(lo, SHORT_OK) else None


def drop_number(text, num, kind):
    """text without the sentences holding the number `num`, or None when nothing worth sending is left."""
    bare = num.rstrip(",.%")
    parts = [s for s in sentences(text) if bare not in {n.rstrip(",.%") for n in NUMBER.findall(s)}]
    out = " ".join(parts)
    return out if parts and len(out) >= min(LENGTHS[kind][0], SHORT_OK) else None


def drop_first_clause(text):
    """text without its opening clause (a shared opening is a template fingerprint), or None."""
    t = normalise(text)
    m = re.match(r"^[^,;:.!?]{3,70}?(?:[,;:]| -)\s+", t)
    if m:
        rest = t[m.end():]
    else:
        parts = sentences(t)
        rest = " ".join(parts[1:]) if len(parts) > 1 else ""
    rest = re.sub(r"^(and|but|so|or)\s+", "", rest, flags=re.I)
    return rest[:1].upper() + rest[1:] if len(rest) >= SHORT_OK else None


def fix(text, why, kind):
    """A code fix for a rejected draft (no LLM call), or None when this reason has none or nothing usable is left.
    Too long -> trim; same opening -> drop the first clause; an unapproved number -> drop its sentence."""
    why = why or ""
    if why.startswith("length_") and int(why.split("_")[1]) > LENGTHS[kind][1]:
        return trim(text, kind)
    if why == "same_opening":
        return drop_first_clause(text)
    if why.startswith("unapproved_number_"):
        return drop_number(text, why[len("unapproved_number_"):], kind)
    return None


# Repair-on-reject (todo/14): for these reasons the second call sends the draft back with what to fix (the smallest
# edit), instead of a fresh roll that repeats the failure. Sentence counts, not characters: this model ignores counts.
# (sentences, words) to cut a too-long draft to; words, because a "cut to 1 sentence" second voice stayed at 316
# characters (21 Oct). Each sits under quality.LENGTHS at ~5.4 characters a word.
REPAIR_LENGTH = {"post": (4, 65), "reply": (2, 40), "second_voice": (2, 35), "journalist": (2, 40),
                 "reply_back": (2, 30), "thread_answer": (2, 30)}


def _close_to(raw, recent):
    body = strip_tag(normalise(raw))
    best = max(recent or [""], key=lambda old: similar(body, strip_tag(old.strip())))
    return best if best and similar(body, strip_tag(best.strip())) > 0.25 else None


def repair_note(why, raw, kind, tag=None, recent=()):
    """What to tell the model to fix in a rejected draft, or None (then the retry is a fresh draft). todo/20 G9: every
    reason a draft fails on in practice has a note, so a retry gets the exact problem, not a fresh roll."""
    why = why or ""
    if why == "near_duplicate":
        old = _close_to(raw, recent)
        return ("This is too close to something we already posted" + (f", which went: «{old[:200]}»" if old else "") +
                ". Make the same point with a different opening, a different detail and different words.")
    if why == "same_opening":
        return "Start with different words: the first four words are the same as something we already posted."
    if why.startswith("unapproved_number_"):
        return (f"Remove the number {why[len('unapproved_number_'):].rstrip(',.')}: use no number except the ones you "
                f"were given, as digits.")
    if why == "not_specific":
        return "Name the exact thing they raised, in a few of their own words, or one of your facts."
    if why == "parrots_target":
        return "Don't repeat their words back to them: say it in your own words."
    if why == "rhetorical_question":
        return "Replace the rhetorical question with a plain statement, or a question they can answer from their own life."
    if why == "hedges_no":
        return "Say plainly that you're voting No, with no hedging."
    if why in ("wrong_claim", "false_claim") or why.startswith("paused_fact_"):
        return ("Remove the claim that isn't true: medical exemptions are in the plan, the certificate is separate from "
                "the ID card, and nobody has had the H2D2 jab yet. Keep the rest.")
    if why == "wrong_logistics":
        return "Remove any day or date and anything about how, when or where to vote. Keep the rest."
    if why == "emoji":
        return "Remove the emoji and symbols."
    if why == "llm_artefact":
        return "Output only the reply itself: no label, no preface, no notes."
    if why.startswith("length_") and kind in REPAIR_LENGTH:
        n = int(why.split("_")[1])
        if n <= LENGTHS[kind][1]:
            return None                            # too short: a fresh draft does better than padding
        k, words = REPAIR_LENGTH[kind]
        return (f"Too long ({n} characters). Cut it to {k} sentences and under {words} words in all, keeping the "
                f"opening" + (", the line saying you're voting No and the last line." if kind == "post" else
                              " and the ending."))
    if why == "copied_fact":
        quoted = "; ".join(f"«{p}»" for p in copied_phrases(raw)) or "a phrase"
        return f"This copies the brief word for word: {quoted}. Say it in your own words."
    if why in ("hashtag", "tag_in_reply", "too_many_tags", "tag_not_allowed", "tag_not_at_end"):
        return f"Use exactly one hashtag, {tag}, as the very last word." if kind == "post" and tag else \
            "Remove every hashtag."
    if why == "no_closing_question":
        if "?" in strip_tag(normalise(raw)):       # it asked, then wrote the verdict after: move, don't reword
            return ("Move your question to the very end, after the line saying you're voting No and just before "
                    "the hashtag, with its question mark.")
        return "End with one question the reader answers from their own life, with a question mark."
    if why in ("consoling_phrase", "generic_phrase"):
        m = (CONSOLING if why == "consoling_phrase" else GENERIC).search(normalise(raw))
        quoted = f"«{m.group(0).strip()}»" if m else "the stock phrase"
        return f"Cut {quoted} and say your own point straight out; change nothing else."
    if why == "no_vote_statement":
        return "Say plainly that you're voting No."
    if why == "spelled_number":
        return "Write every number as digits, and only the numbers you were given."
    return None
