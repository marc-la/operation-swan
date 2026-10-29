"""Engagement per write (todo/33): what the portal paid for our citizen-facing writes, per arm and per free-lever cell.

    python scripts/engagement_report.py                         # last 48 h, from logs/ and data/ here (run it on the box)
    python scripts/engagement_report.py --hours 72 --out docs/06-strategy/engagement-2026-10-26.md

Reads logs/swan_actions.jsonl (streamed: it was 118 MB on 23 Oct), logs/swan_outcomes.jsonl, logs/swan_engagement.jsonl
(followup.py's follow-back reads) and data/portal.json (the portal's hourly points log, kept 48 h). Read-only: no
platform calls.

Two tables, one per design (todo/33 section 2):
  budget arms   arm_eng (base, engagers_first), 2 h switchback blocks: the portal's hourly points split into likes /
                replies / reposts / follows / unfollows / changes of mind, over the arm's blocks (lines 1 h after each
                block's writes), per citizen-facing write and per hour; guardrails: away events, unfollows, hidden posts.
  free cells    eng_cell (none, follow, like, follow+like), randomised per citizen (engage.cell): per citizen, did they
                follow the replying voice back (6 h, 24 h), like or answer our first reply (the 6 h outcome read), and the
                points that is worth at x1 (like 5, reply 15, follow 20, an unfollow -20).
Each table ends in a kill / promote / hold verdict by the rules in todo/33 section 4. They are a human call on thin
numbers: a verdict on fewer than MIN_BLOCKS blocks or MIN_CITIZENS citizens a cell is marked thin.
"""
import argparse
import collections
import datetime as dt
import json
import math
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from swan_bot import config, engage, jsonl  # noqa: E402
from swan_bot.analysis import Z90, block_window, latest_by_post, parse_activity, ts_of, wilson  # noqa: E402

CITIZEN_WRITES = ("reply", "reply_back", "second_voice")
BLOCK_LAG_S = 3600                   # a block's portal lines are those 1 h after its writes (hourly at ~:53)
MIN_BLOCKS = 6                       # per arm: 3 days at 2 h blocks (todo/33 section 4)
MIN_CITIZENS = 300                   # per cell
BASE = {"likes": 5, "reposts": 10, "replies": 15, "follows": 20, "unfollows": -20}
MIND = {"towards": {"primary": 160, "contribution": 8}, "away": {"primary": -80, "contribution": -2},
        "neither": {"primary": 20, "contribution": 1}, "other": {"primary": 20, "contribution": 1}}   # build.MIND_SIDES
SUMMED = ("points", "engagement", "persuasion", "toward", "away", "likes", "replies", "reposts", "follows", "unfollows",
          "gain", "penalty")
KEEP = ("ts", "act", "live", "post_id", "account_id", "username", "target_author", "eng_cell", "arm_eng", "block_id",
        "purpose", "citizen_id", "why", "arm_npc", "npc_block", "npc_score")


def rows_since(path, since):
    """The live rows of the action log since `since`, cut to KEEP, streamed."""
    out = []
    for r in jsonl.Reader(path, contains='"live"'):
        if r.get("live") and r.get("ts") and ts_of(r["ts"]) >= since:
            out.append({k: r[k] for k in KEEP if k in r})
    return out


def portal_points(events):
    """[{ts, points, likes, replies, reposts, follows, unfollows, views, toward, away, engagement, persuasion, gain,
    penalty}] from the portal's hourly rows (data/portal.json "events"). engagement: the points of likes, reposts,
    replies, follows less unfollows at the line's multiplier (views are capped at 500 a day and left out); persuasion:
    the changes of mind (towards 160, away -80, contributions 8 and -2); gain and penalty: the positive and the
    negative items of both, as positive numbers. The portal's own total is `points`."""
    out = []
    for e in events:
        if e.get("type") not in (None, "SCORE_NARRATIVE"):
            continue
        p = parse_activity(e.get("message") or "")
        mult = p.get("multiplier") or 1.0
        row = {k: p.get(k, 0) for k in ("likes", "replies", "reposts", "follows", "unfollows", "views")}
        row["engagement"] = mult * sum(BASE[k] * row[k] for k in BASE)
        minds = [MIND[d][k] * p.get(f"mind_{k}_{d}", 0) for d in MIND for k in ("primary", "contribution")]
        row["persuasion"] = sum(minds)
        row["gain"] = mult * sum(BASE[k] * row[k] for k in BASE if BASE[k] > 0) + sum(x for x in minds if x > 0)
        row["penalty"] = mult * -BASE["unfollows"] * row["unfollows"] - sum(x for x in minds if x < 0)
        row.update(ts=ts_of(e["ts"]), points=e.get("points") or 0, toward=p["towards"], away=p["away"])
        out.append(row)
    return out


