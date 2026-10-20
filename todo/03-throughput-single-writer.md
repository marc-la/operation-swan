# 03: Use the whole budget: one writer, all 3 writes/min, plus the idle like/follow/view budgets

**Owner:** Marc (ops) · **Depends on:** EC2 (done) · **Unblocks:** 04

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

### LLM supply: Gemini quota vs what a full day needs (Marc to sort billing)
**Demand.** 3 writes/min × 1,440 min = **4,320 writes/day** at full pace. With ~25% of drafts rejected and redrafted, that's **~5,500–6,000 LLM calls/day**, plus any simulator calls (06). Today the bot runs `gemini-3.5-flash` then `gemini-3.5-flash-lite`, then falls back to qwen (`--allow-qwen`, 3/min and weak).

**Free tier.** The caps are per model, per project, per day, and Google changes them. We measured 20/day on `gemini-3.8-flash` (19 Oct). Marc's figure for flash-lite is ~1,500/day: check the exact number in AI Studio → *Usage / Rate limits* for our project. Either way, the free tier covers a quarter of a full day at best.

**Don't rotate teammates' free keys** to add up quotas. Using several accounts to get around a provider's limits is against Google's terms, and rules §5.1 requires us to use outside services within their terms. A teammate running their *own* experiments on their own key is fine; the production bot uses one key.

**Free key + model rotation: is it enough for 3/min? (Marc asked 2026-10-20.)** Probably not for a full day. The bot already rotates models (`GEMINI_MODEL` list; each model is parked when its daily cap hits, then the next is tried, then qwen). Free caps are per model per day, so the free total is the **sum of the daily caps of the models in the list**:
- `gemini-3.8-flash`: 20/day (measured 19 Oct);
- flash-lite: ~1,500/day by Marc's figure;
- that's ~1,500–2,000 a day against the **~5,500–6,000** a full day at 3/min needs. Enough for roughly 6–8 hours at full pace, then qwen.

Two things to check before paying:
1. **Gemma models on the Gemini API** (e.g. `gemma-3-27b-it`) have historically had much larger free daily caps than Gemini models, and their quality sits well above qwen 3B. Check AI Studio → Rate limits. If the cap is large, add one to `GEMINI_MODEL` after flash-lite (`GEMINI_MODEL=gemini-3.5-flash-lite,gemma-3-27b-it` in `.env` on EC2) and dry-run 10 drafts through `swan_view.py` to judge the quality.
2. A key in a project **with billing** (ours) doesn't fall back to free limits when the credit runs out: it gets 402 on every model. To use the free tier you need a key from a project **without** billing. One free project of your own is normal; several projects or accounts just to add up quotas is what breaks the terms.

**Paid (recommended).**
0. **Seen 2026-10-20 10:22 UTC on EC2:** Gemini returns `402 Your prepayment credits are depleted. Please go to AI Studio…`. Our key's project is already on **prepaid** billing and the balance is zero, so the bot is running on qwen. **Top up the prepaid credit in AI Studio (Billing) now.** That's the whole fix; no code change. The bot re-tries Gemini every 5 min (`llm.py` parks a model for 300 s on other API errors), so it switches back by itself.
1. AI Studio → API keys → our key's project → **Billing**. Paid Tier 1 has far higher per-minute limits and no small daily cap. This project uses **prepaid credits**: buy a balance (e.g. $40, per the cost estimate below) and turn on auto-reload if offered, so it never runs dry overnight.
2. **Free credit:** new Google Cloud accounts usually get a free-trial credit. Check on the billing page whether it applies to Gemini API usage for that account before paying anything.
3. Billing → **Budgets & alerts**: set an alert at ~$40.
4. Nothing to change in the code: same `GEMINI_API_KEY`. Daily 429s just stop happening.

**Cost (check prices on ai.google.dev/pricing; this uses ~$0.10/M input and $0.40/M output, flash-lite class).** ~6,000 calls × ~2,500 input tokens ≈ 15M input ≈ $1.50/day. ~6,000 × ~300 output ≈ 1.8M ≈ $0.70/day. **About $2–3/day, ~$30–40 for the rest of the competition at full pace.** (Correcting the earlier "$10" estimate, which assumed a partial pace.) Thinking tokens bill as output: `llm.py` sets `max_tokens=4096`, so pass a low reasoning setting (`reasoning_effort="low"`, or `"none"` if the model accepts it) to stop flash models spending tokens on thinking.

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
