"""Variants of persona cards (todo/38): a new account on an existing base card that reads as a different ordinary local.

A variant keeps the card's role, place, frames and argument (problem, covid, arc, lines' gist) and changes who the
person is: display name, username base (handle), age (+-6 y), typing hand, which of the card's details / people /
lines / now events it leans on, and the names of the people in its life. It is stored on the account record as
rec["variant"] (a plain, JSON-safe dict) and reaches prompts ONLY through bot.persona_of(rec) -> `persona(rec)` here,
a read-only overlay on a copy of the card. Profile text is never copied: if the card's profile changes (the facts and
stakes work weights new facts into it), a variant follows.

    v = variants.make_variant("vika", records, rng)      # pure: no network, no LLM, deterministic given the rng
    username = variants.username_for(v["handle"], rng, taken)
    ok, reasons = variants.distinct(v, records)

Schema (version 1):
    v: 1                      schema version
    base: str                 the card key (content.PERSONAS or a staged card in playbook/new_cards.py)
    name, first, last: str    display name ("Tess Aumua", "Tess A." or "Tess"); first and last name
    handle: str               username base, [a-z0-9_]; the registration appends two digits (username_for) unless the
                              handle already ends in digits
    shape: str                one of SHAPES (the handle's kind; the pool keeps these evenly spread)
    age: int                  the card's age +-6 (+-3 for the young, never 60-less for the retired)
    hand: dict                a humanize.HANDS-style dict, every probability moved inside a band from the base hand
    use: {details, people, lines, now: [int]}  indices into the card's lists the variant leans on (subset, shuffled)
    swap: {old: new}          the card's people and the card's own name, replaced everywhere in the profile text
    style_of: str | None      another card (same register) whose voice line it takes, like convert_boosters
    checks: [str]             why the best candidate failed distinct(), if the retry bound ran out; [] otherwise

Handle shapes (SHAPES): firstname_job, nickname, initials_word, place_word, hobby_word, bare_name, word_digits,
first_last, lastname_initial, adj_noun. Chosen so a shape differs from the previous registration's, from the suspended
account being replaced, and so the pool's histogram stays flat (_pick_shape). The charset is [a-z0-9_] only (the
platform says <= 32 characters and unique; existing accounts use letters, digits, underscore and one dot: stay inside).

Names are fictional and fit the setting (docs/01-competition/setting.md): no real public figure, none of the setting's
officials, no name already used by a persona, a person in a profile, or an account in the records (suspended ones too).
"""
import logging
import random
import re

log = logging.getLogger("swan.variants")

VERSION = 1
MAX_TRIES = 40                 # candidates per make_variant before the best one is returned with its reasons
EPS_HAND = 0.12                # least distance between two hands (see hand_distance)
EPS_NAME = 3                   # least edit distance between two handles' stems and between two display names
AGE_BAND = 6
SHAPES = ("firstname_job", "nickname", "initials_word", "place_word", "hobby_word", "bare_name", "word_digits",
          "first_last", "lastname_initial", "adj_noun")
PROB_KEYS = ("lower", "lower_start", "small_i", "apos", "comma", "amp", "dots", "slip", "careful")
_CAP = dict(lower=1.0, lower_start=0.5, small_i=1.0, apos=0.6, comma=0.4, amp=0.4, dots=0.4, slip=0.3, careful=0.9)
_FAMILY = {"phone": ("phone", "tablet"), "tablet": ("phone", "tablet"), "laptop": ("laptop",)}
_DEFAULT_HAND = dict(device="phone", lower=0.0, lower_start=0.0, small_i=0.0, apos=0.0, comma=0.0, amp=0.0, dots=0.0,
                     two_space=False, slip=0.05, careful=0.5)
HANDLE_RE = re.compile(r"^[a-z][a-z0-9_]{2,27}$")

# ---- who the cards are (explicit: the heuristics below are only for cards added later)
GENDER = {"lani": "F", "priya": "F", "isla": "F", "josh": "M", "ana": "F", "mere": "F", "ben": "M", "sione": "M",
          "dan": "M", "grace": "F", "tomasi": "M", "ruth": "F", "esther": "F", "paulo": "M", "wally": "M",
          "ngaire": "F", "kai": "M", "kiri": "F", "rafa": "M", "leo": "M", "vika": "F", "tess": "F", "hari": "M",
          "salote": "F", "dev": "M", "meiling": "F", "anaru": "M", "samir": "M", "juno": "U", "colm": "M",
          "rhea": "F", "bernie": "F"}
_FEMALE = re.compile(r"\b(she|her|hers|daughter|sister|mum|mother|wife|niece|granddaughter|girl|aunt|nana|"
                     r"grandmother|widow|lady)\b", re.I)
_MALE = re.compile(r"\b(he|him|his|son|brother|dad|father|husband|nephew|grandson|boy|uncle|grandfather|lad|"
                   r"bloke)\b", re.I)

