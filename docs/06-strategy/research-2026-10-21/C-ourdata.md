# C: Our own data. What earns us points, and does self-amplification help?

Data as of 21 Oct 13:17 UTC (00:17 Sydney 22 Oct). Sources: portal.json (54 events), swan_actions (939 live writes, 3,275 likes, 197 reposts, 80 follows), swan_outcomes and followups, plus about 90 read-only API calls (followers of 16 voices, reposts, likers, and 42 posts' citizen replies with timestamps). Scripts and raw pulls are in `scratchpad/c_*.py` and `scratchpad/c_data/`.

## 1. Points by source (portal, 19 Oct 19:09 to 21 Oct 12:53 UTC)

The events sum exactly to the score: 7,555 = 3,000 (Poll 1) + 4,555 (NPC engagement).

| Source | Count | Points | Share of 4,555 |
|---|---|---|---|
| Replies ×15 | 151 | 2,265 | **50%** |
| Likes ×5 | 203 | 1,015 | 22% |
| Views ×1 | 784 | 784 | 17% |
| Follows ×20 | 13 | 260 | 6% |
| Reposts ×10 | 11 | 110 | 2% |
| **Persuasion, net** (residual) | | **121** | **2.7%** |
| · "contribution … towards your side" | 6 | ≈ +48 (~8 each) | |
| · "primary … towards neither side" | 3 | ≈ +60 (20 each) | |
| · "contribution … towards neither side" | 34 | ≈ +33 (~1 each) | |
| · "contribution … away from your side" | 8 | ≈ −20 | |

- **We have had no primary change of mind towards our side (160 points).** Persuasion is 1.6% of our total score.
- **All the "neither" events say "on vaccination towards neither side".** The "towards your side" ones don't mention vaccination. So the neither changes are about attitudes to the vaccine, not the referendum. My guess is that this comes from our vaccine-talk content ("not against the jab"; the F3 and F13 frames). With 34 events and no per-post link, that is untested.
- **The view cap bit.** Views for the Sydney day of 21 Oct summed to exactly 500 by the 08:53 UTC event (19:53 Sydney); every event after that shows 0–1 views. On 20 Oct (a partial day) we had 284. Once the cap is reached, only likes, replies and follows score.
- **Hourly rate** (net of views): 74 pts/h before self-amplification (16 h), 108 after it started (22 h), and 53 in the last 4 h, when reply volume collapsed (§6). Best hours were 234, 251, 223 and 220 points, each with 7–12 citizen replies.

## 2. Yield per write type (outcome check at +1 h and +6 h; citizen = id 12–2343)

| Type | n | cit. likes/w | cit. replies/w | % with any | ≈ pts/w |
|---|---|---|---|---|---|
| reply (to a citizen) | 273 | 0.16 | 0.15 | 28% | **3.1** |
| second_voice | 172 | 0.06 | 0.08 | 13% | 1.5 |
| reply_back | 91 | 0.11 | 0.07 | 16% | 1.5 |
| journalist | 13 | 0.08 | 0 | 8% | 0.4 |
| thread (own voice under own post) | 250 | 0.03 | 0.03 | 5% | 0.6 |
| post, not amplified | 63 | 0.03 | 0 | 3% | 0.15 |
| post, heavy amp | 41 | 0.02 | 0 | 2% | 0.1 |
| repost (15 sampled) | 15 | 0.07 | 0 | | 0.3 |

- Citizen-facing writes also bring follows. The 13 portal follows over 549 such writes add about 0.5 pts/w (see §4).
- Engagement arrives fast and then stops. On 798 posts checked twice, citizen likes and replies were identical at +1 h and +6 h (74/74, 66/65).
- **Caveat (coverage):** our per-post reads find 77 citizen likes and 68 citizen replies, but the portal counted 203 and 151. Reposts explain roughly 13 likes. The rest is unexplained. The portal may credit engagement we don't read, such as nested replies in threads. Treat absolute yields as about 2.5× too low; the relative ranking is what matters.
- **Lag link to changes of mind:** the 3 h write mix before the 5 "toward" hours matched "none" hours to within noise (reply 19 vs 20, thread 20 vs 18, repost 16 vs 13). **The inference is void (n=5, hourly granularity, unattributed).**

## 3. Self-amplification

- **Our likes or threads on replies to citizens: never tried.** All 1,489 own likes and 279 threads went to our own posts, not to replies to citizens (n=0), so this is untested.
- **Heavy amplified posts:** 42 posts cost **1,420 own likes**, **269 thread writes, 195 reposts** (plus the posts: **506 writes**), and about 380 LLM calls (posts, threads, and 57 thread rejects). They also drove most of the 1,786 filler likes, because each own like adds filler debt. In return they got **1 citizen like on the posts, plus 6 likes and 7 replies on the threads under them: about 140 points, or 0.28 pts/write.** Direct replies to citizens make about 3.1 pts/write, **roughly 11× more**. Non-own views were 0–12 per post, and some of those views came from other teams' bots.
- **Trending:** none of our posts appeared in the Trending top 50 in 36 snapshots, or in any of the 97 amp_measure checks (best_rank is None every time). About 38 likes in about 15 minutes is not enough against the other teams' rings.
- **Filler likes (1,786):** these land on other teams' No posts, so citizens are not involved and nothing can be measured. Their only job is camouflage against detection.
- **The bandit's own stats agree:** heavy 105 reward over 41 posts (2.6 each, and inflated by non-citizen views), against none 11 over 5 and light 12 over 5. There is no lift.
- **Verdict: self-amplification as built earns close to nothing.** Confidence is high for the posts themselves and medium overall. Points per hour did rise after amplification started (74 → 108 net of views), but that is confounded by more replies to citizens per write (0.16 → 0.40 portal replies per citizen-facing write) and by time of day. The amplified posts measurably got no citizen engagement. Its real cost is the bot's attention: in the last 4 h, threads ran at 16.5/h against 4.5/h for citizen-facing writes.

## 4. Follows

- We followed 80 citizen–voice pairs (79 after reply_backs, 1 "liked_our_post"). Today the 16 voices have **8 citizen followers** (priya 3, mere 3, isla 2, everyone else 0) out of 563 followers in total. The rest are team bots.
- **Follow-back:** 1 clear case (mere → 1654, 16 h later). In a second case (isla ← 1232) the citizen followed us one minute before we followed them. That is **1–2 of 80 (1–2.5%), about 0.25–0.5 pts per follow action.**
- **Follows come from our replies, not from our follows.** 6 of the 8 citizen followers followed the voice **0–2 min after that voice replied to them** (1232, 2092, 280, 625, 1654; 862 followed one minute after another voice's reply). Portal: 13 follows over 549 citizen-facing writes, about 2.4%, or +0.5 pts/write. The portal says 13 and we see 8. The gap may be unfollows or banned accounts (the portal shows 2 banned).

## 5. Citizen responsiveness

- **Speed:** across 42 citizen replies, the median latency is **1 min**, the 90th percentile is 5 min, and 40 of 42 arrived within 30 min.
- **Who:** 69 replies came from 61 distinct citizens, and **59 of the 61 were the citizen we had replied to.** Only 7 replied more than once; the top was 1192, three times. Bystanders almost never join in.
- **Reply rate** (share of citizen-facing writes that got at least one citizen reply):

| Dimension | Higher | Lower |
|---|---|---|
| act | reply 15% | second_voice 8%, reply_back 7%, journalist 0% (n=13) |
| source | latest 19% (n=183) | none/older 7%, news 7% (news gets the most likes, 0.38/w) |
| reply_mode | conditions_first 18% (39), reason_first 16% (82) | none 10% |
| lever | in_group 18%, permanence 16% | fear_answer 0% (21), loss 9% |
| frame | F14 13% (276), F1 12%, F10 15% | **F3 provax_antipass 5.5% (73), F2 no_end 2.5% (40)** |
| target_class | yes_reason 15%, conditions 11% | unsure 0% (12), off_topic 4% |
| text length | 120–280 chars 12% | <120 chars 6.5% (92), 280+ 0% (9) |
| persona | priya 15%, mere 14%, dan 15% | ben, grace, ruth 0% (15–24 each) |
| model | gemini-flash-lite 12% (301) | qwen3.8-27b 9% (135), kimi 7% (42) |

  Cells with fewer than 40 writes are suggestive only. Everything shares the confound of time of day and candidate supply.
- **Follow-ups (12 h later):** 533 contacts. 2 moved towards No, 1 towards Yes, 78 no change, 372 silent, 58 private. Persuasion we can see is around 0.5%.

## 6. Hours (Sydney time)

- **Citizens act around the clock.** Citizen replies to us fall in every 3-hour block (0–23 Sydney). Refresh candidates held at 30–37 from 04:00 to 01:00 Sydney with no day/night shape. Portal points have no clear diurnal pattern either.
- **Supply collapse:** refresh candidates fell **from ~30 to ~4 between 20 Oct 15:00 and 17:00 UTC** (02–04 Sydney), and new posts per hour fell from about 400 to about 50. They have stayed there since, and were 0–1.5 in the last hour. That is why citizen-facing writes dropped from 16/h to 4.5/h. The cause is open: either a deploy changed the filter (deploys at 15:01, 15:44, 15:53 and 16:11 UTC), or bot posts flooded the Latest feed. **This matters more than anything in §3.**
- **Bug found:** in `followup.py run()`, `our_ids` includes posts we only *liked* (like rows have `live` and `post_id`). As a result, the "trending" outcome records list filler-liked posts (137 of them, none ours), and `replied_to_us` in followups is inflated.

## Ranked actions

**Scale**
1. **Direct replies to citizens' fresh Latest posts** (3.1 pts/w, about 15% reply rate, plus about 0.5 pts/w in follows). Get supply back first: find out why candidates fell from 30 to 4 (filter or flood), page deeper into Latest, and use the news-comment threads. High confidence.
2. Use conditions_first and reason_first reply modes and the in_group and permanence levers, at 120–280 characters, from the priya, mere and dan personas on gemini-flash-lite. Medium confidence.
3. Keep talking to citizens who reply: they answer within minutes, and that is where the follows come from.

**Cut**
1. **Heavy amplification of our own posts** (0.28 pts/w, never in Trending), plus the threads and reposts it creates. Do this at least while candidates for replies to citizens are waiting. Cutting it also removes most of the filler likes and much of our blue-team exposure.
2. Proactive follows: about 1% follow-back. Keep them only because they cost no write.
3. Journalist replies (0/13 replies), the F2 no_end and F3 provax_antipass frames, the fear_answer lever, and replies under 120 characters.

**Test**
1. One or two own likes on our replies to citizens (never tried, n=0). An A/B on alternate replies would show whether it lifts citizen likes.
2. Whether vaccine-talk content drives the "neither, on vaccination" events: hold back the F3 and F13 frames for 6 h and compare event counts.
3. Find the portal gap (203 likes against the 77 we read): read nested replies and likes on reposts for a sample.
4. Fix the `our_ids` bug in followup.py.
