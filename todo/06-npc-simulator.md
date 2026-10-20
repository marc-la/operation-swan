# 06: NPC simulator: a fitness landscape for our drafts

**Owner:** narrative lead (+ data lead for the citizen profiles) · **Depends on:** 05 (shapes to test), 10 (ask about external LLM for evaluation) · **When:** 22–23 Oct

## Why
We get one noisy, delayed signal per post (likes, views; mind changes only as hourly portal totals). A local panel of simulated citizens lets us pre-screen many drafts per real post and push the prompts toward what moves people. Citizens are LLM agents with ~40 attributes, beliefs, likes and dislikes, built roughly a third each Yes, No and undecided ([overview](../docs/01-competition/overview.md); [literature-notes §F](../docs/06-strategy/literature-notes.md)).

## ⚠️ Rule gate
CLAUDE.md: external LLMs are allowed "only for generating content". Scoring our own drafts is arguably part of generating content, but it's an open question (`TODO.md`: "External LLM for *analysis*?"). It's in the [10](10-organiser-questions.md) draft. Until answered, run the simulator on the **provided** qwen model (it has no such restriction, but only 3 req/min) or offline only.

**Hard line:** optimise for content that would persuade a thoughtful human reader. Never optimise for text that works only on a model (instructions, role-play setups, markup). That's prompt injection: silently dropped, and penalised (scoring §7).

## Design
1. **Citizen profiles (from public data, gathered gradually).** For ~200 real citizens (pre-launch accounts), store their own posts and the posts they liked (`account_posts`, `account_likes`; 300/min read budget). Summarise each into a persona card: occupation or life hints, island or town, stated concerns (sunset, venue list, ID card, kids, hospitals, jobs) and a stance guess (Yes, soft Yes, unsure, soft No, No). Store in Mongo `citizen_profiles` (08). Keep in-game data only; no real personal data exists here anyway.
2. **Panel.** Sample 30 profiles weighted toward soft Yes and unsure (our targets), with ~20% firm Yes to catch backfire.
3. **Judge prompt per (profile, draft).** "You are <card>. You see this post in your feed: <draft>. Answer as JSON: would you scroll past / like / reply / follow; your vote intention before and after (Yes/No/Unsure plus certainty 0–100); one sentence why."
4. **Fitness** = mean shift toward No × weight − 2 × backfire (any move toward Yes) + small engagement bonus. Report a mean and a spread, not a single number.
5. **Use.** (a) Offline: rank prompt variants and shapes overnight, so 05's experiments start with better arms. (b) Online (later): generate 3 drafts and post the best by panel score, if the LLM budget allows.
6. **Calibrate against reality.** Every few days, compare the panel's ranking of *posted* drafts with their real citizen likes and views (08). If they don't correlate, the simulator is decorative: say so and stop using it.

## Done when
`python -m swan_sim --drafts drafts.jsonl` ranks 20 drafts on a 30-citizen panel. A first calibration note against real metrics is written into `docs/06-strategy/`.
