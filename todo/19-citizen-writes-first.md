# 19: Citizen writes first: undo the 21 Oct write split that halved our hourly points

**Owner:** Marc + a fresh Claude session · **Depends on:** nothing · **When:** tonight, 21–22 Oct (before Sydney morning, ~3am Perth)

## Read first
`CLAUDE.md`, [amplification](../docs/06-strategy/amplification.md) (the 21 Oct ~12:00 Perth tuning), `src/swan_bot/bot.py` main loop (~lines 520–620: the order jobs are picked in), `src/swan_bot/amplify.py` (`priority_window`, `next_write_job`, `on_post`), `src/swan_bot/targeting.py` (`Targeter.refresh`), `config.py` (`AMP_LEVELS`, `AMP_PRIORITY_S`, `SECOND_VOICE`, `REPLY_BACK`, `ACCOUNT_MIN_GAP_S`, `CONTACT_COOLDOWN_S`, `TARGET_MAX_AGE_H`). Related: [todo/18](18-trending-entry.md) (Trending entry).

## Why: measured 2026-10-21 ~13:10 UTC (21:10 Perth)
Sources: the portal points log (`ssh swan-ec2 'cat ~/ctn/data/portal.json'`, `events`, one per hour at :53), `~/ctn/logs/swan_actions.jsonl` and `~/ctn/logs/swan_outcomes.jsonl` on the box.

**Hourly points fell from 120–250 to 15–25.** Three causes, biggest first:

1. **Our own deploy moved the write budget off citizens.** Commit `c37901a` (04:35 UTC / 12:35 Perth, "Amplification pushed harder") set 15–20 thread replies per amplified post, turned off second voices and reply-backs, and holds other writes for 20 min after each amplified post (`AMP_PRIORITY_S`). From the actions log (by hour written):

   | UTC | Citizen-facing writes/h (reply, second voice, reply-back, journalist) | Own-thread writes/h (post, thread, repost, answer) |
   |---|---|---|
   | 20 Oct 20 – 21 Oct 03 | 12–23 | 7–12 |
   | 21 Oct 05–10 | 6–9 | 16–22 |
   | 21 Oct 11 | 4 | 19 |
   | 21 Oct 12 | **1** | 19 |

   What each kind of write earns, every measured write so far (`swan_outcomes.jsonl`, last check per post):

   | Mode | n | Citizen likes / write | Citizen replies / write |
   |---|---|---|---|
   | reply (to a citizen) | 270 | **0.17** | **0.15** |
   | reply_back | 91 | 0.11 | 0.07 |
   | second_voice | 172 | 0.06 | 0.08 |
   | thread (own amplified thread) | 250 | 0.03 | 0.03 |
   | post (amplified original) | 109 | 0.03 | 0.00 |

   The thread replies that replaced citizen writes earn about a fifth as much each, and the 40 heavy amplified posts reached Trending 0 times ([todo/18](18-trending-entry.md)). The portal shows the drop with a ~2–3 h lag: citizen replies per hour went from 4–12 to 1–4.

   Why the bot starves citizens (from the code): the loop takes `amp.next_write_job()` **before** any citizen reply; inside `priority_window()` it `pause(15)`s rather than reply to anyone; and each thread reply puts a voice in its 4-min gap (`ACCOUNT_MIN_GAP_S`), so `accounts.assignable(frame)` often finds no free voice in the right frame when a citizen candidate comes up. Reply candidates averaged 4–6 per refresh all day while citizen writes fell to 6/h: **the targeter keeps finding citizens, but the bot doesn't write to them.**

2. **We hit the 500 views/day cap** (the hourly views add up to exactly 500 at the 09:53 UTC event; 0 views score after it). That cost ~20–40 points/h until the reset at midnight Sydney (13:00 UTC / 9pm Perth). This is the cap, not a fault, and it happens every evening now. Consequence: **views are no longer a reason to do anything**; measure replies, likes, follows and changes of mind.

3. **Candidates dried up late:** 1.5 per refresh at 12:00 UTC, 0 at 13:00 UTC (11pm–midnight Sydney). Probably citizens' night, unproven (the log starts 20 Oct 18:00 UTC, no earlier night to compare). Hypothesis to check as well: `CONTACT_COOLDOWN_S` (72 h) exhausts the pool, because after 2.5 days most citizens who post have already been contacted.

## Decisions (Marc, 2026-10-21 ~21:30 Perth)
- **Undo the write split** (steps 2–3 below).
- **The booster-repost test (todo/18) is approved.** It takes the thread replies' slots, never citizen writes.
- **Judge everything on citizens, not on our own numbers.** A metric counts only what citizens do: citizen likes, citizen replies, citizen reposts, follows by citizens, and the portal's changes of mind. Team accounts (ours and other teams') are left out. Views are not a points metric (500/day cap, filled by ~6pm Perth), but citizen *exposure* still matters, because changes of mind need readers.

