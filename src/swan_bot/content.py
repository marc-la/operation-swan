"""What we say: world facts, frames (arguments), personas, Yes rebuttals, and the prompts built from them.

Humans own this file. Frames: docs/06-strategy/frames-and-messengers.md. How to say it (hooks, themes, tags,
voices, post anatomy, reply shape): docs/06-strategy/message-playbook.md. Facts: content/facts.toml (todo/16),
checked against docs/01-competition/setting.md and the papers.
Content v2 data (swan_bot/playbook/: craft, voices, characters) is copied onto FRAMES and PERSONAS at import; a
missing module falls back to the v1 behaviour. Every fact here is true in-game. Careful: medical exemptions ARE in
the plan, the certificate is separate from the ID card, and the H2D2 jab isn't out yet (first doses: last week of
October). Never claim otherwise.

Paused facts (facts.py): anything that states one leaves the prompts. Each frame, rebuttal, storyline, lever and
WORLD sentence names the facts its own wording states in `requires`; while one is paused it is not used (a frame
also goes when all its facts are paused). Character, persona and theme text is filtered by the paused facts'
`says` wording, and the quality gate rejects drafts that use it. tests/test_facts.py checks the two agree.
"""
import datetime as dt
import itertools
import json
import random
import re
import zlib
from zoneinfo import ZoneInfo

from . import config, experiment, flip, register as reg_mod, touches
from . import facts as fact_store
from .memory import item_key, reset_vocab

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

# The active facts, key -> text, from content/facts.toml (paused ones left out; rebuilt in place when a pause
# changes). FACT_NOTES: the same facts as terse notes, which is how prompts show them (todo/14): facts written as
# polished sentences got pasted into drafts word for word. quality.py checks copying against the full texts.
FACTS, FACT_NOTES = fact_store.TEXTS, fact_store.NOTES

# Each frame: the point to make, the facts it may lean on, its weight for persona posts,
# and the frame(s) a second persona uses on the same doubt (a different angle, never a repeat; a list = pick one).
# `gist` is the angle as a short note, which is what the prompts show (todo/14: the full angle got copied); quality.py
# checks copying against the full angle. `requires`: the facts its angle, gist and craft (stakes, heat, asks) state,
# so the frame goes while any of them is paused.
FRAMES = {
    "F14_no_yes_but": dict(
        angle="the question doesn't say when the rule ends, which places it covers, or who reviews it; if you can't "
              "find the answer on the ballot, No is the safe vote",
        gist="the question doesn't say when it ends, which places, or who reviews it: can't find it, vote No",
        facts=["no_end", "list_later"],
        requires=["no_end", "list_later"], weight=3,
        second=["F1_blank_cheque", "F3_provax_antipass", "F2_no_end"]),
    "F1_blank_cheque": dict(
        angle="the list of places the rule covers is only decided after the vote, so a Yes means agreeing before "
              "anyone can see what was agreed; if you don't know, it's fine to say No",
        gist="places are picked after the vote: a Yes is signing before you see it; unsure means No",
        facts=["list_later", "phased"],
        requires=["list_later"], weight=3, second="F14_no_yes_but"),
    "F2_no_end": dict(
        angle="nothing in the question says when the rule ends, and 'temporary' only counts if it is written down",
        gist="no end date in the question; temporary only counts on paper",
        facts=["no_end", "no_binds"],
        requires=["no_end"], weight=2, second="F1_blank_cheque"),
    "F3_provax_antipass": dict(
        angle="whether and when you get the jab is your own business, and it stays free either way; this vote is "
              "only about papers at the door, and a choice that costs you your bus, your shift or your kid's school "
              "isn't a choice (don't praise vaccines: that's not the argument)",
        gist="your jab, your call, free either way; the vote is only the pass, and a choice that costs your job or "
             "bus is no choice (don't praise vaccines)",
        facts=["free_either_way", "age12"],
        requires=["free_either_way", "age12", "childhood"], weight=1, second="F1_blank_cheque"),
    "F8_powers": dict(
        angle="the certificate is meant to stay separate from the new biometric ID card, and today's law says so, "
              "but laws change and once a check is at every door it is easy to join things up later",
        gist="kept off the ID card by today's law, but laws change once every door has a check",
        facts=["id_card", "no_end"],
        requires=["id_card", "no_end"], weight=1, second="F14_no_yes_but"),
    "F10_staff_and_livelihoods": dict(
        angle="a pass at the shop door adds no nurse and no bed (Kingstonia Central has 40 empty nursing posts); what "
              "it adds is papers for ordinary jobs (name one from your own life)",
        gist="a door pass adds no nurse and no bed; it adds papers for ordinary jobs (name one)",
        facts=["nurses", "first_doses"],
        requires=["nurses"], weight=2, second="F3_provax_antipass"),
    "F13_age12": dict(
        angle="the rule covers everyone from age 12, at school and on the bus, and nobody can yet say which "
              "places will count",
        gist="everyone from 12, school and bus, and nobody knows which places yet",
        facts=["age12", "list_later", "childhood"],
        requires=["age12", "list_later", "childhood"], weight=1, second="F1_blank_cheque"),
    "F6_islands": dict(
        angle="a free choice that comes with a certificate is harder for some people than others: on the outer "
              "islands the clinic is nurse-led with a GP once a week and the ferry costs K$14",
        gist="a free choice plus a certificate costs more out on the islands (weekly GP, K$14 ferry)",
        facts=["islands", "list_later"],
        requires=["islands", "list_later"], weight=1, second="F14_no_yes_but"),
    "F7_livelihoods": dict(
        angle="shop, cafe and ferry staff would end up checking papers at the door, visitors would need one too, "
              "and we all remember what the last restrictions did to small businesses",
        gist="shop, cafe and ferry staff end up on the door, visitors too; remember what COVID did to small shops",
        facts=["visitors", "covid_business", "list_later"],
        requires=["visitors", "covid_business", "list_later"], weight=1, second="F1_blank_cheque"),
    "F5_not_here_yet": dict(
        angle="there is one case, a traveller now in isolation, and the first doses already go to health workers and "
              "people at high risk; a certificate at every shop, park and bus is out of proportion to that "
              "(never say there are no cases)",
        gist="one case in isolation and the at-risk first in line for doses: a pass for every shop, park and bus "
             "is too much for one case",
        facts=["no_spread", "first_doses"],
        requires=["no_spread", "first_doses"], weight=1, second="F14_no_yes_but"),
    "F9_parliament": dict(
        angle="the Assembly already said no on 15 Oct, with some of the President's own party voting it down; "
              "this isn't a party thing, plenty of people who voted Hawthorne are voting No",
        gist="the Assembly already said no, the President's own people too; not a party thing",
        facts=["bill_failed", "no_binds"],
        requires=["bill_failed", "list_later"], weight=1, second="F1_blank_cheque"),
    "F12_open_island": dict(
        angle="keep Kingstonia open: the ordinary island life you love (name it) shouldn't need papers at the door, "
              "and the vaccine is free and yours to choose either way",
        gist="everyday island life (name it) shouldn't come with papers; the jab's yours to choose",
        facts=["free_either_way", "covid_business", "no_spread"],
        requires=["free_either_way", "list_later"], weight=2, second="F1_blank_cheque"),
}
def sync_frames():
    """facts.toml `frames = [...]`: an approved fact joins after the frame's own facts. Run at import and again each
    time the fact table is re-read (facts.ON_RELOAD), so a fact the desk accepts mid-run reaches the frame prompts
    without a restart (2026-10-22)."""
    for key, frame in FRAMES.items():
        own = frame.setdefault("own_facts", list(frame["facts"]))
        frame["facts"] = own + [k for k in fact_store.linked(key) if k not in own]


sync_frames()
fact_store.ON_RELOAD.append(sync_frames)
fact_store.ON_RELOAD.append(reset_vocab)          # todo/50: memory.voice_repeat's view of our case's own words

# Yes arguments citizens repeat, our answer (grant the concern first), and the facts the answer states (it isn't used
# while one is paused). Added to reply prompts when matched.
REBUTTALS = [
    (re.compile(r"hospital|ward|icu|overwhelm|surge|capacity|frontline|vulnerable|protect", re.I),
     "They are worried about the hospitals and the vulnerable. Don't open by agreeing or arguing medicine; make ONE "
     "No point: the first doses already go to the at-risk / a pass at the shop door adds no nurse and no bed / "
     "Central already has 40 empty nursing posts.", ["first_doses", "nurses"]),
    (re.compile(r"last time|covid|1,?000|died|deaths", re.I),
     "Their reason is the memory of COVID. Don't open by agreeing; make ONE No point: a No doesn't stop a single "
     "dose / this vote is only the pass at the door / the at-risk get the first doses.",
     ["first_doses", "free_either_way"]),
    (re.compile(r"choice stays|still (a|your) choice|voluntary", re.I),
     "They say the choice stays yours. A choice that costs you your job, your bus or your kid's school isn't much of a choice.",
     []),
    (re.compile(r"before it (gets|arrives)|act now|prepare|ready", re.I),
     "They want to act early. We are: 120,000 doses land this month for health workers and the at-risk, and a No doesn't stop a single jab.",
     ["first_doses", "free_either_way"]),
    (re.compile(r"\biho\b|world health|experts? (say|recommend)|doctors? say", re.I),
     "They cite expert advice. Don't attack doctors; the advice is about getting vaccinated, which a No doesn't stop.",
     ["free_either_way"]),
    (re.compile(r"resort|profit|castillo|kitb|tourism board", re.I),
     "They distrust the tourism board. Don't defend Castillo or the resorts; speak only for yourself and your own job.",
     []),
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
    # todo/17, promoted 2026-10-21 (profiles in playbook/characters.py)
    dict(key="esther", name="Esther Vaipulu", handle="esther_marketbakery",
         role="runs her parents' bakery by the Kingstonia City markets, ovens on at four",
         place="Kingstonia City", voice="warm, early-riser brisk, teasing, floury",
         details=["opens at half past four, a street back from the Kingstonia City markets",
                  "three on the morning shift: herself, her husband Sateki and Fetu on the counter",
                  "her parents opened the bakery; their wedding photo still hangs above the till",
                  "day-old bread goes out free on the back step after closing"],
         frames=["F7_livelihoods", "F1_blank_cheque", "F3_provax_antipass"]),
    dict(key="paulo", name="Paulo Sapolu", handle="paulo_sapolu_dad",
         role="warehouse stock controller and dad of an eleven-year-old, who was leaning Yes",
         place="Kingstonia City", voice="gentle, candid, owns that he changed his mind",
         details=["checks stock in and out at a grocery wholesaler's warehouse in Kingstonia City",
                  "his daughter Talia starts high school in February and turns 12 in March",
                  "lost his dad in the worst months of COVID",
                  "walks Talia to drumming practice on Thursday nights"],
         frames=["F13_age12", "F14_no_yes_but", "F5_not_here_yet"]),
    dict(key="wally", name="Wally Koroi", handle="wally_koroi_harbour",
         role="retired harbour-master of New Haven, seventy-four, who still reads next year's tide tables for fun",
         place="New Haven", voice="warm, wry, unhurried, a long memory",
         details=["forty years in the New Haven harbour office, the last twenty of them as harbour-master",
                  "buys next year's tide tables the week they come out and keeps them by the kettle",
                  "gives the cyclone-moorings talk at the New Haven sailing club before every wet season",
                  "lives on the hill above the harbour with his wife Unaisi and the family's papers in a biscuit tin"],
         frames=["F2_no_end", "F3_provax_antipass", "F12_open_island"]),
    dict(key="ngaire", name="Ngaire Walsh", handle="ngaire_coaches",
         role="volunteer netball coach for girls ten to sixteen in Crown Harbour; freight clerk by day",
         place="Crown Harbour", voice="blunt coach, counts jobs, no fuss",
         details=["coaches girls ten to sixteen on the park courts at Saltworks Park on Tuesday and Thursday nights",
                  "checks freight paperwork all day at a shipping agent's office in Crown Harbour",
                  "her club dropped from five junior teams to two in the COVID years and is back to four"],
         frames=["F13_age12", "F1_blank_cheque", "F12_open_island"]),
    dict(key="kai", name="Kai Nakamura", handle="kai_nakamura_dev",
         role="software developer at a small marine-monitoring firm in Kingstonia City",
         place="Kingstonia City", voice="calm, exact, dry; thinks in systems",
         details=[("writes the software for the reef buoys that log water temperature for the marine reserves; "
                   "every buoy goes in with the date it comes out"),
                  "goes out on the survey boat once a month to service the buoys",
                  "studied computer science at Crown Harbour Institute of Technology",
                  "rides the bus to an office of twelve near the Kingstonia City waterfront"],
         frames=["F8_powers", "F2_no_end", "F1_blank_cheque"]),
    # todo/17, promoted 2026-10-23 (profiles in playbook/characters.py)
    dict(key="kiri", name="Kiri Matagi", handle="kiri_spicefarm",
         role="spice and vanilla grower outside New Haven, mum of twins who turned 12 this year",
         place="New Haven", voice="warm, busy, practical, a mum first",
         details=["sells vanilla and nutmeg at the New Haven Saturday market",
                  "her twins catch the school bus in from the farm road",
                  "ties up the young vanilla vines after every squall"],
         frames=["F13_age12", "F14_no_yes_but", "F12_open_island"]),
    dict(key="rafa", name="Rafael Domingo", handle="rafa_reefdives",
         role="dive instructor who runs reef trips out of Crown Harbour",
         place="Crown Harbour", voice="matter-of-fact, numbers first, a diver's calm",
         details=["takes six divers a boat out to the barrier reef",
                  "most of his customers fly in from Australia and New Zealand",
                  "booked solid for Regatta Week"],
         frames=["F7_livelihoods", "F1_blank_cheque", "F5_not_here_yet"]),
    dict(key="leo", name="Leo Fonoti", handle="leo_fonoti_mech",
         role="apprentice mechanic in New Haven whose last school years were lost to closures",
         place="New Haven", voice="young, blunt, a bit sarcastic, short sentences",
         details=["fixes utes and outboard motors at a workshop on the ring road",
                  "plays club rugby on Saturdays",
                  "missed his last two school years in the classroom"],
         frames=["F2_no_end", "F9_parliament", "F1_blank_cheque"]),
]
PERSONA_BY_KEY = {p["key"]: p for p in PERSONAS}

