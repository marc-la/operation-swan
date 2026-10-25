"""@mentions in first replies (todo/46, Marc 25 Oct): the arm "mention" of arm_eng.

A notification (replies and mentions only) is the one channel that reaches a citizen who has not heard from us; likes and
follows never do. In a mention block, MENTION_SHARE of ordinary first replies name one OTHER citizen who is active now, by
@username, so that citizen gets a notification from a post in a thread they are not in. The platform allows 3 handles in a
reply (rules); we use MENTIONS_PER_REPLY (1).

Rules that keep it ordinary: first replies only (config.MENTION_MODES), not off-topic or group replies, never a firm Yes or a
No-leaner (they are not the audience), a citizen is named at most once per MENTION_RECONTACT_S, and the handle is written
into the reply by the model in its own words, never appended. Anything that goes wrong means no mention: plan() never raises.

Read-out: the write is logged with `mention` (the handle used, None when the draft dropped it) and `mention_target` (their
id); `citizen_repliers` on the post's outcome reads say whether that citizen answered. The arm is `arm_eng == "mention"`.
"""
import random
import re
import time

from . import config, experiment

CLASSES = ("conditions", "unsure", "unclear")        # the citizens a No can still reach; not yes_reason, lean_no, firm_yes
MAX_AGE_MIN = 120                                    # the mentioned citizen posted within this long
LINES = (
    "Keep answering the person above. In one clause of your own words bring in {at} as a third neighbour who has raised the "
    "same worry, for instance by asking what they make of it. Never address {at} as \"you\" and never open with the handle.",
    "Keep answering the person above, and in the middle of the reply add that {at} has been wondering about the same thing "
    "or ask what {at} thinks. {at} is a third person here, not the one you are talking to; don't open or end on the handle.",
    "Answer the person above as you would, and work {at} in once, in your own words, as someone else in the neighbourhood "
    "who might see it differently. Speak about {at} in the third person; no other @ names.",
)


def active(job, t=None):
    """True when this reply may carry a mention: the mention arm's block, an ordinary first reply, and the share."""
    if not config.MENTION_SHARE or job.get("mode") not in config.MENTION_MODES:
        return False
    if job.get("style") == "off_topic" or job.get("group") or job.get("arm") == "firm_yes":
        return False
    return experiment.block("arm_eng", t)[1] == "mention" and random.random() < config.MENTION_SHARE


def pick(pool, author_id, mentioned, now=None, rng=random):
    """The author id to name, from pool [{author_id, post_id, cls, age_min}] (Targeter.mention_pool), or None: not the citizen
    we are answering, in CLASSES, posted within MAX_AGE_MIN, not named in the last MENTION_RECONTACT_S."""
    now = time.time() if now is None else now
    ok = [p for p in pool if p["author_id"] != author_id and p["cls"] in CLASSES and p["age_min"] <= MAX_AGE_MIN
          and now - float((mentioned or {}).get(str(p["author_id"]), 0)) >= config.MENTION_RECONTACT_S]
    return rng.choice(ok)["author_id"] if ok else None


def plan(job, targeter, mentioned, now=None):
    """{author_id, username} to name in this reply, or None. Reads the account's username (a public read, outside any lock)."""
    try:
        if not active(job):
            return None
        target = job.get("target") or {}
        who = pick(targeter.mention_pool(), target.get("author_id"), mentioned, now)
        if who is None:
            return None
        username = (targeter.social.get_account(who) or {}).get("username")
        if not username or not re.fullmatch(r"\w{2,40}", username):
            return None
        return dict(author_id=who, username=username)
    except Exception:           # never let the extra reach stop a write
        return None


def prompt_line(m, rng=random):
    return rng.choice(LINES).format(at=f"@{m['username']}")


def used(text, m):
    """True when the sent text names the planned citizen (exact handle, any case)."""
    return bool(m and text and re.search(rf"@{re.escape(m['username'])}\b", text, re.I))
