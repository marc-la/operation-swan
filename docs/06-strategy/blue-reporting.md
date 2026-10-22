# Blue reporting: the greedy mechanism (2026-10-21)

How we turn the Blue rules into points, and why the code (`src/swan_blue`, `swan-blue.service`) works the way it does. Rules: [scoring §3](../03-scoring/scoring-guide.md#3-reporting-inauthentic-posts-and-accounts). Work item and status: todo/07.

## 1. The limits, as they stand on 21 Oct (cap and multi-team boost updated 22 Oct)

| Rule | Value | Source |
|---|---|---|
| Ruling time | 3 h after the first report, halved per extra team reporting | scoring page, 20 Oct PM |
| Several teams reporting | the automod "gets a boost to accuracy if a post or account has been reported by multiple teams" | Discord, 22 Oct |
| Moderator error | ~1 ruling in 10 is wrong (either way) | scoring page, 20 Oct PM (was 1 in 4) |
| A "genuine" ruling | no new reports, posts or accounts, for 6 h; pending ones still resolve. Overlapping locks run at the same time (they don't add up) | scoring §3; `#questions` 21 Oct |
| Pending reports | ≤ **30** per team (25 until 22 Oct). We keep the 30th for an account report | Discord, 22 Oct (was 25, 20 Oct) |
| Post report | 25 if our team was **first**, 5 if later (first 5 teams only) | scoring §3 |
| Account report | 15 to **every** team with an open report, if at ruling the account has ≥ 1 moderator-hidden post and ≥ 100 actions. Otherwise dismissed: **no points and no lock** | scoring §3 |
| Per target team per Sydney day | awards 1–5 full, 6–10 half, 11+ 10% (posts and accounts together) | scoring §3 |
| Report routes | 3/min each, a budget of their own (not the posting budget) | api-reference |

## 2. What follows from them

- **Finding targets is easy.** Every account with an id above 2343 was registered after launch, so it belongs to a team. On 21 Oct, every Trending post we scored had 83–100% of its likes from team accounts. 18–23-account reply rings that finish within 15–35 minutes are common.
- **Locks set the pace, not the reports.** With 25 pending and 1 in 10 rulings wrong, the chance that a batch has no "genuine" ruling is 0.9²⁵ ≈ 7% (with 30 pending since 22 Oct, 0.9³⁰ ≈ 4%). So nearly every batch ends in a 6 h lock, and the cycle is about 3 h of rulings plus 6 h locked.
- **The points come from refilling every slot the moment we may**, around the clock, with the best targets first. A model of that cycle (fill to 25, rule at 3 h, lock 6 h on a genuine ruling) gave about **70 reports and 1,200 points a day** (21 Oct; §7 and §8 for what the rulings since then changed). Being first only half the time drops it to about 870. Spreading over 40 teams instead of 12 adds about 70. So freshness matters most, then refilling at once.
- **Account reports are free money** whenever an account qualifies: there's no moderator error and no lock risk. The authors of ring posts, including reply-ring replies, are the accounts that can qualify. Like-only ring accounts never post, so they can't be suspended.
- **First matters for posts only.** It's order, not time: 25 for the first team, 5 for any later one. So we report posts young, under an hour old, and watch the timelines of known ring authors to catch their next post early.

## 3. The mechanism

```
scan (reads only)                    rank                                fill
 Trending every 10 min ─┐            each candidate:                     while not locked and pending < 30:
 Latest every 3 min ────┼─ team-     EV = 0.9 × (25·P(first)+5·(1−P))     file the best EV first
 ring authors' posts ───┘  account   × team's daily rate × strength       (approve mode: only approved posts;
   every 5 min              posts    account EV = 0.95 × 15 × rate         account reports always)
        │                 audit at 10 min (and 45 min):  ↑ team count updated after each pick
        └──────────────── likers, replies, timing  ──→ like ring / reply ring? → cluster label
rulings every 10 min: 404 = hidden (inauthentic) → its author is an account-report lead
                      still visible 3 h 15 min after filing = genuine → locked until filing + 9 h
harvest every 30 min: leads (and ring posts someone else got hidden) with ≥ 100 actions → account candidates
```

- **Evidence (a report needs one):** a *like ring* (≥ 20 team likes, ≥ 85% of all likes, half in the first 30 min or ≥ 8 inside 60 s) or a *reply ring* (≥ 10 replies from ≥ 6 team accounts within 60 min), or an *early ring* (a known ring author's new post where ≥ 8 of its likers and repliers also acted on that author's earlier confirmed ring post, and new accounts are ≥ 85% of its likes). Citizens, verified accounts (ids 1–11) and our own accounts are never targets, and our accounts are left out of every count. The detail text states only measured numbers (likes, timing, id runs), never the post's side (rules §5.2.2, LS.6.5).
- **Clusters stand in for teams.** Accounts that like and reply to the same posts share a label, which is kept across scans, and the daily rate is counted per label. It's a proxy: one team can show up as two clusters, which costs a little rate, never a rule breach.
- **Being first (25, not 5) — what pushes the odds (2026-10-21 evening).** Order decides it, and nobody can see other teams' reports, so we can only raise the odds and measure them afterwards:
  - *Known ring authors first.* An author whose post showed a like or reply ring in the last 36 h is watched: its timeline is polled every 3 min and its new posts are audited at 4, 12 and 45 min (others at 10 and 45), ahead of everything else. The *early ring* class lets a report go out while the ring is still small. Top rings put 86–91% of their likes in the first 2 minutes.
  - *No approval wait.* Auto from the start (see Modes).
  - *A fresh reserve.* Posts over an hour old (which mostly pay 5) may not take the last 5 free slots; those wait for fresh ring posts.
  - *Measure, then tune.* P(first) starts as a prior: 0.9 under 1 h old, 0.6 under 3 h, 0.3 older, ×0.7 on Trending (more teams see it). Every 15 min the service counts "first inauthentic report" against plain "inauthentic report" awards in the portal log. After 8 paid awards, the ratio of that share to what we predicted at filing scales every estimate (0.4–1.3×). The dashboard shows "paid as first X of Y". Posts over 12 h old aren't reported.
  - The first batch (21 Oct, before this) was filed 23–170 min after posting, median ~50 min, mostly because it waited for approval.
- **Modes.** *auto* from the start (since 21 Oct evening; the first batch of 25 was approved by hand). It switches to *approve* and alerts once 10+ post rulings show under 70% inauthentic. If our targets are all bots we expect ~90%: observed rate = 0.1 + 0.8 × (share of our targets that are bots). *off* when `~/ctn/BLUE_OFF` exists. Account reports file in both approve and auto: they're rule-based and can't lock us.
- **Refused reports.** 400/404/409 drop that one target. 401 logs in again. A 403 that says "suspended ... until <time>" (the 6 h lock) waits until that time (since 22 Oct, §7). Anything else (the pending cap, say) waits 30 min and alerts once. A refused report still costs budget, so we never retry in a loop.
- **The reporter** is one booster: the lowest-id active one (`config.blue_reporter`, `salote_sails` on 21 Oct). The bot stops using it. It would register a replacement booster, but on 21 Oct it was already at its cap of 49 live accounts (15 voices, 33 boosters, the reporter), so the like pool is one smaller (33).

## 4. What it costs Red (kept small)

- **Write budget: none.** Report routes have their own budget.
- **Accounts:** one booster leaves the like pool: 33 likers instead of 34 while the bot is at its live-account cap (otherwise its drip registration replaces it).
- **Reads:** about 0.6 feed calls a minute of the team's 10 (it backs off when fewer than 4 are left), and under 150 other reads a minute against 300 per endpoint.
- **Our own exposure is unchanged by this code, but rising.** The organisers are pushing every team into Blue, and our hourly heavy post (one post plus 15–20 thread replies from voices) matches the same two evidence classes. Boosters can't be suspended; voices can. `swan_watch` already takes a voice off amplified posts after 1 hidden post and stops it at 2. Whether to cut thread replies is a Red decision, not a Blue one (decided 2026-10-22: amplification paused, see [direction-2026-10-21](direction-2026-10-21.md)).
- **Upside for Red:** hiding ring posts on Trending frees places there and lowers the cutoff for our amplified posts.

## 5. Running it

- Dashboard, **Blue** section: the state in one line (waiting, locked, pending, hidden today, points); a counts line (filed, approved and waiting to file, pending, hidden, genuine, refused, account rulings, share inauthentic, paid as first); a collapsed table of today's reports with their status and ruling time; and in approve mode the reports waiting, one row per ring. One command approves them all: `ssh swan-ec2 'ctn/scripts/blue.sh approve all'`. The banner turns amber when something waits or swan-blue goes quiet.
- Stop filing: `ssh swan-ec2 'touch ctn/BLUE_OFF'` (rm to resume; the scan and rulings carry on). Stop everything: `sudo systemctl stop swan-blue`.
- Records: `logs/blue_reports.jsonl` (every report with its evidence, detail text, reporter and owner; rulings, locks, mode changes); state in `data/blue_state.json`. A dry run (`cd src && python -m swan_blue`) uses its own `.dry.json` files and files nothing.
- Account-report outcomes don't show through the API: a suspended account still reads as normal (checked on @lani_wharfcafe23, 21 Oct). Read them from the portal points log ("Moderation" lines).

## 6. Assumptions to check with the first rulings

1. The 25 cap counts account reports too (we assume yes) and an over-cap report is refused with some 4xx. Open question B.11.
2. The daily rate counts on the **ruling** day (open question B.10).
3. A ruled-inauthentic post answers 404, as our own hidden posts do. A post its author deleted also answers 404, and we count that as hidden. The portal points log is the ground truth.
4. ~~Tune `evidence.p_first` from the portal~~ Automatic since 21 Oct evening (`service.calibrate`). Check the portal's wording matches "N first inauthentic report(s)" once the first awards land; if not, fix `evidence.FIRST_RE`.

## 7. Fewer locked hours, more teams at full rate (todo/26, 2026-10-22)

todo/26. The first full day showed the cycle model of §2 was right about locks: Blue stopped on a lock, not a cap, with 43 targets ready.

### Before: Sydney day 22 Oct up to 00:15 UTC (8:15am Perth)

| Measure | Value | Source |
|---|---|---|
| Filed | 52 (46 posts, 6 accounts) | `data/blue_state.json` |
| Post rulings | 44 hidden, 2 genuine (96%) | same |
| Genuine by class | like ring only: 2 of 19. Reply ring (24) and like ring + early ring (3): 0 | `logs/blue_reports.jsonl` |
| Blue awards paid | 49: 42 at full rate (86%), 7 at ×0.5 | portal points log |
| Paid as first | 43 of 44 post awards | portal |
| Clusters (teams) reported | 7, five of them already at 5–10 awards for the day | `blue_status.json` |
| Locked | 18:31→02:00 UTC, **7.5 h** (the platform's own times). Our ledger saw only 6 h: `#155963` was ruled genuine at 18:31, 1.5 h after filing (another team reported it too), and we only notice a genuine ruling at 3 h 15 min | the 403 answers in the log |
| Refused while locked | 4 retries, 30 min apart, all 403 | log |

### What changed

- **P(genuine) per post report** (`evidence.p_genuine`): 10% for a like ring alone (the scoring page's error rate), ×0.4 with a reply ring, ×0.7 with a second class, ×0.6 if the moderator already hid a post by the author, ×0.85 with an id run of 10+, ×1.4 for a small, slow like ring (< 30 likes, no 60-s burst of 8, like `#155963`). Expected value counts it: `(1 − P(genuine)) × (25 or 5) × rate`. It's logged on each report (`pg`) and the dashboard shows "genuine against expected" over the rulings.
- **A bar when plenty is ready** (superseded 22 Oct by the no-lock mode, §8): with 10+ targets ready, a post report must be under **6%** P(genuine) to file. In practice reply rings, and like rings with a second class plus an id run or an author already hidden; a like ring alone by an author with nothing hidden yet waits. On 22 Oct's ready list that keeps 26 of 40. With 25 pending, the chance a batch ends with no genuine ruling goes from about 0.9²⁵ ≈ 7% to about 30% (that list's first 25), if the factors hold.
- **The lock's exact end:** the platform's 403 says "reporting is suspended for your team until …". We now take that time as the lock (no more 30-min retries) and cut the recorded locked hours to it. When we detect a genuine ruling ourselves, our lock is an upper bound (ruling ≤ 3 h after the first report), so one report goes out at once: the answer gives the exact end, often earlier than our estimate. Cost: one refused request per genuine ruling.
- **More teams at full rate:** account leads file first (no lock risk). In the ranking, each award already counted against a cluster today lowers its next report by 4% while it's still at full rate, so new clusters go first. On 22 Oct's list: the 3 new clusters (c6628, c2576, c8601) come before c6831's 5th report.
- **Wider discovery, with no extra feed read:** Latest as the bot already read it (`data/latest_snapshot.json`, replies and reposts included). A post that collects 4+ team replies or reposts in that window is a ring forming: a known post whose audits found nothing gets one more audit; an unknown one (older than the snapshot) is looked up with `get_post` (8 per pass at most, its own 300/min route) and noted if a team wrote it. Citizens' posts are skipped: on 22 Oct their replies came from many teams, 1–3 each, which is no ring. The targeter's own thread reads aren't saved anywhere swan-blue can read; using them would need a `swan_bot` change.
- **Account leads from other teams' hides:** every 30 min, up to 80 ring posts **and reply-ring replies** we didn't report are checked for a 404 (each at most every 2 h, never-checked first). A hidden one makes its author a lead, the reply authors included; before, only ring roots were checked, and always the same first 40.
- **Our own accounts:** the swarm's accounts (`secrets/swarm_accounts.json`) now count as ours, so they're never counted, labelled or reported. Citizens added mid-game (`config.EXTRA_CITIZEN_RANGES`) are never team accounts.
- **Dashboard:** the Blue line reads "locked until HH:MM Perth (why) · N ready" ("at most" while it's our estimate). The days table has a "Full rate" column (awards at full rate out of all, from the portal log). The counts line gives clusters today and how many are still at full rate.

### After: to fill in on 23 Oct (from the dashboard's days table and `logs/blue_reports.jsonl`)

| Measure | 22 Oct (before) | 23 Oct |
|---|---|---|
| Hours locked | 7.5 h by 10am Perth (6 h in our ledger) | |
| Genuine rulings / post rulings | 2 / 46 | |
| P(genuine) check: genuine vs expected | n/a | |
| Awards at full rate | 42 / 49 (86%) | |
| Clusters paid | 7 | |
| Rings found by widening (`"act": "widen"`) and leads from others' hides (`"act": "lead"`) | n/a | |

## 8. Blue without locks (todo/28, 2026-10-22)

Marc's bar: Blue runs unattended and earns as few "genuine" rulings as the rules allow (each locks **all** our reporting for 6 h). The floor is the moderator, not our evidence: it is wrong about 1 in 10 either way (scoring page, 20 Oct). Only two routes go under that: account reports (a dismissed one can't lock us) and the evidence classes the rulings show are safer.

### The genuine risk per evidence class (measured 2026-10-22 05:20 UTC)

Every post ruling so far: 59 (21 Oct 13:46 → 22 Oct 05:20 UTC), 57 hidden, 2 genuine. Source: `logs/blue_reports.jsonl` and `data/blue_state.json` on the box, read offline from copies (the running tally per class is `pg_by_class` in `blue_status.json`). "Estimate" is the Jeffreys mean, (genuine + ½) / (n + 1); "95% upper" is the rule of three (3/n) when none was genuine.

| Class | Genuine / rulings | Estimate | 95% upper bound |
|---|---|---|---|
| **Reply ring** (the root, or one of its ring replies) | **0 / 34** (31 of them replies) | **1.4%** | 9% |
| Like ring alone | **2 / 19** | 12.5% | (observed 11%) |
| Like ring + early ring | 0 / 6 | 7% | 50% |
| Account reports | 5 of 6 ruled were upheld (portal); a dismissed one costs nothing | none can lock | |

The same 59 by other cuts (none of them separates risk the way the class does):

| Cut | Genuine / rulings |
|---|---|
| Post age at filing ≤ 30 min / 31–60 / 61–180 / > 180 | 1/16 · 0/31 · 1/10 · 0/2 (the 0/31 is mostly reply-ring replies) |
| Trending root / Latest or author root / ring reply | 1/13 · 1/15 · 0/31 |
| Ruled in < 2 h (2+ teams reported it) / at ~3 h (us alone) | 1/10 (#155963, ruled at 1.5 h by the platform's lock time) · 1/49 |
| Id run of 10+ among its accounts / none | 2/30 · 0/29 (no support, so the factor is gone) |
| Author already had a post hidden | 0/2 (too few to say) |
| `pg` at filing, recomputed with the old (todo/26) model: ≤ 4% / 6–10% / > 10% | 0/34 · 1/18 · 1/6 |

**Calibration.** The todo/26 model predicted 3.2 genuine over these 59 and 2 came; the 13 reports that logged `pg` at filing (22 Oct) predicted 0.55 and got 0. Too few rulings to say more than "not badly off". The new factors (`evidence.PG_FACTORS`): like ring 10%, like ring + a second class 7%, reply ring **2%** (was 4%), author hidden ×0.6 (unmeasured), small slow like ring ×1.4; the id-run factor is dropped. The dashboard gets `pg_by_class` (rulings, genuine, expected per class) in `blue_status.json` to keep checking.

**1% is not demonstrable for post reports.** The safest class has 0 genuine in 34; that is consistent with 1–2% but also with up to 9%. Showing 1% would take about 300 clean rulings of one class. And the todo's target doesn't add up: 70 post reports a day at 1–2% is 5–10 genuine a week, not 2–3; 2–3 a week at 70 a day needs 0.5% a report, which no class can show. So the volume of post reports has to be capped as well as their class.

### The no-lock mode (the default since 22 Oct 05:17 UTC)

- **Account reports always first.** They can't lock us. 55 account leads were ready on 22 Oct; most wait behind the per-team daily rate (11+ awards a team pay 10%) and file at full rate after the Sydney midnight.
- **Post reports only at P(genuine) ≤ `BLUE_POST_PG_MAX`** (default **2%**): reply rings and their ring replies. No like ring files as a post report, whatever its size.
- **Only when worth the lock they risk:** expected points ≥ P(genuine) × 300 (a 6 h lock is about a quarter of a ~1,200-point Blue day). A 2% report must be worth 6+, so reports at the 10% daily rate (2.3) never go.
- **A risk bucket:** post reports may take on `BLUE_PG_PER_DAY` expected genuine rulings a day (default **0.4**, about 3 a week, the todo's bar). It refills continuously and holds a quarter of a day's worth (0.1, five 2% reports), so post reports spread over the day instead of going in one burst.
- **The last pending slot** of the 30 is an account report's.
- **Never our own content** (Marc, 22 Oct): `file()` re-reads our ids (voices, boosters, swarm) and asks the platform who wrote the post; one of ours is refused, logged `"refused": "own account"` and alerted. A post with 3+ of our accounts among its likers or repliers is never post-reported (the report would point the moderator at our boosters). The 22 Oct audit: 0 of 199 report-log lines touched our 54 accounts; our boosters had liked #141107, a ring post we then reported correctly.
- Settings: `BLUE_POST_PG_MAX=0.02` and `BLUE_PG_PER_DAY=0.4` in `.env` on the box (loaded when swan-blue starts: set them, then restart it). `BLUE_PG_PER_DAY=1.0` roughly restores the todo/26 volume of reply-ring reports.

### What it costs (estimates; the first 24 h will measure it)

| Policy | Post reports a day | Genuine a day (expected) | Locked h a day | Blue points a day |
|---|---|---|---|---|
| todo/26 (6% bar when 10+ ready), measured 21 Oct 13:46 → 22 Oct 05:20 UTC | ~70 | 2 in the first 15 h | 7.5 h in the first 15 h | ~1,120 in 15.5 h (44 first, 3 later, 5 upheld account awards) |
| **No-lock, `BLUE_PG_PER_DAY=0.4` (default)** | ~20 (reply rings) | 0.4 (≈ 3 a week) | ~2.4 | ~750: posts ~350, accounts ~470, less the locked time |
| No-lock, `BLUE_PG_PER_DAY=1.0` | ~50 (reply rings worth ≥ 6) | 1 | ~6 | ~930 |

Assumptions: ~50 account leads a day (55 found in the first ~16 h), 5 of 6 upheld, 15 each; post reports paid first 94% of the time (44 of 47 so far); most awards at full or half rate (accounts take a team's first awards, so posts mostly land at half rate). The default trades roughly a third of Blue's points for about a fifth of the locked hours, which is what "as close to zero genuine rulings as the rules allow" asks. If points matter more than locks, `BLUE_PG_PER_DAY=1.0` is the lever.

### Co-reporting and new account leads

- **Time to ruling** is logged per post ruling (`hours`, and `co: true` under 2 h). The timer halves per extra team, so under 2 h means 2+ teams reported it. Its author becomes an account lead at once (flagged `co`), its ring's other posts are checked for hides first, and the harvest runs at the next tick. A genuine ruling takes its time from the platform's lock (`until − 6 h`), so co-reported genuine rulings show too. `blue_status.json` → `co: {fast, of}`.
- **Others' hides → account reports** (the multi-team boost): leads found from posts other teams got hidden (`"act": "lead"`, `by: "other"`) are authors at least one other team reported, so our account report on them is a second report.
- **Alert on every genuine ruling** with its evidence class, P(genuine) at filing, age and cluster, so the next one teaches us something.
