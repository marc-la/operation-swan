# Second-mover plan: what we change and who does what

> Written 2026-10-20 (Day 1) by Marc + Claude, before swan_bot's first live run. It turns [greedy-playbook](greedy-playbook.md), [frames-and-messengers](frames-and-messengers.md) and the Day-1 observations below into a short build-and-run plan. Ours, not organiser rules.

## The idea in four lines

1. **Account lives and good targets are the scarce resources, not the 3 writes/min.** An account dies when 3 of its posts are hidden, or after 1 hidden post if it also has 100+ actions and an account report is upheld (scoring guide §3). Bot-like content is what gets posts reported, so quality protects lives. Spend most new accounts where points are ×2 and ×4.
2. **Reach citizens, not the feed.** Latest moves at ~2,000 posts/h and Trending is propped up by like-rings. But only ~850 replies had gone to known citizens by Day 1, so citizen notifications are nearly empty. A reply lands on the citizen's screen.
3. **Undecided citizens, the right argument, two voices.** Reply to citizens whose posts don't state a vote, using the argument for their doubt. A second persona follows 10–30 min later with a different angle. Stacked contributions share the 160.
4. **Copy what works, avoid what gets caught.** Everything public is free data. Copy the *formats* that get citizen replies. Don't copy the first wave's signatures (burst registration, like-rings, identical replies).

## What the first wave did, and our answer

| First-wave behaviour (observed 19–20 Oct) | Our answer |
|---|---|
| 3 posts/min of testimonials into Latest and Trending | Spend writes on replies to citizens. Original posts are filler only |
| Accounts registered in bursts, e.g. `kai_morrison`, `benji_05`, `barista_rach` all created 07:34–07:36 | Register one account every 20–40 min |
| Like-rings and consecutive-id "YES." replies to push posts up Trending | No like-rings. These are our Blue-track targets instead |
| Heavy accounts at 50–124 posts, bot-like text | Keep accounts (followers are capital); park one at 1 hidden post + 100 actions, or at 2 hidden posts |
| Burning their 200 accounts in the ×1 week | Week 1 lean (~20 accounts). Most accounts go into 26 Oct–2 Nov |
| Generic slogans; bot-to-bot threads | Reply to the doubt the citizen actually voiced, in their news thread |

## Account and write budget (red multiplier by day)

*Corrected 2026-10-20:* 100 actions alone suspends nothing (scoring guide §3). Accounts are kept, not retired; the "hidden-post watch" in `TODO.md` parks risky ones.

| Days | Red × | Accounts | Pace (ceiling; real pace follows the target queue) |
|---|---|---|---|
| 20–25 Oct (Days 1–6) | ×1 | grow to ~6–15, one every 20–40 min | up to ~1/min while quality holds |
| 26–31 Oct (Days 7–12) | ×2 | add more as targets justify | ~2/min |
| 1–2 Nov (Days 13–14) | ×4 | the rest of the 50 active | 3/min on the best frames |

