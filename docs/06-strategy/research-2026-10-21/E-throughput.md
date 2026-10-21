# E: Throughput and capacity: can we put ~3 writes/min into targeted citizens?

2026-10-21, ~13:45 UTC (21:45 Perth). Sources:
- `swan_actions.jsonl` pulled 13:27 UTC. The window is 20 Oct 18:00 → 21 Oct 13:00 UTC (19 h) unless stated.
- `data/llm_usage.json`, `llm_spend.json`, `status.json`, `swan_state.json` and `swan_watch.json` on swan-ec2 (read-only).
- One Latest sample: 5 pages = 500 posts, 13:19–13:29 UTC, plus Trending and 8 Trending threads. That was 14 read calls and no 429s.

I made no LLM calls and no writes. Analysis scripts and raw data are in `scratchpad/E/`.

**Short answer:** citizen supply is the bottleneck, not the write budget. Full Latest coverage plus the classify fix gives roughly 40–55 citizen-facing writes/h at peak, about 0.8/min. The pipeline as built tops out at ~80–110 writes/h. The rest of the 180/h can only go to non-targeted writes.

## (a) Bottlenecks, with numbers

**1. Supply of citizen targets (the binding limit).**
- **Latest is almost all team bots.** It runs at 49.3 posts/min, and 491 of my 500 posts were team accounts. Citizens wrote 9 items in 10.1 min, which is 53/h, but **from only 3 authors**: 1473 alone wrote 5. A config note from earlier in the day reads "500 posts in 10.7 min, 7 by citizens" (39/h). So expect ~40–55 citizen items/h from ~15–25 distinct authors/h.
- **Trending and news threads add little.** The 8 Trending threads held 154 replies, 4 of them by citizens (2.6%). Refresh logs show `citizen_news_replies_last_hour` at 0–1.
- **The 72 h contact cooldown is per author**, so distinct new authors matter, not posts. We have contacted 287 citizens so far, 163 of them in the last 24 h.
- **The classify bug cost tonight's whole supply.** None of tonight's 3 authors had been contacted, yet the bot logged **0 candidates at 13:26**. All three are "Yes, with a sunset clause/exemptions" citizens, which the deployed `classify()` drops. With the working-tree classify, 6 of the 9 items qualify.
- **Coverage today is ~25%:** 50 posts per 4 min against ~200 new ones. Latest is the source of 65% of all replies (183 of 283; thread 59, news 39).
- **Estimate at 100% coverage plus the classify fix:** ~25–40 candidate posts/h, which means ≤~20 first-contact replies/h at peak. Adding second voices and reply-backs gives **~40–55 citizen-facing writes/h**. The best measured hours (20 Oct 20:00–21 Oct 03:00 UTC, citizen-first, 25% coverage) averaged 18.3/h and peaked at 23.

**2. Loop order (being fixed elsewhere).**
- Citizen-facing writes fell from 18.3/h (20 Oct 20:00–03:00 UTC) to 5.6/h (21 Oct 05:00–13:00 UTC). Thread replies held 15–18/h.
- Once a candidate is picked, latency is not the problem. Target age at write has a median of **1 min** for replies (p75 3 min) and 3 min for reply-backs, estimated by interpolating post ids against our own posts' timestamps.

**3. Pipeline ceiling (bites only above ~1.5/min).**
- **Pacing is capped below 3/min in code.** `bot.py` clamps `per_min = max(0.1, min(args.per_min, 2.5))`, and `run.sh` passes 2.5. After each send, `next_write = now + 60/2.5 × U(0.7, 1.5)`, a mean of 26 s. Only then is the next job **drafted, serially**.
- **Each Kimi call takes ~6 s** (median reject→write for the same `draft_id` is 5.8 s).
- **Kimi needs 2.8 calls per accepted reply.** Since 05:30 UTC: 37 accepted, 65 rejects. 25 of the 37 needed a repair, and 47 of Kimi's 64 rejects are `length_*`. About 20 of 57 reply jobs failed both tries, so the target was lost.
- **Reply cycle:** ~26 s pacing + ~17 s drafting + ~1 s send ≈ 44 s, which is **~1.4/min (~80/h)**. One-call drafts (flash-lite threads) manage ~1.9/min. The observed gap between writes has a median of 36 s (p10 22 s), so when jobs exist the loop runs at ~1.7–2.3/min.
- **`targeter.refresh()` blocks the loop.** It makes ~30–40 reads every 4 min: news (2 + ~10 threads), journalists 4, Latest 1–4, Trending 1, 12 Trending threads, and `undecided()` per new author. Writes stop for several seconds each time.

