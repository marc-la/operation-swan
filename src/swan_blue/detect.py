"""Account leads from what the bot already read (todo/28 step 5). Reads only; never a post report.

Three detectors over the team accounts' posts in Latest (data/latest_snapshot.json, replies included):
  fingerprint  one wording from many accounts: a 6-word sequence (links, @mentions and #tags left out) posted by
               FP_ACCOUNTS+ team accounts within 24 h, and not one from the setting's own texts (the facts and frames
               every team quotes). The thing that got our own voices caught on 22 Oct.
  cadence      around the clock: active in CADENCE_HOURS+ of the last 24 hours with CADENCE_POSTS+ posts, or
               BURST_POSTS+ posts inside one hour. (Latest is sampled, so these are lower bounds.)
  block        registered as a batch: within a fingerprint group, BLOCK_ACCOUNTS+ accounts created within BLOCK_MIN
               minutes of each other (the platform's created_at), and the username shape they share.
A flagged account is only watched: an account report pays only when the account has a moderator-hidden post and
100+ actions (scoring §3). The service checks a watched account's recent posts for a hide; a hidden one makes it an
account lead, and its report states these measured numbers (rules §5.2.2, LS.6.5). None of these detectors feeds a
post report, ever: they haven't got 10+ rulings behind them.

Memory is kept small: a 1-in-SAMPLE sample of each post's 6-word sequences (by hash), sequences seen from one account
only are dropped after SINGLE_KEEP_S, everything after 24 h. State lives in its own file, saved by the service.
"""
import hashlib
import re

N = 6                         # words per sequence
SAMPLE = 4                    # keep sequences whose hash is 0 mod this (a template has many; most survive)
FP_ACCOUNTS = 5               # todo/28: one skeleton from >= 5 team accounts in 24 h
DAY_S = 24 * 3600
SINGLE_KEEP_S = 3 * 3600
CADENCE_HOURS, CADENCE_POSTS = 20, 40
BURST_POSTS = 20
BLOCK_ACCOUNTS, BLOCK_MIN = 5, 30
POSTS_KEPT = 6                # recent post ids per account, for the hide checks
POST_KEEP_S = 12 * 3600
STRIP = re.compile(r"https?://\S+|@\w+|#\w+")
WORD = re.compile(r"[a-z0-9']+")


def words(text):
    return WORD.findall(STRIP.sub(" ", (text or "").lower()))


def h(gram):
    return int.from_bytes(hashlib.blake2b(gram.encode(), digest_size=6).digest(), "big")


def grams(text):
    """{hash: the sequence} for the sampled 6-word sequences of a text."""
    w = words(text)
    out = {}
    for i in range(max(0, len(w) - N + 1)):
        g = " ".join(w[i:i + N])
        k = h(g)
        if k % SAMPLE == 0:
            out[k] = g
    return out


_SOURCE = None


def source_hashes():
    """The setting's own wording (facts, frames, craft texts every side quotes): never a fingerprint."""
    global _SOURCE
    if _SOURCE is None:
        try:
            from swan_bot import quality                 # read-only: its SOURCES list
            texts = list(quality.SOURCES)
        except Exception:                                # noqa: BLE001 - a missing source list only widens the net
            texts = []
        _SOURCE = {k for t in texts for k in grams(t)}
    return _SOURCE


def shape(username):
    """A username's shape: words of 4+ letters as 'w', short parts by their length, digits as '9'.
    mira_solis_kc -> w_w_2."""
    parts = re.split(r"([._-])", username or "")
    return "".join(p if p in "._-" else "9" if p.isdigit() else "w" if len(p) >= 4 else str(len(p)) for p in parts)


def empty():
    return dict(grams={}, hours={}, posts={}, profiles={}, watch={}, seen=0)


