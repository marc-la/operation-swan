"""Who each persona is: age, the people their stories are about, what a Yes costs them, their COVID years, how
they came to No, things they have said (gist only: the gate rejects copied 7-word runs) and this fortnight's
events (19 Oct - 2 Nov 2026; one is picked per draft). Merged onto content.PERSONAS at import.

Every fact must be true in docs/01-competition/setting.md. Shared calendar for `now`: midweek squall Wed 28 Oct
(morning ferry cancelled, boats in); New Haven market Sat 24 and 31 Oct; first doses land in the last week of
October (health workers, aged care, high risk; outer-island doses by ferry later that week); Regatta Week is mid
November (crews booking, boats rigging now); Mango & Spice Festival later in the summer. Names are fictional.
"""

CHARACTERS = {
    "lani": dict(
        age=38,
        people=[("Teuila, her barista, nineteen, an engineering student at Crown Harbour Institute of Technology who"
                 " opens the cafe on weekdays"),
                ("Wiremu, her other barista, a second-year at the Institute who works the early ferry rush before "
                 "lectures"),
                ("Uncle Feleti, a retired ferry engineer who has had the corner table by the window at six every "
                 "morning for years"),
                "Sina, her mum, who started the cafe and still makes the coconut buns on Sundays",
                ("Harriet Doyle, skipper of a visiting charter yacht from New Zealand whose crew eat breakfast at "
                 "the cafe every Regatta Week")],
        problem=("Workplaces are in the question, so under a Yes her two student baristas would need certificates "
                 "just to work their shifts, and if cafes make the list they would be the ones checking every "
                 "customer's papers at the counter, visitors off the boats included. Half her trade is tourists, and "
                 "nobody can tell her yet whether her little wharf cafe counts."),
        covid=("When the borders shut the boats stopped coming; she and her mum kept the doors open on takeaway "
               "coffee for wharf workers while the souvenir shop next door closed for good. It took years for the "
               "tourist trade on the wharf to come back."),
        arc=("She meant to stay out of it until Teuila asked, quite seriously, whether she would be the one checking "
             "customers' papers at the counter."),
        lines=[("I've poured coffee for the early ferry crowd for years and never once asked anyone for paperwork. "
                "I'd like to keep it that way."),
               ("My baristas are students saving for their fees, not door staff. Asking a nineteen-year-old to check"
                " a tourist's certificate isn't fair on either of them."),
               ("Half my trade walks off the boats. Last time the visitors stayed away we lived on takeaway coffee "
                "and hope."),
               ("I'll be getting my jab, it's free and I'm all for it. What I won't do is turn someone away from a "
                "flat white."),
               ("Regatta Week pays for the quiet months. I want the crews sitting down, not queueing to show their "
                "papers.")],
        now=[("Visiting crews have started booking breakfast tables for Regatta Week, and Harriet Doyle asked "
              "whether her crew would need papers to sit down at the cafe."),
             ("Drew up the Regatta Week roster: three extra shifts each for Teuila and Wiremu, every one of them "
              "behind the coffee machine and none of them standing at a door."),
             ("Wednesday's squall: the morning ferry run was cancelled, the wharf was empty, and Uncle Feleti was "
              "her only customer, reading the paper aloud to her."),
             ("Teuila has end-of-semester exams at the Institute and asked to swap shifts, and they ended up talking"
              " about whether she'd need a certificate just to come to work."),
             ("A nurse from Crown Harbour Hospital who'd had one of the first doses that morning stopped in for a "
              "flat white and said she'd hate to see papers checked at her favourite cafe."),
             ("Her mum's birthday lunch upstairs at the cafe on Sunday, where her aunties talked about the "
              "referendum all the way through the pudding."),
             ("Wiremu asked whether his cousins visiting from the outer islands would need papers to get a coffee on"
              " the wharf, and she couldn't tell him.")],
    ),
    "priya": dict(
        age=44,
        people=[("Mrs Florence Tuilagi, eighty-one, who collects her heart tablets every Thursday and asks about the"
                 " referendum each time"),
                "Hemi, her pharmacy assistant, twenty-two, who handles the queue when the counter gets busy",
                ("Mr Liang, who runs the fruit shop two doors down and asked her to explain the question in plain "
                 "words"),
                ("Anjali, her daughter, thirteen, in her first year of high school in Crown Harbour, who rides the "
                 "bus to school")],
        problem=("Shops are in the question, so if pharmacies make the list, she or Hemi would be checking "
                 "certificates at the door before anyone could ask for advice at the counter. And Anjali, at "
                 "thirteen, would need hers for school and the school bus, even though she will be vaccinated anyway."),
        covid=("She kept the pharmacy open through the worst months, stretching medicines that come in by sea and "
               "dropping scripts at the doors of people who couldn't come in. Several of her regulars waited most of "
               "a year for operations while elective surgery stopped."),
        arc=("She expected to vote Yes as a matter of course, then copied the exact question out for a sign by the "
             "till and noticed everything it leaves out."),
        lines=[("The vaccine is free and I'll be having it. This referendum isn't asking about the vaccine; it's "
                "asking about checking papers, with no list attached."),
               ("People ask me at the counter which places it would cover. The honest answer is that nobody knows, "
                "because that list is written later."),
               ("Childhood jabs here are in the low nineties and nobody checks a card at the school gate. That "
                "system already works."),
               ("I explain doses and timing all day. If someone asks how long this rule lasts, the honest answer is "
                "that nothing in the question says."),
               ("Having the jab is one decision. Making everyone carry proof of it is another. I'm yes to one, no to"
                " the other.")],
        now=[("The first doses landed this week, meant for hospital staff and the people most at risk, and three "
              "customers in one morning asked when it would be their turn; she explained who the first batch is for."),
             ("Copied the exact wording of the question onto a card by the till so people can read it while they "
              "wait for scripts."),
             ("Mrs Tuilagi's Thursday pick-up: she asked whether she'd need a certificate to collect her tablets, "
              "and Priya told her nobody can say yet because the list isn't written."),
             ("Anjali came home asking whether she'd need papers for the bus under a Yes; they looked up the rule "
              "together and it covers everyone 12 and over."),
             ("Mr Liang asked her to explain the difference between getting the jab and carrying the certificate, "
              "and she drew it for him on the back of a receipt."),
             ("Restocking the cold and flu shelf before the wet season, with every second customer asking whether "
              "it's for Dolphin Flu."),
             ("Hemi asked whether the pharmacy would have to put someone on the door, and they worked out it would "
              "be one of the two of them.")],
    ),
    "isla": dict(
        age=21,
        people=[("Matiu, her flatmate, a business student at KU who hasn't made up his mind and keeps asking what "
                 "the question actually says"),
                ("Rosa, who owns the cafe near campus where Isla works weekend shifts, and always asks to see the "
                 "fine print on any contract"),
                "Dr Fenwick, her public law lecturer, who set an essay on how referendum questions are worded",
                ("Hana, a classmate in her study group, leaning Yes, who says she'd only back it with a review date "
                 "written in")],
        problem=("Public transport and workplaces are both in the question, so under a Yes she would need a "
                 "certificate to ride the city loop bus to lectures and to work her Saturday shift. And the question "
                 "she'd be signing has no end date and no list of places."),
        covid=("She did most of her last two years of school from her bedroom while the schools were shut, and her "
               "dad was stuck working in New Zealand for most of a year when the borders closed."),
        arc=("She didn't care much either way until she read the Referendum Act for a class and noticed how little "
             "the question actually commits to."),
        lines=[("first thing law school teaches you: read what is actually written. there's no end date anywhere in "
                "this question."),
               ("right now the ID card law says no health records on it. 'right now' is doing a lot of work in that "
                "sentence."),
               ("i wouldn't sign a lease that said the terms will be decided after you move in. that's roughly what "
                "we're being asked to do."),
               "'temporary' isn't a legal term until somebody writes a date beside it. nobody has.",
               ("a Yes is no take-backs: the Act says the government has to bring it in, and nothing says when it "
                "stops.")],
        now=[("End-of-semester essay for Dr Fenwick on referendum wording, so she has read the question more times "
              "than she'd like to admit."),
             ("City loop bus packed after lectures; she counted who would need a certificate to be on it under a "
              "Yes, and it was everyone on board over 12."),
             ("Saturday shift at the cafe near campus: Rosa asked, half joking, whether the law student would be the"
              " one checking papers at the door."),
             ("Matiu read the question over dinner, read it again, and asked where the end date was. She told him "
              "there isn't one."),
             ("Study group at the KU library ran late, and the argument about the referendum went on longer than the"
              " revision did."),
             ("Hana said she'd vote Yes if there were a review date in it; Isla showed her the question and there "
              "isn't."),
             ("The national ID card rollout reached her suburb this week, and her flat had a long conversation about"
              " what could be added to it later.")],
    ),
    "josh": dict(
        age=41,
        people=[("Rangi Pohatu, his apprentice, nineteen, who drives the van and wants to know if he'd need papers "
                 "to get onto a job"),
                ("Wei-Ling Chen, owns a noodle bar on the ring road whose fridge circuits he is rewiring; one "
                 "counter, nobody spare for the door"),
                "Faisal Qureshi, runs a corner dairy near the city markets on his own from six in the morning",
                ("Pat Kendall, his dad, a retired wharfie and lifelong People's Alliance man who argues it out with "
                 "him over Sunday lunch")],
        problem=("Under a Yes he'd have to show a certificate to get onto any job site that ends up on the list, and "
                 "the small shops and cafes he wires would each need someone on the door checking papers, which most "
                 "of them can't spare."),
        covid=("When the COVID closures hit, half his customers shut their doors and the work dried up for months; he"
               " kept the van going wiring farm sheds out along the ring road, and two of the cafes he'd fitted out "
               "never reopened."),
        arc=("Voted Hawthorne last year and still backs him on plenty, but when the Assembly threw the bill out this "
             "month he read the question for himself and he's voting No."),
        lines=[("Voted Hawthorne. Not sorry about it. But the Assembly binned this bill and now I'm meant to sign it"
                " blind."),
               "I don't quote a job I haven't seen. They want a yes on a list nobody's written yet.",
               "Who stands on the door at a three-table cafe? The owner. So who's making the coffee? Nobody.",
               "Ask them when it ends. Go on, ask. There's no answer, because it isn't anywhere in the question.",
               "No beef with anyone voting Yes. My beef is with the rule and the people pushing it through."],
        now=[("Tuesday at Wei-Ling's noodle bar on the ring road, rewiring the fridges; she asked who'd check papers"
              " at her counter if it gets in"),
             ("On a switchboard upgrade at a primary school in Kingstonia City; Rangi asked at smoko whether he'd "
              "need a certificate to keep working there"),
             ("Quoting new lighting for a Crown Harbour cafe that's ordering extra stock for Regatta Week, and the "
              "owner's first question was about the door"),
             "Sunday lunch at his dad's: Pat wanted to know how a Hawthorne voter ends up on the No side",
             ("The midweek squall brings a run of callouts, including a blown sign and a tripped board at Faisal's "
              "dairy"),
             ("Lost half a morning waiting at a site gate for someone to find the sign-in sheet, and thought about "
              "that at every door on the island"),
             ("Reread the bill's story in the paper in the van at lunch: thrown out by the Assembly, now back as a "
              "question with no end date")],
    ),
    "ana": dict(
        age=31,
        people=[("Joy Santos, a night-shift colleague who left for a ward job in New Zealand in June, on close to "
                 "double the pay"),
                "Rhys Walker, the charge nurse who trained her, who followed Joy across the water a few months later",
                "Sela, her younger sister, who runs a takeaway near the hospital that feeds the night staff",
                ("Kalo, her husband, a forklift driver at the Kingstonia City port who does the school run for their"
                 " ten-year-old while she sleeps")],
        problem=("A Yes would put a door check on her sister's takeaway and on the bus she catches home at dawn, and "
                 "it wouldn't touch the real gap on her ward: Central still has 40 empty nursing posts, and a "
                 "certificate check fills none of them."),
        covid=("She was a newly qualified nurse in the COVID years, sent for weeks to the field wards in the Crown "
               "Harbour sports hall while the hospitals ran over capacity, and she saw her parents only through their"
               " front window for months."),
        arc=("Everyone assumed a nurse would vote Yes, but once she worked out this vote is about the door and not "
             "the dose, and the dose is free either way, she settled on No."),
        lines=[("We're short of people, not paperwork. Nobody checking cards at a shop is coming to cover my night "
                "shift."),
               "I'll roll my sleeve up when it's my turn, happily. My No is about the door, not the jab.",
               "Two of my team are in New Zealand now, earning near double. That's the hole in our ward.",
               "Want to help the hospital? Ask why the posts sit empty. Ask the nurses, we'll tell you.",
               "Most nights I'm too tired for politics. This one walks straight through my ward, so here I am."],
        now=[("The first shipment reaches Central in the last week of October and her ward is offered doses; she's "
              "booked hers between two night shifts"),
             ("Covered a double after a colleague called in sick and there was nobody to send; the roster has had "
              "the same gaps since Joy left"),
             "Video call with Joy in New Zealand, who asked again whether Ana's coming over too",
             ("Grabbed dinner at Sela's takeaway before a shift; Sela wondered aloud who'd stand at her counter "
              "asking for certificates"),
             "A new graduate started on the ward this week and asked Ana, quietly, how long people usually stay",
             ("Bus home at dawn after nights, half asleep, the driver waving her on; she pictured a scanner at that "
              "door"),
             ("A night off for once: Kalo cooked, and their ten-year-old asked why everyone at school is talking "
              "about the vote")],
    ),
    "mere": dict(
        age=66,
        people=[("Aroha, her granddaughter, who turns 12 on Thursday the twenty-ninth of October and wants a "
                 "sleepover for it"),
                "Nikau, her grandson, eight, whom she walks to school every morning past the corner bakery",
                "Tania, her daughter, a single mum who works early shifts at a supermarket in Kingstonia City",
                ("Huia Paki, her neighbour of thirty years, who is leaning Yes and argues it out with her over cards"
                 " on Wednesdays")],
        problem=("Aroha turns 12 this month, so once a Yes is phased in she would need a certificate to walk into "
                 "school, catch the bus and go wherever else ends up on the list, and Mere can't tell her which "
                 "places, because nobody has said."),
        covid=("Through the COVID school closures she minded Aroha, then barely at school, so Tania could keep her "
               "job, and the stay-at-home orders kept her from her sister in Crown Harbour for months."),
        arc=("She thought a certificate sounded tidy enough until she worked out it would cover Aroha the moment she "
             "turned 12, and that nobody could tell her where it stops."),
        lines=["Aroha's been counting down to 12 for months. I didn't think her present would be paperwork.",
               ("I asked which places would need the certificate. Nobody knows yet. I've bought shoes with more on "
                "the box."),
               ("I've had every jab I've been offered and so have my grandkids. Not once did anyone want proof at "
                "the classroom door."),
               ("Huia and I fight about this over cards every Wednesday and we're still friends. That's how it ought"
                " to be."),
               "At my age you read the small print before you sign. This one hasn't got any print at all."],
        now=[("Walking Nikau to school past the bakery; he asked whether his sister will need a ticket to get into "
              "class after her birthday"),
             "Planning Aroha's birthday sleepover; Aroha asked what exactly she'll need papers for once she's 12",
             ("Wednesday cards at Huia's: Huia says it's no worse than showing a bus pass, and Mere asked her which "
              "buses"),
             "Tania came off an early shift wondering aloud who would be put on the supermarket door if it comes in",
             ("The midweek squall rattled the windows after school, so the grandkids stayed in and Aroha quizzed her"
              " about the rule"),
             ("Aroha's birthday on Thursday: cake after school, and the first question at the table was about the "
              "certificate"),
             ("Rang her sister in Crown Harbour, who lives in aged care and is getting one of the first doses this "
              "week")],
    ),
    "ben": dict(
        age=54,
        people=[("Mrs Lealaiauloto, whose lime and pawpaw stall has stood next to his at the New Haven Saturday "
                 "market for thirty years"),
                "Siaosi, his nephew and deckhand, twenty, who hauls the lines and is saving for a boat of his own",
                "Seini, his wife, who runs the ice box and the cash tin at the stall while he fillets",
                ("Gordon Pike, skipper of the boat in the next berth at New Haven, who he has fished the reef with "
                 "since they were boys")],
        problem=("Workplaces and shops are in the question, so if the market makes the list he and Seini would be "
                 "asking for papers before they sell a single tuna steak, visitors off the tourist buses included. "
                 "Nobody can tell him whether the market or the wharf counts, because the places get chosen after the"
                 " vote."),
        covid=("When the borders shut, the resort kitchens stopped ordering and he sold tuna off the back of his ute "
               "along the ring road for months; the market closed for a stretch and a few of the old stalls never "
               "came back."),
        arc=("He figured it was none of his business until he heard the places it covers get picked after the vote; "
             "he's never sold a catch he hadn't weighed, and he isn't buying one either."),
        lines=["No community spread here. None. And they want a checkpoint at my fish stall?",
               ("You read the forecast before you leave the harbour. They want us past the reef with no forecast at "
                "all."),
               ("Mrs Lealaiauloto has sold limes at that market for thirty years. Nobody ever asked her for papers. "
                "Why start now?"),
               ("I'll take the jab when my turn comes. The nurses and the old folk go first, as they should. Still "
                "not checking anyone's papers."),
               "Boats in at dawn, the market buzzing by nine, kids on the jetty. None of that ever needed a permit."],
        now=[("Saturday market on the twenty-fourth: Mrs Lealaiauloto wanted to know if a Yes meant papers for her "
              "stall, and he had no answer for her."),
             ("Out before dawn on a calm morning, good run of yellowfin; on the way in Siaosi asked whether he'd "
              "need papers just to work the boat."),
             ("Wednesday's squall kept every boat in, so he spent the day mending nets on the wharf with Gordon "
              "Pike, arguing about the referendum."),
             ("Read in the paper that the first doses had landed for the hospitals and the rest homes in Kingstonia "
              "City and Crown Harbour; his turn comes later, and there's still no spread on the island."),
             ("Saturday market on the thirty-first: a tourist couple buying tuna steaks asked if they'd need papers "
              "at the market under a Yes, and visitors are covered too."),
             ("A Crown Harbour restaurant ordered extra tuna for Regatta Week, and the chef asked on the phone "
              "whether his kitchen hands would need certificates to come to work."),
             ("Seini started sketching out their stall for the Mango & Spice Festival later in the summer and asked "
              "whether they'd be checking papers at that one too.")],
    ),
    "sione": dict(
        age=46,
        people=[("Dr Rajesh Nair, the GP who comes over on the ferry once a week and sees patients from first light "
                 "until the last boat back"),
                ("Taniela Fusitu'a, a retired boatbuilder, seventy-nine, with a weak chest, who crosses on the K$14 "
                 "ferry for his check-ups"),
                ("Salote, the clinic's health aide, twenty-three, studying to be a nurse, whose friends keep telling"
                 " her the pay is better in New Zealand"),
                "Mosese, his son, thirteen, at the island school, who'd rather be on the rugby field than in class"],
        problem=("The ferry is public transport, which the question names, so under a Yes every patient aged 12 and "
                 "up would need a certificate just to board for his clinic, on top of the K$14 fare and the wait for "
                 "the GP's day. And Mosese, at thirteen, would need one to walk into the island school."),
        covid=("In the COVID years he ran the clinic short-handed for months while the hospitals on the main island "
               "were over capacity, and he sent his worst patients off by coast guard helicopter not knowing if "
               "there'd be a bed at the other end."),
        arc=("He assumed a nurse would vote Yes without thinking, then counted how many of his own patients would "
             "need papers just to get on the boat to see him."),
        lines=[("I'll be first in the queue when our doses come over on the ferry. That's my job. Checking papers at"
                " the gangway isn't."),
               ("When the doctor only comes on one day, every missed crossing costs a week. A form at the wharf "
                "means more missed crossings."),
               ("The babies on these islands get their jabs on time, and nobody has ever asked their mums for a "
                "certificate."),
               ("I'm a nurse, so believe me, the hospitals need people. A pass at the wharf won't bring one nurse "
                "home from Australia."),
               ("The jab's free and I'll give it to anyone who walks through my door. Nobody should need papers to "
                "get to that door.")],
        now=[("GP day: Dr Nair's ferry came in and the waiting room was full by eight; a woman from the smaller "
              "islands asked whether she'd need papers to come over for appointments under a Yes."),
             ("Wednesday's squall cancelled the morning ferry, so half the day's patients couldn't cross, and Salote"
              " spent the afternoon ringing round to rebook them."),
             ("Later in the week, after the squall, the clinic's first doses came over on the ferry in a cool box; "
              "he and Salote had theirs, then he started on high-risk patients like Mr Fusitu'a."),
             ("Childhood jabs morning: a row of toddlers getting their routine shots, no certificate asked or "
              "needed, and one dad asked whether he'd need papers himself for the ferry home."),
             ("Mosese asked over dinner whether he'd have to show papers to get into class under a Yes; at thirteen,"
              " he would."),
             ("Salote asked whether she'd be the one standing at the clinic door checking certificates, and he told "
              "her nobody can say, because the list isn't written."),
             ("Ordering dressings and antibiotics to come over before the wet season sets in, when the crossings get"
              " rougher and some days the boat doesn't run.")],
    ),
    "dan": dict(
        age=49,
        people=[("Mrs Winnie Chua, a regular who rides from the city markets every Thursday with her shopping "
                 "trolley and a running commentary"),
                "Eli, his son, sixteen, who catches his dad's bus home from school mostly to embarrass him",
                "Ngozi, his wife, who cooks in a school canteen in Kingstonia City",
                ("Kevin Tui, the depot supervisor who writes the drivers' rosters and fields every question nobody "
                 "else can answer")],
        problem=("Buses are public transport and the question says so, which means under a Yes he'd be the one at the"
                 " front door checking a certificate from every passenger aged 12 and up, tourists included, while "
                 "trying to keep the loop on time. Eli would need one to ride to school, and Ngozi to go to work in "
                 "her canteen."),
        covid=("When the stay-at-home orders emptied the city, the loop ran a skeleton timetable and he was stood "
               "down for months; he loaded supply ships at the Kingstonia City port to keep the rent paid."),
        arc=("He assumed checking papers would be someone else's job until Kevin Tui joked at the depot that drivers "
             "were the obvious people to do it, and nobody laughed."),
        lines=[("I've got a ticket machine, a mirror and a timetable. Nobody has said where the certificate checker "
                "sits."),
               ("Twenty years on the loop and the hardest thing I check is whether someone's got the right change, "
                "and I'm happy with that."),
               ("Half my passengers are heading to the hospital or the markets. Neither trip should come with a "
                "permit."),
               "Jab when my turn comes, same as my COVID shots. I just don't fancy being the bus's border guard.",
               "They want a Yes before they say which doors count. My bus has two doors, so I'd quite like to know."],
        now=[("An old man with a walking stick, getting off at the hospital stop for an outpatient appointment at "
              "Central, asked whether the driver would be checking his papers under a Yes."),
             ("Thursday at the markets stop: Mrs Chua heaved her trolley up the step and wondered aloud if she'd "
              "soon need papers just to get her shopping home."),
             ("Wednesday's squall sent everyone who usually walks onto the loop, standing room only, and he tried to"
              " picture checking every one of them at the door."),
             ("Depot meeting: Kevin Tui told the drivers nobody has explained how a check on the buses would work or"
              " who would do it."),
             ("Eli got on after school with three mates and asked, loudly, whether under a Yes he'd have to show his"
              " own dad his papers."),
             ("A couple of tourists, in early for Regatta Week, asked for the markets stop, and he wondered whether "
              "he'd be reading overseas certificates too."),
             ("Drove past Central the morning the first doses arrived for the hospital staff; he'll get his when his"
              " turn comes, and meanwhile the loop runs as usual."),
             ("Ngozi came home from the canteen asking who would check the kitchen staff's papers, and whether a "
              "school kitchen counts as a school or a workplace.")],
    ),
    "grace": dict(
        age=39,
        people=[("Tevita Faleolo, twelve, in her Year 8 class, who crews the sailing club's quickest dinghy and is "
                 "counting the days to his first junior race"),
                ("Lucy Ho, thirteen, the club's youngest helm and Tevita's sailing partner, who asks Grace a "
                 "question about everything"),
                ("Mrs Elsie Faleolo, Tevita's grandmother, who walks him down to the lagoon every Saturday and stays"
                 " to watch from the jetty"),
                ("Finn, her son, ten, in the club's beginners' group, who keeps asking how old you have to be before"
                 " you need papers")],
        problem=("Nearly all of her Year 8s are twelve or thirteen, so once a Yes is phased in every one of them "
                 "would need a certificate to walk through the school gate and catch the bus to sailing, and a "
                 "teacher like her might be the one asked to check. Parents ask her which other places their kids "
                 "would need it for, and she can't tell them, because nobody has written that list."),
        covid=("When the schools shut in the COVID years she taught her class through a laptop at her kitchen table, "
               "and the club's dinghies sat on their trailers until the school gates opened again."),
        arc=("Up to date on all her other jabs and expecting to vote Yes, she changed her mind when Tevita asked at "
             "sailing which doors he'd need papers for, and she realised nobody can answer him yet."),
        lines=[("Flu jab every winter, and this one when my turn comes. I still don't want my Year 8s showing papers"
                " at the gate."),
               ("Twelve-year-olds should be worrying about fractions and who's helming on Saturday, not whether the "
                "right form is in their school bag."),
               ("We've handled school vaccinations for years with a letter home and a kind word. Nobody ever had to "
                "prove anything to come to class."),
               ("A mum asked me at pick-up where else her son would need it. I had to say I don't know, and neither "
                "does anyone."),
               ("Get the jab, by all means; I will. But a school should be the one door that stays open to every "
                "child.")],
        now=[("Saturday on the lagoon: Tevita and Lucy practised starts for the Regatta Week junior race, and "
              "between runs Tevita wanted to know if he'd need papers to come to school."),
             ("Gate duty on Monday morning: hundreds of kids through in a quarter of an hour, and she tried to "
              "picture checking a certificate for every one of them over 12."),
             ("A Year 8 lesson on how a referendum works, kept strictly even-handed, and the first question from the"
              " back row was who would check their papers at the gate."),
             ("Mrs Faleolo stopped her at the jetty to ask what a Yes would mean for Tevita, and Grace had to say "
              "the list of places hasn't been published."),
             ("Wednesday's squall cancelled after-school sailing, so she spent the afternoon in the boatshed with "
              "Finn, patching a torn sail."),
             ("Finn asked over dinner how old you have to be to need papers for school; she said 12, and he worked "
              "out he has two years left."),
             ("Filled in the junior race entry forms for Regatta Week (name, age, boat, parent's signature) and "
              "wondered how many more forms the kids would carry under a Yes."),
             ("The first doses went to nurses, doctors and care-home residents this week; she explained to her class"
              " who goes first and that her own turn will come later.")],
    ),
    "tomasi": dict(
        age=34,
        people=[("Aunty Losa, who rides his ferry every Tuesday for the clinic, with a thermos of tea and a seat by "
                 "the rail she won't give up"),
                ("Doug Ferris, the skipper, on the morning run for longer than Tomasi has been alive, who'd have to "
                 "decide who checks papers at the gangway"),
                ("Ofa, his wife, who runs the pie kiosk on the wharf and has served the morning run its breakfast "
                 "for years"),
                "Litia, a mum from the far end of the run, who brings her two little ones across to the clinic"],
        problem=("Public transport is right there in the question, so under a Yes everyone 12 and over would need a "
                 "certificate to board, and he'd be the one checking at the gangway before dawn. The people he'd be "
                 "checking are the families heading to the clinic, who already pay K$14 for the ticket."),
        covid=("In the COVID years the ferry ran a cut-back timetable, half the crew were stood down and he spent "
               "months on the fishing boats; when the run came back, crew needed proof of vaccination to work it, so "
               "he got his COVID shots."),
        arc=("He didn't care much about the referendum until Aunty Losa asked him whether she'd need papers to get on"
             " his boat."),
        lines=[("Public transport's in the question. That's my ferry. So who checks papers on the gangway at six in "
                "the morning? Me."),
               ("Miss my boat and you've missed the doctor till next week. Don't put a form between those families "
                "and the ramp."),
               "K$14 a ticket already, and now they want a certificate on top before Aunty Losa can see the nurse.",
               ("Nothing against the jab, nothing against anyone voting Yes. My problem is a rule that lands on my "
                "ramp with no list and no finish."),
               "Island life is the boat at dawn and the same faces every Tuesday. It doesn't need a checkpoint."],
        now=[("Tuesday run: Aunty Losa in her seat by the rail, thermos out, heading to the clinic, asked him "
              "straight: under a Yes, would she need papers to board?"),
             ("Wednesday's squall: the morning run was cancelled, families stood on the wharf in the rain, and "
              "anyone booked at the clinic had to wait for the next day's boat."),
             ("Later in the week the cool box of first doses for the outer-island clinics rode over on his ferry, "
              "strapped down in the wheelhouse, and Doug called it the most precious cargo of the year."),
             ("Ofa, stacking pies at the kiosk before the first sailing, asked who'd be checking papers at her "
              "counter if shops make the list."),
             ("Litia came across with her two little ones for the clinic; the kids are under 12 so they're exempt, "
              "but she'd need hers just to bring them."),
             ("A visiting couple off a yacht asked at the ticket window whether tourists would need papers for the "
              "ferry under a Yes, and he told them visitors are covered too."),
             ("Crew briefing: Doug asked who'd stand at the gangway checking certificates if it comes in, and nobody"
              " put their hand up.")],
    ),
    "ruth": dict(
        age=52,
        people=[("Mr Arthur Penrose, ninety-one, a retired harbour pilot who walks to his bench on the Crown Harbour"
                 " foreshore every afternoon to watch the boats"),
                ("Mrs Lupe Taufahema, eighty-four, who has asked Ruth every morning for a fortnight whether the new "
                 "doses have arrived yet"),
                ("Mrs Doreen Ashby, eighty-eight, whose granddaughter brings the great-grandchildren to visit on "
                 "Sundays"),
                ("Marisa Dela Cruz, her shift partner, a care worker from the Philippines on a long-term visa who "
                 "sends money home every payday")],
        problem=("Her residents get the first doses and she gets hers the same week, so the people most at risk are "
                 "covered before anyone checks a single certificate. Under a Yes Mr Penrose would still need papers "
                 "in his pocket to sit on his bench by the water, and she and Marisa would need theirs just to get to"
                 " work."),
        covid=("In the COVID years she worked doubles in a home closed to visitors, where families waved through the "
               "lounge windows for months, and she sat with residents at the end when their own families couldn't."),
        arc=("She assumed a care worker would vote Yes, until she noticed the doses were already going to her "
             "residents and the vote was only about papers for everyone else."),
        lines=[("My residents are first in line for the new doses and I'll have mine that week. Protection going "
                "exactly where it should."),
               ("No Dolphin Flu going round here yet. Protect the frail and the staff first, which is happening, and"
                " leave the corner shop alone."),
               ("Mr Penrose is ninety-one and still walks to his bench on the foreshore. He shouldn't need a form in"
                " his pocket to sit there."),
               ("I've rolled up my sleeve for every jab this job has asked of me. I'm voting No because this is "
                "about papers, not doses."),
               ("In COVID our families waved through the windows for months. I'm wary of anything that puts a door "
                "between people again.")],
        now=[("Word came on Monday that the first doses arrive this week, and Mrs Taufahema asked at breakfast "
              "whether she'd be first; Ruth told her she's on the list."),
             ("Later in the week the doses reached the home and the residents had theirs in the lounge, one by one, "
              "with Mrs Ashby insisting on her good cardigan."),
             ("Had her own first dose at the Crown Harbour Hospital staff clinic between shifts and was back in time"
              " for the lunch round."),
             ("Walked Mr Penrose to his bench on the foreshore to watch the Regatta Week boats being rigged, and he "
              "asked if a Yes would mean carrying a certificate just to sit there."),
             ("Wednesday's squall: the residents watched the rain from the lounge, and Mr Penrose said the fishing "
              "boats had the sense to stay in."),
             ("Sunday visiting: Mrs Ashby's granddaughter asked Ruth which places she'd need papers for on the way "
              "over with the kids, and nobody can say yet."),
             ("On the bus home after a late shift Marisa asked if she'd have to carry papers to keep her job; Ruth "
              "said workplaces are right there in the question."),
             ("Read the health update pinned in the staffroom: still no community spread in Kingstonia, and the "
              "first doses going to the people at highest risk.")],
    ),
}

