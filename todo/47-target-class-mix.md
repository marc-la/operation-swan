# 47 — Targeting: which citizens get the write slots (handoff for a talk with Marc, no change made)

Written 2026-10-27 (Marc + Claude). Read `CLAUDE.md` first. **Nothing here is switched on.** Marc asked for the targeting idea to be parked as a handoff to discuss before any config change. Read-only analysis so far; the figures come from the box's `scripts/conversion_report.py --hours 48` (25 Oct 03:03 to 27 Oct 03:03 UTC, 8,459 citizen-facing writes).

## Why
Writes are capped at 3 a minute and we use 96-99% of them, so score per day is points per write (5.91 base over 24 h on 27 Oct, goal 6.0; see [engagement-audit](../docs/06-strategy/engagement-audit-2026-10-25.md)). Every arm we have varied (frame, model, length, mention, own like) sits inside noise. The one spread left in our own data is the **class of the post we answer**.

## What the 48 h read says
| class of target (regex) | writes | citizen replied [90%] | citizen likes / write |
|---|---|---|---|
| yes_reason | 2,214 | 9% [8-10] | 0.09 |
| conditions | 3,745 | 8% [8-9] | 0.09 |
| lean_no | 664 | 7% [6-9] | 0.05 |
| **unclear** | 1,107 | **4% [3-5]** | 0.04 |
| **unsure** | 360 | **2% [1-4]** | 0.04 |
| **off_topic** | 348 | **3% [2-5]** | 0.04 |

The three weak classes are 1,815 writes, **21% of all slots**. At the 8.5% of conditions and yes_reason they would have added about 90 citizen replies and 90 likes in 48 h: about 1,800 base points, so about +38 base an hour, **+75 points an hour at x2** (+150 at x4). The earlier audit sized class order at only +0.05 a write (about +18 an hour); take **+20 to +70 an hour** as the honest range.

## Why it may be less than that
- **Confounded.** Reply rate belongs to the citizen as much as to our reply: unclear and unsure posts may simply be less chatty people. Replacing them with conditions/yes_reason posts only helps if those posts are available at the moment (the funnel shows supply about twice the slots, and freshness matters more: 9% for a post under 5 minutes old, 1-5% for older ones).
- **Persuasion.** Unsure and unclear citizens are the ones who could move. Their portal "towards" per 100 writes is 0.8 against 0.6 elsewhere, which is noise at these counts, but a change that starves them should be read on away events too (guardrail in todo/46: an arm whose away count beats base is killed).
- `UNSURE_FIRST` is already off (25 Oct). The weak classes still get picked because they are the fresh posts at that moment, not because of the ordering.

## Options to talk through
1. **Down-rank, don't skip:** `Targeter.next_target` sorts unclear/unsure/off_topic after conditions/yes_reason/lean_no when both are fresh (within 5 minutes); a stale conditions post still loses to a fresh unclear one. Cheapest; a `target_order` block arm (the `arm_eng` / `QUEUE_ARMS` pattern in `config.py`) reads it in a day.
2. **Skip off_topic** (348 writes, 3% reply, flagged "kill (away over baseline)" by the report's mechanical rule). Note the report's other two "kill" verdicts (late, turnout) are triggered by one hidden post each and their hide rates (0.5%) are not above baseline (0.65%), so that rule is crude; do not act on it alone.
3. **Nothing:** the audit's view was that class order is worth about +18 an hour and the arm_queue test (fresh/shallow, running since 26 Oct) may already move freshness. Read that first.

## Decisions for Marc
- Option 1 as a switchback arm (2-3 h blocks, base / down-rank), or wait for the `arm_queue` read (`scripts/engagement_recon.py queue`)?
- Keep persuasion as a guardrail only, or give the unsure class a protected share of slots?

## Read-out when it runs
`scripts/engagement_report.py --hours 48` (points per write by arm) and `scripts/conversion_report.py --hours 48 --by target_class` (reply rate, likes, away per 100). Judge arms inside the same mode (hot voice or not) and on the 24 h figure, not one block.
