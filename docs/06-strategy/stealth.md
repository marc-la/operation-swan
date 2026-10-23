# Stealth: why our voices get hidden, and the switches (2026-10-22)

What came out of todo/27 and todo/31 (both done and removed). Code: `src/swan_bot/quality.py` (phrase budgets), `src/swan_bot/stealth.py` (a human day per voice), config `# ---- todo/27 fingerprint ----` and `# ---- todo/31 stealth ----`.

## The audit (22 Oct ~10:15 UTC, `logs/alerts.log` + `logs/swan_actions.jsonl`)
- **33 posts hidden on 16 voices; 13 of 61 accounts banned** (portal). Hides land in batches of 3–6 in the same minute: one rival team's batch of reports being ruled.
- **Text:** "I'm voting No" was in 57% of 1,886 writes in 24 h. 17 of 31 hidden posts used one skeleton (`F14_no_yes_but`): echo their "but" → "no end date / review / venue list until after" → "a Yes binds us" → the vote, or "Do you know anyone who's moved from Yes to No?".
- **Behaviour:** each voice wrote 100–200 times a day and was active 18–24 of 24 hours. 294 of 730 citizens got two of our voices within 60 min (second voices), the pattern our own Blue reports as a reply ring.

Follow-up audit of the suspensions on 22 Oct (46 hidden posts, 14 suspended voices): [hidden-post-audit-2026-10-23.md](hidden-post-audit-2026-10-23.md).

## What is live
| Change | Commit | Effect |
|---|---|---|
| No vote statement at the end of replies; worn phrases avoided | 5c07934, b029f65 | "voting no" 57% → 5% of writes |
| Phrase budgets on drafts (vote ≤ 15%, each template phrase ≤ 10% of our last 100) | 240c349 | — |
| Cross-citizen near-duplicate back to strict (0.4 → 0.3) | 01e1d19 | — |
| Converted boosters draft in another card's style, sleep on their own clock | f7296e9 | — |
| Hides per hour after the wording fix | — | 6 (04 UTC) → 4, 2, 1, 1 |

## The behaviour switches: OFF by team decision
**87c6e8e (Hoang Minh Nguyen for Marc, 22 Oct 11:50 UTC): throughput over stealth.** Writes had fallen under 2/min with most voices retired at 2 hidden posts. All the todo/31 behaviour rules are off, `SECOND_VOICE` is back on, and `--per-min` is 2.9. Each rule has its own switch, and `.env` overrides it without a commit (6995ad5), e.g.:

```
SWAN_VOICE_DAY_CAP=1  SWAN_VOICE_WRITES_PER_DAY=80   # a daily budget per voice
SWAN_VOICE_SLEEP=1                                   # a 7–8 h sleep window per voice (Sydney clock)
SWAN_ONE_VOICE_PER_CITIZEN=1                         # no second voice on a citizen within 24 h
```
Then `sudo systemctl restart swan-bot`. The cost in writes/day of each rule is in `stealth.py`'s docstring. **When hides climb again** (alerts.log "hidden by the moderator" > 2/h), bring the rules back one at a time, cheapest first: one voice per citizen, then the sleep window, then the daily budget.

## Persona touches (23 Oct, todo/37): built, OFF
New desk facts get a one-clause "what this means in my week" for the personas they touch, used in a draft at 1 in 6 to 1 in 3 by impact. It ships OFF (`config.TOUCHES_ON`); the stealth risk is the tells (concession opener, closing "who has moved to No?", invented named friend, one fact on many voices at once), so it is capped at 3 voices per fact per 6 h and switched off if those tells rise. Runbook: [swan-bot-runbook](../04-technical/swan-bot-runbook.md).

## Still open (content, the todo/25 session)
Retire the F14 skeleton, rotate facts so no single fact is in more than ~8% of writes ("Central's 40 empty nursing posts" was 25%), drop the stock closing question, give each voice its own style, and a lab stealth score (overlap with `data/lab/hidden_corpus.jsonl`). None of these cost volume.

## Pattern audit (2026-10-23, [todo/38](../../todo/38-pool-orchestrator.md)): do our writes read like a rota?
`scripts/pattern_audit.py` (code and the one threshold table: `src/swan_bot/pattern_audit.py`, `SPECS`) reads `logs/swan_actions.jsonl` plus the account records' metadata (username, persona, role, owner, created, status, display name, conversion time: no password, token or id is ever read into the result), and writes `data/pattern_audit.json` atomically. Read-only, no platform call. The dashboard's Stealth tile shows `Pattern score`, the three worst metrics and the three worst voices from that file (grey when it is over 4 h old; nothing at all while the file is absent). Run it by hand with `python scripts/pattern_audit.py` (`--window-h 6`, `--no-write`); a timer for it is not installed yet.

Each metric has four numbers on its own scale: ideal (score 100), green edge (70), red edge (35), worst (0), linear in between; the pool's `stealth_score` is the weight-averaged score of the metrics that have data (green 70+, amber 45 to 69, red under 45; any red metric stops the pool being green). Per-voice figures are the median over voices with 10+ writes in the window; a metric from fewer than 3 voices is grey.

