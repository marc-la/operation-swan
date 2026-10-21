# Platform mechanics: each component and how it feeds the score

> Observed 2026-10-19 around 10:00–11:00 UTC (~4 h after launch), using **read-only** API calls only (feeds, posts, counters, replies, likers, accounts, followers, tags). The web UI at social.legitreal.com is a JavaScript app; everything below came from the API, which returns what the UI shows. Re-check as the game evolves. Official behaviour: [api-reference](../04-technical/api-reference.md), [scoring-guide](../03-scoring/scoring-guide.md).

## Key observations

1. **The platform is mostly bots.** Of the last 50 posts in Latest, **43 came from accounts created after launch** (teams), **4 from accounts created before launch** (citizens) and 3 from private accounts. Citizens mostly **read and like**. They post rarely, and when they do it is often a doubt: "voting Yes, but… sunset clause", "publish the list and an end point".
2. **Citizen vs team accounts can be told apart by `created_at`.** Teams could only register from launch (19 Oct 07:00 UTC = 6pm Sydney). Accounts created earlier (from 18 Oct 12:16 UTC, ids up to ~2,300) are organiser-made: citizens and verified figures. Post-launch accounts (e.g. ids 2,356+, created 07:01 onward) are teams. Private accounts hide `created_at`. *Treat this as a strong heuristic, not proof.*
3. **Verified characters are live and talk in threads.** Verified accounts 1–11 are the two papers, four journalists (`amanda_rivera`, `muzhi_wong`, `julio_morales`, `lisa_podworth`), `MarinaCastilloCEO`, `DrAmaraSingh`, `legit_admin` (moderation), `gregorybrotherston` and `RealVictorHawthorne`.
   - **Journalist `julio_morales` replies constantly**, with No-friendly lines ("We can't vote on a blank check", "moves the decision from the voters to the bureaucrats").
   - **`amanda_rivera` posted that she's voting NO on the broad mandate.**
   - **Castillo's account replies and reposts with No lines.** Singh replies conciliatorily. Hawthorne had posted nothing yet.
   - The journalists write the news, so **their threads are the most direct route into the papers.**
4. **Trending #1 was artificially amplified.** Yes post #7450 (team account) had 62 likes, 40 replies, 16 reposts and 54 views. Most replies were one-line "YES." posts from accounts with **consecutive ids (2463–2497)** created at launch. Likers included real citizens (e.g. `janet1966`, `bettyp_coder`). Coordinated amplification works, and it is also an obvious Blue-report target.
5. **Embeds.** Links to `sites.legitreal.com` articles become an **article card** (title, excerpt, image, paper name). Giphy links become a **GIF card** carrying its title and tags (e.g. "confused, unsure, hesitant"). So a post linking a No-friendly article carries the paper's headline and excerpt with it.
6. **Profiles have no bio field.** Only username, display name, avatar URL and private flag. One team puts the role in the display name ("Mere Tavita-Lowe | ICU nurse"). Persona credibility comes from the display name and post history.

## Component by component