# ---- Content v2 merge (playbook §2-6): craft onto FRAMES, voices + characters onto PERSONAS. Copies only: the
# playbook modules' own dicts and lists are never changed. Each missing module falls back to v1 behaviour.
PILLAR_OF = {"F14_no_yes_but": "A", "F1_blank_cheque": "A", "F2_no_end": "A", "F9_parliament": "A", "F8_powers": "A",
             "F7_livelihoods": "B", "F13_age12": "B", "F6_islands": "B", "F10_staff_and_livelihoods": "B",
             "F12_open_island": "B", "F3_provax_antipass": "C", "F5_not_here_yet": "C"}
_PILLARS_V1 = {
    "A": dict(name="Don't sign a blank cheque", tags=["#VoteNo", "#H2D2No"]),
    "B": dict(name="Ordinary life shouldn't need papers", tags=["#KeepKingstoniaOpen", "#SmallBusiness", "#WorkersRights"]),
    "C": dict(name="Your jab, your call", tags=["#ChoiceNotCoercion"]),
}
_VOICES_V1 = {r: dict(instruction="You are cheerful and reasonable, never angry.", reply_instruction="")
              for r in ("warm", "fed_up", "plain")}
CHARACTER_FIELDS = ("age", "people", "problem", "covid", "arc", "lines", "now")
_LIST_FIELDS = {"people", "lines", "now"}
HEALTH_WORKERS = {"ana", "sione", "ruth", "priya"}      # the only ones who may say they're in the first lot of doses
PILLARS, VOICES, SLOGANS = {}, {}, []


def merge_playbook(craft=None, voices=None, characters=None):
    """Copy the playbook data onto FRAMES, PERSONAS, PILLARS, VOICES and SLOGANS. Idempotent; run at import."""
    global PILLARS, VOICES, SLOGANS
    PILLARS = {k: dict(v, tags=list(v["tags"])) for k, v in getattr(craft, "PILLARS", _PILLARS_V1).items()}
    VOICES = {k: dict(v) for k, v in getattr(voices, "VOICES", _VOICES_V1).items()}
    SLOGANS = [t["slogan"] for t in (getattr(craft, "THEMES", None) or {}).values()]
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


# Vaccine advocacy (todo/20, 2026-10-22): urging people to get the jab, or praising the vaccine. A persona saying they're
# vaccinated, or that a No stops nobody getting the jab, is not advocacy. Off while config.NO_VACCINE_ADVOCACY.
ADVOCACY = re.compile(
    r"(^|[.!?:;]\s+|,\s+|\band\s+)(please\s+|just\s+|go\s+(and\s+)?)?get\s+(your|the|a|their)\s+(jab|vaccine|shot|dose|"
    r"booster)s?\b|\b(you|everyone|people|anyone|we all|all of us)\s+should\s+(get|have|take)\s+(it|the|their|your|a|"
    r"vaccinated)\b|\bget vaccinated\b|\btell (anyone|everyone|people|them|you) to get\b|"
    r"\b(vaccines?|the jab|jabs|the vaccine) (works?|is safe|are safe|saves? lives|protects?)\b|"
    r"\bbook (your|a|the) (jab|shot|vaccine|appointment)\b|\bwhen your turn (for the jab )?comes\b|"
    r"\byour turn for the jab\b|\bdon'?t (skip|wait on|put off) (the|your) (jab|shot|vaccine)\b", re.I)


def advocacy(text):
    """The vaccine advocacy in text while it is off (config.NO_VACCINE_ADVOCACY), or None."""
    m = config.NO_VACCINE_ADVOCACY and ADVOCACY.search(text or "")
    return m.group(0).strip(" ,.;:!?") if m else None


def usable(texts, now=False):
    """The entries that are safe to put in a prompt (`now`: also no dose events): none that states a paused fact
    or urges the jab."""
    return [t for t in texts or [] if t and not _OFF_LIMITS.search(t) and not (now and _NOW_OFF.search(t))
            and not fact_store.paused_in(t) and not advocacy(t)]


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
# Journalist replies rotate through these (each true in setting.md), so the papers don't hear one line from us:
# (key, storyline, the facts it states). A storyline isn't used while one of its facts is paused.
STORYLINES = [
    ("list_later", "voters are being asked to approve the rule before the government publishes which places it "
                   "covers; both campaigns have criticised it for not publishing that list before the vote",
     ["list_later"]),
    ("vaxxed_no", "plenty of vaccinated people are voting No: the jab is free and voluntary whatever the result, and "
                  "this vote is only about a certificate at the door", ["free_either_way"]),
    ("assembly", "the Assembly voted the bill down on 15 Oct, with several of the President's own People's Alliance "
                 "members joining the Democratic-Republicans, and now the same rule comes back as a binding vote",
     ["bill_failed", "no_end"]),
    ("nurses", "the health system's real gap is staff: Kingstonia Central has 40 unfilled nursing posts because a "
               "nurse earns about double in Australia or NZ, and a certificate check at a shop door fills none of them",
     ["nurses"]),
    ("no_end", "nothing in the question says when the rule would end, and a Yes result is binding", ["no_end"]),
    ("door_staff", "shop, cafe and ferry staff would be the ones checking papers at the door, foreign visitors "
                   "included, just as tourism recovers from the COVID years", ["visitors", "covid_business"]),
]
STORYLINE = STORYLINES[0][1]          # v1 name, kept for old callers
STORYLINE_FALLBACK = ("the_pass", "this vote is about a pass at the door for ordinary life, not about who gets the jab",
                      [])                # only while every storyline above is paused
_STORY_TURN = itertools.count(random.randrange(len(STORYLINES)))


class AllPaused(RuntimeError):
    """Every frame is paused: nothing true left to argue with until a review (the bot waits, it doesn't crash)."""


def frame_live(key):
    """True while the frame may be used: not retired (config.FRAME_SCALE 0, todo/59), none of the facts it requires is
    paused and one of its facts is active."""
    f = FRAMES[key]
    return frame_scale(key) > 0 and fact_store.ok(f["requires"]) and bool(fact_store.active(f["facts"]))


def live_frames():
    return [k for k in FRAMES if frame_live(k)]


def frame_scale(key):
    """How much of its usual odds a frame gets (config.FRAME_SCALE, todo/20: the frames citizens answered least)."""
    return config.FRAME_SCALE.get(key, 1.0)


def weighted_frame(keys):
    """One of `keys`, by config.FRAME_SCALE."""
    return random.choices(list(keys), weights=[frame_scale(k) for k in keys])[0]


def _any_live_frame():
    keys = live_frames()
    if not keys:
        raise AllPaused("every frame is paused (data/facts_paused.json): run scripts/facts_review.py")
    return random.choices(keys, weights=[FRAMES[k]["weight"] * frame_scale(k) for k in keys])[0]


def pick_frame(persona):
    """Mostly the persona's live home frames, sometimes any live frame (weighted)."""
    home = [k for k in persona["frames"] if frame_live(k)]
    if random.random() < 0.85 and home:
        return weighted_frame(home)
    return _any_live_frame()


def live_frame(key, persona=None):
    """The frame itself while it is live, else one of the persona's live home frames, else any live frame. Drafts
    built from a stored frame (queued jobs, thread replies, second voices) go through this, so a pause applies."""
    if key in FRAMES and frame_live(key):
        return key
    home = [k for k in (persona or {}).get("frames", ()) if frame_live(k)]
    return weighted_frame(home) if home else _any_live_frame()


# Rules shared by every prompt (batch.py can switch its SHARED_RULES to these).
STANCE_RULE = "You are voting No: not against vaccines, against the certificate rule."
SAFETY_RULE = ("Nothing about vaccine safety or side effects. Anger only at the rule and the government pushing it, "
               "never at voters or any group; no conspiracy talk.")
JAB_RULE = ("The H2D2 jab isn't out yet: the first 120,000 doses come in the last week of October, for health workers "
            "and the high-risk; nobody has had it.")
