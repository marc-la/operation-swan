"""Expected points of answering a candidate, when the reply lands (todo/49, 27 Oct 2026). Pure: no reads, no writes.

Writes are capped (3 a minute) and on-vote citizen posts outnumber them, so score is which candidate each slot takes. A
candidate's worth is read off a table keyed by its class group and its age when our reply would land (age now + the
pick-to-send lag, config.VALUE_LAG_S): proxy points a write, citizen replies x15 + likes x5 at the 6 h outcome check (the
portal pays ~4x this; the order holds). scripts/value_table.py builds the table from the logs: each clock hour gets its own
level (the queue runs old at night, when citizens answer most, so raw >4 h posts looked better than 20-min ones: strong 0.95
raw, 0.65 adjusted), cells under 40 writes fall back to the group mean, then each group's curve is made non-increasing
(weighted pool-adjacent-violators) and read between knots, linear in log(1 + minutes). Factors left out: a citizen who
answered us before (-0.2 points, n=2,717: no lift once age and hour are in); 6+ unanswered touches (the queue keeps no touch
count); the hour itself (the same for every candidate of one moment).

targeting.next_target ranks by this in config.VALUE_PICK's "value" blocks (pick_arm); data/value_table.json, when present and
valid, replaces DEFAULT (re-read at most every TABLE_CHECK_S), so the bot never depends on the file. Replay 27 Oct (todo/49,
docs/06-strategy/targeting-audit-2026-10-27.md): within noise of today's order, so it ships off."""
import datetime as dt
import json
import math
import time

from . import config, experiment

# class -> group. conditions_flat stays with conditions until it has its own data (27 Oct); firm_yes (19 writes in 48 h, capped
# at FIRM_YES_PER_H) reads as weak. An unknown class is weak.
GROUPS = {"conditions": "strong", "conditions_flat": "strong", "yes_reason": "strong", "unclear": "weak", "unsure": "weak",
          "off_topic": "weak", "firm_yes": "weak", "lean_no": "lean_no"}
NEEDED = ("strong", "weak", "lean_no")

# scripts/value_table.py build --hours 72 --end 2026-10-27T03:37: 10,165 first replies (ordinary and turnout) with a 6 h check.
# curves: group -> [[mean minutes at landing in the age bin, points], ...]; bins 0-1-2-3-5-10-20-60-240 min and older.
# The 48 h windows ending 26 Oct 15:37 and 27 Oct 03:37 give the same shape (strong 2.8-3.0 under 1 min, ~2.1 at 1.5, ~1.2
# at 4, 0.65-0.8 past 30; weak ~2.7 under 1 min, then 0.5-0.75 flat). The weak cliff after the first minute held in every
# window (137-173 writes a window): a weak post read in its first minute is worth a strong one, after that a third of one.
DEFAULT = {
    "built": "2026-10-27", "window": ["2026-10-24T03:37", "2026-10-27T03:37"], "writes": 10165,
    "curves": {
        "strong": [[0.58, 2.844], [1.56, 2.222], [2.48, 1.935], [3.82, 1.278], [6.93, 1.12], [11.51, 1.12], [37.52, 0.9],
                   [121.67, 0.652], [938.54, 0.652]],
        "weak": [[0.56, 2.832], [1.54, 0.686], [2.5, 0.686], [3.82, 0.686], [7.0, 0.616], [11.54, 0.616], [38.14, 0.616],
                 [121.78, 0.616], [937.77, 0.616]],
        "lean_no": [[0.58, 2.597], [1.54, 2.566], [2.54, 1.007], [3.87, 1.007], [7.18, 0.721], [11.27, 0.721], [41.5, 0.721],
                    [132.19, 0.721], [1508.64, 0.721]],
        "reply_back": [[0.7, 2.157], [1.59, 2.157], [2.33, 2.144], [3.4, 1.934], [14.68, 1.934], [43.01, 1.934],
                       [158.43, 1.934], [663.96, 1.934]],
    },
    "n": {"strong": [556, 1532, 1092, 1120, 747, 123, 179, 266, 971], "weak": [173, 311, 327, 412, 370, 75, 92, 191, 348],
          "lean_no": [101, 79, 84, 132, 162, 31, 10, 49, 88], "reply_back": [57, 244, 173, 27, 1, 3, 25, 14]},
}

