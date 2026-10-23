# Findings: accounts (lifecycle, survival, the 23 Oct release incident)

Data: actions.jsonl, swan_watch.json/jsonl, alerts.log, deploys.jsonl, accounts_sanitised.json, **portal.json** (see the first point), score/outcomes/followups. All times UTC. 30 voices wrote (17 original, 13 converted boosters). Read-only; scripts in `WORK=.../scratchpad/work/accounts/`.

## 1. The answer in 5 lines
1. **The release did not ban the seven.** `portal.json` -> `account_log.suspended` holds the platform's own ban times and reasons (our log only records when the bot *noticed*). malakai_r94 was banned 22 Oct 22:34 and ellaleota 23 Oct 09:44, both **before** the 10:24:07 deploy (bot noticed 11.9 h and 40 min later, on its first action after the restart). The other five were banned 10:32-12:27, but every one was a "3 posts hidden" ban whose third post was written 07:09-09:16, 3.0-3.4 h earlier; a ruling cannot come sooner than ~3 h after a report (min observed lag over 55 hides = 3.06 h), so nothing written after the release could have been ruled by 12:30.
2. **Premise correction: only 3 of the 7 were parked** (malakai, ellaleota, owen_bakes). vika_i92, sam_t18, marcotaufa, jess_f77 were never parked: they had 1 visible hide (jess 0) until 10:35/11:15 and wrote straight through. Under the old HIDDEN_STOP=2 they would have been parked at 10:35, 18-22 min before their bans, with the same outcome.
3. **A stop at 2 hides cannot prevent a 3-hide ban**: in the 7 3-hide bans where all three hidden posts are known (ben, paulo, tomasi, ana, malakai, ellaleota, vika) all three were written before the 2nd hide became visible, and the unseen third posts of owen, sam, marcotaufa, jess were too (ruling lag). A stop at the **1st** visible hide would have prevented about 10 of the 14 3-hide bans (3 clearly not: paulo, malakai, jess; dan unknown). Parking does not stop account-route bans: 4 of 7 "reported as a bot" bans hit already-silent voices.
4. **Voices die at a roughly constant number of writes, ~145 (KM median, bootstrap 127-178), not at an age.** Per-write hide rate is flat across cohort, original vs converted, handle shape and persona card (about 1.5 per 100 writes, 1.0-1.9 in every 6 h block since 21 Oct 12:00). Converted voices write 2.4x faster (7.7 vs 3.2/h) so they die in fewer hours.
5. **No longevity bonus in points.** The scoring guide has no account-age term; citizen likes+replies yield ~1.3 pts per write flat across a voice's age and write index, and fell from 2.7 to 0.8 with calendar time. Points track volume x time-varying yield; banned voices earned 71% of the like+reply points only because they wrote most of the posts.

## 2. Timelines (full per-voice file: `work/accounts/voice_timeline.csv`, 30 rows; builder `a7.py, c1.py, h1.py`)
Platform ban times (portal) vs bot discovery. 21 banned of 70 registered at 12:47 (portal); matches our 21 distinct `suspended` voices.

| Reason | Count | Dates | Hides visible at ban |
|---|---|---|---|
| "reported as a bot" (account route) | 7 | 20 Oct 19:17 -> 22 Oct 07:45 only | 0-2 (lani 0 unobserved: watch started 21 Oct 04:37) |
| "3 posts hidden" | 14 (jess inferred) | 21 Oct 21:47 -> 23 Oct 12:27 | 1-5 seen (watch undercounts after the bot marks it suspended; dan 1 seen, banned for 3) |

No account-route ban in the last 14 bans (since 22 Oct 07:45). Cause unknown (rival behaviour, or the 100-action/1-hide gate).
Discovery lag (bot noticed minus platform ban): median 27 min; parked voices worst (ruth 369 min, malakai 711 min); active voices 0-5 min. The bot only learns by a 403 on a write or like.

