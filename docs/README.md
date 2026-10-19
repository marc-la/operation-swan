# CTN 2026 Knowledge Base

Facts about **Capture the Narrative 2026** that matter for building and running our bots, consolidated from capturethenarrative.com, the launch webinar and Discord announcements. Captured **2026-10-19**, the day the competition opened (rules v1.0.0). Anything that doesn't affect bot work (registration steps, privacy policy, research information sheet, the real-world referral award, 2025 prizegiving details) is deliberately left out.

**New to the team? Read in this order:** [00-quick-reference](00-quick-reference.md) → [team-conduct-checklist](02-rules/team-conduct-checklist.md) → [api-reference](04-technical/api-reference.md) → [scoring-cheatsheet](03-scoring/scoring-cheatsheet.md).

## Index

| Folder / file | What's in it |
|---|---|
| [00-quick-reference.md](00-quick-reference.md) | One-page cheat sheet: dates, limits, points, hard rules |
| **01-competition/** | |
| &nbsp;&nbsp;[overview.md](01-competition/overview.md) | What CTN is, how we score, the game world, NPC facts |
| &nbsp;&nbsp;[setting.md](01-competition/setting.md) | Full Kingstonia / Dolphin Flu / referendum "world bible" (use for prompts) |
| &nbsp;&nbsp;[schedule.md](01-competition/schedule.md) | Day-by-day calendar, polls, multiplier switch dates |
| **02-rules/** | |
| &nbsp;&nbsp;[team-conduct-checklist.md](02-rules/team-conduct-checklist.md) | ✅/⛔ digest for every team member — **share this** |
| &nbsp;&nbsp;[competition-rules.md](02-rules/competition-rules.md) | Official rules v1.0.0 with notes (non-bot sections condensed) |
| &nbsp;&nbsp;[legit-social-platform-rules.md](02-rules/legit-social-platform-rules.md) | In-game ToS / community guidelines |
| **03-scoring/** | |
| &nbsp;&nbsp;[scoring-guide.md](03-scoring/scoring-guide.md) | Official scoring guide, complete, with worked examples |
| &nbsp;&nbsp;[scoring-cheatsheet.md](03-scoring/scoring-cheatsheet.md) | Condensed tables + our analysis of what it implies |
| **04-technical/** | |
| &nbsp;&nbsp;[api-reference.md](04-technical/api-reference.md) | `capturethenarrative` 0.5.x: Legit Social, news sites, LLM, errors, rate limits, organisers' first-days advice |
| &nbsp;&nbsp;[environment.md](04-technical/environment.md) | How this repo/venv is set up; secrets handling |
| **05-reference/** | |
| &nbsp;&nbsp;[links-and-contacts.md](05-reference/links-and-contacts.md) | URLs and who to ask on Discord |
| &nbsp;&nbsp;[launch-webinar-2026-10-19.md](05-reference/launch-webinar-2026-10-19.md) | Organiser hints from the launch webinar: tactics, prompting pattern, example bots |
| &nbsp;&nbsp;[discrepancies-and-open-questions.md](05-reference/discrepancies-and-open-questions.md) | Conflicts between sources, questions for organisers, **answers log** |
| **06-strategy/** *(ours, 2026-10-19)* | |
| &nbsp;&nbsp;[README.md](06-strategy/README.md) | Strategy in one page + live platform snapshot |
| &nbsp;&nbsp;[literature-notes.md](06-strategy/literature-notes.md) | Research digest: referendums, mandates, persuasion, virality, bots, LLM agents, CTN 2025 lessons |
| &nbsp;&nbsp;[frames-and-messengers.md](06-strategy/frames-and-messengers.md) | Vote No frame library, segments, personas, Yes counters, what to avoid |
| &nbsp;&nbsp;[scoring-roi.md](06-strategy/scoring-roi.md) | Where the points are, milestones, budget maths, legitimate edges, red lines |
| &nbsp;&nbsp;[system-architecture.md](06-strategy/system-architecture.md) | Data-flow diagrams, components, build order, team roles, COP |
| &nbsp;&nbsp;[greedy-playbook.md](06-strategy/greedy-playbook.md) | Action value tiers, explicit vs implicit chains, greedy loop, pitfalls |
| &nbsp;&nbsp;[platform-mechanics.md](06-strategy/platform-mechanics.md) | Platform components → score, live observations, account roles |

## Provenance & accuracy

- Rules, scoring and setting text is reproduced faithfully (layout cleaned). Lines marked *Note*, **(derived)** or "analysis", and everything in `06-strategy/` and `discrepancies-and-open-questions.md`, are **ours**, not the organisers'.
- **Organisers may change rules, scoring or rate limits during the competition.** Re-check the live pages and Discord announcements. When something changes, update the relevant file and add the date.
- Not captured: the community portal behind login (team page, leaderboard, the Vote No briefing) and Discord channels other than the announcements.

## Maintaining this

- **Only facts that help build or run the bots.** One topic per file; link, don't duplicate. Put new organiser rulings in the **Answers** table of the discrepancies file.
- Date-stamp changes ("updated 2026-10-2x: organisers raised the post limit to …").
- Never put the team code, passwords or tokens in docs.
