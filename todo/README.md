# todo/: handoffs for cold sessions (written 2026-10-20)

Each file is one self-contained work item. Open a fresh Claude Code session and say:

> Read CLAUDE.md, then `todo/NN-name.md`, and do it.

The *why* behind all of them: [diagnosis-2026-10-20](../docs/06-strategy/diagnosis-2026-10-20.md). Our posts get **1.3 views each** against 300–480 for the leaders, we use 11% of our write budget, and we file 0 reports.

## Order and owners

Owners are suggestions using the roles in [system-architecture §5](../docs/06-strategy/system-architecture.md#5-how-4-people-work-without-stepping-on-each-other). Swap names in as people pick items up.

| # | Item | Owner (role) | When | Needs |
|---|---|---|---|---|
| [01](01-ec2-deploy.md) | ✅ 2026-10-20: bot on EC2 under systemd ([hosting](../docs/04-technical/hosting.md)); AWS-side leftovers listed | Marc (ops) | done | — |
| [02](02-auto-deploy.md) | ✅ 2026-10-20: push to `main` → live in ~2 min; branch protection + tests still open | Marc (ops) | done | — |
| [11](11-alert-channel.md) | Pick the alert channel (Discord webhook recommended) + dead-man switch | anyone | today | — |
| [10](10-organiser-questions.md) | Post our rule questions in Discord `#questions` | Blue lead | **today** | — |
| [07](07-blue-desk.md) | Blue desk: find ring bots, report them | Blue lead | **today → 21 Oct** | 08 helps but not needed for v0 |
| [03](03-throughput-single-writer.md) | One writer using all 3 writes/min; paid LLM key; spare like/follow/view budgets | Marc (ops) | 21 Oct | 01 |
| [04](04-reach-amplification.md) | Reach: own-team amplification into Trending, made to look organic (decided 2026-10-20) | Ops + narrative | **21 Oct** | 03 |
| [05](05-content-v2.md) | Content v2: emotive conversion stories, closing question, hashtags | Narrative lead | 21 Oct | — |
| [08](08-intel-collector.md) | Collector into Mongo: snapshots, team clusters, our per-post metrics | Data lead | 21 Oct | — |
| [09](09-dashboard-cop.md) | Dashboard (nginx + static Jinja page on EC2) | Data lead | 22 Oct | 01, 08 |
| [06](06-npc-simulator.md) | NPC simulator as a fitness landscape for drafts | Narrative lead | 22–23 Oct | 05, 10 |

**Critical path to catch up:** 03 (paid Gemini + full pace) → 04 (amplification), with 07 (Blue) running in parallel from today. Blue needs no new bot infrastructure and is the fastest points.

## Rules for every item
- CLAUDE.md guardrails apply. Anything that writes to Legit Social is **dry-run by default** and needs an explicit `--live`.
- **Only one writer process for the team, ever: the EC2 `swan-bot` service.** Ship changes by merging to `main` (live in ~2 min). Never run `--live` on a laptop.
- Secrets stay in `.env` / `secrets/` on the machine that runs the bot. Never in git, never in Mongo, never in the dashboard.
- When an item is done: tick it in the table above with the date, and move anything learned into `docs/` (link, don't duplicate).
