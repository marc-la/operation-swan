"""New citizens mid-game (todo/21 item 6, G10), read-only. The organisers said more citizens may be added. Our rule
is "seeded before launch" (config.is_citizen: ids 12-2343), so a citizen added later would be treated as a team bot:
never answered, never counted. get_account has no field that tells a citizen from a team account, so this watches the
pace. Measured 2026-10-21 on runs of 30-40 ids: seeded citizens (ids 1000+, 2300+) came every 25-42 s (median) and
evenly (cv of the gaps ~0.7); team accounts (ids 5000+, 9800+) every ~13 s in bursts (cv 1.4-1.9). Two samples
each: a weak signal, hence the human check. Private accounts show no created_at; they count as part of a run.
A full walk the same day (9,198 accounts to id 9961) found team runs that match the pace: 20-36 ids four times and
309 / 283 ids twice (5304-5612, 8238-8520: bot names like "Civic Voice 08", replies a minute after creation, 404
holes at both ends). So pace can't tell a team's bulk registration from new citizens: the alert names a few accounts
and their first posts for the person who decides, and only runs past REVIEWED_TO count.

It walks accounts() from where the last run stopped and flags a run of >= RUN consecutive ids above the seeded range,
none of them ours or verified, created at a steady seeding pace. A flag is an alert, never a change: a person checks
it (ideally against a Discord announcement) and adds the range to config.EXTRA_CITIZEN_RANGES. A wrong range would send
our replies to team bots and pollute every metric.

swan_watch.py runs scan() hourly; by hand:
    python scripts/citizen_watch.py --dry       # print what it finds; no state, log or alert
"""
import argparse
import json
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import capturethenarrative as ctn  # noqa: E402

from swan_bot import config  # noqa: E402
from swan_bot.feeds import created_ts  # noqa: E402

RUN = 50                    # consecutive ids (team runs of 20-36 are common; 283 and 309 happened once each)
REVIEWED_TO = 9961          # 2026-10-21 ~14:55 UTC: every run up to this id checked by hand, all team accounts
PACE_S = (15.0, 120.0)      # median seconds between creations (seeded 25-42 s; team accounts ~13 s)
STEADY_CV = 1.0             # stdev / mean of those gaps (seeded ~0.7; team bursts 1.4-1.9)
MAX_PAGES = 40              # accounts() reads per run, 100 each (that route has 300 a minute)
TAIL = RUN * 3              # accounts kept across runs, so a run that spans two reads is still seen


def suspect_runs(accounts, ours):
    """[(first_id, last_id, n, median_gap_s, cv)] for runs that look seeded."""
    pool = sorted((a for a in accounts if a["account_id"] > max(config.CITIZEN_MAX_ID, REVIEWED_TO)
                   and not config.is_citizen(a["account_id"]) and a["account_id"] not in ours
                   and not a.get("verified")), key=lambda a: a["account_id"])
    groups, cur = [], []
    for a in pool:
        if cur and a["account_id"] != cur[-1]["account_id"] + 1:
            groups.append(cur)
            cur = []
        cur.append(a)
    groups.append(cur)
    out = []
    for g in groups:
        if len(g) < RUN:
            continue
        dated = [created_ts(a) for a in g if a.get("created_at")]          # private accounts show no date
        gaps = [b - a for a, b in zip(dated, dated[1:])]
        if len(gaps) < RUN // 2:
            continue
        mean = statistics.mean(gaps)
        cv = statistics.pstdev(gaps) / mean if mean > 0 else 9.9
        med = statistics.median(gaps)
        if PACE_S[0] <= med <= PACE_S[1] and cv <= STEADY_CV:
            out.append((g[0]["account_id"], g[-1]["account_id"], len(g), round(med, 1), round(cv, 2)))
    return out


def scan(social, state, ours, record, alert):
    """One hourly pass. state: swan_watch's dict (its "citizens" key is ours)."""
    st = state.setdefault("citizens", {"cursor": None, "tail": [], "alerted": []})
    seen = {a["account_id"]: a for a in st["tail"]}
    cursor, pages = st["cursor"], 0
    while pages < MAX_PAGES:
        try:
            page = social.accounts(limit=100, cursor=cursor)
        except ctn.APIError as e:
            record({"act": "citizen_watch_error", "status": e.status})
            break
        pages += 1
        for a in page:
            seen[a["account_id"]] = {k: a.get(k) for k in ("account_id", "username", "verified", "created_at")}
        if not page.next_cursor:
            break                                # the newest account: start this page again next time
        cursor = page.next_cursor
    st["cursor"] = cursor
    accounts = sorted(seen.values(), key=lambda a: a["account_id"])
    found = suspect_runs(accounts, ours)
    st["tail"] = accounts[-TAIL:]
    st["last_id"] = accounts[-1]["account_id"] if accounts else None
    new = [r for r in found if [r[0], r[1]] not in st["alerted"]]
    record({"act": "citizen_watch", "pages": pages, "last_id": st["last_id"], "suspect_runs": found})
    by_id = {a["account_id"]: a for a in accounts}
    for lo, hi, n, med, cv in new:
        st["alerted"].append([lo, hi])
        names = ", ".join(by_id[i]["username"] for i in (lo, (lo + hi) // 2, hi) if i in by_id)
        span = f"{(by_id.get(lo) or {}).get('created_at') or '?'} to {(by_id.get(hi) or {}).get('created_at') or '?'}"
        alert(f"possible NEW CITIZENS: account ids {lo}-{hi} ({n} in a row, none ours, created every ~{med} s, "
              f"cv {cv}, {span}; e.g. {names}). Team bulk registrations look the same, so check Discord for an "
              f"announcement and their first posts. If confirmed, add ({lo}, {hi}) to config.EXTRA_CITIZEN_RANGES. "
              f"Never automatic (todo/21 G10).")
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry", action="store_true", help="print only: no state, log or alert")
    ap.parse_args()
    records = json.loads(config.ACCOUNTS_FILE.read_text()) if config.ACCOUNTS_FILE.exists() else []
    ours = {r.get("account_id") for r in records if r.get("account_id")}
    scan(ctn.LegitSocial(), {}, ours, lambda r: print(json.dumps(r)), print)


if __name__ == "__main__":
    main()
