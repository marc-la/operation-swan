"""Who we reply to (todo/21, 2026-10-22): every citizen (not team bots) posting or replying on the referendum, in
Latest, the news threads and Trending threads, plus journalists' referendum posts. Citizens are scarce (~100 items an
hour) and a missed one may not be back for days, so the keyword read (target_class) sets a candidate's priority, not
whether we answer it. No sentiment model: keyword rules only; the drafting call reads the citizen (todo/20).

Hard skips only: not a citizen, a repost, a post we replied to, off the referendum (its thread included), hostile or
shouting, a thread deeper than config.DEEP_THREAD, firm Yes with config.FIRM_YES_ARM off. A citizen already talking
with config.SESSION_VOICES of our voices this session waits until the session is over.
Reads used: account_posts / replies / get_post (300/min each) and the feeds (10/min between them, feeds.py).

Widening the net (todo/23, 2026-10-22): citizen groups beyond the on-topic items we see live, each an arm with a
flag, a cap per hour and a place below every ordinary candidate (config, the todo/23 block). Candidates and funnel
records carry the group ("g"): sweep (every citizen's most recent post on the vote, any age, read by _widen),
older (36-72 h posts still unanswered), off_topic (their topic, no pivot), engaged (citizens who like or follow our
voices) and turnout (lean No, answered as before with the turnout line). Writes we make to a citizen are kept for
7 days (touched) so the sweep doesn't come back to them.
Thread safety (todo/22): the reader thread runs refresh() while the drafter takes candidates and the writer records
answers, so every method that touches the queue, the funnel or the journalist posts holds self.lock (re-entrant).
"""
import datetime as dt
import functools
import json
import re
import threading
import time
import zoneinfo

import capturethenarrative as ctn

from . import config, content, experiment, feeds

REFERENDUM = re.compile(r"referendum|h2d2|dolphin flu|vaccin|jab|mandate|\bvot(e|ing)\b|ballot|certificate|"
                        r"passport|health pass|designated|national id|biometric|sunset|exemption|"
                        r"public (spaces?|places)|proof of|door checks?|papers at|venue list|\bdolphin\b", re.I)

# doubt -> (frame we answer with, the words that name what they asked for). Order matters: first match wins.
DOUBTS = [
    (re.compile(r"sunset|end date|end point|expir|time[- ]?(limited|bound)|temporary|permanent|forever|new normal|"
                r"independent|oversight|review|appeal|safeguard|guarantee|exemption|non-negotiable|"
                r"yes,? but|only if|as long as", re.I), "F14_no_yes_but"),
    (re.compile(r"venue|which (places|spaces)|the list|spaces list|designated|scope|vague|fine print|"
                r"blank (cheque|check)|spell out|define", re.I), "F1_blank_cheque"),
    (re.compile(r"\bid\b|id card|biometric|privacy|private|personal data|health data|surveillance|track|"
                r"health passport|link(ed|ing)? (it|them|these|everything)", re.I), "F8_powers"),
    (re.compile(r"school|\bkids?\b|children|teen|daughter|\bson\b", re.I), "F13_age12"),
    (re.compile(r"outer island|ferry|two[- ]tier|rural|second[- ]class", re.I), "F6_islands"),
    (re.compile(r"hospital|nurse|ward|icu|beds|surge|overwhelm|capacity|frontline", re.I), "F10_staff_and_livelihoods"),
    (re.compile(r"business|shop|cafe|touris|\bjobs?\b|econom|livelihood", re.I), "F7_livelihoods"),
    (re.compile(r"overreach|blanket|every (single )?(shop|place|door)|too far|proportion|targeted|narrow", re.I),
     "F5_not_here_yet"),
    (re.compile(r"not sure|unsure|undecided|on the fence|torn|\bidk\b|leaning|can'?t decide|don'?t know", re.I),
     "F1_blank_cheque"),
]
WANTS = re.compile(r"sunset( clause)?s?|end date|expiry|independent (oversight|review)|oversight|review|appeals?|"
                   r"exemptions?|safeguards?|venue list|spaces list|the list|which places|scope|fine print|"
                   r"privacy|biometric|id card|health data|surveillance|time[- ]limited|temporary|permanent|"
                   r"hospitals?|nurses?|icu|jobs|small business|tourism|schools?|kids|outer islands?|ferry", re.I)
FIRM_NO = re.compile(r"\b(vot(e|ing)|mark(ing)?|tick(ing)?) no\b|\bi'?m a no\b|#voteno|keepkingstoniaopen", re.I)
# Already on our side, softly: replying is echo, not persuasion. ~1 in 5 replies on 20 Oct went to these
# ("Leaning No at the moment", "My No vote is settled", "slippery slope"), because SOFT matches "leaning".
LEAN_NO = re.compile(r"\blean(ing|s)? (towards? )?no\b|\b(my|a) no vote\b|\bno from me\b|\bvot(e|ing) against\b|"
                     r"\bwon'?t (be )?(vot(e|ing)|tick(ing)?) yes\b|slippery slope|won'?t trade|not trading|"
                     r"(a|the) vaccine i don'?t trust|\bis a joke\b", re.I)
# The fear behind a Yes: the reason our replies now answer first (content.REBUTTALS). Ranked up in targeting.
YES_REASON = re.compile(r"hospital|ward|icu|overwhelm|vulnerable|protect|covid|last time|died|deaths|elderly|"
                        r"immunocompromised|nan\b|grandparent", re.I)
FIRM_YES = re.compile(r"\b(vot(e|ing)|mark(ing)?|tick(ing)?) yes\b|#voteyes|protectkingstonia|mandate now|"
                      r"\bi'?m a yes\b", re.I)
SOFT = re.compile(r"\bbut\b|only if|unless|as long as|provided|not sure|unsure|undecided|leaning|torn|guarantee|"
                  r"safeguard|worr|need(s)? (to|clear|real|a)|should|must|\?|if they want|before (i|we)", re.I)
# A citizen who names the conditions they want ("Publish the venue list now, with a clear sunset") is a Yes-but
# without a hedge word. 2026-10-21: 53 of 159 citizen texts on the vote fell out of classify() for want of SOFT;
# ASKS with WANTS brings back 43 of them, while "No sunset clause, no list, no thanks" stays out.
ASKS = re.compile(r"\b(i|we)('d| would)? (want|need|expect)|\bneeds? (to|a|an|the|targeted|real|clear|proper|strong)\b|"
                  r"\b(publish|spell out|define|set|keep|give us|write|put|build|tie|lock)\b|would make me|"
                  r"\bi'?d (back|support|feel|be)|\bif (a |the )?yes\b|\bif (they|we|it|the)\b|\bwith (a |an )?(clear|real|"
                  r"hard|firm|binding|concrete|proper|published|independent|transparent|genuine)\b|\btied to\b|"
                  r"in the (actual )?law\b|\bbefore (voting|we vote|polling)|\bmake (it|them|the)\b|\bget (it|the plan)\b|"
                  r"\b(has|have) to be\b|\bessential\b|\bi.?d push\b|\bi could (back|support|vote)\b", re.I)
HOSTILE = re.compile(r"resort (profits|owners|bookings)|profits|castillo|kitb|tourism board|\bsheep\b|idiots?|"
                     r"conspiracy|tyrann", re.I)
ON_TOPIC = re.compile(r"referendum|h2d2|dolphin flu|vaccin|\bjabs?\b|mandate|ballot|certificate|health pass|"
                      r"\bvot(e|ing|ers?)\b", re.I)    # journalist posts: the vote itself, not a passing word
