# 22: Reader/writer split: the same bot, without the waiting (a behaviour-preserving refactor)

**Owner:** Marc + a fresh Claude session · **Depends on:** [todo/20](20-replies-that-convert.md) and [todo/21](21-reach-every-citizen.md) finished · **When:** right after them

## Read first
`CLAUDE.md`, [direction-2026-10-21](../docs/06-strategy/direction-2026-10-21.md), [research E: throughput](../docs/06-strategy/research-2026-10-21/E-throughput.md) §a.3, `src/swan_bot/bot.py` (`main()` is one ~430-line loop with closures: `write_status`, `pause`, `save_state`, `desk_fill`), `targeting.py` (`Targeter.refresh`), `amplify.py` (`tick`), `llm.py`.

## Why
The bot runs everything in one serial loop: read targets (`targeter.refresh()`, 30–40 reads, blocking) → reply-back poll (every voice's notifications) → draft (6–17 s of LLM) → send → sleep for pacing (mean ~26 s) → only then draft the next one. A reply cycle is ~44 s (~1.4/min), and every slow read or draft holds up everything else. At tonight's supply that ceiling isn't binding. At peak and on the ×2/×4 days it will be. And a citizen who replies to us mid-session needs our answer within ~1–5 min.

## Goal: same decisions, less waiting
**Not a rewrite.** Same targets, same order of priority, same prompts, same quality gate, same pacing. Only *when* work happens changes:
- **Reader** (one thread):
  - `targeter.refresh()` plus the reply-back poll, every ~60 s;
  - writes the shared `data/latest_snapshot.json` (todo/21 G1);
  - pushes candidates and reply-back jobs into a thread-safe queue.
- **Drafter** (one thread): takes the next job by today's `pick_job` order and drafts it ahead (at most 1–2 drafts waiting, so drafts don't go stale). Rejected or failed drafts go back through todo/20's G8/G9 path.
- **Writer** (the main thread, still the **only** process that writes to Legit Social):
  - sends the next ready draft when `next_write` comes;
  - pacing from `X-RateLimit-Remaining` exactly as now;
  - keeps the 4-min voice gap and the send-time checks (`ledger.send_problem`, `gone()`).
- The amplifier's likes and views keep their own budget in `pause()` / `tick()`, unchanged (amplification is paused anyway).

## Assurance: nothing switched off by accident
Light-touch (Marc, 2026-10-22): the aim is no integration breakage, not proof of identical output. Low results show up in the data anyway.
1. **A feature checklist, in a test:** after the change, every job type still runs in a dry run, and every background duty still fires.
   - **Job types:** `reply`, `reply_back`, `second_voice`, `journalist`, `post`, `repost`.
   - **Background duties:** registration drip, `pulse.update`, fact desk, `amp.tick` (respects `AMPLIFY_OFF`), `write_status` / dashboard, `save_state`, the hidden-post limits, the todo/20 and todo/21 logging (`lost(*)`, `skipped(*)`, `read_*`).
   - Name each one in `tests/test_bot_split.py`, and run the dry run with `--samples` large enough to hit each.
2. **The core rules, a few small tests:**
   - only the writer posts;
   - pacing never faster than today and backs off on 429;
   - the 4-min voice gap holds;
   - no double replies;
   - state files written by one owner, atomically (tmp file + `os.replace`).
3. **A flag for a fast rollback:** `config.SPLIT_LOOP`. Ship with it on, and watch the first hour: write rate, 429s, the G12 funnel, alerts. Off and a restart (~1 min) if anything looks wrong.
4. **A quick before/after** (1–2 h each), noted here: reply-back latency, writes/h, 429s.

## Out of scope
New targeting or content rules (todo/20 and todo/21); more processes (one writer, always: [research E](../docs/06-strategy/research-2026-10-21/E-throughput.md#b-marcs-three-questions)); any change to rate-limit handling except keeping it correct across threads.

## Guardrails
Writes stay off in tests and dry runs. Ship via `main` with all tests green.

## Done when
The checklist test and the rule tests pass, the first live hour is clean, and the before/after numbers are noted here. Delete the old loop once it has run a day without issues.
