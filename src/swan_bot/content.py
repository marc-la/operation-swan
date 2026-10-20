"""What we say: world facts, frames (arguments), personas, Yes rebuttals, and the prompts built from them.

Humans own this file. Frames: docs/06-strategy/frames-and-messengers.md. How to say it (hooks, catchphrases, tags,
voices, post anatomy, reply shape): docs/06-strategy/message-playbook.md. Facts: docs/01-competition/setting.md.
Content v2 data (swan_bot/playbook/: craft, voices, characters) is copied onto FRAMES and PERSONAS at import; a
missing module falls back to the v1 behaviour. Every fact here is true in-game. Careful: medical exemptions ARE in
the plan, the certificate is separate from the ID card, and the H2D2 jab isn't out yet (first doses: last week of
October). Never claim otherwise.
"""
import itertools
import random
import re

from . import experiment

try:
    from .playbook import craft as _craft
except ImportError:
    _craft = None
try:
    from .playbook import voices as _voices
except ImportError:
    _voices = None
try:
    from .playbook import characters as _characters
except ImportError:
    _characters = None

QUESTION = ("Should proof of H2D2 Dolphin Flu vaccination be required to enter public spaces "
            "such as shops, schools, workplaces, public transport, and parks?")

FACTS = {
    "list_later": "Designated public spaces: list set by regulation after the vote; not published yet.",
    "no_end": "Ballot question: no end date; no mention of any review or reviewer. A Yes result is binding.",
    "phased": "After a Yes: requirement brought in by regulation, in stages.",
    "exemptions": "Medical exemptions: yes, in the plan. Under-12s: exempt. End date and venue list: not in the plan.",
    "free_either_way": "Vaccine: free, voluntary, available whatever the result. A No stops nobody getting it.",
    "first_doses": "First 120,000 doses: last week of October; earmarked for health workers and high-risk people.",
    "age12": "Requirement covers ages 12 and up: school, work, public transport.",
    "nurses": "Kingstonia Central Hospital: 40 unfilled nursing posts. Nurses earn about double in Australia/NZ.",
    "no_spread": "H2D2 in Kingstonia: no community spread so far.",
    "islands": "Outer islands: nurse-led clinics, GP visits weekly, ferry K$14.",
    "childhood": "Childhood vaccines: free, most kids get them, no certificate check needed.",
    "visitors": "Foreign visitors: covered by the requirement too.",
    "covid_business": "COVID years: tourism collapsed, small businesses closed, families kept apart.",
    "id_card": "Certificate: separate from the new biometric ID card; current law keeps health records off the card (laws can change).",
    "no_binds": "After a No: no access requirement for the life of this Assembly without a fresh referendum.",
    "bill_failed": "Last week: Assembly voted the bill down; several of the President's own People's Alliance members joined the Democratic-Republicans.",
}

# The same facts as terse notes, which is how prompts show them (todo/14): facts written as polished sentences got
# pasted into drafts word for word. quality.py still checks copying against the full FACTS sentences.
FACT_NOTES = {
    "list_later": "venue list: decided after the vote, by regulation; unpublished",
    "no_end": "no end date or review in the question; a Yes is binding",
    "phased": "brought in by regulation, in stages",
    "exemptions": "medical exemptions in; under-12s exempt; no end date, no venue list",
    "free_either_way": "jab free and voluntary either way; a No blocks nobody's jab",
    "first_doses": "first 120,000 doses, last week of October, for health workers and the high-risk",
    "age12": "covers 12 and over: school, work, buses",
    "nurses": "Central: 40 nursing posts unfilled; pay about double in Australia or NZ",
    "no_spread": "no community spread yet",
    "islands": "outer islands: nurse-led clinics, GP weekly, K$14 ferry",
    "childhood": "childhood jabs free, most kids have them, no certificate check",
    "visitors": "foreign visitors covered too",
    "covid_business": "COVID years: tourism gone, small shops shut, families apart",
    "id_card": "certificate separate from the biometric ID card; law keeps health records off it (laws change)",
    "no_binds": "after a No: no pass this Assembly term without a new referendum",
    "bill_failed": "Assembly voted the bill down last week, some of the President's own party too",
}