# ---- name pools (ASCII letters only: they go into handles). Fictional, Pacific/NZ-flavoured with the setting's mix
# (1 in 6 born overseas). Names already used by a persona, a person or an account are filtered out at call time.
FIRST_F = """Adi Alana Alesi Amiria Anahera Anika Aria Asenati Bethan Briar Bronte Carys Cassie Daisy Dalia Daphne Eden
Ella Eseta Evie Fiona Gwen Hera Hine Ilaisaane Imogen Isabel Jade Jodie Josie Kaia Kalea Karina Kate Keri Lana Leah
Lesieli Lily Lola Maia Maile Mari Matilda Mikayla Millie Mina Nadine Naomi Nina Nola Olive Pania Paige Penina Poppy
Rachel Reia Renee Rosie Ruby Sabrina Salma Sefina Selina Sharon Sofia Talei Tanya Tilly Tiana Vaea Vanessa Violet
Wendy Yvonne Zara Zoe Nalini Priyanka Meera Adaeze Thandi Anneli Cleo Dorothy Edith Gail Harriette Jenna Lorna
Moira Noelle Odette Pru Roslyn Tamsin Una Vivienne Willa Aisha Alinta Amelie Anahita Ange Aperahama Arihia Astrid
Beatrice Bernice Bianca Blessing Bree Brigid Caitlin Carla Cerys Chantelle Charlotte Cheryl Christa Claudia Colleen
Corinne Daphnee Dawn Deanna Delwyn Donna Dylis Elspeth Emere Erin Esme Estelle Faye Felicity Fenella Fern Filomena
Freya Gabrielle Georgina Gillian Glenys Greta Hailey Hattie Heidi Helena Hilda Hinemoa Holly Ingrid Irene 
Iviana Jacqui Janelle Jasmine Jenny Joanna Joyce Julia Kahurangi Karen Kathleen Kelsey Kerry Kiah Kirsten 
Lavinia Leanne Lenora Liesel Linda Lois Louisa Lucinda Lydia Maddy Maggie Mallory Marlene Maureen 
Mirabel Monique Nell Nerida Nicola Niamh Odelia Pamela Patience Paula Perina Petra Philippa Phoebe Primrose
Rae Ramona Rebecca Rhoda Rita Robyn Rochelle Rosalind Sadie Samantha Sandra Serena Shona Sienna Simone Sinead
Siobhan Sonia Stella Susan Sylvie Tabitha Tahlia Tamara Teresa Thelma Tracey Trina Ulrike Valerie Verity Wilma
Winifred Xanthe Yasmin Zelda Zinnia""".split()
FIRST_M = """Aiden Alofa Atu Barry Brent Caleb Cameron Craig Dale Darren Desmond Elijah Emosi Ethan Felix Fraser Gabriel
Glenn Harry Henare Ian Isaac Jacob Jamie Jarrod Joel Kane Kelvin Kenny Lachlan Levi Lincoln Logan Malcolm Manaia
Mateo Nate Neil Nikolai Noel Oscar Pete Rahul Reuben Rex Rob Ronan Stefan Tane Toby Viliami Vince Warren Wes Zane
Arjun Dinesh Kapil Leon Matthew Nasir Pavel Rowan Tevi Aidan Bruce Clive Dennis Errol Frank Hugh Ivor Jim Keith
Leigh Morris Norm Owen Percy Quentin Roy Stuart Trevor Wayne Aaron Abel Adrian Alistair Andre Angus Anthony Archie
Aubrey Austin Benjamin Bernard Blair Boyd Bradley Brendan Cedric Charlie Chris Clarence Colin Connor Cyrus
Damian Danny Declan Dermot Dominic Donald Douglas Duncan Edmund Edward Eric Ewan Farid Fergus Finlay
Francis Gavin Geoffrey Gerald Graham Gregory Harold Heath Howard Hunter Ignatius Jack
Jasper Jeremy Jerome Johan Jonas Julian Justin Karl Kieran Kris Lawrence Lenny Lloyd Lukas Magnus Marco Mario
Martin Maurice Max Michael Miles Nicholas Nigel Olaf Ollie Patrick Paul Philip Ralph Raymond
Reginald Richard Rodney Rory Russell Samuel Sean Sebastian Seth Simon Spencer Stephen Tariq Terence Theo Thomas Tim
Tobias Tyrone Ulysses Walter Wilfred William Xavier Yusuf Zachary""".split()
FIRST_U = """Ari Jordan Sam Kiwa Tui Sasha Reese Robin Morgan Jesse Casey Quinn Terry Lee Dana Jules Billie Frankie""".split()
LAST = """Aitken Akana Alofa Ashworth Bakshi Barnett Bell Brooks Burgess Carr Cooper Cullen Dacosta Dalton Davies
Dunn Eastwood Edwards Faalogo Fakatou Falaniko Fanene Farrell Finau Fitzgerald Fonua Foster Gallagher Gill Grant
Hakaraia Halliday Harrington Havea Hikuroa Holt Huxley Iakopo Jacobs Jennings Kamau Kapoor Kauhale Kaufana
Kelekolio Kerr Khan Kingi Kupu Lacey Langi Lau Leota Lim Lowe Mackay Mahe Malo Marsh Mataele Mathew McKay
Mitchell Moala Monk Murray Nacey Naidu Nand Nathan Nikora Norton Oliver Pasi Patel Penitani Pohe Pritchard Quigley
Rasmussen Rees Ritchie Robati Rowe Saleh Scott Shaw Silva Sims Soane Stirling Taione Takiari Talbot Tamati
Tanuvasa Taumoepeau Tavita Thorne Toala Ulu Vaka Wakefield Wallace Wells Whaanga Wilder Wood Yates Young Zhang
Vuniwai Ravuvu Kolinisau Waqanivalu Brennan Caldwell Dempsey Elliott Fenwick Gilmour Hargreaves Ibbotson Jessop
Kirkwood Lockhart Maddox Nicholls Osborne Pickering Redfern Sutherland Tolliver Underhill Vance Westbrook Adams
Archer Ayers Baxter Beaumont Bishop Blackwood Bowen Bradshaw Bright Buchanan Burke Byrne Calder Campbell Chandler
Clifton Coleman Collins Connolly Crawford Dawson Dixon Donovan Drummond Duffy Ellis Ferguson Fleming Fox
Gibbs Gilbert Goodwin Greer Griffin Hammond Hanley Hartley Hayward Henderson Hodge Howell Hughes
Hutchins Ingram Irving Jarvis Jeffries Keane Kelly Kennedy Lambert Leach Lennox Lindsay Lyons Macrae
Madsen Mansell Markham McBride McCall McDonald McLeod Meade Merrick Moran Morrow Mulholland Nash Newman Nolan
Oakley OBrien Palmer Parsons Pearce Pennington Poole Preston Radcliffe Reynolds Rhodes Roach Rogers
Rutherford Sanderson Savage Sharp Stanton Stewart Sullivan Tait Tanner Thompson Tierney Tobin Townsend
Tucker Vaughan Wade Warner Watts Webb Whitaker Whittle Wilkins Winter Wright Yeoman
Aholelei Alapati Alefosio Anae Ata Atuatasi Aufai Faleafa Faumuina Fuimaono Fusi Hopoi Kalaniuvalu
Kaufusi Kioa Kolo Lemalu Liufau Lolo Maea Mafi Magele Moli Motuliki Naufahu Ofahengaue
Pauga Pili Pulu Salesa Samasoni Seumanu Siale Sika Tago Talakai Tapueluelu Taufa Tevaga Toa Tuala Tuiasosopo
Ulufonua Vainikolo Vave Vili Mua Ngatai Paewai Parata Peihopa Pomare Rangihuna Ratima Rewi Tahu Tauri
Tomoana Waaka Wereta Whata Hohepa Karaka Koro Maihi Marino Nepia Pene Piripi Tuhiwai Wikaira
Chaudhary Prasad Reddy Lal Sharma Pillai Narayan Krishna Maharaj Sami Lakshmi Bhatt Gupta Dutt
Cheung Wong Ng Ong Teo Yeo Goh Bautista Dizon Ocampo Villanueva
Okoye Mensah Boateng Adeleke Banda Moyo Kamara Nwosu Abara
Visser Jansen DeBoer Kruger Hansen Lindqvist Novak Kowalski Petrov Costa Ferreira Moreira """.split()

