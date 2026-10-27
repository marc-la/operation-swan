"""Fleets: a team proxy from account ids and creation times (todo/43 item 4). Pure; no reads here.

A team registers its accounts in bursts, so team accounts with neighbouring ids and creation times a few seconds apart
tend to share a fate (dead or alive 24 h on: 69-75% of pairs against 51% by chance, census 23 Oct,
docs/06-strategy/blue-reporting.md section 10). A fleet is a chain of team accounts, taken in id order, where each link is
at most FLEET_ID_GAP ids and FLEET_GAP_S seconds from the one before. The id gap hardly matters (ids are dense, the median
gap between neighbours is 15 s); the time gap is the cut. Thresholds from scripts/blue_fleet_eval.py. A chain longer
than a team's allowance (FLEET_MAX accounts) is more than one team: it is cut at its largest time gaps.

Blue's `labels` (16 clusters, c8701 alone 450 accounts) are the fallback when no account list has been read yet. A fleet
is a proxy, never proof of a team: it only decides which target team an award is counted against.
"""
from swan_bot import config

FLEET_ID_GAP = 5          # neighbouring team ids: at most this far apart (ids of other teams or ours sit between)
FLEET_GAP_S = 30.0        # ...and created at most this many seconds apart (a bot's registration loop, not a person)
FLEET_MAX = 200           # a team may hold 200 accounts in all (CLAUDE.md): a longer chain is cut


def is_team_row(account_id, verified=False):
    return (account_id > config.CITIZEN_MAX_ID and not config.is_citizen(account_id) and not verified
            and config.blue_citizen(account_id) is None)          # todo/48: a likely citizen is no team's (BLUE_NPC_GUARD)


def rows(accounts, skip=()):
    """[(id, created epoch or None)] for the team accounts of a platform account list (client.accounts() dicts),
    sorted by id. Citizens, organisers and verified accounts are left out, and `skip` (our own ids): they must not
    glue a neighbour's fleet together. A private account has no created_at (None)."""
    out = {}
    for a in accounts:
        i = a["account_id"]
        if i in skip or not is_team_row(i, a.get("verified")):
            continue
        c = a.get("created_at")
        out[i] = round(_epoch(c), 1) if c else None
    return sorted(out.items())


def _epoch(s):
    import datetime as dt
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def chains(rs, id_gap=FLEET_ID_GAP, gap_s=FLEET_GAP_S, max_size=FLEET_MAX):
    """The fleets of sorted rows [(id, epoch|None)] as lists of rows. A private account has no creation time: it is
    taken as created between its neighbours, so it joins the fleet before it when the ids are close, and the next
    account's time is compared with the last one that is known."""
    out, cur, last_t = [], [], None
    for i, t in rs:
        if cur:
            close = i - cur[-1][0] <= id_gap and (t is None or last_t is None or t - last_t <= gap_s)
            if not close:
                out.append(cur)
                cur, last_t = [], None
        cur.append((i, t))
        last_t = t if t is not None else last_t
    if cur:
        out.append(cur)
    return [piece for c in out for piece in _cut(c, max_size)]


def _cut(chain, max_size):
    """Split a chain longer than max_size at its largest time gap, recursively."""
    if len(chain) <= max_size:
        return [chain]
    gaps = [((b[1] - a[1]) if a[1] is not None and b[1] is not None else 0.0, b[0] - a[0], k + 1)
            for k, (a, b) in enumerate(zip(chain, chain[1:]))]
    at = max(gaps)[2]
    return _cut(chain[:at], max_size) + _cut(chain[at:], max_size)


def fleets_from_rows(rs, **kw):
    """{account id: fleet key}. The key is 'f' + the fleet's lowest id (a new registration joins at the top, so the
    key of an existing fleet is stable)."""
    return {i: f"f{c[0][0]}" for c in chains(rs, **kw) for i, _ in c}


def fleets(accounts, skip=(), **kw):
    """{account id: fleet key} for the team accounts of a platform account list. See the module docstring."""
    return fleets_from_rows(rows(accounts, skip), **kw)


def members(fleet_map):
    """{fleet key: [account ids]}."""
    out = {}
    for i, k in fleet_map.items():
        out.setdefault(k, []).append(i)
    return out
