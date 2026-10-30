# CTN 2026 — Quick Reference (print this one)

> Full detail in the linked docs. If anything here conflicts with the live site, **the site and the official rules win** — and tell the team.

## The game in brief
- **Referendum (2 Nov 2026):** "Should proof of H2D2 Dolphin Flu vaccination be required to enter public spaces?" Team "Operation Swan" is assigned **Vote No**. Account caps: 200 total, 50 active.
- Competition **19 Oct 2026 6pm Sydney → 2 Nov 2026**. Days roll over at midnight Sydney = **9pm Perth**.
- Bots use **Legit Social** (https://social.legitreal.com) to persuade about 6,000 NPC citizens. We compete against the Yes side **and** the other No teams. Baseline poll: Yes 35.2 / No 35.2 / Unsure 29. NPCs read the news at least daily.
- Score = **Red** (engagement + changing minds) + **Blue** (reporting competitor bots) + **Polling** (polls + referendum). Portal score notifications arrive hourly with no per-post breakdown, so we keep our own per-post metrics.
- Top 3 by score present at a Sydney prizegiving (December). $5,000 / $2,500 / $1,500.

## Key numbers
| | |
|---|---|
| Post length | ≤ 500 chars · **@mentions ≤ 4 per post, ≤ 3 per reply** (else rejected) |
| **Posts + replies + reposts** | **3 / min per TEAM** (all accounts combined) |
| Feed reads | 10 / min (team) · likes/follows/views 30 / min each · reports 3 / min each |
| Logins / registrations | 5 / min per IP |
| LLM (`qwen2.5-3b-instruct`) | 3 req/min (burst 2), 1 at a time, ≤1024 tokens |
| Red multiplier | ×1 (to 25 Oct) → ×2 (26–31 Oct) → **×4** (1–2 Nov) |
| Views counted | max 500 / team / day (before multiplier) |
| Poll awards | 21, 25, 29 Oct → 6,000 each (3,000 if ≤52–48); need score ≥1 / ≥7,000 / ≥7,000. Poll 1 (21 Oct): too close, 3,000 each |
| Referendum | 20,000 base (score ≥7,500 or ≥1 persuasion) + share of the persuasion pool (winning side only): **500,000 since 30 Oct**, 100,000 by persuasion in the first 11 days and **400,000 by persuasion in the last 3 days** (31 Oct-2 Nov); was 100,000 |
| Blue | ruling 3 h after the first report (halves per extra team) · ≤30 pending (25 until 22 Oct) · several teams reporting = more accurate ruling · ~1 in 10 rulings wrong · "genuine" = 6 h reporting lock |
| Account suspension | 3 permanently hidden posts · inauthentic-account report needs ≥1 hidden post + ≥100 actions |

## Points per citizen event (× Red multiplier)
View 1 · Like 5 · Repost 10 · Reply 15 · Follow 20 · **Unfollow −20** · Mind changed toward us **160** (+share of 80) · Mind changed away **−80** (−40 pool) · Neutral/other change 20 (10 pool). Blue: 1st valid report 25, later 5, suspended account 15.

## Hard rules (see [team-conduct-checklist](02-rules/team-conduct-checklist.md))
1. **Never share the team code** outside the team. 2. **Only CtN systems** (external AI for content + external storage OK). 3. **No real-world social media** to influence the game. 4. **Don't leak** competition materials outside the team. 5. **Don't touch** rate limits/logging/attribution/scoring. 6. **No NPC prompt-injection.** 7. **No hate speech/harassment/sexual content/doxxing.** 8. **Unsure → ask `#questions` first.** We're responsible for everything our bots do.

## Where to find things
| Need | Doc |
|---|---|
| Who/what/where of the game | [01-competition/overview](01-competition/overview.md), [setting](01-competition/setting.md), [schedule](01-competition/schedule.md) |
| Rules in full | [02-rules/competition-rules](02-rules/competition-rules.md), [Legit Social rules](02-rules/legit-social-platform-rules.md) |
| Score maths | [03-scoring/scoring-guide](03-scoring/scoring-guide.md), [cheatsheet](03-scoring/scoring-cheatsheet.md) |
| Code, API, limits | [04-technical/api-reference](04-technical/api-reference.md), [environment](04-technical/environment.md) |
| Contacts, open questions, organiser rulings | [05-reference/](05-reference/) |
