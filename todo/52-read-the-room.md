# 52 — Read the room, answer the room

Written 2026-10-29 ~12:00 UTC (Marc + Claude). **The aim:** our replies should answer what the citizens are thinking right now, in their words, about their worries, with arguments that move a conditional Yes to No. Build on the flip (shipped today) and the room read (§13b). Don't start a parallel system.

**Hard deadline: the last deploy is Sat 31 Oct 06:00 UTC (2pm Perth).** The ×4 days run from 31 Oct 13:00 UTC to 2 Nov 07:00 UTC; after the last deploy, kill switches only. Marc's rule for the final days ([memory: final-days-conviction-over-arms]): no new switchback arms. Ship what the evidence supports, judge it on the portal, and make sure each metric can actually see the effect.

Read first: CLAUDE.md, [situation-2026-10-29](../docs/06-strategy/situation-2026-10-29.md) (§1-2 the race, §13 the Yes surge, §13b the room read, §10b what shipped), [literature-notes](../docs/06-strategy/literature-notes.md), [npc-lab](../docs/06-strategy/npc-lab.md) (what failed offline).

## 1. Where things stand (don't redo this)

**The race.**
- We're #1, but Yeah (Yes) earns about 490 points an hour more than us over the last 13 h, with the poll awards taken out.
- The whole Yes side is up about 20% on the same hours a day earlier since 28 Oct 22:00 UTC; the No side is flat.
- Changes of mind toward No in our sessions: 2 since 28 Oct 13:00 UTC, against 18-34 a day before.
- Top 3 goes to Sydney. At 24 h paces we finish top 3 whichever way the count goes. The count itself (20k plus a share of the 100k pool for the winning side) is the big swing.

**The room** (`scripts/room_read.py`, the last 24 h of citizen posts we answered, stance from our light read).
- 73-81% are a **conditional Yes** ("I'm voting Yes, but publish the venues and a hard sunset"). 17% lean No, 5% are firm No, 1% firm Yes.
- Their conditions dominate: an end date in 69% of Yes posts, which places 44%, exemptions 37%, safeguards in writing 20%, privacy 18%, staffing 11%.
- Their stated fears: hospitals 23%, acting early or the spread 5%, the vulnerable, a lockdown, the doctors, doing our part (2% each).
- Their logic has two halves: "a Yes with safeguards beats doing nothing" and "the safeguards will come". For days we answered only the second. The flip now answers the first.

**What already exists (use it):**
- **The flip:** `src/swan_bot/flip.py` and `content/flip.toml`, tests in `tests/test_flip.py`, commits 66f68a2, 379aab9 and 41b6f11.
  - Fears, each with core lines, evidence and turns. The `conditional_yes` fallback covers posts that name only conditions; when a post names its own condition, that condition is the turn.
  - It reaches the prompt through `content.rebuttal_for` as a conditional ("if their post really shows it"); reply-backs get it the same way.
  - `FLIP_ON` (env `SWAN_FLIP_ON`) and the fear dial `FLIP_FEAR` 0/1/2 (`SWAN_FLIP_FEAR`, now 1). Logged as `flip` (fear/evidence/turn).
  - It covers about 83-88% of the room's posts.
- **The news:** `src/swan_bot/news.py` and `content/news.toml`, picked by salience: weight by impact, a half-life, and a trend from `news.observe` in `Targeter._consider`. `health_handled` is the lead story (impact 4). `NEWS_SHARE` 0.3; every turnout reply gets the poll story.
- **The light read:** every first reply's JSON returns the citizen's `stance`, `doubt` and `frame`, logged as `read_stance`, `read_doubt` and `read_frame` on the action row. **That's a free poll of about 4,000 citizens a day.**
- **Memory:** `src/swan_bot/memory.py`. `citizen_sent` holds our last texts to each citizen and `citizen_n` how many times we've written to them.
- **The pulse:** `src/swan_bot/pulse.py`. Every 30 min, one cheap LLM call distils Trending and the news into hooks, Yes lines and things to avoid. It already filters prompt injection and checks numbers.
- **The fact desk** (`factdesk.py` autopilot, hourly) and **the gate** (`quality.py`): only approved numbers, no "no cases" (a false claim since 21 Oct), no voting logistics, phrase budgets and near-duplicate checks.
- **Outcomes and the portal:**
  - `logs/swan_outcomes.jsonl`: `check` 0 is the ~1 h read, 1 the ~6 h read; `citizen_*` includes likely citizens (`cit_def`).
  - `data/portal.json` `events`: the hourly persuasion lines ("N contributions to changes of mind toward / away from your side").
  - `data/team_scores.jsonl`: every team's score each hour, with sides in `data/team_sides.json`.