FRAME_PRIORITY = {"F14_no_yes_but": 3.0, "F1_blank_cheque": 2.5, "F8_powers": 2.0}
# todo/21: the read sets the priority. Highest: the people we can move toward No. Unclear: unknown, often movable.
# Lean No: engagement and lean->firm moves, no backfire. Firm Yes: the arm (backfire risk -80), lowest and capped.
READ_PRIORITY = {"conditions": 3.0, "yes_reason": 3.0, "unsure": 3.0, "unclear": 2.0, "lean_no": 0.0,
                 "firm_yes": -3.0, "off_topic": 0.0}
# who the citizen says they are -> the personas who share it (playbook §7: an in-group messenger beats a better
# argument). First match wins; the reply still argues the frame their doubt picked.
IDENTITIES = [
    ("health", re.compile(r"\bi'?m an? (nurse|doctor|midwife|pharmacist|carer)|\bi work (in|at) (healthcare|health|"
                          r"the hospital|a clinic|aged care)|\bas an? (nurse|doctor|health worker|carer)|my ward|"
                          r"my patients", re.I), ("ana", "sione", "ruth", "priya")),
    ("teacher", re.compile(r"\bi'?m an? teacher|\bi teach\b|\bas an? teacher|my (students|classroom|class)\b", re.I),
     ("grace",)),
    ("parent", re.compile(r"\bas an? (mum|mom|dad|parent|grandparent|nana)|\bmy (kids?|son|daughter|children|boy|girl|"
                          r"grandkids?|grandson|granddaughter|twins)\b|\bi'?m an? (mum|mom|dad|parent)\b", re.I),
     ("paulo", "mere", "grace", "esther", "ngaire", "wally")),
    ("islands", re.compile(r"\bout on the (outer )?islands|\bon the outer islands|\bi live on the islands|"
                           r"\bisland clinic|\bwe island(ers)?\b", re.I), ("sione", "tomasi")),
    ("shop", re.compile(r"\bmy (shop|cafe|café|business|stall|store|restaurant|bakery)\b|\bi run an? |"
                        r"\bas an? (shop|business) owner|\bsmall business owner", re.I), ("esther", "lani")),
    ("student", re.compile(r"\bi'?m an? (uni |university )?student|\bas an? student|\bmy (lectures?|classes) at|"
                           r"\bat ku\b|\bon campus\b", re.I), ("isla",)),
    ("trades", re.compile(r"\bi'?m an? (tradie|electrician|builder|plumber|sparky|chippy)|\bon (the )?site\b|"
                          r"\bmy (crew|tools|van)\b", re.I), ("josh",)),
    ("fishing", re.compile(r"\bi'?m an? fisher|\bmy boat\b|\bi fish\b|\bat the wharf\b|\bdeckhand", re.I),
     ("ben", "tomasi")),
    ("transport", re.compile(r"\bi drive (a|the) (bus|taxi|ferry)|\bbus driver\b|\bmy route\b", re.I), ("dan",)),
    ("sport", re.compile(r"\bi coach\b|\bas an? (coach|volunteer)\b|\bmy (club|squad)\b|"
                         r"\b(netball|rugby|soccer|footy) (club|training|practice|team)\b", re.I), ("ngaire",)),
    ("older", re.compile(r"\bi'?m (retired|a pensioner)\b|\bas an? (pensioner|retiree)\b|\bat my age\b|"
                         r"\bmy (pension|retirement)\b|\bin my (seventies|eighties|70s|80s)\b", re.I), ("wally", "mere")),
    ("tech", re.compile(r"\bi'?m an? (software (developer|engineer)|developer|programmer|coder)\b|\bi work in (tech|it|software)\b|"
                        r"\bas an? (developer|programmer)\b", re.I), ("kai",)),
]
_MESSENGERS = {name: personas for name, _, personas in IDENTITIES}


def identity(text):
    """The first self-description in the citizen's text ('health', 'parent'...), or None."""
    return next((name for name, pattern, _ in IDENTITIES if pattern.search(text or "")), None)


def messengers(ident):
    """Persona keys who share that identity (empty when unknown)."""
    return _MESSENGERS.get(ident, ())


def loud(text):
    letters = [c for c in text if c.isalpha()]
    return len(letters) > 20 and sum(c.isupper() for c in letters) / len(letters) > 0.6


def hedged(text):
    """A hedge word, or the conditions they want named (ASKS): the Yes-but and the unsure we can still move."""
    return bool(SOFT.search(text) or (ASKS.search(text) and WANTS.search(text)))


def classify(text):
    """(frame, wants): the frame for the first doubt the text names, or None when it names none (the drafting call
    picks one, todo/20), and up to 3 of the things they asked for, in their words. Never a skip (todo/21): the hard
    skips are hard_skip(), the rest is priority (target_class)."""
    text = text or ""
    frame = next((f for pattern, f in DOUBTS if pattern.search(text) and content.frame_live(f)), None)
    wants = []                                    # a paused fact takes its frame out (todo/16)
    for m in WANTS.finditer(text):
        if m.group(0).lower() not in wants:
            wants.append(m.group(0).lower())
    return frame, wants[:3]


def hard_skip(text, context=None):
    """Why we never answer this text, or None: "off_topic" (nothing on the vote, its thread included) or "hostile"
    (abuse or shouting)."""
    text = text or ""
    if not REFERENDUM.search(f"{text} {context or ''}"):
        return "off_topic"
    if loud(text) or HOSTILE.search(text):
        return "hostile"
    return None


def stance(text):
    """Where a post stands on the vote, by the keyword rules: "no" (firm or leaning), "yes" (firm, unhedged),
    "unsure" (hedged or undecided, incl. a Yes-but), "unclear" (on the referendum, no stance), None (off topic).
    Used to label targets and the follow-up reads (todo/13). Keeps SOFT, not hedged(), so labels compare across days."""
    text = text or ""
    if not REFERENDUM.search(text):
        return None
    if FIRM_NO.search(text) or LEAN_NO.search(text):
        return "no"
    if FIRM_YES.search(text) and not SOFT.search(text):
        return "yes"
    return "unsure" if SOFT.search(text) else "unclear"


AGREE_OPENING = re.compile(r"^\W*(exactly|that'?s the (problem|thing)|true|fair point|agreed|yeah|right)\b", re.I)


def agrees(text):
    """todo/32: a citizen's answer to us agrees with our side: it leans or stands No (stance), or opens with an
    agreeing word and makes no Yes statement. The keyword rules only: a reply-back whose answer fails this gets the
    light read (bot.build_prompt) to catch what they miss."""
    s = stance(text)
    return s == "no" or (s != "yes" and bool(AGREE_OPENING.search(text or "")))


# 25 Oct audit (#402451): "That is so incredibly kind of you to do, Mavis. Sending so much love to you and the hospital staff!"
# under a post about knitted beanies had no word of the vote, but its thread did and "hospital" is a YES_REASON, so it was
# answered with a pitch ("checking papers at the bakery counter won't fill one bed"). A comment that is only warmth or
# sympathy is off topic, whatever the thread. 12 of 9,272 targets in the log: rare, and each is a visible tell.
KINDNESS = re.compile(r"sending (so much )?(love|hugs)|\bso (incredibly |really |very )?(kind|lovely|moving|sweet|touching|"
                      r"beautiful|thoughtful)\b|kind of you|sorry (for|about) your|congrat|well done|so proud|\bhugs?\b|"
                      r"\u2764|\U0001f970|\U0001f60d|\U0001f495|\U0001f54a", re.I)
ARGUES = re.compile(r"\bbut\b|should|\bneed|\bmust|worr|\?|\bif\b|\bpass\b|\brules?\b|\bpolic|\bcheck|\bsystem\b|\bargue", re.I)


def kindness_only(text):
    """True for a comment that says nothing of the vote and argues nothing: warmth or sympathy only."""
    text = text or ""
    return bool(KINDNESS.search(text) and not REFERENDUM.search(text) and not ARGUES.search(text))