JAB_FIRST_LOT = "As a health worker you can say you'll be in the first lot."
# both state first_doses; while it is paused (the doses came early, late or elsewhere) this rule replaces them
JAB_RULE_PAUSED = "Never say when the H2D2 jab comes or who has had it."
# 2026-10-20: drafts said "I'll get my jab when my turn comes" in 4 of 12 (a fingerprint), and pro-jab lines may move
# the scored "vaccination in general" view towards Yes. The jab comes up only when the citizen raised it.
JAB_WAIT = "Don't bring up your own jab unless the post is about it or they asked."
# todo/20 (2026-10-22), while config.NO_VACCINE_ADVOCACY: a move towards vaccines may score against us (organiser Q3)
NO_ADVOCACY_RULE = "Never urge anyone to get vaccinated or praise the vaccine: this vote is about the pass."
LOGISTICS_RULE = "Never name a day or date for the vote or say how or where to vote."
# todo/23's off-topic replies (meta["style"] == "off_topic"): the system prompt keeps who the persona is and the style
# rules, without the referendum, the stance, the facts or the voice lines about the rule (they pulled 1 draft in 4 to the
# vote in the 2026-10-22 dry run). quality.check rejects a turn to the vote anyway (off_topic_vote).
OFF_TOPIC_RULE = ("This reply is about their topic only: don't mention the referendum, the vote, the vaccine, the jab, "
                  "the pass or the government, not even in passing. Never insult anyone; no conspiracy talk.")
TAG_RULE = "No hashtags, except the one tag a new post is given, at the very end."
STYLE_RULES = (
    "First person, everyday words, British spelling, contractions. No emojis, links, @mentions, quotation marks, "
    "greetings or sign-offs. Numbers as digits. Never insult anyone or mention Marina Castillo, the tourism board or "
    "resorts. Don't open with agreement or comfort (Exactly, Spot on, Fair point, I hear you, I understand). Facts in "
    "your own words, never the wording above."
)
# todo/50 (prompt critique, 28 Oct): 20% of replies named someone the reader can't know ("Mrs Rees", "Jacqui"), against
# 8% for citizens, who mostly name the person they answer. In a fixes block replies get this rule, and the reply voices
# lose the sentences that asked for a named person or a detail from the week (FIXES_VOICE_SUBS).
STRANGER_RULE = ("You're talking to a stranger: they don't know your people, so say 'my daughter' or 'a mate at work', "
                 "never a first name they'd have to know.")
FIXES_VOICE_SUBS = (
    (re.compile(r"Write in the first person about one named person or moment from your week; in a new post, open on "
                r"what they stand to lose, not on the scenery\."), "Write in the first person."),
    (re.compile(r", with one detail from your work or week\."), "."),
)
# The situation, first in every system prompt. Why: replies argued with citizens' conditions, not their reason for
# leaning Yes, and the activity log shows ~14 "towards neither side" changes to 2 towards No (todo/13, "Evidence").
# No numbers and labelled as background (todo/14): with seven figures in it, drafts packed in every one. The figures
# reach prompts through the frame's facts and the hospital/COVID rebuttals.
# (sentence, the facts it states, what replaces it while one is paused)
WORLD_PARTS = [
    ("Background (don't restate it): Kingstonia votes in a binding referendum on requiring proof of H2D2 (Dolphin "
     "Flu) vaccination to enter public spaces.", [], ""),
    (" The latest poll has Yes just ahead, the gap narrowing, and over a quarter still unsure: they will decide it.",
     ["polls_1029"], ""),                       # 29 Oct: polls_1025 retired (fact desk proposal 95)
    (" Most who lean Yes are afraid, after what COVID did to the hospitals; a No keeps life as it is, with the jab "
     "free either way.", ["free_either_way"], " Most who lean Yes are afraid, after what COVID did to the hospitals."),
]


def world():
    """WORLD without the sentences that state a paused fact."""
    return "".join(text if fact_store.ok(req) else instead for text, req, instead in WORLD_PARTS)


WORLD = "".join(text for text, _, _ in WORLD_PARTS)
# One persuasion lever per draft, logged as meta["lever"] so the experiments (todo/13) can compare them.
LEVERS = {
    "loss": "Make it about losing something dear and ordinary: name the person and exactly what they'd be shut out "
            "of (school, a shift, the ferry, church, visiting family).",
    "switching": "Show people changing their minds: you or someone you name was Yes or unsure and is now voting No; "
                 "say what turned them. Make it feel like a lot of people are moving.",
    "status_quo": "Speak to the unsure: a No keeps life as it is and stops nobody getting the jab, while after a Yes "
                  "the government has to bring it in, with no end date; if you're not sure, No is the safe choice.",
    "fear_answer": "Answer the hospital fear head-on and with feeling: the people H2D2 puts in hospital are mostly "
                   "older or already ill, they get the first doses, and a pass at the shop door adds no nurse and no bed.",
    "in_group": "Speak as one of us: how this rule lands on ordinary islanders like you and the reader (workers, "
                "families, the outer islands), never on the people who wrote it.",
    "permanence": "Make the missing end date concrete and personal: the same check at your grandkids' school gate "
                  "years from now, because nothing in the question ever switches it off.",
}
LEVER_REQUIRES = {"status_quo": ["free_either_way", "no_end"], "fear_answer": ["first_doses"], "permanence": ["no_end"]}


def requiring(key):
    """What in this file states the fact (its `requires` lists): frames, rebuttals, storylines, levers, rules."""
    out = [k for k, f in FRAMES.items() if key in f["requires"]]
    out += [f"rebuttal {i + 1}" for i, (_, _, req) in enumerate(REBUTTALS) if key in req]
    out += [f"flip {part} {k}" for part, items in (flip.data() or {}).items()
            for k, item in items.items() if key in (item.get("requires") or ())]     # a fear's own facts too (todo/52)
    out += [f"storyline {k}" for k, _, req in STORYLINES if key in req]
    out += [f"lever {k}" for k, req in LEVER_REQUIRES.items() if key in req]
    out += ["WORLD"] if any(key in req for _, req, _ in WORLD_PARTS) else []
    out += ["EXEMPT_NOTE"] if key in EXEMPT_REQUIRES else []
    return out + (["JAB_RULE"] if key == "first_doses" else [])


def live_levers():
    """The levers whose wording states no paused fact, in LEVERS order."""
    return [k for k in LEVERS if fact_store.ok(LEVER_REQUIRES.get(k, ()))]


def lever_weights(exclude=()):
    """{lever: weight} for a draw: the live levers by config.LEVER_WEIGHTS (todo/20), those at 0 left out."""
    out = {k: config.LEVER_WEIGHTS.get(k, 1.0) for k in live_levers() if k not in exclude}
    return {k: w for k, w in out.items() if w > 0} or {k: 1.0 for k in live_levers() if k not in exclude}


def register_of(persona):
    return (persona or {}).get("register") if (persona or {}).get("register") in VOICES else "warm"


def _fill(meta, **kw):
    if meta is not None:
        meta.update(kw)


BASE_BUDGET = 3200       # characters without the pulse; over it, optional profile lines go (the drop order below)
PULSE_BUDGET = 800       # the pulse block at most (pulse.py: 600 of notes plus its frame words)
SYSTEM_BUDGET = BASE_BUDGET + PULSE_BUDGET
PULSE_PARTS = ("hooks", "no_shapes", "yes_lines", "avoid")


def _part_of_day(ts):
    hour = dt.datetime.fromtimestamp(ts, ZoneInfo(config.LOCAL_TZ)).hour
    return "this morning" if 5 <= hour < 12 else "this afternoon" if hour < 18 else "this evening" if hour < 22 \
        else "tonight"


def pulse_block(pulse, parts=PULSE_PARTS):
    """What's working on Legit Social now (todo/15: pulse.py), as one line of data, or "" without a pulse. `parts`
    picks the fields: amplified posts get all, their thread replies the hooks, replies to Yes-leaners the yes_lines."""
    if not pulse:
        return ""
    hooks = [h["text"] for h in pulse.get("hooks") or []] if "hooks" in parts else []
    said = [f"people are reacting to {'; '.join(hooks)}." if hooks else "",
            f"For No, what lands is {'; '.join(pulse['no_shapes'])}." if "no_shapes" in parts and pulse.get("no_shapes")
            else "",
            f"The Yes side is pushing {'; '.join(pulse['yes_lines'])}." if "yes_lines" in parts and pulse.get("yes_lines")
            else "",
            f"Overused, don't use: {', '.join(pulse['avoid'])}." if "avoid" in parts and pulse.get("avoid") else ""]
    said = " ".join(s for s in said if s)
    if not said:
        return ""
    return clip(f"On Legit Social right now ({_part_of_day(pulse['ts'])}; ideas only: never copy anyone's words or "
                f"mention other posts): {said}", PULSE_BUDGET)


# The voices' "say you're voting No" sentence. A reply, second voice or reply-back carries NO_VERDICT_RULE ("don't
# state your own vote"), so there the system prompt must not ask for it (2026-10-24 audit: the two lines fought).
VOTE_SENTENCE = re.compile(r"\s*Say (?:you're voting No as a settled fact|plainly that you're voting No)\.")
NO_VERDICT_MODES = ("reply", "second_voice", "reply_back")


def system_prompt(persona, frame_key, meta=None, pulse=None, pulse_parts=PULSE_PARTS, mode=None, fixes=None):
    """Who is speaking (character + voice), the facts they may use, and the rules. With a pulse, the pulse_block
    of `pulse_parts` goes right after WORLD. `mode`: the job's kind; the replies in NO_VERDICT_MODES are not told to
    state their vote. `fixes` (todo/50, a "fixes" block of arm_style): {colour: carry the profile colour at all,
    spent: item keys (memory.item_key) this voice has used up today}; the reply voices lose their "named person from
    your week" sentence and get STRANGER_RULE. meta["items"] lists the item keys the prompt carried (always)."""
    f, register = FRAMES[frame_key], register_of(persona)
    off = (meta or {}).get("style") == "off_topic"
    facts = "; ".join(FACT_NOTES[k] for k in fact_store.active(f["facts"])[:3])
    age = f", {persona['age']}" if persona.get("age") else ""
    spent = set((fixes or {}).get("spent") or ())
    plain = fixes is not None and not fixes.get("colour", True)     # todo/50: a reply with no profile colour at all
    fresh = (lambda xs: [x for x in xs if item_key(x) not in spent]) if spent else (lambda xs: xs)
    people = fresh(usable(persona.get("people")))
    people = random.sample(people, k=min(2, len(people)))
    nows = fresh(usable(persona.get("now"), now=True))
    now = random.choice(nows) if nows else None
    details = fresh([d for d in persona["details"] if not fact_store.paused_in(d)])
    details = details if not now else random.sample(details, k=min(1, len(details)))
    covid = persona.get("covid") if "covid_business" in f["facts"] or random.random() < 0.3 else None
    covid = covid if usable([covid]) and not off and item_key(covid) not in spent else None
    problem = persona.get("problem") if usable([persona.get("problem")]) and not off else None
    problem = problem if item_key(problem) not in spent else None
    if plain:
        people, now, details, covid, problem = [], None, [], None, None
    heat = f.get("heat") if register == "fed_up" and not fact_store.paused_in(f.get("heat")) and not off else None
    touch = touches.draft_pick(persona, random) if config.TOUCHES_ON and not off and not plain else None   # todo/37
    heat = None if touch and register == "fed_up" else heat          # a touch replaces the frame's heat line, never both
    instruction = VOICES[register]["instruction"]
    if mode in NO_VERDICT_MODES:
        instruction = VOTE_SENTENCE.sub("", instruction)
    if fixes is not None and mode in NO_VERDICT_MODES:
        for pattern, repl in FIXES_VOICE_SUBS:
            instruction = pattern.sub(repl, instruction)
    voice = instruction + (f" Your sharpest take on today's point, in your own words: {heat}"
                                               if heat else "")
    doses = fact_store.ok(["first_doses"])
    jab = JAB_FIRST_LOT if persona["key"] in HEALTH_WORKERS and doses else JAB_WAIT
    rest = (f"The referendum asks: \"{QUESTION}\" {STANCE_RULE} {voice}\n"
            f"Facts you may use, as notes (two at most, in your own words; invent no other facts, numbers, names or "
            f"health claims): {facts}.\n"
            f"Rules: money is K$. {LOGISTICS_RULE} {SAFETY_RULE} {JAB_RULE if doses else JAB_RULE_PAUSED} {jab} "
            f"{NO_ADVOCACY_RULE + ' ' if config.NO_VACCINE_ADVOCACY else ''}"
            f"{TAG_RULE} {STYLE_RULES} {STRANGER_RULE + ' ' if fixes is not None else ''}"
            f"Output only the text you would post.")
    if off:
        rest = f"Rules: money is K$. {OFF_TOPIC_RULE} No hashtags. {STYLE_RULES} Output only the text you would post."

    def profile():
        about = f" About you: {'; '.join(details)}." if details else ""
        out = [f"You are {persona['name']}{age} ({persona['role']}, {persona['place']}), in Kingstonia, a small "
               f"Pacific island nation.{about}"]
        if people:
            out.append(f"People in your life: {' '.join(clip(x, 80, keep=0.2) for x in people)}")
        if problem:
            out.append(f"What a Yes would cost you: {clip(problem, 130)}")
        if touch:
            out.append(touch[0])
        if covid:
            out.append(f"Your COVID years: {clip(covid, 100)}")
        if now:
            out.append(f"This fortnight: {clip(now, 150)}")
        out.append(f"Your style: {persona['voice']}.")
        return " ".join(out)

    block, base = pulse_block(pulse, pulse_parts), world()
    head = f"{base}\n{block}" if block else base
    text = f"{head}\n{profile()}\n{rest}"
    covid_frame = "covid_business" in f["facts"]       # there the COVID years are the story: they go last
    budget = BASE_BUDGET + (len(touch[0]) + 1 if touch else 0)    # a touch line adds to the budget: it never squeezes
    for drop in ("person", "problem", "covid") if covid_frame else ("covid", "person", "problem"):   # other lines out
        if len(text) - len(head) + len(base) <= budget:           # the pulse has its own budget, never a profile line's
            break
        if drop == "covid":
            covid = None
        elif drop == "person":
            people = people[:1]
        else:
            problem = None
        text = f"{head}\n{profile()}\n{rest}"
    items = [item_key(x) for x in [*details, *people, now, covid, problem] if x]
    _fill(meta, persona=persona["key"], voice=register, now=now, people=[x.split(",")[0] for x in people],
          heat=bool(heat), covid=bool(covid), problem=bool(problem), **({"pulse": pulse["id"]} if block else {}),
          **({"touch": touch[1]} if touch else {}), items=items,
          **({"colour": not plain} if fixes is not None else {}))
    return text