| Component | What it does | How it scores | Notes for us |
|---|---|---|---|
| **Latest feed** | Every post, newest first | Views (capped) | ~86% bots: a post sinks in minutes. Only useful for being seen *right now* |
| **Trending feed** | Ranked by `global_hot_score` from **recent likes, replies, reposts** | The big reach multiplier | **Any reply or like boosts the target's rank, including counter-replies under a Yes post.** Reply under Yes posts only when the reply is strong. Fit on 2026-10-20: a repost ≈ 6–8 likes, a reply ≈ 1; −2 points/h; top-35 cutoff ≈ 24 ([amplification](amplification.md#how-trending-ranks-measured-2026-10-20-1113-utc-read-only-top-36--counters)) |
| **Home feed** | Personalised; followed accounts more prominent | Reach to followers | Our followers' Home is our channel for the ×4 days |
| **Post** | ≤500 chars, `#tags`, `@mentions`, article/GIF embeds | Views 1, likes 5, reposts 10, replies 15, follows 20, mind change 160 | Our main vehicle for persuasion; needs early engagement to escape Latest |
| **Reply** | Threaded under a post; **notifies the author**. Citizens reply most to a direct reply to *their* post, and rarely once a thread is **>8 messages deep** | Same as a post (it's our post) | Lands in front of a specific person: a doubting citizen, a journalist, or a thread's readers. Uses the 3/min write budget |
| **Repost / quote** | Re-shares (optionally with comment) to followers | Citizen reposting *our* post = 10; repost-of-repost credits the original | Our bare reposts earn us nothing; quote posts are new posts. Uses the write budget |
| **Like** | Own 30/min budget; no notification | Citizen liking our post = 5; our likes = 0 | Raises the target's Trending score. Self-likes to seed Trending: ask first |
| **Follow** | Own 30/min budget | Citizen follows us = +20; unfollow = −20 | Followers are capital for ×2/×4. Following citizens might earn follow-backs: test |
| **Mention** | `@user` notifies them. **≤4 per post, ≤3 per reply**, else rejected | — | Puts a post in front of journalists/figures. Sparingly ("mass mentions" are in-game spam) |
| **Tags** | `popular_tags()` (top 15, 24 h), `tag_posts()` | Indirect | Top: #keepkingstoniaopen, #h2d2, #choicenotcoercion, #voteyes, #protectkingstonia, #yes2h2, #voteno. One or two per post at most |
| **Notifications** | Replies and mentions to our accounts | Lets us continue conversations | A citizen replying to us is +15, and replying back keeps them engaged |
| **Counters** | `counters(post_id)`: likes, replies, reposts, views | Our measurement | Views count citizens; likes/replies include bots |
| **News sites + news accounts** | AI journalists write from platform activity; papers post articles as verified accounts | No direct points to anyone | Reply/quote under news posts; link No-friendly articles for the card |
| **Verified figures** | Castillo, Singh, Hawthorne, journalists, moderation | Moderator rulings on their posts are always correct | Castillo is on our side; journalists are persuadable conversation partners |
| **Reports / moderator** | Inauthentic reports → ruling ≤ 3 h later (since 20 Oct) | Blue: 25 / 5 / 15 | Patterned one-line replies from consecutive-id accounts = high-confidence targets |
| **Feed lock** | Read-only mode (moderator or end of game) | — | Writer should check `feed_lock()` |

## What our accounts should do (roles)

One account = one persona (a person with a name, town, job and voice). Persona *types* repeat across accounts with different people. Suggested day-1 mix: **8–12 accounts**, scaling toward ~25 once the loop is trusted. Every registration uses one of our 200 lifetime slots.

| Role | Share of accounts | Does | Doesn't |
|---|---|---|---|
| **Responder** (most accounts) | ~60% | Replies to citizen doubts and journalist threads in persona; answers replies to itself; 1–2 originals/day | Pile onto a citizen already answered by us; reply to everything |
| **Storyteller** | ~25% | 2–4 specific first-person posts/day (+ slice-of-life); links No-friendly articles | Slogans, hashtag stuffing |
| **Watcher** (Blue desk; can be the human with any account) | 1–2 accounts | Reports high-confidence competitor bots | Report citizens or anything uncertain |
| **Amplifier** | Boosters (like-only) + voices; decided 2026-10-20 | Likes/reposts/thread replies on our posts to seed Trending | See [amplification](amplification.md) |

## Citizen engagement profile (2026-10-19)

Method: Trending top 50. For each post, counted likes and replies from **citizen accounts** (pre-launch, id ≤ 2,343, not verified) and compared them with total counts. Also read 150 Latest posts.

- **Citizens make up only 15 of 150 Latest posts (10%).** The rest are team bots and the papers.
- **Citizens talk to citizens.** Citizen-written doubt posts drew **15–30 citizen replies** and ~400–1,200 views each. Team-written Yes testimonials ("I run a bakery", "I'm a nurse") drew 6–17 citizen *likes* but **0–1 citizen replies**: their 40+ replies were other bots. Bot-inflated rank doesn't buy conversation.
- **News posts get the biggest citizen audience** (1,100–2,000 views, 17–30 citizen replies). Citizens are in the news threads.
- **The dominant citizen position is "Yes, but only with…"**: sunset clauses, a published venue list, independent oversight, keeping it off the ID card, medical exemptions. They don't want a "blanket mandate". This is the swing group. The ballot contains none of those guarantees, hence frame **F14 "No 'Yes, but' box"** ([frames](frames-and-messengers.md)).
- **Some citizens are firmly Yes** ("protect the hospitals first", "false choice!!!") and **some are hostile to KITB** ("more worried about their resort bookings"). This confirms: no KITB-voiced messengers, and don't argue with firm Yes citizens.
- **Citizen style:** casual, lowercase, emojis, lots of Giphy reaction GIFs, short. Team posts are longer and polished. Matching citizen register probably reads as in-group (test it).
- **Profile tell:** 0 of 20 sampled citizen accounts had a display name equal to their username. Several team accounts have that, or no display name at all.

## Finding and profiling citizens (2026-10-19)

- **Who is a citizen:** an account created **before launch** (19 Oct 07:00 UTC). Account ids are sequential, so **id ≤ 2,343** also works for private accounts that hide `created_at`. Ids 1–11 are verified figures and journalists. Organisers said more NPCs may be added mid-game, and those would have high ids. Watch for them; signs are a real-name display name (0/20 citizens had display name = username) and casual, local posts.
- **Two kinds of citizen:**
  - **Posters** (~10% of posts). Reach them with a **reply** to their post, which notifies them.
  - **Readers** (most of the ~6,000). They only like. `account_likes(id)` shows what they liked. E.g. `janet1966` never posts but liked two Yes testimonials *and* two "yes, but only with safeguards" posts: a soft-Yes reader. We reach readers through Trending, news threads, Home (if they follow us) and, sparingly, an @mention.
- **Profile per citizen (built up gradually, not one big scrape):** a stance score from their likes and posts (Yes / soft Yes / unsure / soft No / No); the doubts they've voiced (sunset, venue list, ID card, two-tier, hospitals); and the last time we contacted them.
- **Who to target:** soft Yes and unsure first (persuasion pays 160). Skip firm Yes (backfire risk) and firm No (echo: engagement only). *Superseded 2026-10-22 ([todo/21](../../todo/21-reach-every-citizen.md)): every citizen item on the vote is a candidate, and the stance sets the priority (firm No low, firm Yes as a small capped arm).*
- **Measuring persuasion directly:** after we contact a citizen, check whether their **later** likes and posts shift toward No. It's slow but it's the closest thing to seeing a mind change per citizen.
- **Honest note:** citizens *do* like the Yes sob stories (6–17 citizen likes each). They buy engagement. What they don't get is citizen conversation.

## Citizen ids and the feed budget (2026-10-21, todo/21)

- **Seeded citizens vs team accounts.** Over runs of 30–40 ids, seeded citizens were created every 25–42 s (median), evenly (cv of the gaps ~0.7). Team accounts were created every ~13 s, in bursts (cv 1.4–1.9). Private accounts show no `created_at`. `get_account` has no field that tells the two apart.
- **Bulk team runs look seeded.** A full walk of `accounts()` on 21 Oct (9,198 accounts, up to id 9961) found team runs at the seeded pace: four of 20–36 ids, plus **5304–5612 (309 ids)** and **8238–8520 (283 ids)**. Signs these were teams: bot names ("Civic Voice 08", `civic_voice_08_bc923e`), replies a minute after creation, and 404 holes at both ends. So pace is only a hint. **The real proof of new citizens is an organiser announcement on Discord.** `scripts/citizen_watch.py` (hourly, in swan_watch) alerts on runs of ≥ 50 ids past 9961. A person confirms a run and adds it to `config.EXTRA_CITIZEN_RANGES`; nothing is added automatically.
- **Feed budgets are per route.** `feed_latest` and `feed_trending` each answered with their own 10/min bucket: at 14:41:38 UTC, Latest showed remaining 0 and Trending, 21 ms later, remaining 8. `account_posts`, `replies` and `get_post` each have their own 300/min. The organisers' table says "10 between them" for the feeds. Trust the headers, not the table ([api-reference](../04-technical/api-reference.md#rate-limits)).
- **Open:** on the box, the Latest bucket emptied with no logged reader to account for it. Every feed call on the box now goes to `logs/feed_reads.jsonl` (bot, swan-blue, followup, swan_watch), and the bot is the only Latest reader (`data/latest_snapshot.json`).
