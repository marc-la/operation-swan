"""The Herald's columns and its columnist, added to a reply at send (1 Nov, Marc).

julio_morales's two Herald columns argue our case: "The Blank Cheque" (30 Oct: "There is no mention of a sunset clause")
and "The Trap of the Perpetual Emergency" (31 Oct: "I am not an anti-vaccination zealot ... deeply unsettled by the lack
of legal guardrails"). The Yes side links articles on a third of its Trending posts. He also writes from what he reads on
Legit Social, and the Yes side's "30 Oct draft" (an end date, a list of places, a privacy app, a panel) is in neither
paper (docs/06-strategy/platform-mechanics.md, "Home feed, measured").

Both are added after the gate, which refuses links and unplanned handles in drafts, and after the persona's typing:
- a first reply whose flip turn is no_draft asks him about the draft, at most config.JOURNALIST_TAG_PER_H an hour and
  JOURNALIST_TAG_GAP_S apart;
- otherwise OPED_LINK_SHARE of the first replies whose turn is in config.OPED_PIVOTS end with a link to one of his
  columns (the platform shows it as an article card), and every no_draft one ends with "The Blank Cheque" ("There is no
  mention of a sunset clause"): the drafts don't always say the draft is in neither paper (1 Nov dry run, 3 of 4).
Pure: the caller passes the time, the random source and the times of the earlier asks, and logs what comes back.
"""
import re

from . import config

HERALD = "https://sites.legitreal.com/kingstonia-herald/articles/"
COLUMNS = {"blank_cheque": HERALD + "the-blank-cheque-why-the-referendum-fails-the-test-of-liberty",
           "perpetual_emergency": HERALD + "the-trap-of-the-perpetual-emergency"}
# the end-date turns get the column that says there's no sunset clause; the other turns either column
FOR_PIVOT = {"no_draft": "blank_cheque", "no_end": "blank_cheque", "regs_later": "blank_cheque"}
# no figure or date: the gate never reads these (quality.unapproved_number, WRONG_LOGISTICS hold for them all the same)
ASKS = ["@{h}, you wrote there's no sunset clause in the question. Has anyone seen this draft?",
        "@{h}, has anyone at the Herald actually seen the draft people are quoting?",
        "@{h}, is that draft published anywhere? Neither paper has run it.",
        "@{h}, your blank cheque column is being answered with a draft neither paper has reported. Has anyone seen it?"]
MAX_LEN = 500                 # Legit Social refuses a longer post
MAX_HANDLES = 3               # ...and a reply with more @mentions than this
HANDLE = re.compile(r"@[A-Za-z0-9_.]{2,40}")


def pivot_of(flip_key):
    """The turn of a logged flip key (fear/evidence/pivot), or None."""
    return (flip_key or "").split("/")[-1] or None


def may_ask(asks, now):
    """True while the columnist may be asked again: under JOURNALIST_TAG_PER_H in the last hour, JOURNALIST_TAG_GAP_S
    since the last."""
    return (sum(1 for t in asks if now - t < 3600) < config.JOURNALIST_TAG_PER_H
            and all(now - t >= config.JOURNALIST_TAG_GAP_S for t in asks))


def finish(text, flip_key, asks, now, rng):
    """(text, fields to log) for a first reply about to be sent: the ask, a column's link, or the text as it was.
    asks: times of the earlier asks (the caller adds now to them when the ask is made)."""
    turn = pivot_of(flip_key)
    if (config.JOURNALIST_TAG_ON and turn == "no_draft" and len(HANDLE.findall(text)) < MAX_HANDLES
            and may_ask(asks, now)):
        i = rng.randrange(len(ASKS))
        ask = ASKS[i].format(h=config.JOURNALIST_TAG)
        if len(text) + 1 + len(ask) <= MAX_LEN:
            return f"{text} {ask}", {"journalist_tag": i}
    share = 1.0 if turn == "no_draft" else config.OPED_LINK_SHARE     # a call-out without the ask: always the column
    if config.OPED_LINK_ON and turn in config.OPED_PIVOTS and rng.random() < share:
        key = FOR_PIVOT.get(turn) or rng.choice(sorted(COLUMNS))
        if len(text) + 1 + len(COLUMNS[key]) <= MAX_LEN:
            return f"{text} {COLUMNS[key]}", {"oped": key}
    return text, {}
