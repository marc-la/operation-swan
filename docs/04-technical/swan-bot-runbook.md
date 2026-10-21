# swan_bot runbook (written 2026-10-20)

Code: `src/swan_bot/`. Strategy behind it: [06-strategy](../06-strategy/README.md). **Dry run by default**: nothing is registered or posted without `--live`.

## What it does (updated 2026-10-20)

Plan behind it: [second-mover-plan](../06-strategy/second-mover-plan.md).

- **One process does all our writing.** It's capped by `--per-min` (default 1.0, hard max 2), but the real pace follows the target queue. If nothing is worth writing, it waits.
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
  - replies that don't name the citizen's point or an in-world fact; posts without a local detail;
  - text copied from the fact list, parroting the citizen, near-duplicates.
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
  | **drafter** | `pulse.update`, then `choose()` (the greedy order: reply-backs, citizens, amplifier jobs, second voices, journalists, posts) and `draft()` (prompt, LLM, gate, light read). A failed draft is requeued or logged lost here (G8). It waits when `DRAFT_AHEAD` (2) drafts are already waiting. | `data/llm_usage.json`, `data/llm_spend.json` (`llm.py`: the bot's only LLM caller; the hourly swan-factdesk process writes them too, as before) |
  | **writer** (main thread) | registration, `own_likes`, `amp.tick`, `write_status`, then `send()`: the send-time checks, the write, the bookkeeping. **The only thread that writes to Legit Social.** Pacing is unchanged: `next_write` from `pace_gap(per_min)`, a pause when `X-RateLimit-Remaining` is 0, and the Retry-After on a 429. | `data/swan_state.json`, `secrets/swan_accounts.json`, `data/status.json` |

- **Queues between them:**
  - targeter candidates (reader → drafter, `targeting.Targeter`);
  - the reply-back queue `queue` (reader → drafter);
  - `ready`, the checked drafts (drafter → writer, at most `DRAFT_AHEAD`). The writer sends the first one whose voice may write now (`voice_wait`: 4 min, a reply-back 60 s, a repost 60 s).
  - Drafts not yet sent count as written when the drafter chooses (`held()`). Their voices are reserved (`Accounts.reserved`), and their modes count for the post and journalist limits. Their texts count for the near-duplicate check.
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
  - the writer checks each thread every round. If one died or went silent (`READER_SILENT_S` 20 min, `DRAFTER_SILENT_S` 30 min), it logs `thread_died`, alerts (`BOT THREAD DIED`, via `deploy/alert.sh`), saves and exits 1, so systemd restarts it;
  - SIGINT/SIGTERM set a stop flag. Each thread finishes its step (never mid-send), drafts not sent go back (a reply-back to the saved queue, a citizen to the targeter as `held`), then the state is saved and the bot exits 0;
  - `status.json` gains `loop`, `threads.{reader,drafter,writer}.{last_run, age_s, max_silent_s}`, `queue.{reply_backs, candidates, drafts_ready}`, `oldest_waiting_s` (since the citizen wrote it) and `oldest_queued_s` (since it entered our queue, deliberate waits and todo/23 groups left out).
- **Rollback:** set `SPLIT_LOOP = False` in `config.py` and push. The bot restarts within about 2 min on the old serial loop (same steps, one thread, Ctrl-C raises as before).
- **Invariants and their tests** (`tests/test_bot_split.py`). These are end-to-end runs of `main()` against a fake Legit Social with sockets blocked, in both loops:
  - every job type and every background duty still runs;
  - only the main thread writes;
  - writes are never closer than `pace_gap`, and a 429 waits;
  - the voice gaps hold;
  - no target is answered twice;
  - each state file has one writer, and no `.tmp` files are left;
  - the watchdog fires on an injected reader or drafter failure;
  - SIGTERM stops cleanly with every write recorded.

## Hosting

**Since 2026-10-20 the bot runs on EC2 under systemd, with auto-deploy from `main`. See [hosting](hosting.md).** Don't run `--live` anywhere else. The laptop/tmux instructions are retired.