## Broad requirement: tell citizens from team accounts, everywhere
- **The rule we have:** `config.CITIZEN_MAX_ID = 2343` (the last account created before launch, checked 2026-10-19). Ids ≤ 2343 are citizens (or organiser personas, ids 1–11 verified), and ids above are competitor accounts. The bot uses it in places (`amp_measure`, outcomes), and the ad-hoc scripts each repeat it.
- **Make it one helper**, e.g. `targeting.is_citizen(account_id)`, excluding verified ids 1–11. If it goes in `config.py`, put it outside the Blue block (`blue_reporter`, `BLUE_OFF_FILE`). `swan_blue` has its own `evidence.is_team(id, ours)` (id > `CITIZEN_MAX_ID` and not ours); it needn't change, but keep the two consistent. Use it in every metric: `amp_measure`, `swan_outcomes`, `ring_audit`, the dashboard, and the reply-target filter (never spend a reply on a team bot). Re-check the boundary once: sample ~50 accounts around id 2343 with `get_account` (`created_at` vs 19 Oct 07:00 UTC). Private accounts hide `created_at`, so the id rule decides for them.
- **Per-post report:** citizen likes, replies and reposts, the reply texts, our own views and likes kept separate, and Trending rank. A post's `view_count` mixes citizen and team views; only our own views are known, so treat views as exposure, not as a citizen count.
- **Citizen hours:** log citizen posts, replies and likes per hour (Sydney time) from the Latest reads the targeter already does. That curve decides when amplified posts go out (todo/18) and when citizen replies are worth most.

### What citizens give a Trending post (measured 2026-10-21, read-only, `likers`/`replies`)
| Trending posts | Citizen likes | Team likes | Citizen replies | Views |
|---|---|---|---|---|
| 8 posts from Sydney evening (~18:00–20:00 Sydney, read at 2–5 h old) | **12–29** (mean ~19) | 79–187 | 0–4 | 277–489 |
| 10 posts after Sydney midnight (1.5–3 h old) | **0–7** (mean ~3) | 49–99 | 0–3 | 57–151 |

So a Trending post in citizen hours brings ~20 citizen likes, ~1–2 citizen replies and ~400 views of exposure. At night it brings almost nothing. Team likes reach 187 per post, more than one team's 50 accounts, so several teams' likes stack on the same posts.

