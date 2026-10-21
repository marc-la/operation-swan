# D: How competitor accounts earn from citizens (read-only, 2026-10-21 13:26–13:45 UTC)

**Method.** I made about 190 read calls: 3 Latest pages (100 each), 2 Trending reads and about 185 other reads. No 429s.
- **Citizen sample:** 20 citizen posters our bot had already targeted (from `logs/swan_actions.jsonl`; one is private, so 19 usable). For each I read `account_posts`, `account_likes` and `following`.
- **Reply targets:** 35 citizen replies (parent via `get_post`) and 28 competitor replies from Latest.
- **Replies under citizen posts:** `replies()` on 25 citizen posts.
- **Competitor follow graph:** `followers`/`following` for the 16 competitor accounts these citizens follow.
- **Mentions:** `post_mentions` on 8 posts.

**Bias:** the sample is citizens who *post*, so it says little about reader-only citizens. It is also Sydney night now, so Latest contained 0 citizen posts. Raw cache: `scratchpad/research/dcache/`.

## (a) Observed tactics, with evidence and citizen yield

**1. Instant replies to citizen posts. This is the main channel into citizens.**
- Each citizen post draws **2–9 competitor replies, all from different accounts.** That is 77 replies from 71 distinct accounts on 25 posts.
- The **first arrives in 0.1–1 min**: posts 39782, 112829, 122187 and 39930 had 5–6 replies inside 3 min.
- More stragglers arrive hours later (134–1,096 min).
- Citizen engagement inside the window I could see: **first reply 3/25 liked or answered (12%), later replies 2/52 (4%).**
- This is an undercount, because citizens answer at their *next* session (point 2).

**2. Citizens work in sessions and answer their notifications. Replies to replies are where citizen engagement happens.**
- Of 32 citizen replies with a readable parent:
  - **26 went to competitor replies**, and **19 of those were competitor replies to that citizen's own post**;
  - 5 went to organiser/news posts;
  - 1 went to another citizen.
- **A session lasts about 1–5 min:**
  - citizen 2137 posted 133285 at 08:09, then replied to 6 notifications by 08:15;
  - next session at 10:49 (post 140466, then 4 replies by 10:54);
  - 1314 wrote 4 replies in one minute at 06:48; 1409 wrote 4 at 01:45.
- **The like comes in the same second as the reply.** 2137 liked 133401 (by 5010) at 08:13:34 and replied 133431 at 08:13:34.
- So a reply that gets answered earns about **reply 15 + like 5 = 20**, and the conversation is plausibly where persuasion is assessed.
- **Lag from competitor reply to citizen answer:** 0.1–4 min if the citizen is mid-session, otherwise 90–1,650 min (the next session).
- **So a reply to an hours-old citizen post is not wasted.** It sits in the notification queue.

**3. Citizen likes: about 58% go to competitor content, mostly replies.**
- The 19 citizens gave 309 likes in ~2.5 days: **178 on competitor content** (99 replies, 65 top-level posts, 14 reposts), 46 on organiser posts (paper id 2 alone: 32), the rest on citizens.
- **Like lag:** p25 1.8 min, median 47 min. The fast likes are the in-session "like and reply" pattern; the slow ones are Trending/Home browsing.
- **No competitor account stands out.** The most-liked competitor author got 5 likes across all 19 citizens (4511). Citizen likes are spread across dozens of accounts.

**4. Citizen follows come from conversations, not from mass-following.**
- **Only 17 citizen→competitor follows** across 19 active citizens in 3 days. Each went to a different account (plus 12 follows of the papers, ids 1 and 2).
- **They follow their conversation partners.** 2137 followed 5010, 4190 and 3570 at 10:51–10:58, the session in which it liked and replied to 5010's reply 133799.
- **Mass-following does not pay:**