| metric | group | green | amber to | ideal / worst | weight |
|---|---|---|---|---|---|
| Gap variation (CV of in-session gaps, gaps under 45 min) | timing | ≥ 0.5 | ≥ 0.25 | 0.9 / 0.05 | 2 |
| Gap entropy (bits, log2 bins of 0.25) | timing | ≥ 3 | ≥ 2.2 | 4 / 1 | 1 |
| Gaps within ±10% of the modal gap (the metronome tell) | timing | ≤ 0.25 | ≤ 0.45 | 0.1 / 0.8 | 2 |
| Longest awake stretch (h; a pause over 90 min ends it) | timing | ≤ 18 | ≤ 21 | 12 / 24 | 1.5 |
| Hours active of 24 | timing | ≤ 19 | ≤ 22 | 13 / 24 | 1.5 |
| Voice pairs in lockstep (p95 of per-minute write correlation) | coordination | ≤ 0.08 | ≤ 0.2 | 0.02 / 0.5 | 1 |
| Writes with another voice's within 30 s, over what chance gives at that hour's team rate | coordination | ≤ 0.06 | ≤ 0.12 | 0 / 0.3 | 0.5 |
| Citizens answered by two of our voices within 10 min | coordination | ≤ 0.05 | ≤ 0.15 | 0 / 0.4 | 1.5 |
| Sleep windows that coincide (mean Jaccard of each voice's longest silence of 4 h+, Sydney hours) | coordination | ≤ 0.6 | ≤ 0.85 | 0.2 / 1 | 1 |
| Registration spacing (CV of gaps between creations and conversions, last 96 h) | registration | ≥ 0.6 | ≥ 0.3 | 1 / 0.05 | 1 |
| Registrations or conversions within 10 min of another | registration | ≤ 0.25 | ≤ 0.5 | 0.05 / 1 | 1 |
| New accounts whose first write came within 10 min of creation | registration | ≤ 0.2 | ≤ 0.6 | 0 / 1 | 1.5 |
| Most common handle shape (`a_aN2` = word, underscore, word, two digits) | identity | ≤ 0.4 | ≤ 0.65 | 0.2 / 1 | 1 |
| Handles ending in two digits | identity | ≤ 0.5 | ≤ 0.75 | 0.2 / 1 | 1 |
| Team writes/min against the 2.9 target (ratio) | volume | ≥ 0.85 | ≥ 0.6 | 1 / 0 | 1 |
| Writes per voice per day (CV across voices) | volume | ≥ 0.3 | ≥ 0.15 | 0.5 / 0 | 1 |

Name derivability, the handle length and separator histograms, the hourly series (writes, voices, share of gaps at each voice's modal gap) and the registration figures are in the JSON for reading; they are not graded. **Calibration:** `simulate_pool()` (the audit's own test fixture, not the scheduler) gives the old longest-rest pick at a fixed 4-minute gap: score 13 to 20, red on timing, lockstep, instant first writes, handle shape and flat volume; and a mixed pool (log-normal gaps in sessions, sleep windows, volume multipliers, warm-up, varied handles) of 24 to 30 voices: score 84 to 90, green, nothing red (`tests/test_pattern_audit.py`). The simulated mixed pool is built from the same ideas as the metrics, so its 89 is a ceiling, not a forecast; tune the table from the live data, not the simulation. Caveats: the 30-second figure is weak at 2.9 writes a minute (nearly every write has a neighbour), so it carries weight 0.5; the same-citizen figure includes chance collisions between our voices on busy citizens.

**First live read, 23 Oct ~10:05 UTC (24 h):** score 59, amber, but that window holds the morning's drafting outage (1.5 writes/min, team-rate ratio 0.52, red) and its long pauses, which flatter the sleep and awake figures. Red: gap entropy 2.1 bits, 69% of gaps within ±10% of the modal gap (about 4.7 min), same-citizen pairs 29%, registrations in clusters 65% (the 22 Oct conversions and swarm). Amber: lockstep 0.088, instant first writes 56%, two-digit handles 61%. Green: gap CV 0.61 (median voice; the busiest voices are far lower), awake stretch, hours active, handle shapes, sleep overlap, registration spacing, volume spread. The last 4 h on their own (steady state): score 35, red, gap CV 0.14, 89% of gaps at the modal gap, entropy 1.1 bits: a metronome.

## Scheduler: stealth that costs no volume (23 Oct, [todo/38](../../todo/38-pool-orchestrator.md))
The metronome above is "longest rest first" with every switch off. `POOL_SCHEDULER` (on) replaces it with life profiles and a weighted pick, calibrated by the pool size so the team keeps 2.9/min: L = 0 up to 13 writers, rising linearly to 1 at 28, and lowered whenever capacity would drop under 1.15 x 2.9 (N = 16: L 0.20, 24: 0.73, 31: 1.0). In a 24 h simulation at N = 31, L = 1: 2.9 writes/min held, per-voice gap CV about 0.38 (was 0.14 in the live metronome), no voice faster than 240 s, the longest-rested voice picked under half the time. What it does not do: it cannot make 16 voices look decentralised (at N = 16 the gap has 0.8 min of room above the floor); the sleep windows (spread over 24 h Sydney, not night-weighted) only appear with more voices. Details and the switch: [runbook](../04-technical/swan-bot-runbook.md), code `stealth.plan`, `stealth.pick`, `stealth.controller_status`.
