# 26: Blue: fewer locked hours, more teams at full rate

**Owner:** Marc + a fresh Claude session · **Depends on:** swan-blue (live) · **When:** 22 Oct · **Orchestrated by:** the session coordinating todo/24–26

## Why (2026-10-22 ~00:00 UTC, `data/blue_status.json`)
- **Blue earned ~1,100 of the 3,226 points overnight** (49 awards), and precision is 96% (44 hidden, 2 genuine).
- **It stopped because it's locked, not capped:**
  - `#155963` was ruled genuine, so no reports until 02:01 UTC (10am Perth);
  - 4 h were already locked today;
  - pending 0 of 25, and **43 targets ready** and waiting.
- **Rate:** reports hit only **7 teams (clusters) today**, and the portal shows `Moderation (×0.5 points)` lines. Past 5 paid reports per team per day, the rate halves, then drops to 10%.
- So the two levers are: **(1) fewer genuine rulings** (each costs 6 h of all reporting) and **(2) more distinct teams** per Sydney day.

## Do
1. **Lock economics:**
   - before filing a post report, estimate P(genuine) from its evidence class: ring size, timing, id runs, and whether the author already has a hidden post;
   - when ≥ 10 targets are ready, file only those under a P(genuine) threshold, so a lock is less likely to land while slots are full;
   - log P(genuine) on each report, and compare it with the rulings after 24 h.
2. **More teams at full rate:**
   - rank the ready targets by the per-cluster count already paid today: a 6th report on a cluster pays half, the 1st on a new cluster pays full;
   - widen discovery beyond Trending and Latest rings: reply-ring authors under citizen posts (our targeter's thread reads) and the swarm's snapshot;
   - all through `data/latest_snapshot.json` and `feeds.read`, never extra feed reads.
3. **Account reports while unlocked:** keep account leads (≥ 1 hidden post plus ≥ 100 actions) ahead of post reports, as now. Make sure the leads include authors whose posts *other* teams got hidden (the `account_posts` 404 check).
4. **Dashboard:** the Blue line shows "locked until HH:MM (why)" in Perth time, and the ready count, so a stop is never mistaken for a fault.
5. Write the before/after (points per day, locked hours, teams paid at full rate) into [blue-reporting](../docs/06-strategy/blue-reporting.md) with the date.

## Guardrails
- Report on evidence of automation only; no bad-faith reports (LS.6.5, rules §5.2.2).
- Never report citizens or our own accounts.
- Detail text stays specific.

## Done when
Locked hours per day are down, the share of paid awards at full rate is up, and both are measured against 22 Oct and written down.