def citizen_writes(rows):
    """Writes to citizens: is_citizen, plus todo/48's extra-arm citizens above id 2343 (logged with npc_score)."""
    return [r for r in rows if r.get("act") in CITIZEN_WRITES and r.get("post_id")
            and (config.is_citizen(r.get("target_author")) or r.get("npc_score") is not None)]


def arm_table(rows, points, dim="arm_eng", block="block_id"):
    """{arm: stats}: per arm of the switchback, over its whole blocks, the citizen-facing writes, the hours, the
    portal's lines (1 h lag) summed, and points per write and per hour. block: the field holding the block id."""
    blocks = collections.defaultdict(lambda: collections.defaultdict(list))
    for w in citizen_writes(rows):
        if w.get(dim) and w.get(block):
            blocks[w[dim]][w[block]].append(w)
    out = {}
    for arm, bs in blocks.items():
        a = dict(blocks=len(bs), writes=0, hours=0.0, hidden=0)
        a.update({k: 0.0 for k in SUMMED})
        for bid, ws in bs.items():
            start, end = block_window(bid)
            a["writes"] += len(ws)
            a["hours"] += (end - start) / 3600
            for e in points:
                if start + BLOCK_LAG_S <= e["ts"] < end + BLOCK_LAG_S:
                    for k in SUMMED:
                        a[k] += e[k]
        out[arm] = a
    return out


def arm_verdicts(table, base="base"):
    """{arm: verdict} by todo/33 section 4: kill when away events beat base (per write) or the arm's unfollows plus away
    events cost more points than it gained; promote when points per write beat base; else hold. thin: fewer blocks
    than MIN_BLOCKS on either side (promote needs >= MIN_BLOCKS each)."""
    b = table.get(base)
    out = {}
    for arm, a in table.items():
        if arm == base or not b or not a["writes"] or not b["writes"]:
            continue
        ppw, bpw = a["points"] / a["writes"], b["points"] / b["writes"]
        away_pw, base_away_pw = a["away"] / a["writes"], b["away"] / b["writes"]
        if away_pw > base_away_pw:
            v = "**kill** (away events beat base)"
        elif a["penalty"] > a["gain"]:
            v = "**kill** (unfollows and away events cost more than the gain)"
        elif ppw > bpw:
            v = "promote (points per write beat base)"
        else:
            v = "hold"
        if min(a["blocks"], b["blocks"]) < MIN_BLOCKS:
            v += " (thin: under %d blocks)" % MIN_BLOCKS
        out[arm] = v
    return out


def cohort(rows):
    """{citizen: first reply row} among the rows with an eng_cell, plus per citizen which levers did run:
    ({citizen: row}, {citizen: {"follow", "like"}})."""
    first = engage.first_contacts(sorted((r for r in rows if r.get("eng_cell")), key=lambda r: r["ts"]))
    did = collections.defaultdict(set)
    for r in rows:
        if r.get("act") in ("follow", "like") and r.get("purpose") in ("eng_follow", "eng_like") and r.get("citizen_id"):
            did[str(r["citizen_id"])].add(r["act"])
    return first, did


def citizen_outcomes(first, did, outcomes, checks):
    """One row per citizen: cell, levers done, liked / replied to our first reply (its 6 h outcome read; None when unread
    or, for likes, read before citizen_likers was logged), followed back (at any read; None when unread), unfollowed
    (followed back at 6 h, not at 24 h) and the first reply hidden."""
    by_cit = collections.defaultdict(dict)
    for c in checks:
        by_cit[str(c["citizen_id"])][c["check"]] = c.get("followed_back")
    rows = []
    for cit, w in first.items():
        o = outcomes.get(w["post_id"])
        fb = by_cit.get(cit, {})
        vals = list(fb.values())            # followed back at any read: the portal gave +20 then, an unfollow later -20
        ever = True if any(v is True for v in vals) else (False if any(v is False for v in vals) else None)
        liked = None if o is None or "citizen_likers" not in o else int(cit) in o["citizen_likers"]
        replied = None if o is None else int(cit) in (o.get("citizen_repliers") or [])
        rows.append(dict(citizen=cit, cell=w["eng_cell"], did=did.get(cit, set()), liked=liked, replied=replied,
                         back=ever, unfollowed=(fb.get(0) is True and fb.get(1) is False),
                         hidden=bool(o and o.get("hidden_or_gone") is not None)))
    return rows


def points_each(c):
    """What one citizen was worth at x1: a like 5, a reply 15, a follow 20, an unfollow -20."""
    return (5 * bool(c["liked"]) + 15 * bool(c["replied"]) + 20 * bool(c["back"]) - 20 * c["unfollowed"])


def mean_se(xs):
    n = len(xs)
    if n < 2:
        return (xs[0] if xs else None), None
    m = sum(xs) / n
    return m, math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1) / n)


