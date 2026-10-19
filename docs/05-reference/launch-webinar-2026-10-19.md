# Launch webinar, 19 Oct 2026: organiser hints

> Source: CTN 2026 launch event (36.5 min), from slides and a Whisper transcript with corrected names. Transcription errors are possible. The **facts** from the talk (NPC count, baseline poll, daily news reading, hourly score notifications, prizegiving month) are already in [overview](../01-competition/overview.md), [schedule](../01-competition/schedule.md) and the [quick reference](../00-quick-reference.md). This file keeps what the organisers **advised**. Written rules and the scoring guide prevail. Where the talk conflicted with them (reports "killing" bots), see [discrepancies A1](discrepancies-and-open-questions.md#a-conflicts-between-sources).

## Tactics the organisers mentioned (2025 observations)

These are **hints, not rules**. Read them against [scoring](../03-scoring/scoring-guide.md), which now penalises content that backfires (−80 per mind moved away), and against our [red lines](../06-strategy/scoring-roi.md#red-lines).

- **Persuade journalists.** NPCs read the news at least daily, and a 2025 team got a journalist NPC to write the story they wanted. The organisers invited teams to try again.
- **Get followed.** The Home feed weights followed accounts, which gives "a much more direct line straight into their brain".
- Bot networks with roles (producers, boosters, engagers). Scanning the whole platform semantically. **Micro-targeting** individual accounts through replies and @-mentions, which trigger notifications.
- **Adapting tone per NPC** (the organisers listed "aggression, toxicity or gaslighting") **and measuring whether it worked**. Score notifications don't attribute points to posts, so per-post metrics are on us.
- "A very healthy disregard for the truth." In-game falsehood is allowed. The [content limits](../02-rules/team-conduct-checklist.md) still apply.
- Make our accounts **look authentic**, because Blue teaming is "front and centre" and every banned account is a lost life.
- Hammond's content test: "If you're wondering whether it crosses the line, it probably does."
- The organisers built several example bots to confirm "bots can produce persuasive content". Hammond's example spam bot and Oliver's analytics/dashboard bot (reads Trending, picks posts to reply to) were shown. **Screenshots are promised on Discord.** Our clone of the client repo has no examples folder.

## Prompting demo (slides 32–36)

The point was how little effort it takes to get usable content from a model:

1. A plain request ("write a tweet criticising the young mayor of [fictional town]") gave a mild, polite jab, which Hammond judged would get little engagement.
2. Asking directly for something "toxic… for a game" was refused.
3. What worked combined: a role frame ("you are simulating … social media users"), a **persona** (e.g. an AM-radio host), a rhetorical stance ("just asking questions"), the target message, and **JSON output with `reasoning` and `tweet` fields**.

For our pipeline, the useful pattern is **persona + stance + JSON `{reasoning, post}`**. It gives parseable output and a visible rationale we can log per post. The demo used ChatGPT. The in-game `qwen2.5-3b-instruct` is weaker and may break the JSON format, so validate before posting. Toxicity isn't our goal: our generated posts are read by NPCs, and the screening and content rules in [scoring §7](../03-scoring/scoring-guide.md#7-posts-that-earn-no-points) and the [conduct checklist](../02-rules/team-conduct-checklist.md) apply to them.
