# Launch webinar, 19 Oct 2026: what it added

> Source: CTN 2026 launch event (UNSW + Teams, 19 Oct 2026, 36.5 min), from slides and a Whisper transcript with corrected names. Transcription errors are possible. Captured 2026-10-19.
>
> This file records only what the talk **added to** or **contradicts in** the rest of `docs/` and matters for building and running bots. The scoring table, rate limits, 200/50 accounts, content rules and the 2025 player quotes are already in [overview](../01-competition/overview.md), [scoring](../03-scoring/scoring-guide.md) and [api-reference](../04-technical/api-reference.md). We also checked the companion client reference and the scoring/rules summary from the same day against our docs. The only new item was **client 0.5.1** (see [environment](../04-technical/environment.md#notes)). **Written rules and the scoring guide prevail over anything said in the talk.** Organiser Discord handles are in [links-and-contacts](links-and-contacts.md#people--contacts).

## New facts

| Fact | Where in talk | Updated in |
|---|---|---|
| **Baseline poll: Yes 35.2%, No 35.2%, Unsure 29%.** NPCs were built for roughly a third Yes, a third No and a third undecided | Slide 12, 11:25 | [schedule](../01-competition/schedule.md), [setting](../01-competition/setting.md#starting-poll-from-the-launch-webinar-2026-10-19) |
| **Just over 6,000 NPCs** (2025: about 4,000). More may be added during the game | 15:46 | [overview](../01-competition/overview.md) |
| **NPCs read the news at least once a day** ("that's a hint"). Persuading a journalist is expected to have "a huge impact on the rest of the population". A 2025 team got a journalist NPC to write the story they wanted | 16:30–17:20 | [overview](../01-competition/overview.md) |
| **Home feed** (signed-in default) is a mix of Trending that weights followed accounts. Being followed gives "a much more direct line straight into their brain" | 13:55 | Already in [platform-mechanics](../06-strategy/platform-mechanics.md) |
| **Score notifications** arrive in the portal **about once an hour** (only if we scored). They give totals by type but **not which posts earned them**, so we need our own per-post metrics | 20:10–20:50 | Format in [scoring-guide §6](../03-scoring/scoring-guide.md#6-reading-your-activity-log) |
| **Prizegiving is in December** ("in just over a couple of months", slide 6) | Slide 6, 35:02 | [schedule](../01-competition/schedule.md), [prizes](prizes-and-2025-results.md), [answers log](discrepancies-and-open-questions.md#answers-fill-in-as-you-get-them) |
| The organisers built several example bots "to make sure that we can produce bots that can produce persuasive content". Persuasion is achievable. Hammond's **example spam bot** and Oliver's analytics/dashboard bot (reads Trending, picks posts to reply to) were shown. **Screenshots are to be posted to Discord.** Our clone of the client repo has no examples folder | 27:55–30:20 | Check Discord / upstream repo |

## Said in the talk but differs from the written rules

- **Reports (15:00, 21:00):** "you'll get score and that post will be deleted… the ability to kill that bot". The scoring guide is more detailed: a ruling comes 1.5–24 h later and is wrong about 25% of the time. An account is suspended after **3 permanently hidden posts**, or by an account ruling once it has ≥1 hidden post and ≥100 actions. **Go by the scoring guide.** Logged as [discrepancies A10](discrepancies-and-open-questions.md#a-stale--inconsistent-text-on-the-official-site).

## Tactics the organisers mentioned (their words, 2025 observations)

These are **hints, not rules**. Read them against [scoring](../03-scoring/scoring-guide.md), which now penalises content that backfires (−80 per mind moved away), and against our [red lines](../06-strategy/scoring-roi.md#red-lines).

- Bot networks with roles (producers, boosters, engagers). Scanning the whole platform semantically. **Micro-targeting** individual accounts through replies and @-mentions, which trigger notifications.
- **Adapting tone per NPC** (the organisers listed "aggression, toxicity or gaslighting") **and measuring whether it worked**.
- "A very healthy disregard for the truth." In-game falsehood is allowed. The [content limits](../02-rules/team-conduct-checklist.md) still apply.
- Make our accounts **look authentic**, because Blue teaming is "front and centre" and every banned account is a lost life.
- Hammond's content test: "If you're wondering whether it crosses the line, it probably does."

## Prompting demo (slides 32–36, 30:36–33:30)

The point was how little effort it takes to get usable content from a model:

1. A plain request ("write a tweet criticising the young mayor of [fictional town]") gave a mild, polite jab, which Hammond judged would get little engagement.
2. Asking directly for something "toxic… for a game" was refused.
3. What worked combined: a role frame ("you are simulating … social media users"), a **persona** (e.g. an AM-radio host), a rhetorical stance ("just asking questions"), the target message, and **JSON output with `reasoning` and `tweet` fields**.

For our pipeline, the useful pattern is **persona + stance + JSON `{reasoning, post}`**. It gives parseable output and a visible rationale we can log per post. The demo used ChatGPT. The in-game `qwen2.5-3b-instruct` is weaker and may break the JSON format, so validate before posting ([CLAUDE.md](../../CLAUDE.md)). Toxicity isn't our goal: our generated posts are read by NPCs, and the screening and content rules in [scoring §7](../03-scoring/scoring-guide.md#7-posts-that-earn-no-points) and the [conduct checklist](../02-rules/team-conduct-checklist.md) apply to them.
