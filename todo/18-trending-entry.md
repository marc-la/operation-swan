# 18: Getting into Trending: prove it, or switch to riding No posts already there

**Owner:** Marc + a fresh Claude session · **Depends on:** nothing · **When:** 22 Oct

## Read first
`CLAUDE.md`, [amplification](../docs/06-strategy/amplification.md) (how Trending ranks, the 20 Oct fit, detector risks), `src/swan_bot/amplify.py` (`on_post`, `measure`, `track_ranks`), `config.AMP_LEVELS`.

## Why: it is unproven, and the bar is moving
- **No amplified post of ours has ever reached Trending.** About 20 heavy posts on 20–21 Oct. All `amp_measure` rows have `best_rank: None`, 0 citizen likes and 0 citizen replies, and their views are our own.
- **The cutoff went up:** #35 in Trending had `global_hot_score` ~24 on 20 Oct and **~37.2** on 21 Oct 05:20 UTC (#1 was 43.6).
- The 20 Oct fit: `hot ≈ 1.85·√(likes + replies + 8·reposts) − 2.1·age_h + 10.8`. At a cutoff of 37, a post a few minutes old needs √X ≈ 14.4, **about 200 like-equivalents**. Dan's post 122893 (21 Oct 04:48, the first under the 21 Oct settings) had 38 likes, 13 replies and 5 reposts, ~90 like-equivalents, hot ~27. **We push less than half of what's needed**, if the fit still holds.
- Our likers are capped by accounts: 48 active, and only ~11 voices may write (reply or repost).

## Questions to answer, in order
1. **Is the fit still right?** Re-fit it on fresh data. The targeter already reads Trending every 4 min (`Targeter.refresh`). Log the top 35's `global_hot_score`, `rank_position`, counters (`social.counters`) and age each time for ~6 h. Fit hot against likes, replies, reposts, views, age, and, if the data allows, *distinct* engagers and the author's followers. Write the fit and its error into amplification.md with the date.
2. **What does a post that gets in look like in its first 15 min?** Pick 5 posts that enter Trending (not ours) and read their counters every 2 min from posting (counters are cheap: 300/min). That gives the engagement curve, so we know whether early speed or the total matters.
3. **Can we reach the dose?** With the new fit, cost out the ways to ~200 like-equivalents (or whatever the fit says):
   - **Reposts weigh ~8 likes.** Only voices repost today (5–6, one each). Boosters reposting would add ~30, but a repost is a post that can be reported and hidden, and every booster already has over 100 actions, so one hidden repost puts a booster one account report away from suspension. Ask on Discord (`#questions`) or test on 2–3 boosters before scaling.
   - **Concentrate:** one post every 2 h with every account on it, instead of one an hour.
   - **Timing:** everything inside the first 10 min (`LIKE_DELAY`, `THREAD_DELAY`, `REPOST_DELAY`), against detection: the hourly ring audit (`scripts/swan_watch.py`) alerts when we look as coordinated as the leaders.
   - **More voices** ([todo/17](17-new-personas.md)).
4. **Decide, with a kill rule.** Run the best plan for ~8 heavy posts. If none enters Trending, stop paying for entry. Move the write budget to **riding No posts that are already in Trending** (9 of 21 were No on 21 Oct, none ours): our voices reply under them (their threads get 300–480 views, and likes and replies on our replies score for us), and boosters' filler likes keep them up (`FILLER_RATIO`; 60% of filler already goes to No posts). Targeting already reads 12 Trending threads for citizens to reply to (`config.TRENDING_THREADS`).

## Guardrails
Reads only, apart from the amplification the bot already does. Anything new that writes (booster reposts, a new level) goes in behind a config flag, default off, dry-run first. Watch the hidden-post alerts: each lost voice costs reach for the rest of the campaign.

## Done when
A dated fit and the entry curve are in amplification.md, and the team has decided between pushing harder (with the dose and its risk) and riding No posts in Trending. That decision is in config and running.
