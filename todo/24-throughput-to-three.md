# 24: Throughput to ~3/min and no wasted drafts

**Owner:** Marc + a fresh Claude session · **Depends on:** todo/22 (the split, live since 2026-10-21 15:45 UTC) · **When:** 22 Oct, before Sydney's afternoon peak · **Orchestrated by:** the session coordinating todo/24–26 (message it with each commit hash)

## Why (morning check, 2026-10-22 ~00:00 UTC)
- The split works: a steady **2.2–2.3 writes/min** from 16:00 to 23:00 UTC, with 0 rate-limit errors and 0 thread deaths.
- **But since Sydney's morning we're behind again:** the queue went 41 → 104 candidates, the oldest has waited **29 min**, and hour 23:00 saw 166 citizen items, answered 93, with 54 pending. The cap is `per_min` 2.5 (clamped in `bot.py`) plus jitter, so we never use the 3/min the rules allow.
- **Wasted work, overnight:**
  - 98 drafts thrown away at send (`session_cap_at_send`): the citizen hit the 2-voice cap while the draft waited;
  - **GLM-5 passed first time on 0 of 69 drafts** (not_specific 36, near_duplicate 28). Kimi passes 89% (n=857), flash-lite 86% (n=195);
  - `near_duplicate` is the top reject (Kimi 151);
  - 3 citizens were `lost: latest_band_dropped`.

## Do
1. **Pace to ~2.9/min from the headers.**
   - Raise the clamp in `bot.py` and `deploy/run.sh --per-min` so the writer aims at the team limit, pacing from `X-RateLimit-Remaining` (never hard-coded), with a margin of 1 write.
   - The swarm (`swan-swarm`, teammate's, every 5 min) reposts only while ≥ 2 team writes are left. Keep that rule working: leave it the headroom it checks for.
   - Back off on 429 as now. Target: 2.8–2.9 writes/min average and 0 rate-limited.
2. **Take GLM-5 out of reply drafting** (`config.AMP_MODELS` / `deploy/llm_chain.txt` for `STRONG_MODES`). Keep Kimi first and flash-lite next. Target: overall first-call ≥ 90%.
3. **`near_duplicate`:**
   - show the last ~10 openings to the prompt (today 3: `content.avoid_line`);
   - check that the near-duplicate threshold in `quality.py` compares replies to the **same thread or citizen** strictly, and replies to *other* citizens more loosely. Repeating ourselves across citizens is a bot tell for Blue reporters, so don't drop it entirely.
   - Measure the reject share before and after.
4. **No draft for a capped citizen:** the drafter skips candidates whose author is at the session cap, or will be by the time the draft is ready (check `contacted` at draft time, not only at send). Target: `session_cap_at_send` under 10 a night.
5. **`latest_band_dropped`:** find why 3 Latest bands were dropped and keep them. Coverage must stay 0 lost.
6. **Lighter refresh** (approved 22 Oct): read news threads every 30 min instead of every refresh (0 citizen replies under post-launch paper posts; keep the headline read for pulse).
7. **Test isolation:** `tests/test_llm_budget.py::test_priority_window_holds_other_writes` reads the repo's real `AMPLIFY_OFF` (the box has it). Use a tmp path or monkeypatch `config.AMP_OFF_FILE`, or a future deploy check on the box may fail.
8. **Runbook:** if it isn't there yet, add "How the bot runs: reader, drafter, writer" to `docs/04-technical/swan-bot-runbook.md`, with a pointer in `system-architecture.md` (todo/22's open item). Then delete `todo/22-reader-writer-split.md` and mark 22 done in `todo/README.md`.

## Guardrails
- Pacing from headers only, never circumventing the limit (CLAUDE.md 3–4).
- One writer.
- Small green commits, dry run first, push to `main`, message the orchestrator with each hash.

## Done when
- 2.8–2.9 writes/min at peak with 0 rate-limited;
- first-call ≥ 90%;
- `session_cap_at_send` < 10 a night;
- the queue's oldest wait (`oldest_queued_s`) under 10 min at Sydney peak;
- 0 lost.
