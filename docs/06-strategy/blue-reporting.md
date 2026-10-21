# Blue reporting: the greedy mechanism (2026-10-21)

How we turn the Blue rules into points, and why the code (`src/swan_blue`, `swan-blue.service`) works the way it does. Rules: [scoring §3](../03-scoring/scoring-guide.md#3-reporting-inauthentic-posts-and-accounts). Work item and status: [todo/07](../../todo/07-blue-reporting.md).

## 1. The limits, as they stand on 21 Oct

| Rule | Value | Source |
|---|---|---|
| Ruling time | 3 h after the first report, halved per extra team reporting | scoring page, 20 Oct PM |
| Moderator error | ~1 ruling in 10 is wrong (either way) | scoring page, 20 Oct PM (was 1 in 4) |
| A "genuine" ruling | no new reports, posts or accounts, for 6 h; pending ones still resolve. Overlapping locks run at the same time (they don't add up) | scoring §3; `#questions` 21 Oct |
| Pending reports | ≤ 25 per team | Discord, 20 Oct |
| Post report | 25 if our team was **first**, 5 if later (first 5 teams only) | scoring §3 |
| Account report | 15 to **every** team with an open report, if at ruling the account has ≥ 1 moderator-hidden post and ≥ 100 actions. Otherwise dismissed: **no points and no lock** | scoring §3 |
| Per target team per Sydney day | awards 1–5 full, 6–10 half, 11+ 10% (posts and accounts together) | scoring §3 |
| Report routes | 3/min each, a budget of their own (not the posting budget) | api-reference |

## 2. What follows from them

- **Finding targets is easy.** Every account with an id above 2343 was registered after launch, so it belongs to a team. On 21 Oct, every Trending post we scored had 83–100% of its likes from team accounts. 18–23-account reply rings that finish within 15–35 minutes are common.
- **Locks set the pace, not the reports.** With 25 pending and 1 in 10 rulings wrong, the chance that a batch has no "genuine" ruling is 0.9²⁵ ≈ 7%. So nearly every batch ends in a 6 h lock, and the cycle is about 3 h of rulings plus 6 h locked.
- **The points come from refilling every slot the moment we may**, around the clock, with the best targets first. A model of that cycle (fill to 25, rule at 3 h, lock 6 h on a genuine ruling) gives about **70 reports and 1,200 points a day**. Being first only half the time drops it to about 870. Spreading over 40 teams instead of 12 adds about 70. So freshness matters most, then refilling at once.
- **Account reports are free money** whenever an account qualifies: there's no moderator error and no lock risk. The authors of ring posts, including reply-ring replies, are the accounts that can qualify. Like-only ring accounts never post, so they can't be suspended.
- **First matters for posts only.** It's order, not time: 25 for the first team, 5 for any later one. So we report posts young, under an hour old, and watch the timelines of known ring authors to catch their next post early.

## 3. The mechanism

```
scan (reads only)                    rank                                fill
 Trending every 10 min ─┐            each candidate:                     while not locked and pending < 25:
 Latest every 3 min ────┼─ team-     EV = 0.9 × (25·P(first)+5·(1−P))     file the best EV first
 ring authors' posts ───┘  account   × team's daily rate × strength       (approve mode: only approved posts;
   every 5 min              posts    account EV = 0.95 × 15 × rate         account reports always)
        │                 audit at 10 min (and 45 min):  ↑ team count updated after each pick
        └──────────────── likers, replies, timing  ──→ like ring / reply ring? → cluster label
rulings every 10 min: 404 = hidden (inauthentic) → its author is an account-report lead
                      still visible 3 h 15 min after filing = genuine → locked until filing + 9 h
harvest every 30 min: leads (and ring posts someone else got hidden) with ≥ 100 actions → account candidates
```

- **Evidence (a report needs one):** a *like ring* (≥ 20 team likes, ≥ 85% of all likes, half in the first 30 min or ≥ 8 inside 60 s) or a *reply ring* (≥ 10 replies from ≥ 6 team accounts within 60 min). Citizens, verified accounts (ids 1–11) and our own accounts are never targets, and our accounts are left out of every count. The detail text states only measured numbers (likes, timing, id runs), never the post's side (rules §5.2.2, LS.6.5).
- **Clusters stand in for teams.** Accounts that like and reply to the same posts share a label, which is kept across scans, and the daily rate is counted per label. It's a proxy: one team can show up as two clusters, which costs a little rate, never a rule breach.
- **P(first)** is a guess: 0.9 under 1 h old, 0.6 under 3 h, 0.3 older, ×0.7 when the post is on Trending (more teams see it). Posts over 12 h old aren't reported.
- **Modes.** *approve* until 10 post rulings are in and ≥ 70% came back inauthentic. If our targets are all bots we expect ~90%: observed rate = 0.1 + 0.8 × (share of our targets that are bots). *auto* after that. It drops back to *approve* and alerts if the rate falls under 70%. *off* when `~/ctn/BLUE_OFF` exists. Account reports file in both approve and auto: they're rule-based and can't lock us.
- **Refused reports.** 400/404/409 drop that one target. 401 logs in again. Anything else (most likely the 6 h lock or the pending cap) waits 30 min and alerts once. A refused report still costs budget, so we never retry in a loop.
- **The reporter** is one booster: the lowest-id active one (`config.blue_reporter`, `salote_sails` on 21 Oct). The bot stops using it. It would register a replacement booster, but on 21 Oct it was already at its cap of 49 live accounts (15 voices, 33 boosters, the reporter), so the like pool is one smaller (33).

## 4. What it costs Red (kept small)

- **Write budget: none.** Report routes have their own budget.
- **Accounts:** one booster leaves the like pool: 33 likers instead of 34 while the bot is at its live-account cap (otherwise its drip registration replaces it).
- **Reads:** about 0.6 feed calls a minute of the team's 10 (it backs off when fewer than 4 are left), and under 150 other reads a minute against 300 per endpoint.
- **Our own exposure is unchanged by this code, but rising.** The organisers are pushing every team into Blue, and our hourly heavy post (one post plus 15–20 thread replies from voices) matches the same two evidence classes. Boosters can't be suspended; voices can. `swan_watch` already takes a voice off amplified posts after 1 hidden post and stops it at 2. Whether to cut thread replies is a Red decision, not a Blue one (decided 2026-10-22: amplification paused, see [direction-2026-10-21](direction-2026-10-21.md)).
- **Upside for Red:** hiding ring posts on Trending frees places there and lowers the cutoff for our amplified posts.

## 5. Running it

- Dashboard, **Blue** section: mode, pending x/25, lock and next ruling, today's rulings and Blue points (from the portal points log), and in approve mode the reports waiting, each with a one-line summary of its evidence. One command approves them all: `ssh swan-ec2 'ctn/scripts/blue.sh approve all'`. The banner turns amber when something waits or swan-blue goes quiet.
- Stop filing: `ssh swan-ec2 'touch ctn/BLUE_OFF'` (rm to resume; the scan and rulings carry on). Stop everything: `sudo systemctl stop swan-blue`.
- Records: `logs/blue_reports.jsonl` (every report with its evidence, detail text, reporter and owner; rulings, locks, mode changes); state in `data/blue_state.json`. A dry run (`cd src && python -m swan_blue`) uses its own `.dry.json` files and files nothing.
- Account-report outcomes don't show through the API: a suspended account still reads as normal (checked on @lani_wharfcafe23, 21 Oct). Read them from the portal points log ("Moderation" lines).

## 6. Assumptions to check with the first rulings

1. The 25 cap counts account reports too (we assume yes) and an over-cap report is refused with some 4xx. Open question B.11.
2. The daily rate counts on the **ruling** day (open question B.10).
3. A ruled-inauthentic post answers 404, as our own hidden posts do. A post its author deleted also answers 404, and we count that as hidden. The portal points log is the ground truth.
4. Tune `evidence.p_first` from the portal: what share of our hidden posts paid 25 rather than 5.
