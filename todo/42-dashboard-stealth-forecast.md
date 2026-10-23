# 42 — Dashboard: stealth as rates, plus a bans forecast against a plan

Updated 2026-10-24 (Marc + Claude). Read `CLAUDE.md` first. Code: `src/swan_dash/build.py` (stealth tile rows ~1390, `STEALTH_GREEN_MAX/AMBER_MAX` at 804, `account_days` ~1093, the "Accounts by day" table), `src/swan_dash/portal.py` (`ACCOUNT_COUNTS` ~104). Plan numbers: [39](39-account-budget-multiplier.md).

## Today's problem
The stealth tile counts *bans today* and *hidden posts today*: counts of a rare event with a 3 h delay, so they swing. And the two places that show bans disagree: the portal's `account_log.counts` row (registered / banned) updates **before** the `suspended` message rows (which carry the names and reasons). On 23 Oct 16:03 UTC the counts said 25 banned while the list held 21. The bot's own 403 discovery is a third, later source. Nothing shows the rate per write, which is what decides whether we run out of accounts.

## Marc's spec (24 Oct)
Under **Accounts by day** (a chronological table of bans, with the 3-posts-hidden vs reported-as-a-bot reasons), add columns and a collapsed summary:
- **Forecast new bans** for the day, **actual**, and the **net** (actual − forecast), with a plus/minus tolerance. Forecast = planned writes for that Sydney day ÷ writes-per-ban (below). Planned writes is a small editable table (one number per Sydney day, default the last 3 days' average); Marc edits it, nothing throttles automatically.
- Beside it the **account balance**: alive, spare registrations, and the **reserve goal** for 1 Nov (60, [39](39-account-budget-multiplier.md)). The question it answers: are we on track for the goal, and what is the plus or minus against it? Extend the forecast through the ×2 days (26–31 Oct) and the ×4 days (1–2 Nov), where the forecast bans per day are larger because planned writes are.
- Collapse the detail in place (the same pattern as the Blue timeline): a one-line summary row ("bans today 7 · forecast 12 · net −5 · spare 127 · on track for 31 Oct: +/−N"), a vertical "⋮" / dots control to expand the per-day rows.

## Metrics to add
1. **Hide rate** = hidden text posts ÷ text writes (replies, posts, threads; not likes or reposts, and not booster reposts), trailing 24 h, 95% Wilson interval. Count only writes at least 3.6 h old (a hide takes about 3.3 h to show). Target line 1.4% now, 1.0% after [40](40-hide-rate-changes.md). Colour by whether the interval clears the target. Under 300 writes in the window, show it grey with "n = …".
2. **Writes per ban** (the life of an account): Kaplan–Meier median of writes at ban over voices, trailing 72 h, alive ones censored. Today about 145 [127, 178]. The forecast above divides by this.
3. **Runway** = spare accounts ÷ (planned writes a day ÷ writes per ban), in days, next to days left.
4. **One source for bans:** take the number from `account_log.counts` (it moves first) and the names/reasons from `suspended`; show both with the lag instead of two headers that disagree. Bans per Sydney day roll over at 9pm Perth.
5. **Leaderboard history:** keep the portal leaderboard (rank, our score, 1st and 3rd score, team count) as an hourly series (`data/leaderboard.jsonl`, appended by the portal poll), and show the gap to 3rd and whether it is closing. We only have snapshots today (23 Oct 14:32 UTC: 82,750 / 79,323 / 71,983 vs our 32,328).
6. A detail row: hides per voice before it is banned (median), and how many were already in the 3 h pipeline when the first showed.

## Notes
- "Hidden posts never colour stealth" (Marc, 23 Oct): the rate tile is allowed to colour it, because it is a rate with an interval, not a count.
- Add tests with synthetic logs: Wilson interval edge cases; a voice still alive (censored); the 3.6 h censor; a day with a counts row but no suspended rows yet.

## Done when
The Accounts-by-day table shows forecast, actual, net and the balance vs the reserve goal for 24 Oct–2 Nov, collapsed in place; the stealth tile shows the hide rate with its interval and writes per ban; the bans number is the same wherever it appears; the leaderboard series is being written.