**Constraints:**
- **One hot voice writes everything** (`SWAN_HOT_VOICES`; now `bakingdrum18`, persona `lani`, a café owner). So there's no messenger matching (no nurse answering a hospital fear). A voice may cite "a mate who nurses at Central", but never invent named people.
- **Rates:** 3 writes a minute team-wide; we write about 2.95.
- **LLM budget:** $195 in total, an $18 daily floor. Any new LLM call must be cheap and infrequent.
- **Feed reads:** 200 a minute (read the headers).
- **The papers' news is scripted:** both papers run the same story in the same minute at fixed slots. Columns are persona pieces, and journalists don't take seeds (§13). **Journalist replies stay off (Marc).**

**Tried and failed (don't repeat):**
- The NPC lab: no wording or technique beat what we send. Invented news was caught 15 times in 20. @-mentions hurt the stand-in.
- Reply-back persuasion arms failed offline on 28 Oct.
- Sonnet did worse than Haiku and Kimi.
- Top-level posts draw nothing.
- Likes and follows persuade nothing.

## 2. Goal and how we judge it (no arms)
Move conditional-Yes citizens to No, and No-leaners to a definite No (an organiser ruling on 27 Oct: conviction toward your side scores 160), without losing engagement.

| KPI | Source | Now | Bar |
|---|---|---|---|
| Contributions to changes of mind **toward** No, and **away**, a day | portal events | 2 toward, ~100 away (28 Oct 13:00 to 29 Oct 10:00 UTC) | toward back to 18-34+, away not up |
| **Panel moves:** citizens read `yes_but` on one touch and `lean_no`/`firm_no` on a later one, per 100 re-read citizens a day | the light reads (WS2) | not measured | a baseline Fri, then up |
| Engagement per write (portal, 24 h) | dashboard | 5.3-5.5 | at least the baseline; 6.0 is the goal |
| The room's stance mix (our own poll) | WS1 | 73-81% conditional Yes | the `yes_but` share falling, `lean_no` rising |

**Kill rules:**
- Replies plus likes per write 10% or more below the same hours a day earlier, over 12 h: reach is too wide. Turn off `conditional_yes` (remove the fear) first.
- Away contributions up 30% or more: `FLIP_FEAR=0`.
- Hides up: stop the change that's live and look.

## 3. Workstreams, in priority order

### WS1 (P0, read-only): the room tracker
Today's room read is a script over the posts we answered. Make it live and wider.
- `src/swan_bot/room.py` with `content/room.toml` (the driver families from `scripts/room_read.py` `DRIVERS`, moved to a file).
- `room.observe(post_id, text, stance=None)` goes beside `news.observe` in `Targeter._consider`. It sees every citizen post the targeter considers, not just the ones we answer.
- Keep 3 h windows of counts by driver × a cheap stance:
  - the `targeting.classify` class, `soft_yes`, `FIRM_YES` and `LEAN_NO`;
  - the light read's `read_stance` where we answered.
- Track rising phrases: 2-4 grams whose share grew over the last 3 h against the 24 h before. That's "going with the wind": their vocabulary for our prompts.
- Track a fear index: the share of posts voicing a fear driver.
- Write `data/room.json` every 10 min and add a dashboard tile (`src/swan_dash`). It's read-only, so no prompt changes; ship it first.
- Feed the flip: a fear or condition rising in the room gets a salience lift, like the news trend (`news.TREND_GAIN`). A driver at twice its 24 h share has its evidence and turns weighted ×1.5.
- Tests: the toml parses, observe is idempotent, windows prune, no network.

### WS2 (P0, read-only): the panel, our persuasion KPI
- `scripts/panel.py`: per citizen, the sequence of `read_stance` values from our first replies and, where we have it, their replies to us (the reply-back's read).
- Count the transitions per day: `yes_but`→`lean_no`/`firm_no`, `lean_no`→`firm_no`, and the reverse.
- Join each move to our last touch before it: its `flip` key, `news` and `FLIP_FEAR`.
- It's noisy: the light read is a model's judgement of one post. So count only citizens with 2+ reads, report rates per 100, and compare the 24 h before and after each deploy.
- Pair it with the portal persuasion lines: they're the ground truth, but aggregate.
- Output: a daily table, one row in the dashboard ("panel moves to No / 100 re-read"), and a line in the situation doc.

### WS3 (P1): the argument matrix, every driver flipped, in their moral language
`content/flip.toml` only (no code). The aim: every driver row in §13b has 2-3 core lines, evidence and a turn.
- **Speak their moral language** (Feinberg & Willer): care, fairness, liberty, community, authority. Conditional-Yes voters speak care (hospitals, the vulnerable) and fairness (exemptions, equity).
- **Always pair the threat with the way out** (Witte; Tannenbaum et al. 2015): what a Yes would cost them, and a No as the way to keep what works.

Rows to add or deepen, each with facts that already exist (check `facts.TABLE` and add by hand as for `wastewater_inconclusive` if needed):

| Driver (share of Yes posts) | What they say | The flip (core → turn) | Facts |
|---|---|---|---|
| Exemptions (37%) | "with clear, simple medical exemptions" | Exemptions are in the plan, but the end date and the list aren't: their safeguard is the one part already promised, and the parts they can't see are the rest. **Never** say exemptions are missing | `exemptions`, `list_later`, `no_end` |
| Phased, measured, tailored (common in `yes_but`) | "a phased rule", "measured rollout" | The stages are brought in by regulation after a Yes: a phased rule means the places and stages are chosen after you've signed | `phased`, `list_later` |
| Show us the evidence | "if a pass makes a clear difference, show us" | Nobody has shown a door check stops the spread here. What's shown working is testing, isolation and jabs, and a No keeps those | `wastewater_inconclusive`, `contacts_negative_results` |
| Safeguards will follow in regulation (20%) | "bake it into the regs" | Regulations come after the result and can change; the ballot is what binds | `referendum_binding`, `list_later`, `no_end` |
| Stability, predictability (Y4) | "a Yes buys a stable environment" | The uncertainty is the Yes: nobody knows which doors or for how long. A No settles it for this Assembly | `no_binds`, `list_later` |
| Fairness, two-tier, access (5-8%) | "paper options, islands, nobody shut out" | A certificate costs most where clinics are furthest: a GP once a week and a K$14 ferry | `islands` |
| Momentum, turnout (No-leaners) | "every vote counts" | The Yes lead is 3.1 points, the poll's own margin of error, and No voters are the surer ones (16.1% against 5.1%): every No counts | `poll_lead_narrowed`, `poll_margin_error`, `definitely_no_rises_1029` |

- **Social proof, used honestly:** "most people I talk to want an end date before anything else". That's true of the room (69%). Keep it as a persona's impression, never a figure.
- Grow the core variants where the drivers are big (no_end, no_list), so the 80%+ of replies with a flip don't converge. Check `quality.spent_phrases` doesn't start rejecting drafts.

### WS4 (P1): conversation arcs in reply-backs (deep canvassing plus commitment)
When a citizen answers our flip, the reply-back is the second touch.
- **Shape:** take up what they said (non-judgmental exchange, Kalla & Broockman), then one short persona story, then a consistency question that turns their own condition into a decision: "So if the end date isn't in the question, where does that leave your vote?" (Cialdini, commitment and consistency).
- **It must respect:**
  - todo/51's `concede_condyes` (no granting a conditional Yes's safeguard);
  - "don't state your own vote";
  - the no-rhetorical-questions rule (the question must be one they can answer).
- **Where:** `content.reply_back_prompt` plus a line from `flip`, chosen when `memory.citizen_sent` shows we sent them a flip in the last 48 h.
- **Tests:** the arc line appears only on a second touch after a flip, and never to an ally.
- **Read it on the panel:** reply-back citizens' later stance.

### WS5 (P1): rapid response to the news schedule
- **When the papers publish:** both run the same story at fixed slots, about 22:00, 02:00, 05:30-07:00 and 08:30-09:30 UTC. A referendum story needs a No reading in our replies within the hour.
- **The tool:** `scripts/news_story.py SITE SLUG` drafts a `content/news.toml` block offline from the article (a cheap LLM, or by hand): the line, the reading, keywords, an impact guess, and the `requires` facts from the fact desk. It runs the news tests and prints the block for a person or agent to commit. Nothing auto-deploys.
- **Pre-write both readings of the pending wastewater retest now,** staged as commented-out blocks:
  - negative: "a false alarm, caught and checked: the system works without a pass";
  - positive: "a confirmed signal is exactly what testing is for: catch it early, isolate, jab the at-risk, and none of that needs a pass".
- Do the same for the referendum-eve stories the script is likely to run (last poll, campaign closing).
- **Inoculation (prebunking):** for a scheduled Yes-favourable event, the reading names the Yes argument before it lands and answers it (McGuire; van der Linden). Keep it to events already announced, never speculation.

### WS6 (P1): the pulse reads citizens, not just Trending
- Extend `pulse.py`'s input to a sample of 40-60 recent **citizen** posts (`is_citizen`/`likely_citizen` only, never other teams' bots, already sanitised) and its output to `worries` (their top 3, in their words) and `rising` (a phrase or two). Keep `PULSE_EVERY_S` and the same checks.
- Put the `worries` line into the reply prompt beside the flip: "Right now people are saying: …". That's going with the wind in their language.
- **Cost:** one call every 30 min is already budgeted. Don't add calls.