# never used, whatever the pools say: the setting's officials and orgs, and public figures (real people) the pools could
# make by accident. Lower case.
DENY_TOKENS = {"hawthorne", "castillo", "singh", "whitlock", "reyes", "hale", "brotherston", "abernathy", "halvorsen",
               "meridian", "victor", "marina", "amara", "eleanor", "tomas", "ardern", "luxon", "hipkins", "mahuta",
               "rabuka", "bainimarama", "sopoaga", "malielegaoi", "mataafa", "waititi", "momoa", "lorde", "albanese",
               "morrison", "turnbull", "trump", "biden", "obama", "putin", "macron", "modi", "musk", "gates",
               "bezos", "zuckerberg", "swift", "beyonce", "rihanna", "tupou", "tuipulotu", "ngata", "piutau"}
DENY_FULL = {("dwayne", "johnson"), ("jacinda", "ardern"), ("john", "key"), ("helen", "clark"), ("peter", "jackson"),
             ("keith", "urban"), ("russell", "crowe"), ("taika", "waititi"), ("jason", "momoa"), ("rebel", "wilson"),
             ("sam", "neill"), ("cate", "blanchett"), ("hugh", "jackman"), ("kylie", "minogue")}

# ---- handle words
_JOBS = [(r"store|shop", "store shopkeeper counter"), (r"caf[eé]", "cafe barista coffee"),
         (r"nurse|clinic", "nurse rn ward"), (r"pharmac|chemist", "chemist pharmacy"), (r"student", "uni student"),
         (r"electric", "sparky wiring"), (r"fish|tuna|co-op", "fishing tuna lines coop"), (r"bus ", "bus driver"),
         (r"teach", "teacher teaches"), (r"ferry|deckhand", "ferry deck"), (r"aged|care|support", "carer care"),
         (r"bak", "baker bakery bread"), (r"warehouse|stock", "stock warehouse"), (r"harbour-?master|harbour", "harbour"),
         (r"netball|coach", "coach netball"), (r"software|developer", "dev code"), (r"spice|vanilla|grow|farm", "grower farm"),
         (r"dive|reef", "diver reef"), (r"mechanic", "mech spanners"), (r"plumb", "plumber pipes"),
         (r"stall|preserve|pickle", "stall pickles"), (r"taxi|cab", "cab driver"), (r"video|street food", "eats foodie"),
         (r"office|admin", "admin desk"), (r"front-desk|hotel", "frontdesk hotel"), (r"church|hall|committee", "hall committee"),
         (r"mum|mother|grandkids|nana", "mum nana"), (r"retired", "retired")]
_JOBS_ANY = "local worker resident islander".split()
_PLACES = {"the outer islands": "lagoon reef jetty atoll tidepool sandbar palms outer ferrylane",
           "New Haven": "newhaven spiceroad mango haven orchard hillside",
           "Kingstonia City": "kcity citylights market loop uptown eastside",
           "Crown Harbour": "crownhbr wharf regatta quay harbourside breakwater"}
