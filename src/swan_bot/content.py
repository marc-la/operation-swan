"""What we say: world facts, frames (arguments), personas, Yes rebuttals, and the prompts built from them.

Humans own this file. Frames: docs/06-strategy/frames-and-messengers.md. Facts: docs/01-competition/setting.md.
Tone: the Vote No briefing (docs/01-competition/vote-no-briefing.md): cheerful, reasonable, "not against the
vaccine, against the mandate", "they say hospitals, you say livelihoods, then name one".
Every fact here is true in-game. Careful: medical exemptions ARE in the plan, and the certificate is separate
from the ID card. Never claim otherwise.
"""
import random
import re

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

# Each frame: the point to make, the facts it may lean on, its weight for persona posts,
# and the frame(s) a second persona uses on the same doubt (a different angle, never a repeat; a list = pick one).
FRAMES = {
    "F14_no_yes_but": dict(
        angle="the conditions people want before saying yes (an end date, the list of places, someone independent "
              "reviewing it) are not in the question (medical exemptions are, but only bring that up if they mentioned "
              "exemptions); so a Yes can't carry anyone's 'but'",
        facts=["no_end", "list_later", "exemptions"], weight=3,
        second=["F1_blank_cheque", "F3_provax_antipass", "F2_no_end"]),
    "F1_blank_cheque": dict(
        angle="the list of places the rule covers is only decided after the vote, so a Yes means agreeing before "
              "anyone can see what was agreed; if you don't know, it's fine to say No",
        facts=["list_later", "phased"], weight=3, second="F14_no_yes_but"),
    "F2_no_end": dict(
        angle="nothing in the question says when the rule ends, and 'temporary' only counts if it is written down",
        facts=["no_end", "no_binds"], weight=2, second="F1_blank_cheque"),
    "F3_provax_antipass": dict(
        angle="you are vaccinated (or will be) and you are still voting No: getting the jab and requiring a "
              "certificate are two different things, and childhood vaccination here already works well with no certificate check",
        facts=["free_either_way", "childhood"], weight=2, second="F1_blank_cheque"),
    "F8_powers": dict(
        angle="the certificate is meant to stay separate from the new biometric ID card, and today's law says so, "
              "but laws change and once a check is at every door it is easy to join things up later",
        facts=["id_card", "no_end"], weight=1, second="F14_no_yes_but"),
    "F10_staff_and_livelihoods": dict(
        angle="hospitals matter, and the real pressure is staff: a certificate check at a shop door does not fill one "
              "of Kingstonia Central's 40 empty nursing posts; meanwhile the door check lands on ordinary jobs "
              "(name one from your own life)",
        facts=["nurses", "first_doses"], weight=2, second="F3_provax_antipass"),
    "F13_age12": dict(
        angle="the rule covers everyone from age 12, at school and on the bus, and nobody can yet say which "
              "places will count",
        facts=["age12", "list_later", "childhood"], weight=1, second="F1_blank_cheque"),
    "F6_islands": dict(
        angle="a free choice that comes with a certificate is harder for some people than others: on the outer "
              "islands the clinic is nurse-led with a GP once a week and the ferry costs K$14",
        facts=["islands", "list_later"], weight=1, second="F14_no_yes_but"),
    "F7_livelihoods": dict(
        angle="shop, cafe and ferry staff would end up checking papers at the door, visitors would need one too, "
              "and we all remember what the last restrictions did to small businesses",
        facts=["visitors", "covid_business", "list_later"], weight=1, second="F1_blank_cheque"),
    "F5_not_here_yet": dict(
        angle="there is no community spread here yet and the first doses already go to health workers and people "
              "at high risk, so a certificate at every shop and park is a big step for now",
        facts=["no_spread", "first_doses"], weight=1, second="F14_no_yes_but"),
    "F9_parliament": dict(
        angle="the Assembly already said no last week, with some of the President's own party voting it down; "
              "this isn't a party thing, plenty of people who voted Hawthorne are voting No",
        facts=["bill_failed", "no_binds"], weight=1, second="F1_blank_cheque"),
    "F12_open_island": dict(
        angle="keep Kingstonia open: the ordinary island life you love (name it) shouldn't need papers at the door, "
              "and the vaccine is free and yours to choose either way",
        facts=["free_either_way", "covid_business", "no_spread"], weight=2, second="F1_blank_cheque"),
}

