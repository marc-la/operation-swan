# 58 — Speed: choose the target at the slot, not a slot ahead (todo/53 P5)

Written Sat 31 Oct 2026, ~02:30 Perth (30 Oct 18:30 UTC), by Claude for Marc. **Status: shipped (Marc approved, Claude built).** Step 1: f6c6222, live 30 Oct 23:49 UTC. The mid-send fix and step 2: 4363550, live 31 Oct 00:15 UTC. The live checks are in §6.
**Priority 1 of the 31 Oct designs:** the largest engagement lever found. It changes how the pipeline is timed, not what
we say, so it is not a switchback arm. It needs code and a test: aim to have it live by about 01:00-02:00 UTC
(9-10am Perth), so there are a few live hours before the 06:00 UTC last deploy.

Read first: CLAUDE.md, [todo/53](53-the-last-three-days.md) §3 P5, and `bot.py` `drafter_step` / `write_loop` / `pick_ready`.

## 1. What the data says

**The fresh supply is exhausted, so speed is what's left.**
- At 17:45 UTC on 30 Oct the queue held 8,400 candidates, and only 2 were under 10 minutes old (both even depth).
- 95% of first replies went out within 5 minutes of the citizen's post (29 Oct 04:00-30 Oct 11:00 UTC).
- Writes run at about 176 an hour (162 first replies and 14 reply-backs) against the cap of 180, a 98% load.
- More slots are not on offer. What we control is **how old the post is when our reply lands**.

**Every second counts in the first minute.**
- First replies 27 Oct 04:00-30 Oct 11:00 UTC (n 8,988), 6 h proxy minus the mean of the clock hour. The hour adjustment
  takes out night and day and busy hours.
- Within a minute, when a post lands relative to our 20-second write cycle is close to random, so this is near a natural
  experiment.

| age at send | 0-10 s | 10-15 | 15-20 | 20-25 | 25-30 | 30-35 | 35-40 | 40-50 | 50-60 | 60-75 | 75-90 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| proxy vs hour mean | +1.33 | +1.02 | +0.91 | +0.76 | +0.51 | +0.47 | +0.36 | +0.27 | −0.05 | −0.09 | −0.62 |
| ±1 SE | 0.54 | 0.30 | 0.23 | 0.21 | 0.19 | 0.18 | 0.18 | 0.15 | 0.19 | 0.20 | 0.19 |
| n | 157 | 428 | 744 | 857 | 925 | 1,079 | 967 | 1,469 | 780 | 694 | 466 |

- **The target answers us** 15.4% of the time at 0-15 s, 12-13% at 15-30 s, 10.5% at 30-40 s, 9.5% at 40-50 s, 8.8% at
  50-60 s and 6.8% at 60-90 s.
- **The slope is steeper where the value is.** Relative to the hour mean, odd-depth and top-of-thread targets earn +2.1 under
  20 s against +0.7 at 30-40 s; extra citizens +2.3 at 0-15 s against +0.6 at 30-35 s.
- **The likely mechanism:** citizen sessions are short. A reply that lands while they are still reading gets answered, and
  the first bot reply takes the citizen's attention (on 29 Oct we were first about half the time; situation §1).

**Where our 38 seconds go** (fresh first replies, under 3 min, 29 Oct 04:00-30 Oct 17:00 UTC, n 5,018):

| stage | p25 | p50 | p75 | p90 | why |
|---|---|---|---|---|---|
| posted → chosen (`t_made` → `t_pick`) | 9.1 s | 16.9 s | 29.3 s | 53.7 s | Latest is read every 15.0 s (7.5 s on average), then the post waits for a drafter: they choose only when the pipeline has room, which is right after a send |
| chosen → drafted (`t_pick` → `t_drafted`) | 1.6 s | **2.1 s** | 3.1 s | 6.3 s | drafting is fast (Haiku 1.9 s, Kimi 2.2 s, flash-lite 4.8 s) |
| drafted → sent (`t_drafted` → `t_sent`) | 10.1 s | 16.5 s | 19.6 s | 31.2 s | the draft waits for the write slot |
| **total** | 25.9 s | **37.6 s** | 54.5 s | 93.3 s | |

