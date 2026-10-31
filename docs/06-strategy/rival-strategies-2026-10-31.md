# What the high-scoring writes do that ours don't (31 Oct 2026, 03:00-04:00 UTC)

Asked by Marc on 31 Oct: four teams have 3 h paces above ours (board 03:02 UTC: Vertex_CTN 4,184/h, china 2,973, I.use.arc 2,949,
Yeah 2,861, us 2,609, all at ×2) and three have 24 h paces above ours. Reverse-engineer the strategies behind the gap from what
Legit Social shows, and say what we should change. Read-only throughout; Claude for Marc.

## 1. Parameters

- **Unit: the write and the strategy, never the team.** Rules §5.2.1 allow "analysing in-competition data to inform strategies";
  §5.2.2 forbids "attempting to de-anonymise or identify other participants or teams" (as todo/62 §4 and situation §2 read it).
  So no account is mapped to a team and nothing is matched to the leaderboard. The board only sets the size of the gap. A
  strategy that earns more per write explains a higher pace whoever runs it, since every team has the same 3 writes a minute.
- **Data** (public reads, no login, from the box, 03:10-03:45 UTC 31 Oct, about 10,500 reads, every route paced at half its
  limit or less):
  - all of Latest from 30 Oct 03:00 to 31 Oct 03:10 UTC (~89,000 posts, ~880 reads);
  - every citizen's likes and follows in that window: 4,961 citizens, ids 12-2343 plus the likely citizens above 2343 (npc score
    ≥ 0.9, `config.NPC_TARGET_MIN`), two reads each;
  - Trending's first 150 posts with counters, and the likers of the 12 most-liked bot posts;
  - our own writes from `logs/swan_actions.jsonl`.
- **Points model** (base, citizens only, what can be seen): per write, 15 × distinct citizen repliers + 5 × citizen likers +
  10 × citizen reposts; per account, 20 × citizen follows. Views are left out (capped at 500 a day, which we hit). Persuasion
  can't be seen (§3.6).
- **Calibration.** Our accounts reconstruct to ~522 visible points an hour against a portal pace of ~1,300 base an hour, so the
  portal books ~2.5× what is visible, as todo/60 found. The same factor on every bot roughly reproduces the board's total for
  all teams. Strategies are compared on the visible measure, assuming the factor is similar across them.
- **Window and maturity.** Writes from 30 Oct 03:00 to 31 Oct 02:10 UTC, so each had at least an hour; citizen replies arrive
  within minutes.
- **Like for like.** Reply comparisons are standardised to our own mix of depth × reply speed × citizen class, because we are
  faster and better targeted than most bots.
- Scripts and data: the session scratchpad (`rev_pull.py`, `rev_lib.py`, `rev_an.py`, `rev_trend.py`); raw pulls on the box in
  `/tmp/rev/`.

## 2. The platform in one day

- About 3,000-3,500 bot writes an hour, against ~600 citizen posts. Bots write 76% replies, 15% reposts, 9% top-level posts.
- About 126 distinct citizens post in any hour, 59 in any 30 minutes, 26 in any 10 minutes.
- An on-topic citizen top-level post gets 4.9 bot replies, the first after a median 25 s. A citizen reply gets 2.6, the first
  after 35 s.

## 3. Findings

### 3.1 Our replies are already the best on the platform per write
- Replies to citizens at our mix: **ours 13.6 citizen replies per 100 writes** (2.74 visible points a write). Rival replies
  that end on a question: 14.3 (2.90). Rival replies without a question: 11.4 (2.33).
- Our hot voice ranks 25th of 653 accounts with 40+ writes on visible points per write. Speed and targeting are not the gap.

### 3.2 @mentions: the largest lever we under-use
A mention notifies the citizen named; that is the only channel besides a reply that reaches someone.
- **The extra repliers are the mentioned citizens.** Rival replies to citizens: the citizen answered replies 8.5 per 100 with
  no handle, 9.5 with one, 8.5 with two. *Other* citizens reply 1.7, 4.6 and 10.4 per 100.
- **Form matters.** Among mentioned citizens who are online (they post again within 30 min), a reply that **opens with their
  handle and talks to them** got an answer 10.3% of the time (n 845). A handle buried in the middle got 2.3% (n 306). Offline:
  about 1% either way.
- **Freshness matters most.** Rival opening-handle mentions of citizens who posted in the last 5 minutes: **5.9%** (n 1,626).
  5-15 min: 1.3%. 15 min or more: 0%. Rivals pick from the last 5 minutes 90% of the time.
