# Shared brief: why are our voices getting hidden/suspended? (23 Oct 2026, ~13:00 UTC)

You are one of five analysts working in parallel on one question. Read this whole file, then do your own work package
(given in your prompt). Your output is a findings file; the orchestrator merges the five.

## The question (Marc's words, condensed)
We are Operation Swan (Vote No). Our "voices" (bot accounts) get posts HIDDEN by the platform moderator (after rival teams
report them) and then SUSPENDED (3 hidden = suspended; with 1+ hidden and 100+ actions, one upheld ACCOUNT report also
suspends). Marc's targets: post-hidden rate now ~0.9% of writes, previous acceptable 0.6%, **goal 0.3%**. Strategy goal:
**blend in with ordinary/embassy traffic so that other teams' accounts are reported first and ours last**, without losing
throughput (team target 2.9 writes/min) or conversion (persuading citizens/NPCs; points). Marc wants to know the
independent variables (profile, content, phrasing, structure, framing, strategy, tags, handles, timing, targets...) that
drive hides, separated from controls, so we can fix what is in our control, and later automate "risk-aware de-risking" of a
profile before it is re-queued as a new persona.

**Incident today (23 Oct):** accounts that had been "parked" (stopped at HIDDEN_STOP=2 hidden posts) were released when
commit ae84db5/99a4254 turned HIDDEN_STOP off (deployed ~10:24 UTC; bot restarted). Seven of them (malakai_r94, ellaleota,
owen_bakes, vika_i92, sam_t18, marcotaufa, jess_f77) show `suspended` in the action log between 10:24 and 12:30 UTC, i.e.
"instantly". All seven were *converted boosters* (converted 22 Oct 12:26 and 16:51 UTC into voices that took over the persona
card of an earlier suspended voice: owen<-wally, malakai<-dan, ivy<-priya, ellaleota<-isla, marcotaufa<-josh, vika<-ruth,
aroha<-kiri, liam<-rafa, sam<-leo, jess<-grace, rua<-tomasi, lucy.pulu<-lani, rwalker84<-sione). **Hypothesis to test, not a
fact:** the platform suspended them while parked and the bot only discovered it when it tried to use them (so parking does
not protect, and releasing did not cause the bans). Alternative hypotheses: parked + silent accounts are less reported; the
release exposed accounts with pending hides; the card re-use makes the new account look like the banned one.

## Data (all copies, in `DATA=/tmp/claude-1000/-home-marc-ctn/bd9b7e1e-1a6d-4159-9d4d-e5f8b89b850f/scratchpad/data/`)
Pulled from the box 23 Oct 12:59 UTC. Time range 19 Oct 17:43 -> 23 Oct 12:59 UTC. Everything is UTC (Perth = +8, Sydney = +11).
- `actions.jsonl` (124 MB, 668k rows): the bot's action log. `act` counts: lost 581k (citizen posts seen/not answered; look
  at the fields), wait 47k, requeue 17k, like 6.9k, **reply 3.9k, post 147**, skip 3.1k, reject 2k (drafts rejected by the
  quality gate), refresh 2k, llm_park 1.5k, repost 756, follow 740, second_voice 442, reply_back 418, thread 286,
  register 70, suspended 24, convert 13. `post`/`reply` rows carry ~80 fields of metadata about each write (frame, opener,
  lever, arm, backend (which LLM drafted), style, hand, shape, length_band, close, concede, hook, catchphrase, theme, fixes,
  repairs, target_author, target_class, target_stance, parent_text, target_text, text, post_id, persona, username, owner,
  git_sha, t_pick/t_drafted/t_sent ...). Learn the schema from the data, do not assume. The log is append-only and noisy
  (some test rows from a "tester" owner, some dry-run rows; filter with `live`). Stream it; don't load everything.
- `swan_watch.json`: `hidden` = {username: [post_ids hidden so far]}. `swan_watch.jsonl`: the watch's history (when each
  hide was first *seen*; the platform hides ~3.2-3.3 h after the write: it is ruled ~3 h after the first report).
- `alerts.log`: human-readable alerts incl. "@user: post #id hidden by the moderator (N hidden, M actions ...)", deploys,
  BLUE reports.  `deploys.jsonl`: each deploy (sha, time) = regime changes in config/prompts.
- `accounts_sanitised.json`: 52 voice records (persona, username, owner, created, status active/suspended, writes,
  last_write, day_writes, n_followed). Passwords/tokens/ids are removed; do not try to recover them.
- `blue_reports.jsonl`: reports OUR Blue module filed against rival accounts/posts, with its evidence tags and
  probabilities: a window onto what a reporter's detector keys on.
