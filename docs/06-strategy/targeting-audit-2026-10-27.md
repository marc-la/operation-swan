# Targeting audit, 27 Oct 2026 (blind, from the end product back)

Marc asked for an independent read of who we reply to, what they do, and what we miss. Read-only: the box's logs (19,230
citizen-facing writes, 21-27 Oct), the portal's hourly lines, a 15-minute Latest snapshot and about 400 read calls (no
writes). It replaces todo/47 (class mix), whose numbers it re-checks. What shipped from it is at the end.

## What the data says
| # | Finding | Evidence |
|---|---|---|
| 1 | **Speed is the lever.** Reply rate falls with the target's age at send: <2 min 10.5%, 2-5 min 7.1%, 5-10 min 5.1%, 10-240 min 3-5% | 23-27 Oct replies with t_made/t_sent |
| 2 | `shallow` beat the other queue arms on 26 Oct: reply 9.4% vs base 7.4% / fresh 7.9%; proxy points a write 1.69 / 1.24 / 1.55; created->sent median 52 / 140 / 74 s | one day, intervals overlap; matches #1 |
| 3 | ~85% of `lean_no` targets had no No in them: Yes-buts stating conditions flatly ("A full list of venues, date-stamped limits, and clear exemptions. That's the bare minimum."). They got priority 0 and the turnout line ("they already lean No... every No counts"), as did a few stated Yes voters ("I'm still voting YES") | 1,341 targets; 1,136 via the "doubt, no hedge" rule |
| 4 | About half of the ~1,800 posts a day skipped as `off_topic` were on the vote in other words ("i havent seen a full rules list published yet and thats exactly what is holding me back") | 23 skips in a live slice, re-judged with their real parent |
| 5 | todo/47's class gap is real after controls: unclear/unsure/off_topic reply 3.2 points less than conditions/yes_reason adjusted for age, 1.9 less within the same citizen. Unsure -5.2, off_topic -4.9, unclear -2.3 | Mantel-Haenszel by age bucket and citizen |
| 6 | **Our persuasion labels are noise.** Follow-up regex: 118 moves to No, 81 to Yes, from 33 and 28 citizens. Portal over the same days: 102 contributions toward us, 351 away, 930 neither. Away has risen daily (26 Oct: 131 away, 21 toward) | logs/swan_followups.jsonl vs data/portal.json |
| 7 | ~47% of citizen replies arrive after the 6.5 h outcome check (a second wave ~28 h later), so our reply rates are about half the true ones | 120 replies 40-60 h old, replies read again |
| 8 | Reach: 2,130 of the 2,332 known citizens written to, median 6-7 times; reply rate barely falls with touches (9% first, ~7-8% later). 7 accounts wrote all 4,372 writes of 26-27 Oct; ~14% of replies share stock lines ("doesn't add a nurse or bed", "school gate", "40 nursing posts") | |
| 9 | **The citizen list is incomplete.** Ids 4400-4790 were created 19 Oct 17:00-20:53 UTC at one every ~36 s with real-name display names (the seeded pace, 25-42 s); sampled accounts post in short sessions every 1-2 days in the citizen style (4580, 4516, 4589, 4592, 4760; 7701 near 20 Oct 21:00). The band also holds team bots (4464 posts hourly). `is_citizen` drops every id > 2343, so the bot never answers them and our metrics never count them. todo/48 (27 Oct): ~2,200-2,600 of them, created 19-21 Oct, 39% of citizen posts in Latest | get_account / account_posts reads; [todo/48](../../todo/48-citizens-above-2343.md) read-out |
| 10 | Time of day: 3-5% at 2-5 pm Sydney, 8-11% overnight, at the same target age (crowding) | |

Smaller: answering citizens who once liked us gets 10.0% vs 7.3%; after 6+ unanswered touches a citizen replies 5.9%; we reply back on ~66% of our posts a citizen answered.

## The vote, turnout and early voting (reasoning, to confirm in `#questions` B.12-14)
- Early voting opening 28 Oct is in-world fact (setting page). The scoring page says the referendum "asks every citizen" at the count and an answer "reflects their vaccination views, what's been on their mind recently, how certain they are and how likely they are to vote". So votes are probably taken on 2 Nov and **recency matters**: a base push belongs on 31 Oct-2 Nov, not 28 Oct.
- Turnout and certainty are not scored views (§2 lists the three vaccination views and other topics). They change the count, not points.
- "Soft Yes won't turn out" is already in the polls: only citizens choosing Yes or No count. Poll 2 (Yes 39.3 / No 34.1) is ~7 points among the decided; it has to come from conditional-Yes and unsure citizens, which is what F14 and the `lean_no` fix aim at.
- Soft No to hard No: explicit No posts are ~1% of targets, so we cannot find them by stance. Our identifiable base is ~1,041 citizens who liked or answered us (288 follow us).

## Shipped 27 Oct (Marc)
- `QUEUE_ARMS = ["shallow"]`: shallow in every block (the 3-arm machinery stays).
- `lean_no` split: a flat demand naming conditions is `conditions_flat` (priority 3.0, no turnout line, in the mention pool); a first-person stated Yes is never a No-leaner; an explicit vote No always stands. Over 14,918 logged targets: 543 leave `lean_no`, 648 stay.
- `ON_VOTE`: words like rules list, expiry, review, oversight, regulatory, privacy, "votes" put a post on the vote (skip and class only; follow-up labels keep `REFERENDUM`). Live slice: off-topic skips 23 -> 15, the rest small talk.
- todo/47 option 1: in the newest-first pick, unclear/unsure/off_topic count as `DOWNRANK_MIN` = 2.5 minutes older.
- Arms freeze at midnight Sydney 1 Nov (`ARMS_FREEZE`, `FREEZE_PIN`): the x4 days run the winners. Set each pin to its read-out winner before then.

Expected: shallow about +15% engagement a write (+3k to +7k points a day at x2); the class changes a few tenths of reply rate, mostly the right argument to the swing citizens. Next: todo/48 (citizens above id 2343, and Blue's final check).