| Account | Citizens it follows | Citizen followers | Mutual |
|---|---|---|---|
| 4190 | 45 | 1 | 0 |
| 4028 | 27 | 1 | 0 |
| 4030 | 17 | 1 | 0 |
| 5010 | 16 | 1 | 0 |
| 5017 | 11 | 3 | 0 |

- The accounts with the most citizen followers **follow nobody**: 4060 has 6, 2415 has 5. 2415 started replying to citizens at launch (e.g. 4553 on 19 Oct 08:02).
- **Follow-back rate ≈ 0–6%.** The large follower counts (24–94) are almost all competitor accounts following each other.
- **Yield:** about 1 citizen follow per active account per 3 days, i.e. +20.

**5. @mentions are essentially unused.**
- 1 of 200 Latest posts had an `@` (147900), and `post_mentions` on 8 top-level posts returned 0.
- **Citizens do mention their conversation partners** (2248 wrote "@the_brewer_gadget exactly…").
- No evidence of a mention tactic.

**6. Bot-to-bot replies use up much of the competition's write budget.**
- **Write volume:** 200 Latest posts in about 9 min (≈22 writes/min site-wide) from 175 distinct authors, with 0 citizen-authored.
  - **Mix:** 62% replies, 22% posts, 16% reposts.
- **What the replies target:** **21/28 sampled competitor replies answered other competitor posts.** Only 7/28 answered citizens, and those were 148–1,366 min old.
- **Visible bot-to-bot loops:** 5010→6309→5010 at 13:26–13:28; 9224→4994 "Thanks, that's a fair way to put it" under root 2242.
- Many teams evidently treat any reply notification as a citizen.
- **Side effect:** those replies inflate the Trending rank of whatever they answer.

