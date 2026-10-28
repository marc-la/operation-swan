# 51 — Reply-back fixes: no Sonnet lane, depth cap 8, no conceding a conditional Yes, an outcome rule, a drawn opener

Written 2026-10-28 (Marc + Claude). Why: [replyback-persuasion-2026-10-28](../docs/06-strategy/replyback-persuasion-2026-10-28.md) (audit of 1,210 live reply-backs; two blind offline rounds in `scripts/rb_ab.py`, where no persuasion-wording arm passed). **Built, tested and deployed 28 Oct.** Reply-backs only: first replies stay as todo/50 has them until its 24 h read.

## What changed (`config.py`, todo/51 block, each with its own off switch)
1. **`PREMIUM_REPLY_MODES = {"reply"}`.** The Sonnet lane leads fixes-block first replies only. `bot.draft_models` no longer gives Sonnet to reply-backs. Off: `{"reply", "reply_back"}`.
2. **`THREAD_DEPTH_TEST = False`.** Every reply-back caps at `THREAD_MAX_DEPTH` (8): a citizen's reply at depth 8 or more is skipped as `deep_thread`. Back on: `SWAN_THREAD_DEPTH_TEST=1` + restart.
3. **`CONCEDE_CHECK_KINDS = ("reply_back",)`.**
   - **The check:** a reply-back to a conditional-Yes citizen (`quality.conditional_yes`) that grants a safeguard (`quality.conceding_sentence`: "a sunset clause would help", "those protections would be welcome") is rejected as `concede_condyes`.
   - **The fix:** `quality.fix` keeps what follows the "but" or drops the sentence, with no LLM call. Otherwise the repair note quotes the sentence.
   - **Replay on 1,210 sent reply-backs:** it fires on 13%, and the code fix passes 139 of 159.
   - Off: `()`.
4. **`REPLY_BACK_OUTCOME_RULE = True`.** `content.OUTCOME_RULE` goes in every reply-back prompt: "Claim no more about what a Yes or a No would lead to than the facts you were given say." Off: `False`.
5. **`REPLY_BACK_OPENERS = {"own": 0.4, "thanks": 0.3, "none": 0.3}`.** The current-style reply-back draws its opening line (`content.REPLY_BACK_OPENS`), logged as `rb_open` on writes and rejects. `{"thanks": 1.0}` is the old line. It is a plain random draw, not a switchback arm, so the 1 Nov freeze leaves the mix as it is.
6. **A new phrase budget**, `too_late` ("too late to argue/ask…", 5% of the window, all citizen-facing kinds). It came up in 3 of 40 offline drafts under the first wording of the outcome rule; live it is 0.3%, so it doesn't bind today.

Tests: `tests/test_reply_back_fixes.py` (15); `test_llm_budget` and `test_conversion_arms` updated; `test_fingerprint` lists the new phrase. Fast suite 1,494 passed. Slow suite: `test_bot_split::test_every_background_duty_fires` fails on clean HEAD too (own likes off since 06e0d0b), so it is not from this change.

Offline check: 40 recent reply-backs redrafted with this code on Kimi/Haiku (`rb_ab.py --arms base@live`, no platform call):
- sendable 40/40, first try 34;
- opens with thanks 12%, against 75% sent to the same citizens;
- concessions to conditional-Yes citizens 0 of 31, against 3 sent.

## Deploy
Deployed 28 Oct (Marc), ahead of the todo/50 read at ~04:00 UTC 29 Oct. That read's `arm_style` comparison
then spans this change. Read todo/50 on **first replies only** (`act == "reply"`); this change does not touch them.
The one exception is the `too_late` budget, which can't bind at today's 0.3%. Reply-backs are read here.

## Read at 24 h (box, `logs/swan_actions.jsonl` + `swan_outcomes`)
- **Reply-backs:**
  - citizen answers per reply-back, against the 23-28 Oct base (7%; fixes blocks were 1 of 52 with Sonnet);
  - `concede_condyes` rejects and fixes per draft;
  - `rb_open` shares and the share opening with Cheers/Ta/Thanks (target under ~40%);
  - `deep_thread` skips.
- **Guardrails:** away events (primary and contributions) per day against 26-28 Oct; hides on reply-backs.
- **Kill rules:** reply-back answers per write below ~5% for 24 h, or drafts per sent reply-back up by more than a third. Then undo the item that moved it (each has its own switch).