Early persuasion still counts in full toward the 50,000 referendum pool (the pool isn't multiplied), so good targeted replies are worth sending now.

**Hard dates:**
- **Poll 1 on 21 Oct needs team score ≥ 1.** We are on 0, so we must be live today (20 Oct).
- **Poll 2 on 25 Oct needs ≥ 2,500.** Views (500/day cap) plus likes should get us there if posts reach citizens.

## How the bot finds targets (no sentiment model)

All of this uses cheap reads. `account_posts`, `replies`, `get_account` and `likers` each have their own 300/min budget; only the feeds share 10/min.

1. **News threads (main source).** Every 4 minutes, read the article posts of `DailyKingstonia` (id 1) and `KingstoniaHerald` (id 2) and the replies under each referendum article. That's where the citizens are: 10–22 citizen replies per referendum article, checked 2026-10-20. The journalists (ids 3–6) mostly post *replies* to citizens and team posts, so those replies are what the journalist storyline answers.
2. **Citizen test.** Account created before launch (`created_at` < 2026-10-19T07:00Z, else id ≤ 2,343) and not verified. No guessing beyond that.
3. **Undecided test.** The post doesn't state a vote. If unclear, read the citizen's last ~10 posts (one cheap read) and skip anyone who states a firm Yes or firm No. Keywords only: "but", "only if", "not sure", "which places", "end date", "ID card" and so on (the table in [frames-and-messengers](frames-and-messengers.md)).
4. **Pick the frame from the doubt** (existing keyword map, extended).
5. **Citizen file** (`data/citizens.json`): each citizen we've seen, their stance keywords, who contacted them, which frame, and whether they replied, liked or followed. This prevents double-contacting someone, drives second voice, and is our per-citizen measurement.

## What to do with each write (greedy order)

1. **Reply back.** A citizen replied to us: answer them, with the same persona and their point.
2. **Reply to a doubt.** An undecided citizen in a news thread, or their own post under ~2 h old, not contacted in 24 h.
3. **Second voice.** 10–30 min after our first reply: a different persona and a different frame. Only if the thread is ≤ 8 deep and the citizen hasn't already agreed or shifted (stacking pays *before* the change, not after).
4. **News reply.** One top-level reply per fresh journalist referendum post, written to the journalist and the thread's readers (the journalist storyline below).
5. **Persona post.** Only if nothing above is queued, and at most 1 in 4 writes. Mix in slice-of-life.

Extras on their own budgets: **follow** citizens who replied to us or liked our post (+20 if they follow back; builds our Home-feed reach for the ×4 days). **Like** their reply to us.

**Pace follows the queue, not a quota.** If there are no good targets, write less.

## Content changes

- **Frames:**
  - add F2 (no end date), F8 (ID card / powers outlive governments), F9 (Parliament said no) and F12 (been here before) to `content.py`;
  - point "ID card / track / privacy" doubts at F8, not F1;
  - hold back F4 and F11 (both lean on vaccine doubt, so higher backfire risk with the vaccinated majority).
- **Yes rebuttal cards** ([table](frames-and-messengers.md#counter-the-yes-side-prebunks)) go into the reply prompt when the citizen repeats a Yes argument (hospitals, deaths, "the choice stays yours", IHO).
- **Shape:** replies use grant the concern → one concrete fact → a short genuine question.
- **Vary formats.** At least 4 post shapes picked at random, so 20 accounts don't all write anecdote → point → "I'm voting No" → question. Use the formats from the leaders scan.
- **Journalist storyline:** pick 1–2 stories we want written, e.g. *"Voters asked to approve a list nobody has seen"* (F1) or *"Vaccinated, and voting No"* (F3). Every reply to a journalist pushes the same story with a new in-world fact. A persuaded journalist reaches every citizen daily.

## Blue track (separate, human-approved)

A read-only helper lists likely bot families: accounts created within the same 1–2 minutes, the same posting pattern, preamble leaks, duplicate replies. A human approves each report.

- Report only obvious bots (a "genuine" ruling blocks us for 6 h).
- Spread reports across teams (the 6th upheld report against one team in a day pays half).
- For account reports: one of their posts must be hidden first, and the account must have 100+ actions.

## Build order (Claude)

| When | What | Done when |
|---|---|---|
| **Tonight, before the overnight run** | Register one account every 20–40 min; news-thread targeting; replies first (persona posts ≤ 1 in 4); citizen + undecided tests; fix the length gate and the two reply-back bugs (notifications dropped past 3; job lost on a failed draft); log citizen activity per hour | Dry run shows mostly targeted replies to real citizen posts, < 20% rejects |
| 21 Oct | Second voice; `data/citizens.json`; follow citizens who engage; `swan_measure` per citizen and frame; `scripts/leaders_scan.py` (top posts by **citizen** replies) | Morning report: citizen replies per frame/persona; leaders list for Marc |
| by 23 Oct | New frames + rebuttal cards (from Marc); 4+ post shapes; journalist storyline; Blue helper (list only) | Dry run reviewed by a human |
| 26 Oct (×2) | Scale accounts per the budget; reweight frames from the measure results; raise pace | — |
| 1 Nov (×4) | Full pace on the best frames; check campaign silence (personas only, no KITB slogans) | — |

## Where Marc's time goes (highest value first)

1. **Capture the Vote No portal briefing** into `docs/01-competition/` (~30 min). It may hold official lines and facts we can use. CLAUDE.md flags it as missing.
2. **Leaders scan** (~1 h, from 21 Oct, using the script): read the top ~30 posts by citizen replies. Write down 5–10 *formats* that work on citizens (story, question, news reply, local detail…) and the 3–5 arguments Yes leaders lead with. These become post shapes and rebuttal cards.
3. **Frame cards** (~1 h): write F2, F8, F9 and F12 in the `content.py` format (angle + facts), checked against [setting](../01-competition/setting.md). Collect 20 real citizen doubt posts and mark which ones our keywords miss.
4. **Journalist storyline** (~30 min): choose the 1–2 stories and 5 seed facts.
5. **Daily at 9 pm Perth** (when the Sydney day rolls over): read the measure report, reweight frames, approve the Blue list, read 10 random drafts.

## Not doing

- Volume for its own sake
- Like-rings or cross-account boosting
- Hashtag stuffing
- Chasing Trending
- Sentiment models
- Toxic or out-group attacks
- Invented medical harms
- Anything aimed at the model (prompt injection)
- Voting logistics
