# 50 — Prompt fixes 1-5: memory per voice, the conversation, conditional rebuttals, the citizen's register, the lean prompt

Written 2026-10-28 (Marc + Claude). Why and what: [prompt-critique-2026-10-28](../docs/06-strategy/prompt-critique-2026-10-28.md), §8 maps each finding to its change. **Built; offline A/B passed 28 Oct (§9 of the critique): `STYLE_FIXES` ON, `LEAN_PROMPT` off.**

## Switches (`src/swan_bot/config.py`, todo/50 block)
- `STYLE_FIXES = True` adds `("arm_style", ["base", "fixes"], 9000)` to the switchback: in a fixes block, replies, reply-backs and second voices get fixes 1-4.
- `LEAN_PROMPT = True` (with `STYLE_FIXES`): first replies in fixes blocks use `content.lean_system_prompt` and `content.lean_reply_prompt`.
- Dials: `PROFILE_SHARE` 0.25, `ITEM_MAX_PER_DAY` 3, `VOICE_RUN_MAX` 4 of `VOICE_MEMORY_N` 50, `REPLY_QUESTION_SHARE` 0.10, `FIXES_REPLY_FLOOR` 40.
- Freeze: `FREEZE_PIN["arm_style"] = "base"` from `ARMS_FREEZE` (midnight Sydney, 1 Nov). Set it to "fixes" only on a clean read-out.

## Before switching on
1. Offline, never touching the platform (rules §5.1): draft 100 recent targets on the old prompt, the fixes prompt and the lean prompt (`bot.build_prompt` with `config.STYLE_FIXES` / `LEAN_PROMPT` set in the script). Have Sonnet raters pick the bot, blind, shuffled with real citizen replies. Compare the critique's §3 table across the three sets, plus first-try gate pass and repair share.
2. Live, 24 h after switching on: hides, away events per write, citizen replies and engagement per write by `arm_style`. Engagement is the guardrail: it should not drop. Kill rule as before: hides or away events above base.

## Not in scope (see §8 of the critique)
Salience (fix 6), invented history, dashes, one hot voice's volume, roles that drift between replies.
