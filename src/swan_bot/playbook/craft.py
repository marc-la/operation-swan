"""Craft: how each argument is said. Per pillar a claim and tags; the five themes (wedge slogans); per frame the
stakes (who loses what under a Yes), the heat line (fed-up voice only) and closing asks (questions answered from the
reader's life).

Humans own the rules: docs/06-strategy/message-playbook.md §2 (pillars), §3 (themes and slogans, power and dead words),
§4 (tags), §5 (post anatomy). Every fact is true in docs/01-competition/setting.md. Merged into content.FRAMES at
import. Pure data: imports nothing from content or quality.
"""

PILLARS = {
    "A": dict(
        name="Don't sign a blank cheque",
        claim="They want a Yes before they'll show you what it covers or when it ends",
        tags=["#VoteNo", "#H2D2No"]),
    "B": dict(
        name="Ordinary life shouldn't need papers",
        claim="School, the bus, your shift, the corner shop: a choice that costs you those isn't a choice",
        tags=["#KeepKingstoniaOpen", "#SmallBusiness", "#WorkersRights"]),
    "C": dict(
        name="Your jab, your call",
        claim="The jab is free and your call either way. This vote is only about the pass at the door",
        tags=["#ChoiceNotCoercion"]),
}

# Themes (playbook §3, 2026-10-21): five wedge slogans, each the short form of one belief our personas reach from
# their own lives. The belief recurs in many wordings; the slogan itself goes out word for word only now and then
# (src/swan_bot/themes.py draws the level and keeps the budgets). Fields:
#   belief    the idea, as a note: what the prompt shows at every level
#   slogan    the exact line: shown to the model only on a verbatim draw
#   echo      ways to say it in a line of one's own (one picked per echo draw); echo_speaker: extra ways for the
#             personas in `verbatim` only (things only they can truly say)
#   personas  who carries the belief (None: everyone); verbatim: who may say the slogan or its echo_speaker forms
#             (None: everyone in personas)
#   frames    the frames it fits (None: any); requires: facts its wording states (paused fact -> theme off)
#   marks     regex: the theme's key words, to count echoes in the logs (never a reject)
#   weight    relative odds among the themes that fit a draft
#   replies   False: posts only (default True)
# Never say anyone has had the H2D2 jab (it isn't out until the last week of October): no "jabbed" lines.
IDENTITY_ECHO = ('a short line in the shape "<what you are>. Voting No.", naming your job or your role in your family '
                 '(never that you have had the jab)')
