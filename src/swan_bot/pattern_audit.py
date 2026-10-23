"""Pattern audit (todo/38): how much our write log reads like a rota, measured from the log alone.

Pure functions, no I/O: scripts/pattern_audit.py reads logs/swan_actions.jsonl and the account records' metadata, calls
audit(), and writes data/pattern_audit.json for the dashboard's stealth tile. Read-only: it never touches the platform.

What it measures, per voice and for the pool, over a trailing window (default 24 h, plus an hourly series):
  timing       gap CV, gap entropy, share of gaps within +-10% of the modal gap (the "metronome" tell), longest awake
               stretch, hours active
  coordination pairwise correlation of per-minute write indicators, writes landing within 30 s of another voice's
               (against what independent voices would give), a citizen answered by two voices within 10 min, overlap of
               the voices' sleep windows
  registration gaps between account creations, clustering, delay from creation to first write
  identity     handle shapes (digit suffix, separators, length), display name vs handle
  volume       team writes/min against the 2.9 target, spread of writes/day across voices

SPECS below is the ONE table of thresholds (Marc: tune here). Each metric has four numbers on its own scale: ideal (score
100), green (score 70, the green/amber edge), red (score 35, the amber/red edge) and worst (score 0), between them the
score is linear. The pool's stealth_score is the weight-averaged score of the metrics that have data. Calibrated on
simulate_pool(): the old "longest rest first, 4 min gap" rota grades red, a mixed pool (log-normal gaps, sessions, sleep
windows) grades green (tests/test_pattern_audit.py).

No secrets pass through here: a voice is its public username (plus the persona key), nothing from the account records
except username, persona, role, owner, created, status, display_name and converted.at.
"""
import bisect
import collections
import datetime as dt
import math
import random
import re
import statistics
from zoneinfo import ZoneInfo

WRITE_ACTS = ("post", "reply", "reply_back", "second_voice", "journalist", "thread", "thread_answer", "repost")
TARGET_PER_MIN = 2.9               # the team write rate we plan for (10% under the 3/min limit)
CLOCK_TZ = "Australia/Sydney"      # the competition clock: when citizens are online, where sleep hours are read

# ---- what counts as enough data, and the knobs the metrics read ----
MIN_WRITES = 10                    # a voice needs this many writes in the window to be graded on its own
MIN_GAPS = 6                       # ... and this many in-session gaps for the gap metrics
MIN_VOICES = 3                     # pool figures from fewer graded voices are "grey" (no grade)
SESSION_GAP_S = 45 * 60            # a gap longer than this is a break, not part of the rhythm of a session
AWAKE_BREAK_S = 90 * 60            # a pause longer than this ends an awake stretch
SLEEP_MIN_S = 4 * 3600             # the longest silence counts as a sleep window from this long
MODAL_TOL = 0.10                   # "the same gap" means within +-10% of the modal gap
ENTROPY_BIN = 0.25                 # gap entropy: bins of 0.25 in log2(minutes), about x1.19 wide
NEAR_S = 30                        # a write "lands with" another voice's within this many seconds
MULTI_S = 10 * 60                  # one citizen answered by two of our voices within this long
CLUSTER_S = 10 * 60                # two account creations this close are one cluster
INSTANT_S = 10 * 60                # a first write this soon after creation is "instant"
REG_WINDOW_H = 96                  # registrations and first writes are read over this many hours
MAX_PAIR_VOICES = 80

