# 33: Engagement per write. Optimise what the portal pays every hour; persuasion becomes a guardrail

**Written 2026-10-23 by Claude (closing the todo/25 session) at Marc's request. Owner: whoever picks it up.
Priority: top. Replaces todo/25** (conversion), which is closed: results in
[npc-lab](../docs/06-strategy/npc-lab.md).

## Why (evidence, 23 Oct)

**Persuasion doesn't move, whatever we do.**
- Live: 1 change toward No since 22 Oct (citizen 528, before the vote lines came out), 0 since, across every
  conversion arm (base, fresh_facts, target_order, agree_close).
- Lab: five rounds of stand-in citizens, rated by Haiku and by Sonnet (the Sonnet raters match real citizens' answers
  within ~0.1). Nothing beat what we send:
  - wording, news, overclaim, debate techniques, rally lines;
  - Kimi vs Claude Haiku 4.5 vs Sonnet 4.6 as the drafting model;
  - likes, follows, second voices, peer posts, own posts.
- The NPC lab is retired: dashboard link and page removed with this item, swan-lab.service stopped and disabled
  (23 Oct). The code stays (`src/swan_lab`, `scripts/npc_session_lab.py`).

**Engagement is what pays, and it's measurable every hour.**

| source (portal events, ~44 h to 22 Oct 16:19 UTC) | points |
|---|---|
| NPC engagement (≈30 likes + 30 replies an hour) | ~13,700 |
| Poll 1 (too close to call) | 3,000 |
| Blue | a few hundred |
| persuasion | a handful |

- Base points: like 5, repost 10, reply 15, follow 20, unfollow −20; views 1 but capped at 500/day (we're already
  over the cap, so views add nothing). Likes, reposts, replies and follows are **uncapped** and multiplied **×2 from 26 Oct,
  ×4 on 1–2 Nov**.
- Score 19,001, rank 13; the leader has 57,779.

**Per write today (swan_outcomes, citizen likes ×5 + citizen replies ×15 + views):**

| mode | points / write | |
|---|---|---|
| reply | 3.3 | ~5.2 on 19–20 Oct, ~3.0 on 21–22 Oct |
| reply_back | 3.2 | |
| second_voice | 2.1 | |
| thread one-liner | 1.8 | |

Within a day the drafting model makes no consistent difference. By target stance, replies to yes_but and lean_no
earn ~2.3–2.4 points, unsure ~5.2 (only 9 writes).

**Follows are almost free and untested.**
- The bot follows a citizen only when they answer us (`bot.py`, reply_back): 264 follows so far.
- Read-only check, 23 Oct: of 214 such citizens, **9 follow the persona back (4.2%)**.
- Follows and likes have their own budgets, **30/min each, team-wide**, separate from the 3/min write route. So they
  cost no reply.
- Untested:
  - following citizens who haven't answered us;
  - liking citizens' posts (today our likes go to our own replies);
  - whether a follow or like brings the citizen to our posts (Home ranks followed accounts higher; a follow-back
    puts our posts in their Home feed).

## What to build

### 1. The metric: points per write and per hour, by arm
Extend `scripts/conversion_report.py` (or add `scripts/engagement_report.py`).
- Per arm: the portal's hourly Red points split into likes / replies / reposts / follows / unfollows / changes of
  mind (`build._part` already parses them). Divide by the arm's citizen-facing writes and by hours.
- Per citizen, logged per arm:
  - **follow-back** (followers read at 6 h and 24 h, 300/min read budget);
  - **citizen likes / replies / follows on our posts** within 24 h.
- Guardrails per arm: away events, unfollows, hidden posts, account suspensions.

### 2. Arms
**Two designs**, because some levers spend the shared write budget and some don't:

- **Free levers (follow, like): randomise per citizen, not per block.** Effects land hours later and would smear
  across 2 h blocks. `hash(citizen_id) % 4` →
  - `none`;
  - `follow`: the replying persona follows them on our **first** reply, not only after they answer;
  - `like`: the replying persona likes the post we reply to, with the usual human delay;
  - `follow+like`.

  Log the cell on the write (`eng_cell`). Read out the per-citizen outcomes after 24 h.
- **Budget levers: 2 h switchback blocks** (the existing `config.SWITCHBACK` and `experiment.block`).
  - `ENG_ARMS = ["base", "engagers_first"]` replaces `CONV_ARMS`.
  - `engagers_first` orders candidates by predicted engagement: citizens who answered us before first, then unsure,
    then the freshest posts (a reply within minutes of their post), then the rest.
  - Keep the conversion arms' code; just take them off the switchback.
  - Add more budget arms only after these two read out.

### 3. Limits that make it look human (and keep Blue reporters off us)
- Per persona: at most ~40 follows a day and ~1 follow a minute. Never follow and like the same citizen within a
  minute.
- Pace follows and likes from the route's `rate_limit` header, not hard-coded numbers.
- Never unfollow in bulk (no penalty is stated for us unfollowing, but mass churn reads as a bot).
- A citizen we follow who unfollows us costs −20. Watch unfollows per cell.

### 4. Kill and promote rules
- **Kill a cell or arm** whose unfollows plus away events, in points, exceed its gain. Also kill it if any persona in
  it gets a hidden post or a suspension that the ledger ties to follows or likes.
- **Promote** a free-lever cell whose points per citizen beat `none` over ~300 citizens. Follow-backs at the 4.2% we
  measured give ~0.8 points per follow before multipliers.
- **Promote** a budget arm whose points per write beat base over ≥ 6 blocks each (3 days at 2 h blocks: start now so
  it reads out before ×2 on 26 Oct).
- **Persuasion is a guardrail:** an arm whose away events beat base is killed, as in todo/25.

## Tests
- The cell is a pure function of `citizen_id`. Each cell does exactly its actions, with writes off in tests as
  everywhere.
- Per-persona follow caps hold.
- `engagers_first` ordering: pin the arm with `monkeypatch.setattr(config, "SWITCHBACK", [...])`. conftest clears
  SWITCHBACK for every test.
- The report's per-arm split on a fixture portal log.

## Before going live
- CLAUDE.md rule 8: follows and likes are real, logged platform actions. Marc asked for this test on 23 Oct ("we can
  give this a try"). Still, tell him the deploy commit before it goes live (update.sh deploys main in ~2 min).
- Organiser question (draft for #questions, optional): "Is there any limit or rule on how many citizens an account may
  follow, or on following citizens who haven't interacted with us?"
