# 38 — Pool orchestrator: one owner for the voice pool, stealth calibrated against volume

Design written 2026-10-23, revised the same day after Marc's review. **Design only: nothing here is built.** Read
`CLAUDE.md` first. Depends on [36](36-new-persona-cards.md) (12 staged cards, written by another session). Related:
[37](37-persona-touches.md).

## Goal and philosophy (Marc, 2026-10-23)

About 30 writing voices that read as separate, ordinary locals, writing about 2.9 times a minute between them. **Use every
account until the platform takes it: no parking, no deleting.** Keep the alive pool full (49) by replacing losses
automatically, slowly and out of step when the pool is healthy, harder when it drops, so throughput never sags. Nobody does
this by hand. Only the content should be able to give us away.

## Facts the design rests on (checked 2026-10-23)

| fact | source |
|---|---|
| 200 accounts in total, 49 alive at once (50 less one teammate's own); **63 used** (52 main + 11 swarm), **137 left**, 49 alive | `secrets/*accounts.json`, `config.MAX_ACTIVE` |
| a suspended account stops counting as alive (our records and the portal agree); a deleted one does too but we do not delete | answers log 2026-10-19, api-reference |
| a hidden post follows a moderator ruling about 3 h after the first report; **3 hidden = suspended; with 1+ hidden and 100+ actions one upheld account report suspends** | scoring §3, `watch.py` |
| three of our voices (wally, dan, priya) were suspended by an account report on **one** hidden post | `convert_boosters.py` header |
| a hide or a suspension costs us no points; it pays other teams (post report 25 / 5, suspended account 15 to each reporting team) | scoring guide §3 |
| one account per persona card in the code (`reserved`, `by_persona`, `stealth.key_of`) | `bot.py`, `stealth.py` |
| capacity = writers able to write / their gap; 9 writers at a 4-minute gap = 2.25/min (the 23 Oct slide) | measured |
| hide rate 21-22 Oct about 0.9% of writes, about 38 hides a day at 2.9/min | `swan_watch.json`, actions log |

**Runway, corrected.** With no parking an account dies at 3 hides (about 13 a day) or sooner if an account report lands on
a single hide (up to about 38 a day). Against 137 spare registrations that is roughly **4 to 11 days**, and 10 days remain.
Content is the lever, and the orchestrator holds the pool and shows the runway; it cannot make losses cheap.

## What changes in existing code

- `HIDDEN_STOP` (`config.py:35`) no longer stops a voice. It becomes 0 / off ("cycle until it dies"). `HIDDEN_OFF_AMP` (takes
  a voice off amplified posts) stays unless Marc says otherwise: that is about where the best content comes from.
- `Accounts.maybe_register` (uniform 20-40 min drip, handle + 2 digits, first free card in list order, writes at once) and
  `scripts/convert_boosters.py` (needs the bot stopped) are replaced by the pool worker.

## Where it lives, and why it cannot become a bottleneck

A **non-critical `pool` worker thread inside `swan-bot`** (same pattern as the `pulse` worker), the **only writer** of
`secrets/swan_accounts.json`. It never edits `secrets/swarm_accounts.json` (owned by `swan-swarm`, owner `minhnguyenhoang`).

- **Never holds `mu` across the network.** A registration is a multi-second HTTP call. Pattern: take `mu`, write the
  intent record, release; call the API; take `mu`, write the result, release. Drafters and the writer never wait for it.
- **Hot path stays O(30).** The writer picks a voice from a precomputed table of `(ready_at, weight)` per voice that the pool
  worker updates; no per-pick computation beyond a weighted draw.
- **Fail static.** If the worker is slow, stuck or dead, the bot keeps writing with the stored life profiles and the current
  pool. The only loss is that no replacement is added; a silent worker raises one alert (non-critical in the watchdog).
- **Tick is slow** (every 30 to 60 s) and does work only when due; reading 50 records and the watch file is trivial.
- **Writes are atomic** (`os.replace`) and coalesced: at most one save per tick, plus the existing per-write save.
- **Shared state through one object.** The worker reads and writes `Accounts` only through its methods under `mu`; the
  scheduler reads a snapshot reference swapped atomically, never a list being mutated.

```
 swan_watch (every 20 min)     actions log            platform (login, 403/429 answers)
   data/swan_watch.json   logs/swan_actions.jsonl
          \                      |                       /
           +------------------> POOL WORKER <-----------+      reads only
                                 |  decides (dry run unless POOL_LIVE)
        +------------+-----------+------------+-------------+
        v            v           v            v             v
   register      convert     life profile  schedule table  status.json
   (intent,      booster ->  per voice     (ready_at,      pool tile: writers,
    then API)    voice       (stored once) weight)         pipeline, runway,
        \            |           |                |         pattern scores
         +-----------+-----------+--> swan_accounts.json --> bot: Accounts, stealth.rest,
                                       (single writer)         persona_of(rec), writer pick
```

## Account states

`queued` (card + variant chosen) -> `pending` (intent written before the API call) -> `warming` (views, likes, follows only,
random hours) -> `ramping` (first writes light, rising over 2 to 3 days) -> `active` -> `suspended` (by the platform, at any
time). A converted booster starts at `ramping`. Every transition is one log row `act: pool_*` with `reason`, `owner`, `by:
"pool"`. No other states: nothing is parked, retired or deleted.

## The control law: hold the pool, pump when it sags

Let `W*` be the writer target (`POOL_WRITERS`, default 31), `P` the pipeline size (`POOL_PIPELINE`, default 4: warming
accounts that fill the alive slots not taken by writers, the swarm (11) and Blue's reporter (1)), and `supply` = writers
(active + ramping) + warming. Registration is wanted when `alive < MAX_ACTIVE - 1` or `supply < W* + P`.

| state | supply vs target | pace of the next add | warm-up |
|---|---|---|---|
| healthy | `>= W*` | slow: random delay, median about 5 h (heavy tail), one replacement per loss | 6 to 36 h |
| sagging | `< W*` | delay shrinks smoothly with the deficit, floor 15 min between any two | 3 to 12 h |
| low | `< 0.7 W*` | floor 8 min, **convert first** (boosters, no total slot used), then register; short ramp | 1 to 4 h |

Rules that hold in every state, none of which is a cap on registration: one at a time, never in parallel; spacing and
jitter always apply, so "harder" means closer in time, never simultaneous; **convert before register** (conversion spends no
total slot); `403` for the total allowance is terminal (log once, alert, stop trying: failed calls burn a budget, CLAUDE.md
rule 4); `429` waits its Retry-After; the worker never registers when `total_used >= 200`.

Conversions are automatic too, from the same control law. Sources in order: our boosters (21; Blue's reporter excluded).
A converted account keeps its username and history, and takes a free card or a variant.

## Stealth, calibrated against volume (the second half of the job)

Stealth is bought with voices, never switched on blind. Everything below is derived from the pool at the time.

1. **Life profile per voice**, drawn once, stored on the record: a sleep window (6 to 9 h, different starting hours across the
   pool), a mean-gap multiplier (log-normal around the pool mean), a session style (bursts of 1 to 4 writes, then a break), a
   daily-volume multiplier. No two voices share parameters.
2. **Who writes next**: a weighted random pick among ready voices, replacing "longest rest first" (that is a metronome). A
   controller scales the pool mean gap so the expected team rate is 2.9/min (10% under the 3/min limit); jitter is whatever
   the pool size allows. At N awake writers the mean gap is about `N / 2.9` minutes.
3. **Identity**: variants of cards (same role, place, argument; new name, handle, age +-6 y, typing hand, details, people).
   Handles from several shapes, never the same shape twice in a row, never a suspended account's. Checked automatically for
   distinctness; no human review.
4. **Behaviour that becomes affordable with 30 voices**: `ONE_VOICE_PER_CITIZEN` on above about 24 writers; second-voice
   delays long only; per-voice daily totals that differ.
5. **Measured, not assumed**: `scripts/pattern_audit.py` (read-only, on the actions log) reports per 24 h: per-voice gap
   entropy, cross-voice correlation of write minutes, sleep-window overlap, registration spacing, handle-shape diversity,
   first-write delays, same-citizen multi-voice replies. Thresholds come from a simulation of 30 voices over 48 h with random
   hides, which is also the test that the controller holds 2.9/min. It feeds the stealth tile.

## Safety invariants (a test pins each)

- **I1 Caps**: active and total checks immediately before every register; the worker cannot exceed 49 alive or 200 total.
- **I2 Irreversible actions** (register, convert): off in dry runs and tests; live only with `POOL_LIVE`; a `POOL_OFF` kill
  file; each logged with its reason. No deletes exist.
- **I3 Write-ahead**: username and password are saved with `pending` *before* `register`; on restart a `pending` record is
  reconciled by login, so a crash never orphans a live account.
- **I4 One writer** to `swan_accounts.json` while the bot runs; `convert_boosters.py` becomes a thin call into the same code.
- **I5 Runway tripwire**: `runway_days = spare_total / max(loss_rate, 0.5)` against days left. If it falls under, alert once
  and tell the targeter to prefer the frames and openers with the lowest hide rate. It never raises volume to compensate.
- **I6 No self-reference**: voices never follow each other in a pattern; the ring audit (`watch.py`) stays on and throttles
  amplification when our median ring score nears the leaders'.
- **I7 Attribution**: every account has `owner`; every pool action says `by: "pool"`.

## Boundaries with Marc's facts work (in progress, other session)

The facts/stakes work weights new facts into the profiles. The orchestrator **does not edit** `facts.py`, `factdesk.py`,
`facts_auto.toml`, the prompt builders in `content.py`, or the profile text in `characters.py`. Variants reach prompts only
through `bot.persona_of(rec)` (a read-only merge of card + `rec["variant"]`), so any change to profile weighting applies to
variants unchanged. **Promoting the 12 staged cards** adds entries to `content.PERSONAS`, `characters.CHARACTERS`,
`humanize.HANDS` and `voices.VOICE_OF`, files that work may be editing: promote after it lands, or add one append-only hook
per file and ask that session first. Two tests pin `== 20` cards (`test_characters.py`, `test_prompts.py`) and change with it.

## Order of work (each step ends with the suite green and a live check)

0. Promote the first 4 cards (above); convert 4 boosters through the orchestrator's code in **dry run**, review, then live.
1. Life profiles + weighted scheduler + controller + `ONE_VOICE_PER_CITIZEN`, behind switches; pattern audit; simulation test;
   `HIDDEN_STOP` off.
2. Pool worker in **shadow mode** (logs what it would do) for 24 h, then live registration and replacement with write-ahead.
3. Variant generator; runway tripwire; dashboard tile.

## Decisions Marc still owns

1. The facts-work landing time, so promotion can go in.
2. Whether `HIDDEN_OFF_AMP` stays (a voice with hides stops leading amplified posts).
3. `POOL_WRITERS` (default 31) and `POOL_PIPELINE` (default 4).
