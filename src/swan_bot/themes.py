"""Themes (playbook §3): the five wedge slogans as recurring ideas, worded many ways, the exact line only now and then.

A post or a reply to a citizen may carry one theme (craft.THEMES): the persona must hold its belief; a reply's frame
must fit it (one point only), a post's frame makes it FRAME_FIT times likelier (a post has room for both). Its level is the experiment arm `theme_level` (experiment.py), so the reports can compare them:
  implicit    the idea comes through the persona's own story, none of the slogan's words     posts 50%, replies 60%
  echo        its key words in a line of the persona's own (craft echo forms)                posts 30%, replies 40%
  attributed  someone in the persona's life says it, in their words                         posts 10%
  verbatim    the slogan word for word, mid-post or as the verdict                            posts 10%
The model sees the slogan only on a verbatim draw: shown it, it copies it.

Why not the exact line every time (docs/06-strategy/message-playbook.md §3): one string from many accounts at a
fixed rate and spot is what coordination detectors look for (Pacheco et al. 2021: the same text from several
accounts within a window; Keller et al. 2020 on astroturfing), while real slogans spread as variants (Leskovec et
al. 2009, MemeTracker). So the Ledger keeps, team-wide and from what we actually sent:
  - at most VERBATIM_PER_ACCOUNT slogans per account per day and VERBATIM_PER_DAY across the team;
  - the same slogan from two accounts at least SAME_SLOGAN_GAP_S apart, and never twice in one thread;
  - no theme in more than THEME_PER_HOUR of our writes in an hour;
  - after POSITION_RUN verbatim uses at the end of a post, the next one goes mid-post.
draft_problem() checks a draft against its theme: no slogan it wasn't asked for, the slogan there when it was, no
stock line shared with the theme's recent drafts, a reason of the persona's own. send_problem() rechecks the budget
when a draft goes out (batched drafts wait in a pool). Nothing here hides anything from the organisers: every
write logs its theme, level and slogan with the account and owner (bot.py).
"""
import datetime as dt
import random
import re
import time
from zoneinfo import ZoneInfo

from . import config, experiment, quality
from . import facts as fact_store

try:
    from .playbook import craft as _craft
except ImportError:
    _craft = None

THEMES = getattr(_craft, "THEMES", None) or {}

# share of drafts that carry a theme, rising with the score multiplier (×2 from 26 Oct, ×4 from 1 Nov, Sydney days)
POST_SHARE = (("2026-10-19", 0.40), ("2026-10-26", 0.55), ("2026-11-01", 0.70))
REPLY_SHARE = 0.33
POST_LEVELS = {"implicit": 0.5, "echo": 0.3, "attributed": 0.1, "verbatim": 0.1}
REPLY_LEVELS = {"implicit": 0.6, "echo": 0.4}       # a reply has no room for a quote or a second slogan line
MODES = ("post", "reply")                           # never in our own threads, second voices or journalist replies

VERBATIM_PER_ACCOUNT = 1                            # per rolling 24 h
VERBATIM_PER_DAY = 4                                # team-wide, rolling 24 h
SAME_SLOGAN_GAP_S = 2 * 3600
THEME_PER_HOUR = 2
FRAME_FIT = 3                                       # posts: a theme that fits the frame is this much likelier
POSITION_RUN = 3
KEEP_S = 3 * 86400
ECHO_WINDOW = 20                                    # a theme's latest drafts a new one must not share a line with

# words that don't make two theme lines alike ("so I'm voting No" is in every post)
_COMMON = set("i i'm im a an the and so but it it's is was to of in on at for my our we you your that this that's "
              "why no yes vote voting not just".split())


def post_share(now=None):
    day = dt.datetime.fromtimestamp(time.time() if now is None else now, ZoneInfo(config.LOCAL_TZ)).date().isoformat()
    share = 0.0
    for start, s in POST_SHARE:
        if day >= start:
            share = s
    return share


def live():
    """The themes whose facts are all active and whose belief states no paused fact."""
    return {k: t for k, t in THEMES.items() if k not in getattr(config, "THEMES_OFF", ())
            and fact_store.ok(t.get("requires") or ()) and not fact_store.paused_in(t["belief"])}


