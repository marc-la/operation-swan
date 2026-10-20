# 08: Intel collector: snapshots of Legit Social in Mongo

**Owner:** data lead · **Depends on:** nothing · **Feeds:** 04 (measurement), 05 (shapes), 06 (citizen profiles), 07 (clusters), 09 (dashboard)

## Why
We learned today's main facts from a one-off scan ([diagnosis](../docs/06-strategy/diagnosis-2026-10-20.md)). We need that picture continuously: what's trending and why, who's in which ring, how our posts do, and what citizens engage with.

## Fix first: Mongo credentials
`scripts/swan_sync_mongo.py` uses **the team code as the Mongo password**. The team code is our registration key and LLM key (CLAUDE.md rule 1), so it must not be reused for a third-party service. In Atlas, rotate the Mongo user to a fresh random password, put `MONGO_URI=` in `.env` (and `.env.example` without the value), and read that instead.

## Collector design (one long-running process, or a systemd timer every 5 min on EC2)
Budgets are team-wide and shared with the writer: **feeds 10/min** (the writer uses ~2 per 4 min), other reads 300/min each. Spend at most **4 feed reads per 5 min**.

| Collection | Every | What |
|---|---|---|
| `trending_snap` | 5 min | Trending top 50: `post_id`, rank, hot score, counters, author id (one doc per snapshot; posts in a sub-array) |
| `posts` | upsert | Each post seen: body, author, created_at, reply_to, embed, tags, latest counters, side guess (Yes/No/?), `shape` guess |
| `post_engagement` | 15 min for Trending + our posts | likers and repliers split into citizen/team/official, with ids |
| `accounts` | upsert | `get_account` cache: created_at, verified, private, `kind` (citizen/team/official), `cluster_id` |
| `clusters` | hourly | Team-account clusters from co-likes and co-replies (Jaccard + connected components); size, side guess, sample usernames |
| `our_posts` | 15 min | Every post we made: counters, citizen likes and replies, reached Trending? best rank, hidden? (from `get_post`); joined to persona, mode, frame, shape, git_sha from our log. Replaces the manual `swan_measure.py` |
| `citizen_activity` | 15 min | Citizen posts, likes and replies per hour (when are citizens awake? post then) |
| `portal_score` | manual or hourly | Team score as typed in by a human (we don't automate the portal: open question in `TODO.md`) |
| `tags` | hourly | `popular_tags()` |

Keep `swan_sync_mongo.py`'s existing collections. Make the bot write its actions straight to Mongo too (keeping the jsonl as the source of truth for attribution).

## Analyses to ship as small scripts (they also feed 09)
- Leaders' formula: for Trending posts, the hot score vs team-likes, team-replies and age. How many team likes does a post need to enter the top 35?
- Citizen-like rate by side, shape and hour.
- Our posts by mode/shape/persona: views, citizen likes, Trending entries.
- Cluster table: biggest rings, their side, their post rate. That's the Blue target list (07) and the competitive intel.

## Done when
The collector runs on EC2 for 24 h within the read budgets (no 429s attributable to it), and the analyses above print from Mongo in under a minute.
