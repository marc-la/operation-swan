# Engagement dip, 28 Oct 2026 (06:30 UTC): what it was and what we switched off

Asked by Marc on 28 Oct: hourly rate fell from about 2.4k to under 2.2k, "Yeah" rising. Data: the box's logs and `data/team_scores.jsonl` / `data/portal.json` at 06:20 UTC. Numbers are association from our own logs; the 6 h outcome read sees about 30% of the payout, so it ranks things and does not size them.

## The number
The dashboard's engagement per write (24 h, base points) went 6.28 two days ago, 6.03 yesterday, 5.70 now (last 6 h 5.34, the usual evening low). Points an hour over 24 h: 2,204 now, 2,280 the day before. Writes were at the cap (176-178 an hour of 180), 75% of first replies went out within 5 min of the citizen's post (53% on 24 Oct), hides 0.39%. So volume, speed and freshness were not the problem; the mix of what the slots went to was.

## Findings
> **Correction (29 Oct):** finding 1 was a counting artefact. `citizen_replies` counts ids up to 2343 only, so it could not see replies from the accounts this arm wrote to. The targets answered 13.8% of the time (`target_replied`, 247 matured writes) against 6.6% for ordinary targets, and the portal books these accounts' follows as citizen follows. See [situation-2026-10-29 §4](situation-2026-10-29.md#4-the-missing-citizens-the-biggest-lever).

1. **The extra-citizens arm (todo/48) wrote to accounts that never answer.** 289 writes in 24 h (about 7% of slots; 33-63 an hour inside the extra blocks that picked them); of the 145 with a matured 6 h read, **0 citizen replies and 1 like** (about 12 replies expected at 8%). 141 authors, scores 0.90-1.00. Ordinary targets inside extra blocks did normally (1.71 proxy points a write against 1.60 in base blocks), which is why the arm-level table (-9%) looked like noise. Cause unknown: they may be rival bots that score like citizens (all created 19-21 Oct, the registration rush); the classifier's "precision 1.0" was on our own labels. Cost estimated at about 150 pts/h. **Off 28 Oct** (`NPC_EXTRA_ARM`, with `BLUE_NPC_GUARD`, which rests on the same premise and could shield rival bots from Blue reports).
2. **Late replies (group `late`) under-perform.** About 12% of slots, 4.2% citizen replies (n=867) against 7.7-8.8% for ordinary replies, 0.89 proxy points a write against 1.64; its success line (25 Oct) was 8%+. It is handed out before every other candidate. `LATE_PER_H` 30 to 10 on 28 Oct.
3. **@mention arm: neutral.** Named replies 8.8% [6.3-12.3] against 8.0% unnamed; the named citizen answered 2 of 249 (success line 3%). Left on (no cost found).
4. **Own like: no help.** 6.9% citizen replies with, 7.8% without (n=2,927 / 2,931). `OWN_LIKE_VARIANTS = [False]` on 28 Oct.
5. **Target age is still the biggest lever:** proxy points a write by target age at send: under 1 min 2.50, 1-2 min 1.55, 2-5 min 1.27, 5-15 min 0.53, over 1 h 0.69. In the 12-18 UTC lull 28-39% of replies go to posts over 15 min old; structural.
6. **Prompt fixes (todo/50):** on since 03:32 UTC 28 Oct; only 83 writes had a 1 h read: citizen replies 2.4% against 7.7% for base (thin; likes higher). Sonnet had written nothing at 06:20 (it runs in fixes blocks only). Read-outs: see todo/50.
7. **Yeah (rank 3):** 24 h pace 2,033 an hour against our 2,204; last 3 h 2,828 against 2,237; daily averages 1.46k, 1.79k, 2.03k. Gap 34.6k; we still pulled away about 170 an hour on the 24 h figures. Watch, no action.

## Not changed
Volume, refresh (15 s), swarm (off), queue arm (shallow), mention arm, `arm_style` (base/fixes blocks, pin to fixes at the 1 Nov freeze).

## Read-outs to do
- Does the dashboard number recover once the extra-arm writes (last at 28 Oct ~06:00 UTC) leave the 24 h window, about 29 Oct 06:00 UTC? Expect +5-7%.
- Fixes and Sonnet: todo/50.
