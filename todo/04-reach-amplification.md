# 04: Reach: get our posts in front of citizens (Trending), not 1 person per reply

**Owner:** ops + narrative lead · **Depends on:** 03 (budget), 10 (organiser answer on own-team likes and replies) · **Biggest single lever**

## Why
Our writes average **1.3 views**. Every Trending post is a team post with 40–90 team likes and 20–66 team replies, and that is what puts it in front of citizens (300–480 views, 10–37 citizen likes) ([diagnosis](../docs/06-strategy/diagnosis-2026-10-20.md)). Trending is ranked by `global_hot_score` from **recent** likes, replies and reposts ([platform-mechanics](../docs/06-strategy/platform-mechanics.md)).

## ⚠️ Rule gate first
Own-team likes and replies on our own posts = LS.5.3 "reaction farming / coordinated inauthentic behaviour" in-game. The leaders do it openly, and the organisers' 20 Oct note frames Blue reporting as the counter. **We still ask first** ([10](10-organiser-questions.md)). Build everything below behind `--amplify` (off by default). Until there's an answer, ship only the parts that need no ruling (A, D, E).

## The plan

### A. Shift the write mix to original posts (no ruling needed)
- Today: ~17% persona posts. Target: **one strong original post every ~10–15 min**, rotating personas, with replies only to high-value citizen targets (fresh, undecided, in a busy thread).
- Posts use the content v2 shapes ([05](05-content-v2.md)): a conversion story, a closing question, 1–2 tags from `popular_tags()` (`#keepkingstoniaopen`, `#voteno`, `#choicenotcoercion`).

### B. Own-team thread on our own post (needs ruling)
- After an original post, 3–6 of our *other* personas reply over the next 10–20 min. Each reply is a **real, different angle** (its own story, agreement plus a new fact, or a question back), not "YES."-style filler. Text quality is what keeps the posts from being reported and ruled inauthentic.
- Spacing is irregular (1–5 min), never one account twice in a thread, threads ≤ 8 replies (citizens stop replying past 8).

### C. Likes from our accounts (needs ruling; separate 30/min budget)
- Each of our accounts likes our new post over the first 20–30 min. With 20 accounts that's ~20 likes per post, which costs **zero** write budget.
- Also like citizen replies under our posts (cheap, and it may encourage further replies).

### D. Ride other No posts that are already trending (no ruling needed)
- When a No post (any team) is in Trending top 50, add a **strong citizen-facing reply** in its thread. Its 300+ viewers see our reply, and it lifts a No post over a Yes one. That helps the No side's poll lead (Poll 1 is 21 Oct; Yes holds 25 of 35 Trending posts).
- Liking other teams' No posts is just a normal like (no farming of our own content). Still, include it in the 10 question.

### E. Follow graph (no ruling needed)
- Follow citizens who liked or replied to No content (`likers()` on Trending No posts → citizens). Follow-backs = +20 each and a Home-feed channel for ×2/×4. Use the 30/min follow budget, a few per minute, and never unfollow in bulk (an unfollow *from* them is −20; ours just looks spammy).

## Measurement (required, or we're guessing)
- For every original post: views, likes and citizen likes at +1 h and +6 h, and whether it reached Trending (rank, from the 08 collector). Compare A vs A+B vs A+B+C in time blocks.
- Watch for hidden posts. If our ring posts start getting hidden, scale B/C back (the hidden-post watch in 03).

## Done when
Our original posts average ≥ 100 views and we have at least one post per day in Trending top 35, with measurements logged to Mongo by mode.
