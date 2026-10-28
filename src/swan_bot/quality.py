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

from . import config, content, memory
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
                       r"system prompt|ignore (all|previous)|character count|\(\d+ characters?\)|<<<|>>>|"
                       r"fixed opening|different detail|same point:)", re.I | re.M)
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
                             r"pa'?anga|\b\d[\d,.]*\s*tala\b|\b(?<!K)\$\d", re.I)   # a sum of tala, not a girl called Tala
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
# Re-run on every table reload (facts.ON_RELOAD): since 2026-10-22 the desk no longer restarts the bot, and its new
# facts' figures were rejected as unapproved_number (the 25 nurses, 23 Oct).
def sync_numbers():
    for fact in fact_store.TABLE.values():
        if fact.get("status") == "active":
            nums, pcts = figures(" ".join([fact["text"], *map(str, fact.get("numbers") or [])]))
            ALLOWED_NUMBERS.update(nums)
            ALLOWED_PERCENTS.update(pcts)


sync_numbers()
fact_store.ON_RELOAD.append(sync_numbers)
# a reply must touch the target's point or one in-world fact; a post must carry a local detail
FACT_ANCHORS = re.compile(r"ballot|question|regulation|list|designated|end date|sunset|review|exemption|binding|certificate|"
                          r"\bjab|vaccinat|vaxx|papers at|finish date|stop date|expiry|temporary|permanent|"
                          r"stages|120,000|40 empty|nurs|ferry|K\$|age 12|12 and over|school gate|free|voluntary|"
                          r"ID card|biometric|Assembly|community spread|visitors|in writing|written down", re.I)
# 2026-10-23: the same facts in the words drafts use now. content.WORN_PHRASES (and the phrase budgets) tell the model to
# keep off "end date", "venue list", "list of places", "sunset", "after the vote" and "blank cheque", the very words
# FACT_ANCHORS looked for, so 316 of 721 rejects in 24 h were not_specific on replies that did state the fact ("they
# won't say which doors until you've said yes", "nobody wrote a switch-off", "the IHO's data is still coming in");
# only 19% of those jobs ever got a reply out. Each branch below is one fact in other words, never a bare topic word
# like "pass" or "papers" (those are on every reply, so they prove nothing).
FACT_PARAPHRASES = re.compile(
    r"\b(?:won't|wont|haven't|hasn't|can't|couldn't|don't|doesn't|never|not|nobody|nobody's|no one|no one's)\s+(?:\w+\s+){0,2}?(?:say|said|tell|told|"
    r"name|named|publish|show|list|know|decided?)\s+(?:\w+\s+)?(?:which|what|where|whether)\b|"
    r"\b(?:places|doors|venues|spaces|locations|sites|rooms)\b[^.?!]{0,50}\b(?:after (?:we|the|they|you|it)|until|later|chosen|picked|"
    r"decided?|named|haven't|hasn't|won't|aren't|isn't)\b|"
    r"\b(?:after|until|before) (?:we|you|the|they|i) (?:vote|voted|result|count|referendum)|until after\b|"
    r"switch[- ]?off|finish(?:ing)? line|no (?:end|expiry|stop|exit)\b|never (?:ends?|stops?|switches)|"
    r"where does (?:it|this) (?:ever )?(?:stop|end|switch)|time[- ]?limit|"
    r"roll-?out|staged|phased?\b|doses|booster|late october|Daily Kingstonia|Herald\b|IHO\b|Medical Officers|MOUK|"
    r"\bbill\b|President|one (?:confirmed |isolated )?case|traveller|isolation|transmission|"
    r"blank (?:cheque|check)|under-12|12-year|aged? 12|binds? us|locks? (?:it |us )?in|locked in|"
    r"skeleton|empty (?:posts|beds)|unfilled|nursing", re.I)
# The other way to be specific: take up a word of theirs (the prompts say "Name one concrete detail from their post")
# and bring the rule to it. Only with a policy word, so a reply that merely echoes them still fails.
POLICY_WORDS = re.compile(r"\b(?:papers?|pass(?:es)?|proof|checks?|checking|checked|checker|gate|doors?|cert(?:ificate)?s?|"
                          r"card|app|reader|scanner|enforce\w*|polic(?:e|ing|eman)|staff|jabs?|scan\w*)\b", re.I)
_ECHO_STOP = set("""about above after again against also always another because been before being below between both
could doesn don during each even ever every from have having here into just like made make many more most much must
never only other over really same should since some still such than that their them then there these they thing things
think this those through under until very want wants were what when where which while will with without would your
people vote voting voted rule rules pass passes papers paper shop shops door doors check checks kingstonia
referendum government exactly right agree worry worries worried concern need needs good great fair real true sure hear
understand know knows said says tell told going well come comes year years week weeks time today covid""".split())


def _stems(text):
    text = POLICY_WORDS.sub(" ", re.sub(r"https?://\S+", " ", text or ""))     # the policy word itself is not an echo
    return {w.rstrip("s")[:6] for w in re.findall(r"[a-z]{4,}", text.lower())} - {w.rstrip("s")[:6] for w in _ECHO_STOP}


def touches_target(text, target_text):
    """True when text takes up a distinctive word of the citizen's post and brings the rule to it (POLICY_WORDS)."""
    return bool(target_text and POLICY_WORDS.search(text) and _stems(text) & _stems(target_text))


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
# ---- invented names (2026-10-24 audit). The prompts say "invent no names"; this is the check. It only means anything
# against the system prompt that was really sent: a variant account renames the card's people (Esther's porter
# foreman Ravi Chand is "Leigh Ravuvu" on one account), so judge a name against `job["system_caps"]`, never against
# the base card. A capitalised word is a
# name we know if the character data, the facts or the world text hold it, or the prompt or the citizen's post does.
# Anything else mid-sentence is invented; at a sentence start only a given name from variants' pools counts (so
# "Today's" or "Nobody's" never do).
_CAP = re.compile(r"\b[A-Z][a-z][\w'-]*")
NAME_CHECKED = ("reply", "reply_back", "second_voice", "journalist")

# ---- repeated runs (2026-10-24 audit of six replies): "a pass at the bakery door won't add a single nurse" went out from
# two voices a minute apart and "what's wrong with keeping things as they are today?" closed four of six. Whole-text
# similarity (near_duplicate) lets a shared clause through, so a run of RUN_WORDS words that one of our last
# RUN_WINDOW citizen-facing texts already holds is rejected. Not a run the citizen wrote, and not one holding a number
# (a fact's own figure, "40 empty nursing posts", is allowed to repeat).
RUN_WORDS = 8              # replayed on 24 h of live replies (3,985): 6 words would reject 24%, 7 12%, 8 6.7%
RUN_WINDOW = 60


