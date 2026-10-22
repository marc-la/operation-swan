"""Persona cards from real citizens' histories (todo/25): read-only reads, the citizen's own words, no LLM.

A card holds the citizen's name and bio, their recent posts and likes verbatim, the post we test replies against, their
referendum view in their own words (their latest post on the vote), and the segment used for stratifying and for the
movability report: the stance class (the bot's light read, else the regex class), certainty language, concern topics.
Writing cards needs no LLM, so no external model does analysis (CLAUDE.md rule 2).

Citizens are chosen from our own write log (citizens we replied to, with the read's stance), stratified by class.
"""
import collections
import json
import re
import time

import capturethenarrative as ctn

from swan_bot import config
from swan_bot.targeting import REFERENDUM, target_class

# The segments of todo/25 "Targeting in the lab". The light read's stance first; the regex class splits yes_reason out.
CLASSES = ("firm_yes", "yes_but", "yes_reason", "unsure", "lean_no", "firm_no")
FIRM = re.compile(r"\b(definitely|absolutely|certainly|no way|never|for sure|I'?ll vote|I will vote|I'?m voting|"
                  r"my vote is|100%|no question)\b", re.I)
HEDGE = re.compile(r"\b(not sure|unsure|leaning|unless|undecided|maybe|depends|on the fence|torn|might|"
                   r"if they|until they|still deciding|haven'?t decided)\b", re.I)
CONCERNS = {
    "sunset": r"sunset|end date|temporary|permanent|expir|forever|review",
    "venues": r"venue|which places|list of places|\bshops?\b|\bcaf[eé]s?\b|\bmarkets?\b|\bpubs?\b|restaurant|\bgyms?\b|church",
    "id_privacy": r"\bID\b|privacy|data|surveil|track|scan|app\b|QR|database",
    "hospitals": r"hospital|nurse|ICU|ward|clinic|health system|doctor",
    "kids": r"kids?|children|school|teen|son\b|daughter|baby|grandkid",
    "business": r"business|customers|staff|livelihood|tourism|tourist|wage|shift|boss|owner",
    "islands": r"island|ferry|outer|village|remote|wharf",
}
CONCERN_RE = {k: re.compile(v, re.I) for k, v in CONCERNS.items()}


def segment(texts):
    """(certainty, [concerns]) from a citizen's own words: firm / hedged / plain, and the topics they raise."""
    joined = " ".join(texts)
    firm, hedge = len(FIRM.findall(joined)), len(HEDGE.findall(joined))
    certainty = "firm" if firm > hedge else "hedged" if hedge > firm else "plain"
    counts = collections.Counter({k: len(r.findall(joined)) for k, r in CONCERN_RE.items()})
    return certainty, [k for k, n in counts.most_common() if n][:3]


def class_of(read_stance, target_text):
    """The card's stance class: the light read's stance, with yes_reason from the regex (todo/21's class)."""
    if target_class(target_text) == "yes_reason" and read_stance in ("yes_but", "unsure", "unclear", None):
        return "yes_reason"
    if read_stance == "unclear":
        return "unsure"
    return read_stance if read_stance in CLASSES else None


def candidates(actions_log=config.ACTIONS_LOG):
    """{class: [(author_id, target_post, target_text, ts)]} from our live replies to citizens, newest first."""
    out, seen = collections.defaultdict(list), set()
    rows = []
    for line in open(actions_log):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("act") == "reply" and r.get("live") and config.is_citizen(r.get("target_author")):
            rows.append(r)
    for r in reversed(rows):
        a = r["target_author"]
        cls = class_of(r.get("read_stance"), r.get("target_text") or "")
        if a in seen or not cls:
            continue
        seen.add(a)
        out[cls].append((a, r.get("target_post"), r.get("target_text") or "", r["ts"]))
    return out


class Reader:
    """Read-only Legit Social reads at config.LAB_READS_PER_MIN, backing off on a 429."""

    def __init__(self, social=None):
        self.social = social or ctn.LegitSocial()
        self.gap, self.last = 60.0 / config.LAB_READS_PER_MIN, 0.0

    def __call__(self, fn, *a, **kw):
        for _ in range(3):
            time.sleep(max(0.0, self.last + self.gap - time.time()))
            self.last = time.time()
            try:
                return fn(*a, **kw)
            except ctn.RateLimited as e:
                time.sleep(max(e.retry_after or 0, 30))
            except ctn.APIError:                        # private (403) or gone (404): no card
                return None
        return None


def build(author_id, target_post, target_text, cls, read):
    """One card (a dict) for this citizen, or None when their account can't be read."""
    acc = read(read.social.get_account, author_id)
    if not acc:
        return None
    posts = read(read.social.account_posts, author_id, limit=20) or []
    likes = read(read.social.account_likes, author_id, limit=10) or []
    texts = [p.get("body") or "" for p in posts if (p.get("body") or "").strip()]
    on_vote = [t for t in texts if REFERENDUM.search(t)]
    certainty, concerns = segment(on_vote or texts)
    return dict(
        id=f"c{author_id}", author_id=author_id, name=acc.get("display_name") or acc.get("username") or "",
        handle=acc.get("username") or "", bio=(acc.get("bio") or acc.get("description") or "").strip(),
        stance_class=cls, certainty=certainty, concerns=concerns,
        target_post=target_post, target_text=target_text,
        view=on_vote[0] if on_vote else target_text,
        posts=texts[:12], liked=[(p.get("body") or "")[:280] for p in likes if (p.get("body") or "").strip()][:5],
        built=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