# Each frame: the point to make, the facts it may lean on, its weight for persona posts,
# and the frame(s) a second persona uses on the same doubt (a different angle, never a repeat; a list = pick one).
# `gist` is the angle as a short note, which is what the prompts show (todo/14: the full angle got copied); quality.py
# checks copying against the full angle.
FRAMES = {
    "F14_no_yes_but": dict(
        angle="the conditions people want before saying yes (an end date, the list of places, someone independent "
              "reviewing it) are not in the question (medical exemptions are, but only bring that up if they mentioned "
              "exemptions); so a Yes can't carry anyone's 'but'",
        gist="what people want before a Yes (end date, venue list, a review) isn't in the question, so a Yes can't "
             "carry their 'but' (exemptions are in: raise them only if they did)",
        facts=["no_end", "list_later"], weight=3,     # "exemptions" out: posts volunteered "under-12s exempt"
        second=["F1_blank_cheque", "F3_provax_antipass", "F2_no_end"]),
    "F1_blank_cheque": dict(
        angle="the list of places the rule covers is only decided after the vote, so a Yes means agreeing before "
              "anyone can see what was agreed; if you don't know, it's fine to say No",
        gist="places are picked after the vote: a Yes is signing before you see it; unsure means No",
        facts=["list_later", "phased"], weight=3, second="F14_no_yes_but"),
    "F2_no_end": dict(
        angle="nothing in the question says when the rule ends, and 'temporary' only counts if it is written down",
        gist="no end date in the question; temporary only counts on paper",
        facts=["no_end", "no_binds"], weight=2, second="F1_blank_cheque"),
    "F3_provax_antipass": dict(
        angle="whether and when you get the jab is your own business, and it stays free either way; this vote is "
              "only about papers at the door, and a choice that costs you your bus, your shift or your kid's school "
              "isn't a choice (don't praise vaccines: that's not the argument)",
        gist="your jab, your call, free either way; the vote is only the pass, and a choice that costs your job or "
             "bus is no choice (don't praise vaccines)",
        facts=["free_either_way", "age12"], weight=1, second="F1_blank_cheque"),
    "F8_powers": dict(
        angle="the certificate is meant to stay separate from the new biometric ID card, and today's law says so, "
              "but laws change and once a check is at every door it is easy to join things up later",
        gist="kept off the ID card by today's law, but laws change once every door has a check",
        facts=["id_card", "no_end"], weight=1, second="F14_no_yes_but"),
    "F10_staff_and_livelihoods": dict(
        angle="hospitals matter, and the real pressure is staff: a certificate check at a shop door does not fill one "
              "of Kingstonia Central's 40 empty nursing posts; meanwhile the door check lands on ordinary jobs "
              "(name one from your own life)",
        gist="the hospital gap is staff, and a door check fills no nursing post; it lands on ordinary jobs (name one)",
        facts=["nurses", "first_doses"], weight=2, second="F3_provax_antipass"),
    "F13_age12": dict(
        angle="the rule covers everyone from age 12, at school and on the bus, and nobody can yet say which "
              "places will count",
        gist="everyone from 12, school and bus, and nobody knows which places yet",
        facts=["age12", "list_later", "childhood"], weight=1, second="F1_blank_cheque"),
    "F6_islands": dict(
        angle="a free choice that comes with a certificate is harder for some people than others: on the outer "
              "islands the clinic is nurse-led with a GP once a week and the ferry costs K$14",
        gist="a free choice plus a certificate costs more out on the islands (weekly GP, K$14 ferry)",
        facts=["islands", "list_later"], weight=1, second="F14_no_yes_but"),
    "F7_livelihoods": dict(
        angle="shop, cafe and ferry staff would end up checking papers at the door, visitors would need one too, "
              "and we all remember what the last restrictions did to small businesses",
        gist="shop, cafe and ferry staff end up on the door, visitors too; remember what COVID did to small shops",
        facts=["visitors", "covid_business", "list_later"], weight=1, second="F1_blank_cheque"),
    "F5_not_here_yet": dict(
        angle="there is no community spread here yet and the first doses already go to health workers and people "
              "at high risk, so a certificate at every shop and park is a big step for now",
        gist="not here yet, the at-risk get the first doses: a pass at every shop is too big a step for now",
        facts=["no_spread", "first_doses"], weight=1, second="F14_no_yes_but"),
    "F9_parliament": dict(
        angle="the Assembly already said no last week, with some of the President's own party voting it down; "
              "this isn't a party thing, plenty of people who voted Hawthorne are voting No",
        gist="the Assembly already said no, the President's own people too; not a party thing",
        facts=["bill_failed", "no_binds"], weight=1, second="F1_blank_cheque"),
    "F12_open_island": dict(
        angle="keep Kingstonia open: the ordinary island life you love (name it) shouldn't need papers at the door, "
              "and the vaccine is free and yours to choose either way",
        gist="everyday island life (name it) shouldn't come with papers; the jab's yours to choose",
        facts=["free_either_way", "covid_business", "no_spread"], weight=2, second="F1_blank_cheque"),
}

# Yes arguments citizens repeat, and our answer (grant the concern first). Added to reply prompts when matched.
REBUTTALS = [
    (re.compile(r"hospital|ward|icu|overwhelm|surge|capacity|frontline|vulnerable|protect", re.I),
     "Their reason is fear for the hospitals and the vulnerable. Answer that fear, warmly, with ONE of these: H2D2 "
     "puts mostly older or already-ill people in hospital, and they get the first doses / a pass at the shop door "
     "adds no nurse and no bed / Central already has 40 empty nursing posts."),
    (re.compile(r"last time|covid|1,?000|died|deaths", re.I),
     "Their reason is the memory of COVID. Honour it in a few words. Then ONE of these: this time the jab arrives "
     "before the virus, at-risk first / a No doesn't stop a single dose / this vote is only the pass at the door."),
    (re.compile(r"choice stays|still (a|your) choice|voluntary", re.I),
     "They say the choice stays yours. A choice that costs you your job, your bus or your kid's school isn't much of a choice."),
    (re.compile(r"before it (gets|arrives)|act now|prepare|ready", re.I),
     "They want to act early. We are: 120,000 doses land this month for health workers and the at-risk, and a No doesn't stop a single jab."),
    (re.compile(r"\biho\b|world health|experts? (say|recommend)|doctors? say", re.I),
     "They cite expert advice. Don't attack doctors; the advice is about getting vaccinated, which a No doesn't stop."),
    (re.compile(r"resort|profit|castillo|kitb|tourism board", re.I),
     "They distrust the tourism board. Don't defend Castillo or the resorts; speak only for yourself and your own job."),
]

