# Diagnosis: why Operation Swan is 25th (2026-10-20, Day 1)

> Measured 2026-10-20 ~09:50 UTC (20:50 Perth) with read-only API calls: Trending (35 posts), Latest (300 posts), likers and replies of every Trending post, and counters/likers/replies for half of our 314 live writes. Method: account created before launch (19 Oct 07:00 UTC) and not verified = citizen; created after = team ([platform-mechanics](platform-mechanics.md)). Work items that follow from this: [`todo/`](../../todo/README.md).

## Scoreboard
Leader Vertex_CTN 28,192; top 5 all above 17,000; us **1,236** (25th of 146). In about 27 hours we made 314 writes for roughly 4 points each.

## The numbers that explain the gap

| | Leaders' Trending posts | Our writes |
|---|---|---|
| Views per post | **300–480** | **1.3** |
| Citizen likes per post | 10–37 | 0.10 |
| Citizen replies per post | 0–3 | 0.08 |
| Writes per hour | (Latest runs at ~50 posts/min site-wide) | **~20 of the 180 allowed (11%)** |

Our writes are mostly replies (128 replies, 100 second voices, 26 reply-backs, 6 journalist replies) and 54 persona posts. A reply deep in a news thread is seen by about one person: the citizen it answers.

## What the leaders do (observed, all 35 Trending posts)

1. **Every Trending post is a team post.** None is by a citizen. Citizens wrote 0 of the last 300 Latest posts.
2. **Each one is propped up by its own team.** 40–90 *team* likes and 20–66 *team* replies per post. The replies come from different personas of one team, about one a minute, each a full persuasive mini-post in the same frame (e.g. post 58923: 66 replies, all hospital or beds angles, ids 3089–5649). That lifts `global_hot_score`, Trending puts the post in front of citizens, and citizens then add 10–37 likes and 300–480 views.
3. **Likes are a separate budget** (30/min team-wide, not the 3/min write budget). The leaders spend it on their own posts. We spend almost none of ours.
4. **Content shape:** a first-person conversion story ("I was leaning no, then I remembered…"), a vivid local detail (a bus route, a ferry, a named relative), one concrete fact, and a **closing question** that invites replies, plus one or two hashtags. Emotional, specific, and closed with an ask.
5. **The Yes side owns Trending:** 25 of 35 posts, 348 citizen likes and 6,571 views, against No's 5 posts, 42 citizen likes and 740 views. The No posts that do trend (ruth_retired_teach, ben_busdriver, malia_aged_care, amara_pharmacy) use the same shape with *loss* stories: library shut in 2020, teenagers needing a certificate, a worker asking if he needs a card for his shift.

Compared with 2025: the 2025 winners (CtN_QUT; QUT leads again as Vertex_CTN) found undecided voters with sentiment analysis and targeted them ([literature-notes §G](literature-notes.md)). That is roughly what swan_bot does. In 2026 the board is won on **reach first**: get a post into Trending through own-team amplification, then let citizens see it. Targeting without reach gives 1.3 views.

## What is wrong with us, by layer

| Layer | Problem | Evidence | Fix (todo) |
|---|---|---|---|
| **Reach** | Replies in threads nobody reads; no amplification | 1.3 views/write | [04](../../todo/04-reach-amplification.md) |
| **Throughput** | 11% of write budget used; likes, follows and views almost unused | 20 writes/h; hard cap 2/min in code | [03](../../todo/03-throughput-single-writer.md) |
| **LLM supply** | Free-tier Gemini quotas park the bot | `llm.py` parks models for hours on a daily 429 | [03](../../todo/03-throughput-single-writer.md) |
| **Targets** | Reply targeting starves: citizens rarely post | 0 citizen news-thread replies/hour in recent refreshes; 0/300 Latest posts by citizens | [04](../../todo/04-reach-amplification.md) |
| **Content** | Calm, consoling, process-heavy ("blank cheque", "list nobody's seen") | Rejects dominated by near-duplicate/same-opening; trending No posts are emotive stories | [05](../../todo/05-content-v2.md), [06](../../todo/06-npc-simulator.md) |
| **Blue track** | Not used at all, while the organisers just made it cheaper (cap 25 pending, 3 h base timer) | 0 reports filed | [07](../../todo/07-blue-desk.md) |
| **Infra** | Laptop + tmux; no auto-deploy; no shared picture | WSL sleeps; teammates can't see state | [01](../../todo/01-ec2-deploy.md), [02](../../todo/02-auto-deploy.md), [09](../../todo/09-dashboard-cop.md) |
| **Data** | No snapshots of the platform; no team clusters; per-post metrics only on demand | `swan_measure.py` is manual; Mongo holds only our own log | [08](../../todo/08-intel-collector.md) |

## Rules check (needs a ruling before we copy it)

Own-team likes and replies on our own posts is what the leaders do. In-game rule **LS.5.3** names "coordinated inauthentic behaviour" and "reaction farming", and our open question #4 ([open questions](../05-reference/discrepancies-and-open-questions.md)) is still unanswered. The organisers' 20 Oct announcement treats this as the Red game and Blue reporting as the counter ("every team only gets a finite number of bots"). That suggests it is an in-game risk (reports, hides, suspensions), not a competition-rule breach. **Still ask in `#questions` first** (CLAUDE.md rule 7; draft in [todo/10](../../todo/10-organiser-questions.md)). Build it behind a flag that is off by default.

## Blue track estimate (after the 20 Oct rule change)

- Pending cap is 25; with one reporting team a ruling now comes about **3 h** after the first report. Full use is about 25 reports per 3 h, roughly 200 a day.
- About 1 in 4 rulings is wrong. A "genuine" ruling locks *new* reports for 6 h, but pending reports still resolve. So a realistic **60–120 paid reports a day × 25 ≈ 1,500–3,000 Blue points a day**, before the per-team diminishing rate (5 full, 5 half, then 10%) is applied across many teams.
- That is more than our whole Red score so far. It also hides the ring posts that push the Yes side up Trending: 3 hides suspend an account, and a ring account with ≥100 actions and a hidden post can be suspended by an account report (15 each).