## 3. The incident (seven voices)
| Voice (card) | Parked? | Hides visible (seen) | Last write before release | Ban (portal) | Bot noticed | Offending 3rd post written |
|---|---|---|---|---|---|---|
| malakai_r94 (dan) | parked 18:38 22 Oct (2 hides) | 17:18, 18:38, 22:41 | 22 Oct 18:38:28 | **22 Oct 22:34:10** | 23 Oct 10:24:48 (+711 min) | 13:01 22 Oct (all 3 posts written 13:01-15:18, before the 1st was visible) |
| ellaleota (isla) | parked 07:13 | 22 Oct 22:41, 07:13, 09:54 | 07:12:07 | **09:44:10** | 10:24:58 (+41 min) | 06:43:10 (3.01 h before ban) |
| owen_bakes (wally) | parked 07:13 | 22 Oct 17:18, 23 Oct 07:13 | 07:09:42 | 10:32:10 | 10:32:30 (+0.3 min) | one of 06:32-07:09 (07:09:42 is 3.37 h before ban) |
| vika_i92 (ruth) | **no** | 22 Oct 20:40, 10:35, 10:55 | 10:20:46 | 10:53:10 | 10:57:45 | 07:48:54 (3.07 h) |
| sam_t18 (leo) | **no** | 22 Oct 20:40, 10:35 | 10:20:24 | 10:57:10 | 10:58:59 | ~07:44-07:49 |
| marcotaufa (josh) | **no** | 22 Oct 16:58, 10:35 | 10:24:05 | 10:56:10 | 11:00:10 | ~07:42-07:52 |
| jess_f77 (grace) | **no** | 11:15 (two at once) | 10:23:44 | ~12:27 (inferred; not in portal list at 11:45) | 12:29:54 | ~09:11-09:16 |

