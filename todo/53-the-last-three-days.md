# 53 — The last three days: where our rate leaks (problems, open for new solutions)

Written Sat 31 Oct 2026, ~01:30 Perth (30 Oct 17:30 UTC), by Claude with Marc. **Status: open.** Marc asked for a frank,
independent read of what holds our leaderboard position back, problems only, so that a fresh session can look for new and
novel solutions. This file is that list, with the evidence behind each item, what has already been ruled out, and the
constraints any fix must respect.

**How to use it.** Read CLAUDE.md, then this file, then [situation-2026-10-29](../docs/06-strategy/situation-2026-10-29.md)
(§1-5 and §13 for background). Pick problems, test ideas against the data (§7), and bring Marc a proposal with the evidence
and the points at stake. He approves every live change; the push to `main` is the approval.

## 0. The clock

- **Written:** 30 Oct 17:30 UTC (Sat 31 Oct 01:30 Perth, 04:30 Sydney).
- **×4 starts** 31 Oct 13:00 UTC (Sat 9pm Perth, midnight Sydney). `ARMS_FREEZE` pins the switchback arms (`FREEZE_PIN`) automatically at that time.
- **End:** 2 Nov, when the feed locks. We assume about 07:00 UTC (6pm Sydney, Mon 3pm Perth); not confirmed.
- **About three quarters of the red still to come falls in ×4.** That's 21 h at ×2 against 42 h at ×4.
- **Last deploy:** the 29 Oct plan put it at Sat 31 Oct 06:00 UTC (2pm Perth). Marc is unsure about holding to that, so ask him.
- **Marc's rule for the final days:** no new switchback arms. Ship what the evidence supports and judge it on the portal.

## 1. Where we stand (board 30 Oct 17:02 UTC)

| team (side) | score | gap | 24 h pace, pts/h at ×2 |
|---|---|---|---|
| Operation Swan (No) | 356,456 | – | 2,232 |
| i wanna go to china (No) | 354,610 | −1,846 | 2,298 |
| Yeah (Yes) | 340,146 | −16,310 | 2,483 |
| I.use.arc.by.the.way (Yes) | 283,191 | −73,265 | 1,838 |

- **China:** about 1,700/h on 27-28 Oct, so +35-40% in two days. It closed from −4.4k to −1.8k in 10 hours.
- **Yeah:** has run 5-15% above our pace all week.
- **Engagement per write** (portal, 24 h): 6.08 at 30 Oct 07:46 UTC, against 5.42 a day earlier. Writes run at 2.9-3.0 a minute, the team cap.
- **LLM spend:** $135.97 of the $195 cap at 17:00 UTC, at about $19-21 a day, which leaves roughly $5-8 to spare at the end. Running Haiku on every reply was declined because of the budget (Marc, 31 Oct).
- **Accounts:** bans are 2-3 a day. 129 accounts are left, with about 109 forecast for the end of 31 Oct against 60 in the plan.

## 2. The rule change that reorders everything (30 Oct)

**The referendum persuasion pool went from 100,000 to 500,000.**
- 100,000 is split over persuasion in the first 11 days.
- **400,000 is split over persuasion in the last 3 days** (31 Oct-2 Nov).
- It goes to the winning side only, weighted as before: a change of mind counts 1, a contribution its share of 0.5. The 20,000 base is unchanged.
- Source: the [answers log](../docs/05-reference/discrepancies-and-open-questions.md), 30 Oct. hammond said he is "very unlikely to make any further changes".

**Marc's rule of thumb:** a team's pool share ≈ its share of its side's points, plus the 20,000 base. Here that's points to date for the 100,000 and current pace for the 400,000. On the 16:00 UTC board:

| | red-only finish | if Yes wins | if No wins |
|---|---|---|---|
| Operation Swan | 588k | 588k | **763k** |
| i wanna go to china | 593k | 593k | **772k** |
| Yeah | 599k | **677k** | 599k |
| I.use.arc | 474k | 538k | 474k |

How the table was made:
- A red-only finish is score + 24 h pace × (hours at ×2 + 2 × hours at ×4).
- Poll awards are netted out of the shares: Yes teams −15,000, No teams −3,000.
- The No side has 19 teams and the Yes side 30. We hold 25% of No points to date and 32.5% of No pace; china has 24.8% and 33.5%.

