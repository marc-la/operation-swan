"""Replay evaluation (2026-10-25, Marc): judge a prompt or gate change on a fixed set of real citizen comments instead of
waiting for the next poll and reading three rows by eye.

Pure functions, no I/O and no network: scripts/replay_eval.py freezes jobs from logs/swan_actions.jsonl, drafts them through
the bot's own build_prompt and draft_checked, and calls score() on the result. Nothing is posted, liked or sent to the
platform; the drafts are for reading and counting only.

What a reply is scored on (each a share of the replies, so two runs can be compared):
  motifs         "door", "papers", "bakery", "40 nursing posts", "certificate", "half four", "who in your", a spaced dash
  concedes       it opens by granting the citizen's point (quality's concede_open tell, or "you're right ...")
  bare_they      it opens on They/Them/Those with nobody for it to mean
  echo_open      it opens by quoting the citizen back ("You want a ...", "... you said")
  question       it ends in a question
  off_point      it shares no content word with the citizen's comment (reply_audit.off_point)
  asks_answered  of the comments that name a condition (sunset, review, exemptions...), those whose reply uses that word
  f14_when_asked of the comments that name a condition, those answered in the F14 frame
and across the stream, which is where "one script on one profile" shows up:
  clash          mean of each reply's largest 5-word-shingle overlap with the replies before it (the window starts with
                 the real recent texts, so a run that repeats what the account said all day scores high)
  distinct_open  distinct three-word openings over replies
  top_motif      the largest motif share
"""
import collections
import re

from . import quality, reply_audit

MOTIFS = {
    "door": re.compile(r"\bdoors?\b|\bdoorman\b|\bdoormen\b", re.I),
    "papers": re.compile(r"\bpapers\b", re.I),
    "bakery": re.compile(r"\bbakery\b", re.I),
    "nursing_40": re.compile(r"\b40\b|nursing (?:posts|vacanc)", re.I),
    "certificate": re.compile(r"\bcertificates?\b", re.I),
    "half_four": re.compile(r"\bhalf (?:past )?four\b|\b4[:.]?30\b", re.I),
    "who_in_your": re.compile(r"\bwho in your\b", re.I),
    "spaced_dash": re.compile(r"\s[-–—]\s"),
}
CONCEDES = re.compile(r"^\W*(?:you'?re right|you are right|that'?s (?:fair|true|right)|fair (?:point|enough)|good point|"
                      r"agreed|i hear you)\b", re.I)
ECHO_OPEN = re.compile(r"^\W*(?:you want|you'?d like|you asked|you'?re after|you said|you mention)|"
                       r"\b(?:you said|you'?re after|what you'?re after)\W*$", re.I)
BARE_THEY = re.compile(r"^\W*(?:they|them|those)\b", re.I)
CONDITION = re.compile(r"sunset|end[- ]date|stop date|expir|review|exemption|safeguard|written (?:in|down)|venue list|"
                       r"published list|spaces list|audit|threshold|guarantee", re.I)


def _opening(text, n=3):
    return " ".join(reply_audit.words(text)[:n])


def named_conditions(target_text):
    """The condition words the citizen's comment names (lowercased, first form seen), for asks_answered."""
    return list(dict.fromkeys(m.group(0).lower() for m in CONDITION.finditer(target_text or "")))


def answers_condition(reply, conditions):
    """True when the reply uses a word (to five letters, so 'reviews' meets 'review') of one of the conditions asked for."""
    mine = reply_audit.content_words(reply)
    return any(reply_audit.content_words(c) & mine for c in conditions)


def one(reply, target_text="", frame=None):
    """The flags for one reply: {name: bool}."""
    t = quality.normalise(reply)
    flags = {f"motif_{k}": bool(rx.search(reply or "")) for k, rx in MOTIFS.items()}
    conds = named_conditions(target_text)
    off = reply_audit.off_point(reply, target_text)
    flags.update(
        concedes=bool(CONCEDES.search(t) or quality.PHRASE_BUDGETS["concede_open"][0].search(t)),
        bare_they=bool(BARE_THEY.search(t)),
        echo_open=bool(ECHO_OPEN.search(t)),
        question=t.rstrip().endswith("?"),
        off_point=bool(off) if off is not None else False,
        has_condition=bool(conds),
        answers_condition=bool(conds) and answers_condition(reply, conds),
        f14=(frame or "").startswith("F14"),
    )
    return flags


def score(items, window=()):
    """items: dicts with reply (text), target_text, frame, in the order they would have been sent; window: the real recent
    texts that came before. Returns {metric: number or None} (shares are 0-1)."""
    items = [i for i in items if i.get("reply")]
    n = len(items)
    if not n:
        return {"n": 0}
    flags = [one(i["reply"], i.get("target_text"), i.get("frame")) for i in items]
    share = lambda k: sum(f[k] for f in flags) / n
    asked = [f for f in flags if f["has_condition"]]
    seen = [quality._shingles(quality.strip_tag(w.strip())) for w in window][-300:]
    clash = []
    for i in items:
        mine = quality._shingles(quality.strip_tag(i["reply"].strip()))
        clash.append(max((len(mine & old) / max(1, len(mine)) for old in seen), default=0.0))
        seen.append(mine)
    out = {"n": n,
           **{k: share(k) for k in flags[0] if k.startswith("motif_")},
           **{k: share(k) for k in ("concedes", "bare_they", "echo_open", "question", "off_point")},
           "asked_n": len(asked),
           "asks_answered": (sum(f["answers_condition"] for f in asked) / len(asked)) if asked else None,
           "f14_when_asked": (sum(f["f14"] for f in asked) / len(asked)) if asked else None,
           "clash": sum(clash) / n,
           "distinct_open": len({_opening(i["reply"]) for i in items}) / n,
           "words_median": sorted(len(reply_audit.words(i["reply"])) for i in items)[n // 2]}
    out["top_motif"] = max(v for k, v in out.items() if k.startswith("motif_") and k != "motif_bakery")
    return out


def compare(a, b, names=("A", "B")):
    """A text table of two score() dicts, with b - a. Lower is better for every row except distinct_open, asks_answered and
    f14_when_asked."""
    higher_better = {"distinct_open", "asks_answered", "f14_when_asked"}
    keys = [k for k in a if k in b and k not in ("n", "asked_n")]
    pct = lambda v: "n/a" if v is None else (f"{v:.0f}" if isinstance(v, int) else f"{100 * v:.0f}%")
    lines = [f"{'':22}{names[0]:>10}{names[1]:>10}{'change':>10}   (+ better, - worse)",
             f"{'replies':22}{a['n']:>10}{b['n']:>10}"]
    for k in keys:
        x, y = a[k], b[k]
        if k in ("clash",):
            cell = lambda v: "n/a" if v is None else f"{v:.2f}"
        else:
            cell = pct
        d = "" if x is None or y is None else (f"{y - x:+.0f}" if k == "words_median" else
                                              f"{100 * (y - x):+.0f} pt" if k != "clash" else f"{y - x:+.2f}")
        better = "" if not d or float(d.split()[0]) == 0 else (
            " +" if (float(d.split()[0]) > 0) == (k in higher_better) else " -")
        lines.append(f"{k:22}{cell(x):>10}{cell(y):>10}{d:>10}{better}")
    return "\n".join(lines)