- **Why the pipeline is slow.** In the `shallow` queue arm, `draft_ahead` is 2, and 96% of sends had another draft
  ready (`ready_n` = 2).
- After each send a drafter chooses at once, so the target it takes is the freshest post **about 20 seconds before** it can
  go out.
- A fresher post that arrives meanwhile waits for the next send before anyone even chooses it.
- The other ready draft keeps ageing. `QUEUE_MAX_WAIT_S` (150 s) finally sends it first, as a stale reply.
  - **That's 9.1% of all sends.** 593 of 6,528 first replies and reply-backs, 29 Oct 04:00-30 Oct 17:00 UTC, went out after
    waiting 150 s or more as ready drafts (`ready_s`), at a median target age of 221 s.
  - They earned 1.67 ± 0.20 against a mean of about 2.5.
  - Another 292 waited 60-150 s.
- **The fix is not faster drafting** (drafting takes 2 s). It is **choosing the job a few seconds before the slot**.

## 2. What it is worth
- **The arithmetic.** Shift each first reply under 120 s (70% of them) earlier by the gain, read the gradient above, and
  average over all first replies (mean proxy 2.18): −10 s gives +0.16 proxy a write (+7%), −15 s gives +0.24 (+11%) and
  −20 s gives +0.32 (+15%).
- **The design below should cut the median by 13-18 s.** Choosing just before the slot saves about 13 s, and a 5-second
  Latest read saves another ~5 s.
- **The stale sends are extra.** The 9.1% of slots that now go to drafts 150 s or more old would go to the freshest
  candidate at T − 7 s. At about +0.9 each, that's about +0.08 a write (+3-4%). It's not in the figures above, which hold
  replies over 120 s unchanged.
- **Planning figure:** half the gradient is causal, so **+5-6%** engagement per write, plus part of the stale-send gain.
  - The range is +3% (a third causal, −10 s) to +15% (all causal, −20 s), before the stale sends.
- **In points:** from a 06:00 UTC deploy to the end there are about 195k of engagement points (7 h at ×2 and 42 h at ×4,
  at the 30 Oct pace).
  - That is **about +10k at the planning figure**, with a range of +6k to +29k.
  - It's the size of the gap china is opening on us (todo/62).

## 3. Design

### Step 1: choose at the slot (`JIT_LEAD_S`)
**Behaviour.** In the `shallow` queue arm, a drafter does not choose a new job while the writer's next slot is more than
`JIT_LEAD_S` seconds away. The pipeline holds one draft, not two:
- **At T − 7 s,** the first free drafter calls `choose()`. That returns a due reply-back first, else the newest candidate
  (`targeting.next_target`, unchanged).
- **It drafts.** That takes about 2 s; the p90 with gate repairs is 6.3 s.
- **At T,** the writer sends it.
- **If the draft isn't ready at T** (about 1 in 10), the writer's existing 1-second poll sends it when it lands. A send
  more than `QUEUE_LATE_S` (8 s) late counts as late. `QUEUE_GUARD_N` late sends in 15 min drop the arm to `fresh`
  (draft-ahead 4: the old fill-ahead), and the JIT hold stands down by itself there. The safety valve is already in
  the code.

**Code** (`src/swan_bot/bot.py`, `src/swan_bot/config.py`):
1. `config.py` (by the queue-arm block, ~line 839):
   - `JIT_LEAD_S = 7`: seconds before the writer's next slot at which the next job is chosen. 0 turns it off and
     restores today's behaviour.
   - `QUEUE_SHALLOW_AHEAD = 1` (was 2).
   - Add `JIT_LEAD_S`, `QUEUE_SHALLOW_AHEAD`, `REFRESH_S` and `TRENDING_EVERY` to `STEALTH_ENV` (~line 624). Every kill is
     then a `.env` line and a restart, with no push.
2. A pure helper next to `draft_ahead`:
   ```python
   def jit_hold(next_write, now, arm, lead=None):
       """todo/58: True while a drafter should wait to choose: shallow arm, JIT on, the writer's next slot more than
       `lead` seconds away. next_write 0 (nothing sent yet) never holds."""
       lead = config.JIT_LEAD_S if lead is None else lead
       return bool(lead) and arm == "shallow" and next_write > 0 and next_write - now > lead
   ```
