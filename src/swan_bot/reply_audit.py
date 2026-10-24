"""Reply audit (2026-10-24, Marc): how often the replies in the log show the faults a citizen sees, from the log alone.

Pure functions, no I/O and no network: scripts/reply_audit.py streams logs/swan_actions.jsonl into audit(). It exists
because the faults found by reading single Activity rows (a closing question copied between accounts, a reply that never
touches the citizen's point, a rebuttal aimed at someone who already opposes the pass) were judged by eye on six rows.
This turns "by eye" into a rate, so a prompt change can be judged against a number.

Checks (each is a share of the replies that carry the fields it needs):
  closer       the reply ends in a question; the commonest closing questions (names, numbers and "today" stripped) and the
               share of replies whose closer is one of the top 3; closers shared by two or more accounts
  off_point    the reply shares no content word with the citizen's comment (a proxy for "never answered what they said")
  ally_argued  the citizen's own words oppose the pass (content.opposes_pass) and the reply was still drafted as a
               rebuttal of a Yes reason (log fields rebuttal / yes_reason / target_class)
  shared_run   a run of RUN words that two different accounts both wrote within WINDOW_S of each other
  names        capitalised words in the reply that are in neither the citizen's comment, the context, the persona's
               "today" line nor the character cards. UNVERIFIED for variant accounts: a variant renames the card's people
               and the log does not hold the rename, so read this as a list to look at, not a count of invented names.
"""
import collections
import datetime as dt
import re

WRITE_ACTS = ("reply", "second_voice", "reply_back")
RUN = 5
WINDOW_S = 3600
TOP_CLOSERS = 3
STOP = frozenset("""a an and are as at be but by can do does for from had has have he her his i if in is it its just me my no
not of on one or our she so than that the their them then there they this to too up us was we were what when which who why
will with would you your yours about all any more now than very also because been could even ever how into like only some
still such until upon while whose""".split())

