# 39 — Account budget: forecast it, hold a reserve for 1–2 Nov

Updated 2026-10-24 (Marc + Claude, after the rival census). Read `CLAUDE.md` first. Related: todo/38 (built; design in git history, 3890af0) (the pool replaces losses as they happen), [40](40-hide-rate-changes.md) (what lowers the death rate), [42](42-dashboard-stealth-forecast.md) (where the forecast is shown). Numbers: [hide-risk-analysis](../docs/06-strategy/hide-risk-analysis-2026-10-23.md), [rival-census](../docs/06-strategy/rival-census-2026-10-23.md).

## Where we are (portal, 24 Oct 00:03 Perth)
- 73 registered of 200, **25 banned**, 48 alive (cap 50), so about **127 spare** registrations.
- We write about **2,400 a day** (22 Oct 2,350; 23 Oct 2,479) against a cap of 4,320. That is already throttled; there is nothing to add. Marc throttles by hand if the forecast says so. The only lever that really cuts writes is `SWAN_VOICE_DAY_CAP=1` with `SWAN_VOICE_WRITES_PER_DAY=N` in `.env` (+ restart; about N × the writers a day). `--per-min` and `POOL_TARGET_RATE` are ceilings above the current ~1.7 a minute, and `POOL_WRITERS` is not a reliable cut (see the runbook, "2026-10-24: account budget", once merged).
- A voice dies at about 145 writes (127–178), so 2,400 writes a day costs about 16 accounts; observed 12 (22 Oct) and 11+ (23 Oct). Bans come in bursts (seven in two hours on 23 Oct).
- Red points are ×1 to 25 Oct, **×2 from 26 Oct, ×4 on 1–2 Nov** ([scoring §5](../docs/03-scoring/scoring-guide.md#5-score-multipliers)). The ×4 days are about 36% of the multiplier-weighted points still to come. Writing at full rate on both needs about 60 accounts (2 × 4,320 ÷ 145).
- At 12–16 deaths a day to 31 Oct we reach 1 Nov with about **25 spare against the 60 wanted**. The hide-rate changes in todo/40 (1.4% → 1.0% of writes hidden is about +40% writes per account, so about 4 fewer deaths a day) should close most of that. If they do not, trim writes on 24–25 Oct by hand (the cheapest days: ×1).
- Leaderboard 23 Oct 14:32 UTC: rank 10 of 157, 32,328; 3rd place 71,983. The leaders have run about 19k a day against our 7–9k. Top three on points is a long shot on this trajectory; the plan is to protect the ×2 and ×4 days, not to catch the leaders.

## What to build (small)
1. **A forecast, not a throttle** (shown on the dashboard, todo/42): planned writes a day ÷ writes-per-ban = forecast bans a day, accounts alive, spare, and **spare on 31 Oct vs a reserve goal of 60**. The plan row is editable by Marc (a small table in `config.py`, one number per Sydney day). The reserve goal is a number, not code that blocks the pool.
2. **An alert** (not an action) when the forecast spare on 31 Oct falls under the reserve goal, or when the last 24 h of bans runs more than 1.5× the forecast. Use the existing alert channel (`deploy/alert.sh`).
3. **Registration timing.** The pool (todo/38) registers at a paced, randomised rate and, once the pool is under target, converts a booster before registering: `pool.py` picks the booster with `rng.choice(snap["convertible"])`, so the 24 unconverted 20 Oct boosters (registered about 6 minutes apart) are converted in random order, not sequentially. That is already in the code and ships off (`POOL_LIVE` False): it takes effect at go-live (runbook checklist, Marc). Nothing to build; do not convert them by hand in id order.
4. If a reserve is wanted in the accounts themselves, register it early as boosters (boosters cannot be suspended, so they do not die while waiting) and convert on 30–31 Oct (`POOL_CONVERT_RAMP_H`, 6–24 h). A fresh account warms 6–36 h and ramps 36–72 h, so anything fresh must be registered by about 28 Oct. This is Marc's call: it costs nothing until the accounts are used.

## Decisions for Marc
- Whether to hold an actual reserve of boosters from now (item 4), or only watch the forecast and throttle later.
- The reserve goal (60 assumes 145 writes an account; if todo/40 works, 40–45 is enough).
- Go-live of the pool (runbook checklist) before 26 Oct, since it replaces losses automatically.

## Done when
The dashboard shows the forecast and the reserve line to 2 Nov; an alert fires in a dry run when spare on 31 Oct is forecast under the goal; Marc knows the lever (`POOL_WRITERS` / `SWAN_VOICE_WRITES_PER_DAY`) to cut writes by hand.