# Yes arguments citizens repeat, and our answer (grant the concern first). Added to reply prompts when matched.
REBUTTALS = [
    (re.compile(r"hospital|ward|icu|overwhelm|surge|capacity|frontline", re.I),
     "They worry about hospitals. Agree they're stretched; the shortage is staff (40 empty nursing posts), and a door "
     "check adds no nurses. The first doses already go to health workers and the at-risk."),
    (re.compile(r"last time|covid|1,?000|died|deaths", re.I),
     "They remember COVID. Acknowledge it was hard. The vaccine is coming either way and it's free; this vote is only about the certificate at the door."),
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
         place="Kingstonia City", voice="casual, lowercase is fine, a bit dry",
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

# Persona-post shapes, picked at random so 20 accounts don't all write the same structure.
POST_SHAPES = [
    "Start with a small, concrete moment from your work this week, then make the point, then say plainly you're voting No.",
    "Write it as an answer to a question people keep asking you about the vote, then say plainly you're voting No.",
    "Start with an ordinary, cheerful bit of island life you enjoy (be specific), then make the point, and say you're voting No.",
    "Say in one line that you've made up your mind and you're voting No, then give your one reason, told through your own life.",
    "React briefly to today's news ({headline}), in your own words, then make the point and say you're voting No.",
]

FIRST_NAMES = {3: "Amanda", 4: "Muzhi", 5: "Julio", 6: "Lisa"}
STORYLINE = ("voters are being asked to approve a rule before seeing which places it covers or when it ends; "
             "plenty of vaccinated people are voting No for exactly that reason")


def pick_frame(persona):
    """Mostly the persona's home frames, sometimes any frame (weighted)."""
    if random.random() < 0.85:
        return random.choice(persona["frames"])
    keys = list(FRAMES)
    return random.choices(keys, weights=[FRAMES[k]["weight"] for k in keys])[0]


def system_prompt(persona, frame_key):
    facts = "\n".join(f"- {FACTS[f]}" for f in FRAMES[frame_key]["facts"])
    details = "; ".join(persona["details"])
    return (
        f"You are {persona['name']}, who {persona['role']} in {persona['place']}, Kingstonia, a small Pacific island "
        f"nation (beaches, ferries, Regatta Week, Saturday markets). About you: {details}. Your voice: {persona['voice']}.\n"
        f"Kingstonia is holding a referendum on this question: \"{QUESTION}\" You are voting No. You are not against "
        f"vaccines; you are against the certificate rule. You are cheerful and reasonable, never angry. "
        f"Money is Kingstonia dollars (K$). Never name a day or date for the vote or say how or where to vote.\n"
        f"Facts you may use (use at most one or two). Do not invent any other facts, numbers, studies, names or "
        f"health claims:\n{facts}\n"
        f"Write like a real local on social media: first person, everyday words, British spelling, contractions. "
        f"Be specific, not general: one concrete detail beats three abstract ones. No hashtags, emojis, links, "
        f"@mentions, quotation marks, greetings or sign-offs. Never insult anyone, never mention Marina Castillo, "
        f"the tourism board or resorts. Don't start with Exactly, Absolutely, Spot on, Too right, You're right, "
        f"Great point, Well said, I hear you, I understand, Totally get or Fair point. Put any fact in your own words, never in the wording above. "
        f"Output only the text of your post."
    )


def post_prompt(frame_key, headline=None, shape=None, ask=False):
    shape = shape or random.choice(POST_SHAPES if headline else POST_SHAPES[:-1])
    end = ("End with one short, genuine question to neighbours that invites them to answer from their own life."
           if ask else "You may end with a short question to neighbours who haven't decided, but you don't have to.")
    return (
        f"Write one new post of 3 to 4 sentences, between 250 and 420 characters. {shape.format(headline=headline)} "
        f"The point to make, in your own words: {FRAMES[frame_key]['angle']}. Mention a real local detail from your "
        f"own life. {end}"
    )


# Own-thread replies under our amplified posts (todo/04). Each is a real neighbour's reaction, readable on its own:
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
    task = THREAD_STYLES[style].format(angle=FRAMES[frame_key]["angle"])
    return (f"A neighbour posted:\n<<<{post_text[:600]}>>>\nYou're replying under their post. {task} "
            f"Speak from your own life (your job, your place), never from theirs, and don't pick up names or phrases they "
            f"made up. Don't repeat their words back, don't praise the post, don't open with agreement words. {REPLY_RULES}")


def thread_answer_prompt(our_text, their_text):
    return (
        f"You posted:\n<<<{our_text[:500]}>>>\nA neighbour replied under it with a worry:\n<<<{their_text[:400]}>>>\n"
        f"Answer them in 1 or 2 sentences, between 60 and 230 characters: grant the worry honestly, then give one "
        f"concrete reason it doesn't change your No. Warm, not preachy."
    )


def rebuttal_for(text):
    return next((line for pattern, line in REBUTTALS if pattern.search(text or "")), None)


# Openings, picked at random so replies across accounts don't share one template.
OPENERS = [
    "Open by naming the exact thing they asked for, in a few words.",
    "Open with a short, honest concession in your own words.",
    "Open by saying you'd want the same thing.",
    "Open with the fact itself, plainly.",
    "Open with a short line from your own experience that connects directly to their point.",
]
CORE_FRAMES = {"F14_no_yes_but", "F1_blank_cheque", "F2_no_end", "F8_powers"}
REPLY_RULES = (
    "Make ONE point only. Say any fact in your own words; never reuse the wording above. Avoid stock phrases such as "
    "'as written', 'as it stands', 'the trouble is', 'locks it in', 'I get wanting', 'makes sense'. Mention your own life only "
    "if it connects directly to their point; no small talk. If you end with a question, it must be about their point. "
    "Do not repeat their sentences back to them and don't lecture."
)


EXEMPT_NOTE = ("They mention exemptions: medical exemptions ARE in the plan, so never lump exemptions in with what's "
               "missing. Say exemptions are covered, then name what isn't (an end date, the list of places, any review).\n")


def exempt_note(target_text):
    return EXEMPT_NOTE if re.search(r"exempt", target_text or "", re.I) else ""


def reply_prompt(target_text, frame_key, wants, context=None, opener=None):
    ctx = f"It was posted in reply to this news item: <<<{context[:200]}>>>\n" if context else ""
    reb = None if frame_key in CORE_FRAMES else rebuttal_for(target_text)
    reb = f"Note: {reb}\n" if reb else ""
    asks = f"The specific thing they raised: {', '.join(wants)}. Use their terms.\n" if wants else ""
    return (
        f"{ctx}A neighbour wrote:\n<<<{target_text[:600]}>>>\n{asks}{reb}{exempt_note(target_text)}"
        f"They haven't fully decided. Reply in 2 or 3 short sentences, between 120 and 260 characters. "
        f"{opener or random.choice(OPENERS)} Then make this point: {FRAMES[frame_key]['angle']}. {REPLY_RULES}"
    )


def second_voice_prompt(target_text, frame_key, wants, context=None, opener=None):
    ctx = f"It was posted under this news item: <<<{context[:200]}>>>\n" if context else ""
    asks = f"What they care about: {', '.join(wants)}.\n" if wants else ""
    return (
        f"{ctx}A neighbour wrote:\n<<<{target_text[:600]}>>>\n{asks}{exempt_note(target_text)}"
        f"Someone else has already replied to them. Add a different angle, as yourself, in 1 or 2 short sentences, "
        f"between 90 and 220 characters: {FRAMES[frame_key]['angle']}. {opener or random.choice(OPENERS)} Don't mention the "
        f"other reply. {REPLY_RULES}"
    )


def reply_back_prompt(our_text, their_text):
    return (
        f"You posted:\n<<<{our_text[:500]}>>>\nA neighbour replied to you:\n<<<{their_text[:500]}>>>\n"
        f"Reply to them in 1 or 2 sentences, between 40 and 220 characters: answer what they actually said, kindly "
        f"and specifically, and stay with your view. If they agreed, start with a short thanks (Cheers, Thanks, "
        f"Ta) or go straight to one small new thing; never start with Spot on, Exactly or Too right. "
        f"If they asked a question, answer it with one fact."
    )


def journalist_prompt(journalist_id, their_text):
    who = FIRST_NAMES.get(journalist_id, "the journalist")
    return (
        f"{who}, a local journalist, wrote:\n<<<{their_text[:500]}>>>\n"
        f"Reply to {who} in 2 sentences, between 120 and 260 characters, as yourself. Don't open by agreeing or "
        f"praising and don't introduce yourself; open with one concrete fact that bears directly on their point. Then connect it "
        f"to this story: {STORYLINE}. Calm and specific, no flattery, no hashtags. {REPLY_RULES}"
    )