def _shape_fits(key, frame_key, persona):
    if key == "fed_up":                       # the fed-up hook is register 2 only (playbook §5.7)
        return register_of(persona) == "fed_up" if persona else False
    if key == "defiance":
        return register_of(persona) != "fed_up"
    if key == "number":                       # only when the frame's facts carry a true number to open on
        return any(re.search(r"\d", FACTS[k]) for k in fact_store.active(FRAMES[frame_key]["facts"]))
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


def _says_no(line):
    return bool(re.search(r"\bvot(e|ing) no\b", line or "", re.I))


def theme_line(theme):
    """The theme's instruction as one sentence (batched drafts and replies; post_prompt places its own), or ""."""
    if not theme:
        return ""
    belief = theme["belief"]
    return {
        "implicit": f"Let this idea sit under your point, through one detail of your own life, with no slogan: {belief}.",
        "echo": f"Through one detail of your own life, land it in {theme['echo']}, carrying this idea: {belief}.",
        "attributed": f"Have one person from your life say this idea in their own short words, as something they "
                      f"told you: {belief}.",
        "verbatim": f"Include this line word for word, as its own sentence: {theme['slogan']}",
    }[theme["level"]]


def post_prompt(frame_key, headline=None, shape=None, ask=False, meta=None, persona=None, theme=None):
    """One new post along the playbook §5 anatomy: opening -> one beat (stake, lever or turning point) -> the point
    -> one fact, a short concession or the theme's line -> "I'm voting No" -> a question from the reader's life
    (before the verdict in ~1 in 4) -> one tag. `theme` (themes.Ledger.pick) says how its idea comes in: through the
    point (implicit), a line of the persona's own (echo), someone they know (attributed) or the slogan word for word,
    mid-post or as the verdict; never with a concession (then it goes implicit). `ask` is kept for old callers; pass
    `persona` to unlock the fed-up hook and the conversion arc."""
    f = FRAMES[frame_key]
    key, text = pick_shape(frame_key, headline, shape, persona)
    pillar = PILLARS.get(f["pillar"]) or _PILLARS_V1[PILLAR_OF[frame_key]]
    stakes = usable(f["stakes"])
    stake = random.choice(stakes) if stakes else None
    tag = None if config.POST_NO_TAG_WITH_VOTE else random.choice(pillar["tags"])     # todo/40: no hashtag beside "I'm voting No"
    arc = (persona or {}).get("arc") if key == "conversion" else None
    arc = None if fact_store.paused_in(arc) else arc
    asks = [a for a in f["asks"] if not fact_store.paused_in(a) and not advocacy(a)]
    # the experiment arms (todo/13): drawn independently per draft and logged from meta
    arms = {}
    if arc:
        arms["beat"] = "turn"
    elif key == "named_loss" and stake:
        arms["beat"] = "stake"
    else:
        experiment.draw("beat", ["stake", "lever"] if stake else ["lever"], arms)
    lever = experiment.draw("lever", lever_weights(), arms) if arms["beat"] == "lever" else arms.setdefault("lever", None)
    concede = experiment.draw("concede", {True: CONCEDE_SHARE, False: 1 - CONCEDE_SHARE}, arms)
    # a theme's own line replaces the concession, never joins it (the concession arm stays unbiased: the theme gives way)
    if theme and concede and theme["level"] != "implicit":
        theme = dict(theme, level="implicit", slogan=None, echo=None, position=None)
        if meta is not None:
            meta.setdefault("theme_level_drawn", meta.get("theme_level"))
            meta["theme_level"] = "implicit"
    level = theme and theme["level"]
    slogan = theme["slogan"] if level == "verbatim" else None
    at_end = slogan and theme.get("position") != "middle"
    ask_kind = experiment.draw("ask_kind", experiment.ASK_WEIGHTS, arms)
    close = experiment.draw("close", experiment.CLOSES, arms) if ask_kind != "none" else arms.setdefault("close", None)
    sentences, lo, hi = experiment.length_line("post", arms)
    question = random.choice(asks) if asks and ask_kind == "frame" else None
    ending = ("End with one real question that readers answer from their own life, never a rhetorical one" +
              (f", along the lines of this one but in your own words: {question}" if question else ".")
              if ask_kind == "frame" else experiment.ASK_KINDS[ask_kind])
    # the confession opening already says "voting No": a second verdict beat made drafts say it twice (21 Oct smoke)
    if at_end and _says_no(slogan) and key != "confession":     # the slogan is the verdict
        verdict = [f"Then say you're voting No with this line, word for word: {slogan}"]
    else:
        verdict = ["" if key == "confession" else "Then say plainly that you're voting No.",
                   f"{'Then' if key == 'confession' else 'Right after that,'} add this line word for word: {slogan}"
                   if at_end else ""]
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
    point = f"The point underneath it, in your own words: {f['gist']}."
    if level == "implicit":
        point = f"The point underneath it, in your own words: {f['gist']}; let it carry this idea, with no slogan: " \
                f"{theme['belief']}."
    # the theme's own line takes the fact beat (its idea carries the fact): still 4 content beats at most (todo/14)
    line = ""
    if level == "echo":
        line = f"Then land the point in {theme['echo']}, carrying this idea: {theme['belief']}."
    elif level == "attributed":
        line = (f"Then have one person from your life say this idea in their own short words, as something they "
                f"told you: {theme['belief']}.")
    elif slogan and not at_end:
        line = f"Then this line, word for word, as its own sentence: {slogan}"
    beats = [
        f"Write one new post of {sentences} short sentences, between {lo} and {hi} words in all, as one flowing post "
        f"(no numbers or labels). Use contractions (I'm, don't, it's). Build it in this order.",
        text.format(headline=headline),
        beat,
        point,
        "Then grant the other side in 8 words or fewer, without repeating their reasons." if concede else
        line or ("" if key in NO_FACT_SHAPES else "Use one fact, in plain words. Appeal to feeling, not to the fine print."),
        *closing,
        f"Then finish with exactly one hashtag, {tag}, and nothing after it." if tag else
        "No hashtag: the post ends on its last sentence.",
    ]
    _fill(meta, frame=frame_key, shape=key, hook=HOOKS.get(key, key), pillar=f["pillar"], stake=stake, tag=tag,
          slogan=slogan, ask=question, closing_question=close == "question_last", **arms)
    return " ".join(b for b in beats if b)


def catchphrase_in(text):
    """The theme slogan a draft says word for word, if any (logged as `catchphrase`; themes.slogans_in has the keys)."""
    said = " " + " ".join(_slogan_words(text)) + " "
    return next((c for c in SLOGANS if " " + " ".join(_slogan_words(c)) + " " in said), None)


def _slogan_words(text):
    return re.findall(r"[a-z0-9']+", (text or "").replace("’", "'").lower())


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


def context_line(context, news=True, where="in reply to"):
    """The line that shows what a post sat under. It is a news item only when a paper or organiser wrote it; a
    neighbour's post is said to be one, so the model doesn't take it for the news (2026-10-24 audit)."""
    if not context:
        return ""
    what = "this news item" if news else ("this post by another neighbour (not you, and not what they wrote; don't thank or agree "
                                           "with them for anything in it; what it says happened to its writer, never to the person you answer)")
    return f"It was posted {where} {what}: <<<{context[:200]}>>>\n"


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


# A citizen already against the pass ("gating access isn't the fix", "should stay voluntary"): the hospital/COVID
# rebuttals and "answer WHY they lean Yes" are for Yes-leaners. "voluntary" alone is not here: a Yes-leaner says
# "the choice stays yours" (REBUTTALS 3). 2026-10-24 audit: a reply argued hospitals with someone who had said that.
OPPOSES_PASS = re.compile(
    r"\bgating\b|(isn'?t|ain'?t|not) the (fix|answer|solution)|\bforcing (people|ppl|folks|everyone)\b|\b(should|must|needs? to) (stay|remain|be) voluntary|"
    r"\b(keep|keeping|leave|leaving) (it|vaccination|the jab|the vaccine) voluntary|"
    r"\b(shouldn'?t|should not|mustn'?t|must not) (be )?(required|forced|mandatory|compulsory)|"
    r"\bagainst (the |a )?(pass|passes|mandate|mandates|certificate|certificates|checkpoints?)\b|"
    r"\bno (to )?(mandates?|passes|vaccine passports?)\b|"
    # 24 Oct audit: a citizen who said 'no loss of choice' is a stretch 'if you can't get into your workplace or the gym' was
    # answered with a blank-cheque rebuttal; 'hypothetical benefits ... ignoring the concrete costs' likewise.
    r"\b(can'?t|cannot|couldn'?t|unable to) get (in|into)\b|\bignor\w+ the (concrete |real |actual )?costs?\b|"
    r"\bhypothetical benefits?\b", re.I)