What the table says:
- **If Yes wins,** Yeah is #1 by a distance and we fight china for #2. I.use.arc would need about 19% of the Yes pool to pass us; it has about 9% of Yes points.
- **If No wins,** it's us against china within about 10k. That split is decided by persuasion counts from 31 Oct, not by points.
- **The count is worth about 175k to us.**
- **Yes is the favourite, but it isn't settled.**
  - Poll 3: Yes 38.5, No 35.4 (52.1 to 47.9 among the decided).
  - The Yes side outscores the No side 2.8 to 1 (21.5k against 7.5k pts/h), and Yes is up 15-20% since 28 Oct.
  - The count weighs certainty and turnout, per the scoring page, and Poll 3 had definitely No at 16.1 against definitely Yes at 5.1.
- **The rule of thumb's weak point:** the pool is split by persuasion counts, but 94-97% of our points are engagement.

## 3. The problems, ranked by what they cost us on the board

In this section, "proxy" means the 6 h outcome read: citizen replies × 15 + citizen likes × 5 per write. The portal pays about 2.3 times the proxy (6.08 against about 2.6).

### P1. The count is the biggest lever, and nothing we run aims at it
- **Lean-No posts rank below Yes-leaners in the queue.** `targeting.READ_PRIORITY` gives lean_no 0.0, against 3.0 for conditions, yes_reason and unsure.
- **Most of what we answer is a conditional Yes.** That's 83% of the posts we answered in the 24 h to 30 Oct 07:46 UTC (the room read). Lean No is 11% of what we answer and 6% of all citizen posts on the vote (keyword read).
- **Firming a lean-No scores.** Organiser ruling, 27 Oct: lean No → definitely No is a change of mind toward No (160 × the multiplier, plus weight 1 in the pool). The scoring page says a citizen's vote reflects "how certain they are and how likely they are to vote".
- **Already known:**
  - Lean-No targets engage less on average: proxy 1.8-2.1 against 2.7 for yes_but. Fresh ones are nearly level, though: `value.DEFAULT` gives lean_no 2.6 against 2.8 for strong targets under a minute old.
  - The turnout group (242 writes, 28-29 Oct) drew 4 hidden posts, and the conversion report marked it "kill (hidden post)".
- **Open:**
  - How does the count turn stances into votes?
  - How many lean-No and unsure citizens are there? The organisers said "just over 6,000" citizens: ids 12-2343, plus about 2,270 likely citizens above that id.
  - Has a reply to a lean-No citizen ever produced a "primary contribution towards your side"?

### P2. We persuade very little, and we can't see which writes do it
- **The portal's persuasion lines, 26-30 Oct** (Sydney days; 30 Oct only to 06:49 UTC). We write about 4,200 times a day.

  | | 26 Oct | 27 Oct | 28 Oct | 29 Oct | 30 Oct |
  |---|---|---|---|---|---|
  | primary toward No | 4 | 4 | 2 | 2 | 2 |
  | contributions toward | 14 | 26 | 15 | 3 | 3 |
  | primary away | 3 | 9 | 5 | 5 | 2 |
  | contributions away | 93 | 115 | 94 | 110 | 83 |
  | primary "neither" (pays +20) | 19 | 20 | 11 | 13 | 8 |

- **The portal doesn't say which post caused a change.** Our outcome reads see only replies and likes.
- **The panel can't settle it** (`scripts/panel.py`, re-read stances). Its noise is about 30 moves per 100 each way, symmetric. The 29 Oct targeting change also changed what it measures: gross moves fell from 30-41 to about 20 per 100. Its net fell from +9 to −2 per 100 across the flip deploys, which can't be read as a verdict.
- **Earlier work found no lever:**
  - todo/25 (closed 23 Oct): no lever, wording, technique or model beat what we send, live or in five NPC-lab rounds ([npc-lab](../docs/06-strategy/npc-lab.md)).
  - [replyback-persuasion](../docs/06-strategy/replyback-persuasion-2026-10-28.md): no persuasion-wording arm passed offline.
- **Open:**
  - Can the hourly portal lines be matched to the writes in the sessions they close? They're booked at :49 each hour.
  - Is china persuading better than its points suggest?