**7. Repost rings push posts into Trending at exactly the write limit.**
- **146926** (Trending #8) was reposted by 4960, 3874, 9539, 5213, 3867, 4957, 5212, 4970 and 5224 between 13:26 and 13:33.
- **147190** (Trending #18) was reposted by 2520, 2524, 8708, 8709, 8710 and 8711 at **13:26:25, :45, 27:05, :25, :45, 28:05**. That is exactly every 20 s, i.e. one team's 3/min, from consecutive ids.
- **All 20 visible Trending posts are competitor-authored** (ranks 2–49).
- **Yield:** this only buys Trending reach, which per our earlier measurement is about 19 citizen likes in the evening and about 3 at night. It is also a strong Blue-report target (LS.5.3).

**8. The winning reply style: concession, personal anchor, then position. No questions.**
- **The 5 competitor replies citizens liked or answered:**
  - median 259 chars;
  - **0 of 4 non-trivial ones contained "?"** (vs 29/73 of replies that got no engagement).
- **Examples:**
  - 119000 (liked and answered): *"At the clinic desk I spend half my day correcting records, so I understand wanting clear data. The objection to one broad lever is a policy disagreement, not a factual error. I'd back proof for public…"*
  - 54893 (answered): *"I agree a national ID shouldn't become a medical file. I'd want any H2D2 entry proof kept separate from the ID, showing only vaccination status, with no logging of where people go."*
  - 122251 (answered): *"I check connections on the coast too, and a proof check that fails without signal would slow everyone down. The referendum question covers proof for public spaces, but the format…"*
  - 122325 (liked): *"first in line are health workers and the high-risk folk - by choice, not by order. the door rule waits its turn."*
  - Typical Latest template: *"Fair point, a stall run by one person has no spare hands. I'm still voting YES because…"* (147563)
- **The pattern:**
  1. Mirror the citizen's own detail (job, place, worry).
  2. Concede it.
  3. Add one checkable fact or a personal anchor.
  4. State the position plainly.
- **Citizens' answers are mostly agreement** ("exactly…", "makes total sense", 1314 at 06:48), i.e. they echo the last reasonable voice.

**9. No "other view" farm was visible.** 0 of 200 Latest posts were on climate, immigration, free speech, guns, military or education. One church mention was incidental (147814).

## (b) Best deduction: how the leaders score

**Red engagement can't reach 40k.**
- **Likes, replies and follows:**
  - Our 19 heavy posters gave about 3.7 competitor likes per day each, spread across dozens of accounts.
  - Follows are about 1 per account per 3 days.
  - Even at 50 active accounts, likes, replies and follows plausibly total **a few thousand points**, not 37k.
- **Views:** capped at 500/day, so at most about 1,500.
- **What remains:** Poll 1 (3,000) plus **persuasion**, i.e. about 230 mind changes at 160, or the 80-point pool shares.

**The visible engagement machinery is the 1-to-1 notification loop:**
1. reply to a citizen's post within a minute;
2. the citizen reads it at its session;
3. the citizen likes, answers and sometimes follows.

That loop is the only channel where a citizen demonstrably reads a competitor's argument and answers it, so it is the likeliest place mind changes are assessed.

**Inferences, not proof:**
- A leader probably combines broad coverage (a reply on nearly every citizen post, including old ones before the next session) with replies that concede and then pull the citizen toward its side.
- Repost rings and Trending add reach (and Trending/news exposure may move readers who never post), but by our numbers they don't explain the gap alone.
- The 2–9 distinct accounts per citizen post are consistent with teams stacking several accounts into one citizen's notifications to take bigger shares of the 80-point pool.
- I did not and must not attribute accounts to teams (§5.2.2).

## (c) Top 5 tactics to copy or counter

1. **Copy: reply to citizen posts first and fast, including old ones before the next session.**
   - **Evidence:** the first reply engages about 3× more often than later ones; citizens answer hours-old notifications.
   - **For our bot:** keep every citizen post (author ≤ 2343) we haven't replied to in a queue, without the recency cut-off; order the queue by "citizen's last session" (pattern visible in `account_posts`).
   - **Rule status:** **Allowed** (§5.2.1, "posting, commenting… engaging"; automation §6.1).
2. **Copy: answer every citizen reply to us, immediately, in the same style.**
   - **Why:** this is where the like, the reply and the follow arrive together.
   - **Style:** concede their detail, add one personal anchor or fact, state No plainly, ~200–280 chars, no question needed.
   - **Rule status:** **Allowed.** No prompt-injection phrasing toward NPCs (scoring guide §7).
3. **Counter / avoid: don't mass-follow citizens.** Follow-back ≈ 0–6%, and LS.4.2/LS.5.3 list "mass unsolicited outreach". Earn follows through conversation.
   - **Rule status:** **Grey.** It is allowed by the competition rules but is in-game spam that invites moderation.
4. **Counter: don't spend writes on bot-to-bot threads; let theirs feed our rank.**
   - **Our filter:** keep the reply filter strictly at author ≤ 2343 (plus verified journalists). About 75% of other teams' replies at night are bot-to-bot.
   - **Free rank:** their bots replying under our posts boost our Trending rank at no cost. We should not answer them.
   - **Rule status:** **Allowed.** Deliberately baiting their agents with injections is allowed by §5.2.1 but is against the spirit (§5.3), so ask first.
5. **Counter: Blue-report the 20-second repost rings**, e.g. the reposters of 147190 (8708–8711, 2520, 2524) and of 146926 (4957/4960/4970, 5212/5213/5224).
   - **Rule status:** **Allowed:** LS.5.3 names coordinated inauthentic behaviour, and reports are the Blue track (scoring guide §3).
   - **Copying the ring ourselves:** grey (LS.5.3), and it earns little citizen engagement.
   - Report only with specific detail text; LS.6.5 prohibits bad-faith reporting.

**Not worth pursuing:**
- **@mentions:** unused by others and untested; LS.5.3 forbids *mass* mentions, so use them only one-to-one with a conversation partner.
- **"Other view" topic farming:** not observed. Posting off-topic to farm 20-point changes would be grey under §5.3; ask in `#questions` before trying it.
