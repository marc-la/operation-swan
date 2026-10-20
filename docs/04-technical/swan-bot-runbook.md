# swan_bot runbook (written 2026-10-20)

Code: `src/swan_bot/`. Strategy behind it: [06-strategy](../06-strategy/README.md). **Dry run by default**: nothing is registered or posted without `--live`.

## What it does (updated 2026-10-20)

Plan behind it: [second-mover-plan](../06-strategy/second-mover-plan.md).

- **One process does all our writing.** It's capped by `--per-min` (default 1.0, hard max 2), but the real pace follows the target queue. If nothing is worth writing, it waits.
- **Each write slot goes to the best job:**
  1. reply back to a citizen who replied to us (and follow them);
  2. second voice: a different persona and angle on a doubt we answered 10–30 min ago, if the thread is ≤ 8 replies and they haven't answered yet;
  3. reply to an undecided citizen. Candidates come mostly from the papers' referendum article threads (ids 1–2), plus Latest/Trending. Citizen = created before launch and not verified. Firm Yes, firm No, loud or anti-KITB posts are skipped, as are citizens contacted in the last 3 days;
  4. reply to a journalist's referendum post (≤ 1 per 45 min, same journalist ≤ every 6 h);
  5. persona post: ≤ 1 in 4 writes, or one per 30 min when idle.
- **Content** (`content.py`):
  - 12 personas with local details, 12 frames, Yes rebuttals, varied openings and post shapes;
  - tone from the [Vote No briefing](../01-competition/vote-no-briefing.md);
  - only true in-game facts. Medical exemptions exist, and the certificate is separate from the ID card.
- **Quality gate** (`quality.py`) rejects:
  - LLM artefacts, hashtags, emoji, links, @mentions, wrong length;
  - endorsing Yes; posts that don't say No;
  - stock phrases ("Spot on", "crucial"…);
  - unapproved numbers;
  - wrong claims about the Act;
  - voting logistics;
  - replies that don't name the citizen's point or an in-world fact; posts without a local detail;
  - text copied from the fact list, parroting the citizen, near-duplicates.
- **Accounts:**
  - one registered every 20–40 min up to `--accounts` (default 6; tool cap 15);
  - each writes at most every 8 min;
  - kept, not retired (scoring §3: actions alone never suspend);
  - every account records its owner (`CTN_OPERATOR`, default `marc`).
- **LLM:**
  - Gemini models in order (`GEMINI_MODEL`, default `gemini-3.5-flash,gemini-3.5-flash-lite`). A daily-quota 429 parks that model until its reset; a per-minute 429 parks it for a minute.
  - Free-tier `gemini-3.8-flash` allows only 20 requests/day.
  - qwen is used only with `--allow-qwen`. Otherwise the bot waits rather than post weak text.

## Run

```bash
source .venv/bin/activate
python scripts/run_swan.py --samples 10                       # dry run: real targets, nothing posted
python scripts/swan_view.py -n 20 --rejects                   # drafts in place: news item > citizen > our reply
python scripts/run_swan.py --live --accounts 6 --hours 9      # asks you to type GO
python scripts/swan_measure.py                                # engagement per post/frame/persona
```

- **Stop:** Ctrl-C. On a server, `tmux attach` then Ctrl-C.
- **Files** (all gitignored):
  - `secrets/swan_accounts.json`: passwords and tokens (mode 600);
  - `logs/swan_actions.jsonl`: every write, reject, refresh (with citizen activity counts), register and follow, with owner, frame, target and context;
  - `data/swan_state.json`: replied posts, contacted citizens, pending second voices, recent texts.
- **Before going live:**
  - read a dry run with `swan_view.py`;
  - check `feed_lock`;
  - make sure no teammate is running another writer (the rate limit is shared).

## Hosting

**Since 2026-10-20 the bot runs on EC2 under systemd, with auto-deploy from `main`. See [hosting](hosting.md).** Don't run `--live` anywhere else. The laptop/tmux instructions are retired.
