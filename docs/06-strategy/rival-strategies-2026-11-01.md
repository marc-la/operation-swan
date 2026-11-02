# Rival strategies, second pass: Yeah's lead, who the best bots write to, every idea the rules allow (1 Nov 2026)

Asked by Marc on 1 Nov (Perth): go over [rival-strategies-2026-10-31](rival-strategies-2026-10-31.md) with a fine comb, find its
blind spots, test the ideas the rules allow against data, explain Yeah's pace (3 h pace 7.86k at ×4 on the 16:00 UTC board, against
4.60k for china and 5.05k for us), and compare who the high-yield bots write to with who we write to. Read-only throughout; Claude
for Marc. Times UTC.

## 1. Parameters

- **Unit: the write, the strategy and the side, never a team** (rules §5.2.2, as in the 31 Oct read). The board is public and is
  read per team; nothing on the platform is matched to a team. No search was made for "what started when Yeah's score stepped",
  since that would identify their accounts by timing.
- **Data** (public reads, no login, from the box, 16:09-16:47 UTC 31 Oct, paced at 60-150 a minute per route; raw files in
  `/tmp/rev2/` on the box, scripts in the session scratchpad):
  - all of Latest from 31 Oct 02:58 to 16:09 (56,700 posts), plus the 31 Oct read's pull (30 Oct 03:00-31 Oct 03:10, 87,500);
  - every citizen's likes and follows since 31 Oct 03:00: 5,221 accounts (ids 12-2343 plus the 2,889 scoring 0.9+ in
    `npc_scores.json`), 95% read;
  - Trending's first 150 with counters (16:12);
  - `get_post` for 1,809 of the 2,052 posts older than both pulls that citizens replied to in the window;
  - our `logs/swan_actions.jsonl` from 30 Oct 23:00, the portal lines (`data/portal.json`), the board (`data/team_scores.jsonl`).
- **Measures.** Visible points: 15 × distinct citizen repliers + 5 × citizen likers + 10 × citizen reposts per write (as on 31 Oct).
  **Flow**: every citizen reply, like, repost and follow in a fixed window, counted when it happened, whatever the post's age, by
  the side of the post's author. An account's side is the majority of its keyword-marked writes and of the posts it reposts; about
  40% of rival accounts stay unmarked ("?"), and results are given with both bounds.

## 2. Findings

### 2.1 Yeah's lead is income that no visible action explains, and it belongs to the Yes side
- **Our writes are the best on the platform at volume.** On visible points per write (31 Oct 03:00-15:10 writes, matured an hour),
  our two voices score 3.78 and 3.43. They are #1 and #2 of the 5 accounts with 200+ writes, and #5 and #14 of 393 accounts with
  40+. Bot replies to citizens average 1.87. Nobody writing at volume beats us per write, so Yeah's gap cannot be better writes.
- **The board, against the flow** (writes 04:00-15:00, board 04:02-15:02, base points):

  | side | engagement flow | booked | booked ÷ flow |
  |---|---|---|---|
  | us | 13,704 | 15,704 | **1.15** |
  | other No teams | 22,461 | 23,676 | **1.05** (0.39 if every unmarked account were No) |
  | Yes side | 56,816 | 125,913 | **2.22** (1.33 if every unmarked account were Yes) |

  Engagement explains the No side's points. The Yes side books **2,400-6,000 base points an hour (9,600-24,000 at ×4)** that no
  reply, like, repost or follow explains; views cover at most ~600 of it.
- **The most likely source is persuasion toward Yes: the tide.** Every session in which a citizen moves toward Yes pays the Yes
  posts in it (160 to the post that completes the change, the 80 pool shared by the rest). Our portal shows the same sessions from
  the other side: 72-115 contributions away a day. By 2 h block (30 Oct 03:00-31 Oct 14:00, 18 blocks), the Yes side's unexplained
  income moves with our away events (r 0.37) and with Trending pushes (r 0.48), and pushes with our away events (r 0.31).
  Repeat booking on long-lived Trending posts can't be ruled out as part of it.
- **Yeah's share of it stepped on 31 Oct around 07:00 UTC, and only Yeah's.** Base points an hour from the board:

  | 13:00-16:00 UTC | 30 Oct (×2) | 31 Oct (×4) | change |
  |---|---|---|---|
  | Yeah | 1,177 | 1,925 | **+64%** |
  | us | 1,153 | 1,236 | +7% |
  | china | 1,342 | 1,130 | −16% |
  | rest of the Yes side | 8,475 | 7,465 | −12% |
  | rest of the No side | 917 | 302 | −67% |

  Yeah ran 1,300-1,600 base an hour on 30 Oct and 1,950-2,870 from 31 Oct 07:00. Whatever they changed then, it isn't a tide
  that lifts every Yes team, and it isn't visible engagement. It can't be pinned down within §5.2.2, and a No team couldn't use
  it: it is paid for citizens moving toward Yes.