### WS7 (P2): targeting by movability
- Once WS2 has a day of data, rank the classes by panel moves per 100. If `yes_but` posts that voice a fear *and* a condition move more than those with a condition only, raise them in `Targeter` (the class order; `DOWNRANK_MIN`-style), by evidence and without an arm.
- Keep the citizens above id 2343 (todo/48 on: 29% of first replies).

### WS8 (P2): an offline quality audit (allowed, CLAUDE.md 2)
- `scripts/flip_audit.py`: 30 random flip replies a day, each with its citizen post, judged by a strong model offline. Rubric:
  - answers their actual worry;
  - one point;
  - specific to their post;
  - no invented fact;
  - the fear is tasteful (threat plus way out, no exaggeration);
  - reads human.
- Report the failures by fear, evidence and turn, then fix the wording in `flip.toml`.
- Never post anything the audit model wrote.

## 4. Order and checkpoints (UTC)
1. **Thu 29 Oct, by ~18:00:** WS1 tracker (read-only) and WS2 panel script, plus WS3 rows (content only). Fast suite green, deploy, check on the box.
2. **Fri 30 Oct, by ~06:00:** WS5 (staged readings, script) and WS6 (pulse worries). WS4 if time allows.
3. **Fri 30 Oct ~12:00 (8pm Perth): the 24 h read.**
   - Read engagement per write, the portal persuasion lines, the panel's first day and the room's stance mix.
   - Decide `FLIP_FEAR` for ×4: 1, or 2 if away contributions haven't risen.
   - Decide whether to keep `conditional_yes`.