THEMES = {
    "dont_know": dict(
        belief="nobody can say yet which places a Yes covers (the government won't publish the list until after the "
               "result), so if you can't see it, the safe vote is No",
        slogan="Don't know? Vote No.",
        echo=['a short line of your own that ties not knowing what\'s covered to voting No',
              'a short line of your own built on the words "don\'t know"',
              IDENTITY_ECHO],
        personas=None, verbatim=None, frames=None, requires=["list_later"],
        marks=r"\bdon.?t know\b|\bnobody (knows|can say|can tell)\b|\bno one (knows|can say|can tell)\b",
        weight=2),
    "no_list": dict(
        belief="they want our Yes before they'll show which places count; without the list first, there's no Yes",
        slogan="No list, no Yes.",
        echo=['a short line of your own that makes seeing the list the condition for any Yes',
              'a short line of your own about being asked to sign before seeing which doors count'],
        personas=["lani", "priya", "isla", "josh", "mere", "ben", "dan", "grace", "esther", "paulo", "ngaire", "kai"],
        verbatim=None,
        frames=["F14_no_yes_but", "F1_blank_cheque", "F2_no_end", "F7_livelihoods", "F13_age12", "F12_open_island",
                "F6_islands"],
        requires=["list_later"],
        marks=r"\b(the|a|no|that|which) list\b|\bwhich (places|doors|venues)\b",
        weight=1,
        # posts only: in a reply it argues the citizen's own condition, which got a restated conditional Yes (H1,
        # 20 Oct); reason-first replies answer why they lean Yes instead
        replies=False),
    "get_jab": dict(
        belief="getting the jab when your turn comes and voting No go together: the jab is free and voluntary either "
               "way, and a No stops nobody getting it",
        slogan="Get the jab. Vote No.",
        echo=['a short line of your own that puts getting the jab and voting No side by side',
              'a short line of your own saying a No stops nobody getting the jab',
              IDENTITY_ECHO],
        personas=["priya", "ana", "ruth", "sione", "grace", "esther", "wally", "mere", "paulo"],
        verbatim=None,
        frames=["F3_provax_antipass", "F5_not_here_yet", "F10_staff_and_livelihoods", "F13_age12"],
        requires=["free_either_way"],
        marks=r"\bget (the|your) jab\b|\bjab\b[^.?!]{0,60}\b(vot\w+|a) no\b|\b(vot\w+|a) no\b[^.?!]{0,60}\bjab\b|"
              r"\beither way\b",
        weight=1),
    "own_party": dict(
        belief="even Hawthorne's own People's Alliance members voted the bill down on 15 Oct, so voting No doesn't "
               "mean turning on him",
        slogan="Voted Hawthorne. Voting No.",
        echo=['a short line of your own saying even his own party voted it down'],
        echo_speaker=['a short line of your own that puts having voted Hawthorne next to voting No',
                      IDENTITY_ECHO],
        personas=["josh", "dan", "wally", "kai", "isla"], verbatim=["josh"],
        frames=["F9_parliament", "F8_powers", "F2_no_end", "F1_blank_cheque"],
        requires=["bill_failed"],
        marks=r"\bhawthorne\b|\bown (party|members)\b|\bpeople.?s alliance\b",
        weight=1),
    "staff": dict(
        belief="under a Yes the people behind the counter (baristas, shop staff, drivers, deckhands) end up checking "
               "customers' papers at the door",
        slogan="Baristas, not border guards.",
        echo=['a short line of your own in the shape "<your actual job>, not <a guard or a checkpoint>"',
              'a short line of your own about being hired to serve people, not to check their papers'],
        personas=["lani", "esther", "isla", "dan", "tomasi"], verbatim=["lani", "isla"],
        frames=["F7_livelihoods", "F10_staff_and_livelihoods", "F12_open_island", "F1_blank_cheque"],
        requires=[],
        marks=r"\bborder (guard|post|patrol)s?\b|\bnot (a |the )?(guard|bouncer|checkpoint|cop)s?\b|"
              r"\bcheck(ing)? (people.?s |their |customers.? )?(papers|certificates)\b",
        weight=1),
}

# Lower-case No tags the quality check accepts (playbook §4); #protectkingstonia is the 1-in-10 test tag only.
TAG_ALLOWLIST = {"#voteno", "#h2d2no", "#keepkingstoniaopen", "#smallbusiness", "#workersrights",
                 "#choicenotcoercion", "#protectkingstonia"}

