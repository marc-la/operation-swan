# 22: Reader/writer split: the same bot, without the waiting (a behaviour-preserving refactor)

**Owner:** Marc + a fresh Claude session · **Depends on:** [todo/20](20-replies-that-convert.md) and [todo/21](21-reach-every-citizen.md) merged and stable for ≥ 6 h (G12's funnel log running) · **When:** 23 Oct at the earliest, never on a ×4 day

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

## Assurance that nothing else changes
1. **Invariants, each with a test in `tests/test_bot_split.py`:**
   - **one writer:** only the writer thread calls post, reply, repost or like;
   - **pacing:** the gap between writes is never below today's (`per_min` clamp plus jitter), and the bot backs off on 429;
   - **voice gap:** a voice never writes inside `ACCOUNT_MIN_GAP_S`;
   - **no double replies:** a post in `replied_posts` is never answered again, and the per-session cap holds (todo/21);
   - **state safety:** `swan_state.json`, `swan_accounts.json` and `llm_spend.json` are written by one owner under a lock, atomically (tmp file + `os.replace`). No lost updates when the reader and writer both change state;
   - **the order is unchanged:** for the same queue contents, `pick_job` returns the same job as before.
2. **Replay equivalence:** feed a recorded hour of reads (fixtures from `logs/feed_reads.jsonl` and saved Latest pages) through the old and the new loop in dry-run with a fixed random seed and a fake LLM. Each write decision (target, voice, mode, frame) must be the same; only timestamps may differ. Write down any difference and justify it.
3. **Dry run on the real platform** (`--hours 0.2`, no writes): compare the job mix and target picks with the old loop, run side by side.
4. **Shadow first:** deploy with `config.SPLIT_LOOP = False` (old loop) and switch the flag on in citizen hours with someone watching. Watch the G12 funnel, the write rate, 429s and hidden-post alerts for 1 h. **Rollback:** set the flag back and restart (~1 min).
5. **Before and after** over 6 h each, written into this file with the date: median citizen-post → reply time, reply-back latency, writes/h, 429s per hour, `lost(*)` counts. Expected: reply-back latency drops from ≤ 5 min to ≤ 1 min, and the ceiling rises from ~1.4 to ~2.5 writes/min, with **no change in what gets sent**.

## Out of scope
New targeting or content rules (todo/20 and todo/21); more processes (one writer, always: [research E](../docs/06-strategy/research-2026-10-21/E-throughput.md#b-marcs-three-questions)); any change to rate-limit handling except keeping it correct across threads.

## Guardrails
Writes stay off in tests and dry runs. Ship via `main` only with all tests green and the flag off. Never switch the flag on during the ×4 days unless it has run cleanly for 48 h before them.

## Done when
The invariant tests and the replay test pass. The split has run ≥ 24 h with the flag on and no invariant breaks. The before/after numbers are written here. Then delete the old loop.
