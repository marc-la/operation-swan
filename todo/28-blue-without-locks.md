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
