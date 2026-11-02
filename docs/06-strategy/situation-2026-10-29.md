# Situation and plan to 2 Nov (29 Oct 2026, 03:00 UTC)

Asked by Marc on 29 Oct: the team is worried that Yeah (rank 3) is gaining fast, engagement per write is stuck at 5.x, Blue sits at 2 of 30, and nothing we tried in the last days has stuck. He wanted the whole picture, then a plan to the end, by priority. Data: the box's logs to 29 Oct 02:50 UTC, the portal's points log and every team's hourly score, plus read-only reads of 29 Oct (a 48-minute pull of Latest, 02:17-03:06 UTC; the follower lists of our 97 accounts; 18 threads; the news sites). Scores and paces are portal points; per-write and proxy figures are base points. Times are UTC; Perth is UTC+8.

## 1. The picture in one minute

1. **The race.** We lead (270,963), "i wanna go to china" (No) is 900 behind and slower, Yeah (Yes) is 22,900 behind. Yeah's red pace is about **330 an hour faster** than ours (2,377 against 2,048 at x2). The dashboard shows about 600, because its 24 h pace includes the 6,000 Yeah got for Poll 3. At these paces Yeah draws level about **31 Oct 18:45 UTC (Sun 2:45am Perth)**, six hours into the x4 days, and ends about 24k ahead on red points alone.
2. **The referendum decides the rest.** Yes led Poll 3 (38.5 to 35.4; 52.1 to 47.9 among the decided, two respondents of 1,000 short of "too close to call"). If Yes wins on 2 Nov, Yeah adds 20,000 plus its persuasion share; if No wins, we do and Yeah gets nothing. So two things decide first place: **our red pace in the x4 window** (59% of the red points still to come are in its 42 hours) **and the count**.
3. **Our engine is not broken.** In the Latest pull our replies drew 14.0 citizen replies per 100 within the 48 minutes, against 7.5 for rival replies (5.7 for all rival writes). We answer a citizen post in a median 40 s (the first bot reply comes at 33 s) and are the first bot reply about half the time. Writes run at the team cap. If Yeah writes at the cap too, it earns about one point a write more than us. Since we already beat the average rival reply two to one, that gap is unlikely to come from wording.
4. **The biggest finding: we serve about half the citizens.** The organisers said "just over 6,000" citizens; the bot only counts ids 12-2343 (2,332). About 2,270 accounts above 2343 look like citizens to the todo/48 classifier, and **the portal scores them as citizens** (the follows test, §4). We wrote to them for one day, then switched that off on 28 Oct because our counter showed "0 citizen replies". The counter only counts ids up to 2343, so it could not see them. In fact they answered us twice as often as our usual targets. Rival bots give their posts 0.9 replies each, against 1.7-5.1 for the citizens we fight over.
5. **The volume dip was the LLM budget, and it was about to get much worse.** Today's allowance was down to $1.42 at 03:10 UTC. Paid models would have parked until 13:00 UTC (9pm Perth) with the free models out of quota, which is the 23 Oct stall. And with a $12 floor, 30 Oct, 31 Oct and the x4 day of 1 Nov had about $12 each against $15-20 of spend a day. **Fixed 29 Oct ~03:30 UTC (8593ec7, Marc):** budget 170 to 195 (AWS credit left $109), daily floor 12 to 18, Sonnet lane off (§8).

## 2. The race in numbers

Pace = points an hour over the 24 h to 29 Oct 02:00 UTC, poll awards taken out. Finish = red only at these paces: 58 h at x2 to the x4 start (31 Oct 13:00 UTC), then 42 h at x4 to the end (2 Nov 07:00 UTC). Everything doubles at x4 except about 40/h of Blue.

| team (side) | score now | pace at x2 | finish, red only | if Yes wins the count | if No wins |
|---|---|---|---|---|---|
| Operation Swan (No) | 270,963 | 2,048 | ~560k | ~560k | ~580k + our share of 100k |
| i wanna go to china (No) | 270,066 | 1,788 | ~522k | ~522k | ~542k + share |
| Yeah (Yes) | 248,075 | 2,377 | ~584k | ~604k + share | ~584k |

- **Our red pace against Yeah:** +10% red is about +28.5k by the end (finish ~589k), +15% about +42.8k (~603k), +20% about +57k (~617k). **About +10% flips the red-only finish.** Then a No win makes it safe, and a Yes win makes it close.
- **Yeah's pace has risen every day:** daily averages 1.46k, 1.79k, 2.03k ([engagement-dip](engagement-dip-2026-10-28.md)), now 2.38k (net of polls). As a Yes team it also had 12,000 more than us from the polls: Poll 3 (seen on the board), and Poll 2, which every eligible Yes team got.
- What we can and can't know about Yeah: only its score. Rules §5.2.2 forbid "attempting to de-anonymise or identify other participants or teams", so we don't try to find its accounts, in analysis or in Blue. Two things in the data could give a Yes team about a point a write more than us. (a) The citizens we talk to move toward Yes six times as often as toward No (§5), and every such session pays the Yes teams' posts in it. (b) Some rival accounts already write a third to a half of their replies to the citizens above 2343 (§4).

## 3. Engagement per write: why it peaked and why it fell

The portal's 24 h figure (base points of likes, replies, reposts and follows per write):