### P3. Our own posts may be pushing citizens toward Yes
- **The posts that made a change themselves went the wrong way more often:** 24 changes away against 14 toward, 26-30 Oct.
- **The flip raises the threat in order to answer it** (live since 29 Oct 11:06 UTC): hospitals, the wastewater signal, the first case.
- **The panel's evidence is weak and confounded.** Flipped replies came out +0.9 per 100 pairs toward No; the rest −1.8.
- **The scoring guide warns:** content can backfire "even if they argued for your side".
- **Open:** does naming the threat make the Yes case more vivid? Do any content options line up with the away events in the hourly lines?

### P4. One voice writes everything
- **One persona, no matches.** All 615 replies sampled on 30 Oct (04:04-07:52 UTC) came from one persona ("priya", @lesieli_tait16). `messenger_match` was false on all 615, and `identity` was set on only 3.
- **What it disables.** The persona design depends on matching (playbook §7: an in-group messenger beats a better argument; `targeting.IDENTITIES` maps health workers, teachers and parents to personas), and that can't happen. Citizens also see the same account in every thread.
- **Swaps are automatic** (the hot pool: alerts read "HOT: @x now writes"). 6-7 voices are on standby.
- **The setup belongs to the ban crisis of 22-24 Oct** (12-21 bans a day). Bans are now 2-3 a day, leaving about 49 accounts of ban budget above plan that buy nothing.
- **Background:** todo/45's first hot-voice result (git 60406a0), [stealth](../docs/06-strategy/stealth.md).
- **Open:** does voice variety change reply rates or persuasion?

### P5. Engagement per write is near its ceiling in the current design
Proxy for first replies 29 Oct 04:03-30 Oct 01:30 UTC (n 3,486):
- **By depth:**
  - The citizen's own post (depth 0): 3.75. Depth 1: 3.94. Depth 3: 3.67.
  - Depths 2 and 4-7: 1.8-2.3. These are **76% of first replies**.
  - In a public-read sample of 315 parent posts, **92% of the posts our targets were answering came from rival bots**.
- **The queue confirms it.** At 08:00 UTC 30 Oct, 7,728 citizen posts were waiting. 71% were even-depth replies to rival bots, and only 1 top-level post under 15 minutes old was waiting: we take those as they arrive.
- **Extra citizens** (ids above 2343): 3.34 against 2.24 for classic citizens. They're 32-34% of first replies, and fresh ones are also answered as they arrive.
- **Repeat writes:**
  - A first write to a citizen this hour earns 2.93; repeats earn 2.0-2.4, and 60% of first replies are repeats.
  - In deep threads, first contact and repeat come out the same (2.04 against 2.14, classic).
  - The gap is on top-of-thread posts: 3.47 against 2.26 classic, 5.24 against 3.36 extra.
- **Open:** are there places we never write to? Citizen posts under the papers' articles, Trending, citizens who liked but didn't reply, followers of our voices.

### P6. Nobody prunes the content options that lose
- **The plain-fact opener ran 21% below the other three for two days, unnoticed.** It's a random draw, so that comparison is clean. Removed in 67fbf07.
- **Other weak-looking options** (thin numbers, and not all of them random):

  | option | proxy | n | against |
  |---|---|---|---|
  | `ask_kind` "people" | 1.85 | 157 | 2.41 for none |
  | frame F5_not_here_yet | 1.40 | 111 | stale since the wastewater signal |
  | F8_powers | 1.67 | 78 | |
  | the `health_handled` news line | 1.74 | 112 | 2.64 with no news |
  | target class unclear | 1.17 | 166 | |
  | target class conditions_flat | 1.75 | 240 | |

- **Random draws still unchecked:** `voice`, `length_band`, `rb_open` (reply-back openers), the fear dial, the flip core lines and evidence wordings.
- **Haiku-led drafts:** 2.66 against 2.41 for Kimi-led (n about 1,750 each, about 1.3 SE; `LEAD_HAIKU_SHARE` is a random draw). Declined on budget.
- **The gate:** 65% of drafts pass first time. Each repair costs an LLM call and seconds, and the value of a first reply decays fast in its first two minutes.

