# 04: Reach: own-team amplification into Trending (reaction farming, made to look organic)

**Owner:** ops + narrative lead · **Depends on:** 03 (budget) · **Biggest single lever**

## Why
Our writes average **1.3 views**. Every Trending post is a team post with 40–90 team likes and 20–66 team replies, and that is what puts it in front of citizens (300–480 views, 10–37 citizen likes) ([diagnosis](../docs/06-strategy/diagnosis-2026-10-20.md)). Trending is ranked by `global_hot_score` from **recent** likes, replies and reposts ([platform-mechanics](../docs/06-strategy/platform-mechanics.md)).

## Decision (Marc, 2026-10-20): we do it
Own-team likes and replies on our own posts, built to look organic.
- **Rule status:** Legit Social rule **LS.5.3** names "coordinated inauthentic behaviour" and "reaction farming", and says such accounts "may be restricted or removed". We read that as an **in-game** rule enforced by in-game moderation (reports → hidden posts → suspended accounts). The top teams do it openly, and the organisers' 20 Oct response was to strengthen Blue reporting, not to penalise anyone. The Q1 in [10](10-organiser-questions.md) is now a confirmation, not a gate. If the organisers say it breaches the *competition* rules, switch `--amplify` off that day.
- **What "look organic" means here:** hard to tell apart from real users *for other teams and the in-game moderator*. That is the Red/Blue game. It does **not** mean hiding anything from the organisers. Every like, reply and follow is still logged in `logs/swan_actions.jsonl` with account, persona and owner (CLAUDE.md rule 6). No rate-limit evasion, no IP tricks, no extra accounts beyond our allowance.

## Fingerprints to avoid (we see them in the leaders' rings; Blue teams will too)
| Ring tell (observed 20 Oct) | Our rule |
|---|---|
| 40–90 likes, all from team accounts, almost no citizen likes, in the first minutes | 6–20 own likes per post, a **random** subset of our accounts, spread over 5–120 min with a front-loaded decay curve. Never within 30 s of posting |
| Likers that only ever like that team's posts | Every account also likes **other** content: citizen posts, other teams' No posts, news posts. Aim for ≥ 50% of each account's likes going to non-own posts |
| One reply a minute from different personas, all on one frame | 2–6 own replies per post, irregular gaps (1–15 min), **different** frames and lengths. Some one-liners, some questions, some light pushback ("not sure about X, but…") that the author persona answers |
| Burst-registered families (same minute, templated usernames) | Already avoided: drip registration 15–40 min apart, varied handle styles |
| Every account active 24/7 | Per-persona waking hours (a nurse on nights, a retiree up at 5 am); each account sleeps ~7 h |
| Identical cadence across posts | Not every post gets amplified; vary which ones and by how much (a bandit picks: see Measurement) |

Run the Blue detector from [07](07-blue-desk.md) **on our own accounts** daily. If it would flag us, we change the pattern before someone else reports it. Hidden-post watch (03) parks any account at 2 hidden posts.

## The plan
- **A. Write mix → original posts.** One strong original every ~10–15 min, rotating personas, in the content v2 shapes ([05](05-content-v2.md)): conversion story, closing question, 1–2 tags from `popular_tags()`. Replies only for high-value citizen targets.
- **B. Own-team thread** on each amplified post (rules above). Replies are real, citizen-readable content; they're what thread readers see.
- **C. Own likes** (30/min team budget, separate from writes) as above. Also like citizen replies under our posts.
- **D. Ride other teams' trending No posts.** A strong reply in their thread (300+ readers) and a like. Lifts No over Yes in Trending before Poll 1 (21 Oct; Yes holds 25 of 35 Trending posts).
- **E. Follow graph.** Follow citizens who liked or replied to No content; +20 per follow-back, plus a Home-feed channel for ×2/×4. A few follows a minute; no bulk unfollows.
- Everything behind a `--amplify` flag. Turn it on in `deploy/run.sh` once a dry run shows the schedule.

## Measurement (required)
- Per original post: views, likes and citizen likes at +1 h and +6 h; Trending rank reached (from the 08 collector); own likes and replies spent on it.
- A **bandit over amplification levels** (none / light / heavy): reward = citizen likes + 3 × citizen replies + views/10, net of the write slots spent. It tells us the cheapest level that trends.
- Watch hidden posts per account. If they start climbing, scale B/C down.

## Done when
Our amplified posts average ≥ 100 views, we have ≥ 1 post per day in Trending top 35, and our own Blue detector doesn't rank our accounts above the leaders' rings.