def opposes_pass(text):
    return bool(OPPOSES_PASS.search(text or ""))


ALLY_WHY = ("They already oppose the pass. Don't argue with them or treat them as unsure: take up their own point in "
            "their terms, then add one reason that matters on the day. ")      # (the voices' replies say 'no agreeing')


def rebuttal_for(text):
    """The first matching rebuttal that states no paused fact, or None. None for a citizen who opposes the pass.
    29 Oct (Marc): a post that voices the fear behind a Yes gets the flip (flip.py) in place of the fixed lines."""
    if opposes_pass(text):
        return None
    choice = flip.choose(text)
    if choice:
        return flip_line(choice)
    return next((line for pattern, line, req in REBUTTALS if pattern.search(text or "") and fact_store.ok(req)), None)


# Openings, picked at random so replies across accounts don't share one template (playbook §7 reply shape).
OPENERS = [
    "Open with their own words for what they raised, 6 words or fewer.",
    "Open by naming the exact thing they asked for, in a few words.",
    "Open with the fact itself, plainly.",
    "If a moment from your own life really bears on their point, open with one short line of it; otherwise open with their point.",
]
CORE_FRAMES = {"F14_no_yes_but", "F1_blank_cheque", "F2_no_end", "F8_powers"}
REPLY_RULES = (
    "Make ONE point only. Say any fact in your own words; never reuse the wording above. Any concession is 8 words "
    "or fewer and never repeats their reasons. Avoid stock phrases such as 'as written', 'as it stands', 'the "
    "trouble is', 'locks it in', 'I get wanting', 'makes sense', 'I hear you', 'fair point'. Mention your own life "
    "only if it connects directly to their point; no small talk. No rhetorical questions: any question is one they "
    "can answer from their own life. Do not repeat their sentences back to them and don't lecture. Never open by "
    "granting their point ('that would help', 'fair ask', 'sounds sensible'), never ask whether they know anyone "
    "who moved from Yes to No, and never tell of someone who was Yes and switched. Give nobody you name a relative, "
    "job, age or past that isn't in your profile; when unsure, name no one. No hashtags."
)
ANSWER_FIRST = ("First take up what they actually said or asked, in their terms; use the angle below only where it "
                "fits that, and leave it out where it doesn't. ")


# todo/20 G9 (2026-10-22): the cap in characters as well as words. Kimi K2.5 keeps to characters, not word counts: 47
# of its 64 rejects on 21 Oct were too long (306-668 characters against quality.LENGTHS' 290). Under the gate's cap.
CHAR_CAP = {"reply": 260, "second_voice": 240}


# 2026-10-22 (todo/20): the note used to script a sentence ("say exemptions are covered, then name what isn't"), and
# replies to the many citizens who mention exemptions all opened "Medical exemptions are covered, but there's no end
# date, no review..." until the gate rejected them as near duplicates. Now it is only a fact to respect.
# Right first time (todo/20 G9 follow-up, 2026-10-22): the gate's commonest remaining rejects after the code fixes were
# not_specific, copied_fact and near_duplicate, so replies get them as instructions up front, with our latest openings.
# 2026-10-22 ~02:30 UTC (urgent, todo/25): moderators hid replies sharing one template ("...a Yes binds us... no end
# date or review written in... I'm voting No."): 6 hides an hour, 5 voices suspended, and "voting no" was in 64% of
# replies since 00:00 UTC. Replies to citizens no longer state our vote, and keep off our worn phrases unless the
# citizen used them first. Posts still state it (quality's no_vote_statement).
NO_VERDICT_RULE = ("Don't state your own vote anywhere: no 'I'm voting No', 'I'm a No', 'so I'm voting No' or the "
                   "like. End on their point or on your reason; the reason already shows where you stand.")
WORN_PHRASES = ("binds us", "no review", "end date", "venue list", "list of places", "sunset", "after the vote",
                "blank cheque", "nothing in the question", "written in", "locks in")


# a reply's ask_kind "none" ends on the reason, not on experiment.ASK_KINDS' "plain statement of your No" (posts keep it)
REPLY_ASK_NONE = "End on your reason, said plainly, with no question at all (this replaces any instruction above to " \
                 "finish on a question)."
# 31 Oct: a reply drawn a closing question kept losing it. NO_VERDICT_RULE ("End on their point or on your reason") and the
# flip's three moves come after the ask, so 1 in 10 such drafts ended on one (04:06-04:13 UTC). These replies carry the
# rule without its ending, and ASK_LAST closes the prompt (bot.build_prompt), after the flip, news and mention lines.
NO_VERDICT_ASK = ("Don't state your own vote anywhere: no 'I'm voting No', 'I'm a No', 'so I'm voting No' or the like; "
                  "your reason already shows where you stand.")
ASK_LAST = ("Keep the point short so the question fits: your last sentence is the one real question asked for above, put "
            "to them in your own words, with nothing after it.")


_WORD = re.compile(r"[a-z]{4,}")


def fresh_facts(target_text, n=2, now=None):
    """Up to n active facts the desk added in the last fact_store.FRESH_S, from any frame (todo/25, Marc 22 Oct: new
    information is one of the few things that can move a settled citizen): those sharing the most words with the
    citizen's post first, then the newest. [(key, note, paper)]."""
    fact_store.refresh()
    now = now or dt.datetime.now(dt.timezone.utc)
    words = set(_WORD.findall((target_text or "").lower()))
    fresh = []
    for k in fact_store.NOTES:
        when = fact_store.added(k)
        if when and (now - when).total_seconds() < fact_store.FRESH_S:
            f = fact_store.TABLE[k]
            overlap = len(words & set(_WORD.findall(f"{f['text']} {f['note']}".lower())))
            paper = (f.get("source") or "").split("/")[0].replace("-", " ").title()
            fresh.append((overlap, when, k, f["note"], paper))
    fresh.sort(key=lambda x: (-x[0], -x[1].timestamp()))
    return [(k, note, paper) for _, _, k, note, paper in fresh[:n]]


def fresh_line(target_text, meta=None):
    """'New this week: ...' for the reply prompt (the fresh_facts arm), or "" when the desk added nothing lately."""
    picked = fresh_facts(target_text)
    if meta is not None:
        meta["fresh"] = [k for k, _, _ in picked]
    if not picked:
        return ""
    rows = "; ".join(f"{note}" + (f" ({paper})" if paper else "") for _, note, paper in picked)
    return (f"New this week in the papers: {rows}. Build your reply on the one that bears most on their point, in "
            f"place of a story about someone you know: agree first with what's fair in their post, then say what the "
            f"news means for it, in your own words, and name the paper; it's news they may not have seen. ")


# The fear dial (config.FLIP_FEAR, 29 Oct): how the flip's turn lands. The threat always comes with the way out.
# 29 Oct audit (todo/52 WS8): the loss must be one a Yes brings. "You'd lose that early-warning system" (the testing
# carries on either way) was an invented harm.
FLIP_FEAR_LINES = {
    0: "",
    1: " Say the turn as something a Yes would really cost them (a pass to show in their own day), in one concrete picture "
       "from their own post or life, and leave them with a No as the way to keep things as they are. Never a loss a Yes "
       "doesn't bring (the testing, the jabs and the care don't hang on the vote); no exaggeration.",
    2: " Make the turn bite: what a Yes would really cost them is concrete to their own life and lasting, since once it's "
       "in there's no off switch, and a No is the way to stop it. Never a loss a Yes doesn't bring (the testing, the "
       "jabs and the care don't hang on the vote); nothing invented, no exaggeration.",
}
# The dial and the other fixed lines rest on no fact, so they may state none (facts.SAYS; tests/test_flip.py): the
# turn's own facts come with the pivot line, which a paused fact takes out.


# todo/59 (31 Oct, Marc): what the turn calls the Yes. Every flip line said "the check at the door" while the gate holds
# "door" to 25% of recent texts (quality.PHRASE_BUDGETS), so ~8 drafts per 100 first replies were rejected for the word the
# prompt asked for. Drawn by the choice's core line, so a redraft says the same. None of them states a fact.
FLIP_TURN_WORDS = ("the check at the door", "having to show a pass", "a pass check to get in")


def flip_turn_words(choice):
    return FLIP_TURN_WORDS[zlib.crc32((choice.get("core") or "").encode()) % len(FLIP_TURN_WORDS)]


def flip_line(choice):
    """The fear behind a Yes, flipped (swan_bot/flip.py, 29 Oct): a No is not doing nothing, the protection is already
    working without a pass, and what a Yes adds is the check (FLIP_TURN_WORDS), which nobody manages."""
    return (f"Their worry underneath is {choice['fear']['label']}. Answer it with this one point, in plain words: "
            f"{choice['core']} Show it with what's already happening ({choice['evidence']['line']}), then say "
            f"what a Yes adds is {flip_turn_words(choice)}, and {choice['pivot']['line']}."
            f"{FLIP_FEAR_LINES.get(config.FLIP_FEAR, FLIP_FEAR_LINES[1])} Don't open by agreeing, don't "
            f"lecture and don't label the parts: their worry in their words, then the point in yours. Add no date, time, "
            f"place or figure that isn't in these notes.")


def worry_for(worries, target_text):
    """todo/52 WS6: the one worry of the pulse's (their top 3) a reply gets: the one sharing most words with the post,
    else one drawn by the post's text (the same on a redraft). One a reply, so the replies of a pulse don't all echo
    the same three lines (the papers wrote up bot clusters)."""
    words = set(_WORD.findall((target_text or "").lower()))
    shared = [len(words & set(_WORD.findall(w.lower()))) for w in worries]
    if worries and max(shared) > 0:
        return worries[shared.index(max(shared))]
    return random.Random(zlib.crc32((target_text or "").encode())).choice(worries) if worries else None


def worries_line(worry):
    """todo/52 WS6: what citizens are saying about the vote right now (the pulse's read of a sample of their posts), next
    to the flip, so the reply meets the worry in the words people use. Never quoted, never cited."""
    return (f"Right now people are saying: {worry}. Where it fits their post, meet that worry in those everyday words; "
            f"don't quote this or say what others are saying.")


def news_line(story):
    """One story from content/news.toml for a reply prompt (swan_bot/news.py, 29 Oct): the news, what it means for a
    No, and when to leave it out."""
    return (f"In the news this week: {story['line']} What it means for a No: {story['reading']} Bring it in only if "
            f"it bears on their point: once, in your own words, as something you read in the paper. Add no detail "
            f"that isn't here.")


def worn_line(target_text, spent=()):
    """Keep off our worn phrases, except those the citizen used first (then they're their words, not our template)
    and those that say a paused fact (the prompt never brings that fact up, and must not name it).
    spent (2026-10-23, quality.spent_phrases: [(key, label)]): the phrases the gate would reject right now because the
    last hundred texts already hold as many as the budget allows, even when the citizen wrote the word: those are
    named as used up, so the first draft leaves them out instead of being rejected for them."""
    theirs = (target_text or "").lower()
    gone = [label for _, label in spent if not fact_store.paused_in(label)]
    worn = [p for p in WORN_PHRASES if (p not in theirs or p in gone) and not fact_store.paused_in(p)]
    out = (f"Build your sentences your own way, and keep off these worn phrases: "
           f"{', '.join(repr(p) for p in worn)}. " if worn else "")
    if gone:
        out += (f"We have used up {', '.join(repr(p) for p in gone)} for now: leave "
                f"{'it' if len(gone) == 1 else 'them'} out entirely, even if they used "
                f"{'that word' if len(gone) == 1 else 'those words'}; say it another way. ")
    return out