def observe(d, posts, is_team, t):
    """Take in a Latest page: each team post's sampled sequences, its hour, its id."""
    src = source_hashes()
    for p in posts:
        aid = p.get("author_id")
        if not aid or not is_team(aid) or p.get("repost_of_post_id"):
            continue
        a, pid = str(aid), p["post_id"]
        recent = d["posts"].setdefault(a, [])
        if any(x[0] == pid for x in recent):
            continue                                     # seen in an earlier page
        d["seen"] += 1
        recent.append([pid, t])
        del recent[:-POSTS_KEPT]
        hour = str(int(t // 3600))
        hrs = d["hours"].setdefault(a, {})
        hrs[hour] = hrs.get(hour, 0) + 1
        for k, g in grams(p.get("body")).items():
            if k in src:
                continue
            e = d["grams"].setdefault(str(k), dict(a={}, g=None))
            e["a"][a] = t
            if len(e["a"]) >= 2:
                e["g"] = g                               # keep the words once two accounts share them


def prune(d, t):
    keep = {}
    for k, e in d["grams"].items():
        e["a"] = {a: s for a, s in e["a"].items() if t - s < DAY_S}
        if len(e["a"]) >= 2 or (e["a"] and t - max(e["a"].values()) < SINGLE_KEEP_S):
            keep[k] = e
    d["grams"] = keep
    now_h = int(t // 3600)
    d["hours"] = {a: {hh: n for hh, n in v.items() if now_h - int(hh) < 24} for a, v in d["hours"].items()}
    d["hours"] = {a: v for a, v in d["hours"].items() if v}
    d["posts"] = {a: [x for x in v if t - x[1] < POST_KEEP_S] for a, v in d["posts"].items()}
    d["posts"] = {a: v for a, v in d["posts"].items() if v}


def fingerprints(d):
    """[(accounts, the shared words)] for sequences from FP_ACCOUNTS+ accounts, biggest first; one per account."""
    rows = sorted(((set(e["a"]), e["g"]) for e in d["grams"].values() if len(e["a"]) >= FP_ACCOUNTS and e["g"]),
                  key=lambda r: -len(r[0]))
    return rows


def cadence(d):
    """{account: (active hours of the last 24, posts, most in one hour)} for the round-the-clock and burst ones."""
    out = {}
    for a, v in d["hours"].items():
        n, peak = sum(v.values()), max(v.values())
        if (len(v) >= CADENCE_HOURS and n >= CADENCE_POSTS) or peak >= BURST_POSTS:
            out[a] = (len(v), n, peak)
    return out


def block(accounts, profiles):
    """Within one group: the biggest set of accounts created within BLOCK_MIN minutes of each other, and the
    username shape most of them share. None when under BLOCK_ACCOUNTS."""
    from .evidence import ts
    known = sorted((ts(profiles[a]["c"]), a) for a in accounts if a in profiles and profiles[a].get("c"))
    best = []
    for i, (t0, _) in enumerate(known):
        run = [a for t1, a in known[i:] if t1 - t0 <= BLOCK_MIN * 60]
        best = run if len(run) > len(best) else best
    if len(best) < BLOCK_ACCOUNTS:
        return None
    shapes = {}
    for a in best:
        s = shape(profiles[a].get("u"))
        shapes[s] = shapes.get(s, 0) + 1
    top = max(shapes, key=shapes.get)
    span = (max(ts(profiles[a]["c"]) for a in best) - min(ts(profiles[a]["c"]) for a in best)) / 60
    return dict(accounts=best, span_min=round(span), shape=top, shape_n=shapes[top])


def find(d, t, ours=()):
    """Update the watch list from the detectors; returns the accounts newly watched."""
    prune(d, t)
    new = []

    def flag(a, kind, evidence):
        if int(a) in ours:
            return
        w = d["watch"].setdefault(a, dict(since=t, kinds={}))
        if kind not in w["kinds"]:
            w["kinds"][kind] = evidence
            if len(w["kinds"]) == 1:
                new.append(a)

    for accounts, words_ in fingerprints(d):
        for a in accounts:
            if "fingerprint" not in d["watch"].get(a, {}).get("kinds", {}):
                flag(a, "fingerprint", dict(n=len(accounts), words=words_, accounts=sorted(accounts, key=int)[:40]))
        b = block(accounts, d["profiles"])
        if b:
            for a in b["accounts"]:
                flag(a, "block", dict(n=len(b["accounts"]), span_min=b["span_min"], shape=b["shape"],
                                      shape_n=b["shape_n"]))
    for a, (hours, n, peak) in cadence(d).items():
        flag(a, "cadence", dict(hours=hours, posts=n, peak=peak))
    d["watch"] = {a: w for a, w in d["watch"].items() if t - w["since"] < 3 * DAY_S}
    return new


def need_profiles(d, limit):
    """Accounts in fingerprint groups whose profile (username, created_at) we haven't read yet."""
    want = []
    for accounts, _ in fingerprints(d):
        want += [a for a in sorted(accounts, key=int) if a not in d["profiles"] and a not in want]
    return want[:limit]


def evidence_text(kinds):
    """The measured numbers behind a watched account, as clauses for its account report."""
    out = []
    fp = kinds.get("fingerprint")
    if fp:
        out.append(f"it is one of {fp['n']} accounts registered after the campaign launch that posted the same "
                   f"{N}-word sequence (\"{fp['words']}\") within 24 hours")
    c = kinds.get("cadence")
    if c:
        out.append(f"it posted in {c['hours']} of the last 24 hours ({c['posts']}+ posts, up to {c['peak']} in one "
                   f"hour)" if c["hours"] >= CADENCE_HOURS else
                   f"it posted {c['peak']}+ times inside a single hour")
    b = kinds.get("block")
    if b:
        out.append(f"it is one of {b['n']} accounts in that group created within {max(b['span_min'], 1)} minutes "
                   f"of each other" + (f", {b['shape_n']} of them with the same username pattern"
                                       if b["shape_n"] >= BLOCK_ACCOUNTS else ""))
    return out
