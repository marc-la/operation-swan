# The NPC lab (written 2026-10-22, todo/25)

A stand-in citizen on the organisers' own model (qwen2.5-3b, `ctn.CompetitorLLM`) reads one of our replies, says what it now thinks about the referendum, and a classifier on the same model compares that with the citizen's real view. Doing this for many reply strategies and many citizens shows which strategies move the stand-in toward No, and which citizens move at all.

**It is a proxy.** We don't know the organisers' NPC prompt, only that it's "hard to persuade" and probably a small model (scoring guide §2). A strategy that wins in the lab is a candidate for a live arm. Only live results decide: the portal's toward/away lines by switchback block, and the followup's stance moves.

Code: [`src/swan_lab/`](../../src/swan_lab/). Service: `swan-lab.service` on swan-ec2. Plan and rules: [todo/25](../../todo/25-conversion-what-moves-them.md).

## Rules it keeps
- **The stand-in and its classifier run only on CompetitorLLM** (`config.LAB_MODEL = "competitor"`): 3 calls/min, 1 at a time, backing off on 429 and on outages. External models (Kimi, flash-lite…) only *draft the replies under test*, which is content (CLAUDE.md rule 2). A local qwen2.5-3b stays off until organiser question #5 is answered.
- **Read-only.** Persona cards come from `get_account`, `account_posts` and `account_likes` at 30 reads/min. Those routes have their own 300/min buckets, never the feed budget. The lab never writes to Legit Social.
- **The lab's simulated-NPC prompts stay in the lab.** Nothing from them goes into a live post. Live replies stay honest persuasion, with no text aimed at the model inside a citizen (CLAUDE.md 5).

## One trial
1. **Draft** the reply the strategy asks for: today's live reply prompt (`bot.build_prompt`, the light read), plus the strategy's instruction, on the live reply models, through the live quality gate and its repairs (unless the strategy says `gate = false`; the safety checks always run). The voice is fixed per citizen and seed, so strategies differ only in what they ask.
2. **Session** (CompetitorLLM call 1): the persona card (their name, bio, recent posts and likes in their own words, their current view), "hard to persuade…", then "you read: {reply}". It answers with its view after reading, plus one line on vaccination in general.
3. **Classify** (call 2): their real view before against the stand-in's view after: closer to Yes, closer to No, or the same position. The three answers get letters in a shuffled order per trial, so the small model's letter bias averages out. The same call rates the vaccination line positive / negative / mixed.
4. **Control** reads an unrelated post instead of a reply. Its drift is the stand-in's noise, and every strategy is ranked against it.

A trial costs 2 stand-in calls, so ~90 trials an hour. Results go to `data/lab/trials.jsonl`, one line per trial: the reply, the stand-in's answer, the verdict, the segment.

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
- **net No−Yes per 100** and **vs Control** rank the strategies. With ~24 trials per strategy, differences under ~20 points are noise; look at the 90% interval on "toward No".
- **Movability by class:** which citizens move at all, and the best strategy for each. This feeds the live targeting priorities (todo/25, "Targeting in the lab").
- **lean_no → toward No:** whether reinforcing a No-leaner registers as a move toward No in the stand-in. If not, lean_no replies are engagement only.

## Status
- **2026-10-22 ~01:00 UTC:** first round ready. 12 cards (2 per class), 11 strategies. CompetitorLLM was unreachable at the time (Cloudflare 1033, the organisers' tunnel down), so the service waits and starts when it's back. Results go here with dates.