TABLE_CHECK_S = 60
_cache = {"at": 0.0, "mtime": None, "table": None}


def group_of(cls):
    return GROUPS.get(cls, "weak")


def valid(table):
    """A table the bot may use: every NEEDED group, knots in rising age, finite points that never rise with age."""
    try:
        curves = table["curves"]
        for g in NEEDED:
            knots = curves[g]
            ages, pts = [float(a) for a, _ in knots], [float(p) for _, p in knots]
            if not knots or any(not math.isfinite(x) for x in ages + pts) or any(b <= a for a, b in zip(ages, ages[1:])):
                return False
            if any(b > a + 1e-9 for a, b in zip(pts, pts[1:])):
                return False
        return True
    except (KeyError, TypeError, ValueError):
        return False


def table(path=None, now=None):
    """The table in use: path (default config.VALUE_TABLE_FILE) when it reads and is valid, else DEFAULT. Cached; the file
    is looked at again at most every TABLE_CHECK_S."""
    now = time.time() if now is None else now
    path = path or getattr(config, "VALUE_TABLE_FILE", None)
    if _cache["table"] is not None and now - _cache["at"] < TABLE_CHECK_S and _cache.get("path") == path:
        return _cache["table"]
    _cache.update(at=now, path=path)
    try:
        mtime = path.stat().st_mtime if path else None
    except OSError:
        mtime = None
    if mtime is None:
        _cache.update(mtime=None, table=DEFAULT)
    elif mtime != _cache["mtime"] or _cache["table"] is None:
        try:
            t = json.loads(path.read_text())
        except (OSError, ValueError):
            t = None
        _cache.update(mtime=mtime, table=t if valid(t) else DEFAULT)
    return _cache["table"]


def reset():
    _cache.update(at=0.0, mtime=None, table=None, path=None)


def curve(knots, minutes):
    """Points at this landing age: linear in log(1 + minutes) between knots, flat outside them."""
    x = math.log1p(max(0.0, minutes))
    xs = [math.log1p(a) for a, _ in knots]
    if x <= xs[0]:
        return knots[0][1]
    for (x0, (_, p0)), (x1, (_, p1)) in zip(zip(xs, knots), zip(xs[1:], knots[1:])):
        if x <= x1:
            return p0 + (p1 - p0) * (x - x0) / (x1 - x0)
    return knots[-1][1]


def created_ts(post):
    try:
        return dt.datetime.fromisoformat((post.get("created_at") or "").replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def expected_points(cand, now=None, lag_s=None, tab=None):
    """Proxy points of answering this candidate now: its class group's curve at its age when the reply lands. A post with
    no readable time reads as a day old (last among the fresh)."""
    now = time.time() if now is None else now
    lag_s = config.VALUE_LAG_S if lag_s is None else lag_s
    tab = tab or table(now=now)
    made = created_ts(cand.get("post") or {})
    minutes = ((now - made) if made is not None else 86400) / 60 + lag_s / 60
    return round(curve(tab["curves"][group_of(cand.get("target_class"))], minutes), 3)


def step(ev):
    """Expected points in config.VALUE_STEP steps, for the sort: candidates within one step count as equal and the read's
    score decides (persuasion potential, which a 6 h engagement table can't see: an old lean-No post, an echo, reads 0.72
    and an old strong one 0.65)."""
    s = getattr(config, "VALUE_STEP", 0) or 0
    return math.floor(ev / s + 1e-9) if s else ev


def pick_arm(t=None):
    """'value' or 'base': the pick order of this block. VALUE_PICK off: base. On: arm_pick's switchback block (base/value),
    frozen at ARMS_FREEZE to FREEZE_PIN["arm_pick"]; value everywhere when arm_pick is not in SWITCHBACK."""
    if not getattr(config, "VALUE_PICK", False):
        return "base"
    return experiment.block("arm_pick", t)[1] or "value"