def words(text):
    t = (text or "").replace("’", "'").replace("‘", "'").lower()
    return tuple(re.findall(r"[a-z0-9']+", t))


def _find(seq, sub):
    for i in range(len(seq) - len(sub) + 1):
        if seq[i:i + len(sub)] == sub:
            return i
    return -1


def slogans_in(text):
    """The keys of the themes whose slogan the text says word for word (case and punctuation aside)."""
    w = words(text)
    return [k for k, t in THEMES.items() if _find(w, words(t["slogan"])) >= 0]


def position(text, key):
    """'end' if the slogan sits in the last part of the text (the verdict), else 'middle'; None if it isn't there."""
    w, s = words(quality.strip_tag(text or "")), words(THEMES[key]["slogan"])
    i = _find(w, s)
    if i < 0:
        return None
    return "end" if i + len(s) >= 0.7 * len(w) else "middle"


def thread_of(target):
    """The conversation a reply joins: the post the target itself answered (a news thread), else the target."""
    target = target or {}
    return target.get("reply_to_post_id") or target.get("post_id")


def _theme_lines(text, key):
    """4-word runs (with 2+ uncommon words) of the sentences that carry the theme's key words."""
    marks = re.compile(THEMES[key]["marks"], re.I)
    out = set()
    for sent in re.split(r"(?<=[.!?])\s+", quality.strip_tag(text or "")):
        if marks.search(sent):
            w = words(sent)
            out |= {w[i:i + 4] for i in range(len(w) - 3) if sum(x not in _COMMON for x in w[i:i + 4]) >= 2}
    return out


