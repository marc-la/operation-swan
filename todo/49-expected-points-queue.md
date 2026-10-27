# 49 — Expected-points queue: answer the candidate worth most when the reply lands

Written 2026-10-27 (Marc + Claude). Read `CLAUDE.md`, then [targeting-audit-2026-10-27](../docs/06-strategy/targeting-audit-2026-10-27.md). Runs beside todo/48 (citizens above id 2343). **Nothing here posts**; the new pick ships behind a switch, off.

## Why
Writes are capped (3 a minute, ~176 an hour used) and on-vote citizen posts outnumber them (~300 an hour from the 2,332 known citizens alone; ~1,600 a day expire unanswered). So score is which candidate each slot takes. 25 Oct 03:37 - 27 Oct 03:37 UTC, proxy points a write (citizen replies x15 + likes x5 at the 6.5 h outcome check; the portal pays ~4x this, the order holds):

| class group | <2 min | 2-5 min | 5-20 min | 20 min-4 h | >4 h |
|---|---|---|---|---|---|
| strong (conditions, yes_reason) | 2.31 (2,399) | 1.43 (1,554) | 0.91 (806) | 0.45 (195) | 0.95 (736) |
| weak (unclear, unsure, off_topic) | 1.21 (557) | 0.46 (494) | 0.38 (396) | 0.06 (80) | 0.80 (156) |
| lean_no | 2.21 (232) | 0.71 (168) | 0.56 (156) | - | 1.08 (60) |
| reply_back | 2.05 (255) | 1.16 (151) | - | - | - |

Only 41% of writes landed on a post under 2 min old; ~35 an hour went to posts worth 0.4-0.7. `next_target` ranks by hand weights (tier, gap, class, newest under FRESH_MIN with the 27 Oct `DOWNRANK_MIN`, then a priority score that did not predict a reply: AUC 0.52, 26 Oct). Replace the ordering inside a tier with expected points.

## Build
1. `src/swan_bot/value.py` (pure): `expected_points(cand, now, lag_s)` from a table keyed by (class group, age when the reply would land = age now + the measured pick-to-send lag, ~45-70 s; shallow queue since 27 Oct 04:16 UTC). Smooth the age curve (monotone, interpolated, not bucket steps); fall back to the group mean for thin cells (< 40). Factors only where the logs show them after controls (age adjusted, within-citizen where possible): e.g. a citizen who answered or liked us before (10.0% vs 7.3%), 6+ unanswered touches (5.9% vs 7.9%), Sydney hour (3-5% at 2-5 pm, 8-11% overnight: matters only for comparing waits, not across candidates of the same moment; probably leave out). Keep `conditions_flat` with conditions until it has its own data.
2. `scripts/value_table.py`: rebuilds the table from `logs/swan_actions.jsonl` + `logs/swan_outcomes.jsonl` (read-only, run on the box or on copies) into `data/value_table.json`; the module ships a frozen default so the bot never depends on the file.
3. `Targeter.next_target`: behind `config.VALUE_PICK = False` and a switchback arm `("arm_pick", ["base", "value"], 3 * 3600)` with `FREEZE_PIN["arm_pick"]` (freeze at `ARMS_FREEZE`, midnight Sydney 1 Nov). In `value` blocks, within the existing tier / group order (late first, groups after ordinary candidates, caps, session limits, firm-Yes cap all unchanged), sort by expected points descending. Log `ev` on the job and the write.
4. Offline check before any switch: replay the last 48 h of candidates where the logs allow (the funnel has `lost`/`skip` with age; written targets have class and age) and report how the value pick would have reallocated slots and the expected gain against today's order, with the honest caveat that unanswered candidates' classes are not logged (log them from now on: add class to the `lost` record if cheap).
5. Tests without network (`tests/test_value.py`), `scripts/t.sh` green.

## Coordination
todo/48 (another session) is editing `config.py`, `targeting.py` (`_consider`, a `likely_citizen` admit) and `swan_blue`. Keep your change to `next_target` small (one sort key and a helper), put the rest in `value.py`, so the two branches merge cleanly. Do not push; commit on your worktree branch and report: the table, the replay result, files and flags, and your recommendation.