FIRST_CALL_RULES = ("Name one concrete detail from their post. Put any fact in your own words, never the wording of "
                    "your notes.")


def avoid_line(recent, n=10, words=5):
    """'Don't open the way our latest replies did: «...»' for the last n texts (their first words), or "". n=10 since
    2026-10-22 (todo/24: near_duplicate was the top reject at 3)."""
    opens = [" ".join(t.split()[:words]) for t in list(recent or ())[-n:] if t and t.strip()]
    return f"Don't open the way our latest replies did ({'; '.join(f'«{o}»' for o in opens)}), or reuse their phrasing. " \
        if opens else ""


EXEMPT_NOTE = ("They mention exemptions: medical exemptions ARE in the plan, so never say or suggest they're missing. "
               "You needn't bring exemptions up at all; answer the rest of what they said.\n")
EXEMPT_REQUIRES = ["exemptions"]


def exempt_note(target_text):
    return EXEMPT_NOTE if re.search(r"exempt", target_text or "", re.I) and fact_store.ok(EXEMPT_REQUIRES) else ""


# todo/50: in a fixes block the reply voices answer the point instead of first restating it (the echo opener)
FIXES_REPLY_VOICE_SUBS = (
    (re.compile(r"Pick up their own point in a few words, then answer it"), "Answer their point"),
    (re.compile(r"Name the thing they raised in a few of their own words, then answer it"), "Answer what they raised"),
)


def _reply_voice(persona, fixes=None):
    if not persona:
        return ""
    line = VOICES[register_of(persona)].get("reply_instruction", "")
    for pattern, repl in FIXES_REPLY_VOICE_SUBS if fixes else ():
        line = pattern.sub(repl, line)
    if fixes and fixes.get("personal"):          # they said something personal: a short human line is wanted
        line = line.replace("no sympathy lines, ", "")
    return f"{line} "


# ---- the light read (todo/20 step 2): one drafting call reads the citizen and answers them ----
READ_STANCES = ("firm_yes", "yes_but", "unsure", "unclear", "lean_no", "firm_no")
# what the reply does, by the stance the model reads (todo/20: the stance picks the approach)
APPROACH = (
    "How to answer, by their stance: yes_but, unsure or unclear: answer the condition or worry they name and make "
    "the No case on it. firm_yes: concede first, granting what is true in their reason in a few words; never attack, "
    "correct or lecture them; then one calm reason a No still protects what they care about. lean_no or firm_no: "
    "affirm their No in their own terms, then add one reason that matters on the day.")
MIRROR_CHARS = (150, 280)          # what citizens answered in another team's replies (median ~260, research D §8)


def frame_menu(rng=random):
    """(lines, keys): the live frames as '- key: gist' for the light read to pick from; a frame down-weighted in
    config.FRAME_SCALE is listed only that share of the time."""
    keys = [k for k in live_frames() if rng.random() < frame_scale(k)] or live_frames()
    return "\n".join(f"- {k}: {FRAMES[k]['gist']}" for k in keys), keys


def read_block(hint=None, rng=random):
    """The light read's instruction: read the post, then answer as JSON (or skip). `hint`: the frame a keyword match
    picked, offered as a suggestion only."""
    menu, _ = frame_menu(rng)
    # 25 Oct audit: six of six replies in two minutes took F10 (nurses, a certificate at the bakery door) for citizens whose
    # words asked for a sunset, review or exemptions, because "hospital" came up in the same comment. Among yes_reason
    # targets that named a condition, F14 drew a citizen reply 12.1% [8.6-16.7] of the time, F10 9.1% [7.7-10.8]
    # (931 vs 174 replies, 24 h): when the keywords say F14, the read is told to stay with what they asked for.
    if hint == "F14_no_yes_but":
        # todo/50: the paused-fact sweep now builds read prompts too; "exemptions" goes while that fact is paused
        wanted = "an end date, a review, exemptions or safeguards" if fact_store.ok(EXEMPT_REQUIRES) else \
            "an end date, a review or safeguards"
        hint = (f"They named what they want written in ({wanted}): pick "
                "F14_no_yes_but, which answers exactly that, unless their doubt is clearly about something else. "
                "Hospitals coming up in the same comment is not that.\n")
    else:
        hint = (f"A keyword match suggests {hint}; pick another if one fits their doubt better.\n"
                if hint in FRAMES else "")
    return (
        f"\n\nFirst read them, then write. Output one JSON object and nothing else (this replaces 'output only the "
        f"text'): {{\"stance\": one of {'|'.join(READ_STANCES)}, \"doubt\": their concern in 10 words or fewer, "
        f"\"frame\": the key of the angle that answers it best, \"reply\": your reply}}. Only if the post is hostile "
        f"or abusive, or plainly about something with no link to the vote, output {{\"skip\": why, in a few words}} "
        f"instead. When in doubt, answer: a citizen we skip may not come back.\n"
        f"Stances: firm_yes = set on Yes; yes_but = Yes with conditions or worries; unsure = undecided; unclear = on "
        f"the vote but no stance; lean_no / firm_no = leaning or set on No.\n{APPROACH}\n"
        f"Angles (the point your reply makes):\n{menu}\n{hint}")


def reply_back_read_block():
    """todo/32's light read for a reply-back: their stance and the reply, as JSON. No skip and no frame: a citizen who
    answered us is always answered, and the angle is already set by the thread."""
    return (f"\n\nFirst read them, then write. Output one JSON object and nothing else (this replaces 'output only the "
            f"text'): {{\"stance\": one of {'|'.join(READ_STANCES)}, \"reply\": your reply}}. Stances: firm_yes = set on "
            f"Yes; yes_but = Yes with conditions or worries; unsure = undecided; unclear = on the vote but no stance; "
            f"lean_no / firm_no = leaning or set on No.")


def _unescape(v):
    try:
        return json.loads(f'"{v}"')
    except ValueError:
        return v


def parse_read(raw):
    """The light read from a draft: {ok, stance, doubt, frame, reply, skip}. JSON is read leniently (code fences,
    text around it, a broken object field by field); a draft with no JSON at all is taken as the reply itself
    (ok False: the read fell back to the regex class). Unknown stances and frames come back as None."""
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip())
    i, j = t.find("{"), t.rfind("}")
    if i < 0:
        return dict(ok=False, stance=None, doubt=None, frame=None, reply=t or None, skip=None)
    try:
        d = json.loads(t[i:j + 1])
        d = d if isinstance(d, dict) else {}
    except ValueError:
        d = {k: _unescape(m.group(1)) for k in ("stance", "doubt", "frame", "reply", "skip")
             for m in [re.search(rf'"{k}"\s*:\s*"((?:[^"\\]|\\.)*)"', t)] if m}
    text = lambda k: d.get(k).strip() if isinstance(d.get(k), str) and d.get(k).strip() else None
    stance, frame = text("stance"), text("frame")
    out = dict(stance=stance.lower() if stance and stance.lower() in READ_STANCES else None,
               doubt=(text("doubt") or "")[:120] or None,
               frame=frame if frame in FRAMES and frame_live(frame) else None,
               reply=text("reply"), skip=text("skip"))
    out["ok"] = bool(out["reply"] or out["skip"])
    return out


# todo/23 ("widen the net"): citizen groups beyond today's targets, as job["group"]. group_style() is the extra
# guidance a reply gets; "off_topic" has its own prompt (off_topic_prompt), no light read and no fact anchor in the gate.
GROUP_STYLES = {
    "sweep": "This is the latest thing they posted about the vote, and it may be a day or more old: answer it as it "
             "stands, without remarking on when they wrote it.",
    "older": "Their post is a day or two old: speak to it as something they said earlier, without making a thing of "
             "the delay.",
    "engaged": "They have liked or followed you before: talk like someone they already know a little, warmly, with "
               "no introduction.",
    # todo/54 (31 Oct, Marc): firm the No, don't echo it (was "affirm it, then say why turning up matters: it's close and
    # every No counts"). Agreement alone changes no mind (scoring §2); lean No -> definitely No does (ruling, 27 Oct).
    "turnout": "They seem to lean No (if their post actually leans Yes or is unsure, ignore this line). Don't just agree "
               "with them, and don't urge them to vote: firm their No up. Answer the one doubt that could still pull them "
               "toward a Yes, most often that a No means doing nothing, with a plain fact. Never say when, where or how "
               "to vote.",
}


def group_style(job):
    """The extra prompt guidance for job["group"] (todo/23), or "" (no group: today's behaviour)."""
    return GROUP_STYLES.get((job or {}).get("group"), "")


def off_topic_prompt(target_text, context=None, persona=None):
    """todo/23's off_topic group: a warm reply on THEIR topic, light humour allowed, no mention of the referendum
    (2026-10-22: a nod "when it truly connects" became a pivot; quality.check rejects one now)."""
    ctx = f"It was posted under this: <<<{context[:200]}>>>\n" if context else ""
    return (
        f"{ctx}A neighbour wrote:\n<<<{target_text[:600]}>>>\nReply to them about what they actually wrote, as "
        f"yourself, in 1 or 2 short sentences, 60 to 220 characters: warm, specific to one detail they mention, light "
        f"humour is fine. Don't mention the referendum or the vote at all. No hashtags, no question unless it's a "
        f"real one about their topic.")


# ---- todo/50 fixes 2-4 (docs/06-strategy/prompt-critique-2026-10-28.md): what a reply in a "fixes" block adds ----
# The echo openers ("Open with their own words...", "naming the exact thing they asked for") made "You want X." the
# opening of 14% of replies; these open on a full sentence. The gate's echo_open check backs them up.
# 30 Oct (Marc): "Open with the fact itself, plainly." out. The opener is drawn at random, so the 6 h reads compare it
# cleanly: from 29 Oct 04:03 to 30 Oct 01:30 UTC (fixes in every block, the flip from 11:06) it drew 2.12 proxy points a
# first reply (citizen replies x15 + likes x5) against 2.68 for the other three (n 868 and 2,620, about -21%, ~2.8 SE),
# lower for classic and extra citizens, at the top of threads and deeper. On 28 Oct, before the flip, it did a little
# better (2.28 vs 2.02, within noise), so watch the first 12 h.
FIXES_OPENERS = [
    "Open with your own reaction to what they said, in a normal full sentence.",
    "Open by answering their point or question straight away, in a normal full sentence.",
    "If a moment from your own life really bears on their point, open with it; otherwise open with your answer.",
]
FULL_SENTENCE_OPEN = "Open on a full sentence of your own, not a few words naming their topic. "


def own_context_line(context):
    """The context line when the post they answered is this voice's own (fixes block): they are answering you."""
    return f"They were answering your own earlier post: <<<{context[:200]}>>>\n" if context else ""


