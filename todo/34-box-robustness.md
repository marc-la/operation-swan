# 34: Box robustness. The bot must not stall, starve or go dark again, and we must hear about it off the box

**Written 2026-10-23 by Claude at Marc's request, after a ~2 h degradation (writes ~0.4/min against 2.9/min).
Owner: whoever picks it up. Priority: high, before the ×2 multiplier on 26 Oct.**

Everything on the team's side runs on one EC2 box (`swan-ec2`, ap-southeast-2, `i-06471b75b0166b3c7`, Elastic IP
13.210.120.238): the bot, Blue, the dashboard, the fact desk, the Mongo sync, the update timer. When it stalls, the
dashboard and the alerts stall with it. This item makes each failure below impossible or loud.

## What happened (UTC, 22-23 Oct)

| time | event |
|---|---|
| ~23:00 | CPU credit balance hits 0. The instance was in **Standard** credit mode (Marc switched it to Unlimited ~02:10), so the CPU was held to the t3.micro baseline of 10% per vCPU. |
| ~23:19 | LLM allowance for the day is gone (`LLM_BUDGET_USD` 85 on the box: $10.20 through 23 Oct, $9.35 spent). Only the amplified-post reserve is left, so paid models are skipped, every free model is parked on daily quota, and **drafts find no model**. `next_available_in()` stays 0 (the paid models are skipped, not parked), so the drafter retries at once: **27,858 jobs dropped as `no_model` in 3 h** (10,782 in one 10-minute window). Replies stop; reposts carry on. |
| 23:41, 01:46 | The reader thread dies on one dropped connection (`RemoteDisconnected`, then `SSLEOFError`). The watchdog exits the whole bot; systemd restarts it (01:01 and 01:49 too). The client library retries only 429s. |
| 00:00-01:43 | The kernel OOM-kills `swan-sync` and `swan-followup` (394-514 MB resident each) on a 913 MB box that also holds the bot. |
| 01:58, 02:41 | Each push triggers `update.sh`, which ran the full pytest suite **on the box**. Available memory fell 463 -> 5 MB in about a minute, SSH and the site stopped answering. |
| 03:00 | CloudWatch `EBSByteBalance%` is 0: swapping used up the t3.micro's disk-bandwidth burst. Every disk read crawls, so sshd accepts the TCP connection and never sends a banner. A reboot only helped until the load returned. |
| 03:03 | Resized to **t3.medium** (4 GB, 347 Mbps EBS baseline); Unlimited kept; same IP. Fine since. |

Not the cause: no attack (network-in normal; ~66 failed SSH logins in 3 h is internet noise), no hung VM (status
checks passed), no shortage of targets.

## Already fixed (commits on main)

- `5e19bde` `Worker` rides out transient network errors (`URLError`, `SSLError`, timeouts); 8 in a row still hands over to the watchdog.
- `3a3ab87` `LLM_BUDGET_USD` 85 -> 170; a draft that finds no model pauses drafting `NO_MODEL_PAUSE_S` (60 s). Test: pause 0 gives 6,445 drops in 12 s.
- `5736a75` dashboard **Drafting** banner (amber: drops, paid models held back, budget under 2x the reserve; red: drops with writes under 1/min, or budget spent).
- `a96b486` `update.sh` runs `check.sh` with `SKIP_TESTS=1`: compile, import and `--help` checks only. CI and the laptop run the tests.
- Box resized to t3.medium (not in git: AWS console / API).

## To do (in this order)

**Status 2026-10-23 (evening):**
- Item 2: done in code, not yet on the box. `src/swan_bot/jsonl.py` (streaming reader with a resumable cursor);
  `scripts/swan_sync_mongo.py` is incremental (cursors in `data/swan_sync_cursors.json`, `--full` resyncs, chunks of
  1,000); `followup.load_rows` and `scripts/swan_watch.py` stream; `swan_measure`, `swan_view` and `experiment_report
  --local` too. Peak RSS on a 650k-line, 149 MB fixture: followup 993 -> 189 MB, sync 1,287 -> 73 MB, watch 993 -> 79 MB
  (66 MB of each is the interpreter and imports). Still to do: rotate and compress the log.
- Item 3: partly done. `OOMScoreAdjust=-500` on `swan-bot`; `MemoryMax=` on `swan-sync` (300M), `swan-followup` (600M),
  `swan-watch` (300M), each at 3x or more of the measured peak. Left without limits for lack of peak data: `swan-dash`,
  `swan-factdesk`, `swan-swarm`, `swan-blue`. Re-measure on the t3.medium (`systemd-cgtop`, `MemoryPeak` in
  `systemctl show`) and tighten.