# One persona per account, registered in this order (the first ones cover the most common citizen doubts).
# 'details' give local, specific colour so a post reads like a real person on Kingstonia, not a slogan.
PERSONAS = [
    dict(key="lani", name="Lani Moana", handle="lani_wharfcafe", role="runs a small cafe by the Crown Harbour wharf",
         place="Crown Harbour", voice="chatty and warm",
         details=["serves flat whites at K$5.50 to the early ferry crowd", "two staff, both students",
                  "half her trade is tourists off the boats"],
         frames=["F14_no_yes_but", "F7_livelihoods", "F12_open_island"]),
    dict(key="priya", name="Priya Rao", handle="priya_rao_chemist", role="community pharmacist",
         place="Crown Harbour", voice="careful, explains things simply",
         details=["gets asked about H2D2 at the counter every day", "is vaccinated and will get this one too"],
         frames=["F3_provax_antipass", "F14_no_yes_but"]),
    dict(key="isla", name="Isla Park", handle="isla_park_ku", role="university student who works weekends in a cafe",
         place="Kingstonia City", voice="casual, a bit dry",       # humanize.py types her drafts in lowercase
         details=["studies law at KU", "catches the city loop bus to campus", "works weekend shifts at a cafe near campus"],
         frames=["F14_no_yes_but", "F8_powers", "F2_no_end"]),
    dict(key="josh", name="Josh Kendall", handle="josh_k_sparky", role="electrician who works all over the island",
         place="Kingstonia City", voice="blunt, down to earth, short sentences",
         details=["wires shops and cafes for a living", "voted Hawthorne last year"],
         frames=["F1_blank_cheque", "F9_parliament", "F2_no_end"]),
    dict(key="ana", name="Ana Fifita", handle="ana_fifita_rn", role="ward nurse at Kingstonia Central Hospital",
         place="Kingstonia City", voice="tired but kind, plain words",
         details=["works night shifts on a short-staffed ward", "two colleagues left for jobs in New Zealand this year"],
         frames=["F10_staff_and_livelihoods", "F3_provax_antipass"]),
    dict(key="mere", name="Mere Tuhaka", handle="mere_t_nana", role="retired, looks after her grandkids",
         place="Kingstonia City", voice="gentle, a bit wry",
         details=["walks her grandson to school", "her granddaughter turns 12 soon"],
         frames=["F13_age12", "F14_no_yes_but"]),
    dict(key="ben", name="Ben Tavake", handle="ben_tavake_fish", role="fisherman who sells at the Saturday market",
         place="New Haven", voice="laconic, short sentences",
         details=["sells tuna at the New Haven Saturday market", "out on the boat before dawn"],
         frames=["F5_not_here_yet", "F1_blank_cheque", "F12_open_island"]),
    dict(key="sione", name="Sione Latu", handle="sione_islandclinic", role="nurse at an outer-island clinic",
         place="the outer islands", voice="direct, practical",
         details=["the GP visits his clinic once a week", "patients come over on the K$14 ferry"],
         frames=["F6_islands", "F10_staff_and_livelihoods"]),
    dict(key="dan", name="Daniel Okafor", handle="dan_okafor_bus", role="bus driver on the city loop",
         place="Kingstonia City", voice="dry humour, practical",
         details=["drives the city loop past the hospital and the markets", "would be the one checking papers on the bus"],
         frames=["F1_blank_cheque", "F7_livelihoods", "F9_parliament"]),
    dict(key="grace", name="Grace Holloway", handle="grace_h_teaches", role="secondary school teacher",
         place="Kingstonia City", voice="calm, thinks about kids and families",
         details=["teaches Year 8, mostly 12 and 13 year olds", "runs the school sailing club"],
         frames=["F13_age12", "F3_provax_antipass"]),
    dict(key="tomasi", name="Tomasi Vea", handle="tomasi_ferryhand", role="deckhand on the outer-island ferry",
         place="the outer islands", voice="short and practical",
         details=["works the morning ferry run", "sees the same families every week heading to the clinic"],
         frames=["F6_islands", "F12_open_island"]),
    dict(key="ruth", name="Ruth Seumanu", handle="ruth_s_agedcare", role="aged-care worker",
         place="Crown Harbour", voice="caring, specific about her residents",
         details=["her residents are first in line for the new doses", "is vaccinated herself"],
         frames=["F5_not_here_yet", "F3_provax_antipass"]),
]
PERSONA_BY_KEY = {p["key"]: p for p in PERSONAS}

# ---- Content v2 merge (playbook §2-6): craft onto FRAMES, voices + characters onto PERSONAS. Copies only: the
# playbook modules' own dicts and lists are never changed. Each missing module falls back to v1 behaviour.
PILLAR_OF = {"F14_no_yes_but": "A", "F1_blank_cheque": "A", "F2_no_end": "A", "F9_parliament": "A", "F8_powers": "A",
             "F7_livelihoods": "B", "F13_age12": "B", "F6_islands": "B", "F10_staff_and_livelihoods": "B",
             "F12_open_island": "B", "F3_provax_antipass": "C", "F5_not_here_yet": "C"}
_PILLARS_V1 = {
    "A": dict(name="Don't sign a blank cheque", tags=["#VoteNo", "#H2D2No"], catchphrases=[]),
    "B": dict(name="Ordinary life shouldn't need papers", tags=["#KeepKingstoniaOpen", "#SmallBusiness", "#WorkersRights"],
              catchphrases=[]),
    "C": dict(name="Jabbed, and voting No", tags=["#ChoiceNotCoercion"], catchphrases=[]),
}
_VOICES_V1 = {r: dict(instruction="You are cheerful and reasonable, never angry.", reply_instruction="")
              for r in ("warm", "fed_up", "plain")}
CHARACTER_FIELDS = ("age", "people", "problem", "covid", "arc", "lines", "now")
_LIST_FIELDS = {"people", "lines", "now"}
HEALTH_WORKERS = {"ana", "sione", "ruth", "priya"}      # the only ones who may say they're in the first lot of doses
PILLARS, VOICES, CATCHPHRASE_SHARE = {}, {}, 0.33