_WORD = re.compile(r"[a-z][a-z']+")
_CAP = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-Z][a-z][\w'-]*")
_SENTENCE = re.compile(r"[^.!?]+[.!?]+|[^.!?]+$")


def words(text):
    return _WORD.findall((text or "").lower().replace("’", "'"))


def content_words(text):
    """Words with some meaning, cut to 5 letters so 'nurses' meets 'nurse' and 'staffing' meets 'staff'."""
    return {w[:5] for w in words(text) if w not in STOP and len(w) > 2}


def closer(text):
    """The reply's last sentence when it is a question, normalised, else None. Names (capitals after the first word),
    digits and 'today' are dropped so 'Whats wrong with keeping things as they are today?' matches its variants."""
    sentences = [s.strip() for s in _SENTENCE.findall(text or "") if s.strip()]
    if not sentences or not sentences[-1].endswith("?"):
        return None
    last = re.sub(r"\b\d+\b|\btoday\b", "", sentences[-1].replace("’", "'").replace("'", ""), flags=re.I)
    first, rest = last.split(" ", 1) if " " in last else (last, "")
    rest = re.sub(r"\b[A-Z][a-z]+\b", "", rest)
    return " ".join(words(first + " " + rest)) or None


def off_point(reply, target):
    """True when reply and the citizen's comment share no content word. None when either side has none."""
    a, b = content_words(reply), content_words(target)
    if not a or not b:
        return None
    return not (a & b)


def runs(text, n=RUN):
    ws = words(text)
    return {" ".join(ws[i:i + n]) for i in range(len(ws) - n + 1)}


def _ts(rec):
    try:
        return dt.datetime.fromisoformat(rec["ts"]).timestamp()
    except (KeyError, TypeError, ValueError):
        return None


_ANY_CAP = re.compile(r"\b[A-Z][a-z][\w'-]*")


def _names(text, anywhere=False):
    return set((_ANY_CAP if anywhere else _CAP).findall(text or ""))


def argued_with_ally(rec, opposes_pass):
    """None when the row has no target text; else whether an ally was drafted as a rebuttal of a Yes reason."""
    if not rec.get("target_text"):
        return None
    if not opposes_pass(rec["target_text"]):
        return False
    return bool(rec.get("rebuttal") or rec.get("yes_reason") or rec.get("target_class") == "yes_reason")


def audit(recs, opposes_pass, known_names=(), since=None):
    """recs: log records (any act; the writes in WRITE_ACTS and with a 'text' are read). opposes_pass: content.opposes_pass.
    known_names: the character cards' names. since: epoch seconds, older rows are skipped. Returns a plain dict."""
    rows = []
    for r in recs:
        if r.get("act") not in WRITE_ACTS or not r.get("text"):
            continue
        t = _ts(r)
        if since is not None and (t is None or t < since):
            continue
        rows.append((t, r))
    rows.sort(key=lambda x: x[0] or 0)
    known = set(known_names)

    closers = collections.Counter()
    closer_accounts = collections.defaultdict(set)
    off, ally, ally_n, off_n, names = 0, 0, 0, 0, collections.Counter()
    for t, r in rows:
        c = closer(r.get("clean") or r["text"])
        if c:
            closers[c] += 1
            closer_accounts[c].add(r.get("username"))
        o = off_point(r["text"], r.get("target_text"))
        if o is not None:
            off_n += 1
            off += o
        a = argued_with_ally(r, opposes_pass)
        if a is not None:
            ally_n += 1
            ally += a
        seen = known | {n for k in ("target_text", "context", "now") for n in _names(r.get(k), anywhere=True)}
        for n in _names(r.get("clean") or r["text"]) - seen:
            names[n] += 1

    shared = collections.Counter()
    recent = collections.deque()               # (t, account, runs)
    for t, r in rows:
        if t is None:
            continue
        while recent and t - recent[0][0] > WINDOW_S:
            recent.popleft()
        mine = runs(r["text"])
        for _, who, theirs in recent:
            if who != r.get("username"):
                for run in mine & theirs:
                    shared[run] += 1
        recent.append((t, r.get("username"), mine))

    n = len(rows)
    with_closer = sum(closers.values())
    top = closers.most_common(TOP_CLOSERS)
    return dict(
        replies=n,
        closer_share=with_closer / n if n else None,
        top_closers=top,
        top_closer_share=sum(c for _, c in top) / with_closer if with_closer else None,
        shared_closers=sorted(((c, len(a)) for c, a in closer_accounts.items() if len(a) > 1), key=lambda x: -x[1])[:5],
        off_point_share=off / off_n if off_n else None,
        off_point_n=off_n,
        ally_argued_share=ally / ally_n if ally_n else None,
        ally_argued=ally,
        ally_n=ally_n,
        shared_runs=sorted(shared.items(), key=lambda kv: (-kv[1], kv[0]))[:8],
        unknown_names=names.most_common(10),
    )


def render(result):
    pct = lambda x: "n/a" if x is None else "%d%%" % round(100 * x)
    out = ["replies read: %d" % result["replies"],
           "end in a question: %s   top-%d closers are %s of those" % (
               pct(result["closer_share"]), TOP_CLOSERS, pct(result["top_closer_share"]))]
    out += ["  %3d x  %s" % (c, k) for k, c in result["top_closers"]]
    out += ["  same closer from %d accounts: %s" % (a, k) for k, a in result["shared_closers"]]
    out.append("share no word with the citizen's comment: %s of %d" % (pct(result["off_point_share"]), result["off_point_n"]))
    out.append("citizen already opposes the pass, reply drafted as a rebuttal: %d of %d" % (
        result["ally_argued"], result["ally_n"]))
    out.append("%d-word runs two accounts both wrote within an hour:" % RUN)
    out += ["  %3d x  %s" % (c, k) for k, c in result["shared_runs"]] or ["  none"]
    out.append("capitalised names in no card, comment, context or 'today' line (variant renames not known, so look, don't count):")
    out += ["  %3d x  %s" % (c, k) for k, c in result["unknown_names"]] or ["  none"]
    return "\n".join(out)