**4. LLM quotas (bites at citizen peak).**
- **Every free model was parked for daily quota from 21 Oct 03:30 to 07:00 UTC (Sydney 2:30–6 pm).** Flash-lite's 500/day ran out at 03:30, and Groq gpt-oss/qwen3.8 hit their daily token caps every few minutes. 170 of the 192 `llm_park` events fall in those 3.5 h. Writes carried on through qwen-plus-character and Kimi.
- **Flash-lite already runs at ~500/day** at today's ~32 writes/h (135 calls in the first 6.5 h of today's Pacific day).

**5. Voices (not binding below ~2.5/min).**
- 15 live voices (1 suspended) with a 4-min gap allow 3.75/min.
- Frames don't block. `eligible()` falls back to any ready voice (`fit or ready`), and messenger `prefer` is soft too. What tied voices up on 21 Oct was the thread replies, each of which put a voice into its 4-min gap.

## (b) Marc's three questions

**Should we write at 3/min to target voters?**
No. There aren't 180 reachable target citizens an hour; there are ~20 new authors and ~40–55 useful citizen-facing writes at peak, and far fewer at night (3 authors per 10 min at Sydney midnight).
- **Aim:** answer every reachable citizen within minutes, around 0.7–0.9/min at peak.
- **The other ~2/min of budget:** use it only on writes that cost nothing and risk little, such as booster reposts (todo/18; no LLM).
- **Why not more:** filler writes earn ~0.03 citizen likes each, add hidden-post exposure, and persuasion ≫ volume (moving a citizen away from our side is −80).
- **Raising supply:** wider coverage and classify. Re-contacting a citizen who ignored us is not a fix (todo/19 step 4).

**Would it need several swan_bot processes?**
No, and a second one would hurt.
- **No extra budget, more 429s:** the 3/min is team-wide, so a second writer adds nothing and doubles the 429s, and failed requests burn the separate 20/min failure budget.
- **State races:**
  - `data/swan_state.json` is loaded once and rewritten whole (last writer wins). `replied_posts`, `contacted` and `second_voice` would diverge, so the same citizen gets two replies and the 72 h cooldown breaks.
  - `secrets/swan_accounts.json` `last_write` would let one voice write twice inside its 4-min gap.
  - `llm_spend.json` and `llm_usage.json` are read-modify-write with only a thread lock, so spend would be under-counted and the $85 cap overrun.
- **Rules:** it breaks the repo rule "only one writer process for the team" (todo/README). Any setup whose purpose is more write capacity reads as circumventing a rate limit (CLAUDE.md guardrails 3–4, rules LS.5.2).
- **The one real gain fits in one process:** draft the next job while the pacing timer runs (a drafting thread or prefetch), or use `--batch`.

**Can our API keys and LLM setup handle it?**
At realistic supply, yes once Kimi's length rejects are fixed. At a true 3/min of strong-model drafts, no.
- **Kimi K2.5 cost, measured:** `llm_spend.json` shows $0.1297 for ~115 Kimi calls since 05:30 UTC, which is **$0.0011 per call** at the padded `LLM_PRICES`. That is about 800–1,100 input tokens plus ≤200 output tokens (back-calculated; consistent with the prompts in content.py and no visible thinking). It works out to **$0.0032 per accepted reply now** (2.8 calls) and **~$0.0016 if length is fixed** (~1.4 calls).
- **Daily allowance:**
  - 21–25 Oct: $85/25 = **$3.40/day**, of which only **$2.55** is open to replies (`LLM_AMP_RESERVE_SHARE` 0.25).
  - 26–31 Oct: $6.80/day.
  - 1–2 Nov: $13.60/day.

| Scenario | Strong drafts/day | $/day now (2.8 calls) | $/day, length fixed (1.4) | Fits $2.55? |
|---|---|---|---|---|
| Today's mix, citizen-first (step 1) | ~220 | 0.70 | 0.35 | yes |
| Full coverage + classify (step 2) | ~500 | 1.60 | 0.80 | yes |
| 3/min of strong drafts, 24 h | 4,320 | 13.8 | 6.9 | no, 3–5× over; $85 gone in 6–12 days |

- **Free tiers:**
  - Flash-lite: 500 requests/day. 3/min × 1.4 calls ≈ 6,000/day, 12× over. Batching 4 per call cuts it to ~1,500, still 3× over.
  - Groq: daily token caps, gone by Sydney afternoon.
  - OpenRouter `:free`: ~50/day.
  - Alibaba qwen-plus-character: 1M tokens ≈ 700 calls in total, under a day at 3/min.
  - The 20/day of 3.6/3.8 Flash is reserved for amplified posts and the fact desk.