def merge_playbook(craft=None, voices=None, characters=None):
    """Copy the playbook data onto FRAMES, PERSONAS, PILLARS and VOICES. Idempotent; run at import."""
    global PILLARS, VOICES, CATCHPHRASE_SHARE
    PILLARS = {k: dict(v, tags=list(v["tags"]), catchphrases=list(v.get("catchphrases") or []))
               for k, v in getattr(craft, "PILLARS", _PILLARS_V1).items()}
    VOICES = {k: dict(v) for k, v in getattr(voices, "VOICES", _VOICES_V1).items()}
    CATCHPHRASE_SHARE = getattr(craft, "CATCHPHRASE_SHARE", 0.33)
    per_frame = getattr(craft, "CRAFT", {})
    for key, f in FRAMES.items():
        c = per_frame.get(key, {})
        f.update(pillar=c.get("pillar", PILLAR_OF[key]), stakes=list(c.get("stakes") or []), heat=c.get("heat"),
                 asks=list(c.get("asks") or []))
    voice_of, chars = getattr(voices, "VOICE_OF", {}), getattr(characters, "CHARACTERS", {})
    for p in PERSONAS:
        p["register"] = voice_of.get(p["key"], "warm") if voice_of.get(p["key"], "warm") in VOICES else "warm"
        c = chars.get(p["key"], {})
        for k in CHARACTER_FIELDS:
            v = c.get(k)
            p[k] = list(v or []) if k in _LIST_FIELDS else v


merge_playbook(_craft, _voices, _characters)

# Kept out of every prompt: a claim that someone has had the H2D2 jab (it isn't out yet), and the off-limits names.
_OFF_LIMITS = re.compile(r"\b(had|got|received|given)\b[^.]{0,25}\b(doses?|jabs?|shots?)\b|resort|castillo|tourism board",
                         re.I)


# `now` events are drafted for the whole fortnight, but the prompt says the jab isn't out: no dose events at all.
_NOW_OFF = re.compile(r"\bdoses?\b|\b(had|got) (theirs|hers|his|mine|ours)\b|\bjabbed\b", re.I)


def usable(texts, now=False):
    """The entries that are safe to put in a prompt (`now`: also no dose events)."""
    return [t for t in texts or [] if t and not _OFF_LIMITS.search(t) and not (now and _NOW_OFF.search(t))]


_DANGLING = re.compile(r"(\s+(the|a|an|of|to|at|on|in|for|and|or|but|with|where|who|which|that|his|her|their|"
                       r"its|by|from|as|so|is|was|has|had|he|she|they|it|we|i|just|only|even|then|also|still))+$", re.I)


_OPEN_CLAUSE = re.compile(r",?\s+(who|whose|where|which|that|and|but|so|while|when|because|if|until)\b[^,;]*$", re.I)


def clip(text, n, keep=0.5):
    """At most n characters, ending in a full stop: cut at a sentence end, else a clause, else a word (a cut that
    keeps under `keep` of n tries the next, finer level)."""
    text = (text or "").strip()
    if len(text) > n:
        for pattern in (r"(?<=[.!?])\s+", r"(?<=[,;:])\s+", r"\s+"):
            out = ""
            for piece in re.split(pattern, text):
                if len(out) + len(piece) + 1 > n:
                    break
                out = f"{out} {piece}".strip()
            if len(out) >= n * keep or pattern == r"\s+":
                if pattern == r"\s+":            # mid-clause: back off to before an unfinished "who ..." clause
                    m = _OPEN_CLAUSE.search(out)
                    out = _DANGLING.sub("", out[:m.start()] if m and m.start() >= n * keep else out)
                text = out.rstrip(",;:") or text[:n]
                break
    return text if not text or text[-1] in ".!?" else text + "."


# Post opening styles (playbook §5 hook types), one picked per draft so 12 accounts don't share a structure. The
# react-to-news style must stay LAST and is the only one with {headline} (batch.py uses POST_SHAPES[:-1] and [-1]).
POST_SHAPE_KEYS = ["asked_me", "named_loss", "conversion", "confession", "number", "did_you_know", "fed_up",
                   "defiance", "news"]
POST_SHAPES = [
    "Open with a question someone in your life asked you this week about the vote (a customer, a kid, a patient, "
    "a workmate: name them), then give them your honest answer.",
    "Open with a named person or place from your own life and the ordinary thing they would lose under a Yes, all "
    "in the first sentence.",
    "Open with the moment you changed your mind: you were leaning Yes, or meant to stay out of it, until one detail "
    "of what we're voting on turned you. Name the moment and the detail.",
    "Open by saying who you are in one short line (your job, where you stand on the jab, and that you're voting No "
    "anyway), then say why.",
    "Open with one number from your facts, on its own or in a very short sentence, then say what it means for "
    "someone you know.",
    "Open by pointing out one thing most people haven't noticed about what we're voting on (one of your facts), "
    "then show what it means for someone you know.",
    "Open with one short, blunt line of exasperation at the rule or the way it's being pushed through (at the rule "
    "and the government, never at people), then the facts that make you say it.",
    "Open with cheerful defiance: something you love doing on the island this fortnight, and that you won't be "
    "checking anyone's papers for it. Stay sunny about the island and sharp about the rule.",
    "Open by reacting briefly to today's news ({headline}), in your own words, then bring it back to your own life.",
]
HOOKS = dict(asked_me="someone asked me", named_loss="named loss", conversion="conversion",
             confession="confession / identity", number="number", did_you_know="did you know", fed_up="fed up",
             defiance="cheerful defiance", news="react to news")