### P7. Citizens who answer us often get no reply back
- **Reply-backs pay more.** They earn a proxy of 2.84 (n 204, 29-30 Oct) against about 2.1 for the marginal first reply. `value.DEFAULT`'s reply_back curve stays flat at about 1.9 out to about 11 h.
- **We answer about a third.** We send about 14-18 reply-backs an hour; the portal books about 45 citizen replies an hour.
- **Most late replies go unanswered.** 7 in 10 citizen replies to a first reply arrive after 6 h ([engagement-audit](../docs/06-strategy/engagement-audit-2026-10-25.md)), and most of those get no answer. 9 reply-backs expired in 3.8 h on 30 Oct (`lost` rows, `expired:reply_back`).
- **Caps:** `TURNS_PER_SESSION` 3 per 30 min, `THREAD_MAX_DEPTH` 8, `turn_cap` skips.
- **Not the same case:** "late" replies to citizens who had answered a since-banned voice earned 0.71 against 1.62 and were cut on 28 Oct.
- **Open:** how many citizen replies to our live voices go unanswered, and why? Newest-first picking against their age?

### P8. ×4 runs on thin margins
- **News can't reach replies without a human.** The fact desk's autopilot runs `tests/test_facts.py` on the box and timed out after 900 s on 30 Oct. #108, the day's main story, waited 16 h for a human.
- **The LLM budget has about $5-8 of slack.** A day like 29 Oct ($24.86) would park the paid models for the last hours.
- **Pushes restart the bot.** Every push touching src/, scripts/, deploy/ or content/ restarts it (about a minute of writes).
- **The deploy gate skips slow tests.** The box's check runs only tests not marked slow, which leaves out the paused-fact sweep in `tests/test_facts.py`. That sweep caught a flip wording bug on 29 Oct.
- **People are thin on the ground.** Who watches between Saturday night and Monday afternoon, Perth?
- **Open:** what fails silently at 3am on Sunday?

### P9. China improved 35-40% in two days, and we don't know how
- **Yeah runs 5-15% above us.**
- **Everyone has the same 3-writes-a-minute cap,** so they either get more points per write than we do or score from somewhere we don't: Blue, views, or persuasion. For Yeah, the Yes tide also pays contributions toward Yes.
- **The rules allow looking, within limits.** Rules §5.2.2 forbid identifying other teams. Analysing public posts, and what draws citizen replies whoever wrote them, is allowed (§5.2.1).
- **Open:** what do the replies that draw citizen replies look like, across every bot in Latest?

## 4. Checked 30-31 Oct, not problems
- **Yes teams ganging up on us:** no sign of it.
  - New bans per day: 21, 11, 5, 5, 3, 3, 2 (24-30 Oct).
  - Hidden posts: about 31 a day on 24 Oct, 2-7 a day since.
  - Rival-bot replies under our replies: 11.7 → 1.4 per 100 (22-30 Oct).
  - Coordination inside the competition is allowed anyway (§5.2.1).
- **Volume** is at 2.9-3.0 a minute of the 3 cap.
- **Views** hit the 500 cap every day.
- **Blue** is about 2% of points, limited by the per-team daily rates and by locks after "genuine" rulings.
- **Bans** are well under plan.
- **The Blue tile's "36/30 pending"** was a display artefact, fixed in 2b40161 and e6909fd. The ledger counts reports the platform has already ruled.

## 5. Ruled out before (bring new evidence before re-proposing)
- **Top-level posts.** Our 147 posts on 20-23 Oct drew no citizen replies; rival top-level posts draw 0.036 each.
- **More accounts writing at once.** The cap is team-wide.
- **Likes and follows to reach citizens.** Notifications are replies and mentions only, and the follow/like cells (444 citizens) showed no effect.
- **Sonnet for replies.** 8.2 citizen replies per 100 against 11.2 for Haiku (28 Oct).
- **The late-reply group** (to citizens of banned voices).
- **The value-pick queue:** within noise of newest-first (todo/49).
- **engagers_first:** away events beat base.
- **mirror_concede.**
- **Reply-back arcs** (todo/52 WS4): failed offline twice.
- **Targeting by movability** (WS7).
- **Persuasion-wording arms** (todo/25, the NPC lab, `rb_ab`).
- **Amplification and Trending pushes:** paused since 21 Oct; our amplified posts look as coordinated as the rings we report.
- **New on 31 Oct:**
  - Capping repeat writes per citizen: no gain where it would bite.
  - Boosting extra citizens or top-of-thread posts in the queue: the fresh supply is already taken.

