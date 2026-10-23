# Blue reporting: the greedy mechanism (2026-10-21)

How we turn the Blue rules into points, and why the code (`src/swan_blue`, `swan-blue.service`) works the way it does. Rules: [scoring §3](../03-scoring/scoring-guide.md#3-reporting-inauthentic-posts-and-accounts). Work item and status: todo/07.

## 1. The limits, as they stand on 21 Oct (cap and multi-team boost updated 22 Oct)

| Rule | Value | Source |
|---|---|---|
| Ruling time | 3 h after the first report, halved per extra team reporting | scoring page, 20 Oct PM |
| Several teams reporting | the automod "gets a boost to accuracy if a post or account has been reported by multiple teams" | Discord, 22 Oct |
| Moderator error | ~1 ruling in 10 is wrong (either way) | scoring page, 20 Oct PM (was 1 in 4) |
| A "genuine" ruling | no new reports, posts or accounts, for 6 h; pending ones still resolve. Overlapping locks run at the same time (they don't add up) | scoring §3; `#questions` 21 Oct |
| Pending reports | ≤ **30** per team (25 until 22 Oct). We keep the 30th for an account report. Whether account reports count toward it: probed once from behaviour (todo/28, Marc 22 Oct): the first time 30 are pending with an account lead ready, one extra account report goes out; taken = they don't count (accounts then file beyond 30), refused naming the cap = they do. **Observed 22 Oct (not confirmed by organisers): account reports count.** The probe at 14:18 UTC was taken, which first read as "they don't count"; at 14:26 the platform refused with *"your team already has 30 reports awaiting a moderator's ruling"* while we held only 5 post reports (and 30 account reports by our ledger). Our ledger overcounts: account reports can be ruled before the 3 h we assume and we can't see it, so the probe's slot was really free. The service corrects itself on that refusal (`cap_full`), holds 10 min without a lock, and when our ledger says full it still tries one report every 10 min | Discord, 22 Oct (was 25, 20 Oct); our probe and the platform's refusal, 22 Oct 14:18–14:26 UTC |
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
   every 5 min              posts    account EV = 0.9 × 15 × rate (§10)    account reports always)
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

### The genuine risk per evidence class (measured 2026-10-22 10:00 UTC)

Every post ruling so far: 86 (21 Oct 13:46 → 22 Oct 10:00 UTC), 82 hidden, 4 genuine. Source: `logs/blue_reports.jsonl` and `data/blue_state.json` on the box, read offline from copies (the running tally per class is `pg_by_class` in `blue_status.json`). "Estimate" is the Jeffreys mean, (genuine + ½) / (n + 1); "95% upper" is the rule of three (3/n) when none was genuine.

| Class | Genuine / rulings | Estimate | Note |
|---|---|---|---|
| **Reply ring** (the root, or one of its ring replies) | **2 / 56** (51 of them replies) | **4.4%** (observed 3.6%) | 0 / 34 at 05:20 UTC, which looked like 1.4%; then #185124 (filed 03:33) and #190875 (filed 05:07, a 10%-rate report) came back genuine |
| Like ring alone | **2 / 20** | 12% (observed 10%) | the scoring page's "1 in 10" |
| Like ring + early ring | 0 / 10 | 4.5% | 95% upper bound 30% |
| Account reports | 7 upheld (portal) of 13 ruled | none can lock | a dismissed one costs nothing |

The same 86 by other cuts (none separates risk well):

| Cut | Genuine / rulings |
|---|---|
| Post age at filing ≤ 30 min / 31–60 / 61–180 / > 180 | 3/26 · 0/43 · 1/12 · 0/5 |
| Trending root / Latest or author root / ring reply | 1/14 · 1/21 · 2/51 |
| Ruled in < 2 h (2+ teams reported it) / at ~3 h (us alone) | **2/13** (#155963 at 1.5 h, #190875 at 1.44 h, by the platform's lock times) · 2/73 |
| Id run of 10+ among its accounts / none | 3/38 · 1/48 (no support: the factor is gone) |
| Author already had a post hidden / not | 1/8 · 3/78 (no support: the factor is gone) |

**Co-reported posts are not safer.** Both genuine rulings that came in under 2 h had 2+ teams on them, one of them (#190875) after the 22 Oct "boost to accuracy". 2 of 13 is too few to say they're riskier, but nothing says the boost protects a post report.

**Calibration.** Recomputed over all 86 with the todo/26 factors, the model predicted 3.9 genuine and 4 came; the 40 reports that logged `pg` at filing predicted 1.6 and got 2. Right overall, but it can't tell the classes apart beyond "like ring alone ≈ 10%, anything with a second signal ≈ 4%". New factors (`evidence.PG_FACTORS`, 10:00 UTC): like ring 10%, like ring + a second class 7%, reply ring **4%**, small slow like ring ×1.4; the id-run and author-hidden factors are gone.

**1–2% is unreachable for post reports.** The safest class is about 4% (2 of 56; 95% interval roughly 0.4–12%), and no cut of our data goes lower. Showing 1% would take about 300 clean rulings of one class. The todo's target doesn't add up either: 70 post reports a day at 1–2% is 5–10 genuine a week, not 2–3; 2–3 a week at 70 a day needs 0.5% a report. So the no-lock mode caps the **volume** of post reports as well as their class, and runs accounts first.

### The no-lock mode (the default since 22 Oct 05:17 UTC; recalibrated 10:00 UTC)

- **Account reports always first.** They can't lock us. 102 account leads were ready at 10:00 UTC; most wait behind the per-team daily rate (11+ awards a team pay 10%) and file at full rate after the Sydney midnight.
- **Post reports only at P(genuine) ≤ `BLUE_POST_PG_MAX`** (default **4%**, was 2% until 10:00 UTC): reply rings and their ring replies, the safest class measured. No like ring files as a post report, whatever its size.
- **Only when worth the lock they risk:** expected points ≥ P(genuine) × 300 (a 6 h lock is about a quarter of a ~1,200-point Blue day). A 4% report must be worth 12+, so only full-rate reports go; a 10%-rate one (2.3, like #190875) never does.
- **A risk bucket:** post reports may take on `BLUE_PG_PER_DAY` expected genuine rulings a day (default **0.4**, about 3 a week, the todo's bar): about 10 reply-ring reports a day. It refills continuously and holds a quarter of a day's worth (0.1, two 4% reports), so they spread over the day.
- **The last pending slot** of the 30 is an account report's (account reports count toward the 30: §1).
- **Yes-side targets first** (Marc, 22 Oct): hiding a Yes team's ring post also takes pro-Yes content off the feed, and the referendum pool goes to the winning side only. `swan_blue/side.py` reads the side from the ring root's text (`swan_bot.targeting`'s vote phrases, read-only, plus each side's tags and slogans; no LLM) and the ranking multiplies by `BLUE_SIDE_BIAS` = yes 1.3, unclear 1.0, no 0.7. Ranking only: every target still needs the same evidence, No-side and unclear targets still fill the slots when the Yes ones run out or pay ×0.1, and **the side never reaches the detail text** (rules §5.2.2, LS.6.5). Each report logs its `side`; `blue_status.json` → `today.sides`. On 22 Oct's ring posts: 220 Yes, 196 unclear, 77 No.
- **Never our own content** (Marc, 22 Oct): `file()` re-reads our ids (voices, boosters, swarm) and asks the platform who wrote the post; one of ours is refused, logged `"refused": "own account"` and alerted. A post with 3+ of our accounts among its likers or repliers is never post-reported (the report would point the moderator at our boosters). The 22 Oct audit: 0 of 199 report-log lines touched our 54 accounts; our boosters had liked #141107, a ring post we then reported correctly.
- Settings: `BLUE_POST_PG_MAX=0.04` and `BLUE_PG_PER_DAY=0.4` in `.env` on the box (loaded when swan-blue starts: set them, then restart it). `BLUE_POST_PG_MAX=0` files accounts only (zero lock risk); `BLUE_PG_PER_DAY=1.0` roughly restores the todo/26 volume of reply-ring reports.

### What it costs (estimates; the first 24 h will measure it)

| Policy | Post reports a day | Genuine a day (expected) | Locked h a day | Blue points a day |
|---|---|---|---|---|
| todo/26 (6% bar when 10+ ready), measured 21 Oct 13:46 → 22 Oct 05:20 UTC | ~70 | 2 in the first 15 h, 2 more from its last reports | 7.5 h, then 06:33 → 14:08 UTC on 22 Oct | ~1,120 in 15.5 h (44 first, 3 later, 5 upheld account awards) |
| **No-lock (default: 4%, 0.4 a day)** | ~10 (full-rate reply rings) | 0.4 (≈ 3 a week) | ~2.4 | ~650: posts ~230, accounts ~470 at 5 of 6 upheld (7 of 13 so far, so maybe ~350), less the locked time |
| No-lock, `BLUE_PG_PER_DAY=1.0` | ~25 | 1 | ~6 | ~800 |
| Accounts only (`BLUE_POST_PG_MAX=0`) | 0 | 0 | 0 | ~350–470 |

Assumptions: ~50 account leads a day that reach 100 actions (55 found in the first ~16 h, 102 by 10:00 UTC), 15 each; post reports paid first 94% of the time (44 of 47 on 21 Oct); most awards at full or half rate. On 22 Oct the per-team daily rate already bit hard: 13 first reports paid ×0.5 and 10 paid ×0.1 by 08:19 UTC. The default trades roughly 40% of Blue's points for about a third of the locked hours, which is what "as close to zero genuine rulings as the rules allow" asks. If points matter more than locks, `BLUE_PG_PER_DAY=1.0` is the lever; if locks matter more, `BLUE_POST_PG_MAX=0`.

### Co-reporting and new account leads

- **Time to ruling** is logged per post ruling (`hours`, and `co: true` under 2 h). The timer halves per extra team, so under 2 h means 2+ teams reported it. Its author becomes an account lead at once (flagged `co`), its ring's other posts are checked for hides first, and the harvest runs at the next tick. A genuine ruling takes its time from the platform's lock (`until − 6 h`), so co-reported genuine rulings show too. `blue_status.json` → `co: {fast, of}`.
- **Others' hides → account reports** (the multi-team boost): leads found from posts other teams got hidden (`"act": "lead"`, `by: "other"`) are authors at least one other team reported, so our account report on them is a second report.
- **Alert on every genuine ruling** with its evidence class, P(genuine) at filing, age and cluster, so the next one teaches us something.
- **New account-lead detectors** (`swan_blue/detect.py`, accounts only, never a post report until each has 10+ rulings behind it). They read only the bot's Latest snapshot plus up to 10 profile reads per 15 min:
  - *one wording*: a 6-word sequence (links, @mentions, #tags left out; the setting's facts and frames, which every team quotes, excluded) from 5+ team accounts within 24 h. A 1-in-4 hash sample of each post's sequences keeps memory small; a template has many sequences, so it survives. The first 15 min of Latest on 22 Oct found one: "Common sense and public hospital investment are the only viable path forward for our community" from 15 accounts (ids 6619–10045), and a slot template ("Working early shifts (<bio>) teaches you what everyday folks face") on two;
  - *cadence*: active in 20+ of the last 24 hours with 40+ posts seen, or 20+ posts seen inside one hour (Latest is sampled, so lower bounds);
  - *registration block*: inside a one-wording group, 5+ accounts created within 30 minutes of each other (the platform's `created_at`), and the username shape most share (`mira_solis_kc` → `w_w_2`).
  A flagged account is watched for 3 days: its recent posts are checked for a hide (30 per harvest round, each once per 2 h). A hidden one makes it an account lead (`"act": "lead", "by": "watch"`); it still only files at 100+ actions, and its detail states the detector's measured numbers instead of the ring clause. `blue_status.json` → `detect.by.<kind>` = accounts watched, with a hidden post, reported (the support each detector earns).

## 9. The no-lock mode relaxed (Marc, 23 Oct 2026)

The no-lock mode (§8) cost more than it saved. From the 23 Oct 09:00 UTC data (`logs/blue_reports.jsonl`, `data/portal.json`):

| | 22 Oct | 23 Oct (20 h of 24) |
|---|---|---|
| Filed | 99 (86 post) | 81 (14 post, 67 account) |
| First-report awards paid | 78 | 9 |
| Upheld account reports | 7 | 32 of 67 ruled (about half dismissed), mostly ×0.5 |
| Genuine post rulings | 4 | 3 of 14 |
| Hours locked | 12.5 | 10.7 |
| Blue points (estimated from award counts; the portal log mixes them into hourly rows) | about 1,200 | about 500 |

- **Class doesn't separate risk.** All 100 post rulings: 7 genuine. Reply rings 5 of 64 (8%), like rings 2 of 20, like ring + early ring 0 of 10. The 4% for reply rings (§8) was a small-sample low. `PG_BASE` is now 0.08 for every class.
- **A lock only stops new filings.** Pending reports still pay. The cap on points is each target team's 5 full-rate awards a day (4 of 12 clusters still at full rate on 23 Oct), so more volume against the same teams pays 10%.
- **Accounts first starved the posts.** Account leads filled the 30 slots (67 of 81 reports) at about 7 points each (15 × 0.5 upheld, mostly at half rate) while 25-point post reports waited. Posts and accounts now share one ranking by expected value (`ACCOUNT_UPHELD` = 0.5).
- **Post age.** Filed at 60 min or under: 3 genuine of 76. Over 60 min: 4 of 24 (Fisher p = 0.055; suggestive, not proven). Three of 23 Oct's genuine rulings were posts 67–131 min old, filed the minute the last lock ended.

What changed (`service.py`, `evidence.py`):
1. The class gate (`BLUE_POST_PG_MAX`) and the daily risk bucket (`BLUE_PG_PER_DAY`) are off by default. They still work when set in `.env`. **The box's `.env` had `BLUE_PG_PER_DAY=1.0`: remove it, or the bucket stays on.**
2. A post is post-reported only up to `POST_MAX_AGE_MIN` = 60 min old. The fresh-reserve rule is gone (nothing old files).
3. "Worth the lock": ev ≥ pg × `LOCK_COST`, with pg 8% and `LOCK_COST` 150 (was 300): a fresh full-rate report (about 20) files, a half-rate one (about 10) doesn't.
4. Front-loading at the Sydney reset needed no new code: `counts_today` counts by the day a report is *ruled* (open question B.10: assumed, not confirmed), so from 3 h before Sydney midnight (6pm Perth) every team is back at full rate for what we file. With the gates off, the fill takes the 30 slots with the best fresh full-rate reports as soon as we are unlocked.
5. Widening for new teams: unchanged. Rank spreading (`SPREAD`) already puts new clusters first, and the account-lead detectors (§8) are the route for rings that are not ring posts.

To check on 24 Oct against the table above: post reports filed, genuine per post ruling (expect about 8%), hours locked, first-report awards, and whether `ready_ok` is now close to `ready`. (Done for 24 Oct in the §10 table, which also adds the liveness and fleet measures.)

## 10. Live targets: liveness filter, live-lead scanner, fleets (todo/43, 2026-10-24)

Work item: [todo/43](../../todo/43-blue-live-targets.md); evidence: [rival-census-2026-10-23](rival-census-2026-10-23.md). Code: `swan_blue/{service,evidence,scan,fleets}.py`; offline tools `scripts/blue_fleet_eval.py`, `scripts/blue_scan_eval.py`. Built and tested against fakes only on 24 Oct; **nothing here has run against the real platform** (the first live numbers go in the table at the end).

**Why.** Of our 89 account reports on 23 Oct, 46 (52%) were on accounts already idle for over 3 h at filing (27 over 12 h), and all 37 filed while the account was active (last post an hour or less before) had stopped posting by the ruling. So the 0.5 in `ACCOUNT_UPHELD` was the idle waste, not the live rate. Live supply was thin (21 of 189 unreported leads had posted in the previous 2 h), so the filter alone would only shrink Blue; the scanner and the sibling checks widen the supply of live leads. Fleets replace the 16 clusters as the unit of "one target team": c8701 holds 450 accounts, more than a team's 200, so it showed "saturated".

### What changed, and how to turn each part off

| Part | Default | Setting (in `.env` on the box; read when swan-blue starts) | Off |
|---|---|---|---|
| **Liveness filter** on account reports: the account's newest post is read right before filing (`account_posts(limit=1)`, the 300/min read route, not the report budget); skipped unless it posted within the window | **on, 2 h** | `BLUE_ACCOUNT_LIVE_H=2` | `0` (no filter, priced at the old 0.5) |
| **Live-lead scanner** (reads only): a pass every 3 h re-reads the newest 50 posts of each live rival account (40 reads a minute at most) and logs/lists leads | **on** | `BLUE_SCAN_EVERY_S=10800` | `0` |
| **Filing from the scanner and siblings** | **off** | `BLUE_SCAN_FILE=0` | `1` turns filing on |
| **Sibling checks**: the fleet mates of a live lead are read first (5 a tick) | on (needs the scanner and the account list) | `BLUE_SIBLINGS=1` | `0` |
| **Fleets**: the platform account list is read (100 a page, about 105 reads) every 6 h; awards are counted per fleet | **on** | `BLUE_FLEET_EVERY_S=21600`, `BLUE_FLEET_GAP_S=30` | `BLUE_FLEET_EVERY_S=0` (Blue's cluster labels count teams, as before) |
| **Slot ordering** (below) | on | code: `evidence.ACCOUNT_CO_BOOST=1.3` | set it to `1.0` |

`BLUE_OFF`, approve mode, the 30-report cap (the last slot an account report's), the lock logic, "never our own accounts", dry runs and the report budgets are untouched. A dry run (`cd src && python -m swan_blue`) uses `*.dry.json` files for the new state as well and files nothing.

### 1. The liveness filter (`idle_h`)

- **At filing** (`live_at_filing`, after the own-account check): the newest post is read again now, because a lead may be hours old. Idle hours = the read time minus that post's time. Over `BLUE_ACCOUNT_LIVE_H` (or never posted): skipped, `{"act": "skip", "reason": "idle", "idle_h": ...}` in `logs/blue_reports.jsonl` (at most one line per account per hour), not recorded as refused (it may come back). A read from the same pass (under 60 s old) counts as the re-check.
- **Ranking**: `refresh_live` reads the ready leads' newest post, never-read first, 10 a tick, a live one again after 15 min, an idle one hourly (every 6 h once idle over 12 h). Only leads with a read under 30 min old and within the window are candidates: `unread` and `idle` ones wait. The harvest's own 100-post read also stamps the newest post time for free.
- **Pricing** (`evidence.account_ev`): a live account is `ACCOUNT_UPHELD` = **0.9** (EV 13.5 at full rate), an unknown one `ACCOUNT_UPHELD_UNKNOWN` = 0.5 (7.5, the old behaviour). Unknown means the liveness read failed: the account is still a candidate, but a report on one goes out blind at most once per 10 min (`LIVE_BLIND_GAP_S`), the others wait for the next tick. When the read bucket is nearly spent (`READ_RESERVE`: under 60 of 300 left) or after 8 filing-time reads in a tick, the report waits; it never files blind for lack of budget.
- **Reading the log**: every `act: report` now has `idle_h` (hours since the account's last post, at the read made just before filing; `null` with `live: "unknown"` or `"off"`), `live`, `team` (the fleet or cluster counted) and `n_today` (that team's award count when it was picked). `blue_status.json` → `leads_live`: ready leads by state (`live`, `idle`, `unread`, `unknown`, `off`) and `idle_skips_today`.
- **The window is a guess until measured.** 2 h comes from "all 37 filed within an hour of the last post were gone by the ruling, 46 of 89 over 3 h were wasted". Nothing separates 1 h from 3 h yet. The portal gives upheld counts per hourly row, not per report, so the rate by idle bucket can only be read where a row's rulings (filed 3 h earlier) fall in one bucket; to split 1-2 h from 2-3 h, run a day at `BLUE_ACCOUNT_LIVE_H=3` and compare. Keep `ACCOUNT_UPHELD` at 0.9 until a day of live reports says otherwise.

### 2. The live-lead scanner (`scan.py`, `Blue.scan_step`)

- **Tracked**: team accounts (not ours, citizens or verified) the bot's Latest snapshot saw posting in the last 6 h, plus those with a live snapshot; capped at 1,500, newest posters first. A pass reads each once (`account_posts`, newest 50), 40 a minute at most and only while the read bucket is above `READ_RESERVE`. The 23 Oct census had **797** such accounts (30+ posts, last post within 6 h of the pull's end), so a pass is about 20 minutes.
- **Diff**: the snapshot is post ids only (at most 50 per account, compact JSON in `data/blue_scan.json`, about 0.5 MB at the cap). An id that was on the previous page and is missing now counts only if it should still be there: newer than the oldest id read, or the page holds the whole history. Posts pushed off the page by new ones are not candidates. An account with under 30 posts or not posting for 6 h is dropped.
- **Confirmation**: `get_post` must answer 404 on two reads at least 10 minutes apart; a 200 drops the candidate. Then it is a lead: `{"act": "lead", "by": "scan", "vanished": [...], "posts_per_h", "last_post", "fleet", "file"}` in the Blue log, and listed (newest 40) in `blue_status.json` → `scan.leads`, with `scan.stats` (passes, reads, vanished, confirmed, visible, siblings, errors).
- **What a lead means.** A hidden post vanishes from `account_posts`, **and so does one its author deleted**: from outside they look the same (both 404). Such an account report is dismissed (a slot for 3 h, never a lock). A five-team temporary hide may look the same too and be restored on a genuine ruling. So the detail says only what was measured: *"its post #N is no longer available, it has taken 100+ actions"* plus the measured pace (*"it has posted 50 times in the last 8.2 hours (about 6 an hour)"*) or a lockstep/detector clause **only if measured**. It never says the moderator hid it (that wording stays for leads the existing harvest established) and never mentions a side.
- **Filing, flag off (default)**: leads are logged and listed; nothing enters the filing path. **Flag on** (`BLUE_SCAN_FILE=1`): a lead found in the last 12 h joins the harvest (`by: scan` or `sibling`), which counts its actions (100+ needed, as for every lead), then the same ranked fill, liveness gate, cap and last-slot rule apply. A scan lead without a measured pattern (pace under 3 posts an hour on the page, no lockstep ring, no detector numbers) is not a candidate: the report would have nothing to state.
- **Test it on the second census snapshot before turning the flag on**: `python scripts/blue_scan_eval.py data/rival_census/rest.jsonl data/rival_census/rest-2026-10-24.jsonl --census data/rival_census/census.jsonl --ours data/rival_census/ours_all.json --page 100 --out live_leads.json`. It applies the same diff rule and prints the candidates, how many live accounts it could compare and candidates per hour. A 24 h gap hides vanished posts of fast posters (their old page has scrolled off), so read the count as a floor, and check a handful of candidates with `get_post` (expect 404) before trusting it. The baseline to beat is the 21 live leads of 189.

### 3. Slot value ordering (`Blue.ranked`)

Per target team (fleet) the first 5 awards pay in full, the 6th to 10th half, the 11th on 10%, posts and accounts counted together. The ranking already did the right thing once the numbers were honest; it is now written out in `ranked()` and tested:
1. A fresh ring post whose expected value pays for the lock (`ev >= pg x LOCK_COST`, about 21 against 12) goes first: 25 points for the first report.
2. Live account reports (13.5, no lock risk) fill the rest.
3. An account lead other teams are reporting ranks `ACCOUNT_CO_BOOST` (1.3) higher: our report on it was ruled in under 2 h (`co`), or another team's hide of its post was found in the last 2 h (`by: other`). The ruling then comes in half the time or less, so the slot turns over twice as fast, and an upheld report pays every team that reported. This weights the rank, not the points (EV stays 13.5).
4. From the 6th award a post no longer pays for its lock and an account is worth 6.75; from the 11th, 1.35 is under `MIN_EV`, so the fill moves to another team. `SPREAD` still puts teams with fewer awards first.

### 4. Fleets as the team proxy (`fleets.py`)

A fleet is a chain of team accounts in id order where each link is at most 5 ids and **30 s** from the one before (`FLEET_ID_GAP`, `FLEET_GAP_S`); a chain over 200 (a team's allowance) is cut at its largest time gaps. A private account has no `created_at` and rides with its neighbours. Ours are left out so they cannot bridge a rival's fleet. The key is `f<lowest id>`; a fleet of one with a cluster label counts under the label; with no account list yet, or `BLUE_FLEET_EVERY_S=0`, the label counts, as before.

**Validation** (`python scripts/blue_fleet_eval.py data/rival_census [--min-posts N]`, census of 23 Oct, pull ending 16:12 UTC). Dead = newest post 24 h or more before the end of the pull, alive = under 6 h. Same-fate share of the pairs inside a fleet, against the same pairs with the fate labels shuffled across accounts (30 shuffles; z = shuffle standard deviations above the mean):

| Accounts with | Labelled | Fleets (5 ids, 30 s): same fate | Shuffled | z | Pairs |
|---|---|---|---|---|---|
| 1+ posts | 3,219 | 69.6% | 50.8% | 43 | 27,845 |
| 10+ posts | 1,784 (742 dead) | 69.0% | 51.6% | 24 | 19,533 |
| 30+ posts | 1,345 (532 dead) | **76.0%** | 52.0% | 36 | 11,525 |

The old yardstick agrees: consecutive labelled ids up to 3 apart share a fate in 73% (10+ posts) to 77% (30+ posts) of 1,261 / 920 pairs. Blue's own clusters agree less: 63.5% against 51.4% shuffled (10+ posts, 34,310 pairs).

How the thresholds were chosen (10+ posts, id gap 5): the **time gap is the cut; the id gap barely matters** (ids are dense, the median gap between neighbours is 15 s). Same fate stays at 68-70% from 20 s to 60 s while the share of accounts in a fleet of 2+ climbs from 81% to 95%, then it falls (65% at 120 s); label agreement keeps falling with a looser gap.

| Time gap | Same fate | Fleets | In a fleet of 2+ | Same Blue label (chance 10.5%) |
|---|---|---|---|---|
| 10 s | 63.5% | 4,851 | 58% | 68% |
| 20 s | 69.3% | 2,992 | 81% | 56% |
| **30 s** | **69.0%** | **2,356** | **87%** | **58%** |
| 60 s | 68.1% | 1,224 | 95% | 52% |
| 120 s | 65.4% | 552 | 98% | 45% |
| none | 67.3% | 187 | 100% | 31% |

A single-id gap (neighbours only) is worse at the same time gap (64.1% at 30 s): other teams' registrations sit between a team's accounts. 30 s is where more time gap stops buying agreement and starts costing purity.

**What a fleet is, honestly: a registration batch, not a team.** The census has 7,910 team accounts in 2,356 fleets (1,312 of 2+ accounts, median 3, 90th percentile 8, largest 198; 37% of accounts sit in fleets of 10+) against about 157 teams, so one team is roughly 15 fleets. Teams that register in bursts show whole (cluster c3370: 147 of 187 accounts in 5 fleets of up to 50); drip registrars scatter (c6604: 219 accounts in 175 fleets; c8701's 450 in 185). Consequences:
- Counting per fleet **undercounts** a team that is spread over many fleets: a second fleet of the same team looks fresh while the team is already past its 5 full awards, and those reports pay half. Cluster counts overcounted (c8701). Neither is right; fleets are better where the batch is the team and where clusters over-merge, and they fate-agree better than the clusters do.
- Check it from the table below: the share of reports filed with `n_today` under 5 that the portal paid at a reduced rate (`Moderation (x0.5 points)` lines, `awards_by_rate`). If a third or more of the reports Blue believed full-rate are paid reduced, loosen the gap (`BLUE_FLEET_GAP_S=120`, 552 fleets) or key on the cluster label too.

### 5. Sibling checks

When a lead is read live and its fleet is known (or the scanner confirms one), the fleet's other accounts (up to 30, those the bot's Latest snapshot saw lately first; once per fleet per 6 h) are queued and read before the scan's own list, 5 a tick. A post the bot saw a sibling write 30+ minutes ago (`detect` keeps the last 6 ids per account) that is missing from its page now is a vanished-post candidate and goes through the same two-404 confirmation; its lead is `by: sibling` and files only under `BLUE_SCAN_FILE=1`. Logged as `{"act": "siblings", ...}` and `{"act": "scan", "src": "sibling"}`.

### After: to fill in on 25 Oct (24 Oct is the first day with this code; the 23 Oct column is §9's)

| Measure | 23 Oct | 24 Oct (from the deploy) | 25 Oct |
|---|---|---|---|
| Account reports filed / upheld (portal "upheld account reports") | 89 / about half | | |
| Filed with `idle_h` over `BLUE_ACCOUNT_LIVE_H` (expect 0), and with `live: unknown` | 46 over 3 h | | |
| `idle_skips_today`; `leads_live` live / idle / unread at a quiet hour | n/a | | |
| Upheld rate of live reports (upheld / ruled; by idle bucket where one row's rulings are one bucket) | n/a | | |
| Scan: passes, reads a minute, candidates, confirmed leads (`scan.stats`), by `scan` / `sibling` | n/a | | |
| Scan leads judged by hand: of 10, how many 404 on `get_post`; how many the author deleted | n/a | | |
| Live account leads ready at once (`ready_accounts`) | 15 | | |
| Reports with `n_today` under 5 that the portal paid reduced (fleet undercount) | n/a | | |
| Teams (fleets) paid; awards at full rate; hours locked; genuine per post ruling | see §9 | | |

Turn `BLUE_SCAN_FILE=1` on only after the scan leads have been checked by hand and the offline run on the 24 Oct ~16:00 UTC census snapshot looks right.
