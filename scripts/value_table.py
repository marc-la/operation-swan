#!/usr/bin/env python3
"""Read-only: the expected-points table for the value pick (todo/49, 27 Oct 2026), and the offline replay that checks it.

    python scripts/value_table.py build                     # last 72 h of replies with a 6.5 h outcome -> data/value_table.json
    python scripts/value_table.py build --hours 48 --dry    # print the table, write nothing
    python scripts/value_table.py replay --hours 48         # the queue of the last 48 h, picked the base way and the value way

build reads logs/swan_actions.jsonl and logs/swan_outcomes.jsonl (or --actions / --outcomes copies), streamed line by line,
and writes only --out. The bot reads that file when it is valid (swan_bot/value.py) and falls back to value.DEFAULT.
replay also reads the targeter's funnel and queue in data/swan_state.json (--state): every citizen item of the last ~84 h
with when we found it and what became of it, the classes of the ones still queued; the written ones carry their class in the
log. Neither command makes a platform call. See value.py for the method; todo/49 for why.
"""
import argparse
import collections
import datetime as dt
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from swan_bot import config, jsonl, value  # noqa: E402

EDGES = (0, 1, 2, 3, 5, 10, 20, 60, 240, float("inf"))       # minutes at landing; fine where the curve is steep
MIN_N = 40                                                  # a thinner cell takes its group's mean
BANDS = ((0, 2, "<2m"), (2, 5, "2-5m"), (5, 20, "5-20m"), (20, 240, "20m-4h"), (240, float("inf"), ">4h"))


def points(o):
    """Proxy points of one write at its outcome check: citizen replies x15 + citizen likes x5."""
    return 15 * (o.get("citizen_replies") or 0) + 5 * (o.get("citizen_likes") or 0)


def bin_of(minutes):
    return next(i for i in range(len(EDGES) - 1) if minutes < EDGES[i + 1])


def pava(vals, weights):
    """Weighted pool-adjacent-violators: the closest non-increasing sequence."""
    blocks = []                                             # [value, weight, count]
    for v, w in zip(vals, weights):
        blocks.append([v, w, 1])
        while len(blocks) > 1 and blocks[-1][0] > blocks[-2][0]:
            v2, w2, n2 = blocks.pop()
            v1, w1, n1 = blocks.pop()
            blocks.append([(v1 * w1 + v2 * w2) / (w1 + w2), w1 + w2, n1 + n2])
    return [v for v, _, n in blocks for _ in range(n)]


def fit(rows, min_n=MIN_N, rounds=30):
    """rows: [{group, minutes, hour, points}]. Points = hour effect + (group, age bin) cell, by backfitting; cells under
    min_n take the group's mean; each curve is then non-increasing (pava). -> {"curves": {group: [[minutes, pts]...]},
    "n": {group: [n per knot]}, "raw": {group: [raw mean per knot]}}."""
    for r in rows:
        r["b"] = bin_of(r["minutes"])
    hour, cell = collections.defaultdict(float), collections.defaultdict(float)
    for _ in range(rounds):
        acc = collections.defaultdict(list)
        for r in rows:
            acc[(r["group"], r["b"])].append(r["points"] - hour[r["hour"]])
        cell = {k: sum(v) / len(v) for k, v in acc.items()}
        acc = collections.defaultdict(list)
        for r in rows:
            acc[r["hour"]].append(r["points"] - cell[(r["group"], r["b"])])
        hour = collections.defaultdict(float, {k: sum(v) / len(v) for k, v in acc.items()})
    level = sum(hour[r["hour"]] for r in rows) / len(rows) if rows else 0.0
    out = {"curves": {}, "n": {}, "raw": {}}
    for g in sorted({r["group"] for r in rows}):
        mine = [r for r in rows if r["group"] == g]
        n = collections.Counter(r["b"] for r in mine)
        bins = sorted(n)
        mean = sum(r["points"] - hour[r["hour"]] for r in mine) / len(mine) + level
        vals = [cell[(g, b)] + level if n[b] >= min_n else mean for b in bins]
        ages = [sum(r["minutes"] for r in mine if r["b"] == b) / n[b] for b in bins]
        out["curves"][g] = [[round(a, 2), round(v, 3)] for a, v in zip(ages, pava(vals, [n[b] for b in bins]))]
        out["n"][g] = [n[b] for b in bins]
        out["raw"][g] = [round(sum(r["points"] for r in mine if r["b"] == b) / n[b], 2) for b in bins]
    return out


def ts(iso):
    """Unix seconds of an ISO time; one without a zone is UTC."""
    t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)).timestamp()


