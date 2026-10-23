# swan_bot runbook (written 2026-10-20)

Code: `src/swan_bot/`. Strategy behind it: [06-strategy](../06-strategy/README.md). **Dry run by default**: nothing is registered or posted without `--live`.

## What it does (updated 2026-10-20)

Plan behind it: [second-mover-plan](../06-strategy/second-mover-plan.md).

- **One process does all our writing.** It's capped by `--per-min` (default 1.0, hard max `config.MAX_PER_MIN` = 3; live: 2.4 since 2026-10-22 05:00 UTC (todo/27; was 2.9)) and paced from the write budget's `X-RateLimit-*` headers ([throughput](#throughput-and-pacing-2026-10-22-todo24)). The real pace follows the target queue. If nothing is worth writing, it waits.
- **Each write slot goes to the best job:**
  1. reply back to a citizen who replied to us (and follow them);
  2. second voice: a different persona and angle on a doubt we answered 10–30 min ago, if the thread is ≤ 8 replies and they haven't answered yet;
  3. reply to an undecided citizen. Candidates come mostly from the papers' referendum article threads (ids 1–2), plus Latest/Trending. Citizen = created before launch and not verified. Firm Yes, firm No, loud or anti-KITB posts are skipped, as are citizens contacted in the last 3 days;
  4. reply to a journalist's referendum post (≤ 1 per 45 min, same journalist ≤ every 6 h);
  5. persona post: ≤ 1 in 4 writes, or one per 30 min when idle.
- **Content** (`content.py`):
  - 12 personas with local details, 12 frames, Yes rebuttals, varied openings and post shapes;
  - tone from the [Vote No briefing](../01-competition/vote-no-briefing.md);
  - only true in-game facts. Medical exemptions exist, and the certificate is separate from the ID card.
- **Quality gate** (`quality.py`) rejects:
  - LLM artefacts, hashtags, emoji, links, @mentions, wrong length;
  - endorsing Yes; posts that don't say No;
  - stock phrases ("Spot on", "crucial"…);
  - unapproved numbers;
  - wrong claims about the Act;
  - voting logistics;
  - replies that don't name the citizen's point or an in-world fact (`not_specific`, below); posts without a local detail;
  - text copied from the fact list, parroting the citizen, near-duplicates.
  - **`not_specific` (2026-10-23).** A reply passes when it has a `FACT_ANCHORS` word, one of the citizen's `wants`, a `FACT_PARAPHRASES` hit (the same facts in other words: "won't say which doors", "switch-off", "Daily Kingstonia", "staged"), or `touches_target`: a distinctive word of their post plus a mechanism word of ours (papers, door, check, card, staff...). Why: `content.WORN_PHRASES` and the phrase budgets tell the model to keep off "end date", "venue list", "sunset", "after the vote" and "blank cheque", the very words the old anchors needed, so 316 of 721 rejects in 24 h (22-23 Oct) were good replies, and only 19% of those jobs got a reply out (repairs repeated the failure 155 times). Replayed offline, 84% of those rejects now pass the gate (the rest are vague, or fail another gate such as `copied_fact`). Bare topic words (pass, papers, door) and `rules`/`laws` are not evidence on their own. Also `wrong_logistics` matched the name "Tala" as the currency (8 jobs, none ever sent): it now needs a number before "tala". Tests: `tests/test_specific.py`. If `not_specific` climbs again, check `data/facts_auto.toml` for a new desk fact whose wording has no anchor, and add its paraphrase to `FACT_PARAPHRASES`.
  - **Targeted repairs and phrase echoes (2026-10-23, `tests/test_repairs.py`).** Live logs 22-23 Oct (699 rejected drafts, 1,369 sent): 33.8% of drafts rejected; the repair note never saw the citizen's post. (1) `quality.repair_note` now also takes `target_text`, `wants`, `same`, `phrase_texts`: `not_specific` names their own word(s) (`their_words`; never "exemptions") or their `wants` (not a used-up one), `near_duplicate` quotes the wording we already sent (`shared_wording`) and the opening to avoid, a phrase note says when it was their word and only mentions the vote when `vote` is over; a draft that is the model's own notes ("The user wants...") or a JSON shell gets a fresh draft, not a repair. `bot.gate` keeps the draft after the code fixes (`job["gate_draft"]`) so the repair is of the text the reason is about. (2) New code fixes (no LLM call; the gate re-runs on the result): a leading "Sure," goes; `phrase_<keys>` (not `vote`) and `near_duplicate` drop the sentences saying the phrase or repeating our wording, but never when it leaves under 2 sentences or 55% of the text, a sentence that leans on the dropped one ("That's why..."), or an opening under 20 characters. (3) Echo allowance: 114 of 118 `phrase_sunset` rejects answered a citizen who wrote "sunset" themselves (28% of the citizens we answer do), and `worn_line` already let the model use their word. `over_budget` now lets a draft say a budgeted word the citizen wrote, up to `ECHO_CEILING` (1.5) x the budget (sunset: 10 of the last 100 texts for our own use, 15 in all), never for the tells, `vote`, or a text with 3+ worn phrases. (4) When the window is full the prompt says so up front (`quality.spent_phrases` -> `worn_line(spent=)`): "We have used up 'sunset' for now...". Offline replay (`SINCE` 22 Oct 04:44 UTC, today's gate on both sides): draft reject rate 35.2% -> 22.4%; jobs with a reply out 78.9% -> 88.0%; LLM calls per accepted reply 1.58 -> 1.32; rolling window simulation: peak `sunset` in any 100 texts 10 -> 15, every other phrase unchanged (<=10). Not measurable offline: whether the new repair notes lift the LLM's repair success (it was 15% for `not_specific`, ~31% for `near_duplicate`). To turn the sentence-dropping fixes off, make `fix()` return None for `phrase_` / `near_duplicate`; to turn the echo allowance off, set `quality.ECHO_CEILING = 1.0`.
- **Accounts:**
  - one registered every 20–40 min up to `--accounts` (default 6; tool cap 15);
  - each writes at most every 8 min;
  - kept, not retired (scoring §3: actions alone never suspend);
  - every account records its owner (`CTN_OPERATOR`, default `marc`).
- **LLM:**
  - Gemini models in order (`GEMINI_MODEL`, default `gemini-3.5-flash,gemini-3.5-flash-lite`). A daily-quota 429 parks that model until its reset; a per-minute 429 parks it for a minute.
  - Free-tier `gemini-3.8-flash` allows only 20 requests/day.
  - qwen is used only with `--allow-qwen`. Otherwise the bot waits rather than post weak text.

## Run

```bash
source .venv/bin/activate
python scripts/run_swan.py --samples 10                       # dry run: real targets, nothing posted
python scripts/swan_view.py -n 20 --rejects                   # drafts in place: news item > citizen > our reply
python scripts/run_swan.py --live --accounts 6 --hours 9      # asks you to type GO
python scripts/swan_measure.py                                # engagement per post/frame/persona
```

- **Stop:** Ctrl-C (SIGINT) or SIGTERM. With the split loop, the bot finishes its current step, saves its state and exits 0 (see below).
- **Files** (all gitignored):
  - `secrets/swan_accounts.json`: passwords and tokens (mode 600);
  - `logs/swan_actions.jsonl`: every write, reject, refresh (with citizen activity counts), register and follow, with owner, frame, target and context;
  - `data/swan_state.json`: replied posts, contacted citizens, pending second voices, recent texts.
- **Before going live:**
  - read a dry run with `swan_view.py`;
  - check `feed_lock`;
  - make sure no teammate is running another writer (the rate limit is shared).

## How the bot runs: reader, drafter, writer (2026-10-22, todo/22)

Since todo/22, one process runs three threads (`config.SPLIT_LOOP = True`). They make the same decisions as the old
single loop, so a write no longer waits for a read or a draft. Code: `main()` in `src/swan_bot/bot.py`. Both loops
call the same steps (`choose`, `draft`, `send`, `poll_reply_backs`), so a change to what the bot does is made once.

- **Threads and what each owns:**

  | Thread | Does | Writes |
  |---|---|---|
  | **reader** | `targeter.refresh()` (every `REFRESH_S`, the only Latest/Trending reader) and the reply-back poll (every `NOTIF_EVERY_S`). Has its own `LegitSocial` client and its own sessions (`bot.Sessions`), because a client keeps the `X-RateLimit-*` of its last answer. | `data/latest_snapshot.json` (for swan-blue); notifications resolved |
  | **drafter** | `pulse.update`, then `choose()` (the greedy order: reply-backs, citizens, amplifier jobs, second voices, journalists, posts) and `draft()` (prompt, LLM, gate, light read). A failed draft is requeued or logged lost here (G8). `config.DRAFTERS` of these threads run at once (`drafter-1`..`drafter-N`, [below](#several-drafters-2026-10-23)); each waits when `DRAFT_AHEAD` drafts are chosen and not yet sent. | `data/llm_usage.json`, `data/llm_spend.json` (`llm.py`: the bot's only LLM caller; the hourly swan-factdesk process writes them too, as before) |
  | **writer** (main thread) | registration, `own_likes`, `amp.tick`, `write_status`, then `send()`: the send-time checks, the write, the bookkeeping. **The only thread that writes to Legit Social.** Pacing: `next_write` from `write_gap` (the pace gap or the headers' gap, whichever is longer; [throughput](#throughput-and-pacing-2026-10-22-todo24)), and the Retry-After on a 429. | `data/swan_state.json`, `secrets/swan_accounts.json`, `data/status.json` |

- **Queues between them:**
  - targeter candidates (reader → drafter, `targeting.Targeter`);
  - the reply-back queue `queue` (reader → drafter);
  - `ready`, the checked drafts (drafters → writer; `ready` + `inflight` at most `DRAFT_AHEAD`). The writer sends the first one whose voice may write now (`voice_wait`: 4 min, a reply-back 60 s, a repost 60 s).
  - Drafts not yet sent count as written when the drafter chooses (`held()`). Their voices are reserved (`Accounts.reserved`), their modes count for the post and journalist limits, their citizens count for the session cap (`contacted_now`, todo/24), and their texts count for the near-duplicate check.
  - At send time the writer drops a draft whose target was answered meanwhile, or whose citizen hit the session cap (`gone_at_send`, logged `skip …_at_send`).
- **Locks:**
  - `mu` (an RLock in `main()`) guards `state`, the reply-back queue, `ready`, `stats`, the account records, the themes ledger and the amplifier;
  - `Targeter.lock` (an RLock; `@locked` methods) guards candidates, the funnel and journalist posts. `refresh()` takes it per item (with that item's parent reads), never across a feed or thread read;
  - lock order is always `mu` then `Targeter.lock`, and no LLM call or feed read happens under `mu`;
  - the action log has its own lock (`bot._LOG_LOCK`).
- **State files: one writer each,** written to a `.tmp` and then `os.replace`d:
  - the writer saves `swan_state.json` (the reader asks it to with `save_due`) and `swan_accounts.json`;
  - the reader writes `latest_snapshot.json`.
- **Watchdog, stop, heartbeat:**
  - the writer checks each thread every round. If one died or went silent (`READER_SILENT_S` 20 min, `DRAFTER_SILENT_S` 30 min, each drafter on its own heartbeat), it logs `thread_died`, alerts (`BOT THREAD DIED`, via `deploy/alert.sh`), saves and exits 1, so systemd restarts it;
  - SIGINT/SIGTERM set a stop flag. Each thread finishes its step (never mid-send), drafts not sent go back (a reply-back to the saved queue, a citizen to the targeter as `held`), then the state is saved and the bot exits 0;
  - `status.json` gains `loop`, `threads.{reader,drafter-1..N,writer}.{last_run, age_s, max_silent_s}`, `queue.{reply_backs, candidates, drafts_ready, drafts_inflight}`, `oldest_waiting_s` (since the citizen wrote it) and `oldest_queued_s` (since it entered our queue, deliberate waits and todo/23 groups left out).
- **First live night (21 Oct 16:00 to 23:00 UTC):** a steady 2.2–2.3 writes/min, 0 rate-limited, 0 thread deaths. The serial loop goes once the split has run a clean day (from 21 Oct 15:45 UTC); until then it is the rollback.
- **Rollback:** set `SPLIT_LOOP = False` in `config.py` and push. The bot restarts within about 2 min on the old serial loop (same steps, one thread, Ctrl-C raises as before).
- **Invariants and their tests** (`tests/test_bot_split.py`). These are end-to-end runs of `main()` against a fake Legit Social with sockets blocked, in both loops:
  - every job type and every background duty still runs;
  - only the main thread writes;
  - writes are never closer than `pace_gap` (`write_gap` takes the longer of it and the headers' gap), and a 429 waits;
  - the voice gaps hold;
  - no target is answered twice;
  - each state file has one writer, and no `.tmp` files are left;
  - the watchdog fires on an injected reader or drafter failure (the thread is named `drafter-N`);
  - SIGTERM stops cleanly with every write recorded.

## Several drafters (2026-10-23)

Why: drafting was the bottleneck, not the rate limit. One drafter thread and one `inflight` slot meant each draft (Kimi K2.5, 15-30 s, about 35% rejected, plus repair calls) blocked the next one; `DRAFT_AHEAD` only buffered finished drafts, so the writer starved (158 `wait: drafting` events an hour, ~2 writes/min against ~2.9 allowed).

- **Threads.** `config.DRAFTERS` (3) workers `drafter-1`..`drafter-N` run `drafter_step`; the watchdog gives each its own heartbeat and `DRAFTER_SILENT_S`. `DRAFTERS = 1` is the old behaviour. The serial loop (`SPLIT_LOOP = False`) is unchanged.
- **`inflight`** is a list of the jobs under way (it was one slot), guarded by `mu`. `held()` = `ready` + `inflight`, so `choose()`, `contacted_now`, `save_state`, `shutdown` (puts every one back: citizen to the targeter as `held`, reply-back to the saved queue, voice un-reserved) and `status.json` (`queue.drafts_inflight`) all see every job.
- **Cap.** `DRAFT_AHEAD` (4) now bounds `len(ready) + len(inflight)`, checked again under `mu` just before `choose()`. At 3 drafting and 1 waiting, or 1 drafting and 3 waiting, a draft waits at most about a minute for the writer at 2.9/min (it used to be 2 waiting plus 1 under way).
- **No double booking.** `choose()` picks the job and the drafter reserves its voice (`Accounts.reserved`) and adds it to `inflight` in one `mu` block. `eligible`, `assignable`, the amplifier's `pick_author` and its `answer` jobs skip reserved voices (the `answer` check and the reply-back check are new). A citizen with a job under way is skipped: `choose()` pads that citizen's session count (their candidates wait as `session_cap`), and their reply-backs and second voices wait for the next round. The post and journalist limits already counted `pending` modes.
- **After a draft** (under `mu`): `bot.clashes_with_ready` drops a draft that repeats the opening or is a near-duplicate of one that finished while it was under way (the gate only saw the texts known at its start); the citizen goes back as `clash_concurrent`.
- **Shared state.** `no_model_until`, the no-model alert counters and `stats` are only changed under `mu`; the alert goes out after it. The pulse is no longer refreshed by a drafter (see "Pulse thread" below). `woken` is shared: a drafter clears it just before its own `choose()`, so it can't miss what arrived after.
- **LLM pacing.** `llm.Generator._pace` books each call's slot under a lock and sleeps outside it, so concurrent drafters are spaced `min_gap` (6 s at `LLM_RPM` 10, per model) apart and never refused. A draft is about 1.5 calls at 15-30 s, so three drafters make about 6-9 calls a minute on Kimi: at or just under the cap. If the reply model is the limit, `_pace` queues the calls; raise `LLM_RPM` only if the provider allows it.
- **Load spreading (2026-10-23).** The 10/min is our own cap, not a provider limit (no doc here gives Bedrock's real quota for Kimi or Haiku; unknown). Reply, journalist and amplified drafts go through `llm.Generator.complete_in_order` (`bot.complete_in_order` delegates): each model is tried with `pace_cap = config.LLM_OVERFLOW_AT_S` (2.5 s); if its next free slot is further off, `_pace` raises `Saturated` before booking anything (not a park, not a failure) and the call moves to the next model of `config.LLM_OVERFLOW_MODELS` (= `REPLY_MODELS`: Kimi, Haiku, flash-lite) that is also in the draft's own list and free now. Kimi is used whenever it is free. If all are busy the best is waited for, at most `LLM_MAX_WAIT_S` (20 s, enforced in `_pace`). GLM-5 (`REPLY_NEVER`), models outside the overflow set (the free tail of the chain) and Sonnet (not in the chain) are never reached by overflow; parked or over-budget models are skipped as before; an overflow model that errors parks as usual and the call falls through, so no draft is lost. Audit: the reply row's `backend` is the model that wrote it and `meta.overflowed_from` the lead it replaced; `status.json` `llm[].overflow_in` counts per model. Knobs in `config.py`: `LLM_OVERFLOW_AT_S` (0 = off), `LLM_OVERFLOW_MODELS`, `LLM_MAX_WAIT_S`, `LLM_MODEL_RPM` (per-model cap, empty). Live measure (22-23 Oct, one drafter, Kimi): draft 5 s median / 10 s p90, 1.17 calls per sent reply, 63% of drafts sent, so ~5.5 Kimi calls/min at 2.9 writes/min; overflow is mostly for bursts. Haiku has no live reply data yet (the lab saw 18 of 20 first drafts too long for the gate), so watch its accept rate per `backend` before raising its share. Tests: `tests/test_llm_overflow.py`.
- **Tests:** `tests/test_drafters.py` (end to end, slow fake LLM): no two drafters share a voice or citizen, `held()` holds every job under way, `ready` + `inflight` within the cap, a stop puts every job back, unique watchdog names, pacing with several callers, and the pulse thread tests below.
- **Pulse thread (2026-10-23).** `pulse.update` (one LLM call every `PULSE_EVERY_S`, 30 min) runs in its own `pulse` worker (`pulse_step`), never in a drafter. It copies `pulse`/`pulse_next` under `mu`, calls `pulse.update` outside it, writes the two keys back under `mu`; drafters only `pulse.current(state)` under `mu`. Same cadence and checks as before (a third of the period after a failure). It looks whether a refresh is due every `PULSE_POLL_S` (30 s) and does nothing once stop is set. After a cold start (no saved pulse) the first drafts may go out before the first pulse lands. A failed refresh (any exception) is logged once as `pulse_error`, retried after a third of the period, and drafting uses the last pulse (until `PULSE_MAX_AGE_S`). The watchdog treats it as non-critical (`Worker(critical=False)`, `PULSE_SILENT_S` 30 min): if it dies or goes silent it logs `thread_died` with `fatal: false` and alerts once ("BOT THREAD FAILED (not fatal)"), and the bot runs on; restart when convenient. The serial loop still calls `pulse.update` inline. Tests: `tests/test_drafters.py` (only the pulse thread calls it, a slow call does not hold drafting, a failing refresh and a silent thread do not stop the bot).
- **Expected:** with drafts always ready, the writer is limited by the write budget again (~2.8-2.9/min); drafting capacity at 3 drafters is roughly 4-6 drafts/min, against the ~4.5 drafts/min needed for 2.9 writes at 65% accepted. Not yet measured live: watch `wait: drafting` and `drafts_ready` on the dashboard after the deploy.

## "No model": what it means and how to read it (2026-10-23)

Why: from 22 Oct 19:13Z the LLM day allowance ran down, Kimi (priced) was skipped by the budget gate and the free models were out of quota or parked, so nothing could answer. `next_available_in()` only looked at park times, and a model skipped for the budget, the daily floor or the amplified-post reserve is *not* parked, so it said "available". Drafting kept choosing jobs, and `lose()` dropped journalist, post and second-voice jobs (their selection state only changes after a send), so the same slot was re-picked ~200 times a second: 580,780 `lost no_model` rows (88% of a 119 MB log), ~760 writes lost in 8 h.

- **What "no model" means.** No model in the chain is eligible for the call: not parked, and if priced, today's allowance (`llm.allowance`, daily floor included) is not spent and, for an ordinary call, more than the reserve (`LLM_AMP_RESERVE_SHARE` of today's share) is left. A draft may spend the reserve (`draft_checked` asks again with `priority=True`), so for drafting "no model" means priority-eligible: free models all parked or out of quota, and the allowance spent.
- **The helper.** `LLMChain.no_model_wait(priority=False, models=None)` (`llm.Generator`): seconds until some eligible model could answer, `0.0` if one can now. A priced model the budget holds back counts as off until Sydney midnight (when the allowance steps up), a parked one until its park time (the later of the two); the answer is the minimum over the chain. Empty chain: 3600. `allow_qwen` with no restriction: 0. `next_available_in(priority=True, models=None)` is the same call (default priority, as drafts use it). `bot.model_wait(gen)` is what the loops call (falls back to `next_available_in` for a fake without the helper).
- **Waiting.** The serial loop and every drafter check `model_wait` before choosing: if nothing can answer they record a hit (`no_model_hit("any", ...)`) and wait `wait + 1` s (at most `NO_MODEL_PAUSE_MAX_S` = 600). Reposts need no model but wait too while nothing can answer (as they did when every model was parked before). If a draft is tried and still finds no model (a restricted model list, an error), one failed draft pauses all drafting `NO_MODEL_PAUSE_S` (60 s, or the helper's wait if longer, up to 600); after `NO_MODEL_TRIES` (10) attempts in one episode the pause stretches to `NO_MODEL_LONG_PAUSE_S` (180 s), logged once (`backoff: true`). Hit, pause and deferral happen in one `mu` hold, so no other drafter re-picks the job in between.
- **Nothing is dropped.** `lose(..., "no_model")` calls `bot.defer(job)` for every mode: a reply goes back to the targeter (`requeue`, no try counted since `no_model` is a "free" reason there, no backoff), a reply-back to the front of the queue (tries unchanged), a second voice back into `state["second_voice"]`, thread/answer jobs back into the amplifier's `amp_threads` with the voice's turn undone (`job["defer"]`, set where the job is picked), and post, amplified post and journalist jobs just stay unchosen (their state changes only after a send). Only a job that cannot be put back (a reply with no candidate, an unknown mode) is logged `lost`. Real gate failures (`gate:*`) are unchanged: requeue/lost with a try.
- **Log rows: one episode, not one row per attempt.** `{"act":"no_model","phase":"start"|"ongoing"|"end", "n", "new", "modes", "since", ...}` in `logs/actions.jsonl`. `start` is the first miss; `ongoing` at most every `NO_MODEL_LOG_EVERY_S` (30 s), plus once when the pause stretches; `end` once a model has answered `NO_MODEL_RECOVER_S` (30 s) without a new miss (so a flapping model does not make a row per flap). `n` = attempts in the episode so far (every loop wait or failed draft counts one), `new` = attempts since the previous row (so the rows add up), `modes` = which job kinds those were (`any` = the loops saw nothing could answer and tried none), the `end` row adds `duration_s` and `modes_total`; `pause_s` and `wait_s` show the pause chosen and what the chain said. Worst case a few rows a minute. No `lost`/`requeue` rows with `why: no_model` any more (older logs and `expired:no_model` still have them).
- **Alert.** `NO MODEL: ...` once per episode, when `NO_MODEL_ALERT_N` (5) attempts fall within 10 min or the episode is `NO_MODEL_ALERT_AGE_S` (5 min) old (long waits mean few attempts); `recovered: ...` once when the episode ends. The dashboard "Drafting" banner counts `new` from the episode rows as well as legacy `lost`/`requeue` rows.
- **How to read it.** `grep '"act": "no_model"' logs/actions.jsonl | tail`: a `start` row without an `end` is an open spell; `wait_s` near the seconds to Sydney midnight means the allowance is the cause (`data/llm_spend.json`, dashboard budget line), small values mean free models parked (`status.json` `llm[]`). `modes: {"any": k}` = nothing could answer and nothing was tried; named modes = drafts were tried and failed (look for a restricted model list). If the allowance is the cause, the fix is config (`LLM_DAILY_FLOOR_USD`, `LLM_BUDGET_USD`), not code.
- **Tests:** `tests/test_no_model.py` (helper, `defer`/`lose` per mode, the amplifier's undo, dashboard count), `tests/test_bot_split.py::test_no_model_pauses_the_drafter`, `::test_no_model_defers_every_mode_and_drafting_resumes` (reply, reply_back, journalist, post, second_voice), `::test_spent_allowance_and_parked_free_models_do_not_spin` (real `llm.Generator`, the incident shape, with and without the old "wait is 0" bug).

## Throughput and pacing (2026-10-22, todo/24)

Settings: the `# ---- todo/24 throughput ----` block in `config.py`, and `--per-min` in `deploy/run.sh`.

- **Pace.** After each write the writer reads the write budget from that answer's headers (posts, replies and reposts share 3/min, team-wide). The next write waits for the longer of two gaps (`bot.write_gap`):
  - the pace gap, `60 / per_min` times 0.85–1.15 (`WRITE_JITTER`, mean 1.0; it was 0.7–1.5, which ran 10% slow);
  - the headers' gap (`bot.header_gap`): until `X-RateLimit-Remaining` is back to `WRITE_MARGIN + 1` (2). The bucket refills steadily, one write every `reset / (limit - remaining)` s, so the limit is read from the headers, never assumed.
  - So each of our writes leaves 1 write in the bucket for the swarm (`swan-swarm` reposts while ≥ `SWARM_WRITE_RESERVE` are left). A 429 waits its Retry-After, as before. `status.json` shows `write_budget` (limit, remaining, reset, margin) from our last write.
  - Expected: ~2.8–2.9 of our writes a minute when drafts are ready (a simulation in `tests/test_throughput.py` gives 2.8 with a swarm repost every 5 min, and no 429).
- **Reply models** (`REPLY_MODELS`, `REPLY_NEVER`): replies and reply-backs try Kimi K2.5, then flash-lite, then the rest of `deploy/llm_chain.txt`, never GLM-5 (0 of 69 first-call passes on 21–22 Oct). Amplified posts keep `AMP_MODELS`.
- **No draft for a capped citizen:** the drafter counts drafts waiting for the writer as sent when it applies the session cap (`bot.contacted_now`). Before, a citizen with one voice this session got a second draft while the first waited, and one of the two was dropped at send (`session_cap_at_send`, 100 overnight). The send-time check stays as a backstop.
- **Near-duplicates** (`quality.near_duplicate`): a reply is compared strictly (`NEAR_DUP_SAME` 0.25) to our texts to the same citizen or thread (`bot.same_target_texts`, from `state["recent_sent"]` and the waiting drafts), and loosely (`NEAR_DUP_OTHER` 0.3; 0.4 until todo/27 on 22 Oct, when one reply skeleton from many voices got hidden) to our other recent texts. Posts, thread replies and journalist replies stay at 0.25 against everything. Replaying the night of 21–22 Oct: reply near-duplicate rejects 187 → 44.
- **Latest bands** (`LATEST_MAX_BANDS` 60, was 6): at Sydney peak the feed budget allows about one page a refresh (`X-RateLimit-Remaining` 0–3 though our processes read ~1 a minute), so each refresh over 100 new posts leaves a band. 6 filled in 12 min on 21 Oct and 3 were dropped (`lost: latest_band_dropped`). They're now kept and read back off-peak.
- **Lighter refresh** (`NEWS_THREADS_S` 30 min): the replies under the papers' article posts are read every 30 min, the papers' own posts (headlines for the pulse and persona posts) every refresh. The refresh log has `news_threads_read`.

**What to watch** (`logs/swan_actions.jsonl`, `data/status.json`): writes a minute at peak (target 2.8–2.9), `rate_limited_last_hour` 0, `skip session_cap_at_send` under 10 a night, `reject near_duplicate`, `lost latest_band_dropped` 0, and `oldest_queued_s` under 10 min at Sydney peak.

## Hosting

**Since 2026-10-20 the bot runs on EC2 under systemd, with auto-deploy from `main`. See [hosting](hosting.md).** Don't run `--live` anywhere else. The laptop/tmux instructions are retired.

## Diagnosing without SSH (2026-10-23, [todo/34](../../todo/34-box-robustness.md))

The team's one EC2 box runs the bot, Blue, the dashboard, the timers and the update timer: `i-06471b75b0166b3c7`, region `ap-southeast-2`, Elastic IP 13.210.120.238 (survives stop/start), **t3.medium since 2026-10-23 03:03 UTC** (was t3.micro, 913 MB), **Unlimited** credit mode. When it stalls, SSH accepts the TCP connection and never sends a banner, the dashboard is slow and **no alerts arrive, because they live on the box too**. These commands were all run on 23 Oct.

**SSH-less checklist**
1. Load the AWS key (below) and set `INST=i-06471b75b0166b3c7`.
2. `describe-instance-status`: checks passing while SSH hangs = the OS is starved, not a dead VM.
3. `get-console-output`, grep for OOM kills: which unit, how big.
4. CloudWatch: `EBSByteBalance%` ~0 and `CPUCreditBalance` 0 are the usual starvation signs; `NetworkIn` rules an attack in or out.
5. Fix: `reboot-instances`; if it comes back and stalls again, stop, resize, start (same IP).
6. Confirm over SSH (last section), and check that the dashboard shows the right commit.

### The key (never print it)

The IAM user is `ctn-user` in account 618529336476 (EC2 permissions). Its key is in `.env` as `EC2_ACCESS_KEY` and `EC2_SECRET_ACCESS_KEY`. The laptop's **default AWS profile is a different account and cannot see the box**, so load the team key into the environment, and do not `echo`, `set -x` or paste it anywhere:

```bash
# ~/ctn/secrets/awsenv.sh  (secrets/ is gitignored; source it, do not run it)
env_get() { grep -E "^[[:space:]]*(export[[:space:]]+)?$1[[:space:]]*=" "$HOME/ctn/.env" | tail -1 | sed -E 's/^[^=]*=//; s/\r$//; s/^[[:space:]]*["'"'"']?//; s/["'"'"']?[[:space:]]*$//'; }
export AWS_ACCESS_KEY_ID=$(env_get EC2_ACCESS_KEY)
export AWS_SECRET_ACCESS_KEY=$(env_get EC2_SECRET_ACCESS_KEY)
export AWS_DEFAULT_REGION=ap-southeast-2 AWS_PAGER=""
export INST=i-06471b75b0166b3c7
unset -f env_get
```

Check it is the right account without showing the key: `aws sts get-caller-identity --query Account --output text` must print `618529336476`. If it does not, the default profile is still in use.

### Triage, in order

```bash
source ~/ctn/secrets/awsenv.sh
aws ec2 describe-instance-status --instance-ids $INST --include-all-instances
aws ec2 get-console-output --instance-id $INST --latest --output text --query Output \
  | grep -E 'Out of memory|oom-kill|invoked oom-killer|Killed process'
```

- **`describe-instance-status`:** `InstanceState` running, `SystemStatus` and `InstanceStatus` both `ok` while SSH hangs = the VM is alive and the OS is starved (memory, then disk). `impaired` is a dead or hung VM: reboot straight away.
- **Console output:** each `Killed process <pid> (<name>) ... anon-rss:<kB>` names the victim and its resident size. Before 23 Oct it was `swan-sync` and `swan-followup` at 394-514 MB each. The console output is only the latest ~64 KB, so run it soon after an incident.

```bash
m() {  # m METRIC STATISTIC [hours back, default 6]
  aws cloudwatch get-metric-statistics --namespace AWS/EC2 --metric-name "$1" \
    --dimensions Name=InstanceId,Value=$INST --period 300 --statistics "$2" \
    --start-time "$(date -u -d "-${3:-6} hours" +%FT%TZ)" --end-time "$(date -u +%FT%TZ)" \
    --query 'sort_by(Datapoints,&Timestamp)[].[Timestamp,'"$2"']' --output text
}
m CPUUtilization Average; m CPUCreditBalance Average; m CPUSurplusCreditBalance Average
m CPUSurplusCreditsCharged Average; m EBSByteBalance% Minimum; m EBSIOBalance% Minimum
m NetworkIn Average; m StatusCheckFailed Maximum
```

| Metric (5-minute period) | Reading it |
|---|---|
| `CPUUtilization` (Average) | Pinned at the baseline (10% per vCPU on a t3.micro) while credits are 0 = throttled. High with credits left = a runaway job. |
| `CPUCreditBalance` (Average) | **0 on a Standard-mode instance = throttled to baseline.** In Unlimited mode it sits near 0 and the instance borrows instead (next row). |
| `CPUSurplusCreditBalance`, `CPUSurplusCreditsCharged` (Average) | Unlimited mode only. Surplus balance is credits borrowed; `Charged` above 0 is **money** (todo/34 item 7: check it is small after a day on the t3.medium). |
| `EBSByteBalance%`, `EBSIOBalance%` (Minimum) | The instance's disk-bandwidth and IOPS burst. **~0 = spent**, typical when swapping; every disk read then crawls and sshd's banner times out. |
| `NetworkIn` (Average) | A flood would show here. It was normal on 23 Oct. |
| `StatusCheckFailed` (Maximum) | 1 = AWS sees the VM as failed. 0 while SSH hangs points back to starvation. |

**What told us what on 23 Oct.** Status checks passed and `NetworkIn` was normal, so no dead VM and no attack (about 66 failed SSH logins in 3 h is internet background noise). The kernel log showed the OOM kills, and `EBSByteBalance%` reached 0 at 03:00: pytest in `update.sh` plus the timer jobs exhausted a 913 MB box, it swapped, the disk burst ran out, and everything IO-bound (sshd, the dashboard, the alert timers) crawled. The CPU credit balance had hit 0 at about 23:00 (Standard mode), which made it worse. Cause and fixes: [todo/34](../../todo/34-box-robustness.md).

### Fixes, least invasive first

```bash
aws ec2 reboot-instances --instance-ids $INST
```
The bot, Blue and the timers come back from systemd. The tree is whatever commit the box was on, and within about 2 minutes the update timer moves it to `origin/main`. A reboot alone only helped until the load came back on 23 Oct.

If it keeps stalling, resize (about 2 minutes of downtime; the Elastic IP and the credit specification persist):

```bash
aws ec2 stop-instances --instance-ids $INST
aws ec2 wait instance-stopped --instance-ids $INST
aws ec2 modify-instance-attribute --instance-id $INST --instance-type '{"Value":"t3.medium"}'
aws ec2 start-instances --instance-ids $INST
aws ec2 wait instance-running --instance-ids $INST
```

**Confirm afterwards** (ssh in as `ec2-user`):

```bash
cd ~/ctn && git log -1 --oneline            # the commit you expect (the dashboard version box shows the same)
systemctl is-active swan-bot swan-blue swan-dash
free -m                                      # "available" well above 500 MB on the t3.medium
tail -n 400 logs/swan_actions.jsonl | grep -cE '"act": "(reply|reply_back|second_voice|post|thread|repost)"'   # writes among the last 400 actions; with the timestamps, compare with the dashboard's writes/min
```

### What NOT to do

- **Do not run the full test suite on the box**, and do not change `update.sh` to. It runs `deploy/check.sh` with `SKIP_TESTS=1` (compile, import and `--help` checks only); GitHub CI and the laptop run the tests. Pytest on the 913 MB box was the trigger on 23 Oct. Since todo/34 item 6, `update.sh` also checks each new commit in a throwaway worktree (`data/deploy-check`) before it moves the live tree, so a killed run leaves the old commit and the old bot.
- **Do not leave a manual `git reset` / `git pull` on the box without a deploy record.** The dashboard's version box reads `logs/deploys.jsonl` and the `deployed ...` alert, so it stays stale (it showed `65b71c1 02:03` after a manual deploy on 23 Oct). `update.sh` now notices a HEAD with no `ok` record on its next tick (within 2 minutes) and writes a catch-up record plus the alert (`note: "catch-up"`); it restarts the bot only if the commits since the last recorded one changed code and the bot started before the tree moved. If you changed the tree by hand, restart the bot yourself (`sudo systemctl restart swan-bot swan-blue`).
- **A bad commit fails once:** one `DEPLOY FAILED` alert, then it is skipped (`logs/deploy_failed_sha`) until `origin/main` moves. Push the fix; do not reset the box to "make it deploy".

## New persona cards, staged (2026-10-23, todo/36)

Twelve new base cards (`vika`, `tess`, `hari`, `salote`, `dev`, `meiling`, `anaru`, `samir`, `juno`, `colm`, `rhea`, `bernie`) are in `src/swan_bot/playbook/new_cards.py` as `NEW_CARDS`: each entry holds the `content.PERSONAS` card, the `characters.CHARACTERS` profile and the `humanize.HANDS` hand. **They are staged, not live**: none is in `content.PERSONAS`, `characters.CHARACTERS`, `humanize.HANDS` or `voices.VOICE_OF`, so the bot registers none of them. Promotion (and relaxing `len(CHARACTERS) == 20` in `tests/test_characters.py` and `len(keys) == 20` in `tests/test_prompts.py`) is a separate step, with the pool manager. `tests/test_new_cards.py` holds the rules, the mix table and the cross-checks (including that no person's name word is shared with any other card).

## Persona touches (2026-10-23, todo/37), flag OFF

What it is: after each hourly desk run (`scripts/swan_factdesk.py`, after `auto_decide`), `swan_bot/touches.py` takes every active fact added in the last 2 days (`facts.FRESH_S`) that has no stored record, asks the LLM (desk models, gated) which sectors it hits, picks up to 6 personas whose derived sectors meet that, and writes one short clause per voice about how it lands in their week. Every clause passes the authenticity gates (no emotion words, no target, no number but the fact's, no 7-word copy, a second "contradicts the note?" check) or the voice gets nothing. One alert line per fact.

- **Flag:** `config.TOUCHES_ON = False`. Touches are generated and logged with it off (a day of logging before use); `content.system_prompt` ignores them and is byte-for-byte the old prompt. When on, a draft uses one with chance 1/6, 1/4 or 1/3 by impact weight, never twice running on a fact for a persona, at most 3 voices per fact per 6 h team-wide (in-process state), skipped on off-topic drafts; for a fed_up persona it replaces the frame's heat line. The action log gets `meta["touch"] = {fact, sector, weight}`.
- **Files:** `data/touches_auto.json` (the store, `{fact: record}`; the bot re-reads it on mtime change, no restart) and `data/touches_auto.jsonl` (one line per generation with an id, plus `status: "undone"` lines).
- **Undo:** `ssh swan-ec2 'cd ctn && .venv/bin/python scripts/facts_review.py --undo-touches 7'` removes what log id 7 added and prints `{id, status, removed}`. A paused fact drops its touches by itself; `swan_factdesk.py --no-touches` skips the step for one run; `--dry` writes nothing.
- **Read-out after a day (flag still off):** `tail data/touches_auto.jsonl`, read ten clauses across registers (anger only at the rule or the handling, nothing at groups or Yes voters, nothing invented). Then flip the flag and compare hides per 100 writes with and without (`docs/06-strategy/hidden-post-audit-2026-10-23.md`); `grep '"touch"' logs/swan_actions.jsonl` finds the drafts that used one.

## Pattern audit (2026-10-23, [todo/38](../../todo/38-pool-orchestrator.md))
`python scripts/pattern_audit.py` (read-only; `--window-h N`, `--no-write`) writes `data/pattern_audit.json` from `logs/swan_actions.jsonl` and the account records' metadata; the dashboard's Stealth tile reads it (score, worst metrics, worst voices; grey when over 4 h old, absent file = no rows). No timer yet. The thresholds are the `SPECS` table in `src/swan_bot/pattern_audit.py`; what each metric means is in [stealth](../06-strategy/stealth.md). The dashboard's Pool line reads `status.json["pool"]` (schema in `src/swan_dash/build.py` `pool_view`) and is absent until the pool worker writes it.

## Pool scheduler: stealth bought with voices (2026-10-23, [todo/38](../../todo/38-pool-orchestrator.md)), switch ON

What it does: with 16 to 31 voices able to write, `swan_bot/stealth.py` gives each voice a stored **life profile** (`rec["life"]`: sleep window 6 to 9 h, gap multiplier, session length 1 to 4 writes, volume multiplier), picks who writes next by **weighted random** instead of "longest rest first" (the metronome), and runs a **rate controller** (a gap multiplier in 0.6 to 1.0 that tracks 2.9/min from the writes of the last 20 min, in memory). The stealth level **L** (0 to 1) comes from N, the voices able to write: 0 up to 13 voices, 1 from 28, and **always lowered until the awake voices' capacity is at least 1.15 x 2.9 = 3.335 writes/min**. The 4-minute per-voice floor (`ACCOUNT_MIN_GAP_S`) is never shortened. From 24 writers `ONE_VOICE_PER_CITIZEN` is effective by itself (off again under 22); above 20 writers the 'fast' second-voice arm is dropped.

| writers N | L | mean gap awake | awake (planned) | capacity vs 3.335 |
|---|---|---|---|---|
| 16 | 0.20 | 265 s | 14.7 | 1.15 x |
| 24 | 0.73 | 305 s | 17.0 | 1.15 x |
| 31 | 1.00 | 335 s | 18.6 | 1.15 x |
| 13 or fewer | 0 | 240 s (the floor) | all | 1.12 x at 13: out of reach, the floor caps a pool at N/4 a minute |

- **Switch:** `config.POOL_SCHEDULER` (True). `SWAN_POOL_SCHEDULER=0` in `.env` plus `sudo systemctl restart swan-bot` restores the old pick exactly (`ONE_VOICE_AUTO` likewise via `SWAN_ONE_VOICE_AUTO=0`). Dry runs never use it.
- **First restart:** every voice without `life` is given one (from its username, so the same after any restart) and the accounts file is saved once. Sleep windows start to bite as soon as L > 0 (N = 14 or more); the relief step wakes the soonest-waking sleepers if the awake capacity would fall under the need, so a bunched set of windows cannot cost volume.
- **Look at it:** `controller_status()` (`stealth.py`) is the dict for `status.json`: `n_writers`, `level`, `mean_gap_s`, `capacity_ratio`, `mult`, `observed_rate`, `awake`, `asleep`, `relieved`, `empties_5m`, `over_ceiling`, `one_voice_effective`. If the team rate sits under 2.7/min for an hour with `empties_5m` high, voices are the limit: check parked or suspended voices first; the controller already shortens gaps down to the floor.
- **Tests:** `tests/test_pool_scheduler.py` (capacity invariant for N = 9 to 40, life determinism, 24 h simulations at N = 31 / 16 / 13, controller convergence, the off switch). `tests/conftest.py` turns the switch off for every other test; `tests/test_bot_split.py` lists it in `STEALTH_RULES`.

## 2026-10-23: variants of persona cards (`src/swan_bot/variants.py`, todo/38)

A variant is a new account on an existing base card (a live one or one of the 12 staged in `playbook/new_cards.py`): the card's role, place, frames and argument are untouched, the person is not. `make_variant(card_key, records, rng)` is pure (no network, no LLM, no clock; deterministic given the rng) and returns a plain dict for `rec["variant"]`: `name`, `handle` (username base), `shape`, `age` (card +-6, +-3 for the young, no retired voice under 58), `hand` (a `humanize.HANDS`-style dict, each probability moved inside a band around the card's, device within phone/tablet or laptop), `use` (indices of the details, people, lines and events it leans on, a shuffled subset), `swap` (every person in the card and the card's own name -> a new fictional name, applied to all profile text), `style_of` (20%: another card of the same register lends its voice line), `checks` (empty, or why the best of 40 candidates still failed).

- **Reaches prompts only through `bot.persona_of(rec)`**: with `rec["variant"]` it returns `variants.persona(rec)`, a copy of the card (live or staged) with the overlay; the card's profile text is read from `content.PERSONA_BY_KEY` at the time, so Marc's facts and stakes weighting applies to variants unchanged. Records without a variant take the old path untouched (`tests/test_variants.py` pins it against a copy of the old function, plain and converted, for all 20 cards). `humanize.apply` accepts a hand dict as well as a key, so `persona.get("hand", persona["key"])` in `bot.py` is unchanged.
- **Handles**: 10 shapes (`variants.SHAPES`: firstname_job, nickname, initials_word, place_word, hobby_word, bare_name, word_digits, first_last, lastname_initial, adj_noun), charset `[a-z0-9_]` only. The shape differs from the previous registration's and from the suspended account on that card, and is drawn from the least used shapes among the live voices. `username_for(handle, rng, taken)` appends two digits (none for word_digits, whose handle already ends in digits), caps at 32 and never returns a name in `taken`.
- **Distinct** (`distinct(variant, records)` -> `(ok, reasons)`): handle stem and display name at edit distance 3 or more from every record (suspended too) and every card; first name not any live voice's or card's; no name token shared with another live voice's people; hand at least `EPS_HAND` (0.12, summed probability gaps) from the base card's and every live voice's; age not the card's; two or more differences in `use`. Names come from fictional pools (about 450 first names, 360 surnames) minus every persona, profile person, live variant and a deny list (the setting's officials, real public figures); a suspended variant's people names become free again.
- **Not done here (pool worker / other owners)**: `stealth.key_of` still keys sleep windows on the persona, so two live voices of one card would share a window (return the username when `rec.get("variant")`); `Accounts.reserved/by_persona` still assume one voice per card; `batch.py` (only with `--batch`) builds prompts from `content.PERSONA_BY_KEY[...]` directly, so it would draft a variant as its base card until it uses `persona_of`; the register code must pass `display_name=variant["name"]`, store the whole variant on the record before the API call (write-ahead), and the staged cards must be promoted before `Accounts.assignable` can see them. Tests: `tests/test_variants.py`.

## 2026-10-23: pool orchestrator ([todo/38](../../todo/38-pool-orchestrator.md)), SHIPS OFF (`config.POOL_LIVE = False`)

**What it is.** One owner for the voice pool. `src/swan_bot/pool.py` is the pure planning core (records + caps + `now` + a seeded rng in, an action out; no I/O). `src/swan_bot/pool_runner.py` is the executor, run by `bot.py` as the non-critical **`pool`** worker (tick 30 to 60 s, `Worker(critical=False)`, silent limit 15 min). If it dies the bot keeps writing with the pool it has; the watchdog alerts once ("BOT THREAD FAILED (not fatal): pool ... no accounts are added or activated until a restart"). It needs `--live` and the split loop; `POOL_LIVE` is forced off otherwise. It never holds `mu` across a network call.

**Account states (all in `secrets/swan_accounts.json`, one record each).** `pending` (the write-ahead intent: username, password, the whole `variant`, `status: "pending"`, saved BEFORE `register`) -> `warming` (`role: "booster"`, `pool_state: "warming"`, `warm_until`, the variant's `base` card held in reserve; the existing booster routines give it views and likes) -> activated as a voice (`role: "voice"`, `persona` = the card, `pool_state: "active"`, `ramp: {from, until, start}`) -> `suspended` (by the platform; `suspended_at` is now stamped where the bot learns it). A converted booster skips `pending` and `warming` (`converted.by == "pool"`, `converted.at`). A registration that never happened is kept as `status: "failed"` with `failed_reason` (password removed); it is not a used account. `ramp`: `Accounts.ramp_ok` makes a ramping voice ready with a chance rising linearly from 0.25 to 1 over its ramp (36 to 72 h by state), in `eligible()` and `assignable()`.

**Cards.** One ACTIVE account per persona card (the code assumes it). A card is *free* when no active voice holds it and no warming account has it reserved; a suspended holder frees its card. Only `content.PERSONAS` (20 live cards) are ever given out; the 12 staged cards are not promoted. **Today 14 voices hold 14 cards, so 6 are free: the pool can convert 5 boosters (Blue's reporter is never converted) and register 1, then it has no free card.** That state is expected: it logs one `pool_error` (`why: no_free_card`), sends one alert, and waits (it re-arms when a card is free). The writer target of 31 needs 31 cards (promotion, todo/36), or suspensions to free some.

**Control law** (numbers are `config.POOL_*`; `supply` = voices (writers + ramping) + warming; `W*` = `POOL_WRITERS` 31; `P` = `POOL_PIPELINE` 4):

| state | supply | floor between ANY two actions | next add (register or convert): median, sigma 0.7 | warm-up | ramp |
|---|---|---|---|---|---|
| healthy | `>= W*` | 15 min | 5 h at no deficit (one replacement per loss, counted from when the want arose) | 6 to 36 h | 60 to 72 h |
| sagging | `< W*` | 15 min | log-linear in the deficit `d = (W* - supply) / W*`: 45 min at d = 0.1, 15 min at d = 0.3 | 3 to 12 h | 48 to 60 h |
| low | `< 0.7 W*` | 8 min | 8 min at d = 1 (the floor binds) | 1 to 4 h | 36 to 48 h |

Order inside one tick: (1) ACTIVATE a warmed account while voices < `W*` (needs a free card: its own reserved one, else another); (2) once the paced delay has passed and the state is not healthy, CONVERT a booster (no registration spent) before registering; (3) REGISTER a warming account while `supply < W* + P`, `alive + 1 <= 49` (`MAX_ACTIVE`, swarm and Blue's reporter counted), `total + 1 <= 200`, a card is free. One action per tick, never two closer than the floor; "when low" for the warm-up and ramp hours also counts the writers alone under `POOL_FAST_FRAC` (0.85 of `W*`), because warming accounts do not write yet. The delay is `median(d) * exp(sigma z)`, one draw `z` per action, clipped to [floor, 18 h], so for a fixed draw it only ever shrinks as the deficit grows. Errors: a **429** waits its Retry-After (register only; conversion and activation are local); a **403 whose message says total (and not active)** is terminal (log once, alert once, no more registering, conversions go on); any other 403 waits 30 min (1 h when it mentions total), other refusals back off 2, 4, 8 .. 30 min and alert once after 5 in a row; a dropped connection leaves the record `pending` for the reconcile. Runway: `loss_per_day` = EWMA (half-life 24 h) of suspensions in the last 72 h (timestamps: `suspended_at`, else the actions log `suspended` rows read once at start), `runway_days = spare_total / max(loss_per_day, 0.5)` against `days_left` to **3 Nov 00:00 Sydney** (`POOL_END`); under it: one alert and one `pool_error` row (`why: runway`), re-armed above 1.2 x days left. It never raises volume to compensate.

**Switches.**

| switch | effect |
|---|---|
| `config.POOL_LIVE` (default False); `SWAN_POOL_LIVE=1` in `.env` + `sudo systemctl restart swan-bot` | live: the worker registers, converts and activates, and is the ONLY registrar: `Accounts.maybe_register` and the `--boosters N` top-up (`Amplifier.maybe_register_booster`) return at once; `scripts/convert_boosters.py` refuses to run |
| `POOL_LIVE` False (default) | **shadow**: the worker plans every tick on a private, secret-free copy of the records and logs `pool_shadow` rows of what it WOULD do, applying them to the copy so the plan evolves (warm-ups elapse, warmed accounts activate). Nothing is registered, converted, saved or called; the old registrars run exactly as before |
| `touch ~/ctn/POOL_OFF` (`rm` to resume) | stop, no restart: from the next tick (and re-checked right before every register) nothing is planned or done; the old registrars stay down while `POOL_LIVE` is on. `status["pool"]["dry_run"]` shows true |
| `SWAN_POOL_WRITERS`, `SWAN_POOL_PIPELINE` (`.env`) | the target `W*` and the pipeline `P` |

**Reading the log (`logs/swan_actions.jsonl`).** Every pool row has `by: "pool"` and `owner` (`config.operator()`); actions have `reason`. `pool_shadow`: `would` (register|convert|activate), `reason`, `state`, `card`, `supply`, `target`, `writers`, `warming`, `alive`, `total_used`, and `username`/`name`/`handle`/`shape`/`warm_h` (register) or `username`/`ramp_h` (convert, activate), `checks` when the variant failed `distinct()` after 3 tries. Live: `pool_register` with `phase: "intent"` (record saved, API not yet called) then `phase: "done"` (`account_id`; `reconciled: true` when a login finished it after a crash); `pool_convert`, `pool_activate`; `pool_error` with `why` = `register_failed` (status and message, no secret), `register_unknown` (connection dropped: reconcile decides), `no_free_card`, `runway`, or a tick exception. No password, token or team code is ever logged. Look: `grep -E '"act": "pool_' logs/swan_actions.jsonl | tail -20`; the dashboard's **Pool** line (from `status.json["pool"]`: `dry_run, state, writers_target, writers, ramping, warming, alive, alive_cap, total_used, total_cap, spare_total, loss_per_day, runway_days, days_left, next_add_in_min, last_actions`; `next_add_in_min` is null when nothing can be added). Pending records: `python3 -c "import json;print([ (r['username'],r['status']) for r in json.load(open('secrets/swan_accounts.json')) if r.get('status') in ('pending','failed')])"` (no secrets printed).

**Crash safety.** A tick takes `mu`, checks the caps, writes the whole record as `pending`, saves, releases; calls `register` with no lock; takes `mu`, fills token and id, sets `active`, saves. On every tick with `POOL_LIVE` on, ONE pending record is reconciled by `login` (retry every 60 s): found -> finished (`reconciled`), suspended -> marked, 401/404 -> `failed`, but only once the record is 2 min old (a late server answer may still be coming). So a crash anywhere leaves a finishable record, never an orphan and never a second registration of the same username. If you roll back to `POOL_LIVE` False with a `pending` record on disk, switch it on briefly (or log in by hand) so it is reconciled.

**GO-LIVE CHECKLIST (Marc).**
1. Deploy with the default (`POOL_LIVE` False). `journalctl -u swan-bot | grep "pool orchestrator"` must say `shadow / dry run`. `systemctl list-timers | grep swan-audit` (install.sh adds `swan-audit.timer`, every 30 min, Nice 19; `sudo deploy/install.sh --units-only` if the updater did not).
2. Let it run in shadow for at least 24 h and check: (a) `grep -c '"pool_shadow"' logs/swan_actions.jsonl` is not zero and not a flood (low state: one row per 8 to 40 min at most); (b) the first rows are `would: convert` with `reason` "low: ..." (5 of them, spaced at least 8 min), then one `register` at most, then ONE `pool_error` `no_free_card`; (c) no `pool_error` with any other `why`, no `thread_died` for `pool`; (d) the dashboard shows "Pool low . dry run" with `writers 14/31`; (e) the bot's write rate is unchanged (2.8 to 2.9/min) and `status.json` threads include `pool` with a small `age_s`; (f) read the `name`/`handle`/`shape` of the shadow registers: ordinary locals, shapes vary, none repeated back to back.
3. Decide the cards: with 6 free cards the live pool will convert 5 boosters and register 1, then wait. Promote the staged cards first (todo/36, Marc's facts work) if you want the 31 writers.
4. On the box: `cp secrets/swan_accounts.json secrets/swan_accounts.before-pool.json` (a backup that can be restored with the bot stopped).
5. Put `SWAN_POOL_LIVE=1` in `.env` on the box, `sudo systemctl restart swan-bot`. Within a few minutes `pool orchestrator: LIVE` is printed and `Accounts.maybe_register` is silent (no more `act: "register"` rows). The first action comes no sooner than the paced delay after the restart (8 to 40 min).
6. For the first 2 h watch: each `pool_convert` row (the account keeps its username), the voices' first writes (ramping voices write about a quarter as often at first), `alive` never above 49, no `pool_error`. The first `pool_register` pair (`intent`, `done`) must be seconds apart and the account must show in `secrets/swan_accounts.json` as `warming`.
7. To stop at any time: `touch ~/ctn/POOL_OFF`. To go back to the old drip registrar: remove the `.env` line and restart.

**Limits and what is not verified.** Everything above is tested against fakes with sockets blocked (`tests/test_pool.py`, 54 tests including a 10-day simulation); **no real registration, conversion or login has been made by this code**, so the real API's wording of the 403s (total vs active cap), the effect of conversions on Blue (the reporter is excluded by `config.blue_reporter`), and whether the platform treats a burst of new accounts as suspicious are unverified. A converted booster keeps its display name, so its variant's name is the booster's (`pool.adopt_identity`); its profile text (people, details) still comes from the variant. `--batch` drafting (not used live) builds prompts from the base card, not the variant. The pool cannot make losses cheap: at 38 losses a day the 137 spare accounts last under 4 days (the runway alert fires; content is the lever).

## 2026-10-24: account budget, forecast and reserve alert ([todo/39](../../todo/39-account-budget-multiplier.md))

**What it is.** A forecast and an alert, nothing more: it never throttles writes and never blocks the pool. `src/swan_bot/budget.py` (pure) turns a plan of writes per Sydney day into forecast bans, alive and spare registrations; `watch.budget_run` runs it inside the 20-minute `swan-watch` job (`scripts/swan_watch.py`; `--budget-only --dry` runs just this, from local files, no network, prints and sends nothing). State and the last forecast: `data/swan_budget.json` (`last.days` is the table the dashboard, todo/42, reads); one `act: "budget"` row per run in `logs/swan_watch.jsonl`. A missing portal file, accounts file or log gives no alert (a quiet line in the unit's output).

**Where Marc edits.** `config.BAN_PLAN` (writes planned per Sydney day, `"YYYY-MM-DD": n`; a day left out takes the last given day's value), `RESERVE_GOAL` (60), `RESERVE_DAY` (`"2026-10-31"`, spare counted at the END of that Sydney day), `WRITES_PER_BAN_DEFAULT` (145), `BUDGET_END_DAY` (`"2026-11-02"`). The Sydney day rolls at midnight Sydney (AEDT, UTC+11 from 4 Oct) = 9pm Perth = 13:00 UTC. Today's plan is cut to the part of the day left, because the bans so far are already out of the counts.

**What it assumes (24 Oct).** 127 spare registrations (portal: 73 registered, 25 banned, 200 allowed), 48 alive; about 2,400 text writes a day (x4 days 1-2 Nov at the 4,320 cap); a voice dies at 145 text writes (Kaplan-Meier median, bootstrap 127-178, [hide-risk-analysis](../06-strategy/hide-risk-analysis-2026-10-23.md)); one spare registration replaces each ban while spare lasts; a reserve of 60 on 31 Oct (2 x 4,320 / 145). The job measures writes per ban itself (text writes from `logs/swan_actions.jsonl`: post, reply, reply_back, second_voice, journalist, thread, thread_answer; not likes or reposts; a ban from the portal's `account_log.suspended`, else the account records) and uses the measured median once 10 bans are in, else 145. **With these numbers the plan is already off track:** 16.6 bans a day takes the 127 to about 4 on 31 Oct (at the observed 12 a day it would be about 31); the alert will fire on its first run.

**Reading the alert.** (1) "Account reserve is off track: forecast N spare registrations on 31 Oct against the goal of 60 (M short)": at the planned writes, the pool will not have 60 registrations left for the x4 days. (2) "Bans are running over forecast: N accounts banned in the last 24 h against F forecast": at least 4 and more than 1.5 x the forecast (a whole day's plan / writes per ban); the spare count is falling faster than the plan. Each message ends with the writes per ban used (`measured` or `default`) and the current alive and spare. The same alert (numbers aside) is sent at most once per 6 h (`BUDGET_ALERT_GAP_S`); to see what would go out now: `python scripts/swan_watch.py --budget-only --dry`.

**The throttle lever is Marc's, by hand.** Cut the plan's cheapest days first (24-25 Oct, x1) and keep 26-31 Oct (x2) and 1-2 Nov (x4). Ways to cut writes (none of them is done by this code). **Only (a) is a real throttle.** Checked 24 Oct: the team is writing about 1.7 a minute (2,400 a day), well under `--per-min 2.9` and `POOL_TARGET_RATE` 2.9, so those two are ceilings that nothing is pressing on; the limit today is how many voices can write. (a) `SWAN_VOICE_DAY_CAP=1` and `SWAN_VOICE_WRITES_PER_DAY=N` in `.env` + `sudo systemctl restart swan-bot` (a hard cap of N per voice per rolling 24 h, so about N x the writers a day; the cap is off by default, so the number alone does nothing). (b) `--per-min` in `deploy/run.sh` or `POOL_TARGET_RATE` only bite if set below the current rate (about 1.7); both need a deploy. (c) `POOL_WRITERS` / `SWAN_POOL_WRITERS` changes how many voices the pool holds; with `POOL_SCHEDULER` on, fewer writers may each write more, so it is not a reliable cut. After a cut, lower `BAN_PLAN` to match so the forecast follows. Boosters registered early are not suspended while they wait (todo/39 item 4): that is a decision for Marc, not code.

**Order of conversion.** Once `POOL_LIVE` is on, the pool converts boosters in random order (`pool.py`: `rng.choice(snap["convertible"])`), not by id; there is nothing to build, and do not convert the 20 Oct boosters by hand in id order.

**Unverified.** The 2,400 planned writes a day are the team's total writes as the dashboard counts them, and may include reposts that the 145-per-ban figure does not; the Kaplan-Meier median covers the whole run, not the last 72 h, so it will lag todo/40's hide-rate changes; the portal's ban names and counts disagree for a while after each ban (the counts move first and are used for the 24 h number).

## 2026-10-24: hide-rate changes ([todo/40](../../todo/40-hide-rate-changes.md))

Why and the numbers: [hide-risk-analysis-2026-10-23](../06-strategy/hide-risk-analysis-2026-10-23.md) and [research-2026-10-23/](../06-strategy/research-2026-10-23/) (not repeated here). Each change is a flag in `config.py` with a `SWAN_<NAME>` override in `.env` (`STEALTH_ENV`), read at the next `sudo systemctl restart swan-bot`; `swan_watch.py` reads `.env` on each run. The bot prints every flag's value on start (`todo/31 stealth: ...`). All are ON by default, so a deploy turns all of them on at once; to read 1 and 2 first (todo/40 says 3 a day later), put `SWAN_POST_EVERY_N=4` and `SWAN_POST_NO_TAG_WITH_VOTE=0` in `.env` for the first day.

| # | flag (default) | what it does | turn off |
|---|---|---|---|
| 1 | `NEW_VOICE_NO_POST_H` (24) | A voice in its first 24 h of voice life writes replies only: no persona post, amplified post or thread reply (reposts, replies, reply-backs, second voices and journalist replies go on). Age starts at `converted.at`, else the pool's activate note / `ramp.from`, else `created`; a record with none of them is old. `Accounts.young()` is excluded where the writer picks a voice for a post (`bot.py` next to `POST_EVERY_N`), `Amplifier.pick_author` and the thread branch of `next_write_job` | `SWAN_NEW_VOICE_NO_POST_H=0` |
| 2 | `REPLY_VOTE_SHARE` (0.0, was 0.15) | "I'm voting No" is rejected in replies, reply-backs and second voices (the kinds the phrase budget covers); `quality.drop_vote` cuts it with no LLM call. Posts and threads are not budgeted and a post must still say No. The `agree_close` conversion arm (off while `arm_conv` has no switchback) cannot close on the vote while this is 0 | `SWAN_REPLY_VOTE_SHARE=0.15` |
| 3 | `POST_EVERY_N` (8, was 4); `POST_NO_TAG_WITH_VOTE` (True) | At most 1 persona post in 8 writes. A post no longer carries a hashtag with its "I'm voting No": the prompt asks for none (`meta["tag"]` is null), and a draft that adds one has it cut by a code fix (`tag_with_vote`) | `SWAN_POST_EVERY_N=4`, `SWAN_POST_NO_TAG_WITH_VOTE=0` |
| 4 | `PORTAL_SYNC` (True), `PORTAL_SYNC_S` (120), `PORTAL_MAX_AGE_S` (3600) | Every 2 min the writer reads `data/portal.json` (the dashboard poller's file; no network) and marks an active voice or booster suspended when `account_log.suspended` names its username AND account id. `suspended_at` is the portal's time; the log row is `act: suspended` with `via: portal`, `portal_ts`, `why`. A missing, malformed or stale file (its own `ts` older than 1 h) marks nothing | `SWAN_PORTAL_SYNC=0` |
| 5 | `WATCH_TAIL_S` (14400) | `swan_watch.py` keeps checking a voice that is no longer active for 4 h after its last write; those hides are logged with `after_suspension: true` and not alerted. New fields on every `hidden_post` row: `write_id` (the draft id), `write_act`, `write_ts`, `write_age_h`, `backend`, `length`, `arms` (`sv_delay`, `arm_conv`, ...), `voice_age_h` (at the write), `card` (persona, role, place, age, handle shape, `origin` original/converted/activated, `card_of`, `card_reuse`), `hides_before`, `since_prev_hide_h`, `portal` (time, reason, when already listed). New `suspension` row, once per account: the portal's time and reason, `hide_ts`, `since_last_hide_h`, `last_write_to_suspension_h`, `card`. State gets `hidden_at` and `suspended_seen`; nothing is removed | `SWAN_WATCH_TAIL_S=0` (the new fields stay) |
| 6 | `SV_DELAY_PER_VOICE_DAY` (True) | The `sv_delay` arm of a first reply's second voice is fixed per replying voice and Sydney day (sha256 of voice + day; about half of the voice-days each, the same after a restart). Logged as `sv_delay` on the reply, the second voice and, in `arms`, the hide. Only while the fast arm exists: above `SECOND_FAST_MAX_N` (20) writers every voice-day is slow | `SWAN_SV_DELAY_PER_VOICE_DAY=0` (back to strict turns) |

**How to read it.** Hide rate = hidden text posts / text writes, counting only writes at least 3.6 h old (a hide is ruled about 3 h after the write; `write_age_h` on the hide, `ts` on the action row). Text writes are the `post`, `reply`, `reply_back`, `second_voice`, `journalist`, `thread` and `thread_answer` rows with `live: true` in `logs/swan_actions.jsonl`; likes and reposts are not. Hides are the `hidden_post` rows of `logs/swan_watch.jsonl`, dedup by `post_id`. Split by the deploy time (the change is in effect from the first write after the restart), by `write_act` and `voice_age_h` for 1, by vote statements in reply texts for 2, by `write_act == post` for 3, and by `arms.sv_delay` against the `sv_delay` of the second-voice rows for 6 (the earlier read-out counted second voices only, `scripts/conversion_report.py`). Expect ~30 to 40 hides in 3,000 writes: the interval stays wide, and the baseline is about 1.4% since rivals began reporting on 21 Oct (about 1.0% at best). Items 4 and 5 do not move the rate: 4 frees a slot sooner and avoids one wasted write; 5 is for the next analysis. Tests: `tests/test_new_voice.py`, `test_fingerprint.py`, `test_post_tag_vote.py`, `test_portal_sync.py`, `test_hide_log.py`, `test_sv_split.py`.

**Unverified on the live platform:** whether `account_posts` of a suspended account lists its posts (the tail only trusts a voice whose list shows at least one logged post); whether the portal's suspension time is UTC as the poller assumes; whether the new-voice gate changes anything for original voices (they are old by now).

## 2026-10-24: stealth as rates, and the bans forecast on the dashboard ([todo/42](../../todo/42-dashboard-stealth-forecast.md), [todo/39](../../todo/39-account-budget-multiplier.md))
Code: `src/swan_dash/build.py` (`stealth_rates`, `ban_forecast`, `ban_figures`, `life_scan`, `gap_trend`), `portal.py` (`append_leaderboard`); tests `tests/test_dash_stealth.py`, `tests/test_portal.py`; the maths is `src/swan_bot/budget.py` (pure; tests pin it to `tests/_budget_stub.py`).
- **One bans number.** The Bot header, the Accounts line and the Stealth tile all show the newest `account_log.counts` row (it moves before the moderator's messages), with the lag to the names: "25 banned (list shows 21)". With no counts rows (old `portal.json`) it falls back to the team-page table and shows no lag.
- **Hide rate** (Stealth tile) = hidden text posts / text writes (reply, 2nd reply, 2nd voice, post, thread, thread answer, journalist; not reposts) among live writes made 24 h to 3.6 h ago, with a 95% Wilson interval. Hidden posts come from `logs/swan_watch.jsonl` (`hidden_post` rows) and `logs/alerts.log` ("post #N hidden by the moderator"). Green when the whole interval is under the target (`HIDE_TARGET` 1.4%; set `config.HIDE_RATE_TARGET = 0.010` after todo/40), red when over, amber when it straddles, grey under 300 writes. The row "Posts hidden today" (a count) still never colours the tile.
- **Writes per ban** = `budget.km_writes_per_ban` over voices banned in the last 72 h plus voices still alive and writing (censored), counting each voice's lifetime text writes. Below 5 bans the forecast uses `config.WRITES_PER_BAN_DEFAULT`. **Runway** = spare registrations / (planned writes today / writes per ban), in days, next to the days left to `config.BUDGET_END_DAY`. Both rows, "Hides before a ban" and "Bans against the plan" are grey: the account-budget alarm is the Pool line and the alert, not the tile colour.
- **Bot > Accounts by day** now opens on one line ("bans today 7 · forecast 12 · net −5 · spare 127 · on track for 31 Oct: +8"); the ⋮ control opens the table, 19 Oct (first day on the portal) to 2 Nov: ×1, ×2 (from 26 Oct) and ×4 (from 1 Nov) days, planned writes, forecast bans, actual, net with its tolerance (1.5 standard deviations of the forecast, at least 2), alive and spare at the end of the day (actual to yesterday, forecast from today), and the difference to the reserve goal on `config.RESERVE_DAY`. Today's net compares the bans so far with the forecast for the part of the Sydney day gone. Edit the plan in `config.BAN_PLAN` (one number per Sydney day); a day without one takes its actual writes (if over) or the last 3 complete days' average. `budget.ban_alert` lines show under the table.
- **Leaderboard series.** The portal poll (every 15 min) appends one line an hour to `data/leaderboard.jsonl` (`ts, rank, score, first, third, teams`; last 14 days kept, atomic, through `checked()`, nothing when we are not on the board). Under the leaderboard the dashboard shows the gap to 3rd and whether it closed or widened over 6 h and 24 h, with what each side scored. It says "history building" until a line exists near enough to 6 h / 24 h back.
- **Cost.** `life_scan` streams `logs/swan_actions.jsonl` once a minute and parses only write and suspension rows (0.26 s for a 137 MB synthetic file with 660k lines).
- **Not verified live:** every number above has only been run on synthetic logs; after the deploy, check the first page against the portal (the bans number) and against `data/swan_watch.json` (hidden posts in the rate).
