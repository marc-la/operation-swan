"""Who we reply to: citizens (not team bots) who voice a doubt (soft Yes or unsure), found mostly in the news
threads where citizens gather, plus journalists' referendum replies. No sentiment model: keyword rules only.

Firm Yes (backfire risk), firm No (no persuasion points), loud/hostile posts and anyone we contacted recently are skipped.
Reads used: account_posts / replies / get_account (300/min each) and 2 feed reads per refresh (feeds: 10/min).
"""
import datetime as dt
import re
import time

import capturethenarrative as ctn

from . import config, content

REFERENDUM = re.compile(r"referendum|h2d2|dolphin flu|vaccin|jab|mandate|\bvot(e|ing)\b|ballot|certificate|"
                        r"passport|health pass|designated|national id|biometric|sunset|exemption", re.I)

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
HOSTILE = re.compile(r"resort (profits|owners|bookings)|profits|castillo|kitb|tourism board|\bsheep\b|idiots?|"
                     r"conspiracy|tyrann", re.I)
ON_TOPIC = re.compile(r"referendum|h2d2|dolphin flu|vaccin|\bjabs?\b|mandate|ballot|certificate|health pass|"
                      r"\bvot(e|ing|ers?)\b", re.I)    # journalist posts: the vote itself, not a passing word
FRAME_PRIORITY = {"F14_no_yes_but": 3.0, "F1_blank_cheque": 2.5, "F8_powers": 2.0}
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


def classify(text):
    """(frame, wants) to answer with, or (None, None) to skip this text."""
    if not text or FIRM_NO.search(text) or LEAN_NO.search(text) or loud(text) or HOSTILE.search(text):
        return None, None
    if FIRM_YES.search(text) and not SOFT.search(text):
        return None, None
    for pattern, frame in DOUBTS:
        if pattern.search(text) and content.frame_live(frame):     # a paused fact takes its frame out (todo/16)
            if not SOFT.search(text):
                return None, None
            wants = []
            for m in WANTS.finditer(text):
                if m.group(0).lower() not in wants:
                    wants.append(m.group(0).lower())
            return frame, wants[:3]
    return None, None


def stance(text):
    """Where a post stands on the vote, by the keyword rules: "no" (firm or leaning), "yes" (firm, unhedged),
    "unsure" (hedged or undecided, incl. a Yes-but), "unclear" (on the referendum, no stance), None (off topic).
    Used to label targets and the follow-up reads (todo/13)."""
    text = text or ""
    if not REFERENDUM.search(text):
        return None
    if FIRM_NO.search(text) or LEAN_NO.search(text):
        return "no"
    if FIRM_YES.search(text) and not SOFT.search(text):
        return "yes"
    return "unsure" if SOFT.search(text) else "unclear"


def target_class(text):
    """The experiment's target class (H3): yes_reason (they voice the fear behind a Yes), conditions (only the
    conditions they want), unsure / unclear, or lean_no / firm_yes / off_topic (which targeting should skip)."""
    s = stance(text)
    if s in ("no", "yes", None):
        return {"no": "lean_no", "yes": "firm_yes", None: "off_topic"}[s]
    return "yes_reason" if YES_REASON.search(text) else ("conditions" if WANTS.search(text) else s)


def soft_yes(text):
    return bool(FIRM_YES.search(text or "") and SOFT.search(text or ""))


def age_h(post):
    created = dt.datetime.fromisoformat(post["created_at"].replace("Z", "+00:00"))
    return (dt.datetime.now(dt.timezone.utc) - created).total_seconds() / 3600