3. `drafter_step`:
   - In `full()`, after the existing `len(ready) + len(inflight) >= draft_ahead(arm)` test, also return True when
     `jit_hold(next_write, time.time(), arm)`.
   - Repeat the check in the race guard under `mu` before `choose()` (line ~2448).
   - `next_write` is the writer's (nonlocal in the enclosing function). Drafters only read it, and a float read is atomic.
   - Compute `arm = queue_arm(late_sends=late_sends)` once and pass it in.
4. Nothing else changes: `pick_ready`, `choose`, `next_target`, the gate and the voices.
   - Hot mode: one voice, `HOT_GAP_S` 2 s, so the voice is never the limit.
   - The serial loop (`SPLIT_LOOP` False) is untouched.

**Tests** (with the existing split-loop tests; `grep -n draft_ahead tests/`):
- `jit_hold`:
  - lead 0 never holds; the `fresh` and `base` arms never hold; `next_write` 0 never holds.
  - Slot 20 s away → hold. Slot 7 s away → don't hold. Slot in the past (late) → don't hold.
- `draft_ahead("shallow") == 1` with the new default.
- `scripts/t.sh` (the fast suite is what the box's deploy check runs).

**Edge cases to check in review:**
- **Reply-backs:** `choose()` still takes them first. A citizen who answered us 5 s ago is the "newest target", so
  `pick_ready` would send it anyway.
- **Writer pacing:** the writer still paces from the headers (`write_gap`). A late send moves `next_write` later, so
  throughput can't exceed the cap.
- **`DRAFTERS` 3:** with draft-ahead 1, one drafter works at a time and the others idle on `full()`, so no new contention.

### Step 2: read Latest every 5 s (`REFRESH_S` 15 → 5, `TRENDING_EVERY` 3 → 9)
- **Today:** the reader refreshes every 15.0 s (p10 14.6, p90 15.4), so the refresh finishes well inside its slot.
  - At 5 s the average notice delay drops from about 7.5 s to about 2.5 s.
  - Latest carries about 60 posts a minute, so a refresh reads one 100-post page.
- **Reads:** about 12 Latest reads a minute, plus parent `get_post` for new citizen replies (cached).
  - Keep Trending at its current 45 s by setting `TRENDING_EVERY` to 9. Each Trending read also reads 12 threads'
    replies, so leaving it at 3 would triple those reads.
  - The feed budget is in the headers (300 a minute since 22 Oct; 200 seen on 29 Oct). `_latest` already stops paging
    at `FEED_READS_SPARE`.
  - Check `logs/feed_reads.jsonl` and `feed_remaining` in the refresh rows after the change.
- **Ship it as a `.env` change** (`SWAN_REFRESH_S=5`, `SWAN_TRENDING_EVERY=9`, then restart), once step 1 is in `STEALTH_ENV`.
- **Order:** do it **after** step 1 has run cleanly for 30-60 minutes.

### Rollback
- `SWAN_JIT_LEAD_S=0` and `SWAN_QUEUE_SHALLOW_AHEAD=2` in `.env`, then restart, gives exactly today's pipeline.
- `SWAN_REFRESH_S=15` and `SWAN_TRENDING_EVERY=3` undo step 2.

## 4. How we judge it (no arm: before against after, the same hours a day earlier)

| check | when | source | bar | kill |
|---|---|---|---|---|
| writes a minute | 30 min after each restart | dashboard throughput, `act` reply/reply_back rows | ≥ 2.9 | < 2.8 for 30 min → step 1 off |
| median age at send, first replies under 120 s | 30-60 min | `t_sent − t_made` | ≤ 25 s (was 37.6 s) | no fall → look before step 2 |
| late sends (> 8 s after the slot) | 1 h | `late_sends`; `queue_arm` "fresh" on reply rows | < 5% of sends | > 10% → step 1 off |
| stale sends (`ready_s` ≥ 150 s) | 1 h | reply and reply_back rows | about 0% (was 9.1%) | still above 3% → the hold isn't working; look |
| proxy a first reply, 6 h read, hour-adjusted | 7 h after go-live | outcomes join | above the same hours a day earlier | 10%+ below over 12 h → off |
| portal engagement per write (24 h) | 12-24 h | portal | toward 6.3-6.5 (6.08 on 30 Oct) | 10%+ below the same hours a day earlier over 12 h |

## 5. P5's other questions, answered (no change)
- **Citizen posts skipped as off-topic** (about 85 replies and 18 top-level posts an hour).
  - A read of the snapshot's citizen replies on 30 Oct found 12 of 23 off-topic skips are on the vote when the thread's
    root post is added to the context (`hard_skip` reads only the parent's first 200 characters).
  - But 9 of the 12 classify as `unclear`, our weakest class (proxy 1.07). Not worth slots now. A future fix is the root
    as context.
- **Deep threads** (31 an hour, depth ≥ 8): low value by design. The scoring page says citizens rarely continue past
  eight messages.
- **News threads and Trending:** citizens' replies there reach us through Latest first. All first replies on 29-30 Oct have
  `source` latest.
- **Liked-but-didn't-reply and followers:** the engaged arm (5 an hour) already covers them.
- **Accounts that never post** (981 above id 2343, unscored): there is nothing to reply to, and they can't be shown to be
  citizens.
- **Queue order:** depth isn't in the priority, but the fresh odd and top supply is already taken (2 fresh candidates
  waiting). The value table (todo/49) and the 31 Oct boosts were both null. Speed is the lever left.
- **The `DOWNRANK_MIN` 2.5 for weak classes stays.** It rests on an equal-age finding (weak classes reply 2-5 points less
  at the same age; config comment, 27 Oct), and choosing at the slot helps them too.

## 6. Live checks (31 Oct, on the box; `t_*` fields of reply and reply_back rows, against the same clock window a day earlier)
- **Step 1 (f6c6222, 23:49 UTC), first 14 min.**
  - Writes 2.89 a minute (2.96 the day before).
  - `ready_s` p50 6.2 s (14.7); stale sends 0 (7.3%).
  - But chosen → sent was bimodal, 7 s or 18-20 s, half each. The writer set `next_write` only after the write returned,
    so a drafter that looked mid-send saw the old slot, didn't hold, and chose a slot early.
  - **Fixed in 4363550:** the writer flags a send in progress (`sending`), and `jit_hold` holds then too.
- **Push 2 (4363550, 00:15 UTC: the mid-send fix and Latest every 5 s), first 3 min.**
  - Chosen → sent p25-p90 6.9-7.6 s (18.0-154 the day before).
  - Age at send p50 24.8 s (39.5), n 9.
  - Refresh gap p50 5.0 s; `feed_remaining` never below 199; no `widen_rate_limited`.
- **Push 2, first 27 min (00:15-00:42 UTC), against the same window a day earlier.**
  - Writes 2.94 a minute (2.98); reply-backs 8 (4).
  - **Age at send p50 21.4 s (37.3)**; p25 16.5 (25.9), p75 27.1 (52.9), p90 39.6 (77.0); n 70.
  - Chosen → sent p50 7.4 s, p90 7.9 (19.7 and 149.8). Stale sends 0 (6).
  - Drafting p50 1.9 s, p90 4.0, p95 6.6; 1 of 70 over 7 s, so the 7 s lead leaves room.
  - Refresh gap 5.0 s; `feed_remaining` never below 199; no rate limits.
- **Still to read:**
  - the 6 h proxy per first reply, hour-adjusted, against the same hours a day earlier (from 06:15 UTC);
  - the portal's engagement per write over 12-24 h.
- **An option not taken:** `SWAN_JIT_LEAD_S=5` would save about 2 s more. Drafting's p90 is 4.0 s, so about 1 send in 10
  would land a second or two late. Leave it at 7 unless the 6 h read says speed still pays.
- **After push 4 (5f10159, 01:13 UTC), 16 min.**
  - Writes 2.92 a minute; age at send p50 23.7 s; chosen → sent p50 7.3 s; no stale sends.
  - Refresh 5.0 s; no rate limits; no tracebacks; health state clear.
  - Four restarts in 85 minutes cost no throughput beyond the restart minutes.