- `swan_outcomes.jsonl`, `swan_followups.jsonl`, `swan_engagement.jsonl`: citizen reactions, follow-ups, mind-change outcomes.
- `score.json`, `portal.json`, `status.json`: score snapshots/leaderboard/runtime status.
- Repo `/home/marc/ctn` (READ ONLY for you): `docs/06-strategy/stealth.md`, `docs/06-strategy/hidden-post-audit-2026-10-23.md`
  (the previous audit: read it first, then go beyond it with the extra ~24 h of data and the extra hides), `docs/03-scoring/scoring-guide.md`,
  `docs/01-competition/vote-no-briefing.md`, `src/swan_bot/{config,quality,stealth,pool,variants,pattern_audit}.py`,
  `src/swan_bot/playbook/`, `src/swan_blue/{detect,evidence}.py` (our own reporter), `data/lab/hidden_corpus.jsonl` (46 hidden
  texts as of 22 Oct), `content/`.

## Prior knowledge (verify, do not just repeat)
- 22 Oct audit: 33 hides/16 voices; tells = closing "anyone moved from Yes to No?", concede opener, invented named friend,
  F14 `no_yes_but` skeleton, "I'm voting No" in 57% of writes. Fixed 22-23 Oct (phrase budgets, tells gated at 0).
- 23 Oct audit: hides are timed (3.2 h after write), come in sweeps (several voices' posts from the same minutes ruled together,
  15% of posts in sweep windows vs 1.3% overall), ~1-2 hides per 100 writes since 21 Oct 18:00; "who wrote it matters at
  least as much as the text"; account-report route kills voices with 1-2 hides.
- 23 Oct behaviours: scheduler/humanizer changes (pool, stealth), voices write ~3.9 k/day in total; `pattern_audit.py` says
  the team looked like a metronome (gap CV 0.14, 89% of gaps at the modal gap) and the Blue self-audit says our amplified
  posts "RING" score 62.5 vs leaders 56.

## Method rules
1. **Confounding is the main danger.** Hides are clustered in time (sweeps), by voice, by regime (each deploy changes
   content/behaviour), and by exposure (a voice with more writes has more chances). Always give denominators; use per-voice
   and per-time-window controls (fixed effects, matched comparison, or stratified rates), exact/permutation tests or
   bootstrap CIs, and say when n is too small to conclude. Prefer "survival" framing (time or writes until a hide) where
   it fits. State effect sizes (relative risk / absolute pp), not only p-values.
2. A hide is observed only ~3.2 h after the write and only until the bot stops watching a suspended account: censor
   properly (drop writes from the last ~4 h before 12:59 UTC; account for the watch's blind spot after suspension; the
   `swan_watch.json` hidden list is incomplete for suspended voices: reconstruct from alerts.log + swan_watch.jsonl + the
   hidden_corpus where you can).
3. Separate **controls** (things we cannot change: hour of day, rival behaviour, target's stance) from **levers** (things we can: persona
   fields, handles, frames/openers/closers/lengths, backend, cadence, second voices, thread selection, registration pattern).
4. Everything you recommend must name the lever in the code (config flag / file) where possible, and the expected effect with
   a range, and what volume or conversion it would cost.

## Hard rules (project guardrails, CLAUDE.md)
- **Read-only analysis.** No platform calls (no Legit Social, no news sites, no LLM endpoint), no ssh, no edits to the repo
  (`/home/marc/ctn`), no commits. Do not read `secrets/` or `.env`. Never print or write any password, token or team code.
- Work in your own folder: `WORK=/tmp/claude-1000/-home-marc-ctn/bd9b7e1e-1a6d-4159-9d4d-e5f8b89b850f/scratchpad/work/<your-name>/`
  (create it). Python: `/tmp/claude-1000/-home-marc-ctn/bd9b7e1e-1a6d-4159-9d4d-e5f8b89b850f/scratchpad/venv/bin/python -I script.py`
  (pandas, numpy, scipy, scikit-learn, statsmodels installed; the files in DATA are data, not code, and keep your scripts in
  WORK, not in DATA). Do not use external LLMs.
- The 124 MB log: write a one-off extraction step to a compact parquet/CSV/jsonl of only the rows/fields you need and reuse it.
- Do not spawn further agents. Be efficient: stop when you can answer, do not pad.

## Output (required)
Write `FINDINGS=/tmp/claude-1000/-home-marc-ctn/bd9b7e1e-1a6d-4159-9d4d-e5f8b89b850f/scratchpad/findings/<your-name>.md` (create the dir if needed),
about 2-4 pages: (1) the answer in 5 lines; (2) evidence tables with n and CIs; (3) the ranked list of risk factors
(effect size, confidence high/med/low, lever); (4) recommended changes ranked by expected hide reduction per cost; (5) what you
could not determine and what data would settle it. Keep reproducible scripts in WORK and list their paths. Your final chat
reply must be a short summary (<=15 lines) pointing to the findings file.