- **Gemini Tier 1 billing** (an open todo/README item) would lift flash-lite to 150K requests/day. The price is not verified here; at typical flash-lite list prices it would be well under $1.5/day for 6,000 calls (check the console). This is the cheapest capacity lever if second voices and threads outgrow 500/day, which step 2 will cause.
- **In-game qwen2.5-3b:** 3 requests/min team-wide, 1 at a time, ≤1024 tokens, and 42% rejected in our test, so ≤~1.7 accepted/min while it serialises the loop. Use it only as a last fallback for thread one-liners, never for citizen replies.
- **Batching** (`batch.py`, `--batch`; not run live) divides request-limited calls by N and saves repeated system-prompt tokens.
  - It does nothing for supply, and candidates arrive in bursts per 4-min refresh, so batches of 2–3 per refresh are the natural size.
  - Quality drops at 4 items (qwen-plus-character drops items).
  - Worth it for second voices and threads on the free tier; it is not the fix for citizen throughput.

## (c) Ranked changes toward the most targeted writes per hour

Steps 1–2 are another session's work (todo/19 and the working-tree `targeting.py`). They are listed so the numbers add up; don't duplicate them.

| # | Change (where) | Citizen-facing writes/h, peak | Total writes/h | LLM $/day |
|---|---|---|---|---|
| 0 | Now (amplifier first, 25% coverage, old classify) | 5.6 | ~32 | ~0.2 Kimi |
| 1 | Citizen-first `pick_job`; `REPLY_BACK`/`SECOND_VOICE` on; `AMP_LEVELS` heavy replies 4–6 (other session) | ~18–23 | ~35–45 | ~0.7 |
| 2 | Latest paging to the last seen post (`LATEST_PAGES` 4, ~0.75 feed reads/min of 10) + classify keeps "Yes with sunset/exemptions" (other session) | **~40–55** (night ~10–20) | ~55–70 | ~1.6 |
| 3 | **Kimi length rejects** (`quality.py` length check / `repair_note`, the reply prompt's length line in `content.py`): state the cap in characters for Kimi, or trim a too-long draft at a sentence boundary before rejecting | +10–25% (≈20 lost jobs/day saved), reply latency 17 s → ~8 s | same | **~0.8** (halved) |
| 4 | LLM headroom: enable Gemini billing with a spend cap (Marc's decision), or accept Kimi as second-voice fallback when flash-lite's 500 run out | removes the 03:30–07:00 UTC all-parked window | same | +<1 (Gemini) or +~1 (Kimi) |
| 5 | Cheaper refresh (`targeting.refresh`): `TRENDING_THREADS` 12 → 6, or Trending threads every 2nd refresh (4 citizen replies in 154 tonight) | ~0 | +2–5 (less blocking) | 0 |
| 6 | Fill spare slots with booster reposts (todo/18), never ahead of a citizen job | unchanged | ~100–140 | 0 (no LLM) |
| 7 | Only if 1–6 fill >100/h: overlap drafting with the pacing wait (prefetch in `bot.py` main loop) and raise the clamp `min(args.per_min, 2.5)` → 2.8 with `run.sh --per-min 2.8`, still pacing from `rl.remaining` | unchanged | ceiling ~110 → ~165 | 0 |
| 8 | Voices: 15 is enough to ~2.5/min. Add 3–5 (booster → voice; `MAX_ACCOUNTS` 21 → 26; personas needed) only to replace parked voices or if citizen-facing tops ~90/h | unchanged | unchanged | 0 |

**Hidden-post risk for step 8 and higher volume.**
- **Today's rate:** 3 hidden posts plus 1 suspension over ~1,300 text writes, about 1 per 400.
- **At step 2's ~900 text writes/day:** expect ~2 hidden/day. Spread over 15 voices, `HIDDEN_STOP` = 2 would park roughly one voice a day after the first few days.
- **Replacements:** registrations are not short (150 of 200 lifetime left), but the active cap is (49 of 50 live), so each new voice costs a booster.
- **Per-voice cadence:** a full 3/min would mean every voice writes every 5 min all day, a bot-like rhythm that invites Blue reports. That is one more reason not to chase 3/min with LLM text.

**Bottom line:** do 1–3. They reach the supply ceiling (~0.8 citizen writes/min at peak) for ≤ $1/day. Add 4 before flash-lite runs out, which will happen daily after step 2. Steps 6–7 spend the leftover budget without the LLM. Use one process throughout.