FIRST_NAMES = {3: "Amanda", 4: "Muzhi", 5: "Julio", 6: "Lisa"}
# Journalist replies rotate through these (each true in setting.md), so the papers don't hear one line from us.
STORYLINES = [
    ("list_later", "voters are being asked to approve the rule before the government publishes which places it "
                   "covers; both campaigns have criticised it for not publishing that list before the vote"),
    ("vaxxed_no", "plenty of vaccinated people are voting No: the jab is free and voluntary whatever the result, and "
                  "this vote is only about a certificate at the door"),
    ("assembly", "the Assembly voted the bill down on 15 Oct, with several of the President's own People's Alliance "
                 "members joining the Democratic-Republicans, and now the same rule comes back as a binding vote"),
    ("nurses", "the health system's real gap is staff: Kingstonia Central has 40 unfilled nursing posts because a "
               "nurse earns about double in Australia or NZ, and a certificate check at a shop door fills none of them"),
    ("no_end", "nothing in the question says when the rule would end, and a Yes result is binding"),
    ("door_staff", "shop, cafe and ferry staff would be the ones checking papers at the door, foreign visitors "
                   "included, just as tourism recovers from the COVID years"),
]
STORYLINE = STORYLINES[0][1]          # v1 name, kept for old callers
_STORY_TURN = itertools.count(random.randrange(len(STORYLINES)))


def pick_frame(persona):
    """Mostly the persona's home frames, sometimes any frame (weighted)."""
    if random.random() < 0.85:
        return random.choice(persona["frames"])
    keys = list(FRAMES)
    return random.choices(keys, weights=[FRAMES[k]["weight"] for k in keys])[0]


# Rules shared by every prompt (batch.py can switch its SHARED_RULES to these).
STANCE_RULE = "You are voting No: not against vaccines, against the certificate rule."
SAFETY_RULE = ("Nothing about vaccine safety or side effects. Anger only at the rule and the government pushing it, "
               "never at voters or any group; no conspiracy talk.")
JAB_RULE = ("The H2D2 jab isn't out yet: the first 120,000 doses come in the last week of October, for health workers "
            "and the high-risk; nobody has had it.")
JAB_FIRST_LOT = "As a health worker you can say you'll be in the first lot."
# 2026-10-20: drafts said "I'll get my jab when my turn comes" in 4 of 12 (a fingerprint), and pro-jab lines may move
# the scored "vaccination in general" view towards Yes. The jab comes up only when the citizen raised it.
JAB_WAIT = "Don't bring up your own jab unless the post is about it or they asked."
LOGISTICS_RULE = "Never name a day or date for the vote or say how or where to vote."
TAG_RULE = "No hashtags, except the one tag a new post is given, at the very end."
STYLE_RULES = (
    "First person, everyday words, British spelling, contractions. No emojis, links, @mentions, quotation marks, "
    "greetings or sign-offs. Numbers as digits. Never insult anyone or mention Marina Castillo, the tourism board or "
    "resorts. Don't open with agreement or comfort (Exactly, Spot on, Fair point, I hear you, I understand). Facts in "
    "your own words, never the wording above."
)
# The situation, first in every system prompt. Why: replies argued with citizens' conditions, not their reason for
# leaning Yes, and the activity log shows ~14 "towards neither side" changes to 2 towards No (todo/13, "Evidence").
# No numbers and labelled as background (todo/14): with seven figures in it, drafts packed in every one. The figures
# reach prompts through the frame's facts and the hospital/COVID rebuttals.
WORLD = (
    "Background (don't restate it): Kingstonia votes in a binding referendum on requiring proof of H2D2 (Dolphin "
    "Flu) vaccination to enter public spaces. The polls are level and the unsure will decide it. Most who lean Yes "
    "are afraid, after what COVID did to the hospitals; a No keeps life as it is, with the jab free either way."
)
# One persuasion lever per draft, logged as meta["lever"] so the experiments (todo/13) can compare them.
LEVERS = {
    "loss": "Make it about losing something dear and ordinary: name the person and exactly what they'd be shut out "
            "of (school, a shift, the ferry, church, visiting family).",
    "switching": "Show people changing their minds: you or someone you name was Yes or unsure and is now voting No; "
                 "say what turned them. Make it feel like a lot of people are moving.",
    "status_quo": "Speak to the unsure: a No keeps life as it is and stops nobody getting the jab, while a Yes can't "
                  "be undone; if you're not sure, No is the safe choice.",
    "fear_answer": "Answer the hospital fear head-on and with feeling: the people H2D2 puts in hospital are mostly "
                   "older or already ill, they get the first doses, and a pass at the shop door adds no nurse and no bed.",
    "in_group": "Speak as one of us: how this rule lands on ordinary islanders like you and the reader (workers, "
                "families, the outer islands), never on the people who wrote it.",
    "permanence": "Make the missing end date concrete and personal: the same check at your grandkids' school gate "
                  "years from now, because nothing in the question ever switches it off.",
}


def register_of(persona):
    return (persona or {}).get("register") if (persona or {}).get("register") in VOICES else "warm"


def _fill(meta, **kw):
    if meta is not None:
        meta.update(kw)


SYSTEM_BUDGET = 3200     # characters; over it, optional profile lines go (see the drop order in system_prompt). +300 for WORLD