_PLACES_ANY = "island coast ringroad".split()
_HOBBIES = """surfing ukulele footy rugby netball gardening weaving canoe paddle snorkel taro bbq knitting fishing
sailing drumming crosswords baking running cycling chess carving cricket touch kava rockpool beachcomb fernwalk
kayak darts quilting birding""".split()
_ADJ = "quiet salty slow old little early bright humble windy lazy steady plain red green blue".split()
_NOUN = "tern tide kauri reefs paddler canoe mango fisher wave heron sandal hammock coconut drum".split()
_ROLE_NOUN = dict(F="mum nana aunty sis".split(), M="dad pop uncle bro".split(), U="local islander neighbour".split())
_NICK_END = ["y", "ie", "o", "z", "zy", "sy", "bo", "a"]

_TITLE_SURNAME = {"Mr", "Mrs", "Ms", "Miss", "Dr"}
_TITLE_FIRST = {"Aunty", "Auntie", "Uncle", "Nana", "Papa", "Old", "Nurse", "Captain", "Coach", "Pastor", "Father",
                "Sister", "Brother"}
_TITLE_GENDER = dict(Mr="M", Mrs="F", Ms="F", Miss="F", Uncle="M", Papa="M", Father="M", Brother="M", Aunty="F",
                     Auntie="F", Nana="F", Sister="F")
_KNOWN = {n: g for g, names in (
    ("F", "Teuila Sina Harriet Florence Anjali Rosa Hana Wei-Ling Joy Sela Aroha Tania Seini Salote Winnie Ngozi Lucy "
          "Elsie Losa Litia Lupe Doreen Marisa Talia Ioana Unaisi Noeline Elenoa Babs Deb Saskia Georgie Aiko Priscilla "
          "Vika Pauline Abby Sana Mele Leilani Sia Lia Mareta Losana Kalolaine Rina Anneke Hinewai Nadia Piper Nuala "
          "Orla Deirdre Chloe Lorraine Maraia Lenei Ofa Wiki Huia"),
    ("M", "Wiremu Feleti Hemi Matiu Rangi Faisal Rhys Kalo Nikau Siaosi Gordon Rajesh Taniela Mosese Eli Kevin Tevita "
          "Finn Doug Arthur Fetu Lisiate Sateki Ravi Lafaele Josefa Hamish Hector Manu Tama Noa Pita Kenji Junior Ivo "
          "Jonah Maka Tolu Ioane Falani Kalolo Sefa Isireli Jone Kofi Rawiri Omar Callum Marcus Gareth Cyril Keanu")
    ) for n in names.split()}
_PARTICLES = {"Dela", "De", "Van", "Von", "Le", "La", "Mc", "Mac"}


# ---- small helpers
def _rng(rng):
    if rng is None:
        return random.Random()
    return random.Random(rng) if isinstance(rng, int) else rng


def lev(a, b):
    """Edit distance (insert, delete, replace)."""
    if a == b:
        return 0
    if not a or not b:
        return max(len(a), len(b))
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def near(a, b, k=EPS_NAME):
    """True when the edit distance of a and b is under k (a banded, early-exit lev: the pool compares ~250 strings)."""
    if abs(len(a) - len(b)) >= k:
        return False
    if a == b:
        return True
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) >= k:
            return False
        prev = cur
    return prev[-1] < k


_ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen " \
        "seventeen eighteen nineteen".split()
_TENS = {2: "twenty", 3: "thirty", 4: "forty", 5: "fifty", 6: "sixty", 7: "seventy", 8: "eighty", 9: "ninety"}


def age_words(n):
    """16 -> 'sixteen', 74 -> 'seventy-four'."""
    if n < 20:
        return _ONES[n]
    t, o = divmod(n, 10)
    return _TENS[t] + (f"-{_ONES[o]}" if o else "")