GRADE_GREEN, GRADE_AMBER = 70, 45  # composite stealth_score bars: >= 70 green, >= 45 amber, below red
Spec = collections.namedtuple("Spec", "key label group better ideal green red worst weight unit fix")
SPECS = [
    # key                label                                   group         better   ideal green  red  worst weight unit   what to do
    Spec("gap_cv",       "Gap variation (CV, in-session)",       "timing",     "higher", 0.9, 0.5,  0.25, 0.05, 2.0, "",     "Gaps too even: the scheduler needs per-voice rhythm (lognormal gaps, bursts and breaks)."),
    Spec("gap_entropy",  "Gap entropy (bits)",                   "timing",     "higher", 4.0, 3.0,  2.2,  1.0,  1.0, " bits", "Few distinct gap lengths: widen the gap spread."),
    Spec("modal_gap",    "Gaps within +-10% of the modal gap",   "timing",     "lower",  0.10, 0.25, 0.45, 0.8, 2.0, "",     "A metronome: many writes at the same gap. Stop the fixed gap / longest-rest pick."),
    Spec("awake_h",      "Longest awake stretch (h)",            "timing",     "lower",  12,  18,   21,   24,   1.5, " h",   "Voices never sleep: give each a sleep window of 6-9 h."),
    Spec("hours_active", "Hours active of 24",                   "timing",     "lower",  13,  19,   22,   24,   1.5, " h",   "Voices write in nearly every hour of the day."),
    Spec("pair_corr",    "Voice pairs in lockstep (corr, p95)",  "coordination", "lower", 0.02, 0.08, 0.2, 0.5,  1.0, "",     "Pairs of voices write in the same minutes."),
    Spec("near_excess",  "Writes with a 2nd voice within 30 s (over chance)", "coordination", "lower", 0.0, 0.06, 0.12, 0.3, 0.5, "", "Voices bunch up: stagger starts."),
    Spec("multi_voice",  "Citizens answered by 2 voices in 10 min", "coordination", "lower", 0.0, 0.05, 0.15, 0.40, 1.5, "", "Same-citizen pile-ons: ONE_VOICE_PER_CITIZEN, long second-voice delays."),
    Spec("sleep_overlap", "Sleep windows that coincide (Jaccard)", "coordination", "lower", 0.2, 0.6, 0.85, 1.0, 1.0, "",    "Everyone sleeps at the same hours: spread the start hours."),
    Spec("reg_gap_cv",   "Registration spacing (CV of gaps)",    "registration", "higher", 1.0, 0.6, 0.3, 0.05, 1.0, "",    "Registrations on a timer: random, heavy-tailed delays."),
    Spec("reg_cluster",  "Registrations within 10 min of another", "registration", "lower", 0.05, 0.25, 0.5, 1.0, 1.0, "",   "Registrations (or conversions) come in batches."),
    Spec("instant_write", "New accounts writing within 10 min",  "registration", "lower",  0.0, 0.2,  0.6,  1.0,  1.5, "",    "New accounts write at once: warm them up (views, likes) for hours first."),
    Spec("handle_shape", "Most common handle shape",             "identity",   "lower",  0.2, 0.4,  0.65, 1.0,  1.0, "",     "Handles share one shape: vary the shapes."),
    Spec("handle_2digit", "Handles ending in two digits",        "identity",   "lower",  0.2, 0.5,  0.75, 1.0,  1.0, "",     "A two-digit suffix is the stock bot handle."),
    Spec("team_rate",    "Team writes/min vs the 2.9 target",    "volume",     "higher", 1.0, 0.85, 0.6,  0.0,  1.0, "",     "Under the planned rate: volume is being lost."),
    Spec("voice_spread", "Writes per voice per day (CV across voices)", "volume", "higher", 0.5, 0.3, 0.15, 0.0, 1.0, "",   "Every voice writes the same daily total: give each its own volume."),
]
SPEC = {s.key: s for s in SPECS}
VOICE_KEYS = ("gap_cv", "gap_entropy", "modal_gap", "awake_h", "hours_active")     # the metrics a single voice is graded on


# ---- grading ----
def _x(spec, v):
    return v if spec.better == "lower" else -v


def grade_of(spec, v):
    """green / amber / red for a value, or grey when there is none."""
    if v is None:
        return "grey"
    x = _x(spec, v)
    return "green" if x <= _x(spec, spec.green) else "amber" if x <= _x(spec, spec.red) else "red"


def score_of(spec, v):
    """0-100, linear between ideal (100), green (70), red (35) and worst (0); None without a value."""
    if v is None:
        return None
    pts = [(_x(spec, p), s) for p, s in ((spec.ideal, 100), (spec.green, 70), (spec.red, 35), (spec.worst, 0))]
    x = _x(spec, v)
    if x <= pts[0][0]:
        return 100.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0) if x1 != x0 else y1
    return 0.0