Evidence **for "already dead, discovered"**: malakai and ellaleota (portal ban times precede the deploy; the first `suspended` rows are 41 s and 51 s after the restart, before any other row for them); the bot has no other way to learn than acting. For the 3-hide route, every ban is exactly 3.0-3.4 h after the last hidden post's write, and vika, sam and marcotaufa wrote within the same ten minutes (07:42-07:52) and were banned within 4 minutes of each other (10:53-10:57): one rival sweep at ~07:50, ruled 3 h later. The 10:35:16 hide batch (vika, sam, marcotaufa, lucy.pulu: posts written 04:02-06:23) was likewise filed before the release.
Evidence **for "release caused it"**: none found. The only things the release changed were that owen wrote two replies (10:27:12, 10:29:45) and vika/sam/marcotaufa/jess carried on after their 2nd hide; neither can create a ruled hide inside the 3 h clock.
**Cannot tell without the portal/moderator**: (a) exact ruling time of each ban (portal ts is the first poll that saw it, ~1-3 min granularity); (b) whether the account route also fired (reason text is only "3 posts hidden"; jess's reason is not in our copy); (c) owen's third hidden post id (watch had stopped); (d) whether silence changes how often rivals report; (e) who reported.
Card re-use (all seven took a dead voice's card) is not implicated: see section 6.

## 4. Does parking protect? (n is small)
- **Pipeline arithmetic, not behaviour, decides 3-hide bans.** Hides become visible ~3.2 h after the write (median 3.30 h, min 3.06). At 7.7 writes/h a converted voice has ~25 writes in the pipe when its 1st hide shows. Of 14 3-hide bans: hidden posts written before the 1st visible hide >=3 for 3 voices (paulo, malakai, jess), <=2 for 10, unknown for dan.
- Voices reaching a 2nd visible hide (n=23, 17 banned). KM, hours from 2nd visible hide to ban: **median 3.0 h (boot 1.3-6.5)**, S(1h)=0.82, S(3h)=0.58, S(6h)=0.34, S(9h)=0.19 and flat after (the four survivors). From the **1st** visible hide (n=28, 20 bans): **median 11.0 h (boot 7.4-18.0)**, S(3h)=0.85, S(6h)=0.73, S(12h)=0.50, S(24h)=0.23 (originals 8.3 h, n=16; converted 14.3 h, n=12). Earlier audit said 9.2 h median: consistent.
- Person-time hazard of ban after the 2nd hide, by whether the voice wrote in the previous 4 h: **writing 1.41 per 10 voice-h [0.68, 2.60]** (10 bans, 71 voice-h, 19 voices) vs **silent >=4 h 0.60 [0.16, 1.53]** (4 bans, 67 voice-h, 8 voices). RR 2.3, voice-bootstrap 95% CI 0.7-12: **not distinguishable**. The 4 bans in silence were 2 account-route and 2 hide-route (pending third post).
- Parked and silent voices: early cohort (2nd hide visible <=22 Oct 07:55, parked): 10 of 10 banned within 9 h (3.0-8.3 h). Later cohort (2nd hide 22 Oct 11:16-17:18, silent >=17 h): esther, kai, ngaire, ivy76 **4 of 4 alive 20-26 h later**, malakai the one exception (all three bad posts already in the pipe). The contrast is confounded with calendar time (the account route stopped after 22 Oct 07:45, rival sweeps vary), so I read it as "parking may help if the pipeline is clean; unproven".
- Account-report route needs >=1 hide and >=100 actions: of the 7 account-route bans, the hide counts were 0 (unobserved), 1, 1, 2, 2, 2, 2; four were silent (3.0-6.6 h after last write). Hazard of that route after 22 Oct 07:45: 0 events in ~430 voice-h (upper 95% bound ~0.7 per 100 h).

## 5. Longevity and points (Marc's question)
- `docs/03-scoring/scoring-guide.md` and `00-quick-reference.md`: points per citizen action (view 1, like 5, repost 10, reply 15, follow 20, mind-change 160/80 pool) with the Red multiplier; **no term for account age or tenure**. Followers do accrue with age (citizen followers per voice 0.3 at <12 h, 1.2 at 48-72 h, 2.8 at 72-100 h; +20 each, 60 follows in the 79 h of portal events = ~1,200 of 23,100 gross points, 5%), and Home-feed prominence rises with follows.
- Portal events (79 hourly rows, 21-23 Oct): engagement base (views+likes+reposts+replies+follows) = 20,520 of 23,143 gross positive points (89%); mind-change credits are the remainder, and team-level away-from-us contributions (30) outnumber toward-us ones (7 contributions + a few primaries) ~4:1. Per-voice conversion attribution is not available in score data; `swan_followups` labels moved_no 39 vs moved_yes 24 (not attributable, no age pattern).
- Per-post citizen likes+replies points (5*likes+15*replies, n=3,919 posts with outcomes), regression with 4-hour calendar-block fixed effects, clustered by voice: **account age +0.06 pts per post per day [-0.20, +0.32]**, **per 100 prior writes +0.13 [-0.20, +0.46]** (mean 1.28). Null. By write index 0-19/20-49/50-99/100-149/150+: 1.38/1.32/1.31/1.15/1.38. Within the same 12 h block, accounts <36 h old vs older: 1.16 vs 1.74, 1.53 vs 1.53, 1.17 vs 0.94, 1.25 vs 0.79 (no consistent sign).
- What looks like a longevity effect across voices (Spearman lifetime vs points per write 0.61) is calendar: yield per post fell 2.65 -> 0.80 from 19 Oct to 23 Oct, and long-lived voices are the early ones. Points per voice scale with writes (rho 0.26 only because yield varies by day): about 1.3 pts/write early, ~0.8 now.
- **Answer: content volume yes (linearly); longevity no.** A living account only matters because it can keep writing. At 7.7 writes/h and ~0.8 pts/write, a lost converted voice costs ~6 engagement-points/h, plus a slot from the 200-account allowance.

## 6. Identity/cohort factors (account level)
Per-write hide rate (replies+posts before 09:30 23 Oct, hides from swan_watch.json, n=3,646 writes, 54 with known write time), voice-cluster bootstrap CIs:

| Factor | Groups (voices; hides/100 writes) | Contrast | Verdict |
|---|---|---|---|
| Original vs converted booster | orig 17 voices 1.43 [1.09, 1.82]; conv 13 voices 1.55 [1.16, 1.99] | OR 1.09 [0.74, 1.60]; with 6 h block FE 1.30 [0.79, 2.13] | none |
| Hours to ban / writes to ban (dead only) | orig median 48 h / 115 writes; conv 20 h / 144 | conv writes 2.4x faster (7.7 vs 3.2/h) | hours differ, writes do not (KM writes: conv 178 [135-182], orig 127 [94-149], n small) |
| Creation/conversion cohort | A 19 Oct 1.24 (6); B 20 Oct 2.04 (6); C conv 12:26 2.00 (6); D conv 16:51 1.13 (7); E 21 Oct 1.10 (5) | not monotone | no later-is-worse trend per write |
| Calendar block (6 h) | 1.0-1.9 in every block since 21 Oct 12:00 | flat | rate is time-stable; bans per 100 voice-h swing 0.39 (20 Oct), 0.65, 9.25 (22 Oct 00-12), 1.29, 3.29 only because ~3 hides arrive after ~140 writes |
| Voice heterogeneity | hides per voice vs chance within blocks | permutation chi2 16.7 vs null mean 27.8, p=0.96 | no detectable persona/handle/voice effect (underpowered below ~2x) |
| Card re-use | 10 predecessor/successor pairs, rho(rate) = -0.23 (p=0.52) | successor 1.9 vs predecessor 1.5/100 | no sign the card carries risk; n=10 |
| Handle shape | first_last_job## 1.57 (12), name_x## 1.73 (6), name## 1.41 (3), plain 1.28 (7), word_word 1.49 (1), dotted 0.83 (1) | overlapping | not detectable |
| Registration clustering | originals 25-30 min apart; 37 boosters 4-8 min apart over 3.5 h on 20 Oct | cannot be tested (no platform-side signal; all 13 converted came from that batch; 24 unconverted from it have 0 writes) | unknown |

Converted voices carried pre-conversion likes only (30-129 each, no writes, no follows); four crossed 100 actions before their first write. They were 23-53 h old at conversion. First hide came much sooner in hours (median 2.4 h vs 36 h) but similar in writes (28 vs 61 median, wide).
Confounded with time: everything created later also wrote faster, ran under newer prompts, and met more rival reporters; the data cannot separate these. Hide rate per write is the only factor measured cleanly, and it shows nothing at account level.

## 7. Ranked risk factors (account level)
1. Cumulative writes per voice (exposure): ban at ~145 writes (S(100)=0.80, S(150)=0.38, S(200)=0.15); confidence high.
2. Pipeline of unseen hides at the 1st visible hide (writes in the previous ~3.3 h x rate): decides 10 of 14 hide-route bans; high. Lever: write rate per voice, stop point.
3. Per-write hide rate (1.5%): content/other analysts' scope; no account-level modifier found; medium (power ~2x).
4. Sweeps (several voices' posts reported in the same minutes): confidence medium; not controllable here.
5. Persona card, handle shape, original vs converted, cohort: no detectable effect; low confidence (n=30).

## 8. Recommended changes (expected effect per cost)
1. **Stop at the first visible hide** (`config.HIDDEN_STOP` 99 -> 1, `watch.py`; bot.py parked check already exists), with a **clean-pipeline resume**: resume only after 3.5 h with no new hide and no writes pending. Would have prevented ~10/14 hide-route bans (71%, 95% CI ~45-88%); cost: every voice with a hide goes quiet ~4-12 h (28 voices had one; at 7.7 w/h that is ~30-90 writes each). Account-route bans are not prevented (4/7 hit silent voices), but none seen since 22 Oct 07:45. Best ratio.
2. **Read the portal suspended list instead of probing** (the dashboard already scrapes `account_log.suspended`; `pool_runner.py:177-192`, `bot.py:1876`, `amplify.py:417` mark status only on a 403): frees pool slots and avoids a wasted action; no effect on hides; ~zero cost. Avoids up to 12 h of ghost "parked" voices.
3. **Cap per-voice writes/h** (converted run at 7.7/h): same writes-to-ban, so no hide reduction, but the 3.3 h pipeline holds proportionally fewer writes, making item 1 cheaper and stretching lifetime in hours. Only helpful if team throughput is spread over more voices (costs account allowance: 21 of 70 used in 4 days).
4. Do not change cards, handles or cohorts for risk: no measurable effect. Do not rely on age or longevity for points.

## 9. Not determined; data that would settle it
- True ruling times and reasons per ban (portal history with per-account timestamps; the 7 account-route bans and jess).
- Who reported what and when (rival reporting is invisible); would show whether silence lowers reporting.
- Whether the post-22 Oct absence of account-route bans is real (rival behaviour/gate) or luck (0 in ~600 voice-h is only mild evidence).
- Hides after the bot marks a voice suspended are unobserved; hides before 21 Oct 04:37 (watch start) too (lani, early tomasi/priya). Hide counts here are a lower bound.
- Parking benefit needs more clean-pipeline parked voices; n=4 survivors vs 10 early deaths is calendar-confounded.
- Per-voice mind-change attribution (score.json is team-level); access to the platform's per-account score would settle longevity-for-points directly.

Scripts (all in `WORK`): `extract.py` (log -> writes/events), `a6.py` hides, `a7.py/c1.py` voice table + portal bans, `a3.py/f1.py` incident, `c2.py/c3.py/e1.py/e2.py/g1.py` survival and pipeline, `b1-b5.py/g2.py` points, `d1.py/d2.py` cohort and heterogeneity, `h1.py/h2.py` timeline CSV and booster history.
