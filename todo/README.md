# todo/: handoffs for cold sessions (written 2026-10-20)

Each file is one self-contained work item. Open a fresh Claude Code session and say:

> Read CLAUDE.md, then `todo/NN-name.md`, and do it.

The *why* behind all of them: [diagnosis-2026-10-20](../docs/06-strategy/diagnosis-2026-10-20.md). Our posts get **1.3 views each** against 300–480 for the leaders, we use 11% of our write budget, and we file 0 reports.

## Order and owners

Owners are suggestions using the roles in [system-architecture §5](../docs/06-strategy/system-architecture.md#5-how-4-people-work-without-stepping-on-each-other). Swap names in as people pick items up.

| # | Item | Owner (role) | When | Needs |
|---|---|---|---|---|
| ~~19~~ | ✓ **Shipped 2026-10-21 (d99bd34):** citizen writes first; Latest every 2 min, paged; "Yes, with conditions" kept; reply-backs and second voices on | Marc + Claude | done | — |
| [23](23-widen-the-net.md) | Widen the net: uncontacted-citizen sweep, older posts, off-topic (no forced pivot), engaged quiet citizens, turnout for No, journalists. Each a capped, measured arm | Marc + Claude | **22 Oct** | 21 (shipped), 20 (style hook) |
| [22](22-reader-writer-split.md) | Reader/writer split: same decisions, less waiting (reader thread, draft-ahead, one writer). Light checks: nothing switched off (feature checklist test), core rules tested, flag for rollback | Marc + Claude | right after 20 and 21 | 20, 21 finished |
| ~~21~~ | ✓ **Shipped 2026-10-21 (8446cbf, a035e4f, c35ac3c):** reach every citizen. One Latest reader with a snapshot, no unread pages, a queue that survives restarts, and the citizen funnel (answered / skipped / lost per item); hard skips only, the stance sets priority; per-post and per-session limits; firm-Yes arm; new-citizen alert (a person confirms). 21 | Marc + Claude | done | — |
| [20](20-replies-that-convert.md) | Replies that convert: changes of mind toward No (0 so far), reply style A/B, weak frames out, Kimi length rejects, followup.py bug | Marc + Claude | **22 Oct, concurrently with 21** | 19 (shipped) |
| [07](07-blue-reporting.md) | Blue reporting: **built 21 Oct** (`swan-blue` on EC2, approve mode first). Left: approve the first batch, check the first rulings and locks, ask B.10/B.11 | Blue lead | **21–22 Oct** | — |
| ~~16~~ | ✓ **Done 2026-10-21:** fact desk. Facts in `content/facts.toml`, checked against the papers hourly (contradictions pause, the rest proposed). Workflow: [system-architecture §9](../docs/06-strategy/system-architecture.md#9-fact-desk-who-reviews-when-how-2026-10-21) | Marc + Claude | done | — |
| [09](09-dashboard-cop.md) | Dashboard (nginx + static Jinja page on EC2): built 21 Oct, box setup left | Marc | 22 Oct | — |

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
