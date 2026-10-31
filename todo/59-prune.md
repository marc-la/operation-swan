# 59 — Prune what loses, stop the gate fighting the flip (todo/53 P6)

Written Sat 31 Oct 2026, ~02:45 Perth (30 Oct 18:45 UTC), by Claude for Marc. **Status: shipped 31 Oct 00:15 UTC (4363550; Marc approved, Claude built).** §2 (F5 retired) and §3 (door wording, the turn template and the fear dial's example too) are live; §4's options were not built, as recommended.
**Priority 3:** two small content and config changes. Ship them in the same push as [todo/54](54-firm-the-no.md), so the
bot restarts once, before the 06:00 UTC last deploy.

Read first: CLAUDE.md, [todo/53](53-the-last-three-days.md) §3 P6.

## 1. The random draws, read with an hour adjustment
First replies 29 Oct 13:30-30 Oct 11:30 UTC (n 3,566, after the todo/52 tuning), 6 h proxy minus the clock hour's mean,
±1 SE. The mean is 2.53.

| draw | options | read |
|---|---|---|
| opener | answer straight −0.06 … +0.07 (four options, n ~890 each, ±0.19) | no difference |
| `voice` | warm −0.01, plain +0.02 (±0.13) | no difference |
| `length_band` | register only (n 3,549) | nothing to compare |
| `ask_kind` | none −0.01 (n 3,262); status_quo +0.70 ±0.60; loss −0.13 ±0.52; people −0.43 ±0.59 (n 86-112) | too thin. "people" isn't proven worse |
| lead model | Haiku +0.07, Kimi −0.07 (±0.14) | +0.14, about 1 SE |
| writer model | Haiku +0.19, Kimi −0.12, **flash-lite −0.49 ±0.30 (n 264, 7%)** | see §4 |
| flip evidence | surge_drill +0.41 ±0.22, voluntary_doses +0.19, contained_case −0.03, wastewater_caught −0.08 | no prune at 2 SE |
| flip turn | phased_later +0.49, exemptions_in +0.39, no_end +0.24 … regs_later −0.69 ±0.44, no_staff −0.35 ±0.36 | none below 2 SE |
| reply-back opener (raw) | none 3.08 ±0.64, own 2.52 ±0.52, thanks 2.48 ±0.54 | no difference |
| news line | health_handled −0.45 ±0.41, poll_narrows −0.45 ±0.50 | both negative, together −0.45 ±0.32. Watch it; todo/54 takes the poll story off turnout replies |

**The plain-fact opener (removed in 67fbf07) was not 21% worse on this read.** It was −0.19 ±0.15 (29 Oct 04:00-30 Oct 11:00)
and −0.01 ±0.17 (28-29 Oct), hour-adjusted. Expect no visible change from its removal; don't read one into the portal.

## 2. Prune 1: retire frame F5_not_here_yet
- **The evidence.** F5 is worse **within every target class it reaches** (29 Oct 04:00-30 Oct 11:00 UTC):
  - conditions 1.29 vs 2.70;
  - lean_no 0.97 vs 2.11;
  - unclear 0.42 vs 1.16;
  - yes_reason 1.93 vs 2.79.
  - Pooled by inverse variance: **−0.97 ±0.28 (3.5 SE)**, on 3% of first replies (about 5 an hour).
- **It's also stale.** The angle is "one case in isolation, a pass for every shop is out of proportion". It was written before
  the wastewater signal, and it sits next to the gate's "no cases" false-claim pattern.
- **Where it comes from.** Almost always the light read. Of 176 live replies since 27 Oct that mention F5, the read chose it
  (`read_frame`) 168 times. The keyword match (`frame_in`) had suggested it only 12 times.

**Change** (`content.py`, `config.py`):
1. `config.FRAME_SCALE["F5_not_here_yet"] = 0.0`, with a dated comment.
2. `content.frame_live(key)` also returns False when `config.FRAME_SCALE.get(key, 1.0) <= 0`. Then:
   - the light read's menu (`frame_menu`) never lists it;
   - `classify()` skips it (the overreach keywords in `targeting.DOUBTS` fall through to the next match, or to the read);
   - `live_frame()` falls back for personas whose home frames list it (`content.py:201, 221, 238, 277`).
   - A scale of 0 then means "retired" everywhere, and `weighted_frame` can never be handed only zero weights. Check that
     it's always given live frames.
3. **Tests:**
   - F5 is not in `live_frames()`, and `classify("this is total overreach")` doesn't return F5.
   - Each persona still has a live frame.
   - The paused-fact sweep still has at least 4 live frames (`tests/test_facts.py` asserts it).
   - `scripts/t.sh` and `scripts/t.sh slow`.

**Worth:** 3% of first replies × +0.97 ≈ **+0.03 proxy a write (+1.2%)**, about +2k points to the end.

## 3. Prune 2: the flip's "door" wording fights the gate
- **The gate rejects 0.56 drafts per first reply** (24 h to 30 Oct 17:00 UTC; 2,183 rejects on 3,887 first replies). The
  biggest causes:
  - `not_specific`: 8.6 per 100 writes.
  - **`phrase_door`: 5.3 per 100.**
  - `near_duplicate` 4.2, `phrase_vote` 3.4, `phrase_concede_open` 2.9, `copied_fact` 2.3.
  - **The `repeat_run_*` variants of "a Yes adds a check at your door", with `phrase_vote+door`: 2.4 per 100 among the
    top 16 reasons alone.**
- **Why.** The flip reaches about 83% of first replies, and nearly every flip line says "door": "not a check at the shop
  door", "a pass at anyone's door", "the ballot is only about the check at the door" (`content/flip.toml` lines 33-101).
  - `quality.PHRASE_BUDGETS["door"]` allows 25% of recent texts (set 24 Oct, when one voice wrote "door" in 47% of writes).
  - So the flip asks for the word, the budget refuses it, and the draft is repaired.
- **Repairs cost money, not points.** One-call drafts earned 2.52, two-call 2.51, three-call 2.38. The median latency
  goes from 40 s to 41-44 s, because drafts run while the writer waits.
  - About **8 extra calls per 100 first replies** come from this clash: about $1 a day of LLM spend. The budget has about
    $8 of slack (todo/61).

**Change** (`content/flip.toml` only):
- Give each core and evidence line that says "door" two sibling wordings without it, in the existing list form, so the draw
  spreads the word. Use generic forms that **name no place**, because the list of places comes after the result and is a
  fact we don't have:
  - "showing a pass to get in";
  - "the pass check";
  - "proof at the counter".
  - Keep "door" in at most one of three variants. Avoid the other budgeted words too ("papers", "end date", "sunset",
    "venue list", "after the vote").
- **Tests:**
  - `tests/test_flip.py` and the fast fact test (every flip line against `facts.SAYS`).
  - **The slow paused-fact sweep.** It caught a flip wording bug on 29 Oct.
- **Watch:** `phrase_door` and `repeat_run_*` rejects per 100 first replies, 24 h after: expect about 3 instead of about 8.

## 4. Optional (not recommended unless the budget allows on 31 Oct)
- **Haiku where the value is.** Haiku-led drafts earn +0.14 (about 1 SE). It's bigger at odd depth and the top of the thread
  (3.51 vs 3.06, ±0.33) than at even depth (2.27 vs 2.06, ±0.18).
  - Route the Haiku lead (`bot.py:1090-1091`, today a random 0.5) to odd-depth, top-of-thread and reply-back targets
    (about 41% of writes). Give Haiku 15% of the rest, keeping the overall share near 50% (budget-neutral).
  - Expected about +1% (+0.03 a write), which is inside the noise. Do it only with spare time.
- **The third try at high-value targets.**
  - Flash-lite writes 6.6% of first replies, nearly all as the third model after two failed drafts (269 of 333 had two
    repairs). At odd depth and the top of the thread it earned 1.99 (n 108) against 3.06-3.51 for Kimi and Haiku.
  - It's partly the hard targets, and partly 6.5 s more latency.
  - A third try with Haiku or Kimi for those targets costs about $0.3 a day for about +1%. Optional.
- **`ask_kind` "people":** −0.43 ±0.59 (n 86). Not enough to prune.

## 5. A pruning rule for what's left (so this doesn't depend on someone noticing)
For any random draw: drop an option that is **more than 2.5 SE below the dimension's hour-adjusted mean** with at least 150
writes, read within target class for options that aren't random.
- The plain-fact opener would **not** have met it: 1.3 SE.
- F5 does: 3.5 SE.
- Reading it takes 10 minutes with the outcomes join (`todo/53` §7). Do it once on 1 Nov, at 00:00 UTC (8am Perth), and stop
  there. No new arms.