### 2.2 Who the best bots write to: the same citizens, later
Bot replies to citizens, 31 Oct 03:00-15:10. The top 25 rival accounts (40+ replies to citizens, 3.13+ visible points a write):
- **Same yield as ours:** 3.65 visible points a write, 12.7% of targets answered, against our 3.61 and 10.6%.
- **Slower:** 25.6% of their replies go within 30 s of the citizen's post, against 62.3% of ours.
- **First less often:** they are the first bot reply 44% of the time, we are 69%.
- **Fewer extra citizens:** 28% of their replies go to citizens above id 2343, 44% of ours. Ours yield 4.05 there and 3.25 on
  ids 12-2343.
- **Better late replies:** theirs at 1-5 min yield 3.5-3.7, ours 1.8-2.1. Ours that late are mostly reply-backs (§2.4).
- **Thread position matters little:** among rival replies, the thread's first post being a pushed bot post (2.20), an
  unpushed one (2.44) or a citizen's (1.98) changes little.

**Citizens' own history does not carry over a day** (features from the 30 Oct window, yield of replies to them on 31 Oct, ours):

| past answer rate to bot replies | 0% | 10-20% | 20%+ | not seen on 30 Oct |
|---|---|---|---|---|
| visible points a write | 3.07 | 3.76 | 3.37 | **3.91** |

Heavy posters of the day before yield least (25+ posts: 2.25). Within a window, citizens who are answering yield up to 6.2. That is
being in a session now, which freshness already captures. No identity-based re-ranking has an edge: the value pick (todo/49) found
the same.

**The population is the limit.** We name 88-97% of all citizens who post in each hour. Pure readers (liking without posting in
the same 5 minutes) number only 2-6 at a time, so they are no extra pool. Of the posts we skip, rivals earn 0.85 on the deep
threads (n 90) and little on the rest. 777 queued posts expired unwritten in 13 h: only fresh supply is short.

### 2.3 Late replies exist, are booked, and outlive suspensions (corrects todo/60)
- **30% of the citizen replies our writes earn arrive after 6 h.** For our replies to citizens of 30 Oct 03:00-31 Oct 01:00
  (n 3,652), citizen repliers per 100 writes: 10.0 within 10 min, 1.5 at 10-60 min, 0.4 at 1-6 h, **2.2 at 6-15 h and 3.0 after
  15 h**. That's the target coming back, mostly the next day. Rivals: 6.4, 1.1, 0.8, 3.2, 2.9. Platform-wide, 57% of citizen
  replies in the window went to bot posts 6+ h old.
- **Suspension doesn't stop them.** Citizen replies to a voice's posts after its suspension: lesieli_tait16 97 (up to 30 h
  after), adeleke_g31 58, olaf_driver54 40, coconut85 43, quietpaddler12 7 so far. todo/60's 59 re-read posts were a different
  sample.
- **The portal books them.** Counting every citizen reply to any of our posts by its arrival hour (04:00-13:00), the portal
  booked 556 replies against 412 visible (1.35×), and 603 likes against 483 (1.25×). The rest fits replies to our posts older
  than the pulls. So the "portal pays twice what our posts carry" puzzle (todo/60, todo/55 Q16) is mostly late replies. The
  6.3 h outcome read sees about 70% of a write's replies, the same share for every write, so it still ranks options correctly.
- **Bans don't cost the tail,** and voice longevity isn't a lever for it. Followers aren't either: 9% of the current voice's
  citizen likes come from its followers (18 of 199), 2% for the voice before.

### 2.4 Reply-backs wait for a 60-second poll, and lose value every second
- **Reply-backs reach us only through `poll_reply_backs`**, every `config.NOTIF_EVERY_S` = 60 s. The Latest reader sees the
  citizen's answer within 5 s, but hands it to that path and waits (`targeting.py` 1272-1274).
- **Target answered within 3 h, by our delay** (both windows; n 587 reply-backs, 5,165 first replies):

  | delay | <20 s | 20-30 s | 30-45 s | 45-60 s | 60-90 s | 90-180 s | 3 min+ |
  |---|---|---|---|---|---|---|---|
  | reply-backs | 15.7% | 12.2% | 10.7% | 8.9% | 7.1% | 5.1% | 4.3% |
  | first replies | 10.9% | 12.6% | 10.7% | 9.5% | 8.2% | 5.0% | 4.9% |

- **Most of ours go late.** 17% of our reply-backs go out within 30 s, and 57% take 45 s or more. 31 expired unanswered in 13 h
  (`lost` `expired:reply_back`).

### 2.5 Mentions: the 31 Oct change works and is at its ceiling
- **Visible points a write by handles on our replies** (31 Oct 03:00-15:10): none 2.71 (n 1,179), one 4.26 (n 459), two 5.49
  (n 445). Citizen repliers per 100: 12.8, 19.6, 24.3.
- **A first naming pays 1.48 visible points:** 6.5% of those named replied and 9.9% liked (n 1,346). Repeat namings of the same
  citizen: 0 of 62 replied.
- **Handles reach 55-64% of replies in the Sydney day and 32-36% at night,** set by how many citizens post. That's why the share
  falls at night.