- Item 4: done (dee1ff6, the lead): the writer path rides out network errors.
- Other whole-file reads left alone: `scripts/conversion_report.py` (manual), `swan_dash.build.tail_lines` on
  `logs/alerts.log` (slow growth), `swan_lab` (retired).

1. **Hear about it off the box.** The dashboard and `alert.sh` live on the box, so a stall silences them. Add: (a) a
   dead-man ping, `HEALTHCHECK_PING_URL` in `.env` is already read by `deploy/healthcheck.sh`; (b) CloudWatch alarms to
   an SNS email or the Discord webhook on `StatusCheckFailed`, `EBSByteBalance%` < 20, `CPUSurplusCreditsCharged` > 0
   (money), memory (needs the CloudWatch agent, or a `MemAvailable` line in `healthcheck.sh`); (c) a push alert once per
   episode when `no_model` drops pass ~20 in 10 min (the dashboard banner is only seen when someone looks). Check what
   the IAM user (`.env`: `EC2_ACCESS_KEY`) is allowed; CloudWatch alarms and SNS may need more permissions.
2. **Stop `swan-sync` loading the whole log.** `scripts/swan_sync_mongo.py:50` does `path.read_text().splitlines()`
   on `logs/swan_actions.jsonl` (118 MB, 656k lines on 23 Oct) every 15 min: that is the 400-500 MB. Stream it and keep a
   byte offset in `data/`. It already copies to the team Mongo; the bot should keep the local JSONL as its source of
   truth, so this is not a move to Mongo, it is making the copy incremental. Look at `swan-followup` (514 MB) too.
   Then rotate and compress the log (the `lost` spam added ~30k lines in 3 h).
3. **Make memory pressure kill the right thing.** No unit has limits. Give the timer jobs (`swan-sync`, `swan-followup`,
   `swan-factdesk`, `swan-swarm`, `swan-dash`) `MemoryMax=` (e.g. 600M) and `swan-bot` `OOMScoreAdjust=-500`, so a
   runaway job dies instead of the bot or sshd. Keep the 1 GB swap. Re-measure peak memory per unit on the t3.medium.
4. **Audit the writer path for network errors.** `LOOP_ERRORS = (ctn.APIError, openai.APIError, AllPaused)` does not
   include `urllib.error.URLError`/`SSLError`. `Worker` now covers the reader and drafter threads; the writer runs in the
   main thread. Check that one dropped connection on a send, a like or a follow cannot reach `main()` and exit the bot
   (and does not double-send). Add a test like `test_worker_rides_out_a_transient_network_error`.
5. **Never starve the drafter silently.** Decide: should replies be allowed to spend the amplified-post reserve when no
   free model is available (a last resort, instead of dropping the citizen)? `qwen-plus-character` now returns 403
   "free quota exhausted", which contradicts the config comment (1M tokens to 2027-01-20): fix the comment and the chain.
   Marc's uncommitted Haiku change (`REPLY_MODELS`, `HAIKU` price) is a candidate floor. Watch the daily allowance
   (`llm.allowance`): $11 left on 23 Oct after the 170 bump, a daily share of $6.80 from 24 Oct.
6. **Make `update.sh` safe to interrupt.** It runs `git reset --hard` to the new commit *before* `check.sh`, so a killed
   run leaves the tree on the new commit with the bot not restarted, and no `deployed` record (the dashboard's version box
   reads that alert, so it stayed on `65b71c1 02:03` after our manual deploy). Check in a separate worktree, or restart
   in the same step; write the deploy record whichever way the box got there.
7. **Keep Unlimited on and watch the surplus.** Credit balance was 0 and the surplus balance ~43 at 03:00. The t3.medium
   earns twice the credits; confirm `CPUSurplusCreditsCharged` is small after a day. Standard mode would throttle again.
8. **Runbook.** Add "diagnosing without SSH" to [swan-bot-runbook](../docs/04-technical/swan-bot-runbook.md): the IAM key
   in `.env` (`EC2_ACCESS_KEY`, `EC2_SECRET_ACCESS_KEY`, region ap-southeast-2; never print them), `aws ec2
   get-console-output --latest` (OOM kills), CloudWatch `EBSByteBalance%`, `CPUCreditBalance`, `CPUSurplusCreditBalance`,
   `NetworkIn`, then reboot, or stop, `modify-instance-attribute --instance-type`, start. The Elastic IP survives.

## Done when

A forced `no_model` episode, a dropped connection and a 1.5 GB memory spike each leave the bot writing within 2
minutes (or alert us within 10), and the dashboard still tells us from off the box when the box itself is down.
