# 57 — One voice: keep hot mode; variety buys nothing we can find (todo/53 P4)

Written Sat 31 Oct 2026, ~03:15 Perth (30 Oct 19:15 UTC), by Claude for Marc. **Status: no change recommended.** The spare
ban budget has no use that pays. Close P4 unless Marc wants to spend accounts on something not tested here.

Read first: [todo/53](53-the-last-three-days.md) §3 P4, [stealth](../docs/06-strategy/stealth.md), `config.py` hot mode
(~line 633).

## 1. What could voice variety buy, and what the data says
Each test uses the 26-30 Oct log (18 hot voices, 241-1,951 writes each) and the 6 h outcome proxy.

| possible gain | test | result |
|---|---|---|
| **Citizens tire of one account** (a "fresh face" draws more) | first-reply proxy by how long the current voice had been writing, minus the hour's mean | first hour **−0.16 ±0.10**, 1-2 h −0.06, 2-4 h +0.05, 4-6 h +0.04, 6-8 h +0.08, 8 h+ 0.00 (n 1,100-5,093 a bin). No fatigue; a new voice does slightly *worse* at first |
| **A repeat write lands better from a different voice** | repeat writes to a citizen, same voice vs the previous (now dead) voice | under 1 h: same 1.90 (n 11,328) vs new 2.47 ±0.61 (n 73); 6-24 h: same 1.32 ±0.39 vs new 1.53 ±0.12. No difference |
| **New accounts collect more follows** (20 points each; a citizen can follow every new voice) | portal follows an hour by hours since the last suspension | 0-1 h 4.0, 1-2 h 2.9, 2-4 h 3.0, 4-6 h 4.3, 6 h+ 3.8 (±0.3-0.6). No effect |
| **In-group messengers** (playbook §7; `targeting.IDENTITIES`) | how often a target states an identity the regexes catch | 3 of 615 replies sampled on 30 Oct (0.5%). Even perfect matching would touch about 1 write in 200 |
| **Longer-lived voices answer late replies** | public read on the box, 30 Oct 18:00 UTC: 59 of our posts by three suspended voices (percy87, lesieli_tait16, adeleke_g31), written 6-25 h earlier, read again for citizen replies; `counters()` checked as well | 7 citizen replies in all, 5 within 6 minutes and 2 within 6 h. **None after the suspension, none after the 6.3 h outcome check**, and counters equal the listings. There are no late replies to rescue (todo/60) |

## 2. What a ban costs now
- **The handover:** a spare writes within seconds. `HOT_HANDOVER_FAST`; the alerts show the next voice writing the minute
  the last one is suspended.
- **Citizens mid-conversation:** they had already answered within minutes, so very little is lost. A few reply-backs are
  stranded (1% of visible citizen replies; todo/60).
- **Accounts:**
  - 97 unused of 200; losses 3.4 a day (`status.json` `pool`, 30 Oct);
  - the pool refill is live: 1 writing, 7 standby, 1 warming.
  - We'll end with about 85-90 unused. The 49 "above plan" buy nothing because nothing we found turns accounts into points.

## 3. Recommendation
- **Keep `SWAN_HOT_VOICES` and the refill as they are.**
- **Don't build multi-voice, messenger matching or rotation for the last two days.** None of the gains in §1 shows up, and
  changing the writer at ×4 is a risk without a reason.
- **Keep the persona cards and `IDENTITIES`** (they cost nothing). Note in the runbook that matching is inactive in hot
  mode by design.
- **The one check during ×4** is spares ≥ 3 ([todo/61](61-x4-operations.md) §6), so the refill can't fall behind a run of
  quick bans.

## 4. If Marc still wants variety (not recommended; for completeness)
- **Two hot voices in turn** (alternate writes):
  - no code beyond the roster logic;
  - each voice lives longer, but bans per day rise about 1.3 times under the 24 Oct hazard model (hazard ∝ pace^0.6).
  - **Expected effect on points: none found.** The only way to learn otherwise is an arm, and the final-days rule rules
    that out.