def target_class(text, context=None):
    """The experiment's target class (H3), and since todo/21 the candidate's priority (READ_PRIORITY): yes_reason
    (they voice the fear behind a Yes), conditions (the conditions they want), unsure / unclear, lean_no, firm_yes,
    off_topic. Two fixes (todo/21): a text on the vote only through its thread (context) is "unclear", not off topic;
    a doubt named with no hedge or ask ("No sunset clause, no list, no thanks") is a No-leaning complaint."""
    text = text or ""
    s = stance(text)
    if s is None and REFERENDUM.search(context or "") and not kindness_only(text):
        s = "unclear"
    if s in ("no", "yes", None):
        return {"no": "lean_no", "yes": "firm_yes", None: "off_topic"}[s]
    c = "yes_reason" if YES_REASON.search(text) else ("conditions" if WANTS.search(text) else s)
    if c in ("conditions", "unclear") and not hedged(text) and any(p.search(text) for p, _ in DOUBTS):
        return "lean_no"
    return c


def soft_yes(text):
    return bool(FIRM_YES.search(text or "") and hedged(text or ""))


def age_h(post):
    created = dt.datetime.fromisoformat(post["created_at"].replace("Z", "+00:00"))
    return (dt.datetime.now(dt.timezone.utc) - created).total_seconds() / 3600


def sessions(contacted, t=None):
    """{author: {persona, ...}}: our voices who wrote to each citizen in the last CONTACT_COOLDOWN_S (one session),
    from state["contacted"] = {author: [[ts, persona], ...]} (a bare timestamp is the format before todo/21)."""
    t = t or time.time()
    out = {}
    for author, entries in contacted.items():
        voices = {e[1] for e in (entries if isinstance(entries, list) else [[entries, None]])
                  if t - e[0] < config.CONTACT_COOLDOWN_S}
        if voices:
            out[author] = voices
    return out


def contact(contacted, author, persona, t=None):
    """Record one of our writes to a citizen in state["contacted"]; entries older than a session are dropped."""
    t = t or time.time()
    for a in list(contacted):
        entries = [e for e in (contacted[a] if isinstance(contacted[a], list) else [[contacted[a], None]])
                   if t - e[0] < config.CONTACT_COOLDOWN_S]
        if entries:
            contacted[a] = entries
        else:
            del contacted[a]
    contacted.setdefault(str(author), []).append([t, persona])


VOICE_WAITS = ("voice_asleep", "voice_capped", "voice_owner")      # todo/31: a voice keeping a human day
DELIBERATE_WAITS = ("session_cap", "firm_yes_cap", "reply_back") + VOICE_WAITS   # pending on purpose (oldest_pending)


def locked(method):
    """Run a Targeter method holding its lock (todo/22: refresh() runs on the reader thread)."""
    @functools.wraps(method)
    def run(self, *args, **kw):
        with self.lock:
            return method(self, *args, **kw)
    return run


def hour_of(ts=None):
    return dt.datetime.fromtimestamp(ts or time.time(), dt.timezone.utc).strftime("%Y-%m-%dT%H")


ARMS_ON = {"sweep": "SWEEP_ARM", "older": "OLDER_ARM", "off_topic": "OFF_TOPIC_ARM", "engaged": "ENGAGED_ARM",
           "turnout": "TURNOUT_ARM", "late": "LATE_REPLY"}


def arm_on(net):
    return bool(getattr(config, ARMS_ON[net]))


def group_cap(net, t=None):
    """Hand-outs an hour for a todo/23 group (None: no cap). The sweep gets more at Sydney night."""
    if net == "sweep":
        night = dt.datetime.fromtimestamp(t or time.time(), zoneinfo.ZoneInfo(config.LOCAL_TZ)).hour in config.NIGHT_HOURS
        return config.SWEEP_NIGHT_PER_H if night else config.SWEEP_PER_H
    return {"older": config.OLDER_PER_H, "off_topic": config.OFF_TOPIC_PER_H, "engaged": config.ENGAGED_PER_H,
            "late": config.LATE_PER_H}.get(net)


def citizen_ids():
    """Every citizen id, in order: the seeded ones, then config.EXTRA_CITIZEN_RANGES."""
    ids = list(range(config.OFFICIAL_MAX_ID + 1, config.CITIZEN_MAX_ID + 1))
    for lo, hi in config.EXTRA_CITIZEN_RANGES:
        ids += [i for i in range(lo, hi + 1) if i > config.CITIZEN_MAX_ID]
    return ids