def repeated_run(body, recent_texts, target_text=""):
    """The first RUN_WORDS-word run of body that is in one of our last RUN_WINDOW texts, or None."""
    words = re.findall(r"[a-z']+|\d+", body.lower())
    old = set()
    for o in list(recent_texts)[-RUN_WINDOW:]:
        old |= _shingles(strip_tag(o.strip()), RUN_WORDS)
    own = _shingles(target_text or "", RUN_WORDS)
    for i in range(len(words) - RUN_WORDS + 1):
        run = words[i:i + RUN_WORDS]
        if any(w.isdigit() for w in run):
            continue
        run = " ".join(run)
        if run in old and run not in own:
            return run
    return None


def _strings(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from _strings(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            yield from _strings(v)


def caps_in(text):
    """The capitalised words of text, without a possessive 's."""
    return frozenset(re.sub(r"'s$", "", m.group(0)) for m in _CAP.finditer(text or ""))


def _known_caps():
    from . import variants
    text = list(_strings(getattr(_characters, "CHARACTERS", None) or {})) + list(_strings(content.PERSONAS)) + \
        list(content.FACT_NOTES.values()) + list(content.FACTS.values()) + [content.WORLD, content.QUESTION] + \
        list(content.FIRST_NAMES.values())
    known = set().union(*(caps_in(t) for t in text)) | {w for n in LOCAL_NAMES for w in n.split()} | _NOT_LOCAL
    return frozenset(known), frozenset(variants.FIRST_F) | frozenset(variants.FIRST_M) | frozenset(variants.FIRST_U)


KNOWN_CAPS, GIVEN_NAMES = _known_caps()


def invented_name(text, known=()):
    """The first name in text that is nowhere in the character data, the facts, the world text or `known` (the caps of
    the prompt and the citizen's post), or None."""
    t = strip_tag(normalise(text))
    for m in _CAP.finditer(t):
        w = re.sub(r"'s$", "", m.group(0))
        if w in KNOWN_CAPS or w in known:
            continue
        starts = not re.search(r"[A-Za-z,;]\s$", t[:m.start()])     # first word of a sentence
        if not starts or w in GIVEN_NAMES:
            return w
    return None


LENGTHS = {"post": (200, 495), "reply": (80, 290), "second_voice": (60, 270), "reply_back": (25, 240),
           "journalist": (90, 290), "thread": (18, 250), "thread_answer": (50, 250)}
SHORT_OK = 60               # a reply under its kind's floor still passes from here when it states our No (todo/20 G9)
# todo/23's off-topic replies (check(specific=False)): 60-220 characters, and no turn to the vote when the citizen's
# post has none (2026-10-22 dry run: "...it's the pass I can't stand. No end date on it... Voting No.")
OFF_TOPIC_LEN = (60, 220)
VOTE_TALK = re.compile(r"referendum|h2d2|dolphin flu|vaccin|\bjabs?\b|mandate|\bvot(e|es|ed|ing|ers?)\b|ballot|"
                       r"certificate|health pass|\bthe pass\b|\bpasses\b|door checks?|sunset (clause|date)|end date|"
                       r"exemptions?|\bkitb\b|castillo|(yes|no) campaign", re.I)


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
    t = re.sub(r"\s+", " ", t).strip()
    # 24 Oct (Marc): " - " as a dash was in 33% of 1,019 writes in 6 h and the models write it because the prompts ban the em
    # dash: one fingerprint on a profile. A dash between words becomes a comma (or just a space after a full stop).
    t = re.sub(r"(?<=[.!?]) - (?=\S)", " ", t)
    return re.sub(r"(?<=\w) - (?=[A-Za-z])", ", ", t)


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


# todo/24 near-duplicates (22 Oct: the top reject, 183 of the night's reply drafts at 0.25 against all our last 300
# texts). A draft to one citizen is compared strictly (NEAR_DUP_SAME) to what we sent to that citizen or thread
# (`same`), and loosely (NEAR_DUP_OTHER) to what we sent to everyone else: repeating ourselves across citizens is a bot
# tell for Blue reporters, so it isn't dropped. Posts, threads and journalist replies stay strict against everything.
# todo/27 (22 Oct): 0.4 -> 0.3 across citizens. At 0.4 one reply skeleton went out from many voices and the moderator
# hid it on other teams' Blue reports; the same-citizen check is unchanged.
NEAR_DUP_SAME = 0.25
NEAR_DUP_OTHER = 0.3
PERSONAL_KINDS = ("reply", "reply_back", "second_voice")
# 24 Oct audit: after a repeat_run repair a reply began "They're choosing the places after we decide." with nobody for "they"
# (the repair had cut the sentence that said who). A reply opening on They/Them/Those is fine only where the citizen's own
# comment has a group for it to mean.
BARE_OPEN = re.compile(r"(?:they|them|those)\b", re.I)
GROUP_WORDS = re.compile(r"\b(?:they|them|their|those|government|govt|gov|assembly|ministers?|ministry|council|politicians?|"
                         r"authorities|officials?|people|folks|everyone|businesses|shops|venues|employers|bosses|staff)\b", re.I)

# ---- todo/51 (28 Oct): no conceding a conditional Yes in a reply-back (config.CONCEDE_CHECK_KINDS) ----
# Two-thirds of the citizens who answer us would back Yes with conditions. Granting that the conditions are good or would
# make it fine ("a sunset clause would help, but...") validates Yes-with-conditions. Patterns tuned on 1,210 labelled
# reply-backs, 23-28 Oct (docs/06-strategy/replyback-persuasion-2026-10-28.md): conditional_yes 0.93 precision, 0.93 recall.
CONDITIONAL_YES = re.compile(
    r"\bif (?:a |the )?yes\b|\bif (?:this|it|we|the pass|a pass|the rule|the certificate|they|the government)\b[^.?!]{0,30}"
    r"\b(?:goes ahead|go(?:es)? ahead|passes|pass|moves? (?:ahead|forward)|go(?:es)? forward|wins?|happens|proceed|is to)\b"
    r"|\bif we (?:vote|go|move|do|proceed)\b|\bonly (?:with|if)\b|\byes,? but\b"
    r"|\b(?:could|would|i'?d|might) (?:back|support|accept)\b|\bopen to (?:a )?yes\b|\b(?:still )?lean(?:ing)? yes\b"
    r"|\bbefore (?:i|we)(?:'?d| would| could)? (?:back|vote|support|sign)"
    r"|\b(?:we|it|they|the rule|the plan|regulations?|the law|this) (?:need|needs|must|should|has to|have to|ha(?:s|ve) got to)\b"
    r"[^.?!]{0,60}\b(?:sunset|end date|expiry|venue|list|exemption|oversight|review|guardrail|safeguard|timetable|scope|"
    r"privacy|watchdog|published|written|in law|statute|plan)|\block (?:it |this |these |those )?in\b|\bbake[ds]? in", re.I)
SAFEGUARD = re.compile(r"\bsunset|\bend[- ]?dates?\b|\bexpir(?:y|es|ation)\b|\bfinish line\b|\btime[- ](?:limit|bound)|"
                       r"\bvenues?\b|\bspaces? (?:list|map)|\blist of (?:places|venues|spaces)\b|\bexemptions?\b|"
                       r"\boversight\b|\bwatchdog\b|\breviews?\b|\bguardrails?\b|\bsafeguards?\b|\bscope\b|"
                       r"\btimetable\b|\btriggers?\b|\bmilestones?\b|\bprivacy\b", re.I)
DEMANDS = re.compile(r"\b(?:need|needs|must|should|want|wants|require|requires|publish|written|write|lock|codify|"
                     r"firm|hard|clear|real|proper|essential|before|first|minimum|non-negotiable|deserve)\b", re.I)
SAYS_NO = re.compile(r"\b(?:i'?m|i am|we'?re|i'?ll be)\s+(?:voting|a|going)\s+no\b|\bno from me\b|\bvote no\b|"
                     r"\bthat'?s a no\b|\bvoting no\b", re.I)
CONCEDES = re.compile(
    r"\b(?:would|could|might) (?:help|fix|be (?:welcome|good|great|nice|ideal|fair|sensible|a start|reasonable|better))\b"
    r"|'d (?:help|be (?:welcome|good|great|nice|ideal|fair|sensible|a start|reasonable|better))\b"
    r"|\bsounds? (?:fair|fine|sensible|good|reasonable|grand|lovely|tidy|kind|wise|ideal|great|right|solid|workable|nice)"
    r"|\b(?:is|are|seems?|look) (?:fair|sensible|reasonable|ideal|essential|welcome)\b|\ba fine idea\b"
    r"|\bfair (?:enough|ask|point|to want|call)\b|\bmakes? sense\b|\breasonable ask\b|\bgood (?:to want|idea|call|start)\b"
    r"|\bwould (?:have )?made? (?:it|this) (?:workable|acceptable|fair|fine|ok|okay|better|work)\b|\b(?:a|the) fine system\b"
    r"|\bthat version\b|\bi'?d (?:back|support|vote for|feel differently)\b|\bthose (?:three )?protections\b"
    r"|\b(?:guardrails|safeguards|protections|conditions)[^.?!]{0,25}\b(?:matter|are (?:right|good|smart|needed))\b"
    r"|\byou'?re right that (?:th(?:ose|ese|at)|it|they)\b[^.?!]{0,25}\bmatters?\b|\byou want what i want\b", re.I)
CONCEDE_BACKREF = re.compile(
    r"\b(?:th(?:ose|ese|at)|your|all (?:of )?th(?:ose|ese)|both)\b[^.?!]{0,20}\b(?:things?|fix(?:es)?|protections?|"
    r"conditions?|guardrails?|safeguards?|ideas?|points?|asks?|limits?|rules?|version|plan|framework|system|changes?)\b"
    r"|\bwould (?:have )?made? (?:it|this) |\bthat version\b|\bfine system\b|\bi'?d back\b|\bfeel differently\b"
    r"|\bthat'?d be ideal\b|\byou want what i want\b", re.I)
_BUT = re.compile(r"(?:,\s*|\s+)but\s+", re.I)


def conditional_yes(target_text):
    """True when the citizen's post would back Yes with conditions, or talks about how a Yes should be done (todo/51)."""
    t = re.sub(r"https?://\S+", "", target_text or "")
    if SAYS_NO.search(t):
        return False
    n = len({m.group(0).lower()[:5] for m in SAFEGUARD.finditer(t)})
    return bool(CONDITIONAL_YES.search(t)) or n >= 2 or (n >= 1 and bool(DEMANDS.search(t)))


def conceding_sentence(text):
    """The first sentence of text that grants a safeguard or the citizen's conditions (CONCEDES next to a SAFEGUARD
    word or a reference back to their list), or None. Conceding something else ("better pay would help") is fine."""
    for s in sentences(TRAILING_TAGS.sub("", normalise(text))):
        if CONCEDES.search(s) and (SAFEGUARD.search(s) or CONCEDE_BACKREF.search(s)):
            return s
    return None


def drop_concession(text, kind):
    """A code fix for concede_condyes: the conceding sentence keeps only what follows its "but" ("A sunset would help,
    but they won't say which shops" -> "They won't say which shops"), or goes; None when nothing usable is left."""
    parts = sentences(TRAILING_TAGS.sub("", normalise(text)))
    for i, s in enumerate(parts):
        if s != conceding_sentence(s):
            continue
        m = _BUT.search(s)
        rest = _cap(s[m.end():]) if m and CONCEDES.search(s[:m.start()]) else ""
        if rest and len(rest) >= 20 and not conceding_sentence(rest):
            out = " ".join(parts[:i] + [rest] + parts[i + 1:])
        else:                                      # the sentence goes; one sentence left is enough for a reply-back
            kept = parts[:i] + parts[i + 1:]
            if not kept or (i < len(parts) - 1 and _BACKREF.match(parts[i + 1])):    # "That's why..." leans on it
                return None
            out = _cap(" ".join(kept))
        return out if out and len(out) >= LENGTHS[kind][0] and not conceding_sentence(out) else None
    return None


def near_duplicate(body, kind, recent_texts=(), same=()):
    """True when body is too close to one of our texts (5-word shingles, quality.similar), as above."""
    other = NEAR_DUP_OTHER if kind in PERSONAL_KINDS else NEAR_DUP_SAME
    return (any(similar(body, strip_tag(old.strip())) > NEAR_DUP_SAME for old in same) or
            any(similar(body, strip_tag(old.strip())) > other for old in recent_texts))


# ---- todo/27 phrase budgets. 22 Oct 00-05 UTC: "voting no" in 64% of our 606 citizen-facing writes, "end date" 24%,
# "sunset" 21%, "venue list" 18%, "no review" 16%, and the moderator hid replies sharing that one skeleton ("...a Yes
# binds us... no end date or review... I'm voting No.") on other teams' Blue reports. Over our last PHRASE_WINDOW
# citizen-facing texts (replies, reply-backs, second voices to citizens), each phrase may be in at most its share; a
# draft that would go over is rejected with phrase_<keys> (repair_note names the phrase; fix() cuts a sentence or
# clause that only states the vote, drop_vote). Posts must still say No (no_vote_statement) and are not budgeted.
PHRASE_WINDOW = 100
PHRASE_BUDGETS = {                  # key: (pattern, share of the window)
    # todo/40 (24 Oct): 0.15 -> 0 for replies, reply-backs and second voices (the PERSONAL_KINDS this budget is applied to; posts and
    # threads are not budgeted, and a post must still say No). A vote statement in a reply: adjusted OR 2.5, 19% hidden when one
    # leaked after the gate (n = 26). The prompts already say not to (content.NO_VERDICT_RULE); this rejects the leak and
    # drop_vote cuts it. The live value is config.REPLY_VOTE_SHARE (budget_share), so SWAN_REPLY_VOTE_SHARE=0.15 undoes it.
    "vote": (VOTES_NO, config.REPLY_VOTE_SHARE),
    "binds_us": (re.compile(r"\bbind(s|ing)? (us|you|everyone|kingstonia)\b", re.I), 0.10),
    "no_review": (re.compile(r"\bno\b[^.?!]{0,25}\breview\b", re.I), 0.10),      # "no end date or review" too
    "end_date": (re.compile(r"\bend dates?\b", re.I), 0.10),
    "venue_list": (re.compile(r"\bvenue lists?\b", re.I), 0.10),
    "sunset": (re.compile(r"\bsunset\b", re.I), 0.10),
    "after_the_vote": (re.compile(r"\bafter the vote\b", re.I), 0.10),
    # 24 Oct (Marc): one hot voice wrote these in 6 h (1,019 writes): "door" 47%, "papers" 30%, "who in your..?" 10%, "half four" 6%.
    # On a single profile that is one script. Budgets at about half of that; the citizen's own word still counts as an echo.
    "door": (re.compile(r"\bdoors?\b|\bdoormen\b|\bdoorman\b", re.I), 0.25),
    "papers": (re.compile(r"\bpapers\b", re.I), 0.18),
    "half_four": (re.compile(r"\bhalf (?:past )?four\b|\b4[:.]?30\b", re.I), 0.03),
    "who_in_your": (re.compile(r"\bwho in your\b", re.I), 0.05),
    # 28 Oct (todo/51): "until it's too late to argue" came up in 3 of 40 offline reply-back drafts (live: 14 of 4,313 writes
    # in 24 h, 0.3%), so it is held to the budget of a stock phrase before it becomes one.
    "too_late": (re.compile(r"\btoo late to (?:argue|ask|object|change|take it back|say no)\b", re.I), 0.05),
    # 23 Oct hidden-post audit (docs/06-strategy/hidden-post-audit-2026-10-23.md): posts with one of these were hidden
    # 3-5x as often as the rest (since 21 Oct 12:00 UTC: closing "know anyone who moved from Yes" 7 of 131, a story of
    # someone who was Yes and is now No 9 of 264, a conceding opener 11 of 280; the other 2,116 writes 25). No share.
    "switch_close": (re.compile(r"(?:know|knows) (?:anyone|someone)[^?]*(?:yes|unsure|switch|moved|shift)"
                                r"|anyone[^?]{0,40}(?:moved|shifted|switched)"
                                r"|(?:moved|shifted|switched)[^?]{0,25}(?:yes|unsure)[^?]{0,20}\?", re.I), 0.0),
    "switch_story": (re.compile(r"(?:was|were|used to be|started)[^.?!]{0,30}(?:yes|unsure|undecided|leaning)"
                                r"[^.?!]{0,60}(?:now|then|until|till|switched|changed|came round)"
                                r"|(?:switched|moved|shifted|changed (?:her|his|their) mind)[^.?!]{0,30}(?:to|from)"
                                r"[^.?!]{0,20}\b(?:no|yes)\b|\bfrom (?:yes|unsure)[^.?!]{0,15}to no\b", re.I), 0.0),
    "concede_open": (re.compile(r"^[^.!?]{0,80}(?:would help|sounds (?:fair|sensible|good|reasonable)|fair "
                                r"(?:ask|enough|worry|point|question)|reasonable ask|makes sense|is fair|comfort"
                                r"|fair to want|good to want|good things? to want|worth wanting|sounds? (?:workable|right|solid)|sound right"
                                r"|(?:it|that|this) is workable|(?:it|that|this)'s workable)", re.I), 0.0),
}
TELL_KEYS = ("switch_close", "switch_story", "concede_open")      # share 0: never, whatever the window holds
PHRASE_PREFIX = "phrase_"


def budget_share(k):
    """The share of the window key k may take: PHRASE_BUDGETS', except "vote", read live from config.REPLY_VOTE_SHARE
    (todo/40) so a .env override reaches a bot that imported this module before the override was applied."""
    return config.REPLY_VOTE_SHARE if k == "vote" else PHRASE_BUDGETS[k][1]


def phrases_in(text):
    """The PHRASE_BUDGETS keys whose phrase text says."""
    return [k for k, (rx, _) in PHRASE_BUDGETS.items() if rx.search(text or "")]


def phrase_shares(texts):
    """{key: share of texts saying it} over texts (the measurement for todo/27)."""
    texts = list(texts)
    return {k: (sum(bool(rx.search(t or "")) for t in texts) / len(texts) if texts else 0.0)
            for k, (rx, _) in PHRASE_BUDGETS.items()}


# 2026-10-23: echoing a citizen's own word is not a template. 114 of the 118 phrase_sunset rejects in 24 h answered a
# citizen who had written "sunset" themselves (28% of the citizens we answer do: the Yes-buts ask for one), and the
# drafting prompt (content.worn_line) already lets a worn phrase through when they used it first, so the gate rejected
# what the prompt allowed. A draft may now say a budgeted word its citizen wrote, up to ECHO_CEILING times the budget
# (sunset: 10 of the last 100 texts for our own use, 15 in all). The ceiling keeps the global frequency of every phrase
# bounded, whoever wrote it first; the tells (share 0) and the vote line are never echo-exempt.
ECHO_CEILING = 1.5
ECHO_MAX_STACK = 2                  # a text with more worn phrases than this gets no echo allowance
ECHO_PATTERNS = {                   # the citizen's wording that makes our use of the key an echo (default: its own pattern)
    "sunset": re.compile(r"\bsunsets?\b", re.I),
    "end_date": re.compile(r"\bend[- ]dates?\b", re.I),
    "venue_list": re.compile(r"\bvenues? lists?\b|\blist of (?:venues|places)\b", re.I),
}
ECHO_KEYS = tuple(k for k, (_, share) in PHRASE_BUDGETS.items() if share > 0 and k != "vote")


def echoed(target_text):
    """The ECHO_KEYS the citizen's own post says: our draft may repeat those words (up to ECHO_CEILING)."""
    return tuple(k for k in ECHO_KEYS
                 if (ECHO_PATTERNS.get(k) or PHRASE_BUDGETS[k][0]).search(target_text or ""))


def _used(k, last):
    rx = PHRASE_BUDGETS[k][0]
    return sum(bool(rx.search(t or "")) for t in last)


def over_budget(text, window, exempt=(), echo=()):
    """The PHRASE_BUDGETS keys text would push over budget, given window (our latest citizen-facing texts, oldest
    first): with the draft as the newest of PHRASE_WINDOW texts, more than share * PHRASE_WINDOW would say it. A short
    window counts as full, so a fresh start isn't stricter than the budget. exempt: keys this draft may say anyway.
    echo: keys the citizen said first (echoed()): their budget is ECHO_CEILING times as big."""
    last = list(window)[-(PHRASE_WINDOW - 1):]
    out = []
    said = phrases_in(text)
    if sum(k in ECHO_KEYS for k in said) > ECHO_MAX_STACK:
        echo = ()                  # three worn phrases in one text is the hidden template itself: no echo allowance
    for k in said:
        if k in exempt:
            continue
        share = budget_share(k) * (ECHO_CEILING if k in echo and k in ECHO_KEYS else 1)
        if _used(k, last) + 1 > share * PHRASE_WINDOW:
            out.append(k)
    return out


def spent_phrases(window, target_text=""):
    """The budgeted words a draft to this citizen can't use right now (the window already holds as many as its budget
    allows, ECHO_CEILING times as many for a word the citizen wrote): [(key, label)], for the drafting prompt to keep
    off on the first draft instead of being rejected for them. Tells (share 0) are the prompts' own rules."""
    if window is None:
        return []
    last = list(window)[-(PHRASE_WINDOW - 1):]
    echo = echoed(target_text)
    return [(k, PHRASE_LABELS[k]) for k in ECHO_KEYS if k in PHRASE_LABELS
            and _used(k, last) + 1 > budget_share(k) * PHRASE_WINDOW * (ECHO_CEILING if k in echo else 1)]


PHRASE_LABELS = {"binds_us": "binds us", "no_review": "no review", "end_date": "end date",
                 "venue_list": "venue list", "sunset": "sunset", "after_the_vote": "after the vote",
                 "door": "the door", "papers": "papers", "half_four": "half past four", "who_in_your": "who in your"}


_VOTE_FILLER = set("that's thats that this it it's its why so which is and but then well yes yeah i i'm im i am will "
                   "i'll be still just here now on one for me too also as written definitely firmly simply all the a "
                   "referendum question ballot".split())


def only_states_vote(sentence):
    """True when the sentence says how we vote and next to nothing else ("That's why I'm voting No.")."""
    m = VOTES_NO.search(sentence or "")
    if not m:
        return False
    rest = re.findall(r"[a-z']+", (sentence[:m.start()] + " " + sentence[m.end():]).lower())
    return sum(w not in _VOTE_FILLER for w in rest) <= 1


_VOTE_WORDS = r"(?:i'?m |i am |i'?ll be |i will be |i )?(?:still )?(?:vot(?:e|ing)|mark(?:ing)?|tick(?:ing)?) no"
# "..., so I'm voting No." / "...; I'm voting No on this one." -> "..."
_VOTE_TAIL = re.compile(r"\s*(?:[,;:]|\s-)\s*(?:and |so |which is why |that'?s why |and that'?s why )?" + _VOTE_WORDS +
                        r"(?: on this(?: one)?| here| for (?:that|this))?\s*([.!]?)$", re.I)
# "I'm voting No because the rule..." / "Still voting No: one traveller..." -> "The rule..." / "One traveller..."
_VOTE_HEAD = re.compile(r"^(?:so |and |still )?" + _VOTE_WORDS + r"(?:\s*[:,]\s*(?:and |because )?|\s+-\s+|\s+because\s+)",
                        re.I)


def drop_vote(text, kind):
    """text without its statements of the vote (todo/27, a code fix for phrase_vote), or None: a sentence that only
    states it goes ("That's why I'm voting No."), a closing clause ("..., so I'm voting No.") or an opening one ("I'm
    voting No because the rule...") is cut. None when the vote is still there or what's left is under the kind's
    floor."""
    parts = sentences(TRAILING_TAGS.sub("", normalise(text)) if kind != "post" else text)
    if not any(VOTES_NO.search(s) for s in parts):
        return None
    kept = [s for s in parts if not only_states_vote(s)]
    out = []
    for s in kept:
        if VOTES_NO.search(s):
            cut = _VOTE_TAIL.sub(lambda m: m.group(1) or ".", s)
            if cut == s:
                cut = _VOTE_HEAD.sub("", s)
                cut = cut[:1].upper() + cut[1:]
            s = cut
        out.append(s)
    out = " ".join(s for s in out if s.strip())
    return out if out and len(out) >= LENGTHS[kind][0] and not VOTES_NO.search(out) else None


# todo/50 (prompt critique, 28 Oct): "You want X." opened 14% of replies; a list of their topic words ("Sunset, review,
# privacy.") the same way. Checked in a fixes block only (echo_open=True); fix() drops the opening clause.
ECHO_OPEN = re.compile(r"^(?:you(?:'re| are)? (?:want|wanting|after|asking for|need)\b|(?:[\w']+,\s){1,3}(?:and\s)?[\w']+\.\s)",
                       re.I)
VOICE_REPEAT = "voice_repeat_"


def check(text, kind, recent_texts=(), prompt_text="", target_text="", wants=(), closing_question=True, specific=True,
          same=(), phrase_texts=None, phrase_exempt=(), known_caps=(), mention=None, voice_texts=None, floor=None,
          echo_open=False):
    """kind: 'post' | 'reply' | 'second_voice' | 'reply_back' | 'journalist' | 'thread' | 'thread_answer'.
    same: our texts to this citizen or in this thread (todo/24), held to the strict near-duplicate threshold.
    phrase_texts: our latest citizen-facing texts (todo/27): a citizen-facing draft is held to PHRASE_BUDGETS over
    them. None: no budget (posts, threads, journalists, and callers that don't track them).
    closing_question=False lets a post end on its verdict instead (a draft told to end without a question).
    specific=False: todo/23's off-topic reply: needn't name an in-world fact, OFF_TOPIC_LEN characters, and no talk
    of the vote (VOTE_TALK) unless the citizen's own post has some.
    known_caps: the capitalised words of the system prompt (the voice's own people), for invented_name.
    mention: the one @username this reply is meant to name (todo/46, src/swan_bot/mention.py); that handle alone is allowed.
    todo/50 (a fixes block): voice_texts: the writing voice's own latest texts (memory.voice_repeat); floor: a lower
    length floor for this kind; echo_open: reject an opening that restates their topic (ECHO_OPEN)."""
    t = normalise(text)
    if kind != "post":
        t = TRAILING_TAGS.sub("", t).strip()
    if not t:
        return None, "empty"
    if ARTEFACT_START.search(t) or ARTEFACTS.search(t):
        return None, "llm_artefact"
    if FORBIDDEN.search(re.sub(rf"@{re.escape(mention)}\b", "", t, count=1, flags=re.I) if mention else t):
        return None, "forbidden_content"
    if content.advocacy(t):                    # todo/20: no vaccine advocacy until organiser Q3 is answered
        return None, "vaccine_advocacy"
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
    if kind == "post" and config.POST_NO_TAG_WITH_VOTE and TAG.search(t) and VOTES_NO.search(t):
        return None, "tag_with_vote"                  # todo/40: a hashtag and "I'm voting No" together; fix() cuts the tag
    if any(ord(ch) > 0x2600 for ch in t):        # emoji and other symbols
        return None, "emoji"
    if not specific and VOTE_TALK.search(t) and not VOTE_TALK.search(target_text or ""):
        return None, "off_topic_vote"
    if not specific and not OFF_TOPIC_LEN[0] <= len(t) <= OFF_TOPIC_LEN[1]:
        return None, f"off_topic_length_{len(t)}"
    lo, hi = LENGTHS[kind]
    lo = min(lo, floor) if floor else lo
    short_ok = kind != "post" and len(t) >= SHORT_OK and VOTES_NO.search(t)     # todo/20 G9: short but says No
    if specific and (len(t) > hi or (len(t) < lo and not short_ok)):     # off-topic: OFF_TOPIC_LEN, above
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
    if kind in NAME_CHECKED:
        name = invented_name(t, caps_in(prompt_text) | caps_in(target_text) | frozenset(known_caps))
        if name:
            return None, f"invented_name_{name}"
    if kind in ("reply", "journalist") and specific:   # second voices carry a set angle; off-topic replies (todo/23) none
        if not (FACT_ANCHORS.search(t) or FACT_PARAPHRASES.search(t) or any(w.lower() in t.lower() for w in wants)
                or touches_target(t, target_text)):
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
    if near_duplicate(body, kind, recent_texts, same):
        return None, "near_duplicate"
    if kind in PERSONAL_KINDS and BARE_OPEN.match(t) and not GROUP_WORDS.search(target_text or ""):
        return None, "bare_they_open"
    if kind in config.CONCEDE_CHECK_KINDS and conditional_yes(target_text) and conceding_sentence(t):
        return None, "concede_condyes"                # todo/51: granting a conditional Yes its conditions
    if kind in PERSONAL_KINDS:
        run = repeated_run(body, recent_texts, target_text)
        if run:
            return None, "repeat_run_" + run.replace(" ", "_").replace("'", "")
    if echo_open and kind in PERSONAL_KINDS and ECHO_OPEN.match(t):
        return None, "echo_open"
    if voice_texts and kind in PERSONAL_KINDS:
        run = memory.voice_repeat(body, voice_texts, target_text)
        if run:
            return None, VOICE_REPEAT + run.replace(" ", "_").replace("'", "")
    over = (over_budget(t, phrase_texts, phrase_exempt, echoed(target_text))
            if phrase_texts is not None and kind in PERSONAL_KINDS else [])
    if over:
        return None, PHRASE_PREFIX + "+".join(over)
    return t, None


# ---- code fixes (todo/20 G9: "we cannot afford a rejection"): a soft failure, or a made-up number, is fixed here with
# no LLM call when what's left still stands; bot.draft_checked runs the gate again on the result.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def sentences(text):
    return [s for s in _SENTENCE_END.split(normalise(text)) if s]


def trim(text, kind, hi=None, keep_no=True):
    """text cut at sentence boundaries to fit the kind's cap (or hi), or None: the last sentences go first, but never
    the opening one or (keep_no) one that says we're voting No; what's left must be over the floor and, if the draft
    said No, still say it."""
    lo, cap = LENGTHS[kind]
    hi = hi or cap
    parts = sentences(TRAILING_TAGS.sub("", normalise(text)) if kind != "post" else text)
    keep = [i == 0 or (keep_no and bool(VOTES_NO.search(s))) for i, s in enumerate(parts)]
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


_FILLER_OPEN = re.compile(r"^(?:sure|okay|ok|certainly|of course|absolutely)\b[,.!]?\s+", re.I)
_CONJ_OPEN = re.compile(r"^(?:and|but|so|or|well|then)\b[,]?\s+", re.I)


def _cap(text):
    text = _CONJ_OPEN.sub("", text.strip())
    return text[:1].upper() + text[1:]


def strip_filler(text):
    """text without a leading "Sure," / "Okay," (ARTEFACT_START reads it as the model talking to us; as a reply's first
    word it is only a casual opener), or None when there is none."""
    t = normalise(text)
    out = _cap(_FILLER_OPEN.sub("", t, count=1))
    return out if _FILLER_OPEN.match(t) and out else None


FIX_KEEPS = 0.55          # a sentence-dropping fix keeps at least this share of the characters, or the reply is gutted
_BACKREF = re.compile(r"^(?:that|this|those|these|it|which|so|such|then|there)\b", re.I)


def _without(parts, drop, kind):
    """The sentences `parts` without the indexes in `drop`, joined, or None when that would gut the reply: nothing to
    drop, under two sentences or FIX_KEEPS of the characters left, an opening shorter than 20 characters, a sentence
    left leaning on the one before it ("That's why..."), or under the kind's floor. For the fixes that drop sentences."""
    kept = [(i, s) for i, s in enumerate(parts) if i not in drop]
    if not drop or len(kept) < 2:
        return None
    if any(i - 1 in drop and _BACKREF.match(s) for i, s in kept) or (kept[0][0] > 0 and len(kept[0][1]) < 20):
        return None
    out = _cap(" ".join(s for _, s in kept))
    if len(out) < FIX_KEEPS * len(" ".join(parts)) or len(out) < LENGTHS[kind][0]:
        return None
    return out


def drop_phrase_sentences(text, keys, kind):
    """text without the sentences that say one of the budgeted phrases `keys` (0.0-share conceding openers only count
    in the first sentence, as the pattern does), or None when no sentence says one on its own or what's left is under
    the kind's floor. A code fix for phrase_<keys> (2026-10-23): the gate checks what's left again."""
    parts = sentences(TRAILING_TAGS.sub("", normalise(text)))
    drop = {i for i, s in enumerate(parts)
            if any(PHRASE_BUDGETS[k][0].search(s) and (k != "concede_open" or i == 0)
                   for k in keys if k in PHRASE_BUDGETS)}
    return _without(parts, drop, kind)


def drop_clash(text, kind, recent=(), same=()):
    """text without the sentences that repeat our earlier wording (5-word runs shared with recent / same, the
    near_duplicate measure), the most-shared sentence first, until it no longer counts as a near duplicate; or None
    when that can't be done above the kind's floor. A code fix for near_duplicate (2026-10-23)."""
    parts = sentences(TRAILING_TAGS.sub("", normalise(text)) if kind != "post" else text)
    old = set()
    for o in list(recent)[-300:] + list(same):
        old |= _shingles(strip_tag(o.strip()))
    drop = set()
    while len(drop) < len(parts) - 1:
        left = " ".join(s for i, s in enumerate(parts) if i not in drop)
        if not near_duplicate(strip_tag(left), kind, recent, same):
            break
        score = {i: len(_shingles(s) & old) for i, s in enumerate(parts) if i not in drop}
        worst = max(score, key=lambda i: (score[i], -i))
        if not score[worst]:
            return None
        drop.add(worst)
    out = _without(parts, drop, kind)
    return out if out and not near_duplicate(strip_tag(out), kind, recent, same) else None


def fix(text, why, kind, recent=(), same=()):
    """A code fix for a rejected draft (no LLM call), or None when this reason has none or nothing usable is left.
    Too long -> trim; same opening -> drop the first clause; an unapproved number -> drop its sentence; 2026-10-23: a
    leading "Sure," goes; a budgeted phrase (or a conceding opener) -> drop the sentences saying it; near_duplicate ->
    drop the sentences that repeat our earlier wording (recent / same: our texts, as for check); todo/51: a conceded
    conditional Yes -> keep what follows its "but", or drop the sentence."""
    why = why or ""
    if why == "llm_artefact":
        return strip_filler(text)
    if why == "tag_with_vote":                     # todo/40: the post keeps its statement of the vote and loses the hashtag
        out = strip_tag(normalise(text)).strip()
        return out if out != normalise(text) else None
    if why == "near_duplicate" and kind in PERSONAL_KINDS:
        return drop_clash(text, kind, recent, same)
    if why.startswith("length_") and int(why.split("_")[1]) > LENGTHS[kind][1]:
        return trim(text, kind)
    if why == "off_topic_vote":                    # todo/23: their topic only; the sentences about the vote go
        parts = [s for s in sentences(text) if not VOTE_TALK.search(s)]
        out = " ".join(parts)
        return out if parts and len(out) >= OFF_TOPIC_LEN[0] else None
    if why.startswith("off_topic_length_") and int(why.rsplit("_", 1)[1]) > OFF_TOPIC_LEN[1]:
        return trim(text, kind, hi=OFF_TOPIC_LEN[1], keep_no=False)
    if why in ("same_opening", "echo_open"):
        return drop_first_clause(text)
    if why == "concede_condyes":                   # todo/51: what follows the "but", or the sentence goes
        return drop_concession(text, kind)
    if why.startswith(VOICE_REPEAT) and kind in PERSONAL_KINDS:      # todo/50: the voice's own script goes
        run = why[len(VOICE_REPEAT):].replace("_", " ")
        parts = sentences(TRAILING_TAGS.sub("", normalise(text)))
        drop = {i for i, s in enumerate(parts) if run in " ".join(re.findall(r"[a-z']+|\d+", s.lower()))}
        return _without(parts, drop, kind) if drop and len(drop) < len(parts) else None
    if why.startswith("unapproved_number_"):
        return drop_number(text, why[len("unapproved_number_"):], kind)
    if why == "vaccine_advocacy":
        parts = [s for s in sentences(text) if not content.advocacy(s)]
        out = " ".join(parts)
        return out if parts and len(out) >= min(LENGTHS[kind][0], SHORT_OK) else None
    if why.startswith(PHRASE_PREFIX):
        keys = why[len(PHRASE_PREFIX):].split("+")
        if "vote" in keys:                                                                  # todo/27
            return drop_vote(text, kind)
        if kind in PERSONAL_KINDS:
            return drop_phrase_sentences(text, keys, kind)
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


def shared_wording(raw, olds, n=5, limit=2):
    """The longest runs of words the draft shares with the texts `olds` (n-word runs merged), at most `limit`, longest
    first: what a near_duplicate repair has to say differently. [] when they share none."""
    words = re.findall(r"[a-z']+", strip_tag(normalise(raw)).lower())
    old = set()
    for o in olds:
        old |= _shingles(strip_tag(o.strip()), n)
    covered = [" ".join(words[i:i + n]) in old for i in range(len(words) - n + 1)]
    mask = [False] * len(words)
    for i, c in enumerate(covered):
        if c:
            mask[i:i + n] = [True] * n
    runs, cur = [], []
    for w, c in zip(words + [""], mask + [False]):
        if c:
            cur.append(w)
        elif cur:
            runs.append(" ".join(cur))
            cur = []
    return sorted(runs, key=lambda r: -len(r))[:limit]


def their_words(target_text, k=2):
    """Up to k distinctive words of the citizen's post, in their spelling, longest first: what a not_specific repair
    tells the model to pick up (the same stems touches_target compares)."""
    text = re.sub(r"https?://\S+", " ", target_text or "")
    skip = {w.rstrip("s")[:6] for w in _ECHO_STOP}
    seen, out = set(), []
    for w in re.findall(r"[A-Za-z']{5,}", text):
        stem = w.lower().rstrip("s")[:6]
        if stem in skip or stem in seen or stem.startswith("exempt") or POLICY_WORDS.fullmatch(w) or any(
                rx.search(w) for rx, _ in PHRASE_BUDGETS.values()):
            continue
        seen.add(stem)
        out.append(w)
    return sorted(out, key=lambda w: -len(w))[:k]


_THINKING = re.compile(r"^\W*(?:the user|let me|i need to|okay, so|first,? i|looking at|analy[sz]e)", re.I)


def repair_note(why, raw, kind, tag=None, recent=(), target_text="", wants=(), same=(), phrase_texts=None):
    """What to tell the model to fix in a rejected draft, or None (then the retry is a fresh draft). todo/20 G9: every
    reason a draft fails on in practice has a note, so a retry gets the exact problem, not a fresh roll.
    2026-10-23: the note is targeted. target_text / wants: the citizen's post and what they asked for (not_specific
    names their words, a phrase repair says whose word it was); recent / same: our texts (near_duplicate quotes the
    wording that repeats); phrase_texts: the phrase window, so a note doesn't send the model to a word that is spent."""
    why = why or ""
    if why == "near_duplicate":
        olds = list(same) + list(recent)
        old = _close_to(raw, olds)
        runs = shared_wording(raw, olds)
        opening = " ".join(re.findall(r"[a-z']+", normalise(raw).lower())[:4])
        same_open = [o for o in olds[-30:] if " ".join(re.findall(r"[a-z']+", o.lower())[:4]) == opening]
        return ("This is too close to something we already posted" + (f", which went: «{old[:200]}»" if old else "") +
                (f". The repeated wording is {' and '.join(f'«{r}»' for r in runs)}: say that point another way, or "
                 f"leave it out" if runs else "") +
                (f". Don't open with «{opening}» again" if same_open else "") +
                ". Use a different opening, a different detail from your own life and different words.")
    if why == "same_opening":
        return "Start with different words: the first four words are the same as something we already posted."
    if why.startswith("unapproved_number_"):
        return (f"Remove the number {why[len('unapproved_number_'):].rstrip(',.')}: use no number except the ones you "
                f"were given, as digits.")
    if why.startswith("repeat_run_"):
        run = why[len("repeat_run_"):].replace("_", " ")
        return (f"The words «{run}» are in something we already posted, so a reader sees one script. Make the same "
                f"point in different words, or make a different one; keep the rest. Say who or what you mean in the "
                f"first sentence (the government, the plan, the list): never start on They, Them or Those.")
    if why.startswith(VOICE_REPEAT):
        run = why[len(VOICE_REPEAT):].replace("_", " ")
        return (f"You have said «{run}» to many people today; nobody tells the same story to every stranger. Say "
                f"something else in its place, or leave that part out; keep the rest.")
    if why == "echo_open":
        return ("Don't open by naming their topic back to them in a few words. Start on a full sentence of your own "
                "that answers them; keep the rest.")
    if why == "concede_condyes":
        said = conceding_sentence(raw)
        return ((f"Cut «{said[:160]}»: " if said else "Cut the part that grants their conditions: ") +
                "don't say their sunset, list or safeguards would help, sound fair or would make a Yes fine. Say plainly "
                "that they aren't in what we're voting on, or answer something else they said. Keep the rest.")
    if why == "bare_they_open":
        return ("The reply starts on They, Them or Those with nobody for it to mean. Start again from the citizen's "
                "own point, naming who or what you mean (the government, the plan, the list). Keep the rest.")
    if why.startswith("invented_name_"):
        return (f"Cut the name {why[len('invented_name_'):]}: you don't know anyone by that name. Name only the people "
                f"in your profile, or no one (say 'a neighbour' or 'my colleague'). Keep the rest.")
    if why == "not_specific":
        spent = {k for k, _ in spent_phrases(phrase_texts, target_text)}
        ask = [w for w in wants if w and not any(PHRASE_BUDGETS[k][0].search(w) for k in spent)][:2]
        mine = their_words(target_text)
        theirs = (f"Use their own word {' or '.join(f'«{w}»' for w in (ask or mine))}, and " if (ask or mine) else
                  "Use a word or two of theirs, and ")
        return (theirs + "say which part of the rule bears on it (who has to check at the door, which places the "
                "question doesn't name, how long it lasts, who would staff it, or what the news says) in plain words. "
                "Keep the rest.")
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
    if why == "vaccine_advocacy":
        return (f"Cut «{content.advocacy(raw)}»: don't urge anyone to get vaccinated or praise the vaccine; this vote "
                f"is only about the pass. Keep the rest.")
    if why == "emoji":
        return "Remove the emoji and symbols."
    if why == "off_topic_vote":
        return "Stay on their topic: don't mention the vote, the referendum, the jab or the pass at all. Keep the rest."
    if why.startswith("off_topic_length_"):
        n = int(why.rsplit("_", 1)[1])
        return (f"Too long ({n} characters): 1 or 2 short sentences, under 35 words." if n > OFF_TOPIC_LEN[1] else
                None)
    if why == "llm_artefact":
        if _THINKING.match(raw or "") or (raw or "").lstrip().startswith("{"):
            return None       # the model's notes to itself (or a JSON shell), not a draft: a fresh draft does better
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
    if why == "tag_with_vote":
        return "Remove the hashtag: end on your question, with no hashtag. Change nothing else."
    if why.startswith(PHRASE_PREFIX):              # todo/27: name each worn phrase as the draft has it
        keys = why[len(PHRASE_PREFIX):].split("+")
        said = [m.group(0) for k in keys if k in PHRASE_BUDGETS
                for m in [PHRASE_BUDGETS[k][0].search(normalise(raw))] if m]
        quoted = " or ".join(f"«{p}»" for p in said) or "our usual phrases"
        if all(k in TELL_KEYS for k in keys):
            return (f"Cut {quoted}. Don't open by granting their point, don't ask whether they know anyone who has "
                    f"moved from Yes to No, and don't tell of anyone who was Yes and switched. Start from your own "
                    f"point and end on your reason. Change nothing else.")
        theirs = [k for k in keys if k in echoed(target_text)]
        them = "them" if len(said) > 1 else "it"
        note = (f"We've said {quoted} too often lately: make the point without {them}, in words of your own"
                + (" (\"time limit\" works)" if "sunset" in keys else "")
                + (f". They wrote that word themselves, so answer what they asked for without repeating {them}"
                   if theirs else "") + ".")
        if "vote" in keys:
            note += " Don't state your vote at the end: end on your reason."
        return note + " Change nothing else."
    if why == "spelled_number":
        return "Write every number as digits, and only the numbers you were given."
    return None
