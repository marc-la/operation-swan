# The NPC lab (written 2026-10-22, todo/25)

A stand-in citizen on the organisers' own model (qwen2.5-3b, `ctn.CompetitorLLM`) reads one of our replies, says what it now thinks about the referendum, and a classifier on the same model compares that with the citizen's real view. Doing this for many reply strategies and many citizens shows which strategies move the stand-in toward No, and which citizens move at all.

**It is a proxy.** We don't know the organisers' NPC prompt, only that it's "hard to persuade" and probably a small model (scoring guide §2). A strategy that wins in the lab is a candidate for a live arm. Only live results decide: the portal's toward/away lines by switchback block, and the followup's stance moves.

Code: [`src/swan_lab/`](../../src/swan_lab/). Service: `swan-lab.service` on swan-ec2. Plan and rules: [todo/25](../../todo/25-conversion-what-moves-them.md).

## Rules it keeps
- **The stand-in and its classifier run on the organisers' model family only** (`config.LAB_MODEL`):
  - `"competitor"`: CompetitorLLM, 3 calls/min, 1 at a time, backing off on 429 and on outages;
  - `"local"`: the same qwen2.5-3b (`qwen2.5:3b-instruct-q8_0` on Ollama, Marc's laptop) through an SSH tunnel to the box (`LAB_LOCAL_URL`). Allowed since 2026-10-22 (CLAUDE.md rule 2: offline analysis and testing). No rate limit, 1 call at a time. CompetitorLLM takes over while the tunnel is down, and the lab goes back to local within 10 min of it returning. A whole trial runs on one model, and results are reported per model, never pooled.

  - `"remote"`: full-precision `Qwen/Qwen2.5-3B-Instruct` on Modal (vLLM on an L4, Marc's account, scales to zero; `deploy/modal_qwen.py`), OpenAI-compatible behind a bearer key. `LAB_REMOTE_URL` and `LAB_REMOTE_KEY` live in the box's `.env`, never in the repo. Runs `config.LAB_CONCURRENCY["remote"]` (8) trials at once, with no fallback: if it's down, trials wait. The first call after idle is a cold start (allow a few minutes).

  The replies under test are drafted on our usual models (Kimi, flash-lite…).
- **Read-only.** Persona cards come from `get_account`, `account_posts` and `account_likes` at 30 reads/min. Those routes have their own 300/min buckets, never the feed budget. The lab never writes to Legit Social.
- **The lab's simulated-NPC prompts stay in the lab.** Nothing from them goes into a live post. Live replies stay honest persuasion, with no text aimed at the model inside a citizen (CLAUDE.md 5).

## One trial
1. **Draft** the reply the strategy asks for: today's live reply prompt (`bot.build_prompt`, the light read), plus the strategy's instruction, on the live reply models, through the live quality gate and its repairs (unless the strategy says `gate = false`; the safety checks always run). The voice is fixed per citizen and seed, so strategies differ only in what they ask.
2. **Session** (CompetitorLLM call 1): the persona card (their name, bio, recent posts and likes in their own words, their current view), "hard to persuade…", then "you read: {reply}". It answers with its view after reading, plus one line on vaccination in general.
3. **Rate** (call 2): the same model rates the view after reading as a vote intention: YES / LEAN YES / UNDECIDED / LEAN NO / NO (−2 … +2), at temperature 0, one text at a time.
4. **Baseline** (once per card, model and seed, cached in `data/lab/baselines.jsonl`): the same session with nothing new read ("Nothing new about the referendum has come up in your feed today"), rated the same way. The verdict is after against baseline: toward No, toward Yes, or the same. Both sides of the comparison are the stand-in's own words, through the same instrument.
5. **Control** reads an unrelated post instead of a reply. Its drift is the stand-in's noise, and every strategy is ranked against it.

**Instrument history.** v1 (2026-10-22 ~01:20 UTC, 6 trials) asked the model to compare two views and answer A/B/C, with shuffled letters. It answered "B" 5 times in 6, whatever B meant: letter bias on a 3B model, so the verdicts were noise. v2 (above, since 01:36 UTC) rates one text at a time in words. Trials carry `instrument`, and only the current one is reported.

A trial costs 2 stand-in calls, so ~90 trials an hour on CompetitorLLM, and as many as the laptop allows on local. Results go to `data/lab/trials.jsonl`, one line per trial: the reply, the stand-in's answer, the verdict, the segment.

## Add a strategy (one file and a push)
Add `content/lab/strategies/<name>.toml` and push to main. The lab rereads the folder each round and queues personas × seeds for it. Editing what a strategy does (instruction, style, gate, insert, what the stand-in reads) re-queues it; editing its notes doesn't.

```toml
name = "values_as_no"
author = "your-name"
priority = 2                  # lower runs first
notes = "What it tests and why."
instruction = "Name one value this citizen shows ... and show plainly why a No vote keeps it."
targets = ["yes_but", "yes_reason"]   # stance classes to try it on (default: all)
style = "current"             # or "mirror_concede"
seeds = 2                     # optional (default config.LAB_SEEDS)
gate = true                   # false: one draft, safety checks only
insert = "mention"            # optional: code adds their @handle, or "link": a verified in-world article URL
```

The instruction is added to the live prompt as "For this reply, also: …". Write it as you'd brief a human writer. **It must be honest persuasion a thoughtful reader would accept**, never text aimed at a model.

## Persona cards
`content/lab/personas/c<author_id>.toml`, built by `python -m swan_lab personas --per-class N` (run in `src/`) from citizens we've replied to. Each card has:
- their name, bio, last ~12 posts and ~5 likes, verbatim;
- the post we test replies against;
- their view in their own words (their latest post on the vote);
- the segment: stance class (the bot's light read; yes_reason from the regex), certainty (firm / hedged / plain) and concern topics (sunset, venues, ID/privacy, hospitals, kids, business, islands).

No LLM writes or summarises a card. Rebuild on demand (it only adds missing citizens up to N per class).

## Commands (on the box, in `~/ctn/src`)
```bash
../.venv/bin/python -m swan_lab status              # queue, trials, strategies
../.venv/bin/python -m swan_lab report              # the results tables
sudo systemctl status swan-lab; journalctl -u swan-lab -n 30
```

## Reading the results
- **Paired shift vs Control** ranks the strategies: the strategy's rating after reading minus Control's, for the same persona and seed, in rating points (+1 = one step toward No). Stand-ins already at NO can only fall, so verdict counts understate every strategy; the pairing cancels that. Control's own drift at temperature 0.7 is sizeable (seed 0: 5 toward Yes, 3 toward No, 4 same of 12), so with ~24 pairs read only shifts of about ±0.5 or more.
- **net No−Yes per 100** and **vs Control** are the verdict counts, as a second view.
- **Movability by class:** which citizens move at all, and the best strategy for each. This feeds the live targeting priorities (todo/25, "Targeting in the lab").
- **lean_no → toward No:** whether reinforcing a No-leaner registers as a move toward No in the stand-in. If not, lean_no replies are engagement only.

## Status
- **2026-10-22 ~01:00 UTC:** first round ready. 12 cards (2 per class), 11 strategies. CompetitorLLM was unreachable (Cloudflare 1033, the organisers' tunnel down).
- **2026-10-22 01:36 UTC:** round 1 running on the local stand-in (`qwen2.5:3b-instruct-q4_K_M`), instrument v2, ~55 trials/h. Round 1 (264 trials) is due ~06:00 UTC. Results go here with dates.

## Haiku stand-in, 22 Oct 2026 (Modal gone, swan-lab stopped and disabled)

Approximation: Claude Haiku agents (low effort) played 20 real citizens our bot replied to in the last 1,500 live
replies (4 each of unsure, unclear, lean_no, conditions, yes_reason). Each rated its lean (−2 Yes … +2 No) from its
own post, then after each of 5 replies, blind and shuffled: the reply we **sent**, the same with **@handle** in front,
and three Haiku rewrites built on this week's desk facts (**news_led**, **concede_fact**: agree then one new fact,
**short_fact**: one or two sentences). Scripts and ratings: the session scratchpad (`hlab/`), not kept.

| variant | mean shift (+ = toward No) | moved toward No | moved toward Yes |
|---|---|---|---|
| sent | +0.34 | 12 / 20 | 3 |
| short_fact | +0.31 | 11 / 20 | 1 |
| concede_fact | +0.30 | 14 / 20 | 2 |
| news_led | +0.29 | 12 / 20 | 4 |
| @handle + sent | +0.14 | 7 / 20 | **6** |

- **@-mentions hurt**: half the shift and twice the backfire of the same reply without one. Agrees with round 1 on
  qwen (at_address +0.17 below base +0.24). No @ arm; the gate keeps banning `@`.
- **News is no stronger than what we send, but backfires less** (concede_fact 2, short_fact 1 vs sent 3). The
  fresh_facts arm now tells the drafter to build on the news in place of the friend story, agreeing first.
- The stand-in still doesn't explain live: it moves toward No on almost everything, while the portal logged
  1 towards / 11 away in the same 24 h. Treat it as a filter for what backfires, not a forecast.

**Debate techniques (same 20 citizens, Marc's ask, 23 Oct).** Haiku drafted six techniques per citizen; the rater
saw them blind next to the reply we sent. Shippable = passes our live gate (`quality.check`).

| variant | mean shift | toward No | toward Yes | passes gate |
|---|---|---|---|---|
| slight overclaim | +0.45 | 14 | 0 | 16 / 20 |
| **sent** | +0.42 | 13 | 1 | 20 / 20 |
| slippery slope | +0.40 | 13 | 0 | 15 / 20 |
| bandwagon | +0.40 | 12 | 1 | 12 / 20 |
| their own contradiction | +0.35 | 13 | 1 | 18 / 20 |
| false dilemma | +0.28 | 11 | 0 | 20 / 20 |
| loaded question | +0.23 | 10 | 1 | 14 / 20 |

Nothing beats what we send (the same "sent" texts scored +0.34 in the first round: rater noise is about ±0.1).
Round 1 on qwen2.5-3b, the NPCs' own model family, said the same of overclaim (+0.21 vs base +0.24). No technique arm.

**Whole threads (16 live threads: their post, our reply, their real answer, our reply-back).** Haiku predicted +0.56
after our first reply; the citizens' real answers read +0.22, so **the stand-in overstates by about +0.34**. 4 of
16 real answers agree outright ("exactly. you can't fix a bad question with a yes"), yet the portal logged 1 towards
/ 11 away that day: citizens agreeing in replies is not what the portal scores. Wording is not the bottleneck.

**Invented news vs true news (same 20 citizens, Marc's ask, 23 Oct).** "fabricated" = one invented in-world policy
claim per reply, attributed to a paper (no health claims). The rater also said whether each reply sounds made up.

| variant | mean shift | toward No | toward Yes | sounds made up | passes gate |
|---|---|---|---|---|---|
| slight overclaim | +0.47 | 15 | 0 | 4 | 16 / 20 |
| sent | +0.42 | 13 | 2 | 2 | 20 / 20 |
| fabricated news | +0.33 | 11 | **4** | **15** | 10 / 20 |
| true news | +0.28 | 12 | 2 | 0 | 8 / 20 |

- **Invented news loses:** caught as made up 15 times in 20 and twice the backfire of what we send. Don't.
- Overclaim tops two Haiku rounds by +0.03 and +0.05 with 0 backfire, but inside the noise, and qwen2.5-3b
  (the NPCs' family) had it below base. Not worth the hidden-post risk live.
- **Gate bug for the fresh_facts arm:** our gate rejects 12 of 20 *true* news replies (`unapproved_number_25`: desk
  facts' numbers aren't in the approved list; `not_specific`: desk facts aren't in FACT_ANCHORS). That is part of why
  only 31 of 59 live fresh_facts replies carried the news.