class Targeter:
    """Collects candidate targets every few minutes and hands out the best one.

    The funnel (todo/21 G12): every citizen item we read (a citizen's post or reply, not a repost, under
    TARGET_MAX_AGE_H old) gets one record in self.items, from first sight to an end: "answered", "skipped" (a reason
    we chose not to answer) or "lost" (a reason we failed to). Until then it is "pending", with what it waits for.
    Skips, waits and losses go to the action log one line each; every refresh record carries the per-hour counts."""

    def __init__(self, social, log=print, snapshot=None):
        self.social, self.log = social, log
        self.snapshot = snapshot     # path: write what we read for swan-blue (the live bot only), feeds.py
        self.accounts = {}           # account_id -> account dict ({} if unreadable)
        self.candidates = {}         # post_id -> candidate dict
        self.journalist = {}         # post_id -> journalist post
        self.headline = None         # latest referendum headline (for timely persona posts)
        self.feed_posts = []         # last Latest + Trending read (the amplifier's filler-like pool)
        self.trending_ids = []       # last Trending order (the amplifier records our posts' best rank)
        self.trending_posts = []     # last Trending read, with rank_position and global_hot_score (pulse.py)
        self.trending_at = None      # ...and when it was read
        self.headlines = []          # the papers' article titles of the last 24 h, newest first (pulse.py)
        self.next_refresh = 0.0
        self.news_next = 0.0         # when the news threads are read next (NEWS_THREADS_S, todo/24)
        self.refreshes = 0
        self.latest_seen = 0         # newest Latest post id read so far: each refresh pages back to it
        self.bands = []              # [[cursor, stop_id]]: Latest stretches not read yet, newest first (G2)
        self.recent_latest = []      # Latest posts of the last feeds.SNAPSHOT_KEEP_S (the snapshot)
        self.items = {}              # post_id -> funnel record: h (hour first seen), c (created), f (found), o, why, src
        self.unjudged = {}           # post_id -> [post, source, context]: a read hit the rate limit; next refresh
        self.posts = {}              # post_id -> post (parents and thread depth), {} if gone
        self.firm_yes_out = []       # when firm-Yes candidates were handed out (FIRM_YES_PER_H)
        # todo/23
        self.group_out = {}          # group -> when its candidates were handed out (the caps per hour)
        self.touched = {}            # citizen id -> our last write to them (kept SWEEP_RECONTACT_S)
        self.dead_ids = set()        # account ids of voices whose notifications we cannot read (suspended, parked): bot.py sets it (todo/46)
        self.swept = {}              # citizen id -> when the sweep last read them (or a time ahead: private)
        self.sweep_next = 0          # index into citizen_ids(): where the sweep carries on
        self.engaged_pool = {}       # citizen id -> persona: liked or follows that voice, not read yet
        self.engaged_next = 0        # which voice's likers and followers are read next
        self.visits = {}             # group -> {what a citizen visit came to: n} since start (the groups line)
        self.reads = 0               # account_posts / get_post / likers / followers reads made by this targeter
        self._rl = None              # the rate limit as our last widen read saw it
        self._ours, self._ours_mtime = [], None
        self.lock = threading.RLock()  # todo/22: the reader refreshes while the drafter and the writer use the queue

    # ---- saved across restarts (G3) ----------------------------------------------------------
    @locked
    def dump(self):
        """What a restart needs: the read position, the queue and the funnel (bot.save_state)."""
        cut = time.time() - 12 * 3600
        t = time.time()
        return dict(latest_seen=self.latest_seen, bands=self.bands, candidates=list(self.candidates.values()),
                    items={str(k): v for k, v in list(self.items.items()) if self._deadline(v) >= cut},
                    unjudged=list(self.unjudged.values()),
                    group_out=self.group_out, sweep_next=self.sweep_next, engaged_pool=dict(self.engaged_pool),
                    engaged_next=self.engaged_next,
                    touched={a: x for a, x in list(self.touched.items()) if t - x < config.SWEEP_RECONTACT_S},
                    swept={a: x for a, x in list(self.swept.items()) if x > t - 2 * config.SWEEP_REVISIT_S})

    @locked
    def load(self, saved):
        saved = saved or {}
        self.latest_seen = saved.get("latest_seen", 0)
        self.bands = [list(b) for b in saved.get("bands", [])]
        self.candidates = {c["post"]["post_id"]: c for c in saved.get("candidates", [])}
        self.items = {int(k): v for k, v in saved.get("items", {}).items()}
        for it in self.items.values():
            it.setdefault("f", time.time())       # saved before found times were kept: count from this start
        self.unjudged = {u[0]["post_id"]: list(u) for u in saved.get("unjudged", [])}
        self.group_out = saved.get("group_out", {})
        self.sweep_next = saved.get("sweep_next", 0)
        self.engaged_pool = saved.get("engaged_pool", {})
        self.engaged_next = saved.get("engaged_next", 0)
        self.swept = saved.get("swept", {})
        if "touched" in saved:
            self.touched = saved["touched"]
        else:                                         # first start with todo/23: who we wrote to, from the log
            self.seed_touched()

    def seed_touched(self, path=None):
        """touched from the action log: the citizens our live replies, reply-backs and second voices went to in the
        last SWEEP_RECONTACT_S (read once, when the state has none)."""
        cut = time.time() - config.SWEEP_RECONTACT_S
        try:
            f = open(path or config.ACTIONS_LOG)
        except OSError:
            return
        with f:
            for line in f:
                if '"target_author"' not in line or '"live": true' not in line:
                    continue
                try:
                    rec = json.loads(line)
                    ts = dt.datetime.fromisoformat(rec["ts"]).timestamp()
                except (ValueError, KeyError):
                    continue
                a = rec.get("target_author")
                if rec.get("act") in ("reply", "reply_back", "second_voice") and ts >= cut and config.is_citizen(a):
                    self.touched[str(a)] = max(ts, self.touched.get(str(a), 0))

    # ---- who is a citizen -------------------------------------------------------------------
    def account(self, account_id):
        if account_id not in self.accounts:
            try:
                self.accounts[account_id] = self.social.get_account(account_id)
            except ctn.RateLimited:
                return {}                             # don't cache: try again next refresh
            except ctn.APIError:
                self.accounts[account_id] = {}
        return self.accounts[account_id]

    def is_citizen(self, account_id):
        """The id rule (config.is_citizen), no read: a get_account that hit the rate limit used to make a citizen
        look like a bot, and the item was never read again (G4)."""
        return config.is_citizen(account_id)

    # ---- the funnel (G12) -------------------------------------------------------------------
    def _item(self, post, source):
        """The funnel record of a citizen item, made on first sight. g: its todo/23 group, once it has one; exp: a
        deadline other than the post's age (swept items, off-topic ones)."""
        pid = post["post_id"]
        if pid not in self.items:
            created = dt.datetime.fromisoformat(post["created_at"].replace("Z", "+00:00")).timestamp()
            self.items[pid] = dict(h=hour_of(), c=created, f=time.time(), o="pending", why="new", src=source,
                                   reply=bool(post.get("reply_to_post_id")))
        return self.items[pid]

    @staticmethod
    def _deadline(it):
        """When a pending item is lost: its own deadline, else the post's age reaching the limit (B: 72 h)."""
        return it.get("exp") or it["c"] + 3600 * (config.OLDER_MAX_AGE_H if config.OLDER_ARM else config.TARGET_MAX_AGE_H)

    @locked
    def _end(self, post, outcome, why, source=None):
        it = self._item(post, source)
        if it["o"] == "answered" or (it["o"], it["why"]) == (outcome, why):
            return
        it["o"], it["why"] = outcome, why
        self.log({"act": {"skipped": "skip", "lost": "lost", "pending": "wait"}[outcome], "why": why,
                  "post_id": post["post_id"], "author_id": post.get("author_id"), "source": it["src"],
                  "reply": it["reply"], "age_min": round((time.time() - it["c"]) / 60, 1), "group": it.get("g")})

    def skip(self, post, why, source=None):
        """We chose not to answer this citizen item (final)."""
        self._end(post, "skipped", why, source)

    def lose(self, post, why, source=None):
        """We meant to answer it and couldn't (final)."""
        self._end(post, "lost", why, source)

    def wait(self, post, why, source=None):
        """Still pending, for this reason (logged once per reason)."""
        self._end(post, "pending", why, source)

    @locked
    def mention_pool(self):
        """[{author_id, post_id, cls, age_min}]: the citizens waiting in the queue, for mention.pick (todo/46). A copy, no
        candidate is changed."""
        return [dict(author_id=c["post"]["author_id"], post_id=pid, cls=c.get("target_class"), age_min=age_h(c["post"]) * 60)
                for pid, c in self.candidates.items() if config.is_citizen(c["post"].get("author_id"))]

    @locked
    def answered(self, post, mode):
        """bot.py, after a write to a citizen's item: a reply or reply-back ends it as answered."""
        if mode in ("reply", "reply_back") and self.is_citizen(post.get("author_id")):
            it = self._item(post, "reply_back" if mode == "reply_back" else None)
            it["o"], it["why"], it["a"] = "answered", mode, time.time()
        if self.is_citizen(post.get("author_id")):    # the sweep leaves them alone for a week (todo/23)
            self.touched[str(post["author_id"])] = time.time()

    @locked
    def oldest_pending(self):
        """For status.json (todo/22): (written, queued) = seconds since the oldest citizen item still pending was
        written, and since the oldest one not waiting on purpose (DELIBERATE_WAITS) and not in a todo/23 group (old
        by design: sweep, engaged, off_topic, older) entered our queue. None if none."""
        t, pending = time.time(), [(pid, it) for pid, it in self.items.items() if it["o"] == "pending"]
        grouped = {pid for pid, c in self.candidates.items() if self._net(c, t)}
        queued = [it.get("f", t) for pid, it in pending
                  if it["why"] not in DELIBERATE_WAITS and not it.get("g") and pid not in grouped]
        pending = [it for _, it in pending]
        return (round(t - min(it["c"] for it in pending)) if pending else None,
                round(t - min(queued)) if queued else None)

    @locked
    def funnel(self, hours=3, group=False):
        """{hour: {seen, answered, skipped: {why: n}, lost: {why: n}, pending: {why: n}}} for the items first seen
        in each of the last `hours` hours. seen = answered + skipped + lost + pending, exactly. group: only the items
        of that todo/23 group (False: all)."""
        out = {}
        keep = {hour_of(time.time() - 3600 * i) for i in range(hours)}
        for it in list(self.items.values()):
            if it["h"] not in keep or (group is not False and it.get("g") != group):
                continue
            f = out.setdefault(it["h"], dict(seen=0, answered=0, skipped={}, lost={}, pending={}))
            f["seen"] += 1
            if it["o"] == "answered":
                f["answered"] += 1
            else:
                f[it["o"]][it["why"]] = f[it["o"]].get(it["why"], 0) + 1
        return dict(sorted(out.items()))

    @locked
    def _expire(self):
        """Items still pending past their deadline (TARGET_MAX_AGE_H, OLDER_MAX_AGE_H with the older arm, or their
        own) are lost, with what they were waiting for; 12 h later the record goes."""
        t = time.time()
        for pid, it in list(self.items.items()):
            if it["o"] == "pending" and self._deadline(it) < t:
                c = self.candidates.pop(pid, None)
                self.unjudged.pop(pid, None)
                self.lose(c["post"] if c else dict(post_id=pid), f"expired:{it['why']}")
            elif self._deadline(it) < t - 12 * 3600:
                del self.items[pid]
        self.candidates = {k: c for k, c in self.candidates.items()
                           if k in self.items and self._deadline(self.items[k]) >= t}

    # ---- collection -------------------------------------------------------------------------
    def post(self, post_id):
        """A post by id (cached), {} when it's gone, None when the rate limit stopped the read (judge it later)."""
        if post_id not in self.posts:
            try:
                self.reads += 1
                self.posts[post_id] = self.social.get_post(post_id)
            except ctn.RateLimited:
                return None
            except ctn.APIError:
                self.posts[post_id] = {}
            if len(self.posts) > 5000:
                for k in list(self.posts)[:1000]:
                    del self.posts[k]
        return self.posts[post_id]

    def depth(self, post):
        """Replies above this one in its thread (0 for a post), read up the chain, capped at DEEP_THREAD; None when
        the rate limit stopped a read."""
        d, p = 0, post
        while p.get("reply_to_post_id") and d < config.DEEP_THREAD:
            d += 1
            if p.get("root_post_id") == p["reply_to_post_id"]:
                break                                 # a reply to the thread's first post: no read needed
            p = self.post(p["reply_to_post_id"])
            if p is None:
                return None
        return d

    @locked
    def _consider(self, post, source, context=None, parent=None):
        """Judge a post once: not a citizen item (not counted), a hard skip (logged), or a candidate whose read sets
        its priority. A citizen reply gets its parent post as context when the thread gave none (todo/21 item 5)."""
        pid = post["post_id"]
        if pid in self.candidates or post.get("kind") == "repost" or not self.is_citizen(post.get("author_id")):
            return                                    # team bots, ~98% of Latest: not in the funnel
        max_h = config.OLDER_MAX_AGE_H if config.OLDER_ARM else config.TARGET_MAX_AGE_H     # todo/23 B
        if age_h(post) > max_h or (pid in self.items and self.items[pid]["o"] != "pending"):
            return
        it = self._item(post, source)
        if it["why"] not in ("new", "unjudged"):
            return                                    # judged before and waiting (handed out, routed...)
        body = post.get("body") or ""
        if parent and parent.get("post_id") == post.get("reply_to_post_id"):
            self.posts[parent["post_id"]] = parent
        elif post.get("reply_to_post_id"):
            parent = self.post(post["reply_to_post_id"])
        d = self.depth(post)
        if (post.get("reply_to_post_id") and parent is None) or d is None:   # the rate limit: next refresh (G4)
            self.unjudged[pid] = [post, source, context]
            return self.wait(post, "unjudged", source)
        self.unjudged.pop(pid, None)
        if context is None and parent:
            context = (parent.get("body") or "")[:200] or None
        cls = target_class(body, context)
        why = (hard_skip(body, context) or ("deep_thread" if d >= config.DEEP_THREAD else None)
               or ("firm_yes" if cls == "firm_yes" and not config.FIRM_YES_ARM else None))
        group = None
        # todo/46: a citizen answering a post of a voice we can no longer read (suspended: its notifications are gone, and 7 in 10
        # replies arrive hours after the post) is a conversation we owe a reply, whatever the topic: answered by a live voice, first
        late = bool(config.LATE_REPLY and parent and parent.get("author_id") in self.dead_ids)
        if late and why == "off_topic" and not (loud(body) or HOSTILE.search(body)):
            why, group = None, "off_topic"                          # a thank-you or an aside: on their topic, no pivot to the vote
        elif why == "off_topic" and self._off_topic_ok(post, d):      # todo/23 C: their topic, no pivot
            why, group = None, "off_topic"
            it["exp"] = it["c"] + 3600 * config.TARGET_MAX_AGE_H
        if why:
            return self.skip(post, why, source)
        self._queue(post, source, context, parent, d, cls, group=group, net="late" if late else None)

    def _off_topic_ok(self, post, d):
        """An off-topic citizen post we may answer on its own topic (todo/23 C): the arm on, not hostile or shouting,
        not deep, not old, and no voice of ours wrote to them in OFF_TOPIC_RECONTACT_S."""
        body = post.get("body") or ""
        return (config.OFF_TOPIC_ARM and not (loud(body) or HOSTILE.search(body)) and d < config.DEEP_THREAD
                and age_h(post) <= config.TARGET_MAX_AGE_H
                and time.time() - self.touched.get(str(post["author_id"]), 0) >= config.OFF_TOPIC_RECONTACT_S)

    @locked
    def _queue(self, post, source, context, parent, d, cls, group=None, net=None, prefer=None):
        """Make a judged citizen item a candidate, its read setting the score. group: the todo/23 group the reply
        gets (content.group_style), net: the arm it counts against (default: the group), prefer: the persona to
        answer it from (D: the voice they engaged with)."""
        body = post.get("body") or ""
        frame, wants = classify(body)
        score = (READ_PRIORITY.get(cls, 0.0) + FRAME_PRIORITY.get(frame, 1.5 if frame else 1.0)
                 + (2.0 if soft_yes(body) else 0.0) + (1.5 if YES_REASON.search(body) else 0.0)
                 + 2.0 * max(0.0, 1 - age_h(post) / config.TARGET_MAX_AGE_H) + (1.0 if source == "news" else 0.0)
                 + (config.TRENDING_THREAD_BONUS if source == "thread" else 0.0))
        self.candidates[post["post_id"]] = dict(post=post, frame=frame, wants=wants, context=context, source=source,
                                                score=score, identity=identity(body), target_class=cls, depth=d,
                                                parent_author=(parent or {}).get("author_id"),
                                                **({"group": group, "net": net or group} if group else {"net": net} if net else {}),
                                                **({"prefer": prefer} if prefer else {}))
        it = self._item(post, source)
        it["why"] = "queued"
        if group:
            it["g"] = net or group

    def refresh(self, force=False):
        """Read everything new; True when it ran (bot.py saves the state then)."""
        if not force and time.time() < self.next_refresh:
            return False
        self.next_refresh = time.time() + config.REFRESH_S
        self.refreshes += 1
        before = len(self.candidates)
        fresh_citizen, newest, heads, papers_read = 0, None, [], False
        # 1) news threads: citizens reply under the papers' article posts. The papers' posts (headlines, for the pulse
        # and persona posts) every refresh; the replies under them every NEWS_THREADS_S (todo/24)
        threads_due = time.time() >= self.news_next
        if threads_due:
            self.news_next = time.time() + config.NEWS_THREADS_S
        for aid in config.NEWS_IDS:
            try:
                articles = [p for p in self.social.account_posts(aid, limit=12)
                            if not p.get("reply_to_post_id") and p.get("kind") != "repost"]
            except ctn.APIError:
                continue
            papers_read = True
            for art in articles:
                title = (art.get("body") or "").split("\n")[0]
                if title and age_h(art) <= 24:
                    heads.append(dict(title=title, ts=art["created_at"], paper=aid, post_id=art["post_id"]))
                if not REFERENDUM.search(art.get("body") or "") or age_h(art) > 72:
                    continue
                newest = newest or title              # account_posts is newest first
                if not threads_due:
                    continue
                try:
                    for r in self.social.replies(art["post_id"], limit=100):
                        self._consider(r, "news", context=title, parent=art)
                        if age_h(r) < 1 and self.is_citizen(r["author_id"]):
                            fresh_citizen += 1
                except ctn.APIError:
                    pass
        self.headline = newest or self.headline
        if papers_read:
            self.headlines = sorted(heads, key=lambda h: h["ts"], reverse=True)
        # 2) journalists' own referendum replies and posts (for the journalist storyline)
        for aid in config.JOURNALIST_IDS:
            try:
                posts = list(self.social.account_posts(aid, limit=8))
                with self.lock:
                    for p in posts:
                        if age_h(p) < config.JOURNALIST_MAX_AGE_H and ON_TOPIC.search(p.get("body") or ""):
                            self.journalist.setdefault(p["post_id"], p)
            except ctn.APIError:
                pass
        # 3) feeds: citizen posts in Latest/Trending, and citizen replies under top referendum posts in Trending.
        # Latest every refresh; Trending every TRENDING_EVERY-th (the 10/min feed budget, G1)
        for post, source, context in list(self.unjudged.values()):     # a rate limit stopped them last time
            self._consider(post, source, context)
        latest = self._latest()
        for p in latest["posts"]:
            self._consider(p, "latest")
        trending = []
        if (self.refreshes - 1) % config.TRENDING_EVERY == 0 or not self.trending_posts:
            try:
                trending = list(feeds.read(self.social, "feed_trending", "swan-bot", limit=50))
            except ctn.APIError:
                pass
        for p in trending:
            self._consider(p, "trending")
        if trending:
            self.trending_ids = [p["post_id"] for p in trending]
            self.trending_posts, self.trending_at = trending, feeds.now_iso()
        top = [p for p in trending if REFERENDUM.search(p.get("body") or "")][:config.TRENDING_THREADS]
        for p in top:
            try:
                for r in self.social.replies(p["post_id"], limit=50):
                    self._consider(r, "thread", context=(p.get("body") or "")[:200], parent=p)
            except ctn.APIError:
                pass
        feed_posts = latest["posts"] + trending
        self.feed_posts = feed_posts or self.feed_posts
        self._snapshot(latest["posts"])
        reads = self.reads
        self._widen()                                 # todo/23: the sweep and engaged quiet citizens
        widen_reads = self.reads - reads
        self._expire()
        cit = [p for p in latest["posts"] if config.is_citizen(p["author_id"]) and p.get("kind") != "repost"]
        self.log({"act": "refresh", "candidates": len(self.candidates), "new": len(self.candidates) - before,
                  "journalist_posts": len(self.journalist), "citizen_news_replies_last_hour": fresh_citizen if threads_due else None,
                  "news_threads_read": threads_due,
                  # citizen hours (todo/19): what citizens wrote in Latest since the last refresh, and whether we
                  # read all of it (gap: stretches left for the next refresh, G2)
                  "latest_read": len(latest["posts"]), "latest_pages": latest["pages"], "latest_gap": latest["gap"],
                  "latest_bands": len(self.bands), "latest_error": latest["error"],
                  "feed_remaining": latest["remaining"], "trending_read": bool(trending),
                  "citizen_latest_posts": sum(not p.get("reply_to_post_id") for p in cit),
                  "citizen_latest_replies": sum(bool(p.get("reply_to_post_id")) for p in cit),
                  "citizen_latest_authors": len({p["author_id"] for p in cit}),
                  "funnel": self.funnel(), "groups": self.groups(), "widen_reads": widen_reads})
        return True

    def _latest(self):
        """New Latest posts down to the newest one read before, then the stretches earlier refreshes stopped short
        of (bands, newest first), in 100-post pages while LATEST_PAGES and the feed budget last. A stretch we stop
        in is kept as [cursor, stop id] for the next refresh (G2) and saved with the state (G3), so no page is
        skipped. New posts go first: their authors may still be online. A band that reaches posts older than
        TARGET_MAX_AGE_H is done (nothing in it could be answered)."""
        posts, pages, error, left, top = [], 0, None, [], None
        for cursor, stop in [[None, self.latest_seen]] + self.bands:
            while True:
                rl = self.social.rate_limit
                if pages and (pages >= config.LATEST_PAGES or (rl and rl.remaining <= config.FEED_READS_SPARE)):
                    if cursor is not None:            # an unread top needs no band: the next refresh starts there
                        left.append([cursor, stop])
                    break
                try:
                    page = feeds.read(self.social, "feed_latest", "swan-bot", limit=100, cursor=cursor)
                except ctn.APIError as e:
                    error = e.status
                    if cursor is not None:
                        left.append([cursor, stop])
                    break
                pages += 1
                if cursor is None and page:
                    top = max(p["post_id"] for p in page)
                new = [p for p in page if p["post_id"] > stop]
                posts += new
                if (len(new) < len(page) or not page.next_cursor or not stop or not new or new[-1]["post_id"] <= stop + 1
                        or age_h(new[-1]) > config.TARGET_MAX_AGE_H):
                    break                             # reached the stop (the very first refresh reads one page)
                cursor = page.next_cursor
        if top:
            self.latest_seen = max(self.latest_seen, top)
        if len(left) > config.LATEST_MAX_BANDS:       # never expected with one reader; logged, not silent
            for cursor, stop in left[config.LATEST_MAX_BANDS:]:
                self.log({"act": "lost", "why": "latest_band_dropped", "stop_id": stop})
            left = left[:config.LATEST_MAX_BANDS]
        self.bands = left
        rl = self.social.rate_limit
        return dict(posts=posts, pages=pages, gap=bool(left), error=error, remaining=rl.remaining if rl else None)

    def _snapshot(self, new_posts):
        """The Latest posts of the last few minutes and the last Trending read, for swan-blue (feeds.py)."""
        if not self.snapshot:
            return
        cut = time.time() - feeds.SNAPSHOT_KEEP_S
        merged = {p["post_id"]: p for p in self.recent_latest + new_posts if feeds.created_ts(p) >= cut}
        self.recent_latest = sorted(merged.values(), key=lambda p: -p["post_id"])
        try:
            feeds.write_snapshot(self.recent_latest, self.trending_posts, self.trending_at, path=self.snapshot)
        except OSError as e:
            self.log({"act": "snapshot_error", "error": str(e)})

    # ---- todo/23: widening the net ------------------------------------------------------------
    def ours(self):
        """Our accounts (id, persona, role, status) from secrets/swan_accounts.json, re-read when it changes. Only
        those fields are kept: no passwords or tokens leave the file."""
        try:
            mtime = config.ACCOUNTS_FILE.stat().st_mtime
        except OSError:
            return self._ours
        if mtime != self._ours_mtime:
            try:
                recs = json.loads(config.ACCOUNTS_FILE.read_text())
            except (OSError, ValueError):
                return self._ours
            self._ours = [dict(account_id=r["account_id"], persona=r.get("persona"), role=r.get("role", "voice"),
                               status=r.get("status", "active")) for r in recs if r.get("account_id")]
            self._ours_mtime = mtime
        return self._ours

    def _read(self, fn, *args, **kw):
        """One widen read (account_posts, likers, followers), counted, its rate limit kept for _spare()."""
        self.reads += 1
        out = list(fn(*args, **kw))
        self._rl = self.social.rate_limit
        return out

    def _spare(self, start):
        """Room for another widen read this refresh: under SWEEP_READS_PER_REFRESH, and the bucket our last read
        hit not down to SWEEP_READS_SPARE (other readers share it: swan-blue, followup)."""
        rl = self._rl
        return self.reads - start < config.SWEEP_READS_PER_REFRESH and not (rl and rl.remaining <= config.SWEEP_READS_SPARE)

    @locked
    def queued(self, net):
        return sum(c.get("net") == net for c in list(self.candidates.values()))

    def _widen(self):
        """todo/23's collectors, inside SWEEP_READS_PER_REFRESH reads a refresh (<= 20/min; never a feed read):
        D first (one voice's citizen likers and followers, then those citizens), then A (the sweep, from where it
        stopped). Each reads citizens only while its queue is short of SWEEP_QUEUE. A rate limit ends it for this
        refresh. Runs on the reader thread (todo/22): engaged_pool, swept and sweep_next are the reader's own (dump
        copies them); _visit takes the lock where it touches the queue and the funnel, not around its reads."""
        start, self._rl = self.reads, None
        t = time.time()
        try:
            if config.ENGAGED_ARM:
                if self.queued("engaged") < config.SWEEP_QUEUE and not self.engaged_pool:
                    self._engaged_step()
                for aid, persona in list(self.engaged_pool.items()):
                    if not self._spare(start) or self.queued("engaged") >= config.SWEEP_QUEUE:
                        break
                    if t - self.swept.get(aid, 0) >= config.SWEEP_REVISIT_S:
                        self._visit(int(aid), "engaged", config.ENGAGED_RECONTACT_S, prefer=persona)
                    del self.engaged_pool[aid]
            if config.SWEEP_ARM:
                ids = citizen_ids()
                for _ in range(len(ids)):
                    if not self._spare(start) or self.queued("sweep") >= config.SWEEP_QUEUE:
                        break
                    aid = ids[self.sweep_next % len(ids)]
                    if t - self.swept.get(str(aid), 0) >= config.SWEEP_REVISIT_S:
                        self._visit(aid, "sweep", config.SWEEP_RECONTACT_S)
                    self.sweep_next = (self.sweep_next + 1) % len(ids)
        except ctn.RateLimited:
            self.log({"act": "widen_rate_limited", "reads": self.reads - start})

    def _engaged_step(self):
        """D: the next voice's posts of the last ENGAGED_POSTS_H, their citizen likers, and the voice's citizen
        followers, into engaged_pool (citizen -> that voice's persona). ~5-8 reads."""
        voices = [r for r in self.ours() if r["role"] != "booster" and r["status"] == "active"]
        if not voices:
            return
        v = voices[self.engaged_next % len(voices)]
        self.engaged_next += 1
        found = set()
        self._saw("engaged", "voices_read")
        try:
            posts = [p for p in self._read(self.social.account_posts, v["account_id"], limit=20)
                     if p.get("kind") != "repost" and age_h(p) <= config.ENGAGED_POSTS_H]
            for p in posts[:5]:
                found |= {x.get("account_id") for x in self._read(self.social.likers, p["post_id"], limit=50)}
            found |= {x.get("account_id") for x in self._read(self.social.followers, v["account_id"], limit=100)}
        except ctn.RateLimited:
            raise
        except ctn.APIError:
            pass
        for aid in found:
            if config.is_citizen(aid):
                self._saw("engaged", "citizens_found")
                self.engaged_pool.setdefault(str(aid), v["persona"])

    def _saw(self, net, what):
        """Count what a widen step came to, for the groups line (why a group queues nothing, on the box)."""
        seen = self.visits.setdefault(net, {})
        seen[what] = seen.get(what, 0) + 1

    def _visit(self, aid, net, recontact_s, prefer=None):
        """Read one citizen's last posts and queue their most recent post on the vote, any age (A, D), or for D with
        the off-topic arm on, their most recent post. Not read: a citizen we wrote to within recontact_s or with a
        candidate waiting. Not queued (skipped, in the funnel): hostile or shouting, a deep thread, a reply to one of
        us (the reply-back path's), a firm Yes (todo/21's arm has those). A private account is left for a week."""
        t, key = time.time(), str(aid)
        with self.lock:
            if t - self.touched.get(key, 0) < recontact_s or any(
                    c["post"].get("author_id") == aid for c in list(self.candidates.values())):
                self.swept[key] = t
                return self._saw(net, "recent")
        try:
            posts = self._read(self.social.account_posts, aid, limit=20)
        except ctn.RateLimited:
            raise
        except ctn.APIError as e:
            self.swept[key] = t + (6 * 86400 if e.status == 403 else 0)
            return self._saw(net, "private" if e.status == 403 else "unreadable")
        self.swept[key] = t
        with self.lock:                               # the queue and the funnel (todo/22)
            self._judge_visit(aid, key, t, net, posts, prefer)

    def _judge_visit(self, aid, key, t, net, posts, prefer):
        """_visit's second half, holding the lock: pick the citizen's post and skip or queue it."""
        own = [p for p in posts if p.get("author_id") == aid and p.get("kind") != "repost"]
        # on the vote: a post must say so plainly (ON_TOPIC: "watched the sunset from the porch" isn't); a reply may
        # lean on its thread (REFERENDUM)
        on = [p for p in own if ON_TOPIC.search(p.get("body") or "")
              or (p.get("reply_to_post_id") and REFERENDUM.search(p.get("body") or ""))]
        pick = on[0] if on else (own[0] if own and net == "engaged" and config.OFF_TOPIC_ARM else None)
        if not pick or pick["post_id"] in self.items or pick["post_id"] in self.candidates:
            return self._saw(net, "judged" if pick else "nothing")   # judged already: answered, skipped...
        body = pick.get("body") or ""
        parent = self.post(pick["reply_to_post_id"]) if pick.get("reply_to_post_id") else None
        d = self.depth(pick)
        if (pick.get("reply_to_post_id") and parent is None) or d is None:
            del self.swept[key]                       # not judged: read this citizen again next refresh
            raise ctn.RateLimited("GET", "/posts", 429, "widen", 30)
        context = ((parent or {}).get("body") or "")[:200] or None
        cls = target_class(body, context)
        it = self._item(pick, net)
        it["g"], it["exp"] = net, t + config.GROUP_QUEUE_S
        ours = {r["account_id"] for r in self.ours()}
        why = ("hostile" if loud(body) or HOSTILE.search(body) else None) \
            or ("deep_thread" if d >= config.DEEP_THREAD else None) \
            or ("reply_to_us" if parent and parent.get("author_id") in ours else None) \
            or ("firm_yes" if cls == "firm_yes" else None)
        self._saw(net, why or "queued")
        if why:
            return self.skip(pick, why, net)
        self._queue(pick, net, context, parent, d, cls, group=net if on else "off_topic", net=net, prefer=prefer)

    @locked
    def groups(self):
        """The refresh record's line per todo/23 group: on, cap, queued, handed out and answered in the last hour,
        and its funnel (items first seen in the last 3 h). Plus where the sweep is."""
        t = time.time()
        out = {}
        for net in ARMS_ON:
            done = [it for it in list(self.items.values()) if it.get("g") == net]
            f = self.funnel(group=net)
            out[net] = dict(on=arm_on(net), cap=group_cap(net, t), queued=self.queued(net),
                            out_1h=sum(t - x < 3600 for x in self.group_out.get(net, [])),
                            answered_1h=sum(it["o"] == "answered" and t - it.get("a", 0) < 3600 for it in done),
                            **({"visits": dict(self.visits[net])} if self.visits.get(net) else {}),
                            **({"funnel": f} if f else {}))
        out["sweep"].update(at=self.sweep_next, of=len(citizen_ids()),
                            read_24h=sum(t - x < 86400 for x in list(self.swept.values())))
        out["engaged"].update(pool=len(self.engaged_pool))
        return out

    def _net(self, c, t=None):
        """The todo/23 group a candidate counts against: its own (sweep, engaged, off_topic), "older" once its post
        is past TARGET_MAX_AGE_H, else None (an ordinary candidate)."""
        if c.get("net"):
            return c["net"]
        return "older" if age_h(c["post"]) > config.TARGET_MAX_AGE_H else None

    # ---- hand out targets -------------------------------------------------------------------
    @locked
    def requeue(self, cand, why):
        """Put a handed-out candidate back, pending for `why` (G8): "no_voice" is tried again at the next slot, and so
        is "held" (a draft that waited when the bot stopped, todo/22) and "no_model" (no model could answer; the
        drafter's own pause spaces the next try, 23 Oct); anything else (a failed draft) after a backoff of 2, 4, 8... up to 30 min, until it ages out (then it is lost as expired:<why>).
        A "no_voice" or "held" hand-out doesn't count against its group's cap. todo/31's VOICE_WAITS are no_voice
        with the reason (the voice is asleep, capped, or the citizen's voice of the day is busy): no try counted, and
        the caller's not_before (until that voice is free) is kept."""
        free = why in ("no_voice", "held", "no_model") + VOICE_WAITS      # no_model: our side's fault, no try counted
        if free and cand.get("out_at") in self.group_out.get(cand.get("net"), []):
            self.group_out[cand["net"]].remove(cand["out_at"])
        if not free:
            cand["tries"] = cand.get("tries", 0) + 1
            cand["not_before"] = time.time() + min(120 * 2 ** (cand["tries"] - 1), 1800)
        self.candidates[cand["post"]["post_id"]] = cand
        self.wait(cand["post"], why, cand.get("source"))

    @locked
    def next_target(self, our_ids, replied_posts, contacted, engaged=()):
        """The best candidate we may answer now, or None (todo/21). contacted: {author: our voices who wrote to them
        this session} (sessions()); engaged: authors who answered us before (ENGAGED_BONUS: they answer again).
        Posts under FRESH_MIN old go first: their author may still be online. A citizen talking with SESSION_VOICES
        of our voices waits (queued) until the session is over; a citizen reply to one of our posts goes to the
        reply-back path; firm Yes goes out as the arm, at most FIRM_YES_PER_H an hour. The candidate handed out
        carries target_class, priority, arm and engaged for the job.
        todo/23: a candidate in a group (sweep, older, off_topic, engaged; _net) goes only when no ordinary one can,
        in GROUP_ORDER, at most group_cap() an hour; a group switched off ends its candidates as skipped. An ordinary
        lean-No candidate goes out as "turnout" under TURNOUT_ARM. The candidate carries group (for the reply's
        style, content.group_style) and prefer (the persona to answer from) when it has them."""
        t = time.time()
        self.firm_yes_out = [x for x in self.firm_yes_out if t - x < 3600]
        self.group_out = {n: [x for x in xs if t - x < 3600] for n, xs in self.group_out.items()}

        def priority(c):
            return (c["score"] + (config.FRESH_BONUS if age_h(c["post"]) * 60 < config.FRESH_MIN else 0.0)
                    + (config.ENGAGED_BONUS if str(c["post"]["author_id"]) in engaged else 0.0))

        def tier(c):
            net = self._net(c)
            if net == "late":
                return -1                                 # todo/46: a citizen who answered a lost voice goes before everything
            return config.GROUP_ORDER.index(net) + 1 if net in config.GROUP_ORDER else 0

        # todo/25's target_order arm: in its blocks the lab's movability order goes first (config.TARGET_ORDER), the
        # score only within a class; base blocks keep the todo/21 weights
        order = experiment.block("arm_conv")[1] == "target_order"

        unsure_first = config.UNSURE_FIRST and not order      # Marc, 24 Oct: split the queue in two, the unsure first; the order inside each half is unchanged

        def rank(c):
            cls = c.get("target_class")
            if unsure_first:
                return 0 if cls in config.UNSURE_FIRST_CLASSES else 1
            return config.TARGET_ORDER.index(cls) if order and cls in config.TARGET_ORDER else len(config.TARGET_ORDER)

        # todo/33's engagers_first arm: in its blocks the citizens most likely to engage go first (see engage_rank)
        eng = experiment.block("arm_eng")[1] == "engagers_first"

        def engage_rank(c):
            if not eng:
                return 0
            if str(c["post"]["author_id"]) in engaged:
                return 0                              # answered us before: they answer again
            if c.get("target_class") in config.ENG_UNSURE:
                return 1
            return 2 if age_h(c["post"]) * 60 < config.FRESH_MIN else 3     # a reply within minutes of their post

        gap = getattr(config, "RECONTACT_GAP_S", None)

        def gap_rank(c):                              # todo/46: a citizen we wrote to 1-6 h ago answers least; they go last, not never
            if not gap:
                return 0
            return 1 if gap[0] <= t - self.touched.get(str(c["post"]["author_id"]), 0) < gap[1] else 0

        for pid, c in sorted(self.candidates.items(),
                             key=lambda kv: (tier(kv[1]), gap_rank(kv[1]), engage_rank(kv[1]), rank(kv[1]), -priority(kv[1]))):
            if c.get("not_before", 0) > t:
                continue                              # requeued: backing off
            post, author, source = c["post"], c["post"]["author_id"], c.get("source")
            if pid in replied_posts or author in our_ids:
                self.candidates.pop(pid)
                self.skip(post, "replied" if pid in replied_posts else "ours", source)
                continue
            if config.REPLY_BACK and c.get("parent_author") in our_ids and c.get("parent_author") not in self.dead_ids:
                self.candidates.pop(pid)
                self.wait(post, "reply_back", source)    # they answered one of us: the reply-back path has it
                continue
            if len(contacted.get(str(author), ())) >= config.SESSION_VOICES:
                self.wait(post, "session_cap", source)   # stays queued: answered once their session is over
                continue
            net = self._net(c)
            if net and not arm_on(net):
                self.candidates.pop(pid)
                self.skip(post, f"{net}_off", source)
                continue
            recontact = {"sweep": config.SWEEP_RECONTACT_S, "engaged": config.ENGAGED_RECONTACT_S,
                         "off_topic": config.OFF_TOPIC_RECONTACT_S}.get(net)
            if recontact and t - self.touched.get(str(author), 0) < recontact:
                self.candidates.pop(pid)
                self.skip(post, "contacted_recently", source)    # we reached them some other way meanwhile
                continue
            cap = group_cap(net, t) if net else None
            if cap is not None and len(self.group_out.get(net, [])) >= cap:
                self.wait(post, f"{net}_cap", source)
                continue
            if c.get("target_class") == "firm_yes":
                if len(self.firm_yes_out) >= config.FIRM_YES_PER_H:
                    self.wait(post, "firm_yes_cap", source)
                    continue
                self.firm_yes_out.append(t)
                c["arm"] = "firm_yes"
            if not net and c.get("target_class") == "lean_no" and config.TURNOUT_ARM:
                net = "turnout"
            if net:
                c["group"], c["net"], c["out_at"] = c.get("group") or net, net, t
                self.group_out.setdefault(net, []).append(t)
                self._item(post, source)["g"] = net
            c["priority"], c["engaged"] = round(priority(c), 2), str(author) in engaged
            self.candidates.pop(pid)
            self.wait(post, "drafting", source)
            return c
        return None

    @locked
    def next_journalist(self, replied_posts, journalist_last):
        if not config.JOURNALIST_ARM:                 # todo/23 F: the switch
            return None
        for pid, p in sorted(self.journalist.items(), key=lambda kv: age_h(kv[1])):
            aid = p["author_id"]
            if pid in replied_posts or age_h(p) > config.JOURNALIST_MAX_AGE_H:
                continue
            if time.time() - journalist_last.get(str(aid), 0) < config.JOURNALIST_SAME_GAP_S:
                continue
            return p
        return None