- **A rival pattern appeared at 15:00:** three handles appended to Yes replies ("…I'm voting Yes. @a @b @c"). Rival handles went
  from about 200-240 an hour to 563. They name the same fresh citizens we do.

### 2.6 Everything else, tested and set aside

| idea (rule or mechanic) | evidence | verdict |
|---|---|---|
| A third handle, or naming a citizen more than once an hour | We already name 88-97% of posting citizens each hour. Repeat namings: 0 of 62 replied | no gain |
| Mentions of online readers | 2-6 pure readers online per 5 min | no pool |
| Longer replies | No-handle replies: ours 2.62 → 2.96 (<150 to 250-300 chars); rivals flat at 2.55-2.97 (150-400) once handles are out | no gain |
| Closing questions | Raw: ours 4.15 with a question, 3.52 without. Within the same handle count there's no steady effect: 0 handles 2.51 against 2.87; 1 handle 5.64 against 3.93 (n 72); 2 handles 5.72 against 5.41. Rivals' fast replies with no handles: 2.57 against 2.56. Only 16% of our first replies end on one, though `ask_kind` is drawn on all | none; the raw gap is the handles |
| GIFs, hashtags | GIFs 2.61 against 2.46 (n 65); hashtags unused in replies | none |
| Article links in replies | 3.23 against 2.46, 14.7% against 9.9% answered, n 68 (about 1 SE) | **unproven**: the only content hint left |
| Trending pushes for engagement | 30-39 bot reposts in 15 min: 155 visible points over 75 writes (2.06 a write); 40-59: 1.20; 60+: 1.52. Our replies: 3.61 | loses per write; unknown for the count |
| Unpushed top-level posts | 0.38 visible points a write (2,745 posts) | no |
| Trending today | No No post in the top 68; 5 of 150. Top posts carry 150-550 views and 87-240 likes | Yes owns it |
| Identity-based targeting | §2.2 | no edge |
| Followers, voice longevity | §2.3 | no |
| Our `root_post_id` | `bot.py:2171` `acc.reply(target["post_id"], text)` sets the root to the parent, so every reply to a reply names the wrong thread root. But `replies()` lists by parent, and ours show under it as rivals' do | no effect on reach; a records fix only |
| "Other view" changes (20) | 1-4 primary a day | no |
| Blue | ×1, ~2% of points, at its caps | no change |

### 2.7 The race (board 16:02, 12 h paces at ×4, 39 h to 07:00 UTC 2 Nov)

| finish | if Yes wins | if No wins |
|---|---|---|
| Yeah | ~831k | ~735k |
| i wanna go to china | ~658k | ~871k |
| Operation Swan | ~641k | ~843k |
| I.use.arc (#4) | ~560k | ~497k |

- **Method:** the pool is split by each team's share of its side's points, the 31 Oct rule of thumb. That isn't how it pays (§3,
  item 3).
- **We stay in the top 3 either way.** If Yes wins, the margin to #4 is about 80k.
- **What decides #2 against #3:**
  - if Yes wins (the likely case, given §2.1 and Trending), about 17k of red;
  - if No wins, persuasion counts.

## 3. What to change, by points at stake

| # | change | evidence | expected | cost, risk |
|---|---|---|---|---|
| 1 | **Reply-backs on the citizen's answer, not on the poll.** Lower `NOTIF_EVERY_S` from 60 to ~15 s (one line; the poll reads only unparked voices' notifications, a few reads a minute). Better still, when the Latest reader routes a candidate to `reply_back`, poll at once | §2.4: about −0.1 pp answered per second in the first minute, and most of ours wait 45 s or more | **+2-4% of engagement**, about +4-7k by the end | one config line and a restart; pace from the route's headers |
| 2 | **Nothing to copy from Yeah.** Don't spend the last day chasing their number with engagement tweaks: their lead is Yes-side income (§2.1) | §2.1 | avoids lost time | none |
| 3 | **Know what the pool pays if No wins.** It splits by toward-No persuasion (a change counts 1, a contribution its share of 0.5), not points. Since 31 Oct 13:00 our portal shows 0 primary toward No and 14 contributions (about 0.3-0.5 units). If No wins, a No team with a handful of primary changes takes most of the 400,000. The only lever is persuasion we can't measure in time (todo/55) | portal lines, scoring §4 | decides #1 against #2 if No wins; can't be estimated | asking `#questions` whether "neither side" changes count (todo/55 Q15) is free and would size it |
| 4 | Optional: a news story's article link in the replies that already carry it | §2.6, n 68 | 0 to +5% on those replies (~30% of replies) | unproven; a content change in the final days |

- **The count:** the one lever with big stakes is Trending, which is all Yes. A single team's push costs about 75 writes, about
  1,300 points at ×4 in replies forgone, and its effect on the count can't be measured. A No-side push needs teams to coordinate,
  which is allowed in-game and only through the official Discord (§5.2.1, §5.2.2). It is a long shot, not a plan.
- **Corrections to make:**
  - todo/60 §1: late replies do arrive, and continue after a suspension (§2.3).
  - The "portal pays 2.3× the proxy" factor: most of it is late replies.