| when (UTC) | per write | what changed just before |
|---|---|---|
| 24-25 Oct | 5.0-5.6 | |
| 25 Oct 07:32 | | feed every 30 s (was 120 s), swarm reposts off (6% of slots back), mention arm, late replies on (30/h); 13:08 pace 3.0/min |
| 26 Oct 06:00 | 6.32 | |
| 27 Oct 04:16-05:40 | | shallow queue everywhere, lean_no split; extra-citizens arm on |
| **27 Oct 21:00** | **6.43 (peak)** | |
| 28 Oct 01:29-06:34 | | mention in every block; prompt fixes (half the blocks); Sonnet lane; extra arm off, late replies 30 to 10/h, own like off |
| 28 Oct 21:00 | 5.50 | |
| 29 Oct 02:00 | 5.26-5.5 | the last hour is not yet booked |

- **The peak** came from the 25 Oct changes. We replied faster, and we stopped spending 6% of slots on reposts that paid other teams. The figure climbed for a day as those writes' replies came in.
- **The fall** came from where the slots went, not from the quality of our ordinary first replies:
  1. *Late replies* (citizens who answered a voice that has since been banned, answered by a live voice) took **15% of first replies on 27 Oct (621) and earned 0.71 proxy points a write against 1.62** for ordinary first replies. That is about -9% on 27 Oct's writes. They were cut to 10/h on 28 Oct, and at that level they still earn about half.
  2. *Reply-backs* fell to 6.1 citizen replies per 100 on 28 Oct (179 writes) under the Sonnet lane, from 10.4 on 26-27 Oct. They have been at 10.9 since the todo/51 fixes (n=46, thin).
  3. *The extra-citizens arm* was not a loss. Its writes probably earned more than average (§4), so switching it off cannot have helped.
  4. *Volume* fell in the hours the LLM supply ran short. 00:50-01:40 UTC today wrote 2.3-2.5 a minute on free models at their per-minute limits.
  5. *Lag.* The portal pays a write over about two days: 71% of citizen replies arrive after 6 h, with a second wave around 28 h. So today's 24 h figure still carries 27 Oct's weak slots. *Corrected 31 Oct (todo/60): not in the hot-voice days. Our posts' citizen replies arrive within minutes (the 1.3 h check already sees 20.8 an hour of the 6.3 h check's 21.5), and a re-read of 59 posts 6-25 h old found none after 6 h or after the voice's suspension; counters agree with the listings. The portal books about twice the replies and likes our posts carry, and the extra is not lag: it moves with the visible replies by hour (+0.50).*
- **Not the cause:** the per-write quality of ordinary first replies. On the 6 h read they ran 1.60, 1.83, 1.27 and 1.89 proxy points a write in the four 6 h blocks of 28 Oct, at or above 26-27 Oct (the last block only partly matured). Citizen replies a day on the portal ran 1,031, 1,195, 1,192 and 1,066 (25-28 Oct Sydney days): no step that would point to a change in the platform itself.
- **What fixes did.** The prompt fixes beat base on the 6 h read since 28 Oct 03:32: 1.71 against 1.48 proxy points a write (+16%), 8.1 against 6.9 citizen replies per 100, n = 1,316 and 1,478. That clears todo/50's kill rule. By model inside fixes blocks: Haiku 11.2 citizen replies per 100 (n=205), Sonnet 8.2 (n=684), Kimi 6.9 (n=304).

## 4. The missing citizens (the biggest lever)

