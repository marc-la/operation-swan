"""The live-lead scanner (todo/43 item 2): account leads with a vanished post, from reads alone. Pure state functions;
the service does the reading (service.Blue.scan_step).

A post the moderator hides vanishes from `account_posts`. Every BLUE_SCAN_EVERY_S the service re-reads the newest
page of each tracked LIVE rival account (team account, posted within LIVE_H hours, MIN_POSTS+ posts, not ours) and
compares it with the previous snapshot, kept here as post ids only. A post id that was on the page and is missing
from an account that is still posting is a vanished-post candidate (a post only counts as missing if it should still
be on the page: it is newer than the oldest id read, or the page held the whole history). A candidate becomes a lead
once `get_post` answers 404 on two reads at least CONFIRM_GAP_S apart. An author deleting their own post looks the same
from outside, so a lead only says the post is no longer available: its account report is dismissed if the post was
the author's delete (a slot lost for 3 h, never a lock). The report's detail text says exactly that and never that
the moderator hid it (service/evidence.account_detail, vanished=True).

Leads are logged and shown in blue_status.json. They file only with BLUE_SCAN_FILE=1, through the same ranked fill as
every account lead (liveness gate, cap, 100-action rule), and only with a measured pattern to state (PACE_MIN posts an
hour on the page read, or a ring/detector clause found by the harvest).

Memory is bounded: KEEP_ACCOUNTS snapshots of at most PAGE ids each (about 0.5 MB as compact JSON), candidates
dropped after CAND_KEEP_S, LEADS_KEPT leads.
"""
import datetime as dt

PAGE = 50                     # posts per read (one read per account): at 10 posts an hour that is 5 h of history
LIVE_H = 6.0                  # a tracked account posted within this long
MIN_POSTS = 30                # accounts with fewer posts visible are not worth a slot
KEEP_ACCOUNTS = 1500          # snapshots kept, newest posters first (census 23 Oct: about 1,500 posted in 24 h)
CONFIRM_GAP_S = 10 * 60       # the second 404 comes at least this long after the first
CAND_KEEP_S = 24 * 3600
LEADS_KEPT = 200
PACE_MIN = 3.0                # posts an hour (page read) that we are willing to state as a measured fact


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def empty():
    return dict(v=1, snap={}, seen={}, cand={}, leads={}, todo=[], pass_at=0, pass_n=0, sib=[], sib_done={},
                stats=dict(passes=0, reads=0, errors=0, vanished=0, confirmed=0, visible=0, siblings=0))


def observe(st, posts, is_team, t):
    """Take in a Latest page: team accounts that posted lately are the pool the next pass reads."""
    for p in posts:
        aid = p.get("author_id")
        if aid and is_team(aid):
            try:
                at = ts(p["created_at"])
            except (KeyError, ValueError):
                at = t
            k = str(aid)
            st["seen"][k] = max(st["seen"].get(k, 0), at)
    st["seen"] = {k: v for k, v in st["seen"].items() if t - v <= LIVE_H * 3600}


def targets(st, t, is_team):
    """The accounts a pass reads: seen posting within LIVE_H, or snapshotted as posting then; newest first."""
    last = dict(st["seen"])
    for k, s in st["snap"].items():
        last[k] = max(last.get(k, 0), s.get("last") or 0)
    live = sorted(((v, k) for k, v in last.items() if t - v <= LIVE_H * 3600 and is_team(int(k))), reverse=True)
    return [k for _, k in live[:KEEP_ACCOUNTS]]


def facts(page):
    """(ids newest first, newest post time, count, span in seconds) of an account_posts page."""
    ids = [p["post_id"] for p in page]
    times = [ts(p["created_at"]) for p in page if p.get("created_at")]
    return ids, (max(times) if times else None), len(ids), (max(times) - min(times) if len(times) > 1 else 0.0)


def vanished(prev_ids, new_ids, limit=PAGE):
    """Ids on the previous page that are missing from this one although they should still be on it: newer than the
    oldest id read, or the page holds the whole history (fewer posts than the limit)."""
    if not prev_ids or not new_ids:
        return []
    have, lo = set(new_ids), min(new_ids)
    whole = len(new_ids) < limit
    return [p for p in prev_ids if p not in have and (whole or p > lo)]


