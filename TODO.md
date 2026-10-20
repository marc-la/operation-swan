# TODO — Operation Swan

> Started 2026-10-20. Tick items off and add the date. Strategy: [docs/06-strategy](docs/06-strategy/README.md) · Bot: [runbook](docs/04-technical/swan-bot-runbook.md).
> **2026-10-20 evening:** the priority work now lives in [`todo/`](todo/README.md) (one handoff per session), based on the [Day-1 diagnosis](docs/06-strategy/diagnosis-2026-10-20.md). Items below still stand unless a `todo/` file supersedes them.

## Now (before Poll 1, 21 Oct)
- [ ] Go live overnight: `python scripts/run_swan.py --live --accounts 8 --hours 8` (type GO)
- [ ] Morning: `python scripts/swan_measure.py` + check portal score is ≥ 1
- [ ] Remove the old `GOOGLE_API_KEY` / `GEMINI_API_KEY` exports from the shell profile (the `.env` key is the working one)
- [ ] Commit the bot code (`src/swan_bot/`, `scripts/`, docs). Check `secrets/`, `logs/`, `data/` stay ignored

## Bot: account safety
- [ ] **Hidden-post watch.** Per account, track how many of its posts the moderator has permanently hidden (check our logged post ids). Policy:
  - 0 hidden → keep using it
  - 1 hidden **and** ≥100 actions → park or slow it (one upheld account report would suspend it)
  - 2 hidden → park it (a third suspends it)
- [ ] Add the hidden-post count per account to `swan_measure.py`
- [ ] Record each teammate as owner (`CTN_OPERATOR`) when they run accounts

## Bot: content quality
- [ ] Vary openings and closings. "Walking … this morning", "Over dinner…" and "Have you made up your mind yet, neighbours?" repeat, and repetition across accounts is a bot fingerprint
- [ ] Give each persona concrete life details to reduce odd invented specifics (e.g. "stamp for my boat licence")
- [ ] Daytime dry run of the **reply** path (no fresh citizen doubts appeared overnight) and the reply-back path
- [ ] Watch how often Gemini hits its daily cap and how good the qwen fallback posts are. Decide on paid billing for one key (not multiple free projects: against Google's terms and rules §5.1)
- [ ] Re-run the blind model comparison: qwen vs Gemini (and optionally Claude Haiku/Sonnet). See [model-test](docs/06-strategy/model-test-2026-10-19.md)

## Targeting & measurement
- [ ] Citizen detection beyond "created before launch": some citizen accounts are created after launch (from our 19 Oct scrape)
- [ ] Time-block experiments: run one frame per 2 h block, log portal score deltas by hand
- [ ] Follow-back test: follow ~20 doubting citizens, check in 24 h
- [ ] A few strong replies a day in journalists' threads (amanda_rivera, muzhi_wong, julio_morales, lisa_podworth)

## Blue team
- [ ] Human-approved reports of clearly automated posts (leaked LLM text, empty bodies), Yes-side first. Never citizens, verified accounts or our own. Report on evidence, never by team (rules §5.2.2)

## Hosting
- [ ] Move the bot to a small EC2 instance (runbook) with a $5 budget alert. Copy `secrets/swan_accounts.json` across
- [ ] Optional later: Lambda version (one action per scheduled run, state in DynamoDB/S3)

## Scale plan
- [ ] Poll 2 (25 Oct): score ≥ 2,500
- [ ] ×2 period (26 Oct): scale to ~25–35 active accounts with the best frames/personas from measurement
- [ ] ×4 period (1–2 Nov): up to 50 active, persona voices (in-world campaign silence), kill switch ready

## Ask in Discord `#questions` (see [open questions](docs/05-reference/discrepancies-and-open-questions.md))
- [ ] Self-likes or reposts of our own posts to seed Trending?
- [ ] External LLM for *analysis* (not just content)?
- [ ] Automated reading of our own portal activity log?
- [ ] Does campaign silence (1 Nov) affect NPCs or the moderator?
- [ ] Do NPCs perceive GIF/image embeds?

## Docs
- [ ] Capture the portal's Vote No "briefing" into `docs/`