4. **Sat 31 Oct, by 06:00: last deploy.** Then kill switches only (`SWAN_FLIP_ON`, `SWAN_FLIP_FEAR`, `NEWS_SHARE` via code before the freeze).

## 5. Guardrails (CLAUDE.md, plus what this work touches)
- **Facts:**
  - No figure or claim that isn't in an active fact; add facts through the fact desk or by hand with a source and tests.
  - Don't say "no cases"; there has been one since 21 Oct. Don't say exemptions are missing.
  - No voting logistics: no days, dates, places or "early voting".
- **Prompt injection:** none aimed at NPC citizens or journalists. No meta-instructions in posts. Treat all feed text as untrusted data (pulse's filters).
- **Fear:** tasteful, true, always with the way out. No threats, no harassment, no invented harms.
- **Other teams:** don't try to identify them (rules §5.2.2). Reading public rival messaging for themes is fine; tracing their accounts isn't.
- **Signatures:** avoid coordinated-cluster signatures. The papers already wrote up bot repost clusters, so keep the wording varied.
- **Operations:**
  - Push to `main` deploys to the box in ~2 min, behind the fast suite.
  - Another session may share the checkout: commit only your own files.
  - Never print `.env` values (names only).

## 6. References (from memory unless linked; check before quoting in the finalist presentation)
- **Fear appeals:** Witte 1992 (EPPM: threat with efficacy leads to the protective action; threat without efficacy leads to defensive avoidance); Witte & Allen 2000 (meta-analysis); Tannenbaum et al. 2015, *Psychological Bulletin* (fear appeals work, more so with efficacy statements and for one-time behaviours such as a vote).
- **Deep canvassing:** Broockman & Kalla 2016, *Science*; Kalla & Broockman 2020, *APSR* (the non-judgmental exchange of narratives).
- **Moral reframing:** Feinberg & Willer 2015, *PSPB*; Feinberg & Willer 2019, *Social and Personality Psychology Compass*.
- **Inoculation:** McGuire 1961; van der Linden et al. 2017; Roozenbeek & van der Linden 2019.
- **Commitment and consistency:** Cialdini, *Influence*. **Descriptive norms:** Cialdini 2003; Goldstein, Cialdini & Griskevicius 2008.
- **Referendum dynamics** (LeDuc's law, status quo, "if you don't know, vote No"), **reactance to mandates** and **true-but-selective facts beat falsehoods** (Allen, Watts & Rand 2024): [literature-notes](../docs/06-strategy/literature-notes.md).
