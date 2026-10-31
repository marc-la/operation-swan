# 56 — Is the flip pushing citizens to Yes? No sign of it: keep it, with a tripwire (todo/53 P3)

Written Sat 31 Oct 2026, ~03:00 Perth (30 Oct 19:00 UTC), by Claude for Marc. **Status: closed, no change (Marc approved, 31 Oct).**
One watch rule for the ×4 days (§3). The only content change touching the flip is the "door" rewording in
[todo/59](59-prune.md) §3, which is about the gate, not persuasion.

Read first: [todo/53](53-the-last-three-days.md) §3 P3, [situation §13](../docs/06-strategy/situation-2026-10-29.md#13-the-yes-surge-and-the-flip-29-oct-evening).

## 1. What the data says
The portal's persuasion lines per 1,000 of our writes, in 24 h windows either side of the flip going live (29 Oct 11:06
UTC). The lines are booked at about :49, matched to the writes of the hour before:

| window | writes | primary toward | contributions toward | primary away | contributions away | primary neither | contributions neither | replies | likes |
|---|---|---|---|---|---|---|---|---|---|
| 48-24 h before | 4,233 | 0.7 | 4.0 | 1.2 | 22.9 | 2.4 | 48.0 | 256 | 279 |
| 24 h before | 4,222 | 0.5 | 0.9 | 1.2 | **26.1** | 3.1 | 38.8 | 237 | 282 |
| 24 h after | 4,236 | 0.7 | 1.9 | **0.7** | **23.1** | 2.4 | 36.1 | **263** | **302** |
| 24-30.5 h after (lines not all booked yet) | 1,145 | 0.0 | 0.9 | 0.0 | 20.1 | 0.9 | 27.1 | — | — |

- **Away events did not rise with the flip.** Contributions away went 26.1 → 23.1 per 1,000 writes, and primary away
  1.2 → 0.7.
- **Toward fell the day before the flip, not after.** 4.0 → 0.9 in the 24 h before, then 1.9 after. The fall lines up with
  the Yes surge, which began when the papers ran the wastewater signal (28 Oct 22:00 UTC; the whole Yes side ran 19-24%
  above the day before while the No side was flat; situation §13).
- **Engagement rose:** replies per 1,000 writes 237 → 263 (+11%), likes 282 → 302.
- **On the Sydney-day view,** away contributions run 93-115 a day on every day from 26 to 30 Oct. That's flat through the
  flip.
- **The 24 vs 14 "made a change themselves" count** (todo/53) is primary away 2-9 a day against toward 2-4. That ratio was
  already there on 26-28 Oct, before the flip.
- **The panel's +0.9 vs −1.8 per 100 pairs is noise,** and it was confounded by the 29 Oct targeting change (todo/53 P2).

**Reading.**
- With 30 Yes teams outscoring the 19 No teams 2.8 to 1, the conditional-Yes citizens we answer (83% of our targets) are
  the ones the Yes side is moving. Our posts sit in those sessions and share the −40 pool for addressing the same view.
- The away lines measure the tide, not our wording. At about −5 points each at ×2, they cost about 500 a day. They
  don't reduce our pool weight, which counts toward events only.

## 2. On "does naming the threat make the Yes case more vivid?"
- **The flip never names a threat alone.** Every reply pairs the fear with its efficacy: it's handled, and a No keeps it
  running (core line → proof → turn; the fear dial at 1).
  - "A fear appeal works with the way out and backfires without one"
    ([situation §13b](../docs/06-strategy/situation-2026-10-29.md#13b-the-room-read-and-the-tuning-29-oct-1200-utc), the fear dial).
- **The WS8 audit (29 Oct) fixed the cases that broke this:** invented losses, turns for conditions the post never named,
  flips on No-leaners.
- **What to keep watching is invented detail.** On 30 Oct `hospital_plans` produced one invented anecdote in five uses
  ("My daughter's school already has the surge plan posted…"). Use the existing `flip_audit` sample (todo/53 §6) once
  more on 31 Oct before 06:00 UTC.
  - If invented specifics recur, tighten that one evidence line's "add no date, time, place or figure" note. Don't touch
    the flip's structure.

**The audit, 31 Oct 00:50 UTC** (`scripts/flip_audit.py sample --n 30 --since-h 0.6`, flips since 4363550, judged offline by
Claude against the rubric):
- **10 of 30 failed something:** no_invention 6, worry 3, then one each of tasteful, human, specific and one_point.
- **`hospital_plans` caused most of it (5 failures in 8 uses).**
  - "Surge beds and staff ready now" (twice), where the fact is a plan for if it spreads.
  - The invented school plan again: "my daughter's school already has its plan, same as the hospitals".
  - **Fixed in the next push:** both wordings now say what has already happened is the plan being published, and the
    beds and staff are only if it spreads. A test holds the condition.
- **The rest, once each, left alone:**
  - "kept the first case out";
  - "40 empty nursing posts they won't fill";
  - a privacy post matched the hospitals fear through "frontline";
  - a thank-you to a nurse got a pitch;
  - a fragment opening.
- **Nothing pushed citizens toward a Yes:** no reply named a loss a Yes doesn't bring.
- **`no_firm`, the lean-No fallback (1 in the sample),** answered the permanence worry in the citizen's terms. The other
  lean-No replies firmed the No with a fact: "the first case came, they isolated it, contacts tested clean: that's the
  system working. A No keeps that."

## 3. The tripwire for ×4
- **What to read.** Contributions away per 1,000 writes, over the last 12 h of portal lines (compute them as todo/53 §7
  describes: lines at :49 against the writes of the hour before).
- **The trigger.** If they pass **30** (the range is 20-26 now) and the replies per write haven't risen with them:
  1. `SWAN_FLIP_FEAR=0` and restart (the plainer turn). Read again 12 h later.
  2. If it's still above 30, `SWAN_FLIP_ON=0` and restart.
- **What not to react to.** Ignore single hours: away events come in bursts of 0-17 an hour.

## 4. Not doing
- **Turning the flip off "to be safe".** It's linked to +11% replies per write, and nothing in the persuasion lines points
  against it.
- **New flip arms or wording tests** (Marc's final-days rule).