def cell_table(citizens):
    """{cell: stats} over the citizens: counts, rates with 90% intervals, points per citizen (mean, standard error)."""
    out = {}
    for name in config.ENG_CELLS:
        cs = [c for c in citizens if c["cell"] == name]
        if not cs:
            continue
        known = lambda key: [c for c in cs if c[key] is not None]
        m, se = mean_se([points_each(c) for c in cs])
        out[name] = dict(n=len(cs), followed=sum("follow" in c["did"] for c in cs), liked_by_us=sum("like" in c["did"] for c in cs),
                         back=(sum(bool(c["back"]) for c in known("back")), len(known("back"))),
                         cit_liked=(sum(bool(c["liked"]) for c in known("liked")), len(known("liked"))),
                         cit_replied=(sum(bool(c["replied"]) for c in known("replied")), len(known("replied"))),
                         unfollowed=sum(c["unfollowed"] for c in cs), hidden=sum(c["hidden"] for c in cs),
                         gain=sum(5 * bool(c["liked"]) + 15 * bool(c["replied"]) + 20 * bool(c["back"]) for c in cs),
                         penalty=20 * sum(c["unfollowed"] for c in cs), mean=m, se=se)
    return out


def cell_verdicts(table, base="none"):
    """{cell: verdict}: kill when its unfollows cost more points than it gained (or its hidden replies per citizen run
    over `none`'s by 2 points of share: check the ledger for follows or likes), promote when its mean points per citizen beat none's by more than the
    90% interval of the difference over >= MIN_CITIZENS citizens each, else hold."""
    b = table.get(base)
    out = {}
    for name, c in table.items():
        if name == base or not b or c["mean"] is None or b["mean"] is None:
            continue
        diff = c["mean"] - b["mean"]
        half = Z90 * math.sqrt((c["se"] or 0) ** 2 + (b["se"] or 0) ** 2)
        if c["penalty"] > c["gain"]:
            v = "**kill** (unfollows cost more than the gain)"
        elif c["hidden"] / c["n"] > b["hidden"] / b["n"] + 0.02:
            v = "**kill?** (more hidden replies than none; check the ledger for follows or likes)"
        elif diff - half > 0:
            v = "promote (beats none)"
        else:
            v = "hold"
        if min(c["n"], b["n"]) < MIN_CITIZENS:
            v += " (thin: under %d citizens)" % MIN_CITIZENS
        out[name] = v
    return out


def pct(k, n):
    return "–" if not n else f"{100 * k / n:.0f}%"


def fmt(x, nd=1):
    return "–" if x is None else f"{x:.{nd}f}"


def proxy(w, outcomes):
    """Our points proxy for one write from its latest outcome read, at x1: likes 5, replies 15, by citizens and (todo/48)
    by likely citizens above id 2343. None when unread. Since 29 Oct (cit_def "likely") citizen_* already include
    them, so npc_* is added only to older rows."""
    o = outcomes.get(w["post_id"])
    if not o or o.get("hidden_or_gone"):
        return None
    extra = 0 if o.get("cit_def") else 1
    return (BASE["likes"] * ((o.get("citizen_likes") or 0) + extra * (o.get("npc_likes") or 0))
            + BASE["replies"] * ((o.get("citizen_replies") or 0) + extra * (o.get("npc_replies") or 0)))


def npc_section(rows, points, outcomes):
    """todo/48's arm_npc (base / extra, NPC_BLOCK_S blocks): portal points per write over the arm's blocks, and our proxy
    per write from the outcome reads, the extra writes (npc_score set) apart. [] when no write carries arm_npc."""
    table = arm_table(rows, points, "arm_npc", "npc_block")
    if not table:
        return []
    verdicts = arm_verdicts(table)
    out = [f"### Extra citizens (arm_npc, {config.NPC_BLOCK_S // 3600} h blocks; todo/48)", "",
           "| arm | blocks | writes | of them to npc | portal points | points per write | proxy per write (read) | "
           "npc proxy per write (read) | npc answered | verdict |", "|---|---|---|---|---|---|---|---|---|---|"]
    for arm in sorted(table):
        a = table[arm]
        ws = [w for w in citizen_writes(rows) if w.get("arm_npc") == arm and w.get("npc_block")]
        px = [x for x in (proxy(w, outcomes) for w in ws) if x is not None]
        nw = [w for w in ws if w.get("npc_score") is not None]
        npx = [x for x in (proxy(w, outcomes) for w in nw) if x is not None]
        ans = [bool((outcomes.get(w["post_id"]) or {}).get("target_replied")) for w in nw if w["post_id"] in outcomes]
        out.append(f"| {arm} | {a['blocks']} | {a['writes']} | {len(nw)} | {a['points']:.0f} | "
                   f"**{fmt(a['points'] / a['writes'] if a['writes'] else None, 2)}** | "
                   f"{fmt(sum(px) / len(px) if px else None, 2)} ({len(px)}) | {fmt(sum(npx) / len(npx) if npx else None, 2)} "
                   f"({len(npx)}) | {pct(sum(ans), len(ans))} | {verdicts.get(arm, '(base)')} |")
    return out + [""]