def composite(values, keys=None):
    """Weight-averaged score of the metrics that have data, as (score 0-100 or None, grade). A red metric keeps the
    overall grade from being green; fewer than 4 metrics with data is grey."""
    parts = [(SPEC[k].weight, score_of(SPEC[k], v)) for k, v in values.items() if (keys is None or k in keys) and v is not None]
    if len(parts) < (4 if keys is None else 2):
        return None, "grey"
    score = sum(w * s for w, s in parts) / sum(w for w, _ in parts)
    grade = "green" if score >= GRADE_GREEN else "amber" if score >= GRADE_AMBER else "red"
    if grade == "green" and any(grade_of(SPEC[k], v) == "red" for k, v in values.items() if (keys is None or k in keys)):
        grade = "amber"
    return round(score), grade


# ---- reading rows ----
def parse_ts(s):
    """Epoch seconds from an ISO string (or a number), else None."""
    if isinstance(s, (int, float)):
        return float(s)
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def write_events(rows):
    """Live writes as (t, voice, persona, citizen) sorted by time. citizen is the target author id (else the target
    post) for writes to a citizen, else None."""
    out = []
    for a in rows:
        if a.get("act") not in WRITE_ACTS or a.get("live") is not True:
            continue
        user = a.get("username")
        t = parse_ts(a.get("ts"))
        if not user or t is None or str(user).startswith("("):
            continue
        cit = a.get("target_author") if a.get("target_author") is not None else a.get("target_post")
        out.append((t, str(user), a.get("persona"), cit))
    out.sort(key=lambda e: e[0])
    return out


def _median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def _pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * p
    lo = int(math.floor(k))
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


# ---- per-voice timing ----
def gap_stats(gaps):
    """cv, entropy (bits) and modal share of a list of in-session gaps in seconds, or Nones for too few."""
    if len(gaps) < MIN_GAPS:
        return None, None, None
    mean = sum(gaps) / len(gaps)
    cv = math.sqrt(sum((g - mean) ** 2 for g in gaps) / len(gaps)) / mean if mean else None
    bins = collections.Counter(int(math.floor(math.log2(max(g, 1) / 60) / ENTROPY_BIN)) for g in gaps)
    ent = -sum(c / len(gaps) * math.log2(c / len(gaps)) for c in bins.values())
    s = sorted(gaps)
    best = 0
    for g in s:
        lo, hi = bisect.bisect_left(s, g * (1 - MODAL_TOL)), bisect.bisect_right(s, g * (1 + MODAL_TOL))
        best = max(best, hi - lo)
    return cv, ent, best / len(gaps)


def awake_stretch_s(times):
    """The longest run of writes with no pause over AWAKE_BREAK_S, as its length in seconds."""
    best = start = 0.0
    prev = None
    for t in times:
        if prev is None or t - prev > AWAKE_BREAK_S:
            start = t
        best = max(best, t - start)
        prev = t
    return best