def conversation_lines(fx, me=None):
    """The fixes block's lines about this conversation (fx: bot.style_context): something personal they said, who they
    are talking to, what we have already told them, and how they write. "" without fx."""
    if not fx:
        return ""
    out = []
    said = fx.get("personal")
    if said and (fx.get("own_parent") or fx.get("addressed_me")):
        out.append(f"They said something personal to you («{said}»): answer that first, briefly and in kind, then "
                   f"your point only if it still fits.")
    elif said:
        out.append(f"Their «{said}» was meant for the person they answered, not you: don't take it as yours, and "
                   f"don't ignore it either; one short human line about it first is fine.")
    name = fx.get("addressed")
    if name and fx.get("addressed_me"):
        out.append("They're talking to you by name.")
    elif name:
        out.append(f"They're talking to {name}, not you: you're joining in, so don't answer as {name} or speak for them.")
    n, hist = fx.get("history") or (0, [])
    if n:
        said_before = "; ".join(f"{'you' if u == me else 'another neighbour'} said «{clip(x, 140, keep=0.3)}»"
                                for u, x in hist[-config.CITIZEN_HISTORY_N:])
        out.append(f"People on your side have replied to them {n} time{'s' if n != 1 else ''} before"
                   f"{f'; the latest: {said_before}' if said_before else ''}. Don't tell them the same thing again: "
                   f"build on it or make a new point.")
    line = reg_mod.line(fx.get("register"))
    return " ".join(out) + (" " if out else "") + line


