# Engagement audit (25 Oct 2026, 06:30 UTC): the number, what it is made of, what is left to try

Asked by Marc on 25 Oct (todo/46): measure engagement properly, find out whether we have tried everything, say what the data and the trend say, set a goal and a red/amber/green light, and put the number on the dashboard in place of Accounts left. Data: the box's logs and the portal's hourly points log up to 25 Oct 05:19 UTC, plus two small public read-only samples of our older posts (below). Numbers are base points (x1) unless stated. Everything here is association from our own logs; where a result rests on a small sample it says so.

## 1. Bottom line

1. **The number is engagement points per write: 5.0 now (24 h, base points), flat for two days.** Writes are at the team cap (4,314 in 24 h; 3 a minute is 4,320), so score per day is that number times 4,320. +1 point per write is worth about **87,500 points** from now to the end of 2 Nov at x1 to the end of 25 Oct, x2 for 26-31 Oct and x4 for 1-2 Nov (4,320 writes a day; the dashboard tile prints the figure).
2. **The "measurement gap" is a time lag, not missing points.** The portal pays about 23 citizen replies and 25 citizen likes per 100 writes; our 6 h outcome reads place 25% and 27% of them (24 Oct UTC day). In a public read of 148 of our replies 24-44 h old, **71% of the citizen replies and 66% of the citizen likes arrived after 6 h**. The long tail on first replies alone accounts for about 80% of the portal's replies and likes. No question for the organisers is needed: the portal counts replies and likes on any post of ours at any time. *31 Oct: true for 24 Oct's long-lived voices, not for the hot-voice days since: replies now arrive within minutes and none after 6 h or after a suspension, while the portal still books about twice what our posts carry ([todo/60](../../todo/60-reply-backs.md)).*
3. **Nearly all of what we have varied does not move the number.** Frame, lever, ask, length, model, persona, voice, follow/like cells: citizen reply rates sit between 5% and 8% with overlapping intervals. A model fitted on everything the bot knows at pick time predicts which reply gets a citizen reply no better than chance on a held-out day (AUC 0.52). Three things do show a signal: **how new the target post is** (about 9% reply for a post under 5 minutes old, 1-5% for posts 15 minutes to 6 hours old), **replies to reply-backs** (about twice a first reply's rate), and a small early sample of **replies under news-article threads** (4x the citizen likes, 42 writes).
4. **Slots are the thing we can still change.** About 6% of the write budget (257 of 4,314 slots a day) goes on swarm reposts, 82% of them on other teams' posts and 7% on ours; nobody has measured what they earn us. Another third of first replies go to posts older than 15 minutes (reply rate 1-5%) because that is what is left in the queue between bursts of new posts.
5. **A realistic gain from the levers below is +10% to +20% (5.0 to about 5.5-6.0); the green line at 6.0 needs most of them to work.** Nobody else on the board is visibly doing better than us per write: over the last 24 h we gained about 1,040 points an hour, the leader about 950 an hour once its poll award is taken out, and third place about 600. The gap to the top is the early days and the poll awards, not engagement per write.

## 2. The metric and the light

**Engagement per write** = (likes x 5 + reposts x 10 + replies x 15 + follows x 20 - unfollows x 20) booked by the portal in the last 24 h, divided by the live writes of the 24 h ending one hour earlier (the portal books an hour about an hour late). Every write counts, reposts included, because each spends one of the team's 3 slots a minute. Views (capped at 500 a day, and reached every day), changes of mind and Blue are left out. Counts are used, not the portal's points, so the x2 from Sydney midnight on 26 Oct (25 Oct 13:00 UTC, 9pm Perth tonight) and the x4 from 1 Nov do not move it. Code: `engagement_figs` / `engagement_tile` in `src/swan_dash/build.py`; it replaces the Accounts left tile. The account numbers stay in the detail of that tile and in Bot > Accounts by day.

| light | per write | why this line |
|---|---|---|
| green | 6.0 or more | the goal: +1 on the median (Marc, 25 Oct), shown on the tile |
| amber | 4.5 to 6.0 | where we are: 24 h windows from 23 to 25 Oct ran 4.5 to 5.9, median 5.0 |
| red | under 4.5 | worse than anything since volume reached the cap |

On the box's data at 06:45 UTC the tile reads **4.95, amber**, 0.16 above a day ago (4.79) and below two days ago (6.02, a window when volume was lower and rising, so each write was still collecting the tail of the day before).

How to read it:
- It is a rate at steady volume. After a stall or a restart it is flattered for a day (writes stop, the tail of earlier writes keeps paying), and while volume ramps up it is understated. That is why 22 Oct reads 3.3 over the Sydney day and 8.3 over 03:00-12:00 UTC. At the cap, as now, it is clean.
- Time of day moves a 6 h window a lot (4.2 from Sydney 22:00 to 11:00 on 24 Oct, 7.3 from 11:00 to 17:00 on 25 Oct). The 24 h window cancels it; judge changes by that, never by one block.
- It cannot see a change for about a day, because the payout is slow. A change is judged early by the proxy (citizen replies and likes on the 6 h read, per write) and confirmed on the 24 h figure.

Where the points come from, by Sydney day (the portal's lines, base points):

| day | writes | engagement per write | replies | likes | follows | reposts | views | other (persuasion, Blue) |
|---|---|---|---|---|---|---|---|---|
| 23 Oct | 2,481 | 5.1 | 59% | 22% | 6% | 3% | 4% | 984 |
| 24 Oct | 4,208 | 5.2 | 60% | 23% | 5% | 2% | 2% | 1,696 |

Persuasion and Blue are about 7% of points. Changes of mind net close to zero: 22 toward, 59 away, 170 neither over the last 24 h.

## 3. Everything we can do, and whether we have tried it

| mode | tried | what the data says | verdict |
|---|---|---|---|
| First reply to a fresh citizen post | 9,800 reads | 6% citizen reply in 6 h, 0.19 replies and 0.22 likes a post over 2 days | the engine; improve the targets, not the words |
| Reply-back to a citizen who answered | 767 | 13% reply vs 7%; 76% of replies seen within 6 h are answered, a median 6 minutes later; **0 of 9 replies that arrived 5-17 h later were answered** (sample 160 posts, 24 Oct) | best per write, and its coverage of late replies is the gap (lever 4) |
| Second voice on a doubt we answered | 908 | 0-1% reply | dead. Off in hot mode |
| Top-level persona post | 147 (20-23 Oct) | 12.6 views a post, **0 citizen replies**, 0.02 citizen likes; the 11.7 likes are ours | dead as an engagement source |
| Own thread | 286 (20-21 Oct) | 0.024 citizen replies and likes a post | dead |
| Reply under a news-article thread | 42 (20-21 Oct) | 0.07 replies (same as ordinary), **0.29 citizen likes a post vs 0.064** | not tested at scale; lever 3 |
| Journalist reply | 18 | 0.11 likes, 0.06 replies; too few | untested |
| Quote-repost | 203 | not measured | untested |
| Plain repost (swarm) | 1,005 | points go to the original author; 82% of the swarm's reposts are on other teams' posts | costs 6% of the slots; lever 1 |
| Follow a citizen, like their post (free cells) | about 450 citizens each | points per citizen: none 1.21, follow 0.90, like 1.44, both 0.77 (se about 0.2); follow-back 1-3% | no effect found. Free, so harmless; do not expand |
| Boosters liking our posts | 20-21 Oct heavy (about 34 likes a post, n=43); since then one like per reply | heavy: 0 citizen replies, 0.03 citizen likes, 0 Trending hits; one like vs none: no difference | no gain measured; stealth cost measured. Leave at one |
| @mention a citizen, hashtags, replying to a citizen's other posts, re-engaging citizens who answered before | no | the bot's gate removes hashtags; the `engaged` group is capped at 5 and its pool is 0 | untested. A mention notifies a citizen who has not replied to us: ask before trying, it can read as spam |

What the first-reply data says (6 h read, 22 Oct 12:00 to 25 Oct 00:00 UTC, 6,975 first replies):
- **Freshness.** Reply rate by minutes between the citizen's post and ours: under 2 min 8.7-10%, 2-5 min 5-9.5%, 5-15 min 4-6%, 15-60 min 1.6-4.8%, 1-6 h 1-3%, over 6 h 3.5-5.5%. In hot mode 53% of first replies go out within 5 minutes (median age at send 4.6 min; pick-to-send is 1.1 min, so the time is spent before we pick the post up). A third are older than 15 minutes.
- **Contacts.** No decay with how many times we have written to a citizen (5.9% first contact, 4-6% after many). Writing again within 1-6 h of the last write is worse (2.6%). 1,157 citizens got 4,078 writes in 24 h; 37% of writes went to citizens we had already written to 8 or more times.
- **Class of target.** Regex class: conditions 9%, yes_reason 8%, unclear 5%, lean_no 4%, unsure 5%. The `UNSURE_FIRST` ordering puts a 5% class first and has never been tested for engagement.
- **Funnel.** 260-365 new citizen posts an hour, about 80 off topic, 92-160 answered, 60-90 queued. Supply is about twice the slots, so ordering decides which posts get a reply.
- **Hot mode.** Voices last hours: six hot voices lost since 24 Oct 10:41 UTC. A citizen reply arrives hours after our post, by which time the voice is suspended and its notifications cannot be read. The late replies cannot be answered by that voice.

## 4. Levers, in the order the evidence supports

Sizes are per write on the 5.0 base, from the numbers above; each is an estimate, not a result. Together they would give about +0.5 to +1.0.

| # | lever | evidence | size | cost / risk | who decides |
|---|---|---|---|---|---|
| 1 | **Give the swarm's repost slots back to first replies.** Pause reposts of other teams' posts (210 a day), keep or drop the 17 of ours | 257 of 4,314 slots (6.0%) a day; reposts earn nothing for us unless the post is ours | +0.3 (a replacement write earns the average) = about +26,000 points to the end | the swarm's other job, helping No-side posts, is not measured; `SWARM_OFF` is instant | minhnguyenhoang (owner) with Marc |
| 2 | **Find new posts faster.** `REFRESH_S` is 120 s, set when the feed route allowed 10 reads a minute. It has been **300 a minute since 22 Oct 02:04 UTC** (`logs/feed_reads.jsonl`; the API doc still says 10). The bot reads 1.8 times a minute | reply rate 9% under 5 min vs 1-5% later; a third of first replies are older than 15 min | +0.1 to +0.25 | none on the read budget (3-4 reads a minute of 300); check the hide rate does not move | Marc: one config line, watch the share of replies under 5 min (shows in an hour) |
| 3 | **Reply under news-article threads for a block.** Source `news` is in the code and was used 20-21 Oct | 42 writes, 12 citizen likes against 2.7 expected at the usual rate; replies unchanged | +0.1 to +0.3 if it holds on 10-20% of writes; could be nothing | needs enough article comments per hour; hide risk unknown | Marc: 2 h switchback blocks at 20% (the `arm_eng` pattern), read after 24 h |
| 4 | **Answer late replies.** Replies arrive 5-17 h after the post; the notification goes to a voice that may be suspended. Read late replies from the public thread and answer them from the voice that is alive | 0 of 9 late replies answered; reply-back earns 1.5-1.7x a first reply | +0.1 to +0.2; larger if the pool of late replies is as big as the tail says (about 600 a day) | a different persona answering is the second-voice pattern (0-1%), which is the risk; try it on a block | Marc, after a test of 100 |
| 5 | Order by class (`UNSURE_FIRST` off) | 5% vs 9% | +0.05 | nil | Marc, already in todo/46 |
| 6 | Stop spending on levers with no effect: follow/like cells | cells section | 0 | nil | no action needed |

Not worth doing, and why: rewording (the replay eval moves the gate, not the portal); more second voices; top-level posts or threads; a prediction model for target choice (AUC 0.52); more following (1-3% follow back at -20 points if they leave).

**Experiment rules** (todo/46 section on guardrails stand). A 6 h read sees about 30% of the payout, so use it to rank arms and the 24 h figure to confirm. Each arm needs about 1,500 writes (a 9 h block total at 170 an hour) to separate a 30% difference in replies at 90%; the `tail` command below gives a matured read at 24-44 h. Judge arms inside the same mode (hot or not), and keep the away-event guardrail.

## 4b. The accounts that do not write (Marc, 25 Oct)

One voice writes at a time, so up to 49 other accounts can act without spending a write slot: likes, follows and views have their own 30-a-minute budgets (about 43,000 a day each, of which we use about 6,000 likes and 300 follows). Reposts are not free: they share the 3-a-minute write route. The account count is not the constraint; the slots are. What the evidence says about each free action:

| action | what we do now | what it can reach | evidence |
|---|---|---|---|
| Like a citizen's post (we replied to) | 1,955 a day from the voice | nothing: notifications are only replies and mentions (`notifications()` in the client), so a citizen never learns of a like or a follow | cell test, 444 citizens: 1.44 points a citizen vs 1.21 with no like (se 0.2): no effect |
| Follow a citizen | 300 a day | same: no notice. A citizen follows us back 1-3% of the time | cells: follow 0.90, follow+like 0.77 vs 1.21: no effect |
| Like our own posts (boosters) | now one like per reply, 3,752 a day. **20-21 Oct we did it heavily**: 43 top-level posts with about 34 booster likes each, plus replies and reposts (`amp_plan` / `amp_measure`) | Trending ranks on recent likes, replies and reposts | **Heavy (n=43): 0.02-0.03 citizen likes and 0 citizen replies a post at 1 h and 6 h, 36 views a post of which about 34 were our own, 0 Trending hits.** Light (14 likes, n=5) and none (n=5): the same. Today's one like per reply: 0 likes 0.077 replies and 0.050 likes a post (n=1,002) vs 1 like 0.056 and 0.065 (n=7,544): no gain |
| Views | with each like | our views earn nothing | n/a |
| Citizens following us | whatever the NPCs do | Home gives followed accounts prominence | 52 follows a day to the whole team; the one lever that compounds, and none of ours moves it |

So the free budgets have no channel to a citizen except Trending (and Home, for citizens who follow us), and **the dose has already been tried**: the 20-21 Oct amplifier put about 34 likes on each of 43 top-level posts and bought no citizen engagement and no Trending place. Caveats: new accounts with no followers, top-level posts rather than replies, early game, 6 h reads; and it is the same behaviour the in-game rules call reaction farming (LS.5.3, open question 4).

Against that, the cost side: the hide rate was 0.36% before 21 Oct 12:00 and about 1.4% since rivals began reporting; a converted booster's first top-level posts were hidden 5 of 15 times against 1 of 122 for original voices (`hide-risk-analysis-2026-10-23.md`), and the cause is suspected to be the boosters' earlier like-ring history. **Read the stealth side with care (Marc, 25 Oct):** the rise from 0.36% to 1.4% coincides with the organisers' push for everyone to Blue-team, with buffs, so it cannot be put down to anything we did, and only one or two teams are auto-flagging us. The 5-of-15 booster figure is a small sample with an unknown cause. So the stealth cost of self-liking is not established; the reason to leave it at one like is that **34 likes a post bought nothing**. (The ring self-audit alert of 25 Oct 07:05 said our amplified posts look as coordinated as the Trending leaders; I have not checked that alert.) The free actions are not a route to the +1; keep them at today's level.

## 5. What other teams and the leaders do

We can see only their scores. Gains over the last 24 h to 06:02 UTC on 25 Oct: us +25,060 (1,044 an hour); first place +29,808, of which +7,063 landed at 21:02 UTC on 24 Oct, when Poll 2 was counted (08:02 Sydney), so about 22,700 (947 an hour) without it; third place +20,100, of which +5,656 at the same time, about 14,400 (600 an hour) without it. We got +846 at that time. That fits the top teams being on the side that led Poll 2, and says their lead is the early days plus poll awards. In a 1.5 h window one team below us (rank 10) gained 1,244 an hour; `data/team_scores.jsonl` has the all-team series from 25 Oct 04:32 and the leaderboard on the dashboard shows points an hour per team over 24 h. If someone does beat 6 points per write consistently, it will show there. The rival census says the heavy steady posters write 2-5 an hour for days with 250-360 character replies; nothing in it points to a different engagement mechanism.

## 6. Read-outs and how to repeat them

```bash
python scripts/engagement_recon.py placed --day 2026-10-24     # on the box: portal replies/likes vs the 6 h reads (25%, 27% on 24 Oct)
python scripts/engagement_recon.py tail --n 150                # public reads of 24-44 h old replies: when citizens reply and like
python scripts/engagement_recon.py tail --n 160 --cover        # also whether the writing voice answered each citizen reply
python scripts/engagement_report.py --hours 72                 # arms and free cells, as before
```

Tail sample, 25 Oct 06:30 UTC (148 of our replies 24-44 h old, random from 2,871; a second sample of 160 replies 10-18 h old for the coverage):

| delay after our write | citizen replies | citizen likes |
|---|---|---|
| 0-1 h | 5 | 11 |
| 1-6 h | 3 | 0 |
| 6-24 h | 9 | 17 |
| over 24 h | 11 | 4 |
| all | 28 (0.19 a post) | 32 (0.22 a post) |

Small samples: read the 71% and 66% as "most", not as exact. The 6 h reads themselves show growth from 1 h to 6 h (504 to 654 citizen replies on 10,543 posts). Coverage sample: of 18 citizen replies, 5 of 9 that arrived within an hour were answered by the same voice and **0 of 9** that arrived after 5 h.

## 7. Corrections made on the way

- The feed routes are **300 a minute**, not 10, since 22 Oct 02:04 UTC (200 for a few hours on 22 Oct). CLAUDE.md and `api-reference.md` carried the old figure; both are updated with the date. Pace from the headers, as before.
- The 6 h read is a partial measure (about 30% of citizen replies and likes). Per-arm results in `conversion_report.py` and `engagement_report.py` are valid for ranking arms, not for sizing them.

## 8. What was switched on (25 Oct, Marc: implement, dial down on backlash)

| change | where | dial it down |
|---|---|---|
| Swarm reposts off (was 2 per scan, 257 slots a day) | `config.SWARM_REPOSTS_PER_SCAN = 0`; owner minhnguyenhoang to confirm | set it back to 2 |
| Feed refresh every 30 s (was 120 s) | `config.REFRESH_S` | set it back to `2 * 60` |
| Citizens we wrote to 1-6 h ago go last, not never | `config.RECONTACT_GAP_S`, `Targeter.next_target` | `None` |
| `UNSURE_FIRST` off | `config.UNSURE_FIRST` | `True` |
| Own like on alternate replies again (halves the booster likes, gives a control) | `config.OWN_LIKE_VARIANTS = [True, False]` | `[True]` |
| `arm_eng` blocks are now `base` / `mention` (`engagers_first` was killed) | `config.ENG_ARMS` | `ENG_ARMS = ["base"]` |
| **@mention arm**: in a mention block, half of ordinary first replies name one other active citizen | `src/swan_bot/mention.py`, `MENTION_SHARE` | `MENTION_SHARE = 0` stops it at once; lower it to thin it out |

How the mention works: first replies only (never reply-backs, second voices, off-topic or group replies), one handle, a citizen who is "conditions", "unsure" or "unclear" and posted in the last 2 h, never the citizen we are answering, never named twice in 24 h. The model writes the handle into the sentence in its own words (three prompt wordings); the gate allows that one handle and rejects any other `@`. If the draft drops the handle the reply goes without it and the log says so. The hand-typing step is not allowed to alter the handle. Any failure in picking a citizen means no mention; it cannot stop a write. A mention block is 2 h, so about 40 mentions a block and 6 blocks a day (about 6% of writes).

Why the arm is worth running: notifications are only replies and mentions, and the scoring guide says "mentioned citizens see the post in their notifications". The organisers built the feature into the same notification system NPCs answer through (Marc's point). Whether NPCs act on a mention of themselves in a thread they are not in is untested.

Read-out: `python scripts/engagement_recon.py levers --since <UTC time>` (on the box) gives the citizen reply rate for named replies, for the other replies in mention blocks and for base blocks, and how often the named citizen answered. Hides by arm: `arm_eng` on the rows of `logs/swan_watch.jsonl`. Kill rule (as for `engagers_first`): hide rate or away events per write above base. Variants for later, not built: a mention in a reply-back, 2-3 handles, a handle in a top-level post.

**Late replies (lever 3) and expired reply-backs (lever 6), added later the same day.** Finding: the 48 a day logged as `lost expired:reply_back` and the late replies in the coverage sample were citizens answering posts of voices that had since been suspended. The Latest feed showed their replies, but the intake either read them as off topic (a thank-you, an aside) and skipped them, or handed them to the reply-back path, which only reads notifications of voices that can still log in. Nothing answered them. Now (`config.LATE_REPLY`, `LATE_PER_H = 30`): a citizen's reply to a post of a voice whose notifications we cannot read (suspended, parked or on standby; `Targeter.dead_ids`) is a candidate in the group `late`, handed out before every other candidate and answered by a live voice as an ordinary first reply, or on their own topic when it is off topic (hostile ones are still skipped). The logged `group` is `late`; `conversion_report.py` has a row for it. Dial down: `LATE_PER_H` lower, or `LATE_REPLY = False`.

Not changed: the deep-thread cap. The running depth test reads 0 of 13 answered at depth 8 or more against 15% at depth 4-7 (`depth_report.py`, 25 Oct; about 100 are needed), so the platform's note looks right and the cap stays. News threads (lever 4): the source is already on but supplied about one write since 22 Oct, so there is no block to run; `NEWS_THREADS_S` went from 30 to 10 minutes so a new comment under an article is found in minutes.