## Step 1 results: finding the citizens (2026-10-21 ~13:20 UTC / 21:20 Perth, read-only)
- **The targeter saw ~25% of Latest.** Latest runs at **~47 posts/min** (500 posts in 10.7 min, 61% replies, 14% reposts), and only **7 were by citizens** (~39/h at Sydney midnight). One 50-post read every 4 min covers ~1 min in 4. Trending threads and news threads gave 0–2 citizen posts under 36 h old; nearly all citizen posts there are the 19 Oct seeded batch. Candidates per refresh: ~30 on 19–20 Oct, then **~5 from 20 Oct 15:00 UTC on**. That drop is about 13 h before the write-split deploy. The seeded citizen posts (created 19 Oct 03:11–06:00 UTC) aged out of `TARGET_MAX_AGE_H` (36 h): per refresh, candidates slide smoothly 30 → 6 from 15:11 to 18:00 UTC, with no step at the 15:44 deploy of `5047fe8` (the `LEAN_NO` skip: 21, 21, 19). New citizen posts were hidden by team bots in Latest. **Fix:** each refresh pages Latest back to the newest post the last one saw (`config.LATEST_PAGES` 4 × 100, stopping when the feed budget has `FEED_READS_SPARE` 3 left), and logs `citizen_latest_posts`/`_replies`/`_authors` and `latest_gap` per refresh. That is the citizen-hours curve.
- **classify() dropped a third of the best group.** Of 159 citizen texts on the vote (the follow-up reads, 77 citizens), **53 matched a doubt but no hedge word (SOFT)**, e.g. "Publish the venue list now, with a clear sunset; keep door checks simple…". Those are the Yes-with-conditions people (F14). **Fix:** `targeting.hedged()` = SOFT, or a demand (`ASKS`) naming a condition (`WANTS`). It brings back 43 of 53. Complaints like "No sunset clause, no list, no thanks" stay out. Used in `classify`, `soft_yes` and the history check. `stance()` keeps SOFT so the follow-up labels compare across days.
- **Demographics.** Citizens almost never say who they are: 0 of 160 follow-up texts and ~5 of 501 citizen texts carry a self-description, so `IDENTITIES`/messenger matching seldom fires and can't steer much. Per write, the targeted classes perform about the same (citizen likes / replies per reply: conditions 0.10 / 0.17, yes_reason 0.05 / 0.18, all replies 0.17 / 0.15; 268 follow-ups, 2 moved No, 1 moved Yes). That is too thin to rank one class over another, so the ranking stays as the playbook has it (Yes-but first).
- **Contacted.** 287 citizens are contacted within 72 h. Of 37 citizens seen in one full read, 17 were contacted. Widening the pool (step 4) waits until the Latest fix has run for some citizen-active hours.
- **Speed.** Citizens answer team replies that land in their few-minute session (ctn-68's reach study: 2 posts, 5 of 9 and 4 of 8 answered, all within ~5 min). So `REFRESH_S` 4 → 2 min, and `next_target` ranks posts under `FRESH_MIN` (10 min) first (`FRESH_BONUS` 4). Older candidates are still answered, because notifications bring their authors back next session. Feed budget: ~1 read/min for the bot plus ~0.4 for swan-blue, against 10/min.
- **Dry run (2026-10-21 13:40 UTC, `--amplify --samples 2`):** the first job was a reply to citizen 270 (a "conditions" post the old filter dropped), then the amplified post with 4 thread replies. No errors.
- **Not done yet:** the `skip` record for "no assignable voice". The loop change (step 3) makes the citizen wait for the next free voice instead of losing its slot to a thread job.

## Do, in order
1. **Confirm the diagnosis (read-only, ~20 min).**
   - Per hour since 20 Oct 18:00 UTC: refresh candidates, citizen-facing writes, own-thread writes, portal replies/likes. The numbers above should reproduce.
   - Find where candidates are lost. Count, per hour, the candidates that were replied to, skipped as `gone` (replied post or contacted citizen), or skipped for **no assignable voice**. If the bot doesn't log the last one, add a `skip` record with the reason (one line, cheap).
   - Night or broken: count citizen posts and replies in Latest by hour (citizen = `author_id <= config.CITIZEN_MAX_ID`) for one 300-post read now and one at ~06:00 Sydney. Compare unique citizens seen in refreshes over 48 h against the citizens in `state["contacted"]`.
2. **Restore the split.** Config, reverting to values the bot ran on 20 Oct:
   - `AMP_LEVELS["heavy"]["replies"] = (4, 6)` (was 15–20).
   - `AMP_PRIORITY_S = 5 * 60` (was 20 min), or 0 if step 1 shows the window blocks citizen replies.
   - `REPLY_BACK = True`; `SECOND_VOICE = True`. Both earn more per write than own-thread replies. Second voice is the weaker; keep it if voices are free, otherwise only reply-back.
   - Update the comments on those lines with the date and the per-mode numbers above (the current comments say they were turned off for thread slots).
3. **Change the loop order** (code, `bot.py`): a due citizen reply (queue or candidates) goes **before** `amp.next_write_job()`. The exception is reposts in an amplified post's first ~15 min, if todo/18's repost test is on. Nothing pauses while a citizen candidate is waiting. Keep the change small and add a test in `tests/` that a citizen candidate beats a due thread job.
4. **Only if step 1 shows the pool is the limit:** widen it, each change logged with the date in config:
   - `TARGET_MAX_AGE_H` 36 → 48;
   - `CONTACT_COOLDOWN_S` 72 h → 36 h, for citizens who **replied or liked** last time only;
   - replies under Trending threads ranked first (`TRENDING_THREAD_BONUS`).
   Don't do this blind: re-contacting a citizen who ignored us earns nothing and looks like spam.
5. **Dry-run, then ship via `main`** (CLAUDE.md; only the EC2 `swan-bot` writes). Dry run: `python scripts/run_swan.py --amplify --boosters 34 --samples 10 --hours 0.1` and check the job mix in the output.
6. **Measure for 6 citizen-active hours** (Sydney ~7am–1pm = 04:00–10:00 Perth). Baseline is 20 Oct 20:00 – 21 Oct 04:00 UTC.

## Fit with todo/18
The repost test in todo/18 should take the slots of the **thread replies**, not of citizen writes. We use ~34 writes/h of the 180 allowed, so both fit: ~30 reposts per amplified post at one amplified post every 40–60 min still leaves well over 100 writes/h. If they ever compete, citizen replies win until a Trending entry is shown to bring citizen engagement.

## Guardrails
Config reverts to values that ran before are low risk. The loop-order change is code: test first, dry-run, then `main`. No new kinds of writes in this item. Watch the hidden-post alerts: more citizen replies means more content on show (@mere_t_nana70 has 1 hidden post since 11:02 UTC; decide whether that voice keeps writing).

## Done when
- `is_citizen` (or equivalent) is the one rule used by every metric listed above, with a test.
- The citizen-hours curve is in [platform-mechanics](../docs/06-strategy/platform-mechanics.md) with the date.
- In citizen-active hours, **≥15 citizen-facing writes/h** and **≥5 citizen replies/h** on the portal, with points back to ≥150/h before the view cap.
- The candidate-loss counts (step 1) and the before/after numbers are in [amplification](../docs/06-strategy/amplification.md) with the date.
- Config comments match the new values, and this row is ticked in `todo/README.md`.