def clock_hours(t0, t1):
    """The set of clock hours (Sydney, 0-23) whose middle falls in [t0, t1]."""
    tz = ZoneInfo(CLOCK_TZ)
    out, t = set(), (t0 // 3600) * 3600 + 1800
    while t <= t1:
        if t >= t0:
            out.add(dt.datetime.fromtimestamp(t, tz).hour)
        t += 3600
    return out


def sleep_hours(times, start, end):
    """Clock hours of the voice's longest silence in [start, end] if it is a sleep (>= SLEEP_MIN_S), else an empty set."""
    edges = [start] + list(times) + [end]
    a, b = max(zip(edges, edges[1:]), key=lambda p: p[1] - p[0])
    return clock_hours(a, b) if b - a >= SLEEP_MIN_S else set()


def voice_stats(times, start, end):
    """One voice's figures from its sorted write times inside [start, end]."""
    gaps = [b - a for a, b in zip(times, times[1:])]
    cv, ent, modal = gap_stats([g for g in gaps if g <= SESSION_GAP_S])
    full_day = end - start >= 23 * 3600
    buckets = {int((t - start) // 3600) for t in times}
    return dict(n=len(times), gap_cv=cv, gap_entropy=ent, modal_gap=modal,
                awake_h=awake_stretch_s(times) / 3600 if full_day else None,
                hours_active=len(buckets) if full_day else None,
                sleep=sleep_hours(times, start, end) if full_day else set())


# ---- pool figures ----
def pair_corr(minute_sets, n_min):
    """Pairwise Pearson correlations of per-minute write indicators (each voice is a set of minute numbers)."""
    names = sorted(minute_sets)[:MAX_PAIR_VOICES]
    out = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            x, y = minute_sets[a], minute_sets[b]
            va, vb = len(x) * (n_min - len(x)), len(y) * (n_min - len(y))
            if va and vb:
                out.append((n_min * len(x & y) - len(x) * len(y)) / math.sqrt(va * vb))
    return out


def near_write(events, window_s=NEAR_S):
    """(share of writes with another voice's write within +-30 s, share expected if voices wrote independently at the
    same hourly team rate). Independent-chance, not zero: at 2.9 writes a minute nearly every write has a neighbour."""
    if len(events) < 2:
        return None, None
    ts = [e[0] for e in events]
    hit = 0
    for i, (t, v, _, _) in enumerate(events):
        lo, hi = bisect.bisect_left(ts, t - window_s), bisect.bisect_right(ts, t + window_s)
        hit += any(events[j][1] != v for j in range(lo, hi) if j != i)
    per_hour = collections.Counter(int(t // 3600) for t in ts)
    exp = sum(1 - math.exp(-2 * window_s * (per_hour[int(t // 3600)] - 1) / 3600) for t in ts) / len(ts)
    return hit / len(events), exp


def multi_voice(events):
    """Share of citizens (with a write in the window) that two different voices wrote to within MULTI_S, and how many."""
    by = collections.defaultdict(list)
    for t, v, _, c in events:
        if c is not None:
            by[c].append((t, v))
    hits = 0
    for lst in by.values():
        lst.sort()
        hits += any(b[1] != a[1] and b[0] - a[0] <= MULTI_S for a, b in zip(lst, lst[1:]))
    return (hits / len(by) if len(by) >= 20 else None), len(by), hits


def jaccard_mean(sets):
    sets = [s for s in sets if s]
    if len(sets) < 2:
        return None
    vals = [len(a & b) / len(a | b) for i, a in enumerate(sets) for b in sets[i + 1:]]
    return sum(vals) / len(vals)


# ---- identity ----
def handle_shape(h):
    """'marcotaufa' -> 'a', 'lucy.pulu' -> 'a.a', 'vika_i92' -> 'a_aN2', 'kai_nakamura_dev76' -> 'a_a_aN2'."""
    return re.sub(r"\d+", lambda m: f"N{len(m.group())}", re.sub(r"[A-Za-z]+", "a", str(h)))


def name_derived(handle, display):
    """True when the handle holds the display name's first or last name (3+ letters), None without a display name."""
    toks = [t for t in re.findall(r"[a-z]+", str(display or "").lower()) if len(t) >= 3]
    if not toks:
        return None
    h = re.sub(r"[^a-z]", "", str(handle).lower())
    return any(t in h for t in (toks[0], toks[-1]))


def identity_stats(handles, displays):
    """Histograms and shares over the handles: shapes, digit suffix length, separators, length, name derivability."""
    n = len(handles)
    if n < MIN_VOICES:
        return dict(n=n)
    shapes = collections.Counter(handle_shape(h) for h in handles)
    suffix = collections.Counter(len(m.group(1)) if (m := re.search(r"(\d+)$", h)) else 0 for h in handles)
    seps = collections.Counter(sorted({c for c in h if not c.isalnum()}).__str__() if any(not c.isalnum() for c in h) else "none" for h in handles)
    lens = [len(h) for h in handles]
    derived = [d for d in (name_derived(h, displays.get(h)) for h in handles) if d is not None]
    return dict(n=n, shapes=dict(shapes.most_common(8)), top_shape_share=shapes.most_common(1)[0][1] / n,
                suffix_digits={str(k): v for k, v in sorted(suffix.items())}, two_digit_share=suffix[2] / n,
                separators=dict(seps), length_mean=sum(lens) / n, length_sd=statistics.pstdev(lens),
                name_derived_share=sum(derived) / len(derived) if derived else None)


# ---- registration ----
def registration_stats(created, convert_ts, first_write, now, window_h=REG_WINDOW_H):
    """created: {username: epoch}, convert_ts: [epoch], first_write: {username: epoch}. Spacing and clustering of the
    account creations and conversions inside the window, and how soon the new accounts first wrote."""
    lo = now - window_h * 3600
    events = sorted([t for t in created.values() if lo <= t <= now] + [t for t in convert_ts if lo <= t <= now])
    gaps = [b - a for a, b in zip(events, events[1:])]
    cv = None
    if len(gaps) >= 4 and (m := sum(gaps) / len(gaps)):
        cv = math.sqrt(sum((g - m) ** 2 for g in gaps) / len(gaps)) / m
    cluster = None
    if len(events) >= 5:
        near = sum(1 for i, t in enumerate(events) if (i and t - events[i - 1] <= CLUSTER_S) or (i + 1 < len(events) and events[i + 1] - t <= CLUSTER_S))
        cluster = near / len(events)
    delays = sorted((first_write[u] - c) / 60 for u, c in created.items() if lo <= c <= now and u in first_write and first_write[u] >= c - 60)
    instant = sum(d * 60 <= INSTANT_S for d in delays) / len(delays) if len(delays) >= 4 else None
    return dict(n_events=len(events), reg_gap_cv=cv, reg_cluster=cluster, instant_write=instant, n_first_writes=len(delays),
                median_first_write_min=statistics.median(delays) if delays else None,
                median_gap_min=statistics.median(gaps) / 60 if gaps else None)


# ---- the audit ----
def _round(v, k=3):
    return None if v is None else round(v, k)


def audit(rows, accounts, now, window_h=24.0):
    """The audit of the log rows (dicts as logs/swan_actions.jsonl holds them) and the account records' metadata
    (dicts with at least username; created / persona / role / status / display_name when known), as of epoch `now`.
    Returns a JSON-able dict; rows older than the window are used only for first writes and registrations."""
    rows = list(rows)
    all_events = write_events(rows)
    start = now - window_h * 3600
    events = [e for e in all_events if start <= e[0] <= now]
    by_voice = collections.defaultdict(list)
    persona_of = {}
    for t, v, p, _ in events:
        by_voice[v].append(t)
        persona_of[v] = p
    graded = {v: voice_stats(ts, start, now) for v, ts in by_voice.items() if len(ts) >= MIN_WRITES}
    values = {}
    for k in ("gap_cv", "gap_entropy", "modal_gap", "awake_h", "hours_active"):
        xs = [s[k] for s in graded.values() if s[k] is not None]
        values[k] = _median(xs) if len(xs) >= MIN_VOICES else None
    # coordination
    minutes = {v: {int((t - start) // 60) for t in ts} for v, ts in by_voice.items() if len(ts) >= MIN_WRITES}
    corr = pair_corr(minutes, max(int(window_h * 60), 1)) if len(minutes) >= MIN_VOICES else []
    values["pair_corr"] = _pct(corr, 0.95) if corr else None
    near, exp = near_write(events)
    values["near_excess"] = max(near - exp, 0.0) if near is not None and len(by_voice) >= MIN_VOICES else None
    values["multi_voice"], n_cit, n_multi = multi_voice(events)
    values["sleep_overlap"] = jaccard_mean([s["sleep"] for s in graded.values()]) if window_h >= 23 else None
    # registration
    created, convert_ts, displays, status, role = {}, [], {}, {}, {}
    for a in accounts:
        u = a.get("username")
        if not u:
            continue
        c = parse_ts(a.get("created"))
        if c is not None:
            created[u] = c
        if a.get("display_name"):
            displays[u] = a["display_name"]
        status[u], role[u] = a.get("status"), a.get("role")
        conv = a.get("converted")
        if isinstance(conv, dict) and parse_ts(conv.get("at")) is not None:
            convert_ts.append(parse_ts(conv["at"]))
    seen_convert = set(convert_ts)
    for a in rows:
        t = parse_ts(a.get("ts"))
        if t is None or not a.get("username"):
            continue
        if a.get("act") == "register":
            created.setdefault(a["username"], t)
            if a.get("role"):
                role.setdefault(a["username"], a["role"])
        elif a.get("act") == "convert" and t not in seen_convert:
            convert_ts.append(t)
            seen_convert.add(t)
    first = {}
    for t, v, _, _ in all_events:
        first.setdefault(v, t)
    reg = registration_stats(created, convert_ts, first, now)
    values["reg_gap_cv"], values["reg_cluster"], values["instant_write"] = reg["reg_gap_cv"], reg["reg_cluster"], reg["instant_write"]
    # identity: voices that wrote in the window, and the active voices on record
    handles = sorted(set(by_voice) | {u for u, s in status.items() if s == "active" and role.get(u) not in ("booster",) and u in created})
    ident = identity_stats(handles, displays)
    values["handle_shape"], values["handle_2digit"] = ident.get("top_shape_share"), ident.get("two_digit_share")
    # volume
    rate = len(events) / (window_h * 60)
    values["team_rate"] = rate / TARGET_PER_MIN if events or all_events else None
    counts = [len(ts) for ts in by_voice.values() if len(ts) >= MIN_WRITES]
    values["voice_spread"] = (statistics.pstdev(counts) / (sum(counts) / len(counts))
                              if len(counts) >= MIN_VOICES and window_h >= 23 else None)
    # grades
    metrics = {}
    for s in SPECS:
        v = values.get(s.key)
        metrics[s.key] = dict(label=s.label, group=s.group, value=_round(v), grade=grade_of(s, v), score=_round(score_of(s, v), 1),
                              weight=s.weight, thresholds=dict(better=s.better, ideal=s.ideal, green=s.green, red=s.red, worst=s.worst), fix=s.fix)
    score, grade = composite(values)
    worst_metrics = [k for k, m in sorted(((k, m) for k, m in metrics.items() if m["score"] is not None),
                                          key=lambda km: (km[1]["score"], -km[1]["weight"]))[:3] if metrics[k]["grade"] != "green"]
    # voices
    voices = {}
    for v, st in graded.items():
        vals = {k: st[k] for k in VOICE_KEYS}
        sc, gr = composite(vals, keys=VOICE_KEYS)
        bad = [SPEC[k].label for k in VOICE_KEYS if grade_of(SPEC[k], vals[k]) == "red"] or \
              [SPEC[k].label for k in VOICE_KEYS if grade_of(SPEC[k], vals[k]) == "amber"]
        voices[v] = dict(persona=persona_of.get(v), writes=st["n"], score=sc, grade=gr, why=bad,
                         **{k: _round(vals[k]) for k in VOICE_KEYS})
    offenders = [dict(voice=v, persona=d["persona"], score=d["score"], writes=d["writes"], why=d["why"])
                 for v, d in sorted(voices.items(), key=lambda kv: (kv[1]["score"] if kv[1]["score"] is not None else 101, -kv[1]["writes"]))
                 if d["score"] is not None][:3]
    # hourly series (the last min(window, 48) hours)
    modal = {}
    for v, ts in by_voice.items():
        g = sorted(b - a for a, b in zip(ts, ts[1:]) if b - a <= SESSION_GAP_S)
        if len(g) >= MIN_GAPS:
            modal[v] = max(g, key=lambda x: bisect.bisect_right(g, x * (1 + MODAL_TOL)) - bisect.bisect_left(g, x * (1 - MODAL_TOL)))
    hourly = []
    nh = int(min(window_h, 48))
    for h in range(nh):
        h0 = now - (nh - h) * 3600
        evs = [e for e in all_events if h0 <= e[0] < h0 + 3600]
        gaps = near_ = 0
        last = {}
        for t, v, _, _ in evs:
            if v in last and v in modal and (t - last[v]) <= SESSION_GAP_S:
                gaps += 1
                near_ += abs(t - last[v] - modal[v]) <= MODAL_TOL * modal[v]
            last[v] = t
        hourly.append(dict(hour=dt.datetime.fromtimestamp(h0, dt.timezone.utc).strftime("%Y-%m-%dT%H:00Z"), writes=len(evs),
                           voices=len({e[1] for e in evs}), per_min=_round(len(evs) / 60, 2),
                           modal_gap=_round(near_ / gaps, 2) if gaps >= 10 else None))
    return dict(ts=dt.datetime.fromtimestamp(now, dt.timezone.utc).isoformat(timespec="seconds"), window_h=window_h,
                writes=len(events), voices_writing=len(by_voice), voices_graded=len(graded), per_min=_round(rate, 2),
                target_per_min=TARGET_PER_MIN, stealth_score=score, grade=grade, metrics=metrics,
                worst_metrics=worst_metrics, worst_voices=offenders, voices=voices, hourly=hourly,
                registration={k: _round(v) for k, v in reg.items()}, identity=ident,
                citizens=dict(written_to=n_cit, multi_voice=n_multi))


def table(report):
    """A short plain-text table of the audit for the CLI."""
    lines = [f"stealth_score {report['stealth_score']} ({report['grade']}) · {report['writes']} writes in {report['window_h']:g} h · "
             f"{report['per_min']}/min · {report['voices_graded']} of {report['voices_writing']} voices graded"]
    for k, m in report["metrics"].items():
        v = "—" if m["value"] is None else f"{m['value']:g}"
        lines.append(f"  {m['grade']:<6} {m['label']:<52} {v:>8}  (green {m['thresholds']['green']:g}, red {m['thresholds']['red']:g})")
    if report["worst_voices"]:
        lines.append("  worst voices: " + ", ".join(f"{o['voice']} ({o['score']})" for o in report["worst_voices"]))
    return "\n".join(lines)


# ---- simulation: the audit's own test fixture, not the real scheduler ----
SIM_T0 = dt.datetime(2026, 10, 20, tzinfo=dt.timezone.utc).timestamp()
SIM_WORDS = ["sam", "lani", "kai", "mele", "tom", "ana", "liam", "ivy", "noah", "ella", "jess", "ben", "rua", "sione", "tess", "owen",
             "nadia", "dan", "priya", "leo", "wally", "isla", "maya", "jack", "zoe", "finn", "hana", "ned", "pia", "ross"]
SIM_LAST = ["taufa", "reid", "park", "nguyen", "bakes", "rao", "latu", "fifita", "walker", "coaches", "garden", "pulu", "ukulele", "leota"]
SIM_SHAPES = ["{a}", "{a}_{b}", "{a}.{b}", "{a}{d2}", "{a}_{b}{d2}", "{a}{d4}", "{a}_{d2}", "{a}{b}", "{a}_{c}"]


def _handle(rng, i, scheduler):
    a, b = SIM_WORDS[i % len(SIM_WORDS)], rng.choice(SIM_LAST)
    shape = "{a}_{b}{d2}" if scheduler == "old" else rng.choice(SIM_SHAPES)
    return shape.format(a=a, b=b, c=rng.choice(["reads", "m", "t", "cafe"]), d2=f"{rng.randrange(10, 99)}", d4=f"{rng.randrange(1970, 2005)}") + (str(i) if i >= len(SIM_WORDS) else "")


def _sim_row(t, user, persona, rng, citizens, recent):
    r = rng.random()
    act = "post" if r < 0.05 else "repost" if r < 0.08 else "reply"
    row = dict(ts=dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat(), act=act, live=True, username=user, persona=persona)
    if act != "post" and act != "repost":
        row["target_author"] = rng.randrange(citizens)
        row["target_post"] = rng.randrange(10 ** 6)
    return row


def simulate_pool(n_voices=30, hours=48, seed=1, scheduler="mixed"):
    """Synthetic write logs for the audit's tests. scheduler "old": the longest-rest pick with a fixed 4 min gap, one slot
    every 60/2.9 s, no sleep, registrations on a 20-40 min timer, new accounts writing at once, one handle shape, second
    voices on the same citizen straight away. "mixed": per-voice log-normal gaps in sessions, sleep windows, volume
    multipliers, staggered warm-up, varied handles, rare long-delay second voices; the team limit (3 in any 60 s) keeps it
    honest. Returns (rows, accounts, now): rows as the action log holds them, accounts as the records' metadata."""
    rng = random.Random(seed)
    end = SIM_T0 + hours * 3600
    users = [_handle(rng, i, scheduler) for i in range(n_voices)]
    personas = [f"p{i}" for i in range(n_voices)]
    rows, citizens = [], 2500
    if scheduler == "old":
        created, c = [], SIM_T0
        for _ in range(n_voices):
            created.append(c)
            c += rng.uniform(20, 40) * 60
        last = {}
        t, step = SIM_T0, 60 / TARGET_PER_MIN
        prev_cit = None
        while t < end:
            ready = [i for i in range(n_voices) if created[i] <= t and t - last.get(i, -1e9) >= 240]
            if ready:
                i = min(ready, key=lambda j: last.get(j, -1e9))
                row = _sim_row(t, users[i], personas[i], rng, citizens, None)
                if prev_cit is not None and rng.random() < 0.10 and "target_author" in row:
                    row["target_author"] = prev_cit
                prev_cit = row.get("target_author")
                rows.append(row)
                last[i] = t
            t += step + rng.uniform(-0.5, 0.5)
    elif scheduler == "mixed":
        span = 5 * n_voices * 3600                              # registrations over the days before the window: heavy-tailed gaps, median ~5 h
        draws = [rng.lognormvariate(0, 0.9) for _ in range(n_voices)]
        created, acc = [], 0.0
        for d in draws:
            created.append(SIM_T0 - span + acc)
            acc += d / sum(draws) * span
        awake = 1 - 7.5 / 24
        gen_rate = 3.1                                          # per min across the pool, before the team limit
        events = []
        for i in range(n_voices):
            mult = rng.lognormvariate(0, 0.35)
            gmean = n_voices * awake / gen_rate * mult * 60
            sleep_start, sleep_len = rng.uniform(21, 28), rng.uniform(6, 9)
            t = created[i] + rng.uniform(6, 36) * 3600           # warm-up (views and likes only) before the first write
            while t < end:
                local = ((t - SIM_T0) / 3600 + 10 - sleep_start) % 24      # clock hours since the sleep started (Sydney = UTC+10)
                if local < sleep_len:
                    t += (sleep_len - local) * 3600 + rng.uniform(0, 1800)
                    continue
                k = rng.choice([1, 1, 2, 2, 3, 4])
                for _ in range(k):
                    events.append((t, i))
                    t += max(rng.lognormvariate(math.log(150), 0.6), 30)
                intra = 150 * math.exp(0.18) * (k - 1)
                t += max(rng.lognormvariate(math.log(max(gmean * k - intra, 90)) - 0.4, 0.9), 60)
        events.sort()
        recent = []
        win = collections.deque(maxlen=3)
        for t, i in events:
            if len(win) == 3 and t - win[0] < 60:
                t = win[0] + 60 + rng.uniform(0, 3)
            if t >= end:
                break
            win.append(t)
            row = _sim_row(t, users[i], personas[i], rng, citizens, recent)
            if "target_author" in row and recent and rng.random() < 0.02:
                old = [r for r in recent if t - r[0] > 1800]
                if old:
                    row["target_author"] = rng.choice(old)[1]
            if "target_author" in row:
                recent.append((t, row["target_author"]))
                recent = recent[-400:]
            rows.append(row)
    else:
        raise ValueError(f"unknown scheduler {scheduler!r}")
    rows.sort(key=lambda r: r["ts"])
    accounts = [dict(username=users[i], persona=personas[i], role="voice", status="active", owner="sim",
                     created=dt.datetime.fromtimestamp(created[i], dt.timezone.utc).isoformat()) for i in range(n_voices)]
    return rows, accounts, end