def system_prompt(persona, frame_key, meta=None):
    """Who is speaking (character + voice), the facts they may use, and the rules."""
    f, register = FRAMES[frame_key], register_of(persona)
    facts = "; ".join(FACT_NOTES[k] for k in f["facts"][:3])
    age = f", {persona['age']}" if persona.get("age") else ""
    people = random.sample(usable(persona.get("people")), k=min(2, len(usable(persona.get("people")))))
    now = random.choice(usable(persona.get("now"), now=True)) if usable(persona.get("now"), now=True) else None
    details = persona["details"] if not now else random.sample(persona["details"], k=1)
    covid = persona.get("covid") if "covid_business" in f["facts"] or random.random() < 0.3 else None
    covid = covid if usable([covid]) else None
    problem = persona.get("problem") if usable([persona.get("problem")]) else None
    heat = f.get("heat") if register == "fed_up" else None
    voice = VOICES[register]["instruction"] + (f" Your sharpest take on today's point, in your own words: {heat}"
                                               if heat else "")
    jab = JAB_FIRST_LOT if persona["key"] in HEALTH_WORKERS else JAB_WAIT
    rest = (f"The referendum asks: \"{QUESTION}\" {STANCE_RULE} {voice}\n"
            f"Facts you may use, as notes (two at most, in your own words; invent no other facts, numbers, names or "
            f"health claims): {facts}.\n"
            f"Rules: money is K$. {LOGISTICS_RULE} {SAFETY_RULE} {JAB_RULE} {jab} {TAG_RULE} {STYLE_RULES} "
            f"Output only the text you would post.")

    def profile():
        out = [f"You are {persona['name']}{age} ({persona['role']}, {persona['place']}), in Kingstonia, a small "
               f"Pacific island nation. About you: {'; '.join(details)}."]
        if people:
            out.append(f"People in your life: {' '.join(clip(x, 80, keep=0.2) for x in people)}")
        if problem:
            out.append(f"What a Yes would cost you: {clip(problem, 130)}")
        if covid:
            out.append(f"Your COVID years: {clip(covid, 100)}")
        if now:
            out.append(f"This fortnight: {clip(now, 150)}")
        out.append(f"Your style: {persona['voice']}.")
        return " ".join(out)

    text = f"{WORLD}\n{profile()}\n{rest}"
    covid_frame = "covid_business" in f["facts"]       # there the COVID years are the story: they go last
    for drop in ("person", "problem", "covid") if covid_frame else ("covid", "person", "problem"):
        if len(text) <= SYSTEM_BUDGET:
            break
        if drop == "covid":
            covid = None
        elif drop == "person":
            people = people[:1]
        else:
            problem = None
        text = f"{WORLD}\n{profile()}\n{rest}"
    _fill(meta, persona=persona["key"], voice=register, now=now, people=[x.split(",")[0] for x in people],
          heat=bool(heat), covid=bool(covid), problem=bool(problem))
    return text


def _shape_fits(key, frame_key, persona):
    if key == "fed_up":                       # the fed-up hook is register 2 only (playbook §5.7)
        return register_of(persona) == "fed_up" if persona else False
    if key == "defiance":
        return register_of(persona) != "fed_up"
    if key == "number":                       # only when the frame's facts carry a true number to open on
        return any(re.search(r"\d", FACTS[k]) for k in FRAMES[frame_key]["facts"])
    return key != "news"


def pick_shape(frame_key, headline=None, shape=None, persona=None):
    """(key, text) of a post opening style: the one asked for (text or key), else a random one that fits."""
    if shape in POST_SHAPE_KEYS:
        return shape, POST_SHAPES[POST_SHAPE_KEYS.index(shape)]
    if shape:
        return (POST_SHAPE_KEYS[POST_SHAPES.index(shape)] if shape in POST_SHAPES else "custom"), shape
    keys = [k for k in POST_SHAPE_KEYS if _shape_fits(k, frame_key, persona)] + (["news"] if headline else [])
    key = random.choice(keys)
    return key, POST_SHAPES[POST_SHAPE_KEYS.index(key)]


# A post gets at most 4 content beats before its fixed close (todo/14: the model includes every beat it is given, so
# drafts with all of them ran long and read stitched): the opening, ONE of stake / lever / turning point, the point,
# and a fact or a concession. These openings already carry their own fact, so they get no extra facts beat.
NO_FACT_SHAPES = {"conversion", "defiance", "number", "did_you_know"}
CONCEDE_SHARE = 0.35        # 7 of 12 drafts shared one concession formula (20 Oct)