def render(rows, points, outcomes, checks, since, until):
    p = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%d %b %H:%M UTC")
    writes = citizen_writes(rows)
    out = [f"## Engagement per write: {p(since)} to {p(until)}", "",
           f"- Citizen-facing writes: **{len(writes)}** ({', '.join(f'{k} {v}' for k, v in collections.Counter(w['act'] for w in writes).most_common())}); "
           f"portal rows in the window: {sum(since <= e['ts'] < until for e in points)}.", ""]
    table = arm_table(rows, points)
    if table:
        verdicts = arm_verdicts(table)
        out += [f"### Budget arms (arm_eng, {config.ENG_BLOCK_S // 3600} h blocks; portal lines {BLOCK_LAG_S // 3600} h after each block)", "",
                "| arm | blocks | writes | hours | portal points | engagement | likes / replies / reposts / follows | "
                "unfollows | persuasion | away | points per write | points per hour | verdict |",
                "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for arm in sorted(table):
            a = table[arm]
            out.append(f"| {arm} | {a['blocks']} | {a['writes']} | {a['hours']:.0f} | {a['points']:.0f} | {a['engagement']:.0f} | "
                       f"{a['likes']:.0f} / {a['replies']:.0f} / {a['reposts']:.0f} / {a['follows']:.0f} | {a['unfollows']:.0f} | "
                       f"{a['persuasion']:.0f} | {a['away']:.0f} | **{fmt(a['points'] / a['writes'] if a['writes'] else None, 2)}** | "
                       f"{fmt(a['points'] / a['hours'] if a['hours'] else None, 0)} | {verdicts.get(arm, '(base)')} |")
        out.append("")
    out += npc_section(rows, points, outcomes)
    first, did = cohort(rows)
    citizens = citizen_outcomes(first, did, outcomes, checks)
    cells = cell_table(citizens)
    if cells:
        verdicts = cell_verdicts(cells)
        out += ["### Free levers (eng_cell, per citizen)", "",
                "Points per citizen at x1: like 5, reply 15, follow-back 20, unfollow -20; liked / replied from the 6 h read "
                "of our first reply, follow-back from the 6 h and 24 h follower reads (– when unread).", "",
                "| cell | citizens | we followed | we liked | followed back [90%] | liked our reply | answered | unfollowed | "
                "hidden | points per citizen (se) | verdict |", "|---|---|---|---|---|---|---|---|---|---|---|"]
        for name in config.ENG_CELLS:
            c = cells.get(name)
            if not c:
                continue
            rate, lo, hi = wilson(*c["back"])
            ci = "" if rate is None else f" [{100 * lo:.0f}–{100 * hi:.0f}%]"
            out.append(f"| {name} | {c['n']} | {c['followed']} | {c['liked_by_us']} | {pct(*c['back'])}{ci} | "
                       f"{pct(*c['cit_liked'])} | {pct(*c['cit_replied'])} | {c['unfollowed']} | {c['hidden']} | "
                       f"**{fmt(c['mean'], 2)}** ({fmt(c['se'], 2)}) | {verdicts.get(name, '(base)')} |")
        out.append("")
    if not table and not cells:
        out += ["No arm_eng blocks or eng_cell rows in the window yet.", ""]
    out += ["Verdicts are a human call: kill and promote by todo/33 section 4, never from a thin cell. Persuasion is a "
            "guardrail, not a goal: an arm whose away events beat base is killed.", ""]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hours", type=float, default=48, help="window length")
    ap.add_argument("--root", default=str(config.ROOT), help="where logs/ and data/ are")
    ap.add_argument("--out", help="write the markdown here instead of printing it")
    args = ap.parse_args()
    root = pathlib.Path(args.root)
    until = time.time()
    since = until - args.hours * 3600
    rows = rows_since(root / "logs" / "swan_actions.jsonl", since)
    outcomes = latest_by_post([o for o in jsonl.Reader(root / "logs" / "swan_outcomes.jsonl", contains='"outcome"')
                               if o.get("act") == "outcome"])
    checks = [c for c in jsonl.Reader(root / "logs" / "swan_engagement.jsonl") if c.get("act") == "engage"]
    try:
        events = json.loads((root / "data" / "portal.json").read_text()).get("events") or []
    except (OSError, ValueError):
        events = []
    text = "\n".join(render(rows, portal_points(events), outcomes, checks, since, until))
    if args.out:
        pathlib.Path(args.out).write_text(text + "\n")
        print("wrote", args.out)
    else:
        print(text)


if __name__ == "__main__":
    main()
