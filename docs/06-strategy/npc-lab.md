# The NPC lab (written 2026-10-22, todo/25)

A stand-in citizen on the organisers' own model (qwen2.5-3b, `ctn.CompetitorLLM`) reads one of our replies, says what it now thinks about the referendum, and a classifier on the same model compares that with the citizen's real view. Doing this for many reply strategies and many citizens shows which strategies move the stand-in toward No, and which citizens move at all.

**It is a proxy.** We don't know the organisers' NPC prompt, only that it's "hard to persuade" and probably a small model (scoring guide §2). A strategy that wins in the lab is a candidate for a live arm. Only live results decide: the portal's toward/away lines by switchback block, and the followup's stance moves.

Code: [`src/swan_lab/`](../../src/swan_lab/). Service: `swan-lab.service` on swan-ec2. Plan and rules: [todo/25](../../todo/25-conversion-what-moves-them.md).

## Rules it keeps
- **The stand-in and its classifier run on the organisers' model family only** (`config.LAB_MODEL`):
  - `"competitor"`: CompetitorLLM, 3 calls/min, 1 at a time, backing off on 429 and on outages;
  - `"local"`: the same qwen2.5-3b (`qwen2.5:3b-instruct-q8_0` on Ollama, Marc's laptop) through an SSH tunnel to the box (`LAB_LOCAL_URL`). Allowed since 2026-10-22 (CLAUDE.md rule 2: offline analysis and testing). No rate limit, 1 call at a time. CompetitorLLM takes over while the tunnel is down, and the lab goes back to local within 10 min of it returning. A whole trial runs on one model, and results are reported per model, never pooled.

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