def _tokens(text):
    return {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z'-]*", text or "")}


def _cap_tokens(text):
    return {w.lower() for w in re.findall(r"\b[A-Z][\w'-]+", text or "")}


def _stem(username):
    u = (username or "").lower()
    u = u[5:] if u.startswith("(dry)") else u
    return re.sub(r"[\d_.]+$", "", u)


def hand_distance(a, b):
    """How far apart two hands type: the sum of the probability gaps, plus 0.1 for another device, 0.04 for another
    full-stop habit."""
    a, b = {**_DEFAULT_HAND, **a}, {**_DEFAULT_HAND, **b}
    return (sum(abs(a[k] - b[k]) for k in PROB_KEYS) + (0.1 if a["device"] != b["device"] else 0.0)
            + (0.04 if bool(a["two_space"]) != bool(b["two_space"]) else 0.0))


# ---- the cards
def _staged(key=None):
    """The staged cards (playbook/new_cards.py: card + profile + hand) as merged cards, {key: card}; or one of them."""
    try:
        from .playbook import new_cards
    except ImportError:
        return {} if key is None else None
    out = {c["card"]["key"]: dict(c["card"], **{k: (list(v) if isinstance(v, list) else v)
                                                for k, v in c["profile"].items()}, hand=dict(c["hand"]))
           for c in new_cards.NEW_CARDS if key is None or c["card"]["key"] == key}
    return out if key is None else out.get(key)


def card_for(key):
    """One card as variants see it: the live one (content.PERSONA_BY_KEY already carries the merged profile) with its
    hand, else the staged one, else None. A copy: nothing shared is changed."""
    from . import content, humanize
    card = content.PERSONA_BY_KEY.get(key)
    if card is None:
        return _staged(key)
    return dict(card, hand=dict(humanize.HANDS.get(key) or humanize.CANDIDATE_HANDS.get(key) or _DEFAULT_HAND))


def default_cards():
    """{key: card} for every card, live and staged (the live one wins a key both have)."""
    from . import content
    out = _staged()
    out.update({k: card_for(k) for k in content.PERSONA_BY_KEY})
    return out


def _as_map(cards):
    if cards is None:
        return default_cards()
    return cards() if callable(cards) else cards


def _gender(card):
    g = GENDER.get(card["key"])
    if g:
        return g
    text = " ".join([card.get("problem") or "", card.get("covid") or ""] + list(card.get("details") or []))
    f, m = len(_FEMALE.findall(text)), len(_MALE.findall(text))
    return "F" if f > m + 1 else "M" if m > f + 1 else "U"


# ---- people in a profile: parse "Mrs Florence Tuilagi, eighty-one, who ..." into what to swap
def parse_person(entry):
    """{'gender', 'first', 'last'} for a people entry; first/last are None when the entry has no such part. Handles
    'Old Tolu', 'Mr Brandt', 'Mrs Florence Tuilagi', 'Marisa Dela Cruz', 'The Rokotuni family'."""
    head, _, rest = entry.partition(",")
    toks = head.split()
    gender = None
    if toks and toks[0] == "The" and toks[-1].lower() == "family":
        return dict(gender="U", first=None, last=" ".join(toks[1:-1]) or None)
    title = None
    if toks and toks[0] in _TITLE_SURNAME | _TITLE_FIRST:
        title, toks = toks[0], toks[1:]
        gender = _TITLE_GENDER.get(title)
    if not toks:
        return dict(gender=gender or "U", first=None, last=None)
    if title in _TITLE_SURNAME and len(toks) == 1:
        first, last = None, toks[0]
    elif len(toks) == 1:
        first, last = toks[0], None
    else:
        first, last = toks[0], " ".join(toks[1:])
    if gender is None:
        gender = _KNOWN.get(first or "")
    if gender is None:                                         # a relation word before the "who ..." clause
        seg = rest.partition(" who ")[0]
        f = len(re.findall(r"\b(daughter|sister|mum|mother|wife|niece|granddaughter|widow)\b", seg, re.I))
        m = len(re.findall(r"\b(son|brother|dad|father|husband|nephew|grandson)\b", seg, re.I))
        gender = "F" if f > m else "M" if m > f else "U"
    return dict(gender=gender, first=first, last=last)


def _pool_for(gender):
    return {"F": FIRST_F + FIRST_U, "M": FIRST_M + FIRST_U}.get(gender, FIRST_F + FIRST_M + FIRST_U)


def _blocked_tokens(cards, records):
    """Lower-case name tokens nobody new may take: every persona's name, every person in any profile, every LIVE
    account's display name and every live variant's names and swaps, and the deny list. A suspended account's people
    names are free again (the pools are finite); its username and display name still count in _check."""
    out = set(DENY_TOKENS)
    for c in cards.values():
        out |= _tokens(c["name"]) | {t for p in c.get("people") or [] for t in _cap_tokens(p.split(",")[0])}
    for r in records or []:
        if not _is_active(r):
            continue
        out |= _tokens(r.get("display_name"))
        v = r.get("variant") or {}
        out |= _tokens(v.get("name")) | {t for x in (v.get("swap") or {}).values() for t in _tokens(x)}
    return out


# ---- voices (who counts as "another active voice")
def _is_active(r):
    return r.get("status", "active") == "active"


def _is_voice(r):
    return r.get("role", "voice") != "booster" and r.get("persona") is not None


def _voice_hand(r, cards):
    v = r.get("variant")
    if v and v.get("hand"):
        return v["hand"]
    style = (r.get("converted") or {}).get("style_of")
    card = cards.get(style) or cards.get(r.get("persona")) or {}
    return card.get("hand") or _DEFAULT_HAND


def _voice_names(r, cards):
    """Lower-case name tokens a voice's profile carries: its own and its people's."""
    v = r.get("variant")
    if v:
        return _tokens(v["name"]) | {t for x in v.get("swap", {}).values() for t in _tokens(x)}
    card = cards.get(r.get("persona")) or {}
    if r.get("converted"):
        return _tokens(r.get("display_name"))
    return _tokens(card.get("name")) | {t for p in card.get("people") or [] for t in _cap_tokens(p.split(",")[0])}


# ---- the pieces of a candidate
def _pick_shape(records, card_key, rng):
    voices = [r for r in records or [] if _is_voice(r) or r.get("variant")]
    prev = None
    stamped = [r for r in records or [] if r.get("username")]
    if stamped:
        prev = shape_of(max(stamped, key=lambda r: r.get("created") or "") if any(r.get("created") for r in stamped)
                        else stamped[-1])
    lost = [r for r in records or [] if r.get("persona") == card_key and not _is_active(r)]
    gone = shape_of(lost[-1]) if lost else None
    counts = {s: 0 for s in SHAPES}
    for r in voices:
        if _is_active(r):
            s = shape_of(r)
            counts[s] = counts.get(s, 0) + 1
    ok = [s for s in SHAPES if s != prev and s != gone] or [s for s in SHAPES if s != prev]
    low = min(counts[s] for s in ok)
    return rng.choice(sorted(s for s in ok if counts[s] == low))


def shape_of(rec):
    """The handle shape of an account record: the variant's own, else a guess from its username (legacy accounts are
    mostly firstname_job and first_last)."""
    v = rec.get("variant")
    if v and v.get("shape") in SHAPES:
        return v["shape"]
    stem = _stem(rec.get("username"))
    parts = [p for p in re.split(r"[_.]", stem) if p]
    if len(parts) <= 1:
        return "bare_name"
    if len(parts[0]) <= 2:
        return "initials_word"
    if len(parts[-1]) == 1:
        return "lastname_initial"
    if len(parts) >= 3:
        return "first_last"
    words = " ".join(_JOBS_ANY + _HOBBIES + [w for _, ws in _JOBS for w in ws.split()])
    place = " ".join(w for ws in _PLACES.values() for w in ws.split())
    if parts[0] in place.split() or parts[1] in place.split():
        return "place_word"
    if parts[1] in _HOBBIES:
        return "hobby_word"
    return "firstname_job" if parts[1] in words.split() else "first_last"


def _job_words(card):
    text = f"{card['role']} {card.get('voice', '')} ".lower()
    out = []
    for pat, words in _JOBS:
        if re.search(pat, text):
            out += words.split()
    return out or _JOBS_ANY


def _place_words(card):
    return _PLACES.get(card["place"], "").split() or _PLACES_ANY


def _handle(shape, ctx, first, last, rng):
    f, la = first.lower(), last.lower()
    jobs, places = ctx.jobs, ctx.places
    yy = f"{(2026 - ctx.age) % 100:02d}"
    if shape == "firstname_job":
        h = f"{f}_{rng.choice(jobs)}"
    elif shape == "nickname":
        base = f[:rng.choice((3, 4))]
        h = base + rng.choice(_NICK_END)
        if h == f:
            h += "o"
    elif shape == "initials_word":
        h = f"{f[0]}{la[0]}_{rng.choice(_HOBBIES + jobs)}"
    elif shape == "place_word":
        h = f"{rng.choice(places)}_{rng.choice(_ROLE_NOUN[ctx.gender])}"
    elif shape == "hobby_word":
        h = rng.choice((f"{rng.choice(_HOBBIES)}_{rng.choice(_ROLE_NOUN[ctx.gender])}",
                        f"{f}_{rng.choice(_HOBBIES)}", f"{rng.choice(_HOBBIES)}{rng.choice(_NOUN)}"))
    elif shape == "bare_name":
        h = f if len(f) >= 3 else f + "xx"
    elif shape == "word_digits":
        h = f"{rng.choice(places + _NOUN + _HOBBIES)}{yy}"
    elif shape == "first_last":
        h = rng.choice((f"{f}_{la}", f"{la}_{f}"))
    elif shape == "lastname_initial":
        h = f"{la}_{f[0]}"
    else:                                                      # adj_noun
        h = f"{rng.choice(_ADJ)}{rng.choice(_NOUN)}"
    h = re.sub(r"[^a-z0-9_]", "", h.lower()).strip("_")
    return re.sub(r"_+", "_", h)[:27].rstrip("_")


def username_for(handle, rng=None, taken=()):
    """The username to register: the handle plus two digits (what Accounts.maybe_register does), or the handle as it is
    when it already ends in digits (shape word_digits). Capped at 32 characters, never one in `taken` (lower-cased
    usernames seen anywhere, suspended included); a clash adds digits. Deterministic given the rng."""
    rng = _rng(rng)
    taken = {t.lower() for t in taken}
    base = re.sub(r"[^a-z0-9_]", "", handle.lower())[:30]
    plain = base if base[-1:].isdigit() else None
    if plain and plain not in taken:
        return plain
    for _ in range(60):
        u = f"{base}{rng.randint(10, 99)}"[:32]
        if u not in taken:
            return u
    while True:                                                # 90 two-digit tails all taken: lengthen, never loop long
        u = f"{base[:28]}{rng.randint(1000, 9999)}"
        if u not in taken:
            return u


def _perturb(base, rng):
    """One hand drawn near `base`: each probability inside a band around its value, the device within its family."""
    base = {**_DEFAULT_HAND, **base}
    out = dict(base)
    for k in PROB_KEYS:
        p = base[k]
        w = max(0.05, 0.45 * p)
        lo, hi = max(0.1 if k == "careful" else 0.0, p - w), min(_CAP[k], p + w)
        out[k] = round(rng.uniform(lo, max(lo, hi)), 2)
    if rng.random() < 0.2:
        out["device"] = rng.choice(_FAMILY.get(base["device"], (base["device"],)))
    if rng.random() < 0.08:
        out["two_space"] = not base["two_space"]
    return out


def _pick_hand(base, others, rng, tries=16):
    """Of `tries` perturbations of `base`, the one farthest from every hand in `others` (so many voices of one card
    spread out instead of landing on each other)."""
    best, best_d = None, -1.0
    for _ in range(tries):
        h = _perturb(base, rng)
        d = min([hand_distance(h, o) for o in others] or [9.9])
        if d > best_d:
            best, best_d = h, d
    return best


def _pick_age(card, rng):
    base = card["age"]
    band = 3 if base <= 25 else AGE_BAND
    lo, hi = max(16, base - band), min(90, base + band)
    if base <= 25:
        lo = max(lo, 18)
    if re.search(r"\bretired\b", card["role"] + " " + (card.get("voice") or ""), re.I) and base >= 60:
        lo = max(lo, 58)
    choices = [a for a in range(lo, hi + 1) if a != base]
    return rng.choice(choices) if choices else base


def _pick_use(card, rng):
    """{field: [index]}: a subset of each list in a shuffled order, at least two things different from the card."""
    floor = dict(details=2, people=2, lines=3, now=4)
    n = {f: len(card.get(f) or []) for f in floor}
    room = {f: max(0, n[f] - min(floor[f], n[f])) for f in floor}
    drop = {f: rng.randint(0, room[f]) for f in floor}
    fields = sorted(floor)
    while sum(drop.values()) < 2 and any(drop[f] < room[f] for f in fields):
        f = rng.choice([f for f in fields if drop[f] < room[f]])
        drop[f] += 1
    use = {}
    for f in floor:
        idx = list(range(n[f]))
        keep = sorted(rng.sample(idx, n[f] - drop[f])) if n[f] else []
        order = keep[:]
        rng.shuffle(order)
        if order == keep and drop[f] == 0 and len(order) > 1:       # nothing dropped: at least reorder
            order = order[1:] + order[:1]
        use[f] = order
    return use


def use_diff(use, card):
    """Differences from the card: items left out, plus one per field kept whole but in another order."""
    d = 0
    for f, idx in use.items():
        n = len(card.get(f) or [])
        d += (n - len(idx)) + (1 if len(idx) == n and idx != sorted(idx) else 0)
    return d


def _pick_names(card, ctx, rng):
    """(first, last, display name, swap) for a candidate, from the pools minus everything blocked."""
    blocked = ctx.blocked
    used = set()

    def take(pool):
        free = sorted(w for w in pool if w.lower() not in blocked and w.lower() not in used)
        if not free:
            free = sorted(w for w in pool if w.lower() not in blocked)
        w = rng.choice(free or sorted(pool))
        used.add(w.lower())
        return w

    pool = _pool_for(ctx.gender)
    for _ in range(50):
        first, last = take(pool), take(LAST)
        if (first.lower(), last.lower()) not in DENY_FULL:
            break
    fmt = rng.random()
    name = f"{first} {last}" if fmt < 0.72 else f"{first} {last[0]}." if fmt < 0.9 else first
    swap = {}
    own_first = card["name"].split()[0]
    swap[card["name"]] = f"{first} {last}"
    swap[own_first] = first
    for entry in card.get("people") or []:
        p = parse_person(entry)
        nf = take(_pool_for(p["gender"])) if p["first"] else None
        nl = take(LAST) if p["last"] else None
        if p["first"] and p["last"]:
            swap[f"{p['first']} {p['last']}"] = f"{nf} {nl}"
            swap.setdefault(p["first"], nf)
            if " " not in p["last"]:
                swap.setdefault(p["last"], nl)
        elif p["first"]:
            swap.setdefault(p["first"], nf)
        elif p["last"]:
            swap.setdefault(p["last"], nl)
    return first, last, name, swap


def _pick_style(card, cards, records, rng):
    """Another card of the same register, not the base and not one an active voice drives, or None (20% of the time)."""
    if rng.random() >= 0.2:
        return None
    busy = {r.get("persona") for r in records or [] if _is_active(r)} | {
        (r.get("variant") or {}).get("style_of") for r in records or [] if _is_active(r)}
    free = sorted(k for k, c in cards.items() if k != card["key"] and k not in busy
                  and c.get("register") == card.get("register") and c.get("voice") != card.get("voice"))
    return rng.choice(free) if free else None


# ---- the check
class _Ctx:
    """Everything make_variant and distinct need about the pool, computed once."""

    def __init__(self, card_key, records, cards):
        self.cards = cards
        if card_key not in cards:
            raise ValueError(f"no such card: {card_key!r}")
        self.card = cards[card_key]
        self.records = list(records or [])
        self.gender = _gender(self.card)
        self.jobs, self.places = _job_words(self.card), _place_words(self.card)
        self.age = self.card["age"]
        self.blocked = _blocked_tokens(cards, self.records)
        self.seen = {(r.get("username") or "").lower() for r in self.records}
        self.stems = {_stem(r.get("username")) for r in self.records if r.get("username")} \
            | {_stem(c.get("handle")) for c in cards.values()}
        self.names = {(r.get("display_name") or "").lower() for r in self.records} \
            | {c["name"].lower() for c in cards.values()}
        live = [(r.get("display_name") or "").lower() for r in self.records if _is_active(r)] \
            + [c["name"].lower() for c in cards.values()]
        self.firsts = {n.split()[0] for n in live if n}
        self.voices = [r for r in self.records if _is_active(r) and _is_voice(r)]
        self.voice_info = [(r, _voice_names(r, cards), _voice_hand(r, cards)) for r in self.voices]


def _check(v, ctx):
    why = []
    card = ctx.card
    if v.get("shape") not in SHAPES:
        why.append("shape_unknown")
    h = v["handle"]
    if not HANDLE_RE.match(h) or "__" in h or h.endswith("_"):
        why.append(f"handle_invalid:{h}")
    stem = _stem(h)
    for other in sorted(ctx.stems):
        if not other:
            continue
        if near(stem, other) or (len(min(stem, other, key=len)) >= 4 and (stem.startswith(other) or other.startswith(stem))):
            why.append(f"handle_near:{other}")
            break
    if h.lower() in ctx.seen:
        why.append(f"username_seen:{h}")
    name = v["name"].lower()
    if any(o and near(name, o) for o in ctx.names):
        why.append("name_near")
    if v["first"].lower() in {f.lower() for f in ctx.firsts}:
        why.append("first_name_taken")
    if v["first"].lower() in DENY_TOKENS or v["last"].lower() in DENY_TOKENS or (v["first"].lower(), v["last"].lower()) in DENY_FULL:
        why.append("real_or_setting_name")
    mine = _tokens(v["name"]) | {t for x in v["swap"].values() for t in _tokens(x)}
    people_new = [x for k, x in v["swap"].items()]
    if len(set(people_new)) != len(people_new):
        why.append("people_repeat")
    for r, names, _ in ctx.voice_info:
        if mine & names:
            why.append(f"people_shared:{r.get('username')}")
            break
    base_hand = card.get("hand") or _DEFAULT_HAND
    if hand_distance(v["hand"], base_hand) < EPS_HAND:
        why.append("hand_close_to_base")
    for r, _, hand in ctx.voice_info:
        if hand_distance(v["hand"], hand) < EPS_HAND:
            why.append(f"hand_close:{r.get('username')}")
            break
    if v["age"] == card["age"] or not 16 <= v["age"] <= 90:
        why.append("age")
    if use_diff(v["use"], card) < 2:
        why.append("use_same")
    return not why, why


def distinct(variant, records, cards=None):
    """(ok, reasons): is `variant` a different person from every account in `records` and from its base card? Checks
    edit distance on handle and name against all records (suspended too), no people names shared with another active
    voice, hand beyond EPS_HAND of every other voice and the base card, age not the card's, two or more differences
    in `use`. `cards`: a mapping or a callable returning one (default: default_cards())."""
    records = [r for r in records or [] if r.get("variant") != variant]       # an account's own record is not "another"
    ctx = _Ctx(variant["base"], records, _as_map(cards))
    return _check(variant, ctx)


def make_variant(card_key, records, rng=None, cards=None):
    """A new variant of card `card_key` that is distinct from `records` (every account record, any status). Tries up
    to MAX_TRIES candidates and returns the first that passes distinct(), else the one with the fewest failed checks
    (its reasons in v["checks"], logged as a warning). Pure and deterministic given `rng` (a random.Random or a seed).
    `cards`: mapping or callable like distinct(); default_cards() otherwise."""
    rng = _rng(rng)
    ctx = _Ctx(card_key, records, _as_map(cards))
    card = ctx.card
    best, best_why = None, None
    for _ in range(MAX_TRIES):
        shape = _pick_shape(ctx.records, card_key, rng)
        first, last, name, swap = _pick_names(card, ctx, rng)
        style = _pick_style(card, ctx.cards, ctx.records, rng)
        base_hand = (ctx.cards[style].get("hand") if style else None) or card.get("hand") or _DEFAULT_HAND
        others = [card.get("hand") or _DEFAULT_HAND] + [h for _, _, h in ctx.voice_info]
        v = dict(v=VERSION, base=card_key, name=name, first=first, last=last,
                 handle=None, shape=shape, age=_pick_age(card, rng), hand=_pick_hand(base_hand, others, rng),
                 use=_pick_use(card, rng), swap=swap, style_of=style, checks=[])
        # a handle collision is retried inside the candidate: only the handle changes
        for _ in range(8):
            v["handle"] = _handle(shape, ctx, first, last, rng)
            ok, why = _check(v, ctx)
            if ok or not any(w.startswith(("handle_", "username_")) for w in why):
                break
        if ok:
            v["checks"] = []
            return v
        if best is None or len(why) < len(best_why):
            best, best_why = v, why
    best["checks"] = best_why
    log.warning("variant of %s: no clean candidate in %d tries, best fails: %s", card_key, MAX_TRIES, best_why)
    return best


# ---- the overlay bot.persona_of uses
def _swapper(swap):
    keys = sorted(swap, key=len, reverse=True)
    if not keys:
        return lambda t: t
    rx = re.compile(r"(?<![\w'])(" + "|".join(re.escape(k) for k in keys) + r")(?!\w)")
    return lambda t: rx.sub(lambda m: swap[m.group(1)], t) if t else t


def overlay(card, v, cards=None):
    """A copy of `card` as the variant `v` plays it: its name and age, the details, people, lines and events it leans
    on, the people's names swapped everywhere, its hand (a dict: humanize.apply takes it), and (style_of) another card's
    voice line. role, place, frames, register and argument are the card's. Never changes `card`."""
    sw = _swapper(v.get("swap") or {})
    out = dict(card)

    def pick(field):
        items = list(card.get(field) or [])
        idx = [i for i in (v.get("use") or {}).get(field, range(len(items))) if 0 <= i < len(items)]
        return [sw(items[i]) for i in idx] or [sw(x) for x in items]

    out.update(name=v["name"], age=v["age"], hand=dict(v["hand"]),
               details=pick("details"), people=pick("people"), lines=pick("lines"), now=pick("now"),
               problem=sw(card.get("problem")), covid=sw(card.get("covid")), arc=sw(card.get("arc")))
    old = age_words(card["age"]) if card.get("age") else None
    if old and old not in _TENS.values():                                          # the card's own age spelled out (wally: "seventy-four")
        new = age_words(v["age"])
        for f in ("details", "lines"):
            out[f] = [re.sub(rf"\b{old}\b", new, x, flags=re.I) for x in out[f]]
        for f in ("problem", "covid", "arc", "role"):
            if out.get(f):
                out[f] = re.sub(rf"\b{old}\b", new, out[f], flags=re.I)
    if v.get("style_of"):
        style = _as_map(cards).get(v["style_of"]) if cards is not None else card_for(v["style_of"])
        if style:
            out["voice"] = style["voice"]
    return out


def persona(rec, cards=None):
    """The persona dict for an account record with rec["variant"]: the base card (live, else staged) overlaid."""
    if cards is not None:
        cm = _as_map(cards)
        return overlay(cm[rec["persona"]], rec["variant"], cm)
    card = card_for(rec["persona"])
    if card is None:
        raise KeyError(rec["persona"])
    return overlay(card, rec["variant"])
