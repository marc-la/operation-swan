# todo/: handoffs for cold sessions (written 2026-10-20)

Each file is one self-contained work item. Open a fresh Claude Code session and say:

> Read CLAUDE.md, then `todo/NN-name.md`, and do it.

The *why* behind all of them: [diagnosis-2026-10-20](../docs/06-strategy/diagnosis-2026-10-20.md). Our posts get **1.3 views each** against 300–480 for the leaders, we use 11% of our write budget, and we file 0 reports.

## Order and owners

Owners are suggestions using the roles in [system-architecture §5](../docs/06-strategy/system-architecture.md#5-how-4-people-work-without-stepping-on-each-other). Swap names in as people pick items up.

| # | Item | Owner (role) | When | Needs |
|---|---|---|---|---|
| ~~19~~ | ✓ **Shipped 2026-10-21 (d99bd34):** citizen writes first; Latest every 2 min, paged; "Yes, with conditions" kept; reply-backs and second voices on | Marc + Claude | done | — |
| [33](33-engagement-per-write.md) | **Engagement per write (top priority, replaces 25):** optimise the points the portal pays every hour (likes 5, replies 15, follows 20; uncapped, ×2 from 26 Oct). Follows and likes randomised per citizen (follow-back 9/214 today), engagers-first targeting in 2 h blocks; persuasion is a guardrail | open | **23 Oct** | — |
| [32](32-agree-close-reply-backs.md) | **agree_close (new arm):** when a citizen answers us in agreement, a short casual reply-back naming one gap and ending on our own vote, like the only thread that converted on 22 Oct (citizen 528, portal towards 04:47 UTC). Reply-backs only, no double-stacking | open | **23 Oct** | — |
| ~~25~~ | ✓ **Closed 2026-10-23:** conversion. No lever, wording, technique or drafting model beat what we send, live or in five lab rounds; the NPC lab is retired. Results: [npc-lab](../docs/06-strategy/npc-lab.md). Followed by 33 | — | done | — |
| ~~31~~ | ✓ **Done 2026-10-22 (c3662cb, f7296e9, 6995ad5):** a human day per voice, built with every switch OFF by team decision (87c6e8e, throughput over stealth); `.env` brings each rule back. Second voices back on. What and how: [stealth](../docs/06-strategy/stealth.md). Content asks (F14 skeleton, fact rotation, per-voice style) are with todo/25 | — | done | — |
| ~~30~~ | ✓ **Superseded 2026-10-22:** 10 boosters converted into voices instead of registering (f7296e9). Registering more voices is Marc's call (139 accounts left; keep a reserve for ×2 on 26 Oct, ×4 on 1 Nov) | — | done | — |
| ~~29~~ | ✓ **Shipped 2026-10-22 (951afc9 and before):** dashboard decluttered (throughput row, four score numbers, Blue timeline that collapses in place, portal account counts, coloured alerts); facts fully autonomous (fab93e0, 8b6eda6): [system-architecture §9](../docs/06-strategy/system-architecture.md#9-fact-desk-who-reviews-when-how-2026-10-21) | — | done | — |
| ~~28~~ | ✓ **Shipped 2026-10-22 (13fda57 … 16efdbe, 9ea5c3c):** Blue cap 30 (account reports count, observed), risk budget 1.0 genuine/day (.env), account reports first, never our own accounts, Yes-side first, account-lead detectors: [blue-reporting §8](../docs/06-strategy/blue-reporting.md#8-blue-without-locks-todo28-2026-10-22) | — | done | — |
| ~~27~~ | ✓ **Shipped 2026-10-22 (5c07934, 240c349, 01e1d19):** no vote statements, phrase budgets, strict near-duplicates: [stealth](../docs/06-strategy/stealth.md) | — | done | — |
| ~~24~~ | ✓ **Shipped 2026-10-22 (7d9150a, 9bb94cc, 171b7c7, a98ae90, 33dba69, b92e50f):** ~2.9 writes/min from the headers, GLM-5 out of replies, no drafts for capped citizens, near-duplicate split, Latest stretches kept, news threads every 30 min. What to watch: [runbook](../docs/04-technical/swan-bot-runbook.md) | — | done | — |
| ~~26~~ | ✓ **Shipped 2026-10-22 (c2ee192, 2973899):** Blue: P(genuine) per report and a threshold, exact lock end from the server, new clusters first, wider discovery from the snapshot, swarm accounts excluded. Before/after: [blue-reporting §7](../docs/06-strategy/blue-reporting.md) | — | done | — |
| ~~23~~ | ✓ **Read out 2026-10-22 (24 h):** sweep killed (3 of our hidden posts), off-topic cap 3 → 6/h, turnout kept (no cap), older and engaged held (thin). Numbers: [direction §24 h read-out](../docs/06-strategy/direction-2026-10-21.md#24-h-read-out-2026-10-22-1504-utc-todo20-todo23-todo25) | — | done | — |
| ~~22~~ | ✓ **Shipped 2026-10-21 (c825d9f), live 15:45 UTC:** reader/writer split (reader, drafter, one writer), `SPLIT_LOOP` for rollback. How it runs: [runbook](../docs/04-technical/swan-bot-runbook.md#how-the-bot-runs-reader-drafter-writer-2026-10-22-todo22). Left there: drop the serial loop after a clean day | Marc + Claude | done | — |
| ~~21~~ | ✓ **Shipped 2026-10-21 (8446cbf, a035e4f, c35ac3c):** reach every citizen. One Latest reader with a snapshot, no unread pages, a queue that survives restarts, and the citizen funnel (answered / skipped / lost per item); hard skips only, the stance sets priority; per-post and per-session limits; firm-Yes arm; new-citizen alert (a person confirms). 21 | Marc + Claude | done | — |
| ~~20~~ | ✓ **Read out 2026-10-22 (24 h):** reply style "current" kept (mirror_concede out), own like on every reply; second voices are a team call (back on since 87c6e8e). Numbers: [direction §24 h read-out](../docs/06-strategy/direction-2026-10-21.md#24-h-read-out-2026-10-22-1504-utc-todo20-todo23-todo25) | — | done | — |
| ~~16~~ | ✓ **Done 2026-10-21:** fact desk. Facts in `content/facts.toml`, checked against the papers hourly (contradictions pause, the rest proposed). Workflow: [system-architecture §9](../docs/06-strategy/system-architecture.md#9-fact-desk-who-reviews-when-how-2026-10-21) | Marc + Claude | done | — |

**Critical path (2026-10-22):** changes of mind at volume ([direction-2026-10-21](../docs/06-strategy/direction-2026-10-21.md#the-plan-changes-of-mind-at-volume-22-oct--2-nov)). **21** = reach every citizen (volume), **20** = replies that convert (conversion and the light read), run concurrently in two sessions. Blue runs on its own (`swan-blue`). Amplification is **paused** (`AMPLIFY_OFF`, 2026-10-21 14:12 UTC), and Trending pushes are dropped (old 18 deleted 2026-10-22).

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
- **Writers on EC2 only, one per budget:** `swan-bot` owns posts, replies, reposts, likes and follows; `swan-blue` owns the report routes (their own 3/min budgets) and its one reporter account (decided 2026-10-21, so the two are decoupled). Ship changes by merging to `main` (live in ~2 min). Never run `--live` on a laptop.
- Secrets stay in `.env` / `secrets/` on the machine that runs the bot. Never in git, never in Mongo, never in the dashboard.
- When an item is done: tick it in the table above with the date, and move anything learned into `docs/` (link, don't duplicate).