CRAFT = {
    "F14_no_yes_but": dict(
        pillar="A",
        stakes=[
            "A retired nurse went looking for who reviews this each year. Nobody is named, and no review is written into the question.",
            "A youth footy coach can't tell his under-12s whether the clubrooms count as a door: they pick the places after the vote.",
            "A dad went looking for the end date on the ballot. There isn't one, so he can't tell his kids when it stops.",
        ],
        heat="Read the question for when it stops, which doors it covers and who checks on it. None of the three is written down.",
        # 2026-10-20: asks that invite a citizen to restate their conditions get a reworded conditional Yes ("neither
        # side" in the activity log), not a No. Ask about people and what they'd lose instead.
        asks=[
            "Who in your house would be the first one stopped at the door?",
            "Do you know anyone who was a Yes last month and isn't now?",
            "If you're still not sure, what would it cost you to keep things as they are?",
        ]),
    "F1_blank_cheque": dict(
        pillar="A",
        stakes=[
            "A hairdresser can't tell her apprentice if he'll be checking papers at the salon door: they pick the places after the vote.",
            "A mum can't say whether the library or the Saturday market will turn her 14-year-old away, because nobody has seen the list of places.",
            "A resort housekeeper wants to know if the staff entrance counts. Nobody can tell her, and they won't say until after we've voted.",
        ],
        heat="They want your signature now and they'll tell you which doors it covers later. Nobody signs a lease before they've seen the rooms.",
        asks=[
            "Which doors do you walk through in a normal week that could end up on the list?",
            "Who at your work would end up being the person on the door?",
            "Which place would you most want to find on that list, or off it?",
        ]),
    "F2_no_end": dict(
        pillar="A",
        stakes=[
            "A fisher who'd put up with checking papers at his stall for one season can't find out when it stops: nothing we're voting on gives an end date.",
            "A school leaver could be showing a pass at the start of every shift for years, because \"temporary\" only counts once it's written down.",
            "A tour operator taking bookings for next year can't tell her guests when the pass stops: there's no finish line in the question.",
        ],
        heat="If it's temporary, they can write the date down. They didn't, and after a Yes they have to bring it in.",
        asks=[
            "How long would you put up with papers at your door before it felt too long?",
            "What end date would you want written down, if it were your call?",
            "Which part of your week would you want back first if this ran for years?",
        ]),
    "F9_parliament": dict(
        pillar="A",
        stakes=[
            "A man who voted Hawthorne last year watched his own party's members vote this down on 15 Oct. Now a Yes asks him to sign what they wouldn't.",
            "A market stallholder who breathed out when the Assembly said no on 15 Oct gets the same rule back with a Yes, and still no list of places.",
            "A family split between the two parties can still land on one No: People's Alliance and Democratic-Republican members voted it down together.",
        ],
        heat="They couldn't get it through the Assembly on 15 Oct, not even with their own members. So now they want your signature instead.",
        asks=[
            "If the Assembly said no on 15 Oct, why is it back in front of us?",
            "Who in your family votes differently from you, and where are they landing on this?",
            "Who in your street was relieved when the Assembly voted it down?",
        ]),
    "F8_powers": dict(
        pillar="A",
        stakes=[
            "A software developer knows a checkpoint at every door is easy to join up later, whatever today's promise says.",
            "A nan picking up her new biometric ID card has her health records kept off it by one law, and the next Assembly can change a law.",
            "A school receptionist checking passes for this rule could be told to check for the next emergency too: powers like this outlast whoever asked for them.",
        ],
        heat="Today the law keeps health records off the new ID card. Laws change, and they want a checkpoint at the shop door, the school gate and the bus, with no end date.",
        asks=[
            "What would you not want a future government checking at your door?",
            "Where would you draw the line on what a door check can be used for?",
            "If the pass and your ID card were ever joined up, what would you want kept off it?",
        ]),
    "F7_livelihoods": dict(
        pillar="B",
        stakes=[
            "A cafe owner with two student staff takes one off the coffee machine to check papers at the door, and pays for those hours.",
            "A dive operator has to check every visitor's overseas certificate on the boat ramp, just as tourism is getting back on its feet.",
            "A family shop that only just survived the COVID closures can't find out if its door counts: they pick the places after the vote.",
        ],
        heat="They want shop staff on the door checking papers, and they won't say which doors until after we've voted. We remember what the last restrictions did to small businesses.",
        asks=[
            "Who's the one person your favourite local shop couldn't run without?",
            "If your work had to put someone on the door, who would it be?",
            "Which local business got your street through the COVID years?",
        ]),
    "F13_age12": dict(
        pillar="B",
        stakes=[
            "Under a Yes, a 13-year-old would need papers to walk into class, and again to ride the school bus there.",
            "The parent of a 12-year-old can't say yet whether the sports ground, the library or youth club will count: they pick the places after the vote.",
            "Parents who kept every childhood jab up to date never showed a certificate at the school gate. Under a Yes, their 12-year-old would.",
        ],
        heat="They'd have 12-year-olds showing papers to get into maths, and they still won't tell parents which other doors count.",
        asks=[
            "How many kids in your house are 12 or over?",
            "Where does your teenager go after school most days?",
            "What would your 13-year-old say if you told them about the papers?",
        ]),
    "F6_islands": dict(
        pillar="B",
        stakes=[
            "On an outer island the clinic is nurse-led, the GP comes once a week and the hospital is a K$14 ferry away: a 'free choice' costs more out here.",
            "The deckhand on the ferry ramp could end up checking papers for neighbours he has carried across all his life.",
            "A gran riding the ferry to her clinic visit can't find out yet whether the wharf counts, because they pick the places after the vote.",
        ],
        heat="They call it a free choice. Out here the GP comes once a week, the ferry is K$14, and they still won't say whether the wharf counts.",
        asks=[
            "Who in your family rides that ferry most weeks?",
            "Which day does the GP come to your island?",
            "How long does it take you to reach the nearest GP, door to door?",
        ]),
    "F10_staff_and_livelihoods": dict(
        pillar="B",
        stakes=[
            "A pass at the shop door adds no nurse and no bed: Kingstonia Central's 40 nursing posts stay empty while a nurse earns about double in Australia or NZ.",
            "A cleaner on the early shift would need papers to clock on at work, and again for the bus that gets her there.",
        ],
        heat="A checkpoint at the bakery door adds no nurse and no bed. What it adds is papers for your shift.",
        asks=[
            "What's your shift this week, and how do you get there?",
            "Who do you know who has gone nursing in Australia or NZ, or is thinking about it?",
            "Which job in your family would need papers just to clock on?",
        ]),
    "F12_open_island": dict(
        pillar="B",
        stakes=[
            "A stallholder at the Saturday market would have to ask her regulars for papers before she can sell them a mango.",
            "Regatta Week in Crown Harbour and the Mango & Spice Festival in New Haven could start with a queue at the gate for a papers check.",
            "A family day at the beach park starts with checking the teenagers have their papers before anyone leaves the house.",
        ],
        heat="They want papers for the bus, the park and the market, and won't show you the list first. Keep the island open: the jab's free and your call either way.",
        asks=[
            "What's the first place you go on a Saturday off?",
            "Which part of Regatta Week or Mango & Spice do you never miss?",
            "Where does your family head when everyone finally has the same day off?",
        ]),
    "F3_provax_antipass": dict(
        pillar="C",
        stakes=[
            "A bus driver booked in for his own jab still loses under a Yes: he becomes the person on the door, checking papers before anyone can sit down.",
            "A mum who'll take her jab when her turn comes, whose 19-year-old hasn't decided: under a Yes he's the one locked out of the shop, the bus and his shift.",
            "Someone who'd book the jab anyway loses the choosing: under a Yes it stops being their call and becomes a permit for ordinary life.",
        ],
        heat="Childhood jabs here reach the low nineties without one check at the school gate. So why do they need a pass at the shop door for this one?",
        asks=[
            "Which jabs has your family had without anyone checking papers?",
            "Which door in your week would you least want a pass at?",
            "Who in your family would be stopped at the first door?",
        ]),
    "F5_not_here_yet": dict(
        pillar="C",
        stakes=[
            "A family that walks the park every evening would need papers at the gate, with one H2D2 case in Kingstonia and that case in isolation.",
            "The first 120,000 doses already go to health workers and high-risk people; under a Yes, the apprentice buying his lunch needs papers too.",
        ],
        heat="One case, in isolation, and they want papers for shops, schools, buses and parks. The first doses already go to health workers, so why a pass for everyone?",
        asks=[
            "Which door in your week would you least want to show papers at?",
            "Which shop or park in your week would you be showing papers at first?",
            "How many doors do you walk through on an ordinary Saturday?",
        ]),
}