## 6. Live watches from 30-31 Oct
- **67fbf07** (live 30 Oct 17:04 UTC):
  - The plain-fact opener is gone.
  - New flip proof `evidence.hospital_plans` (requires `hospital_contingency_protocols`, fact desk #108). It's the hospitals fear's first proof and a proof for "acting before it spreads".
  - Facts #108 and #109 accepted (#109's note reworded).
- **First 17 minutes** (51 writes):
  - 3.0 a minute; only the three remaining openers were drawn.
  - `hospital_plans` was used in 5 of 42 flips. One reply invented an anecdote ("My daughter's school already has the surge plan posted in the office…"), 3 were clean, and 1 dropped the proof.
  - `copied_fact` rejects: 3 in 51 writes, against 2.2 per 100 before.
- **To read after about 12 h:**
  - The proxy by opener. If the −21% holds, expect about +5% per write. Note that on 28 Oct the plain-fact opener did slightly better (2.28 against 2.02).
  - A `flip_audit` sample of the `hospital_plans` replies.
  - The `copied_fact` rate.
- **565357a** (Marc): the Room tile is off the dashboard; the bot still writes `data/room.json`.

## 7. Data, and how to repeat the reads
- **On the box:** `ssh swan-ec2`, then `~/ctn`. The bot is live, so run reads with `nice -n 19 .venv/bin/python`.
- **`logs/swan_actions.jsonl`** (about 320 MB) holds every action in time order. Seek to a start time by binary search on the line timestamps rather than reading from the top.
  - Reply rows carry `target_author`, `depth`, `flip` (fear/evidence/pivot), `flip_fear`, `opener`, `ask_kind`, `voice`, `lead`, `backend`, `read_stance`, `target_class`, `npc_score`, `news`, `arm_*`.
  - `lost` and `skip` rows give the funnel.
- **`logs/swan_outcomes.jsonl`** (join on `post_id`): `act` "outcome", with check 0 at about 1.3 h and check 1 at about 6.3 h.
  - Since 29 Oct, `citizen_*` includes likely citizens (`cit_def` "likely"). Older rows count ids ≤ 2343 only, so add `npc_*` for those.
  - Proxy = 15 × |`citizen_repliers` ∪ `npc_repliers`| + 5 × `citizen_likes`.
- **`data/portal.json`:** the portal's hourly lines ("NPC engagement (×2 points): 53 likes, … 1 primary contribution to a change of mind towards your side"). Parse them into counts by Sydney day; `account_log` gives bans over time.
- **Other data files:**
  - `data/team_scores.jsonl`: every team's score each hour. `data/team_sides.json`: each team's side.
  - `data/swan_state.json` → `targeter.candidates`: the queue, with `depth` and `parent_author`.
  - `data/latest_snapshot.json`: the last ~15 min of Latest, with author ids.
- **Existing tools:**
  - `scripts/conversion_report.py --split <UTC>`
  - `scripts/panel.py --days N --touch --deploys`
  - `scripts/engagement_recon.py levers`
  - `scripts/flip_audit.py sample | tally`
  - `scripts/value_table.py`
  - `scripts/news_story.py latest`
- **Platform reads:** public only (`get_post`, `replies`, `likers`), paced at about one every 1.5 s, from the box. Never write (CLAUDE.md guardrail 8).

## 8. Constraints on any solution
- **Approval:** Marc approves every live change, and the push is the approval. It's live in about 2 minutes, and src/, scripts/, deploy/ and content/ restart the bot. Facts go through `scripts/facts_review.py` on the laptop (team Mongo); the commit author is the approver.
- **Guardrails** (CLAUDE.md):
  - No posting, liking, following or reporting from a session.
  - No identifying other teams (§5.2.2).
  - No prompt injection aimed at citizens.
  - No voting logistics (`quality.WRONG_LOGISTICS`).
  - Only in-game facts (`content/facts.toml`; every flip line and news story requires the facts its words state, checked through `facts.SAYS`). Watch the false-claim patterns: "no cases", "the virus isn't here".
- **The final-days rule:** no new switchback arms.
- **Tests:** `scripts/t.sh` (fast, about 45 s, the same set the box runs). `scripts/t.sh slow` for the sweeps.