class Ledger:
    """What we sent with a theme or a slogan, newest last; `entries` is the bot's state list (saved with it)."""

    def __init__(self, entries=None):
        self.entries = entries if entries is not None else []

    def _prune(self, now):
        self.entries[:] = [e for e in self.entries if now - e["ts"] < KEEP_S]

    def _slogan_uses(self, now, within=86400):
        return [(e, k) for e in self.entries if now - e["ts"] < within for k in e.get("slogans") or ()]

    def verbatim_problem(self, key, persona_key, thread=None, now=None):
        """Why `persona_key` may not say theme `key`'s slogan now, or None."""
        now = time.time() if now is None else now
        uses = self._slogan_uses(now)
        if sum(e["persona"] == persona_key for e, _ in uses) >= VERBATIM_PER_ACCOUNT:
            return "slogan_account_day"
        if len(uses) >= VERBATIM_PER_DAY:
            return "slogan_team_day"
        if any(k == key and e["persona"] != persona_key and now - e["ts"] < SAME_SLOGAN_GAP_S for e, k in uses):
            return "slogan_gap"
        if thread is not None and any(k == key and e.get("thread") == thread
                                      for e, k in self._slogan_uses(now, KEEP_S)):
            return "slogan_thread"
        return None

    def next_position(self, now=None, rng=random):
        """Where the next verbatim slogan goes: mid-post after a run of endings, else either."""
        now = time.time() if now is None else now
        ends = [p for e in self.entries for p in (e.get("positions") or {}).values()][-POSITION_RUN:]
        if len(ends) == POSITION_RUN and all(p == "end" for p in ends):
            return "middle"
        return rng.choice(["end", "middle"])

    def candidates(self, persona_key, frame_key, now=None, mode="post"):
        now = time.time() if now is None else now
        hour = [e["theme"] for e in self.entries if now - e["ts"] < 3600 and e.get("theme")]
        return {k: t for k, t in live().items()
                if (mode == "post" or t.get("replies", True))
                and (t.get("personas") is None or persona_key in t["personas"])
                and (mode == "post" or t.get("frames") is None or frame_key in t["frames"])
                and hour.count(k) < THEME_PER_HOUR}

    def pick(self, persona_key, frame_key, mode, thread=None, now=None, meta=None, rng=random):
        """The theme for one draft, as the dict the prompts take, or None (no theme this time). Writes theme and
        theme_level into meta (theme_level is the arm drawn, downgraded when a budget or the persona rules it out:
        then theme_level_drawn keeps the draw)."""
        now = time.time() if now is None else now
        if meta is not None:
            meta.update(theme=None, theme_level=None)
        if mode not in MODES or rng.random() >= (post_share(now) if mode == "post" else REPLY_SHARE):
            return None
        cands = self.candidates(persona_key, frame_key, now, mode)
        if not cands:
            return None
        keys = list(cands)
        fit = lambda t: FRAME_FIT if t.get("frames") is None or frame_key in t["frames"] else 1
        key = rng.choices(keys, weights=[cands[k].get("weight", 1) * fit(cands[k]) for k in keys])[0]
        t = cands[key]
        speaker = t.get("verbatim") is None or persona_key in t["verbatim"]
        arms = {}
        drawn = level = experiment.draw("theme_level", POST_LEVELS if mode == "post" else REPLY_LEVELS, arms, rng)
        if level == "verbatim" and (not speaker or self.verbatim_problem(key, persona_key, thread, now)):
            level = "echo"
        theme = dict(key=key, level=level, belief=t["belief"], thread=thread,
                     slogan=t["slogan"] if level == "verbatim" else None,
                     echo=rng.choice(list(t["echo"]) + (list(t.get("echo_speaker") or []) if speaker else []))
                     if level == "echo" else None,
                     position=self.next_position(now, rng) if level == "verbatim" else None)
        if meta is not None:
            meta.update(theme=key, theme_level=level, **({"block_id": arms["block_id"]} if "block_id" in arms else {}))
            if drawn != level:
                meta["theme_level_drawn"] = drawn
        return theme

    def send_problem(self, text, persona_key, thread=None, now=None):
        """Why this draft may not go out now (a slogan over budget since it was drafted), or None."""
        for key in slogans_in(text):
            why = self.verbatim_problem(key, persona_key, thread, now)
            if why:
                return why
        return None

    def record(self, text, persona_key, theme=None, thread=None, mode=None, now=None):
        """Note a write that went out. Only writes with a theme or a slogan are kept."""
        now = time.time() if now is None else now
        found = slogans_in(text)
        if not theme and not found:
            return
        self.entries.append(dict(ts=now, persona=persona_key, mode=mode, thread=thread,
                                 theme=theme and theme["key"], level=theme and theme["level"], slogans=found,
                                 positions={k: position(text, k) for k in found},
                                 text=(text or "")[:500] if theme else None))
        self._prune(now)

    def recent_texts(self, key, n=ECHO_WINDOW):
        return [e["text"] for e in self.entries if e.get("theme") == key and e.get("text")][-n:]


def draft_problem(text, theme, mode, ledger=None):
    """Why a draft that passed quality.check doesn't fit its theme (None: fine). A draft without a theme is only checked
    for a slogan it wasn't asked for."""
    found = slogans_in(text)
    planned = theme and theme["level"] == "verbatim"
    if any(not (planned and k == theme["key"]) for k in found):
        return "unplanned_slogan"
    if not theme:
        return None
    if planned and theme["key"] not in found:
        return "slogan_missing"
    if mode == "reply" and not (quality.LOCAL.search(text) or (quality.LOCAL_NAME and quality.LOCAL_NAME.search(text))):
        return "theme_without_reason"
    if ledger is not None:
        mine = _theme_lines(text, theme["key"])
        if any(mine & _theme_lines(old, theme["key"]) for old in ledger.recent_texts(theme["key"])):
            return "theme_echo_repeat"
    return None


def repair_note(why, theme=None):
    """What to tell the model to fix for a draft_problem reason, or None (a fresh draft)."""
    if why == "unplanned_slogan":
        return "One line reads like a campaign slogan: say that idea in your own words instead; change nothing else."
    if why == "slogan_missing" and theme:
        return f"Add this line word for word, as its own sentence, and change nothing else: {theme['slogan']}"
    if why == "theme_without_reason":
        return "Tie your point to one person, place or detail from your own life; change nothing else."
    if why == "theme_echo_repeat":
        return ("Your line on the main idea sounds like other people's: say it a fresh way, through a detail of your "
                "own; change nothing else.")
    return None