class Targeter:
    """Collects candidate targets every few minutes and hands out the best one."""

    def __init__(self, social, log=print):
        self.social, self.log = social, log
        self.accounts = {}           # account_id -> account dict ({} if unreadable)
        self.stance = {}             # citizen id -> "ok" | "firm" (from their recent posts)
        self.candidates = {}         # post_id -> candidate dict
        self.journalist = {}         # post_id -> journalist post
        self.headline = None         # latest referendum headline (for timely persona posts)
        self.feed_posts = []         # last Latest + Trending read (the amplifier's filler-like pool)
        self.trending_ids = []       # last Trending order (the amplifier records our posts' best rank)
        self.trending_posts = []     # last Trending read, with rank_position and global_hot_score (pulse.py)
        self.headlines = []          # the papers' article titles of the last 24 h, newest first (pulse.py)
        self.next_refresh = 0.0

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
        """Seeded before launch and not verified. Team accounts were all created after launch."""
        if account_id <= config.OFFICIAL_MAX_ID:
            return False
        a = self.account(account_id)
        if not a or a.get("verified"):
            return False
        created = a.get("created_at")
        return created < config.LAUNCH_UTC if created else account_id <= config.CITIZEN_MAX_ID

    def undecided(self, account_id):
        """Read the citizen's last posts once: skip anyone who has stated a firm vote (unless softened)."""
        if account_id not in self.stance:
            verdict = "ok"
            try:
                for p in self.social.account_posts(account_id, limit=15):
                    body = p.get("body") or ""
                    if (FIRM_NO.search(body) or LEAN_NO.search(body)
                            or (FIRM_YES.search(body) and not SOFT.search(body))):
                        verdict = "firm"
                        break
            except ctn.APIError:
                pass                                  # private: judge by the post alone
            self.stance[account_id] = verdict
        return self.stance[account_id] == "ok"

    # ---- collection -------------------------------------------------------------------------
    def _consider(self, post, source, context=None):
        pid = post["post_id"]
        if pid in self.candidates or post.get("kind") == "repost":
            return
        body = post.get("body") or ""
        if age_h(post) > config.TARGET_MAX_AGE_H or not REFERENDUM.search(body + " " + (context or "")):
            return
        if not self.is_citizen(post["author_id"]):
            return
        frame, wants = classify(body)
        if not frame:
            return
        score = (FRAME_PRIORITY.get(frame, 1.5) + (2.0 if soft_yes(body) else 0.0)
                 + (1.5 if YES_REASON.search(body) else 0.0)
                 + 2.0 * max(0.0, 1 - age_h(post) / config.TARGET_MAX_AGE_H) + (1.0 if source == "news" else 0.0)
                 + (config.TRENDING_THREAD_BONUS if source == "thread" else 0.0))
        self.candidates[pid] = dict(post=post, frame=frame, wants=wants, context=context, source=source, score=score,
                                    identity=identity(body))

    def refresh(self, force=False):
        if not force and time.time() < self.next_refresh:
            return
        self.next_refresh = time.time() + config.REFRESH_S
        before = len(self.candidates)
        fresh_citizen, newest, heads, papers_read = 0, None, [], False
        # 1) news threads: citizens reply under the papers' article posts
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
                try:
                    for r in self.social.replies(art["post_id"], limit=100):
                        self._consider(r, "news", context=title)
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
                for p in self.social.account_posts(aid, limit=8):
                    if age_h(p) < config.JOURNALIST_MAX_AGE_H and ON_TOPIC.search(p.get("body") or ""):
                        self.journalist.setdefault(p["post_id"], p)
            except ctn.APIError:
                pass
        # 3) feeds: citizen posts in Latest/Trending, and citizen replies under top referendum posts in Trending
        feed_posts = []
        for name, feed in (("latest", self.social.feed_latest), ("trending", self.social.feed_trending)):
            try:
                posts = list(feed(limit=50))
            except ctn.APIError:
                continue
            feed_posts += posts
            for p in posts:
                self._consider(p, name)
            if name == "trending":
                self.trending_ids = [p["post_id"] for p in posts]
                self.trending_posts = posts
                top = [p for p in posts if REFERENDUM.search(p.get("body") or "")][:config.TRENDING_THREADS]
                for p in top:
                    try:
                        for r in self.social.replies(p["post_id"], limit=50):
                            self._consider(r, "thread", context=(p.get("body") or "")[:200])
                    except ctn.APIError:
                        pass
        self.feed_posts = feed_posts or self.feed_posts
        # forget stale candidates
        self.candidates = {k: c for k, c in self.candidates.items() if age_h(c["post"]) <= config.TARGET_MAX_AGE_H}
        self.log({"act": "refresh", "candidates": len(self.candidates), "new": len(self.candidates) - before,
                  "journalist_posts": len(self.journalist), "citizen_news_replies_last_hour": fresh_citizen})

    # ---- hand out targets -------------------------------------------------------------------
    def next_target(self, our_ids, replied_posts, contacted):
        """Best candidate whose author is undecided and not contacted recently, or None."""
        for pid, c in sorted(self.candidates.items(), key=lambda kv: -kv[1]["score"]):
            author = c["post"]["author_id"]
            if pid in replied_posts or author in our_ids or str(author) in contacted:
                self.candidates.pop(pid, None)
                continue
            if not self.undecided(author):
                self.candidates.pop(pid, None)
                continue
            return self.candidates.pop(pid)
        return None

    def next_journalist(self, replied_posts, journalist_last):
        for pid, p in sorted(self.journalist.items(), key=lambda kv: age_h(kv[1])):
            aid = p["author_id"]
            if pid in replied_posts or age_h(p) > config.JOURNALIST_MAX_AGE_H:
                continue
            if time.time() - journalist_last.get(str(aid), 0) < config.JOURNALIST_SAME_GAP_S:
                continue
            return p
        return None