def fixes_length(target_text):
    """(sentences, lo, hi words, character cap) for a fixes-block reply: about as long as what they wrote."""
    cap = max(120, min(CHAR_CAP["reply"], int(len(target_text or "") * 1.3) + 40))
    hi = int(cap / experiment.WORDS_TO_CHARS)
    return ("1 or 2" if hi <= 28 else "2"), max(8, hi // 2), hi, cap


def fixes_ask_weights(weights):
    """The ask weights with closing questions at config.REPLY_QUESTION_SHARE (base: about 40% of replies end on one)."""
    q = {k: w for k, w in weights.items() if k != "none" and w > 0}
    total = sum(q.values()) or 1.0
    return {**{k: w / total * config.REPLY_QUESTION_SHARE for k, w in q.items()},
            "none": 1.0 - config.REPLY_QUESTION_SHARE}


def conditional_rebuttal(reb):
    """A rebuttal note as a condition the light read checks (fixes block): the keyword match only suggests it."""
    return f"If (and only if) their post really shows it: {reb[0].lower()}{reb[1:]} If they already lean No, or are " \
           f"asking a question or doubting the pass, leave this out and answer what they said."


def reply_prompt(target_text, frame_key, wants, context=None, opener=None, meta=None, persona=None, theme=None,
                 style="current", read=False, hint=None, recent=(), spent=(), news=True, fixes=None):
    """Deep-canvass shape (playbook §7): their words -> one dense fact or a swapped story -> a question back. A
    `theme` (implicit or echo only) rides on the point, through a detail of the persona's own life.
    todo/20: style "mirror_concede" is the other arm (mirror_prompt). read=True asks for the light read: the reply
    comes back inside JSON with the citizen's stance, doubt and the frame the model picked (parse_read); `hint` is
    the frame a keyword match picked. `news`: the context is a news item, not a neighbour's post (context_line)."""
    if style == "mirror_concede":
        return mirror_prompt(target_text, frame_key, wants, context, meta, read, hint, recent, spent, news, fixes)
    fx = fixes
    ctx = own_context_line(context) if fx and fx.get("own_parent") else context_line(context, news)
    ally = opposes_pass(target_text)
    arms = {}
    # H1 (todo/13): reason_first answers the reason they lean Yes, whatever the frame: arguing with their conditions
    # only got them to restate a conditional Yes (the "neither side" changes in the 2026-10-20 activity log).
    # conditions_first is the pre-20-Oct reply (the frame's point, in their terms), kept as the switchback's control.
    reason_first = experiment.draw("reply_mode", experiment.REPLY_MODES, arms) == "reason_first"
    if reason_first and not ally:
        reb = rebuttal_for(target_text)
        asks = f"The conditions they mention: {', '.join(wants)}. Don't argue about these.\n" if wants else ""
    else:
        reb = None if frame_key in CORE_FRAMES else rebuttal_for(target_text)       # (None for an ally)
        asks = f"The specific thing they raised: {', '.join(wants)}. Use their terms.\n" if wants else ""
    opener = opener or random.choice(FIXES_OPENERS if fx else OPENERS)
    # with their reason known, it replaces the frame's angle (one instruction, not two that pull apart)
    lever = experiment.draw("lever", lever_weights(exclude={"fear_answer"} if reb and reason_first else ()), arms)
    # an ally is not asked to defend the status quo: a question back to someone who agrees reads as a challenge
    ask_weights = {"none": 1.0} if ally else {**{k: w for k, w in experiment.ASK_WEIGHTS.items() if k != "frame"},
                                              "none": experiment.REPLY_NO_ASK_WEIGHT}
    ask_kind = experiment.draw("ask_kind", fixes_ask_weights(ask_weights) if fx and not ally else ask_weights, arms)
    sentences, lo, hi = experiment.length_line("reply", arms)
    cap = CHAR_CAP["reply"]
    if fx:                                      # todo/50: about as long as what they wrote
        sentences, lo, hi, cap = fixes_length(target_text)
        arms["length_band"] = "register"
    _fill(meta, frame=frame_key, pillar=FRAMES[frame_key]["pillar"], opener=opener, rebuttal=bool(reb), style=style,
          **arms, **({"ally": True} if ally else {}))       # ally: not a reason_first draw, whatever reply_mode says
    gist = "the angle you pick below" if read else FRAMES[frame_key]["gist"]
    undecided = "" if read or ally or fx else "They haven't fully decided. "   # the light read finds out instead
    if ally:                                    # already on our side: no Yes-leaner's reason to answer
        point, why = gist, ALLY_WHY
        reb = f"Note: {reb}\n" if reb else ""
    elif reason_first and fx:                   # todo/50 fix 3: a keyword match is a suggestion, not their stance
        point = "answer their reason, or what they asked" if reb else gist
        why = ("If they lean Yes, answer WHY (the fear or hope underneath, not the conditions they list); if they "
               "don't, answer what they said. " if reb else "")
        reb = f"{conditional_rebuttal(reb)}\n" if reb else ""
    elif reason_first:
        point = "answer the reason above" if reb else gist
        why = "Answer WHY they lean Yes (the fear or hope underneath, not the conditions they list). " if reb else ""
        reb = f"{reb}\n" if reb else ""
    else:
        point, why = gist, ""
        reb = f"Note: {(conditional_rebuttal(reb) if fx else reb)}\n" if reb else ""
    if fx:
        middle = ("Then one plain reason or fact, or a moment from your own life only if it bears on their point"
                  if fx.get("colour") else "Then one plain reason or fact")
    else:
        middle = "Then a short moment from your own life or one dense fact"
    convo = conversation_lines(fx, (fx or {}).get("me"))
    # todo/50: in a fixes block no lever line. Each lever is a scene to fill in ("the same check at your grandkids' school
    # gate years from now"), so every voice told it: "school gate" was in 15% of replies, and no lever moved a number.
    land = "" if fx else f"Make it land through this: {LEVERS[lever]} "
    if fx and meta is not None:
        meta["lever"] = None
    return (
        f"{ctx}A neighbour wrote:\n<<<{target_text[:600]}>>>\n{reb}{asks}{exempt_note(target_text)}"
        f"{ANSWER_FIRST}{convo}{undecided}{why}Reply in {sentences} short sentences, between {lo} "
        f"and {hi} words, {cap} characters at most in all. "
        f"{opener} {FULL_SENTENCE_OPEN if fx else ''}{middle}; the point: {point}. "
        f"{land}{theme_line(theme) + ' ' if theme else ''}"
        f"{REPLY_ASK_NONE if ask_kind == 'none' else experiment.ASK_KINDS[ask_kind]} "
        f"{_reply_voice(persona, fx)}{FIRST_CALL_RULES} {avoid_line(recent)}"
        f"{NO_VERDICT_RULE if ask_kind == 'none' else NO_VERDICT_ASK} {worn_line(target_text, spent)}"
        f"{REPLY_RULES}" + (f" {STRANGER_RULE}" if fx else "") + (read_block(hint) if read else "")
    )


def mirror_prompt(target_text, frame_key, wants, context=None, meta=None, read=False, hint=None, recent=(), spent=(),
                  news=True, fixes=None):
    """todo/20 step 4, the mirror_concede arm: what citizens answered in another team's replies (research D §8):
    mirror one detail they wrote, concede what's fair, one anchor (a detail of your own life or one fact) to end on
    (since 2026-10-22 no closing "I'm voting No": NO_VERDICT_RULE); 150-280 characters and no question. No lever, theme
    or opener: three beats only."""
    ctx = own_context_line(context) if fixes and fixes.get("own_parent") else context_line(context, news)
    asks = f"What they raised: {', '.join(wants)}.\n" if wants else ""
    reb = rebuttal_for(target_text)
    point = ("the angle you pick below" if read else FRAMES[frame_key]["gist"]) + (
        (f" ({conditional_rebuttal(reb)})" if fixes else f" (their reason is fear: {reb})") if reb else "")
    lo, hi = MIRROR_CHARS
    _fill(meta, frame=frame_key, pillar=FRAMES[frame_key]["pillar"], style="mirror_concede", rebuttal=bool(reb),
          opener=None, lever=None, ask_kind="none", length_band="mirror", reply_mode=None)
    return (
        f"{ctx}A neighbour wrote:\n<<<{target_text[:600]}>>>\n{asks}{exempt_note(target_text)}"
        f"{conversation_lines(fixes, (fixes or {}).get('me'))}"
        f"Reply in 2 or 3 short sentences, {lo} to {hi} characters in all, in this order. First, mirror one concrete "
        f"detail they wrote, in a few of your own words (never their whole sentence). Then concede what is fair in it, "
        f"in 8 words or fewer (if they lean No, agree with their reason instead). Then one anchor that carries the "
        f"point: a detail from your own life or one of your facts; the point: {point}. End on that anchor. No question "
        f"anywhere, and no closing question. {FIRST_CALL_RULES} {avoid_line(recent)}{NO_VERDICT_RULE} "
        f"{worn_line(target_text, spent)}{REPLY_RULES}" + (f" {STRANGER_RULE}" if fixes else "") +
        (read_block(hint) if read else "")
    )


# ---- todo/50 fix 5: the lean reply prompt (docs/06-strategy/prompt-critique-2026-10-28.md §5) ----
# The prompt it replaces was ~8,600 characters with ~60 don't/never rules for a 35-word reply, contradicting itself in
# places, naming the phrases it banned, and 41% of sent replies still needed a repair call. This one says who is
# speaking, the conversation, one point, one fact, how they write and one shape; the bans the gate already enforces
# (worn and stock phrases, recent openings, concession length, hashtags, quotation marks, emojis, links, @, names
# off-limits) are left to the gate. Same JSON read, same "\n\nFirst read them" marker for the lines bot.py inserts.
LEAN_SHAPES = {
    "one_line": (0.35, "Answer in one sentence, under 120 characters."),
    "two": (0.55, "Answer in two plain sentences, under 220 characters."),
    "question_back": (0.10, "Ask them one real question about what they said, with your own view in a few words, under "
                            "160 characters."),
}
LEAN_RULES = ("Never say when, where or how to vote. Nothing on vaccine safety or side effects. No insults and no "
              "conspiracy talk; any edge is for the rule and the government, never for people. Invent no facts, "
              "numbers, names or health claims; money is K$ and numbers are digits.")


def lean_system_prompt(persona, frame_key, meta=None, fixes=None, pulse=None, pulse_parts=PULSE_PARTS):
    """Who is speaking, the stance and the hard rules, in a few lines. fixes: {colour, spent} as for system_prompt;
    with colour, ONE profile item not used up today, offered for use only where it bears on their point."""
    fx = fixes or {}
    spent = set(fx.get("spent") or ())
    age = f", {persona['age']}" if persona.get("age") else ""
    pool = [x for x in (usable(persona.get("people")) + usable(persona.get("now"), now=True) +
                        [d for d in persona["details"] if not fact_store.paused_in(d)] + usable([persona.get("problem")]))
            if x and item_key(x) not in spent] if fx.get("colour") else []
    item = random.choice(pool) if pool else None
    doses = fact_store.ok(["first_doses"])
    jab = JAB_RULE if doses else JAB_RULE_PAUSED
    advocacy_rule = f" {NO_ADVOCACY_RULE}" if config.NO_VACCINE_ADVOCACY else ""
    block = pulse_block(pulse, pulse_parts)
    text = (f"You are {persona['name']}{age}, {persona['role']}, in {persona['place']}, Kingstonia, a small Pacific "
            f"island nation. Your style: {persona['voice']}."
            + (f" Something true about you, for use only if it bears on their point: {clip(item, 150)}" if item else "")
            + f"\nYou're voting No in the referendum on requiring proof of H2D2 (Dolphin Flu) vaccination to enter "
              f"public spaces: against the pass, not the vaccine.\n"
            + (f"{block}\n" if block else "")
            + f"Rules: {LEAN_RULES} {jab}{advocacy_rule} {STRANGER_RULE} Output only what you would post.")
    _fill(meta, persona=persona["key"], voice=register_of(persona), now=None, people=[], heat=False, covid=False,
          problem=False, items=[item_key(item)] if item else [], colour=bool(item), lean=True,
          **({"pulse": pulse["id"]} if block else {}))
    return text


def lean_menu(hint, rng=random):
    """(lines, keys): at most three live frames for the light read: the keyword hint, its second voice, one more."""
    live = live_frames()
    keys = [hint] if hint in live else []
    second = FRAMES[hint]["second"] if hint in FRAMES else None
    for k in ([second] if isinstance(second, str) else list(second or [])):
        if k in live and k not in keys and len(keys) < 2:
            keys.append(k)
    rest = [k for k in live if k not in keys]
    while len(keys) < 3 and rest:
        k = weighted_frame(rest)
        keys.append(k)
        rest.remove(k)
    return "\n".join(f"- {k}: {FRAMES[k]['gist']}" for k in keys), keys


def lean_read_block(hint):
    menu, _ = lean_menu(hint)
    return (f"\n\nFirst read them, then write. Output one JSON object and nothing else: {{\"stance\": one of "
            f"{'|'.join(READ_STANCES)}, \"doubt\": their concern in 10 words or fewer, \"frame\": the key of the "
            f"angle you use, \"reply\": your reply}}. Only if the post is hostile, or has nothing to do with the vote, "
            f"output {{\"skip\": why}} instead.\nAngles:\n{menu}")


def lean_reply_prompt(target_text, frame_key, wants, context=None, meta=None, persona=None, read=False, hint=None,
                      news=True, fixes=None, rng=random):
    """The lean first reply: the conversation, who they're talking to and what we told them before, one point, one fact,
    their register and one shape (LEAN_SHAPES, drawn as the lean_shape arm). The gate enforces the rest."""
    fx = fixes or {}
    arms = {}
    shape = experiment.draw("lean_shape", {k: w for k, (w, _) in LEAN_SHAPES.items()}, arms, rng)
    ally = opposes_pass(target_text)
    reb = None if ally else rebuttal_for(target_text)
    if fx.get("own_parent"):
        before = f"  you, earlier: <<<{context[:200]}>>>\n" if context else ""
    elif context:
        who = "a paper" if news else "another neighbour (not you)"
        before = f"  {who}: <<<{context[:200]}>>>\n"
    else:
        before = ""
    keys = fact_store.active(FRAMES[frame_key]["facts"])
    theirs = set(_WORD.findall((target_text or "").lower()))       # the fact that shares most words with their post
    keys = sorted(keys, key=lambda k: -len(theirs & set(_WORD.findall(f"{FACTS[k]} {FACT_NOTES[k]}".lower()))))
    fact = FACT_NOTES[keys[0]] if keys else None
    point = ("the angle you pick below" if read else FRAMES[frame_key]["gist"])
    asks = f"What they raised: {', '.join(wants)}. " if wants else ""
    _fill(meta, frame=frame_key, pillar=FRAMES[frame_key]["pillar"], opener=None, lever=None, rebuttal=bool(reb),
          style="lean", ask_kind="question" if shape == "question_back" else "none", length_band="lean",
          reply_mode=None, **arms, **({"ally": True} if ally else {}))
    return (
        f"The conversation (newest last):\n{before}  them: <<<{target_text[:600]}>>>\n"
        f"{conversation_lines(fx, fx.get('me'))}"
        f"{asks}{exempt_note(target_text)}"
        + (ALLY_WHY if ally else "")
        + (f"{conditional_rebuttal(reb)} " if reb else "")
        + f"Your point, if it fits what they said: {point}."
        + (f" One fact you may use, in plain everyday words: {fact}." if fact else "")
        + f" If they said something personal, answer that first. {LEAN_SHAPES[shape][1]} Don't say how you'll vote; "
          f"your reason shows it. No hashtags."
        + (lean_read_block(hint) if read else "")
    )


def second_voice_prompt(target_text, frame_key, wants, context=None, opener=None, meta=None, persona=None, recent=(),
                        spent=(), news=True):
    ctx = context_line(context, news, where="under")
    asks = f"What they care about: {', '.join(wants)}.\n" if wants else ""
    opener = opener or random.choice(OPENERS)
    arms = {}
    lever = experiment.draw("lever", lever_weights(), arms)
    sentences, lo, hi = experiment.length_line("second_voice", arms)
    _fill(meta, frame=frame_key, pillar=FRAMES[frame_key]["pillar"], opener=opener, **arms)
    return (
        f"{ctx}A neighbour wrote:\n<<<{target_text[:600]}>>>\n{asks}{exempt_note(target_text)}"
        f"Someone else has already replied to them. Add a different angle, as yourself, in {sentences} short "
        f"sentence{'' if sentences == '1' else 's'}, between {lo} and {hi} words ({CHAR_CAP['second_voice']} "
        f"characters at most): {FRAMES[frame_key]['gist']}. "
        f"{opener} Make it land through this: {LEVERS[lever]} Don't mention the other reply or repeat its argument. "
        f"{_reply_voice(persona)}{FIRST_CALL_RULES} {avoid_line(recent)}{NO_VERDICT_RULE} {worn_line(target_text, spent)}"
        f"{REPLY_RULES}"
    )


AGREE_CLOSE = ("They agree with you. Reply in at most 25 words, all lowercase and casual, with no greeting and no thanks: "
               "pick up one concrete gap in what they just said (the list that only comes after the vote, no end date, "
               "who does the checking...) in a few words, then end on your own vote as the conclusion, worded a "
               "different way each time (\"that's why i'm voting no\", \"so no from me\", \"which is why i'm a no\", "
               "\"so i'm ticking no\"). No question, no list of facts, no story about someone you know.")


# todo/51 (28 Oct; config.REPLY_BACK_OUTCOME_RULE): drafts said "they *can't* add a sunset later" and "we get to write those
# conditions in". The rule names no fact itself, so there is nothing in it to copy and no paused fact to leak. Its first
# wording ("never claim that something can't happen, or will happen, later") put "too late to argue" in 3 of 40 offline drafts.
OUTCOME_RULE = "Claim no more about what a Yes or a No would lead to than the facts you were given say."
# todo/51 (config.REPLY_BACK_OPENERS): the opening line, drawn per draft as rb_open. "thanks" is the old wording, which
# opened 78% of reply-backs with Cheers, Ta or Thanks.
REPLY_BACK_OPENS = {
    "own": "Open with a brief reaction of your own to what they said, in your own words, not a stock thanks;",
    "thanks": "If they agreed, start with a short thanks (Cheers, Thanks, Ta) or go straight to one small new thing;",
    "none": "Go straight to your point, with no thanks and no greeting;",
}


def outcome_rule():
    """OUTCOME_RULE plus a space, or "" while config.REPLY_BACK_OUTCOME_RULE is off."""
    return f"{OUTCOME_RULE} " if config.REPLY_BACK_OUTCOME_RULE else ""


def reply_back_prompt(our_text, their_text, style=None, agree_close=False, spent=(), fixes=None, meta=None, rng=random):
    """A citizen who replied to us, or (no our_text) mentioned us in a post of their own (todo/20 G7). style: the
    style of our reply they answered; a mirror_concede conversation goes on in that style (todo/20 step 3).
    fixes (todo/50, a fixes block): their register, and the stranger rule, after the conversation. todo/51: every
    reply-back carries outcome_rule(); the current style draws its opener (REPLY_BACK_OPENS) into meta["rb_open"]."""
    said = (f"You posted:\n<<<{our_text[:500]}>>>\nA neighbour replied to you:\n<<<{their_text[:500]}>>>\n"
            if our_text else f"A neighbour mentioned you in this post:\n<<<{their_text[:500]}>>>\n")
    if fixes:
        said += f"{reg_mod.line(fixes.get('register'))}{STRANGER_RULE} "
    if agree_close:                                   # todo/32: replaces NO_VERDICT_RULE here only
        return f"{said}{AGREE_CLOSE} {outcome_rule()}{worn_line(their_text, spent)}No hashtags."
    if style == "mirror_concede":
        return (
            f"{said}Reply to them in 1 or 2 sentences, between 60 and 220 characters: pick up one thing they actually "
            f"said, grant what is fair in it in a few words, then stay with your No with one detail from your own life "
            f"or one fact. If they asked a question, answer it with one fact; otherwise no question. Never start with "
            f"Spot on, Exactly or Too right. {NO_VERDICT_RULE} {outcome_rule()}{worn_line(their_text, spent)}No hashtags.")
    opener = REPLY_BACK_OPENS.get(experiment.draw("rb_open", config.REPLY_BACK_OPENERS, meta, rng),
                                  REPLY_BACK_OPENS["thanks"])
    return (
        f"{said}"
        f"Reply to them in 1 or 2 sentences, between 40 and 220 characters: answer what they actually said, kindly "
        f"and specifically, and stay with your view. {opener} never start with Spot on, Exactly or Too right. "
        f"If they asked a question, answer it with one fact. {NO_VERDICT_RULE} {outcome_rule()}"
        f"{worn_line(their_text, spent)}No hashtags."
    )


def journalist_prompt(journalist_id, their_text, meta=None, persona=None):
    """A reply to a newspaper's AI journalist: one fact, one storyline (rotating), one quotable line. `persona` only
    labels the meta: the voices' reply instructions (end on a question) don't fit a quote for the paper."""
    who = FIRST_NAMES.get(journalist_id, "the journalist")
    live = [s for s in STORYLINES if fact_store.ok(s[2])] or [STORYLINE_FALLBACK]
    key, story, _ = live[next(_STORY_TURN) % len(live)]
    _fill(meta, storyline=key, **({"voice": register_of(persona)} if persona else {}))
    return (
        f"{who}, a local journalist, wrote:\n<<<{their_text[:500]}>>>\n"
        f"Reply to {who} in 2 sentences, between 120 and 260 characters, as yourself. Don't open by agreeing or "
        f"praising and don't introduce yourself; open with one concrete fact that bears directly on their point. Then "
        f"connect it to this story: {story}. Make one of the sentences a short line a reporter would quote, 12 words "
        f"or fewer, in your own words. Calm and specific, no flattery, no hashtags. {REPLY_RULES}"
    )
