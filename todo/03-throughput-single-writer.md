# 03: Use the whole budget: one writer, all 3 writes/min, plus the idle like/follow/view budgets

**Owner:** Marc (ops) · **Depends on:** 01 · **Unblocks:** 04

## Why
We make ~20 writes/hour out of 180 (11%) ([diagnosis](../docs/06-strategy/diagnosis-2026-10-20.md)). Separate per-route budgets of 30/min for likes, follows and views are almost unused. Causes in the code:
- `bot.py`: `per_min` is clamped to a **hard max of 2**, defaults to 1.0, and adds a 0.7–1.5× jitter;
- `ACCOUNT_MIN_GAP_S = 8 min` × 12 accounts ≈ 1.5 writes/min at most;
- the reply-target queue starves (citizens rarely post), so the loop sleeps 45 s;
- free-tier Gemini quotas park models for hours (`llm.py`).

## Design
### One writer, many producers
Marc's idea of "three concurrent scripts" works only if they share **one** rate limiter. Otherwise they 429 each other and burn the failed-request budget (20 for posting). So:
- **Producers** (async tasks or separate processes) build *jobs*: target, persona, mode, draft text, quality verdict. They put them in a queue: a Mongo `jobs` collection, or an in-process `asyncio.PriorityQueue` if everything stays in one process.
- **One writer** pops the highest-value job and sends it. It paces from `social.rate_limit` (`remaining`, `reset`) as CLAUDE.md rule 4 requires, and drains at the real budget (target 2.7/min, leaving headroom for a human's manual post).
- Separate small token buckets for likes (30/min), follows (30/min) and views (30/min). Each uses its own budget, so they never block writes.
- Drafting runs ahead: keep 5–10 approved drafts in the queue so the writer never waits on the LLM. Drop drafts older than ~20 min (the target thread moves on).

### LLM supply
- Rotating teammates' **free** Gemini keys to dodge per-project quotas is against Google's terms. We flagged it in `TODO.md`, and rules §5.1 says external services must be used within their licences. **Use one paid key instead.** Flash-lite costs cents per thousand drafts; $10 covers the whole competition. Put the billing on one teammate's card, with a budget cap in Google Cloud.
- If teammates each want to run their *own* experiments with their own key, fine, but the production bot uses the one paid key.
- Make the model list configurable (`GEMINI_MODEL`) and add an Anthropic/OpenAI fallback behind the same `Generator.complete` interface if anyone has credits.

### Accounts
- Account gap: 8 min → **3–4 min**. More accounts: grow to ~20 by 25 Oct, one every 15–30 min. Raise `MAX_ACCOUNTS` from 15 accordingly; the 200 lifetime allowance is plenty. [Second-mover plan](../docs/06-strategy/second-mover-plan.md#account-and-write-budget-red-multiplier-by-day) says to save accounts for ×2/×4. The hidden-post watch in `TODO.md` is the real safety limit, so build it now.
- **Hidden-post watch** (from `TODO.md`): per account, count our logged post ids that `get_post` reports as hidden or 404. Park an account at 2 hidden posts, or at 1 hidden post plus ≥100 actions.

### Kill switch and pause
- `PAUSE` file in the repo root, or a Mongo `control` doc `{paused: true}`, checked before every write. Lets any teammate pause from the dashboard (09) without sudo.

## Guardrails
- Never exceed what `rate_limit` says, and back off on 429 (rule 4). No hammering retries.
- Writes off by default (`--live` still required).
- Every job records `owner`, `persona`, `account`, `mode`, `frame`, `git_sha` (attribution, rule 6).

## Done when
Over a 2-hour window on EC2, writes/hour ≥ 150 with zero 429 storms; the like/follow buckets are used by 04; Gemini is never "parked" for quota on the paid key.