def post_prompt(frame_key, headline=None, shape=None, ask=False, meta=None, persona=None):
    """One new post along the playbook §5 anatomy: opening -> one beat (stake, lever or turning point) -> the point
    -> one fact or a short concession -> "I'm voting No" -> catchphrase (about 1 in 3, never with a concession) -> a
    question from the reader's life (before the verdict in ~1 in 4) -> one tag. `ask` is kept for old callers; pass
    `persona` to unlock the fed-up hook and the conversion arc."""
    f = FRAMES[frame_key]
    key, text = pick_shape(frame_key, headline, shape, persona)
    pillar = PILLARS.get(f["pillar"]) or _PILLARS_V1[PILLAR_OF[frame_key]]
    stakes = usable(f["stakes"])
    stake = random.choice(stakes) if stakes else None
    tag = random.choice(pillar["tags"])
    arc = (persona or {}).get("arc") if key == "conversion" else None
    # the experiment arms (todo/13): drawn independently per draft and logged from meta
    arms = {}
    if arc:
        arms["beat"] = "turn"
    elif key == "named_loss" and stake:
        arms["beat"] = "stake"
    else:
        experiment.draw("beat", ["stake", "lever"] if stake else ["lever"], arms)
    lever = experiment.draw("lever", list(LEVERS), arms) if arms["beat"] == "lever" else arms.setdefault("lever", None)
    concede = experiment.draw("concede", {True: CONCEDE_SHARE, False: 1 - CONCEDE_SHARE}, arms)
    # the catchphrase replaces the concession, never joins it: drawn only without one, so still ~1 post in 3
    catch = (random.choice(pillar["catchphrases"]) if pillar["catchphrases"] and not concede
             and random.random() < CATCHPHRASE_SHARE / (1 - CONCEDE_SHARE) else None)
    ask_kind = experiment.draw("ask_kind", experiment.ASK_WEIGHTS, arms)
    close = experiment.draw("close", experiment.CLOSES, arms) if ask_kind != "none" else arms.setdefault("close", None)
    sentences, lo, hi = experiment.length_line("post", arms)
    question = random.choice(f["asks"]) if f["asks"] and ask_kind == "frame" else None
    ending = ("End with one real question that readers answer from their own life, never a rhetorical one" +
              (f", along the lines of this one but in your own words: {question}" if question else ".")
              if ask_kind == "frame" else experiment.ASK_KINDS[ask_kind])
    verdict = ["Then say plainly that you're voting No.",
               f"Right after that, add this line word for word: {catch}" if catch else ""]
    if close == "verdict_last":                 # the question moves before the verdict; the post ends on the No
        closing = [ending.replace("End with one", "Then ask one", 1)] + verdict
    else:
        closing = verdict + [ending]
    beat = {
        "turn": f"Your own turning point: {arc}",
        "stake": (f"Make that loss this one, told about your own person (gist only, never these words): {stake}"
                  if key == "named_loss" else
                  f"Then the stake: someone from your own life (name them) loses something ordinary under a Yes. "
                  f"Take the gist only, never these words: {stake}"),
        "lever": f"Then make it land through this: {LEVERS[lever]}" if lever else "",
    }[arms["beat"]]
    beats = [
        f"Write one new post of {sentences} short sentences, between {lo} and {hi} words in all, as one flowing post "
        f"(no numbers or labels). Use contractions (I'm, don't, it's). Build it in this order.",
        text.format(headline=headline),
        beat,
        f"The point underneath it, in your own words: {f['gist']}.",
        "Then grant the other side in 8 words or fewer, without repeating their reasons." if concede else
        "" if key in NO_FACT_SHAPES else "Use one fact, in plain words. Appeal to feeling, not to the fine print.",
        *closing,
        f"Then finish with exactly one hashtag, {tag}, and nothing after it.",
    ]
    _fill(meta, frame=frame_key, shape=key, hook=HOOKS.get(key, key), pillar=f["pillar"], stake=stake, tag=tag,
          catchphrase=catch, ask=question, closing_question=close == "question_last", **arms)
    return " ".join(b for b in beats if b)


def catchphrase_in(text):
    """The catchphrase a draft actually used, if any (for logging and the variety check)."""
    low = (text or "").lower()
    return next((c for p in PILLARS.values() for c in p["catchphrases"] if c.lower().rstrip(".?!") in low), None)


# Own-thread replies under our amplified posts (docs/06-strategy/amplification.md). Each is a real neighbour's reaction, readable on its own:
# varied in length and kind, never a chorus of the same line.
THREAD_STYLES = {
    "one_liner": "React in ONE short sentence, between 20 and 90 characters, the way people react in a thread. "
                 "Not a slogan; something only you would say, tied to one detail of their post.",
    "question": "Ask them one genuine, specific follow-up question about something in their post, between 40 and 160 "
                "characters. No argument, just the question.",
    "detail": "Add one concrete detail from your own life that bears on their point, in 1 or 2 sentences, between "
              "80 and 220 characters.",
    "own_angle": "Add a different reason you're voting No, in 1 or 2 sentences, between 80 and 220 characters: {angle}.",
    "pushback": "You mostly agree, but one worry from the other side nags at you (hospitals being stretched, or "
                "remembering COVID). Raise it politely as a question to them, between 60 and 200 characters. Don't "
                "say how you'll vote.",
}


def thread_reply_prompt(post_text, frame_key, style):
    task = THREAD_STYLES[style].format(angle=FRAMES[frame_key]["gist"])
    return (f"A neighbour posted:\n<<<{post_text[:600]}>>>\nYou're replying under their post. {task} "
            f"Speak from your own life (your job, your place), never from theirs, and don't pick up names or phrases they "
            f"made up. Don't repeat their words back, don't praise the post, don't open with agreement words. {REPLY_RULES}")


def thread_answer_prompt(our_text, their_text):
    return (
        f"You posted:\n<<<{our_text[:500]}>>>\nA neighbour replied under it with a worry:\n<<<{their_text[:400]}>>>\n"
        f"Answer them in 1 or 2 sentences, between 60 and 230 characters: grant the worry honestly, then give one "
        f"concrete reason it doesn't change your No. Warm, not preachy. No hashtags."
    )


def rebuttal_for(text):
    return next((line for pattern, line in REBUTTALS if pattern.search(text or "")), None)


# Openings, picked at random so replies across accounts don't share one template (playbook §7 reply shape).
OPENERS = [
    "Open with their own words for what they raised, 6 words or fewer.",
    "Open with a short, honest concession, 8 words or fewer, then turn.",
    "Open by naming the exact thing they asked for, in a few words.",
    "Open with the fact itself, plainly.",
    "Open with a short line from your own experience that connects directly to their point.",
]
CORE_FRAMES = {"F14_no_yes_but", "F1_blank_cheque", "F2_no_end", "F8_powers"}
REPLY_RULES = (
    "Make ONE point only. Say any fact in your own words; never reuse the wording above. Any concession is 8 words "
    "or fewer and never repeats their reasons. Avoid stock phrases such as 'as written', 'as it stands', 'the "
    "trouble is', 'locks it in', 'I get wanting', 'makes sense', 'I hear you', 'fair point'. Mention your own life "
    "only if it connects directly to their point; no small talk. No rhetorical questions: any question is one they "
    "can answer from their own life. Do not repeat their sentences back to them and don't lecture. No hashtags."
)


EXEMPT_NOTE = ("They mention exemptions: medical exemptions ARE in the plan, so never lump exemptions in with what's "
               "missing. Say exemptions are covered, then name what isn't (an end date, the list of places, any review).\n")