def read_writes(path):
    """Live first replies (act reply) and reply-backs with their stage times, trimmed to what the table and replay need."""
    keep = ("ts", "act", "post_id", "target_post", "target_author", "target_class", "net", "t_made", "t_pick", "t_sent",
            "priority", "engaged", "queue_arm")
    for r in jsonl.Reader(path, contains='"act": "reply'):
        if r.get("act") in ("reply", "reply_back") and r.get("live") and r.get("post_id"):
            yield {k: r.get(k) for k in keep}


def read_outcomes(path):
    """post_id -> its last outcome check (check 1 = 6 h after the write, OUTCOME_AT_S)."""
    out = {}
    for r in jsonl.Reader(path, contains='"outcome"'):
        if r.get("act") == "outcome" and "error" not in r and r.get("check") == 1:
            out[r["post_id"]] = r
    return out


def ordinary(w):
    """A write the ordinary tier handed out: a first reply, no group but turnout (lean No, TURNOUT_ARM)."""
    return w["act"] == "reply" and w.get("net") in (None, "turnout")


def build_rows(writes, outcomes, start, end):
    rows = []
    for w in writes:
        o = outcomes.get(w["post_id"])
        if not (o and w.get("t_made") and w.get("t_sent") and start <= w["t_sent"] < end):
            continue
        if not (ordinary(w) or w["act"] == "reply_back"):
            continue
        rows.append(dict(group="reply_back" if w["act"] == "reply_back" else value.group_of(w.get("target_class")),
                         minutes=max(0.0, (w["t_sent"] - w["t_made"]) / 60), points=points(o),
                         hour=int(w["t_sent"] // 3600)))   # each clock hour its own level: time of day, crowding, drift
    return rows


def show(table):
    for g, knots in table["curves"].items():
        raw = table.get("raw", {}).get(g, [None] * len(knots))
        print(f"{g:10s} " + " | ".join(f"{a:g}m {p:.2f} (raw {r}, n{n})" for (a, p), r, n in zip(knots, raw, table["n"][g])))


def cmd_build(a):
    writes = list(read_writes(a.actions))
    outcomes = read_outcomes(a.outcomes)
    done = [w["t_sent"] for w in writes if w["post_id"] in outcomes and w.get("t_sent")]
    end = ts(a.end) if a.end else max(done) + 1
    start = end - a.hours * 3600
    rows = build_rows(writes, outcomes, start, end)
    table = fit(rows)
    fmt = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M")      # noqa: E731
    table.update(built=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M"), window=[fmt(start), fmt(end)],
                 writes=len(rows), points="15 x citizen replies + 5 x citizen likes at the 6 h outcome check")
    show(table)
    if not value.valid(table):
        raise SystemExit("not a valid table (a group missing?): nothing written")
    if not a.dry:
        pathlib.Path(a.out).write_text(json.dumps(table, indent=1))
        print(f"wrote {a.out} ({len(rows)} writes, {table['window'][0]} - {table['window'][1]} UTC)")


# ---- replay -------------------------------------------------------------------------------------------------------
def band(minutes):
    return next(lbl for lo, hi, lbl in BANDS if lo <= minutes < hi)


def pool_from(writes, items, candidates):
    """The ordinary queue's entries: every first reply's target (class, found, picked at) and every candidate still queued
    (class, found). items: the targeter's funnel {post_id: {c, f, o, why, a}}; candidates: its queue."""
    pool = {}
    for w in writes:
        if not ordinary(w) or not w.get("t_made") or not w.get("t_pick"):
            continue
        it = items.get(str(w["target_post"])) or {}
        fresh = (w["t_pick"] - w["t_made"]) / 60 < config.FRESH_MIN
        pool[w["target_post"]] = dict(pid=w["target_post"], author=w["target_author"], cls=w.get("target_class"),
                                      made=w["t_made"], found=it.get("f", w["t_made"] + config.REFRESH_S),
                                      score=(w.get("priority") or 0) - (config.FRESH_BONUS if fresh else 0), picked=w["t_pick"],
                                      lag=w["t_sent"] - w["t_pick"])
    for c in candidates:
        post = c.get("post") or c
        pid = post["post_id"]
        it = items.get(str(pid)) or {}
        if pid in pool or c.get("net") not in (None, "turnout") or it.get("why") not in ("queued", "no_voice", "held"):
            continue
        made = value.created_ts(post)
        if made is None:
            continue
        pool[pid] = dict(pid=pid, author=post.get("author_id"), cls=c.get("target_class"), made=made,
                         found=it.get("f", made + config.REFRESH_S), score=c.get("score") or 0, picked=None, lag=None)
    return sorted(pool.values(), key=lambda e: e["found"])


def base_key(e, t, last):
    """Today's order inside the ordinary tier (shallow blocks): the 1-6 h recontact gap last, the newest post under FRESH_MIN
    first with the weak classes DOWNRANK_MIN older, then the priority (score + the fresh bonus)."""
    age = (t - e["made"]) / 60
    late = config.DOWNRANK_MIN if e["cls"] in config.DOWNRANK_CLASSES else 0.0
    prio = e["score"] + (config.FRESH_BONUS if age < config.FRESH_MIN else 0.0)
    return (gap(e, t, last), min(age + late, config.FRESH_MIN), -prio)


def value_key(e, t, last, tab):
    """The value block's order, as next_target has it: the recontact gap last, expected points at VALUE_LAG_S in VALUE_STEP
    steps, then today's order."""
    g, *rest = base_key(e, t, last)
    return (g, -value.step(ev(e, t, config.VALUE_LAG_S, tab)), *rest)


def gap(e, t, last):
    g = getattr(config, "RECONTACT_GAP_S", None)
    seen = last.get(e["author"])
    return 1 if g and seen and g[0] <= t - seen < g[1] else 0


def ev(e, t, lag, tab):
    return value.curve(tab["curves"][value.group_of(e["cls"])], (t - e["made"]) / 60 + lag / 60)


def simulate(pool, slots, policy, tab, onestep=False):
    """Hand out one entry per slot (t, lag, the real pick's author) by policy ("base", "value"). Firm Yes at most
    FIRM_YES_PER_H an hour; posts past TARGET_MAX_AGE_H leave the tier; the 1-6 h recontact gap counts our picks. No session
    limit: it counts voices, and since todo/31 one voice answers a citizen all day (62% of real picks went to a citizen we
    wrote to under an hour before). onestep: the queue as it really was (each entry leaves at its real pick, the real picks
    set the recontact gap), so each slot is a choice from the real queue."""
    picks, i, active, taken, last, firm = [], 0, [], set(), {}, []
    prev = None                                       # onestep: the previous slot's real pick, (t, author)
    for t, lag, real_author in slots:
        if onestep and prev and prev[1] is not None:
            last[prev[1]] = prev[0]
        prev = (t, real_author)
        while i < len(pool) and pool[i]["found"] <= t:
            active.append(pool[i])
            i += 1
        if onestep:
            active = [e for e in active if e["picked"] is None or e["picked"] >= t]
        active = [e for e in active if e["pid"] not in taken and t - e["made"] < config.TARGET_MAX_AGE_H * 3600]
        firm = [x for x in firm if t - x < 3600]
        best, bk = None, None
        for e in active:
            if e["cls"] == "firm_yes" and len(firm) >= config.FIRM_YES_PER_H:
                continue
            k = base_key(e, t, last) if policy == "base" else value_key(e, t, last, tab)
            if bk is None or k < bk:
                best, bk = e, k
        if best is None:
            picks.append(None)
            continue
        if not onestep:
            taken.add(best["pid"])
            last[best["author"]] = t
        if best["cls"] == "firm_yes":
            firm.append(t)
        picks.append(dict(pid=best["pid"], cls=best["cls"], minutes=(t - best["made"]) / 60 + lag / 60,
                          ev=ev(best, t, lag, tab)))
    return picks


def mix(picks):
    out = collections.Counter()
    for p in picks:
        if p:
            out[(value.group_of(p["cls"]), band(p["minutes"]))] += 1
    return out


def cmd_replay(a):
    writes = list(read_writes(a.actions))
    outcomes = read_outcomes(a.outcomes) if pathlib.Path(a.outcomes).exists() else {}
    state = json.loads(pathlib.Path(a.state).read_text())
    tq = state.get("targeter", state)
    items, cands = tq["items"], tq["candidates"]
    tab = value.table(pathlib.Path(a.table)) if a.table else value.DEFAULT
    end = ts(a.end) if a.end else max(w["t_pick"] for w in writes if w.get("t_pick"))
    start = end - a.hours * 3600
    mine = [w for w in writes if ordinary(w) and w.get("t_pick") and w.get("t_made") and start <= w["t_pick"] < end]
    mine.sort(key=lambda w: w["t_pick"])
    slots = [(w["t_pick"], w["t_sent"] - w["t_pick"], w["target_author"]) for w in mine]
    pool = pool_from(writes, items, cands)
    actual = [dict(pid=w["target_post"], cls=w["target_class"], minutes=(w["t_sent"] - w["t_made"]) / 60,
                   ev=value.curve(tab["curves"][value.group_of(w["target_class"])], (w["t_sent"] - w["t_made"]) / 60))
              for w in mine]
    runs = {"actual": actual, "base": simulate(pool, slots, "base", tab), "value": simulate(pool, slots, "value", tab)}
    print(f"{len(slots)} ordinary slots {dt.datetime.fromtimestamp(start, dt.timezone.utc):%d %b %H:%M} - "
          f"{dt.datetime.fromtimestamp(end, dt.timezone.utc):%d %b %H:%M} UTC; pool {len(pool)} entries "
          f"({sum(e['picked'] is None for e in pool)} never answered, classes from the queue)")
    for name, picks in runs.items():
        got = [p for p in picks if p]
        print(f"  {name:6s} filled {len(got)}  expected points {sum(p['ev'] for p in got):8.0f}  a write "
              f"{sum(p['ev'] for p in got) / max(1, len(got)):.3f}")
    real = [points(outcomes[w["post_id"]]) for w in mine if w["post_id"] in outcomes]
    evs = [p["ev"] for p, w in zip(actual, mine) if w["post_id"] in outcomes]
    if real:
        print(f"  calibration: actual picks with a 6 h check {len(real)}: mean points {sum(real) / len(real):.3f}, "
              f"their expected {sum(evs) / len(evs):.3f}")
    cells = sorted(set(mix(runs["base"])) | set(mix(runs["value"])) | set(mix(actual)))
    print("  slots by group x landing age: actual / base / value (value - base)")
    for c in cells:
        x, b, v = mix(actual)[c], mix(runs["base"])[c], mix(runs["value"])[c]
        print(f"    {c[0]:8s} {c[1]:7s} {x:5d} {b:5d} {v:5d} ({v - b:+d})")
    # one step from the real queue: what each order takes from the queue as it was at each slot
    ob = simulate(pool, slots, "base", tab, onestep=True)
    ov = simulate(pool, slots, "value", tab, onestep=True)
    same_b = sum(1 for p, w in zip(ob, mine) if p and p["pid"] == w["target_post"])
    same_v = sum(1 for p, w in zip(ov, mine) if p and p["pid"] == w["target_post"])
    diff = sum(1 for p, q in zip(ob, ov) if p and q and p["pid"] != q["pid"])
    gain = sum(q["ev"] - p["ev"] for p, q in zip(ob, ov) if p and q)
    print(f"  one step from the real queue: base reconstruction = the real pick in {same_b} of {len(slots)} slots, value in "
          f"{same_v}; value differs from base in {diff}, expected +{gain:.0f} points over those slots (myopic)")
    if a.by_arm:
        arms = collections.Counter(w.get("queue_arm") for w in mine)
        for arm in arms:
            idx = [k for k, w in enumerate(mine) if w.get("queue_arm") == arm]
            sb = sum(1 for k in idx if ob[k] and ob[k]["pid"] == mine[k]["target_post"])
            mean = lambda ps: sum(p["ev"] for p in ps if p) / max(1, sum(1 for p in ps if p))      # noqa: E731
            print(f"    queue_arm {arm}: {len(idx)} slots, base reconstruction matches {sb}; expected points a write: real "
                  f"{mean([actual[k] for k in idx]):.3f}, base one step {mean([ob[k] for k in idx]):.3f}, value one step "
                  f"{mean([ov[k] for k in idx]):.3f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("build", "replay"))
    ap.add_argument("--actions", default=str(config.ACTIONS_LOG))
    ap.add_argument("--outcomes", default=str(config.OUTCOMES_LOG))
    ap.add_argument("--state", default=str(config.STATE_FILE))
    ap.add_argument("--out", default=str(config.VALUE_TABLE_FILE))
    ap.add_argument("--table", help="replay: score with this table file (default value.DEFAULT)")
    ap.add_argument("--hours", type=float, default=72)
    ap.add_argument("--end", help="ISO time the window ends (default: the last write with a 6 h check / the last pick)")
    ap.add_argument("--dry", action="store_true", help="build: print the table, write nothing")
    ap.add_argument("--by-arm", action="store_true", help="replay: how well the base reconstruction matches, per queue arm")
    a = ap.parse_args()
    t0 = time.time()
    (cmd_build if a.cmd == "build" else cmd_replay)(a)
    print(f"({time.time() - t0:.0f} s)", file=sys.stderr)


if __name__ == "__main__":
    main()
