# todo/: handoffs for cold sessions (written 2026-10-20)

Each file is one self-contained work item. Open a fresh Claude Code session and say:

> Read CLAUDE.md, then `todo/NN-name.md`, and do it.

The *why* behind all of them: [diagnosis-2026-10-20](../docs/06-strategy/diagnosis-2026-10-20.md). Our posts get **1.3 views each** against 300–480 for the leaders, we use 11% of our write budget, and we file 0 reports.

## Order and owners

Owners are suggestions using the roles in [system-architecture §5](../docs/06-strategy/system-architecture.md#5-how-4-people-work-without-stepping-on-each-other). Swap names in as people pick items up.

| # | Item | Owner (role) | When | Needs |
|---|---|---|---|---|
| [07](07-blue-reporting.md) | Blue reporting: find ring bots, report them (0 reports so far) | Blue lead | **today, 21 Oct** | — |
| ~~16~~ | ✓ **Done 2026-10-21:** fact desk. Facts in `content/facts.toml`, checked against the papers hourly (contradictions pause, the rest proposed). Workflow: [system-architecture §9](../docs/06-strategy/system-architecture.md#9-fact-desk-who-reviews-when-how-2026-10-21) | Marc + Claude | done | — |
| [17](17-new-personas.md) | New personas: replace lost voices, keep reserves (voices now limit posting, not the models) | Narrative lead + fresh session | 22 Oct | — |
| [18](18-trending-entry.md) | Getting into Trending: re-fit the hot score (cutoff ~24 → ~37), find the dose or ride No posts already there | Marc + fresh session | 22 Oct | — |
| [09](09-dashboard-cop.md) | Dashboard (nginx + static Jinja page on EC2): built 21 Oct, box setup left | Marc | 22 Oct | — |

**Critical path to catch up (2026-10-21):** Blue (07) starts today. Amplification went harder on 21 Oct: one post an hour, every one heavy, 15–20 thread replies on top of 5–6 reposts, best models and best-measured voices ([amplification](../docs/06-strategy/amplification.md)). The trending pulse (old 15, built 21 Oct: [amplification](../docs/06-strategy/amplification.md#trending-pulse-2026-10-21)) keeps that content current. Its 24 h before/after check is open there. Dropped 21 Oct: the overnight experiments (old 13; too little data), the NPC simulator (old 06), the intel collector (old 08), second voices and reply-backs.

## Ops leftovers (small, Marc)
Done 2026-10-20 and deleted from this folder: bot on EC2 under systemd, plus auto-deploy from `main` with alerts and CI ([hosting](../docs/04-technical/hosting.md)); throughput (old 03: LLM chain, 2.5 writes/min, 4-min voice gap); amplification (old 04, now [amplification](../docs/06-strategy/amplification.md)). Still open:
- [ ] **LLM supply (do first):** the bot's Gemini key is on the *free* project (flash-lite 500/day; 3.6 and 3.8 Flash 20/day each). One heavy post an hour needs ~20 drafts an hour (the post plus 15–20 thread replies), about 480 a day before rejects and repairs. Move the key in EC2 `~/ctn/.env` to the paid Tier 1 project (3.8 Flash 10K/day), then check `data/llm_usage.json` the next day.
- [ ] ~~2026-10-20: Gemini project upgraded to paid Tier 1~~ **Wrong (corrected 2026-10-21):** the email was misread. The project is still on the **free** tier (flash-lite 500/day; 3.6 and 3.8 Flash 20/day each). Chain re-ranked in `deploy/llm_chain.txt`; qwen 3B fallback removed. Still to do: enable billing on the bot's project with a spend cap.
- [ ] AWS: ~~Elastic IP~~ (done 2026-10-21: `13.210.120.238`), termination protection, SSH from team IPs only, budget alert.
- [ ] Teammates' public SSH keys → `~ec2-user/.ssh/authorized_keys` (don't share the PEM).
- [ ] GitHub branch protection on `main`: require the `checks` job and PRs (today a direct push goes live in 2 min).
- [ ] `tests/` for `quality.check` and `targeting.classify` (CI and the deploy checks run them when present). Log the git sha in each action record. Graceful stop via a signal flag instead of KeyboardInterrupt.

## Rules for every item
- CLAUDE.md guardrails apply. Anything that writes to Legit Social is **dry-run by default** and needs an explicit `--live`.
- **Only one writer process for the team, ever: the EC2 `swan-bot` service.** Ship changes by merging to `main` (live in ~2 min). Never run `--live` on a laptop.
- Secrets stay in `.env` / `secrets/` on the machine that runs the bot. Never in git, never in Mongo, never in the dashboard.
- When an item is done: tick it in the table above with the date, and move anything learned into `docs/` (link, don't duplicate).