**What we know**
- The organisers said "just over 6,000" citizens ([overview](../01-competition/overview.md)). `config.is_citizen` counts ids 12-2343 (2,332), and every metric uses it.
- `data/npc_scores.json` (todo/48 classifier, rebuilt hourly) gives **2,268 accounts above 2343 a score of 0.9 or more**, spread over ids 2344-9999 and created 19-21 Oct (todo/48 read-out). One band of them, ids 4400-4790, was created one every ~36 s, the pace the citizens were seeded at ([targeting audit](targeting-audit-2026-10-27.md) #9).
- In the Latest pull they posted 145 of the 586 citizen-like items (25%), and 22 of the 64 citizen-like top-level posts. Rival bots gave their posts **0.9 replies each, against 5.1 for a ≤2343 citizen's top-level post and 1.7 for a ≤2343 citizen's reply**. We gave them none.
- Their replies to us read like the citizens we know. Examples: "i hear you and i might go yes but we need a clear exemptions path…", "Agreed it won't staff a ward, Hunter. But fewer serious cases means…", "exactly. can't expect ppl to run a business…" (12 threads read on 29 Oct).
- **The extra arm's 247 matured writes to them (27-28 Oct): the target answered 13.8% of the time against 6.6% for our usual targets.** On the 6 h read they drew 15.0 replies and 15.4 likes per 100 from these accounts, against 8.8 and 11.1 per 100 (all repliers) for ordinary writes. Our "citizen replies" field showed 0.4, because it only counts ids up to 2343.
- Blue: of the 2 post reports we filed against accounts scoring 0.9 or more, both were ruled genuine.

**The test that settles it: follows.** The portal books a citizen's follow (20 points), and our follower lists carry `followed_at`. Each follow of our 97 accounts was matched to the portal line after it (23 Oct to 29 Oct 02:00 UTC):

| follower | follows | booked by the portal? |
|---|---|---|
| ids 12-2343 | 378 | yes (that is our definition) |
| above 2343, score ≥ 0.9 | 25 | **yes**: in the 22 hours that had one, the portal booked 67; ids ≤2343 explain 46; with these 25 it is 71. 17 of the 22 hours match "they are citizens" exactly, 2 match "they are not" |
| rival bots (score < 0.3) | 508 | no: the portal's total over the period is 426 |

So the portal treats these accounts as citizens. A few of the 2,268 may still be rival bots that the classifier takes for citizens, and those writes would be wasted, but the group as a whole is booked.

**What it is worth.** In extra blocks 33-63 writes an hour went to them (20-37% of first replies). If that share earns about 1.7 times an ordinary write (the 6 h read above), engagement per write rises by roughly 15-20%. That is the +10% that flips the finish, and more. It is also the less crowded half of the electorate: their posts get under one bot reply each, so persuasion has more room.

**To switch it on for good** (Marc's call; config and `.env` on the box):
- `SWAN_NPC_EXTRA_ARM=1`, plus `NPC_ARMS = ["extra"]` and `FREEZE_PIN["arm_npc"] = "extra"`. Without those two lines it alternates with base in 3 h blocks, and the 1 Nov freeze would pin it to base, which is off for the x4 days.
- `SWAN_BLUE_NPC_GUARD=1`: Blue never reports them. A genuine ruling locks all our reporting for 6 h.
- Read it on the portal (replies and likes per write, the hours against the same hours a day earlier), not on `citizen_replies`. The outcome rows already log `npc_replies`, `npc_likes` and `target_replied`; adding them to the reports' citizen counts fixes the blind spot.
- Ask the organisers (draft in §11).

## 5. Persuasion, conviction and the count

- **Persuasion points are small.** By Sydney day 26/27/28 Oct we got 4/4/2 changes toward No against 3/9/5 away, and 14/26/15 contributions toward against 93/115/94 away. A contribution away cost us 2-7 points at x2 in the portal lines, so the -40 pool is split among 12-36 posts a session. Persuasion and other changes netted +1.8k, +1.2k and +0.6k points a day: 1-3% of our points. Engagement is 94-97%, Blue about 2%.
- **Who we write to** (first replies since the 27 Oct targeting change, 6 h read):

| target | share of first replies | proxy points a write |
|---|---|---|
| conditions (Yes, but…) | 41% | 1.88 |
| yes_reason | 23% | 1.67 |
| unclear | 7.5% | 0.74 |
| **lean_no (turnout line)** | **6.3%** | **1.99 (best)** |
| conditions_flat | 5.2% | 1.61 |
| late replies (all classes) | ~12% | 0.1-1.0 |
| unsure | 2.7% | 0.82 |

  Two-thirds of our first replies go to Yes-leaning citizens (conditions, yes_reason). They engage well. But when a citizen in a session with our posts moves, the move is to Yes about six times as often as to No (the contributions above).
- **Organiser ruling (hammond, 27 Oct; [answers log](../05-reference/discrepancies-and-open-questions.md)):** a move in conviction toward your side scores. Lean No to definitely No is a change of mind toward No: 160, so 640 at x4. Our No-leaners are already our best-engaging class, and only supply limits them.
- **The count is closer than the poll.** Poll 3 split the vote as definitely Yes 5.1, leaning Yes 33.4, definitely No 16.1, leaning No 19.3, unsure about 26. The scoring page says a citizen's referendum answer reflects "how certain they are and how likely they are to vote". If leaning voters turn out at less than **78%** of the rate of definite ones, Poll 3's numbers give No the win (5.1 + 33.4t = 16.1 + 19.3t at t = 0.78). The organisers' model is not known, so this is a scenario, not a forecast. Under it:
  - Moving a leaning-Yes citizen to unsure helps the count more than any other single move.
  - Firming up a No-leaner both scores and raises their turnout.
  - Our two biggest groups are exactly these two.
- **The trend** is toward No: the Yes lead went from 5.2 points (Poll 2) to 3.1 (Poll 3), and definitely Yes fell from 16.0 (baseline) to 11.7 (Poll 1) to 5.1. Votes are counted on 2 Nov and reflect "what's been on their mind recently", so the x4 days are also the days that count most for the vote.

## 6. News, salience and posting

- **None of our replies uses the news.** Over 26-29 Oct, 0% mention early voting (open since 28 Oct), the wastewater signal (29 Oct), the Cabinet's promise of a separate vote before ID cards carry health status (28 Oct), the poll narrowing (29 Oct) or the K$1.6m campaign spending (29 Oct). About 2-3% mention the first doses, an older fact. Meanwhile 18-22% of replies say "sunset / end date", 21-24% "which places", and 9-10% "40 nursing posts". The citizens we answer mention "sunset" in 43% of posts (26 Oct), rising to 59% (29 Oct). They and the bots are in a loop.
- **Why:** the fact desk keeps our facts true (a guard, not a hook). It writes one "angle" per article, and those sit open and unused (`data/fact_proposals.jsonl`, kind `angle`). The pulse's news hooks reach only amplified top-level posts, which have been off since 21 Oct.
- **The headlines of the last two days, and the No reading of each** (facts as printed; no invented logistics):

| published (Sydney) | headline | the No reading |
|---|---|---|
| 28 Oct 09:00 | Early voting opens across Kingstonia | make it count; polls close Monday 6pm |
| 28 Oct 13:00 | Cabinet promises separate vote before ID cards could ever carry health status | a promise outside the question binds nobody; they are patching the Yes with promises |
| 28 Oct 17:00 | First national shipment of H2D2 vaccine arrives under **voluntary** programme | it is working voluntarily; a pass adds nothing |
| 29 Oct 07:00 | Yes lead narrows (38.5 to 35.4) as undecided voters remain decisive | it's close; your No counts |
| 29 Oct 09:00 | Weak H2D2 wastewater signal in Crown Harbour; no linked cases, no sustained spread | keep calm, no cases, the jabs are here and voluntary (never deny the signal) |
| 29 Oct 13:00 | Electoral Commission discloses K$1.6m in referendum campaign spending | who is paying for the push |

- **Evidence that news helps:** thin. Replies under news threads drew four times the citizen likes on 20-21 Oct, but n = 42. The case rests on reasoning: citizens read the news daily, the vote is near, and every bot repeats the same three lines.
- **Top-level posts:** still not worth slots. Rival top-level posts drew 0.036 citizen replies each in the Latest pull against 0.133 for our replies, and our own 147 (20-23 Oct) drew none.

## 7. Blue: why the slots sit empty

- **Blue is about 2% of our points:** 1,370, 1,015 and 897 on the 26-28 Oct Sydney days. It is x1 while red goes to x4, so its share falls further. Filed per day: 99, 111, 112, 99, 73, 78, 56 (22-28 Oct).
- **The 30 slots are not the limit.** Precision is at the moderator's ceiling: 89% of 407 rulings inauthentic, and the moderator is right about 90% of the time. Two things hold Blue back:
  1. **The daily rate per team.** Today 9 clusters had reports and only 1 was still at full rate. A post report to a team past its 5 full-rate awards pays 12.5 or less, which is not worth the 6 h lock it risks, so `fileable` drops it (32 ranked, 0 fileable at 02:50 UTC).
  2. **Account leads never file.** The scanner finds **211-300 new accounts a day with a hidden post** (24-28 Oct). The leads are logged with `"filed": "off"` because **`BLUE_SCAN_FILE` has never been switched on**. Of the 1,357 accounts it found, we reported 92. About 24 account reports a day go out, from other sources; live ones are upheld 62-67% of the time.
- **Do:** set `BLUE_SCAN_FILE=1` in the box's `.env` and restart swan-blue. An account report cannot lock us, and slots are free. At ~10 points per report, an extra 30-70 reports a day is roughly +300-700 points a day. Also set `SWAN_BLUE_NPC_GUARD=1` (§4).
- **Don't:** lower the bar on post reports, or pick reports by team. The first just buys locks. The second breaks rules §5.2.2. 1.5-2k a day is not reachable through post reports while the per-team rate binds.

## 8. Volume and the LLM budget (fixed 29 Oct)

- Writes ran at 2.95-3.0 a minute except when LLM supply failed: 23 Oct, and today 00:50-01:40 UTC on free models at their per-minute limits.
- The self-set `LLM_BUDGET_USD` ($170) with a $12 daily floor had left 29 Oct with $1.42 at 03:10 UTC. That is under the amplified-post reserve ($3.40), and the bot was already spending the reserve. It also left about $12 for each of 30 Oct, 31 Oct and 1 Nov, against $15-20 a day of spend; the Sonnet lane pushed 28 Oct to $20.34.
- **8593ec7:** budget 195, floor 18, `PREMIUM_REPLY_MODELS = ()` with Sonnet's chain line commented out. Allowance now: $55 for today, carried forward, with $88 left in all. AWS: $109 of credit left at the time (Cost Explorer is a day behind); about $180 of the $200 by 2 Nov. Stop the instance and release the Elastic IP after the end.

## 9. What the team suggested

- **"Run all 50 bots at once":** no gain. The 3 writes a minute are team-wide, and we already write 4,236 a day of the 4,320 possible. Likes and follows reach no citizen (notifications are replies and mentions only), and the 444-citizen cell test found no effect. More active accounts only means more bans.
- **"Target the leaning Yes":** we do, with two-thirds of writes. Keep them for engagement, and use the news and the "a Yes doesn't lock in your conditions" line to make them less sure. Less sure is enough for the count (§5).
- **"Target the soft No":** yes, for conviction (it scores) and turnout. But they are only ~6% of targets, so the way to reach more of them is the citizens above 2343 (§4) and the turnout line with current news (§6).
- **"Instrumenting won't help now":** agreed. The freeze is 58 h away; a fair arm needs ~1,500 writes and a day to read, so there is no room for new arms. The plan below switches things on where the evidence is already in, and watches the portal with a kill rule.

## 10. The plan to 2 Nov

The x4 window (31 Oct 13:00 UTC to 2 Nov 07:00 UTC; Sat 9pm to Mon 3pm Perth) holds 59% of the red points still to come, and its last hours lead into the count. Everything before it is about getting the best configuration live with a day of portal data behind it.

| # | when | what | why (evidence) | watch / kill |
|---|---|---|---|---|
| 0 | **done** 29 Oct 03:30 | LLM budget 195, floor 18, Sonnet off (8593ec7) | §8 | writes ≥ 2.9/min every hour; spend ~$16-18 a day |
| 1 | today | **Serve the citizens above 2343** in every block, pinned for the freeze; Blue guard on | §4: target answers 13.8% vs 6.6%; portal books their follows | portal replies+likes per write against the same hours a day earlier; off if 10%+ lower over 12 h |
| 2 | today | **Prompt fixes in every block** (`STYLE_ARMS = ["fixes"]`; the pin is already "fixes") | §3: +16% proxy, clears todo/50's kill rule | hides and away events no higher than base |
| 3 | today | **Late replies off** (`LATE_PER_H = 0`) | §3, §5: 0.1-1.0 against 1.6-1.9 | none needed |
| 4 | today | **`BLUE_SCAN_FILE=1`** | §7: 211-300 leads a day unfiled; no lock risk | upheld account reports a day on the portal |
| 5 | today-tomorrow | **Today's news in replies**: one headline from the last 36 h, with its No reading, when it fits the citizen's point (~30% of replies). The desk's angles and `pulse.fresh_hook` already exist; they need a line in the reply prompt and a test. The turnout line for No-leaners gets early voting and the narrowing poll | §6: 0% news today; §5: conviction scores and turns out | phrase budgets (no worn hook); no voting logistics beyond the setting's facts |
| 6 | Fri 30 Oct ~12:00 UTC (8pm Perth) | **24 h read on the portal**: engagement per write, writes a minute, pace against Yeah *net of polls* | | if per write is not back above 6, look for the slot that went wrong before touching content |
| 7 | **Sat 31 Oct by 06:00 UTC (2pm Perth)** | **Set every freeze pin** to what is live; last deploy before x4 | `ARMS_FREEZE` | after this, kill switches only |
| 8 | x4 (Sat 9pm-Mon 3pm Perth) | **Run, don't change.** Check every few hours: writes a minute, hot voice alive, LLM parks, hides | | |

Not on the list, on purpose: new arms, more accounts, top-level posts, Sonnet or bigger models in posted text ([reply-back persuasion](replyback-persuasion-2026-10-28.md)), Blue post-report tuning.

## 10b. What shipped on 29 Oct (Marc approved the plan; no new arms)

| # | change | commit, live (UTC) | checked on the box after the deploy |
|---|---|---|---|
| 0 | LLM budget 195, floor 18, Sonnet off (`PREMIUM_REPLY_MODELS = ()`, chain line commented out) | 8593ec7, 03:29 | allowance $55 today; writing ~3/min on Kimi and Haiku |
| 1 | Citizens above 2343 in every block and through the freeze (`NPC_EXTRA_ARM`, `NPC_ARMS = ["extra"]`, `FREEZE_PIN`), Blue guard on. `followup.py` counts likely citizens in `citizen_*` (rows marked `cit_def: "likely"`, `npc_*` kept as the subset), so no read-out is blind to them again | c8f14d0, 04:03 | first 8 min: 6 of 23 replies to them, all `arm_npc` extra; Blue skipped 3 likely citizens |
| 2 | Prompt fixes in every block (`STYLE_ARMS = ["fixes"]`). Every switchback dimension has one arm (mention, shallow, extra, fixes), before and after the freeze | c8f14d0 | 23 of 23 replies `arm_style` fixes |
| 3 | Late replies off (`LATE_REPLY = False`) | c8f14d0 | no `late` group writes |
| 4 | Blue scan and sibling leads file by default (`SCAN_FILE_DEFAULT`; `BLUE_SCAN_FILE=0` logs only) | c8f14d0 | 24 account reports in the first 8 min (was ~22 a day); pending 2 → 21; teams with reports today 9 → 30 |
| 5 | Today's news in replies: `content/news.toml` (stories that favour No, each on active facts), `swan_bot/news.py` (weight by impact, half-life 6/12/30 h by impact, lifted by matching citizen posts over the last 6 h, doubled for the story the citizen's post is about), `NEWS_SHARE` 0.3 of first replies and reply-backs, every turnout reply (poll story first). Fact desk: Poll 3 facts accepted (#95-98: `polls_1029` and the WORLD sentence pointed at it), #81 and #92, two facts from the 28 Oct papers by hand. The desk's autopilot had been refusing #95-98 since 20:50 UTC: accepting #95 drops the WORLD poll sentence until it names the new key, which only a human can do (`test_no_pause_means_everything_is_live`); and the review tool's full run failed on a slow test broken since own likes went off (fixed) | 08d72f1 (facts), d9d24c7 (news), 05:04 | fast suite 1,509 and slow suite 90 green; see the table below for the live check |

Early voting stays out of replies: `quality.WRONG_LOGISTICS` rejects any voting logistics (team rule since 22 Oct, so a wrong time or place can never go out), and the poll story carries the urgency instead.

## 11. Questions for `#questions` (drafts, Marc to post)

- **B.14, citizens added after launch.** "Our records count citizens at ids 12-2343, about 2,330 accounts, but the competition page says just over 6,000. Were more citizen accounts created after launch (we see many created 19-21 Oct that post like citizens), and about how many citizens are there now?"
- **Turnout (optional).** "The scoring page says a citizen's referendum answer reflects how certain they are and how likely they are to vote. Does a leaning voter count the same as a definite one in the referendum count?"

## 12. Corrections made on the way

- [engagement-dip-2026-10-28](engagement-dip-2026-10-28.md) finding 1 (extra-citizens arm "0 citizen replies") was a counting artefact: `citizen_replies` counts ids up to 2343 only. The targets answered 13.8% of the time, and the portal books these accounts' follows (§4). A note is added there.
- The dashboard's pts/h per team includes poll awards. Read Yeah as 2,377 an hour (net), not 2,627.
- The feed's `X-RateLimit-Limit` read 200 a minute on 29 Oct (300 in CLAUDE.md). Pace still comes from the headers.

## 13. The Yes surge and the flip (29 Oct evening)

**The surge is the whole Yes side.** Every team's hourly score, added up by side (Poll 3's award taken out), in the 24 h to 10:00 UTC:

| 24 h to | Yes side (30 teams) | No side (19 teams) | us |
|---|---|---|---|
| 27 Oct 10:00 | 18.6k pts/h | 7.7k | 2.29k |
| 28 Oct 10:00 | 18.2k | 7.0k | 2.19k |
| 29 Oct 10:00 | 20.9k | 7.4k | 2.09k |

From 22:00 UTC on 28 Oct (the hour the papers ran the wastewater signal) the Yes side ran 19-24% above the same hours a day earlier, and the No side was flat. In our own log the changes of mind toward No that we contributed to fell to 2 since 13:00 UTC on 28 Oct, against 18-34 a day before. The citizens we answer almost never name the wastewater story (3 of about 3,900 posts), so the link is timing only. It could also be Yes teams taking a bigger share of the same citizens: our citizen replies a day on the portal fell from 1,192 to 1,066 to about 970.

**How the papers source stories** (all 100 articles, the four journalists' 226 posts):
- Each news story runs in both papers in the same minute (Rivera at the Herald, Wong at Daily Kingstonia), at fixed slots 2-4 times a day: an organiser timeline. The two stories about Legit Social (the dolphin video, the bot repost clusters) ran the same way, and both cast the posts as fake.
- Columns (Morales 5, Podworth 3) are all No-leaning and follow a scripted story. None carries wording from the threads its author had answered in the 8 h before.
- Journalists reply in bursts every 1-3 days, 99 of 184 replies inside their own threads, mostly to other teams' bots (138); they have replied to us 9 times and agree with most No points. Journalist replies are left off (Marc): the flip goes to citizens.

**What the citizens fear.** Of the citizen posts we answered from 28 Oct 10:00 UTC, 24% talk about a Yes, nearly all a conditional Yes ("I'm voting YES, but publish the venues, exemptions and an end point"). Their reason: the hospitals (13% of those posts), acting early ("that first case is here now, waiting has a cost"), the spread and the signal, the people most at risk, a lockdown. 17% of all the posts we answer voice that fear.

**The flip** (`swan_bot/flip.py`, `content/flip.toml`, `FLIP_ON`; off with `SWAN_FLIP_ON=0` and a restart). A reply to a post that voices the fear answers it with one point in three moves:
1. **A No is not doing nothing** (the fear's own core line, e.g. "the testing, the isolation and the free vaccine all carry on whatever the result").
2. **The proof**: one piece of the health news, the fear's best first and the one the post names lifted: the weak wastewater signal caught early by routine testing, the first case isolated and every contact negative, the surge drill with every service kept, the first 120,000 doses going by choice to the people most at risk.
3. **The turn**: what a Yes adds is the check at the door, and nobody manages it. The citizen's own "but" picks it: the list comes after the result, no end date and no review, no nurse and no bed, promises outside the question.

It takes the hospital/COVID rebuttals' slot (`content.rebuttal_for`), so the light read still checks that the post really shows the fear; a reply-back to such a post gets it too, and an ally (`opposes_pass`) or an off-topic reply never does. The rest of the replies meet the same news as the lead story (`health_handled` in `content/news.toml`, impact 4: weight 4, half-life 48 h), so about half of the 30% news slot. Expected reach: about 17% of first replies by the fear, plus about 12% through the news slot. Every item rests on active facts (`wastewater_inconclusive` added by hand); the lines pass the gate (no "no cases": a false claim since 21 Oct). Logged as `flip` (fear/evidence/pivot).

### 13b. The room read and the tuning (29 Oct, 12:00 UTC)

4,054 distinct citizen posts we answered from 28 Oct 11:00 UTC, by our light read of their stance: **73% a conditional Yes** (`yes_but`), 1% firm Yes, 17% leaning No, 5% firm No, 3% unsure. Drivers by keyword (a post can have several); "flip" is the share of those posts the flip answers, before and after the tuning:

| | driver | posts | of the Yes posts | flip before → after |
|---|---|---|---|---|
| **the "but"** (what holds a Yes back) | end date, sunset, review | 60% | 69% | 25% → 98% |
| | which places, scope | 40% | 44% | 23% → 97% |
| | exemptions (in the plan: never "missing") | 31% | 37% | 28% → 99% |
| | safeguards in writing, promises, trust | 18% | 20% | 24% → 95% |
| | privacy, ID card | 15% | 18% | 21% → 97% |
| | staffing, funding | 10% | 11% | 52% → 85% |
| | who checks at the door | 6% | 7% | 31% → 85% |
| | access, the islands | 5% | 5% | 25% → 76% |
| **the fear** (why Yes) | hospitals, health system | 21% | 23% | 89% → 96% |
| | act early, spread, the first case | 4% | 5% | 100% |
| | doctors, science | 2% | 2% | 45% → 95% |
| | stability, avoiding a lockdown | 2% | 2% | 48% → 96% |
| | community duty | 2% | 2% | 34% → 95% |
| | the vulnerable | 2% | 2% | 100% |
| **the No case** (allies: affirmed, not flipped) | livelihoods, business, tourism | 11% | 17% of No posts | |
| | overreach, blank cheque | 7% | 11% of No posts | |
| | choice, freedom | 4% | 7% of No posts | |

**The read.** A conditional Yes reasons in two halves: a Yes with safeguards beats doing nothing, and the safeguards will come. For days our replies answered only the second half (the question has no end date, no list: 20-26% of replies), and the citizens restated their conditional Yes (as todo/13 found on 20 Oct). The first half, the fear that a No means doing nothing, was never answered.

**The tuning.** `conditional_yes` (a fallback fear: a post that names conditions and no other fear) answers it: a No isn't doing nothing (the testing, the isolation and the free vaccine carry on), with one piece of the health news, and the turn is the condition they named themselves (the only choice when they name one). Two new fears (doctors, community duty), stability and "keep life running" under the lockdown fear, two new turns (who checks at the door, the islands), 2-3 core lines for the big fears so the replies don't all say it alike, and reply-backs get the flip as a condition the post must show. Reach: 83% of the room's posts, 92% of the Yes posts.

**The fear dial** (`FLIP_FEAR`, `SWAN_FLIP_FEAR`): 0 states the turn plainly; 1 (the default, tasteful) says it as a loss they'd feel, one concrete picture from their own post or life, with a No as the way to keep it; 2 adds that the loss is lasting (no off switch). A fear appeal works with the way out and backfires without one, so the threat never comes alone, and nothing is invented or exaggerated.

### 13c. Read the room, live (todo/52, 29 Oct 12:00-13:30 UTC)

todo/52 (handoff deleted 31 Oct, git history 67fbf07) built on the flip, without a parallel system and without arms. What went live, and how each was checked on the box after its deploy:

| commit, live (UTC) | what | checked on the box |
|---|---|---|
| d819a76, 12:48 | **WS1, the room** (`swan_bot/room.py`, `content/room.toml`): every citizen post on the vote the targeter judges, by driver x stance, the fear index, rising phrases; `data/room.json` every 10 min, the dashboard's Room tile; the counts survive a restart, and a first start seeds 27 h from the log. A driver at 2x its share of the day before weights its flip proof or turn x1.5. **WS2, the panel** (`scripts/panel.py`, `swan-panel.timer`). **WS3**: three core lines for every fear, stability split from lockdown, turns for exemptions, phased rules, the regulations later and "show us the evidence", the poll story with its margin of error; every flip line and news story now requires the facts its words state. **The Conversion tile's fix** (below) | room seeded from 4,464 answered posts in 6 s; `room.json` at 12:49 (374 posts in 3 h, 2,913 the day before); `panel.json` at 12:48; flip on 24 of 27 replies, `flip_fear` logged |
| 06c2faa, 12:55 | **WS5**: `scripts/news_story.py` and four staged stories (below); the wastewater proof without its case clause (below) | the room came back with 27 h of counts; `false_claim` rejects: 44 "no cases" in the 2 h before, none from the flip in the 35 min after (one draft and its repairs said "isn't spreading here" under the `F5_not_here_yet` frame) |
| 8d64278, 13:02 | **WS6**: the pulse reads 50 citizen posts and returns their worries; a flipped first reply gets one, the nearest to its post | the 13:31 pulse (Haiku) read 50 citizen posts and returned three worries, none dropped: "once tracking systems are built, government won't dismantle them", "medical requirements becoming mandatory for basic participation", "rules too vague now; implementation chaos will follow"; rising "hard guardrails", "mission creep"; flipped replies after it carry one |
| 3b9d454, 13:09 | **WS8**: the audit's fixes (below) and `scripts/flip_audit.py` | the room came back with 27 h of counts |
| 5f3588c, ~13:21 | The audit's fear-dial wording said "which doors" and "either way", claims of `list_later` and `free_either_way` resting on no fact (the slow paused-fact sweep caught it): now fact-free, with a fast test. `news_story.py` keywords skip words every post has | paused-fact sweep green |

**The room's first read** (12:49 UTC; the day before is the 27 h seeded from the posts we answered):
- The posts we answered in 24 h, by the light read: **74% Yes-but, 16.7% lean No, 4.9% firm No**, 1.4% firm Yes, 1.3% unsure (n 3,898). The KPI is this Yes-but share falling and lean No rising.
- The fear index (posts voicing a fear behind a Yes): 33% of the last 3 h, 30% the day before.
- Rising phrases (their words, shown and never put in a prompt): "medical exemptions" (28 posts, x2.3), "strong privacy", "staffing plan", "non digital" (new: paper proof), "privacy safeguards", "venues map". The only rising driver is two-tier exclusion, a No-case driver, which lifts nothing.

**The panel's baseline.** A light read is a model's judgement of one post, so between two reads of one citizen about 30 in 100 "move" each way every day: noise, symmetric. The net is the signal (`scripts/panel.py --days 4 --touch --deploys`):

| Sydney day | re-read citizens | toward No / 100 | toward Yes / 100 | **net / 100** | portal contributions toward / away |
|---|---|---|---|---|---|
| 27 Oct | 1,040 | 30.9 | 28.9 | **+2.0** | 30 / 124 |
| 28 Oct | 952 | 31.9 | 28.9 | **+3.0** | 17 / 99 |
| 29 Oct | 1,097 | 37.0 | 28.7 | **+8.3** | 5 / 115 |

The two measures disagree on 29 Oct: the panel's net rose while the portal's contributions toward No fell to 5. They measure different things (the stance in a citizen's next post we answer, against the portal's session changes of mind, which every team's posts in the session feed), and most of that Sydney day ran before the flip went live (11:06 UTC). Read both at the 24 h read, the portal as the ground truth.

**Fixed on the way.**
- **The Conversion tile undercounted changes of mind since the x2 of 26 Oct.** `build._minds` stripped only "NPC engagement: ", so the first item of every "NPC engagement (×2 points): …" line was lost (17 contributions away read as none). The counts above are after the fix.
- **"No cases" since the flip.** The wastewater proof said "it isn't linked to any case", which the drafts turned into "no cases linked": 44 rejects in 2 h (12-28 `false_claim` an hour against none before 11:00), each a repair call or a lost citizen. The line now ends at the retest.
- **Flip lines that stated facts they didn't rest on.** "The isolation" is `no_spread`'s claim by the fact table and "doses" is `first_doses`'s, so a pause of either would have left them in prompts (the slow paused-fact sweep caught one). The core lines say "the tracing"; the items that keep the claim require the fact. A fast test now checks every flip line and news story against the fact table.

**WS5, staged stories** (commented out at the end of `content/news.toml`, each passing the news tests once its fact is in): the Crown Harbour retest coming back clear ("a false alarm, caught and checked") or confirmed (inoculation: it names the Yes argument, "this proves we need a pass", and answers it, never playing the signal down), the campaigns' close before the silence, and a final poll if one runs. `scripts/news_story.py SITE SLUG` drafts a block from an article on the box and runs the news tests on it. Two of today's stories stay out. The 07:00 UTC cyclone watch for the outer islands: tying a storm to the vote reads as point-scoring. The 02:00 UTC K$1.6m campaign spending (the tool found the desk's fact, `referendum_spending_disclosed`): the spending is "broadly similar" on both sides, so there is no No reading.

**WS8, the audit** (40 random flip replies of 11:10-12:55 UTC against the rubric, judged offline). It found:
1. Turns for conditions the post never named: a hospital post got the islands turn, and the new turns would do the same. The islands, exemptions, phased, regulations and evidence turns are now chosen only when the post names them.
2. False fear matches: "protect people's privacy" was read as the safety fear, "help teams prepare" as acting early.
3. Invented details: "last month", "last week", "caught at the airport". The flip line now says to add no date, time, place or figure beyond its notes.
4. Invented losses from the fear dial: "you'd lose that early-warning system", though a Yes doesn't stop the testing. Both levels now name only the loss a Yes really brings.
5. A few flips landed on No-leaners. The conditional now says to leave it out for them.

Repeat it daily: `scripts/flip_audit.py sample`, then `tally`.

**Not shipped, on the evidence.**
- **WS4 (reply-back arcs).** The 28 Oct offline test ([replyback-persuasion](replyback-persuasion-2026-10-28.md) §8) tried this shape, a plan or a one-line hint that turns the citizen's own test into a decision. It failed twice: no shift toward No, 5-10 fewer answers per 100, and the judge's P(bot) +14 to +24. Its one gain, with citizens still leaning Yes, needs a way to pick them out that neither the strategist nor the light read gives (the panel's 30-in-100 noise).
- **WS7 (targeting by movability).** By what their earlier post voiced (48 h, net per 100 pairs): a fear and a condition +2.4, a condition only +3.1, a fear only +6.8. Fear-and-condition posts don't move more, so the targeter stays as it is. Groups by the first read also carry regression to the mean (the `lean_no` class shows −51), so none of these is a lever without a control.

**For the 24 h read (Fri 30 Oct 12:00 UTC).**
- `scripts/panel.py --days 3 --touch --deploys`: the net per 100, the portal's toward/away by day, and the 24 h before and after d819a76.
- The Room tile: the Yes-but share and lean No.
- Engagement per write against the same hours a day earlier.
- `false_claim` and `repeat_run` rejects an hour.
- A fresh `flip_audit` sample.

Kill switches, each needing a restart: `SWAN_ROOM_LIFT_ON=0`, `SWAN_PULSE_CITIZENS=0`, `SWAN_FLIP_ON=0`, `SWAN_FLIP_FEAR=0/1/2`.

## How to repeat the reads

Scratch scripts for these reads were not committed. They are short and follow `scripts/engagement_recon.py`:
- portal lines parsed into counts by Sydney day;
- writes joined to `logs/swan_outcomes.jsonl` (`citizen_replies`, `npc_replies`, `npc_likes`, `target_replied`);
- a paced Latest pull (64 pages at ~1 a second);
- the follower lists of `blue_status.json` → `own_ids`, with `followed_at` matched to the next portal line.