def exempt_note(target_text):
    return EXEMPT_NOTE if re.search(r"exempt", target_text or "", re.I) else ""


def _reply_voice(persona):
    return f"{VOICES[register_of(persona)].get('reply_instruction', '')} " if persona else ""


def reply_prompt(target_text, frame_key, wants, context=None, opener=None, meta=None, persona=None):
    """Deep-canvass shape (playbook §7): their words -> one dense fact or a swapped story -> a question back."""
    ctx = f"It was posted in reply to this news item: <<<{context[:200]}>>>\n" if context else ""
    arms = {}
    # H1 (todo/13): reason_first answers the reason they lean Yes, whatever the frame: arguing with their conditions
    # only got them to restate a conditional Yes (the "neither side" changes in the 2026-10-20 activity log).
    # conditions_first is the pre-20-Oct reply (the frame's point, in their terms), kept as the switchback's control.
    reason_first = experiment.draw("reply_mode", experiment.REPLY_MODES, arms) == "reason_first"
    if reason_first:
        reb = rebuttal_for(target_text)
        asks = f"The conditions they mention: {', '.join(wants)}. Don't argue about these.\n" if wants else ""
    else:
        reb = None if frame_key in CORE_FRAMES else rebuttal_for(target_text)
        asks = f"The specific thing they raised: {', '.join(wants)}. Use their terms.\n" if wants else ""
    opener = opener or random.choice(OPENERS)
    # with their reason known, it replaces the frame's angle (one instruction, not two that pull apart)
    lever = experiment.draw("lever", [k for k in LEVERS if not (reb and reason_first and k == "fear_answer")], arms)
    ask_kind = experiment.draw("ask_kind", {k: w for k, w in experiment.ASK_WEIGHTS.items() if k != "frame"}, arms)
    sentences, lo, hi = experiment.length_line("reply", arms)
    _fill(meta, frame=frame_key, pillar=FRAMES[frame_key]["pillar"], opener=opener, rebuttal=bool(reb), **arms)
    if reason_first:
        point = "answer the reason above" if reb else FRAMES[frame_key]["gist"]
        why = "Answer WHY they lean Yes (the fear or hope underneath, not the conditions they list). "
        reb = f"{reb}\n" if reb else ""
    else:
        point, why = FRAMES[frame_key]["gist"], ""
        reb = f"Note: {reb}\n" if reb else ""
    return (
        f"{ctx}A neighbour wrote:\n<<<{target_text[:600]}>>>\n{reb}{asks}{exempt_note(target_text)}"
        f"They haven't fully decided. {why}Reply in {sentences} short sentences, between {lo} and {hi} words. "
        f"{opener} Then a short moment from your own life or one dense fact; the point: {point}. Make it land "
        f"through this: {LEVERS[lever]} {experiment.ASK_KINDS[ask_kind]} {_reply_voice(persona)}{REPLY_RULES}"
    )


def second_voice_prompt(target_text, frame_key, wants, context=None, opener=None, meta=None, persona=None):
    ctx = f"It was posted under this news item: <<<{context[:200]}>>>\n" if context else ""
    asks = f"What they care about: {', '.join(wants)}.\n" if wants else ""
    opener = opener or random.choice(OPENERS)
    arms = {}
    lever = experiment.draw("lever", list(LEVERS), arms)
    sentences, lo, hi = experiment.length_line("second_voice", arms)
    _fill(meta, frame=frame_key, pillar=FRAMES[frame_key]["pillar"], opener=opener, **arms)
    return (
        f"{ctx}A neighbour wrote:\n<<<{target_text[:600]}>>>\n{asks}{exempt_note(target_text)}"
        f"Someone else has already replied to them. Add a different angle, as yourself, in {sentences} short "
        f"sentence{'' if sentences == '1' else 's'}, between {lo} and {hi} words: {FRAMES[frame_key]['gist']}. "
        f"{opener} Make it land through this: {LEVERS[lever]} Don't mention the other reply or repeat its argument. "
        f"{_reply_voice(persona)}{REPLY_RULES}"
    )


def reply_back_prompt(our_text, their_text):
    return (
        f"You posted:\n<<<{our_text[:500]}>>>\nA neighbour replied to you:\n<<<{their_text[:500]}>>>\n"
        f"Reply to them in 1 or 2 sentences, between 40 and 220 characters: answer what they actually said, kindly "
        f"and specifically, and stay with your view. If they agreed, start with a short thanks (Cheers, Thanks, "
        f"Ta) or go straight to one small new thing; never start with Spot on, Exactly or Too right. "
        f"If they asked a question, answer it with one fact. No hashtags."
    )


def journalist_prompt(journalist_id, their_text, meta=None, persona=None):
    """A reply to a newspaper's AI journalist: one fact, one storyline (rotating), one quotable line. `persona` only
    labels the meta: the voices' reply instructions (end on a question) don't fit a quote for the paper."""
    who = FIRST_NAMES.get(journalist_id, "the journalist")
    key, story = STORYLINES[next(_STORY_TURN) % len(STORYLINES)]
    _fill(meta, storyline=key, **({"voice": register_of(persona)} if persona else {}))
    return (
        f"{who}, a local journalist, wrote:\n<<<{their_text[:500]}>>>\n"
        f"Reply to {who} in 2 sentences, between 120 and 260 characters, as yourself. Don't open by agreeing or "
        f"praising and don't introduce yourself; open with one concrete fact that bears directly on their point. Then "
        f"connect it to this story: {story}. Make one of the sentences a short line a reporter would quote, 12 words "
        f"or fewer, in your own words. Calm and specific, no flattery, no hashtags. {REPLY_RULES}"
    )