def pace(n, span_s):
    """Posts an hour over the page read (n posts span n - 1 intervals); None when the page covers under 10 minutes (a
    burst says nothing)."""
    return round((n - 1) / (span_s / 3600), 1) if span_s >= 600 else None


def pace_text(n, span_s):
    """The measured rate as a clause for the report: 'N times in the last H hours (about R an hour)'."""
    p = pace(n, span_s)
    if p is None:
        return None
    h = span_s / 3600
    return f"{n} times in the last {h:.1f} hours (about {p:g} an hour)" if h >= 1 else \
        f"{n} times in the last {round(span_s / 60)} minutes"


def compare(st, aid, page, t, src="scan"):
    """Take in an account's newest page. Returns the vanished candidate ids (also recorded in st['cand']) or None when
    the account isn't worth tracking (too few posts, or not posting any more: its snapshot is dropped)."""
    ids, last, n, span = facts(page)
    if last is None or n < MIN_POSTS:                 # the page is short only when that's the whole history
        st["snap"].pop(aid, None)
        return None
    if t - last > LIVE_H * 3600:
        st["snap"].pop(aid, None)
        return None
    prev = st["snap"].get(aid)
    st["snap"][aid] = dict(t=round(t), ids=ids[:PAGE], last=round(last), n=n, span=round(span), pace=pace(n, span))
    gone = vanished(prev["ids"], ids) if prev else []
    note(st, aid, gone, t, src)
    if len(st["snap"]) > KEEP_ACCOUNTS:
        for k, _ in sorted(st["snap"].items(), key=lambda kv: kv[1].get("last") or 0)[:len(st["snap"]) - KEEP_ACCOUNTS]:
            del st["snap"][k]
    return gone


def note(st, aid, pids, t, src):
    """Record vanished-post candidates (from a diff, or a sibling check)."""
    for p in pids:
        st["cand"].setdefault(aid, {}).setdefault(str(p), [round(t), 0, src])


def due(st, t, limit):
    """[(account, post id)] whose next get_post check is due: never checked, or the first 404 was CONFIRM_GAP_S ago."""
    out = []
    for aid, ps in st["cand"].items():
        for pid, (t0, c1, _src) in ps.items():
            if c1 == 0 or t - c1 >= CONFIRM_GAP_S:
                out.append((t0, aid, int(pid)))
    return [(a, p) for _, a, p in sorted(out)[:limit]]


def verdict(st, aid, pid, t, gone):
    """Record one get_post answer (gone = it answered 404). 'visible' drops the candidate, 'pending' is the first 404,
    'confirmed' the second one 10+ minutes later (the candidate is removed; the caller makes the lead)."""
    ps = st["cand"].get(aid) or {}
    e = ps.get(str(pid))
    if e is None:
        return None
    if not gone:
        del ps[str(pid)]
        out = "visible"
    elif e[1] == 0:
        e[1] = round(t)
        return "pending"
    else:
        del ps[str(pid)]
        out = "confirmed"
    if not ps:
        st["cand"].pop(aid, None)
    return out


def src_of(st, aid, pid):
    return ((st["cand"].get(aid) or {}).get(str(pid)) or [0, 0, "scan"])[2]


def prune(st, t):
    st["cand"] = {a: {p: e for p, e in ps.items() if t - e[0] <= CAND_KEEP_S} for a, ps in st["cand"].items()}
    st["cand"] = {a: ps for a, ps in st["cand"].items() if ps and a in st["snap"]}
    if len(st["leads"]) > LEADS_KEPT:
        keep = sorted(st["leads"].items(), key=lambda kv: -kv[1]["found"])[:LEADS_KEPT]
        st["leads"] = dict(keep)
    st["sib_done"] = {k: v for k, v in st["sib_done"].items() if t - v < 6 * 3600}


def has_pattern(h):
    """Does a scan or sibling lead carry a measured pattern the report can state besides the vanished post and the
    100 actions? A pace of PACE_MIN an hour or more, a lockstep ring we measured, or a detector's numbers."""
    return bool((h.get("pace") or 0) >= PACE_MIN or h.get("ring_posts") or h.get("kinds"))