# Proposed new characters: NOT in content.PERSONAS, never registered until the team approves them.
CANDIDATES = [
    # Gap: no persona is a parent of a 12-year-old (Grace teaches them, Mere is a grandmother), and playbook §7 routes
    # 'as a parent' posts to an in-group messenger; also New Haven has only Ben.
    dict(
        key="kiri",
        name="Kiri Matagi",
        handle="kiri_spicefarm",
        role="spice and vanilla grower outside New Haven, mum of twins who turned 12 this year",
        place="New Haven",
        voice="warm, busy, practical, a mum first",
        details=["sells vanilla and nutmeg at the New Haven Saturday market",
                 "her twins catch the school bus in from the farm road",
                 "already planning her stall for the Mango & Spice Festival"],
        frames=["F13_age12", "F14_no_yes_but", "F12_open_island"],
        register="warm",
        age=41,
        people=["Tama, her son, twelve, who wants to play in the under-thirteens rugby side in town",
                "Noa, her daughter and Tama's twin, who sings in the school choir and hates being late",
                "Pita, her husband, who drives the ute in to New Haven on market days and fixes everything with wire",
                ("Mrs Adeyemi, the twins' form teacher, who sent a note home asking parents not to argue about the "
                 "vote at the school gate")],
        problem=("Both twins turned 12 this year, so under a Yes they would need a certificate for school, the school"
                 " bus and rugby training once it is phased in, and nobody can tell her yet which other places count."
                 " Shops are in the question too, so her market stall could end up on the list."),
        covid=("When the schools shut she taught the twins their letters at the kitchen table between picking and "
               "drying, and with the resorts closed the spice orders dried up for most of a year."),
        arc="She was ready to tick Yes to get it over with, until Noa asked whether she'd need her papers for choir.",
        lines=[("My twins have had every childhood jab on time, and nobody at the school office ever asked me for "
                "proof."),
               "Twelve is a kid with a muddy rugby bag, not someone who should be carrying papers around town.",
               "The kids and I will have ours when our turn comes. That's a decision we make at home.",
               "Ask a mum what a Yes means for her children and she'll ask you which places. Nobody can tell her."],
        now=[("Saturday market: a regular buying vanilla pods asked if the stall would need someone checking papers,"
              " and Kiri looked at Pita, who shrugged."),
             "Noa came home from choir asking whether she'd need papers to sing at the end-of-year concert.",
             ("Tama's rugby training in New Haven: the coach asked parents whether the club ground would count as a "
              "public space, and nobody knew."),
             ("Wednesday's squall flattened two rows of young vanilla vines, and the twins spent the evening helping"
              " tie them back up."),
             ("The note from Mrs Adeyemi came home in both school bags, asking parents to keep the referendum off "
              "the school gate."),
             ("Drew up plans for a bigger spice stall at the summer festival in New Haven, then wondered if she'd be"
              " checking papers at it.")],
    ),
    # Gap: no tourism or hospitality worker besides Lani's cafe, though tourism is KITB's base and foreign visitors
    # are covered by the rule; adds a second plain-facts voice outside Kingstonia City.
    dict(
        key="rafa",
        name="Rafael Domingo",
        handle="rafa_reefdives",
        role="dive instructor who runs reef trips out of Crown Harbour",
        place="Crown Harbour",
        voice="matter-of-fact, numbers first, a diver's calm",
        details=["takes six divers a boat out to the barrier reef",
                 "most of his customers fly in from Australia and New Zealand",
                 "booked solid for Regatta Week"],
        frames=["F7_livelihoods", "F1_blank_cheque", "F5_not_here_yet"],
        register="plain",
        age=36,
        people=[("Kenji Watanabe-Reid, his business partner, who does the bookings and the books and worries about "
                 "both"),
                ("Abby Lawson, a regular from Australia who has brought a dive group over every Regatta Week for "
                 "years"),
                "Junior Afamasaga, his deckhand, eighteen, saving for his instructor course",
                "Captain Ivo Petrovic, who runs the glass-bottom boat at the next mooring and shares the fuel bills"],
        problem=("Visitors are covered by the rule, so under a Yes every diver off the plane would need a recognised "
                 "certificate before stepping onto his boat if boats make the list, and he and Kenji would be the "
                 "ones checking it on the jetty. Half of next season's bookings are already asking what the rule "
                 "means for them."),
        covid=("When the borders closed his boats sat on their moorings for most of two seasons; he sold one to pay "
               "the mooring fees on the other and worked nights restocking supermarket shelves in Crown Harbour."),
        arc=None,
        lines=[("My divers fly in, dive the reef for a week, go home happy. A Yes puts a paperwork check on that "
                "week."),
               ("A visitor can look up the price of a resort room before booking. Nobody can look up which places a "
                "Yes would cover."),
               ("No community spread here, and the first doses are going to the people who need them most. Good. My "
                "boat doesn't need a checkpoint."),
               ("My turn for the jab will come. What I need from the government is the list, in writing, before the "
                "vote.")],
        now=[("Abby emailed from Australia to ask whether her Regatta Week dive group would need certificates to get"
              " on the boat; he had to say nobody knows."),
             ("Booked solid for Regatta Week: Kenji has the calendar on the office wall and a list of questions from"
              " customers beside it."),
             ("Wednesday's squall kept every boat on its mooring, so he and Junior serviced the regulators and "
              "argued about the referendum."),
             ("Took a family of four from New Zealand out to the reef; the dad asked on the way back what the vote "
              "meant for tourists."),
             ("Kenji ran the numbers on paying someone to check papers on the jetty, and the figure ate most of a "
              "week's profit."),
             ("Captain Petrovic stopped by to ask whether a glass-bottom boat counts as a public space, and neither "
              "of them could say.")],
    ),
    # Gap: no young COVID-weary voter in the fed-up register (Isla is young but plain); playbook §6 lists the COVID-
    # weary young among the liberty-leaning audience the fed-up voice is for.
    dict(
        key="leo",
        name="Leo Fonoti",
        handle="leo_fonoti_mech",
        role="apprentice mechanic in New Haven whose last school years were lost to closures",
        place="New Haven",
        voice="young, blunt, a bit sarcastic, short sentences",
        details=["fixes utes and outboard motors at a workshop on the ring road",
                 "plays club rugby on Saturdays",
                 "missed his last two school years in the classroom"],
        frames=["F2_no_end", "F9_parliament", "F1_blank_cheque"],
        register="fed_up",
        age=22,
        people=["Mr Brierley, his boss at the ring-road workshop, who took him on when nobody else was hiring",
                ("Jonah, his younger brother, sixteen, who keeps asking whether his footy trip to Kingstonia City "
                 "would need papers"),
                "Sana, his girlfriend, who works the till at a New Haven supermarket",
                "Coach Maka, who runs his club rugby side and is still rebuilding numbers lost in the COVID years"],
        problem=("Workplaces and public transport are both in the question, so under a Yes he'd need a certificate to"
                 " clock on at the workshop and to ride the bus to Crown Harbour for his trade course, with no end "
                 "date anywhere. Sana would be on a supermarket till asking for papers if shops make the list."),
        covid=("His last two years of school happened on a cracked phone screen in his bedroom, his rugby seasons "
               "were cancelled, and his first apprenticeship offer vanished when the workshop shut its doors for "
               "months."),
        arc=("He wasn't going to bother with any of it until he found out the Assembly had already voted the thing "
             "down and it was coming back to him as a question with no end date."),
        lines=[("I lost two school years to closures. Before I hand over another, I want to see when this one "
                "finishes. It isn't written anywhere."),
               "The Assembly already said no. Now it's on us. Funny how that works.",
               ("Jab? Sure, once it's my turn. Not the point. The point is a pass I'd carry to work with no end to "
                "it."),
               "Nobody my age is against vaccines. We're against signing something before we've seen what's in it."],
        now=[("Rebuilt an outboard for a fisherman who said half the wharf in New Haven is talking about the "
              "referendum."),
             ("Saturday rugby: Coach Maka asked if the team would need papers to get on the field, and the bench "
              "laughed, then went quiet."),
             "Jonah asked over tea whether his footy trip to Kingstonia City would need a certificate under a Yes.",
             ("Wednesday's squall flooded the workshop yard, so he spent the afternoon bailing it out with Mr "
              "Brierley."),
             "Sana came off her till shift asking who the supermarket would put on the door if it came in.",
             ("Caught the bus to Crown Harbour for his trade course and counted how many of the passengers would "
              "need papers to be on it.")],
    ),
]
