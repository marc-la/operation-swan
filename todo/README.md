# todo/: handoffs for cold sessions (written 2026-10-20)

Each file is one self-contained work item. Open a fresh Claude Code session and say:

> Read CLAUDE.md, then `todo/NN-name.md`, and do it.

The *why* behind all of them: [diagnosis-2026-10-20](../docs/06-strategy/diagnosis-2026-10-20.md). Our posts get **1.3 views each** against 300–480 for the leaders, we use 11% of our write budget, and we file 0 reports.

## Order and owners

Owners are suggestions using the roles in [system-architecture §5](../docs/06-strategy/system-architecture.md#5-how-4-people-work-without-stepping-on-each-other). Swap names in as people pick items up.

| # | Item | Owner (role) | When | Needs |
|---|---|---|---|---|
| [07](07-blue-desk.md) | Blue desk: find ring bots, report them | Blue lead | **today → 21 Oct** | 08 helps but not needed for v0 |
| [12](12-batched-drafting.md) | Batched drafting: fix `batch.py`, A/B vs single (≥95% quality), wire into the draft pool | Marc (ops) | 21 Oct | — |
| [08](08-intel-collector.md) | Collector into Mongo: snapshots, team clusters, our per-post metrics | Data lead | 21 Oct | — |
| [09](09-dashboard-cop.md) | Dashboard (nginx + static Jinja page on EC2): primary, built 21 Oct, box setup left (Marc) | Marc | 22 Oct | 01, 08 |
| [06](06-npc-simulator.md) | NPC simulator as a fitness landscape for drafts | Narrative lead | 22–23 Oct | 05, 10 |
| [13](13-overnight-experiments.md) | Overnight experiments: random arms per draft, citizen follow-up reads, switchbacks, morning report | Marc + fresh session | 21 Oct, then nightly | 05 live |
| [14](14-prompt-steering.md) | Prompt steering: built and live; left: same-seed flash-lite screen (after quota reset) + teammate read of 10 drafts | Marc + teammate | 21 Oct after 15:00 | 13 live |

**Critical path to catch up:** amplification is live (2026-10-20, [amplification](../docs/06-strategy/amplification.md)); next are 07 (Blue: the fastest points, and `scripts/ring_audit.py` already finds the rings) and 05 (content that ranks).

## Ops leftovers (small, Marc)
Done 2026-10-20 and deleted from this folder: bot on EC2 under systemd, plus auto-deploy from `main` with alerts and CI ([hosting](../docs/04-technical/hosting.md)); throughput (old 03: LLM chain, 2.5 writes/min, 4-min voice gap); amplification (old 04, now [amplification](../docs/06-strategy/amplification.md)). Still open:
- [x] 2026-10-20: Gemini project upgraded to **paid Tier 1** (flash-lite 150K requests/day). Chain re-ranked in `deploy/llm_chain.txt`; qwen 3B fallback removed. Watch the monthly spend cap: when the billing account hits it, Gemini pauses until the 1st and the bot falls back to Groq.
- [ ] AWS: Elastic IP (then update `~/.ssh/config` + hosting.md), termination protection, SSH from team IPs only, budget alert.
- [ ] Teammates' public SSH keys → `~ec2-user/.ssh/authorized_keys` (don't share the PEM).
- [ ] GitHub branch protection on `main`: require the `checks` job and PRs (today a direct push goes live in 2 min).
- [ ] `tests/` for `quality.check` and `targeting.classify` (CI and the deploy checks run them when present). Log the git sha in each action record. Graceful stop via a signal flag instead of KeyboardInterrupt.

## Rules for every item
- CLAUDE.md guardrails apply. Anything that writes to Legit Social is **dry-run by default** and needs an explicit `--live`.
- **Only one writer process for the team, ever: the EC2 `swan-bot` service.** Ship changes by merging to `main` (live in ~2 min). Never run `--live` on a laptop.
- Secrets stay in `.env` / `secrets/` on the machine that runs the bot. Never in git, never in Mongo, never in the dashboard.
- When an item is done: tick it in the table above with the date, and move anything learned into `docs/` (link, don't duplicate).
