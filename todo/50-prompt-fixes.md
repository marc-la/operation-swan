# 50 — Prompt fixes 1-5: memory per voice, the conversation, conditional rebuttals, the citizen's register, the lean prompt

Written 2026-10-28 (Marc + Claude). Why and what: [prompt-critique-2026-10-28](../docs/06-strategy/prompt-critique-2026-10-28.md), §8 maps each finding to its change. **Built; offline A/B passed 28 Oct (§9 of the critique): `STYLE_FIXES` ON, `LEAN_PROMPT` off.**

## Switches (`src/swan_bot/config.py`, todo/50 block)
- `STYLE_FIXES = True` adds `("arm_style", ["base", "fixes"], 9000)` to the switchback: in a fixes block, replies, reply-backs and second voices get fixes 1-4.
- `LEAN_PROMPT = True` (with `STYLE_FIXES`): first replies in fixes blocks use `content.lean_system_prompt` and `content.lean_reply_prompt`.
- Dials: `PROFILE_SHARE` 0.25, `ITEM_MAX_PER_DAY` 3, `VOICE_RUN_MAX` 4 of `VOICE_MEMORY_N` 50, `REPLY_QUESTION_SHARE` 0.10, `FIXES_REPLY_FLOOR` 40.
- Freeze: `FREEZE_PIN["arm_style"] = "fixes"` from `ARMS_FREEZE` (midnight Sydney, 1 Nov); pinned 28 Oct (Marc). Back to "base" if the 24 h read-out is bad.

## Before switching on
1. Offline, never touching the platform (rules §5.1): draft 100 recent targets on the old prompt, the fixes prompt and the lean prompt (`bot.build_prompt` with `config.STYLE_FIXES` / `LEAN_PROMPT` set in the script). Have Sonnet raters pick the bot, blind, shuffled with real citizen replies. Compare the critique's §3 table across the three sets, plus first-try gate pass and repair share.
2. Live, 24 h after switching on: hides, away events per write, citizen replies and engagement per write by `arm_style`. Engagement is the guardrail: it should not drop. Kill rule as before: hides or away events above base.

## Not in scope (see §8 of the critique)
Salience (fix 6), invented history, dashes, one hot voice's volume, roles that drift between replies.

## Sonnet lane (28 Oct, Marc)
- `config.PREMIUM_REPLY_MODELS = (SONNET,)`: Sonnet 4.6 leads high-value replies (`bot.high_value`: movable classes, citizens who answered us, reply-backs) **in fixes blocks only**; Kimi/Haiku follow as the fallback. It sits in `deploy/llm_chain.txt` only to be named: `llm.Generator.complete` skips it on unrestricted calls, `draft_models` drops it from every other order. `LLM_MODEL_RPM[SONNET] = 6` (account quota 10/min).
- Why: offline A/B on 100 targets (same prompt, Sonnet vs Kimi/Haiku, Sonnet raters blind): fixes prompt engage +3.8 [+2.1, +5.5], misread -5 pts, first-try gate pass 85% vs 62%, repeats what we told the citizen 9% vs 17%; P(bot) not lower; on the base prompt P(bot) +5.0, hence fixes only. Lean prompt on Sonnet: 59% first-try pass. Caveat: the rater is also Sonnet; shift did not move for any set.
- Cost to watch: it converges on the same wording (16% of drafts would hit the phrase budgets vs 2%); about $0.01 a reply, est. $5-10 a day.
- Read-out at 24 h: `backend` = Sonnet vs not, within fixes blocks: hides, away events, citizen replies, engagement per write, `voice_repeat`/phrase-budget rejects. Kill: `PREMIUM_REPLY_MODELS = ()`.

## Checkpoints (28 Oct, Marc: hold other changes until these are read)
- **~10:00 UTC 28 Oct (6 pm Perth):** 6 h read, fixes against base (`python scripts/engagement_report.py --hours 24` on the box, or the join of `arm_style` with `logs/swan_outcomes.jsonl`). The 1 h read at 06:20 UTC had 83 fixes writes at 2.4% citizen replies against 7.7% base (thin).
- **~04:00 UTC 29 Oct (noon Perth):** 24 h read incl. Sonnet (`backend`). **Kill rule:** fixes citizen replies per write below about 6% against base's ~8%, or hides/away events above base: `STYLE_FIXES = False` (this also removes the Sonnet lane) and drop the `FREEZE_PIN["arm_style"]` line. Sonnet had written nothing by 06:20 UTC (runs in fixes blocks only): confirm `backend` shows it in the first fixes block.
- Three changes landed within 3 hours on 28 Oct (fixes 03:32, pin 06:03, Sonnet 06:06 UTC), so attribute with care; no other behaviour changes until the 29 Oct read.
