# 46 — Engagement: measure it per write, reconcile it with the portal, then move it

Written 2026-10-25 (Marc + Claude). Read `CLAUDE.md` first. Read-only analysis first; nothing here posts. Any change to what we send is a `.env`/config switch with a block-based read-out (the `arm_eng` / `CONV_ARMS` pattern), logged by arm.

## Why
- Every team is capped at 3 writes a minute (180 an hour, 4,320 a day) and we use all of it, so score per day is **points per write**. Engagement is about 88% of our points; persuasion nets about 2% ([scoring-roi](../docs/06-strategy/scoring-roi.md), [hide-risk-analysis](../docs/06-strategy/hide-risk-analysis-2026-10-23.md)). +1 point per write is about +4,300 a day at x1, then x2 from 26 Oct (13:00 UTC) and x4 from 1 Nov.
- Where it comes from (`scripts/engagement_report.py`, 23 to 25 Oct, base arm, 3,888 citizen-facing writes, 19,710 engagement points = **5.7 a write**): citizen replies 884 (13,260 points, **67%**), likes 940 (4,700, 24%), follows 64 (1,280, 6.5%), reposts 47 (470, 2%). Views are capped at 500 a day and are not in that table. `engagers_first` (5.83 a write) was killed on away events, so the free levers are not the lever.
- Citizen reply rate of our writes (`conversion_report.py`, 24 h to 25 Oct 03:43 UTC, 4,061 writes, citizen replied [90% interval]): first replies 6% (3,687 writes), **reply-backs 14% [10-19%]** (176), second voices 1% [0-3%] (198). By the light read's class: conditions 9% [7-10] (1,322), yes_reason 6% (1,123), unclear 4% (941), lean_no 4% (328), **unsure 3% [2-5]** (280), off_topic 11% (51). Hot mode (from 24 Oct 10:41 UTC): first replies 5% before, 7% after.

## The measurement gap (do this first)
The portal pays about **23 citizen replies per 100 writes** (884 over 3,888). Our own reads (`logs/swan_outcomes.jsonl`, the 6 h read of our first reply) see 6% on first replies and 14% on reply-backs, about 250 replies for the 4,061 writes of a day. **Roughly 60-70% of the biggest points source is not attributed to any write of ours.** Until that is explained, every per-arm result measures a minority of the points. Possible causes (none checked): replies deeper in a thread than our 6 h read, replies to our top-level posts, replies to our reply-backs, or how the portal counts a chain (the scoring guide only says "a citizen replies to your post", 15 points).

1. **Reconcile (read-only, `scripts/engagement_recon.py`).** For a window, count citizen replies on our posts at any depth from the thread reads we already make (`swan_followups.jsonl`, `swan_outcomes.jsonl`) and compare, hour by hour, with the portal's "replies" count (`data/portal.json` events, or the activity CSV for older hours). Output: share of portal replies we can place on a write, by kind (reply, reply_back, second_voice, post, thread). If a class of reply is unplaceable, ask what the portal counts before building anything on it (`#questions` draft for Marc).
2. **One headline number: engagement points per citizen-facing write**, rolling 24 h, on the dashboard, split by first reply / reply-back / second voice. Portal engagement points over writes is the truth (hourly, unattributable); the per-write proxy is `15 x citizen replies + 5 x citizen likes + 20 x follow-backs` from the outcome reads (a result in hours). Show both and the ratio between them, so drift in the proxy is visible. Reuse `engagement_report.py`'s parsing; the tile belongs next to the speed/volume/stealth lights.
3. **A fixed weekly table**, by arm and class: writes, citizen reply rate with interval, proxy points per write. `conversion_report.py` already has most of it; add the proxy column and keep the unit "per write", never "per hour" (hours move with the day).

## Levers to test, in order of what the data says (each is a block test, killed or kept by the todo/33-style rules)
- **Class order.** `UNSURE_FIRST` (24 Oct, for persuasion, never tested) puts the class with the lowest reply rate (3%) at the front. Switch it off for alternate 2 h blocks and compare proxy points per write. Expected size is small (about 1% of points, my estimate); the cost of testing is nil.
- **Reply-backs.** Twice the reply rate of first replies. The depth test (cap 11 against 8, `depth_report.py`) is running; read it when about 100 deep reply-backs exist. Check that none expire in the queue (`lost` `expired:reply_back`, 26 in 24 h).
- **Second voices.** About 1% reply rate on 198 writes a day; those slots are worth more as first replies or reply-backs (about 150 points a day). Kept on for stealth by team decision; revisit with the reconciled numbers. Hot mode has them off already.
- **Wording.** `scripts/replay_eval.py` scores a prompt or gate change on frozen real citizen comments (F14 12.1% against F10 9.1% citizen replies is the last result). A question ending lifts reply rate (target about 45% of replies); check it against the proxy, not only against the gate.
- **Targets that reply.** Citizens who answered us before (the "engaged" arm was held as too thin on 22 Oct): re-test once the reconciliation says whether chains count.

## Guardrails
- Away events are the guardrail, as for `engagers_first`: an arm whose away or unfollow counts beat base is killed even if it earns more engagement ([scoring-roi](../docs/06-strategy/scoring-roi.md) section 4: an away hit is -160 at x2, -320 at x4).
- Hot mode changes the baseline: compare arms only inside the same mode, and note that changes of mind per 100 writes fell after the switch (toward 0.6 to 0.3, away 1.4 to 0.8, neutral 4.2 to 2.7, small counts).
- No new writes to Legit Social from the analysis. The blocks reuse existing levers; each logs its arm on the action row.

## Marc's calls
- Whether `#questions` should be asked about what the portal counts as "a citizen replies to your post" (only if the reconciliation leaves a large unplaceable share).
- Whether to turn `UNSURE_FIRST` off for the block test.
