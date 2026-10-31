"""@mentions in first replies (todo/46, Marc 25 Oct): the arm "mention" of arm_eng.

A notification (replies and mentions only) is the one channel that reaches a citizen who has not heard from us; likes and
follows never do. In a mention block, MENTION_SHARE of ordinary first replies name up to MENTIONS_PER_REPLY OTHER citizens
by @username, so they get a notification from a post in a thread they may not be in. The platform allows 3 handles in a
reply (rules).

31 Oct (Marc; docs/06-strategy/rival-strategies-2026-10-31.md §3.2): who and how, from what the rival replies that get
answered do. The citizens named are the ones online now: posted in Latest within MENTION_FRESH_S (Targeter.fresh_pool),
freshest first, posts on the vote before the rest. The handles OPEN the reply and the reply speaks to them (rivals: 5.9%
answered, 11.9% liked; a handle buried in the third person, as we wrote it until then: 1.4%).

Rules that keep it ordinary: first replies only (config.MENTION_MODES), not off-topic or group replies, never a firm Yes or
an angry post, never one of our accounts, a citizen is named at most once per MENTION_RECONTACT_S, and the model writes the
handles in itself, never appended. Anything that goes wrong means no mention: plan() never raises.

Read-out: the write is logged with `mention` (the first handle used, None when the draft dropped them all), `mentions` (every
handle used), `mention_target` and `mention_targets` (the ids planned); `citizen_repliers` on the post's outcome reads say
whether they answered. The arm is `arm_eng == "mention"`.
"""
import random
import re
import time

from . import config, experiment, targeting

USERNAME = re.compile(r"\w[\w.]{1,39}")             # the platform's handles: letters, digits, _ and .
HOLD_S = 120                                         # a planned citizen isn't offered to another draft for this long
_held = {}                                           # author id -> until when (drafts in flight don't name the same people)
LINES = (
    "Start the reply with {ats} exactly as written, nothing before it, then answer the person above as you would. "
    "Everyone you name is in this conversation now: speak to them directly, never about them in the third person, "
    "and don't write any handle again later.",
    "Open with {ats} and a space, then reply to the person above. Write it so it reads to all of them at once, as one "
    "conversation among neighbours; any question you ask can go to all of them. Each handle once, only at the start.",
    "Put {ats} at the very start, then carry on with your reply to the person above. They are talking about this too, so "
    "talk to them, not about them. No other @ names, and these only once.",
)


def as_list(m):
    """[{author_id, username}] from a plan: None, one dict (before 31 Oct) or a list."""
    if not m:
        return []
    return [m] if isinstance(m, dict) else [x for x in m if x]


def handles(m):
    """The planned usernames, in order."""
    return [x["username"] for x in as_list(m)]


def active(job, t=None):
    """True when this reply may carry a mention: the mention arm's block, an ordinary first reply, and the share."""
    if not config.MENTION_SHARE or job.get("mode") not in config.MENTION_MODES:
        return False
    if job.get("style") == "off_topic" or job.get("group") or job.get("arm") == "firm_yes":
        return False
    return experiment.block("arm_eng", t)[1] == "mention" and random.random() < config.MENTION_SHARE


def pick(pool, author_id, mentioned, now=None, k=1, skip=()):
    """Up to k author ids to name, from pool [{author_id, age_s, body, ...}] (Targeter.fresh_pool): not the citizen we
    are answering or in `skip`, posted within MENTION_FRESH_S, not named in the last MENTION_RECONTACT_S, not a firm Yes
    or an angry post. Posts on the vote first, then the freshest."""
    now = time.time() if now is None else now
    ok, seen = [], set()
    for p in pool:
        a, body = p["author_id"], p.get("body") or ""
        if a == author_id or a in skip or a in seen or p["age_s"] > config.MENTION_FRESH_S:
            continue
        if now - float((mentioned or {}).get(str(a), 0)) < config.MENTION_RECONTACT_S:
            continue
        if targeting.loud(body) or targeting.HOSTILE.search(body) or targeting.target_class(body) == "firm_yes":
            continue
        seen.add(a)
        ok.append((not targeting.on_vote(body), p["age_s"], a))
    return [a for _, _, a in sorted(ok)[:max(0, k)]]


def plan(job, targeter, mentioned, now=None):
    """[{author_id, username}] to name in this reply, or None. Reads usernames through Targeter.account (cached; a
    public read, outside any lock)."""
    try:
        if not active(job):
            return None
        target = job.get("target") or {}
        t = time.time() if now is None else now
        for a in [a for a, until in _held.items() if until <= t]:
            _held.pop(a, None)
        skip = {r["account_id"] for r in targeter.ours()} | set(_held)
        out = []
        for who in pick(targeter.fresh_pool(now), target.get("author_id"), mentioned, now,
                        k=config.MENTIONS_PER_REPLY, skip=skip):
            username = (targeter.account(who) or {}).get("username")
            if username and USERNAME.fullmatch(username):
                out.append(dict(author_id=who, username=username))
                _held[who] = t + HOLD_S
        return out or None
    except Exception:           # never let the extra reach stop a write
        return None


def prompt_line(m, rng=random):
    return rng.choice(LINES).format(ats=" ".join(f"@{u}" for u in handles(m)))


def named(text, m):
    """The planned citizens the text names (exact handle, any case), in plan order."""
    return [x for x in as_list(m) if text and re.search(rf"@{re.escape(x['username'])}(?!\w|\.\w)", text, re.I)]


def used(text, m):
    """True when the sent text names any planned citizen."""
    return bool(named(text, m))
