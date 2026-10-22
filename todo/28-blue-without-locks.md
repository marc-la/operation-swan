# 28: Blue without locks. Near-zero genuine rulings, more signals, cap 30

**Owner:** orchestrator (ctn-9c) + a background agent · **When:** now (22 Oct) · **Urgent:** Blue is our steadiest income

## Why (2026-10-22, ~05:00 UTC)
- **Marc's bar:** Blue runs unattended and must not earn a "genuine" ruling: one locks all reporting for 6 h (~450 points lost at our rate). Today: 81 filed, 48 hidden, **2 genuine**, 9 teams.
- **Organiser update (Discord, 22 Oct, quoted by Marc):** "The pending report cap is lifted to 30 from 25, and the automod gets a boost to accuracy if a post or account has been reported by multiple teams."
- **The floor is the moderator, not our evidence:** it is wrong ~1 in 10 either way (scoring page, 20 Oct). A single-team post report on a real bot still risks a genuine ruling at ~10%. Only two routes get below that:
  - **Account reports:** a dismissed one brings no points and **no lock** (scoring §3; [blue-reporting §1](../docs/06-strategy/blue-reporting.md#1-the-limits-as-they-stand-on-21-oct));
  - **Post reports other teams also filed:** boosted accuracy. We can't see others' reports, but a ruling well before 3 h means more than one team reported (the timer halves per extra team).
- **Our own voices are being caught by a text fingerprint** (todo/27): the same skeleton from many accounts. Other teams' bots will have fingerprints too. Today we only detect like/reply **rings**.

## Do (small commits, each shipped green; `src/swan_blue` only)
1. **Cap 30:** `service.CAP = 30`, with the source and date in the comment. Update the docs that say 25: [blue-reporting](../docs/06-strategy/blue-reporting.md) table and §2 maths, [00-quick-reference](../docs/00-quick-reference.md), [scoring-cheatsheet](../docs/03-scoring/scoring-cheatsheet.md), CLAUDE.md "Key facts", and the answers log in [discrepancies](../docs/05-reference/discrepancies-and-open-questions.md) (the quote above, dated). Leave the 30th slot to account reports when posts already hold 29 (accounts can't lock).
2. **Measure the real genuine risk per evidence class** from `logs/blue_reports.jsonl` and the rulings, all days: like ring, reply ring, early ring, account. Also by `pg` bucket, by post age and by Trending vs Latest. Write the table into blue-reporting §7 (dated). Check whether the `pg` model is calibrated (predicted vs observed).
3. **A no-lock mode, the new default (`BLUE_POST_PG_MAX`, config):**
   - account reports always first;
   - **post reports only where the evidence predicts P(genuine) ≤ 1–2%**: at most 2–3 genuine a week at ~70 post reports a day, against 2 today. Use the classes step 2 finds safest (e.g. reply ring plus like ring plus id run, an author already hidden or co-reported) and nothing else;
   - say in the doc what this costs in post points against the hours of lock it saves. If the data says 1% is unreachable for posts, say so plainly and run accounts-first with the lowest-risk posts only.
4. **Co-reporting as a signal:** log time-to-ruling per post. A post hidden in < 2 h had ≥ 2 teams reporting; its author and its ring partners become account leads at once. Ring posts hidden by others are already harvested; make sure the new accuracy boost is used there (account reports on authors others reported).
5. **New detectors for account leads** (accounts only, never post reports, until each has 10+ rulings that support it):
   - **text fingerprint across accounts:** near-duplicate replies or one skeleton from ≥ 5 team accounts in 24 h (the thing that got us caught; reuse the shingle/near-duplicate idea from `swan_bot.quality`, read-only);
   - **cadence:** an account replying at a fixed interval or ≥ N an hour around the clock;
   - **id runs plus a shared name or bio pattern** (accounts registered in a block).
   An account still only pays at ≥ 1 hidden post and ≥ 100 actions, so these find accounts to watch and report once they qualify. The detail text states measured numbers only (rules §5.2.2, LS.6.5).
6. **Alert** on any genuine ruling with the evidence class, so the next one teaches us something.

## Ownership
`src/swan_blue/*`, `scripts/blue.sh`, `tests/test_blue*.py`, the Blue docs above, CLAUDE.md "Key facts" Blue line. Don't touch `swan_bot` or the dashboard (todo/29 owns `src/swan_dash`); expose any new numbers in `data/blue_status.json` and note them in this file for todo/29. Rebase on `origin/main` before every push; `deploy/check.sh` must pass.

## Done when
Cap 30 is live, the per-class risk table is in the doc, the no-lock mode is the default, and the first 24 h after it show genuine rulings and points against today (write them here).

## Shipped (2026-10-22, background agent)

| Commit | What |
|---|---|
| 13fda57 | Step 1: `CAP = 30` (Discord 22 Oct), the 30th slot kept for an account report; the cap and the multi-team boost in blue-reporting, quick reference, cheatsheet, CLAUDE.md, answers log |
| 8603d2c | Step 3: the no-lock mode, the default: accounts first; post reports only at P(genuine) ≤ `BLUE_POST_PG_MAX` (2%, 4% since 83e0833), worth the lock they risk (ev ≥ pg × 300), within a risk bucket of `BLUE_PG_PER_DAY` (0.4 expected genuine a day, holds 0.1). `p_genuine` recalibrated: reply ring 2% (was 4%), id-run factor dropped. Live since 05:17 UTC |
| 9760288 | Marc's addendum: never report our own content: `file()` re-reads our ids and asks the platform for the post's author; refuses, logs `"refused": "own account"`, alerts. Posts with 3+ of our accounts among likers/repliers are never post-reported |
| 6ff0adf | Steps 4 and 6: time to ruling and `co` (< 2 h = 2+ teams) on every post ruling; a co-reported hide flags its author's lead and puts its ring first in the hide checks; a genuine ruling takes its time from the platform's lock and alerts with class, P(genuine), age, cluster |
| 226a606, fcec111 | blue-reporting §8: the per-class risk table, why 1% is not demonstrable, the policy and its cost, co-reporting, detectors |
| 9208052 | `own_ids` in `blue_status.json` (ids only) |
| 545ecdf | Step 5: `swan_blue/detect.py`: one wording from 5+ accounts in 24 h, cadence, registration block; watched accounts → hide checks → account leads with the measured numbers; never a post report |
| 622d6a3 | Blue tests never page anyone: a test with `live=True` sent a real "BLUE: #2 ruled genuine … cluster cA" alert from every pre-deploy test run on the box (05:36 → 10:02 UTC, about every 3 min while deploys of 60ad207 kept failing on test_widen). **Those alerts were the test, not a ruling** |
| 83e0833 | Recalibration at 10:00 UTC: reply rings are ~4%, not 2%; `BLUE_POST_PG_MAX` default 0.04; author-hidden factor dropped |

### Measured (all post rulings to 22 Oct 10:00 UTC, 86)

| Class | Genuine / rulings |
|---|---|
| Reply ring (root or ring reply) | 2 / 56 (3.6%; estimate 4.4%) |
| Like ring alone | 2 / 20 (10%) |
| Like ring + early ring | 0 / 10 |
| Ruled < 2 h (2+ teams) | 2 / 13 (#155963, #190875): co-reporting is not a safe class |
| Accounts | 7 upheld (portal) of 13 ruled; none can lock |

At 05:20 reply rings stood at 0 / 34 and the mode went live at 2%; two reply-ring reports filed under the todo/26 policy (#185124 at 03:33, #190875 at 05:07, a 10%-rate report the new lock-cost rule would have blocked) then came back genuine, locking us 06:33 → 14:08 UTC. The model (todo/26 factors) predicted 3.9 genuine over the 86 and 4 came. **The spec's number is off:** 1–2% is unreachable for post reports (the safest class is ~4%), and 70 a day at 1–2% would be 5–10 genuine a week anyway, not 2–3. Hence accounts first, posts at ≤ 4% and only at full rate, inside a risk bucket of 0.4 expected genuine a day (≈ 3 a week): about 10 post reports a day. Estimated ~650 Blue points a day against ~1,100 under todo/26 (blue-reporting §8 has the assumptions). Levers in `.env` (then restart swan-blue): `BLUE_PG_PER_DAY=1.0` for more points and ~1 genuine a day; `BLUE_POST_PG_MAX=0` for accounts only and no lock risk at all. **Marc's call.**

Since the mode went live (05:17 → 10:00 UTC): 3 post reports filed under it (05:38; all hidden), 1 account report, then locked from 06:33 by the two older reports. 102 account leads ready, most behind the per-team daily rate; they file after the lock ends (14:08 UTC, after the 13:00 UTC Sydney midnight, so at full rate). Detectors after 4.5 h: 11,078 Latest posts read, 272 one-wording groups, 549 accounts watched for one wording, 59 for a registration block, 17 for cadence; 39 / 7 / 2 of them already have a hidden post (leads through other routes so far).

### New `blue_status.json` fields for todo/29
`own_ids` (our account ids), `risk` {level, per_day, cap, posts_now}, `pg_max` (always set now), `pg_by_class` {class: n, genuine, expected}, `co` {fast, of} (post rulings today under 2 h), `detect` {posts_seen, sequences, groups, by: {fingerprint|cadence|block: watched, hidden, reported}}.

### First 24 h after (to fill in by 23 Oct 05:20 UTC)

| Measure | Before (21 Oct 13:46 → 22 Oct 05:20, todo/26) | After (22 Oct 05:20 → 23 Oct 05:20) |
|---|---|---|
| Post reports filed | ~70 a day | |
| Account reports filed | 12 in 15.5 h | |
| Genuine rulings | 2 (+2 more from its last reports, ruled 06:33 and 08:08 UTC) | |
| Hours locked | 7.5, then 06:33 → 14:08 UTC | |
| Blue points | ~1,120 | |
| Leads from detectors (`"by": "watch"`) | n/a | |

### Addendum (22 Oct, Marc via the orchestrator)
- `BLUE_PG_PER_DAY=1.0` set on the box ~10:40 UTC (`risk.per_day` reads 1.0).
- 37f7c38: the one-off cap probe, and Yes-side targets first (`swan_blue/side.py`, `BLUE_SIDE_BIAS` yes 1.3 / unclear 1.0 / no 0.7, ranking only, never in the detail; `side` per report, `today.sides`, `cap_probe` in `blue_status.json`). First 50 min after the lock: 20 Yes, 14 unclear, 1 No-side reports.
- 16efdbe: **account reports count toward the 30** (observed, not confirmed). The probe at 14:18 was taken and first read "no"; at 14:26 the platform refused with "30 reports awaiting a moderator's ruling" while we held 5 post reports. Our ledger overcounts because account reports can be ruled before 3 h and we can't see it. A full cap is now a 10-minute hold (it had set a 30-minute lock twice, until 15:27). The probe file corrects itself and alerts, and when our ledger says full we still try one report every 10 minutes.