- **It costs nothing with the person answered.** Their reply rate is 8.9% with opening handles against 8.1% with none.
- **Rivals open with *other* citizens' handles** (the target is among them in 39 of 1,749), answer the target, and speak to
  all of them.
- **Ours:** 243 of 3,925 first replies (6%) carried a handle, in the third person, mid-sentence, as `mention.LINES` asks ("never
  address {at} as you, never open with the handle"). The picks were mostly not online: 5 of 217 posted within 30 min after.
  **1.4%** answered.
- **Why so few.** `mention.pick` takes citizens waiting in our queue through `config.is_citizen`, so the 2,600 likely citizens
  are never named. It names each citizen once in 24 h. A username with a dot fails `\w{2,40}`. Then `MENTION_SHARE` 0.5 applies.
- **The platform is moving to it.** The share of bot replies to citizens that open with a handle went from 3-4% to 8-9% between
  30 Oct 20:00 and 31 Oct 02:00 UTC.
- **They like it too.** An opening handle to a fresh citizen: **11.9%** of them liked the write (n 1,481). Other combinations:
  1.4-3.4%.
- **What it is worth.** Each such mention is worth about 0.059 × 15 + 0.119 × 5 ≈ 1.5 visible points. About 126 fresh
  citizens an hour supports about 0.7 handles per reply when each is named at most once an hour.
  - At the rivals' rates, that is about +180 visible points an hour on our ~522: **about +35% engagement points**, or ~+1,800
    portal points an hour at ×4 through the 2.5 factor.
  - At a third of their rate, about +12%.
  - The new form is measured on rivals, not on us yet. The effect holds across 110 rival accounts (5.7% among accounts with
    under 40 such mentions) and in every 6 h block (4.6-9.0%).

### 3.3 Closing questions: mixed evidence, cheap to restore
- 40-50% of all bot replies to citizens end on a question, every hour. Ours: 5%. `REPLY_QUESTION_SHARE` = 0.10 since 28-29 Oct;
  the prompt critique cut it from ~40% as a stealth tell (citizens end on one 1% of the time).
- At our mix, rival replies ending on a question beat rival replies without one by 24% (2.90 against 2.33 points a write).
  Ours ending on a question: 2.97 against 2.66 (n 207, inside the noise).
- Our own ask arms found no difference (prompt critique 28 Oct). That was randomised; the rival comparison is not.

### 3.4 Trending: the Yes side owns it, and it doesn't pay per write
- **Trending is all bots and no No.** 139 of the first 150 Trending posts are bot posts, and **none of the top 60 argues No**.
  Nearly all say Yes outright; the rest are for the vaccine. Every pushed post in the 24 h was Yes (151, ~6.5 an hour). There were
  no No pushes.
- **A push is mechanical.** In the first 15 minutes, 25-47 bot reposts (each from a different account) and about 40 bot replies,
  plus 60-130 bot likes. Each push uses about 66 bot writes in its first hour.
  - That is more than one team's cap (45 in 15 min), so it means pooled budgets (coordination is allowed, §5.2.1) or several
    operations.
  - Across all 138 matured pushes: 17.8 citizen likes and 0.7 citizen replies a post, ~100 visible points.
- **There is a threshold.** Unpushed top-level bot posts get no citizen likes (6,230 posts, 0.0 each). Citizen likes by reposts
  in the first 15 min: 20-29 → 8, 30-39 → 25, 40 or more → 43. They peak at 7-11am Sydney (33-42 a push).
- **Per write it loses to replies, or at best ties.** Visible points a post at 20-29 reposts ~49, at 30-39 ~136, at 40 or more
  ~225 (likes almost all of it; under one citizen reply a post). The push uses about 55-85 writes, so 0.9-2.6 a write against
  ~2.7 for our replies (all pushes together: ~1.5 a write).
- **For the count it may matter.** Citizens who scroll Trending see only Yes, which fits the Yes tide and our contributions away.
  That can't be measured here.

### 3.5 Small or ruled out
- **Off-topic citizen posts.** A bot reply to one is answered 2.7 times per 100, against 6-7 on topic. Not worth slots, and it
  confirms todo/23's switch-off.
- **Follows.** About 750 citizen follows of bot accounts a day across the whole platform; 63% follow no visible contact.
- **Long replies.** Rival question-enders of 300+ characters draw 14.9 citizen replies per 100, against 12.1 under 200. We
  write none that long, so it is untested for us.
- **Flash-lite drafts.** 330 of our writes (8%) at 2.01 points a write, against 2.6-2.8 for Kimi and Haiku.

### 3.6 What can't be seen
- Persuasion. Citizens rarely say they moved: 26 of 10,688 replies to bots use mind-change language, mostly "I'll still vote Yes".
- So the Yes teams' share of the tide (contributions toward Yes), and any persuasion edge china has, are outside this read.

## 4. What to change, by points at stake

| # | Change | Evidence | Expected | Cost, risk |
|---|---|---|---|---|
| 1 | **Mentions done the rivals' way.** Name 1-2 citizens who posted in the last 5 minutes (Latest is read every 5 s, likely citizens included), not in the thread, each at most once an hour. **Open the reply with their handles** and speak to them and the person answered. Every first reply where a fresh citizen exists. Usernames with dots allowed | §3.2: 5.9% answer and 11.9% like, against our 1.4%; no cost to the target's reply | **+12-35% engagement** (supply-bound) | `mention.py`, `bot.py` (job carries a list), `quality.check` (allow the listed handles, ≤3), tests. Watch hides and away events |
| 2 | **Closing questions back to ~40%** (`REPLY_QUESTION_SHARE` 0.10 → 0.40), a question to the people named when there is a mention | §3.3: mixed | 0 to +10% | one line; reverses a stealth-driven cut |
| 3 | Keep paid drafting models over flash-lite where the budget allows | §3.5 | ~+2% | LLM budget |
| - | **Trending pushes: not for engagement.** Only as a call on the count, and then with ≥30 reposts in the first 15 minutes, Sydney morning, judged on citizen likes | §3.4 | negative per write; unknown for the count | about 66 writes and 50+ distinct likers a push |

Marc's final-days rule (no new switchback arms) applies. Items 1-2 are changes to live behaviour, not arms. Judge them on the
portal: citizen replies a write against the same hours a day earlier.

## 5. Shipped (31 Oct, Marc approved 1-3)

**ec95655**, pushed 04:03 UTC, live 04:06:49 UTC:
- **Mentions** (`mention.py`, `Targeter.fresh_pool`, `quality.check`):
  - up to 2 citizens whose newest Latest post is under 5 min old (likely citizens too), posts on the vote first;
  - never the target, ours, a firm Yes or an angry post; once an hour, with a 2-minute hold so drafts in flight don't share
    them;
  - every eligible first reply; the handles open the reply; dotted usernames allowed;
  - the gate judges the reply without its planned handles.
- **Questions:** `REPLY_QUESTION_SHARE` 0.40.
- **Models:** `REPLY_MODELS` Kimi, Haiku. flash-lite drafts only when both fail or park.

**First live read, 04:06:53-04:19:52 UTC** (38 first replies, 2.9 a minute):

| | 03:30-04:00 (before) | after |
|---|---|---|
| first replies with handles | 10 of 73 (14%) | **19 of 38 (50%)**, 14 of them with two |
| replies opening with the handles | 1 | **19** |
| flash-lite drafts | 6 of 86 | **0** (Kimi 19, Haiku 19) |
| ending on a question | 4 of 73 | 2 of 38 |

Two gaps:
- **Planned handles were dropped.** 34 replies had a plan, and 15 of the drafts dropped the handles. Kimi did so on 9 of 12
  first drafts; Haiku on 0 of 5.
- **The question share did not take.** 45% of replies were drawn a closing question, but the draft ended on one 1 time in
  10. `NO_VERDICT_RULE` ("End on their point or on your reason") and the flip's three moves came after the ask in the
  prompt.

**Follow-up push** (same day): fixes both gaps.
- A draft that dropped every planned handle opens with them (`mention.ensure`). The gate's verdict stands, since it reads
  the reply without its handles.
- Replies drawn a question carry the rule without its ending (`content.NO_VERDICT_ASK`).
- `content.ASK_LAST` is the last line of the prompt, after the flip and mention lines.

**d4f6702**, live 04:32:53 UTC. First read, 04:32:58-04:41:04 UTC (21 first replies and 3 reply-backs, 3 a minute):
- handles on 13 of 21 first replies (8 with two). Every planned reply carried them; the 8 without had no fresh citizen to
  name, mostly in the minutes after the restart, while the index fills;
- 7 of 21 end on a question;
- no flash-lite (Kimi 13, Haiku 11);
- rejects as before.

**Not a regression.** Citizen replies within 8 min of our first replies fell from 19.6 per 100 writes (03:43-04:06, 51
writes) to 6.1 (04:07-04:18, 33).
- Speed was not the cause: the target's age at send went from a median 28 s to 20 s.
- The hour explains it. 04:00 UTC (3pm Sydney) drew 4.2 per 100 the day before, the second-lowest hour of the day; the
  daily mean is about 9-10.
- In that window, writes that carried the handles drew 2 replies in 17; those where the model dropped them drew 0 in 16.

**Read it** against the same hours a day earlier: the board's 3 h pace against china and Yeah, the portal's engagement per
write, and our first replies' citizen repliers per write.

**Back out** (each alone, then push):
- mentions: `MENTION_SHARE = 0`;
- questions: `REPLY_QUESTION_SHARE = 0.10`;
- flash-lite: add `"gemini-3.5-flash-lite"` back to `REPLY_MODELS`;
- or revert ec95655.

## 6. The mention study and the send-time pick (31 Oct 16:00 UTC - 1 Nov; Marc approved)

**What the change did (measured 31 Oct, 04:33-15:00 UTC against the same hours on 29-30 Oct).**
- Portal base engagement per write: **7.57** after the change against 5.22 and 5.79 a day and two days earlier. The
  morning before the change ran 7.27 against 6.70 and 7.07, so the gain is about **+30-35%** (writes matched to the
  portal line of the same hour: that lines up better than a 1 h lag, correlation 0.49 against 0.38).
- First replies, citizen replies and likes at +1.5 h: 2.37 visible points a write with no handle, 3.83 with one, 5.14 with
  two. The person we answered replied as often as before (about 10%). Questions: no measurable effect. Kimi and Haiku:
  the same within the noise.
- Guardrails: away events 39 against 43 in the same hours a day earlier, no unfollows. Hidden: 6 of 679 replies with
  handles against 1 of 455 without (not significant; recheck).

**The study** (read-only: Latest 30 Oct 03:00 - 31 Oct 16:00 UTC, 142,000 posts, and the account list for usernames; ~690
reads). 8,446 bot writes that name a citizen other than the one answered; answered = that citizen replied to it within 1 h.
- Age of the citizen's newest post at the write: under 10 s 8.8%, 20-30 s 6.6%, 45-60 s 1.4%, 3-5 min 0.4%, older about 0.
- Opening handle 5.3% against 1.7% mid-text. Two handles 6.7% each; **three: 0 of 66**.
- Named by others 2 or more times in the 15 min before: 4%, 3 or more: 0. Second to name them within 2 min: about the
  same as first (5.0% against 5.3%).
- Answered a mention before: 17% (n 86). Replied to bots 6-10 times in the past day: 8.8% against 5.6% for none.
- Ours: 6.1% against 5.0% for rivals; median 26 s at send, 88% under a minute. Prepended handles (Kimi, which drops them)
  6.8%, written ones (Haiku) 6.0%.
- **Supply is the limit.** About 130 citizens post an hour by day, 60-80 at night (11-19 UTC), in short sessions. Replaying
  our picker over the real stream: today's rules give 0.89 handles a reply by day and 0.41 at night, as live. A 1-minute
  window, a 30-minute recontact or 3 handles add nothing; a 15-minute recontact adds 0.05. So who we pick hardly matters:
  we name nearly everyone online. Picking 5 s nearer the send gives +13% answers on the rivals' curve.
- Bigger picture (Marc agreed): engagement per write is capped by citizens online; at night we have more writes than fresh
  citizens, so night writes earn little whatever the wording.

**Shipped:** `mention.refresh` at send (`bot.py`, after `mention.ensure`):
- a planned opening handle whose citizen posted `MENTION_STALE_S` (20 s) ago or more is swapped for the freshest citizen
  not yet named, at least `MENTION_FRESHER_BY_S` (10 s) fresher and under `MENTION_ADD_MAX_S` (60 s);
- a reply planned without handles gets the fresh ones that arrived while it was drafted;
- handles written into the sentence, reply-backs and anything else are untouched; the same exclusions as `pick`; usernames
  from the cache only (`plan` warms `MENTION_WARM` = 4 more), so no read at send;
- logged: `mention_planned`, `mention_swapped`, `mention_ages` (seconds since each named citizen's newest post, at send).

Expected +5-13% on mention answers, about +2-3% engagement. **Read it** on `mention_ages` (should fall from a 26 s median)
and the named citizens' answer rate. **Back out:** `MENTION_SEND_REFRESH = False`.
