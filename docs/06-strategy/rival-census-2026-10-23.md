# Rival census: what other teams' accounts tell us (23 Oct 2026, ~14:00-17:00 UTC)

Question (Marc, 23 Oct): is there a control group on Legit Social, i.e. how long do other teams' accounts last, how stealthy are the long-lived ones, and does it tell us anything for Red (account budget) or Blue (who to report)? Method: a read-only scrape of public data (account list, `account_posts`) at a paced rate under the shared 300/min bucket, no login, nothing posted. Data and README: `data/rival_census/` (gitignored); scripts `scripts/rival_*.py`. Follow-ups: [todo/39](../../todo/39-account-budget-multiplier.md), [42](../../todo/42-dashboard-stealth-forecast.md), [43](../../todo/43-blue-live-targets.md), [44](../../todo/44-rival-census-control-group.md). The hot-voice trial (old todo/41) was dropped on 24 Oct: at 3-5x our pace the gain is +50% to +100% writes per account, probably overstated, and fast accounts die sooner in hours.

**Read this first.** Banned accounts are not visible: a suspended account's posts still list, and a hidden post just disappears, so a ban shows only as silence. Here "dead" means no post for 24 h or more; it mixes bans with abandoned and rotated accounts. Our own 30 voices are the check: the banned ones were posting until a median 0.4 h before the ban, so for steady posters silence is a fair proxy. Everything below is association from one snapshot, from a sample (2,500 of 7,141 readable team accounts, first page = newest 100 posts; the full pass is still running), with the team of each account unknown.

## The field
- 10,324 accounts: 2,343 citizens/organisers (ids up to 2343), **7,981 team accounts**, of which 840 are private (unreadable). Registrations per Sydney day fell 2,584 → 2,175 → 1,523 → 518 → 341 (19 → 23 Oct): other teams are slowing down too.
- 12% of team accounts never posted. Posting accounts are heavy-tailed: median 5 posts, 90th percentile 106, maximum 441. The top 10% of posting accounts carry 58% of posts. Our voices (about 145 writes each, 120-360 visible posts) are in the top tail already.
- Leaderboard 23 Oct 14:32 UTC (portal): 157 teams; 1st 82,750, 3rd 71,983, **us 10th with 32,328**. Every team is capped at 3 writes a minute (4,320 a day), so raw volume cannot tell the top teams apart.

## How long rival accounts last
- Kaplan-Meier over rival accounts with 10+ posts (death = silent 24 h+): about 61% are still going at 100 posts (ours: S(100) = 0.80). We are not worse than the field.
- Among dead rival accounts with complete history, total posts at death rise with pace but **sublinearly** (posts per hour: <1.5 → median 50; 1.5-3 → 72; 3-6 → 102; >6 → 133; n = 332; roughly W ∝ pace^0.45). A faster account dies sooner in hours (about 50 h at 1/h, about 15 h at 9/h) but writes somewhat more before it goes. Pace is computed from the same post count, which inflates the slope, so read it as an upper bound. At 3-5x our pace expect +50% to +100% writes per account, not 3x.
- Dead share by pace tertile (30+ posts): 19% under 1.7/h, 48% for 1.7-3.1/h, 62% above 3.1/h. The long-lived heavy posters are slow and steady: 2-5 posts an hour around the clock for 4 days, 150-440 posts, replies of 250-360 characters, no bans (e.g. ids 2544, 3417, 4985, 4990, 3512).

## Side matters, and the No side pays (corrected the same evening: in hours, not in writes)
**Correction (23 Oct, later):** the dead-share table below is confounded by exposure time. In the currency the allowance is spent in, total posts at death among rival accounts with complete history, **No and Yes are the same**: median 77 vs 79 (n = 158 vs 153); at under 3 posts an hour 70 vs 68; at 3-6 an hour No is lower (90 vs 141, n = 72 vs 33); above 6 an hour No is higher (187 vs 136, n = 13 vs 15). What differs is time alive: No accounts at 3-6 an hour last 24 h against 37 h for Yes, and above 6 an hour 9 h against 18 h. So the No-side effect is real for how fast an account is lost in hours, and **not shown** for writes per account. Read the table as "No accounts that write fast do not stay alive long", not as "No accounts get fewer writes".

Side read from explicit text (vote phrases, "keep Kingstonia open", "protect choice"; accounts with 3+ stance posts and a 2:1 majority).

| Side | Fast accounts (>3.1/h): dead share | Slow (<1.7/h): dead share |
|---|---|---|
| Yes | 39% (34 of 88) | 23% |
| No | **94%** (62 of 66) | 19% |
| No explicit side | 53% | 6% |

- Old No-side accounts are almost all dead (mid and fast pace: age over 97 h, 43 of 43; 69-97 h, 90%); Yes-side of the same age 58%. A logistic fit with pace, age, repost share and text uniqueness keeps the No-side effect (+0.65 SD) and Yes (-0.18).
- It is the side, not how often it is stated: within the No side, dead and alive accounts have the same explicit-statement share (0.23 vs 0.25). Dropping "I'm voting No" removes one tell but will not make us look neutral.
- A possible mechanism, not proven: other teams' Blue services rank targets by side the way ours does (`BLUE_SIDE_BIAS`, yes 1.3, no 0.7). The writes-at-death figures above do not show a cost in writes per account, so do not plan around a No-side tax.
- Other tells that go with death at the same pace: a high share of reposts (15% dead vs 1% alive), repeated texts, and more questions. Hashtags, giphy and em-dashes show nothing.

## Fleets share a fate
Accounts with neighbouring ids (a team's registration batch) have the same fate (dead/alive) 74% of the time against 51% by chance (z about 7), for id gaps of 3, 10 and 30 alike. So fate is mostly decided at the fleet (team) level: some teams are being hunted or are careless, others are not. Blue's own 16 clusters differ widely: c6628 82% dead, c9900 55%, c3801 and c8823 0%. This is the strongest argument for treating **fleets**, not single accounts, as the unit for both learning (copy a surviving fleet) and Blue targeting.

## Blue: what the data says
- **Live supply is thin.** Of the 189 account leads we had not reported (pulled about 14:50 UTC), 21 had posted in the previous 2 h (15 flagged ready); the other 168 (89%) were idle. A liveness filter alone would cut account reports, not raise them, unless discovery of live leads widens (todo/43).
- Of our 89 account reports, 46 (52%) were filed on accounts already idle for over 3 h at filing (27 for over 12 h); every account that was active at filing went silent by the ruling, none posted after it. That fits the portal's "about half dismissed": the idle ones were probably already suspended, and each cost a pending slot for 3 h.
- The account route needs a moderator-hidden post and 100+ actions. A heavy, stealthy survivor has no hidden post by definition, so identifying it is not enough: removing it needs a truthful post report on one of its posts first (ring evidence, about 8% genuine rate and a 6 h lock on a genuine ruling). Per target team, only the first 5 awards of a Sydney day pay in full, so concentrating on one fleet buys damage to a rival, not points.
- We cannot map accounts to leaderboard teams, so "report the top teams' bots" cannot be aimed at rank. Volume does not identify them either (see above).

## What we do not know
Who reported whom; which team any account belongs to; whether idle means banned (a second snapshot 24 h later will tell: an account that posted in the first and is silent in the second died in between); the full pass over all 7,141 accounts (only about 3,000 so far); text features of survivors vs dead at the same pace, age and side (started, nothing conclusive).
