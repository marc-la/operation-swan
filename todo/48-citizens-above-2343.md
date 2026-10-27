# 48 — Citizens above id 2343: a classifier, then an arm and Blue's final check

Written 2026-10-27 (Marc + Claude). Read `CLAUDE.md` first, then [targeting-audit-2026-10-27](../docs/06-strategy/targeting-audit-2026-10-27.md) (finding 9). **Nothing here posts, follows, likes or reports.** Build and validate offline; every new switch ships **off**.

## Why
The briefing says "just over 6,000" NPC citizens; `config.is_citizen` knows 2,332 (ids 12-2343, seeded before launch). The organisers said more may be added mid-game, and the evidence says they were:
- Ids **4400-4790** were created 19 Oct 17:00-20:53 UTC at one every ~36 s with real-name display names, the seeded pace (25-42 s, [platform-mechanics](../docs/06-strategy/platform-mechanics.md#citizen-ids-and-the-feed-budget-2026-10-21-todo21)). Sampled accounts there (4516, 4580, 4589, 4592, 4760) post in short sessions every 1-2 days in the citizen style. Near **7701** (20 Oct ~21:00) the same, mixed with deleted/private ids.
- The same bands hold team bots too: **4464** posts almost every hour; 4348-4377 posted polished testimonials ("I'm a nurse...", "I run New Haven's pantry"). So an **id range is not safe**; judge each account.
- Why it matters: the bot drops every post by an id > 2343 ("team bots, ~98% of Latest", `Targeter._consider`), so we may answer only ~40% of the electorate, and our metrics (outcomes, follow-ups, `citizen_replies`) never count those citizens. In a 15-min Latest snapshot, 103 posts were by ids <= 2343 and 829 by higher ids.
- Blue: `swan_blue/evidence.py:33` and `fleets.py:21` call any id > 2343 a competitor. A "genuine" ruling locks all reporting for 6 h; four came on 26 Oct alone. Marc remembers a block of genuine rulings that must have been citizens. **The classifier is a final check there too.**

## Build
1. **Data (read-only).** `account_posts`, `get_account`, `replies` (300/min each, **team-wide, shared with the live bot and swan_blue**: stay under ~60/min, read `rate_limit`, back off on 429). Cache to a file, never re-read an account within a run. The box (`ssh swan-ec2`, read-only) has `logs/`, `data/latest_snapshot.json`, `data/blue_state.json`, `logs/blue_reports.jsonl`. Copies of the action/outcome/follow-up logs: `/tmp/claude-1000/-home-marc-ctn/60015ff6-f5a0-4737-a51c-8b9c68734f6b/scratchpad/` (`actions.jsonl` etc.).
2. **Labels.** Citizens: a random ~300 of ids 12-2343 that posted. Team bots: our own accounts (ids only from `secrets/swan_accounts.json`, never print other fields), authors Blue's moderator ruled **inauthentic** (hidden), and accounts with team names (`civic_voice_08_bc923e`). The authors of posts ruled **genuine** are a separate check set (expected to look citizen-like).
3. **Features**, simple and explainable: posting rhythm (sessions = posts within ~15 min; sessions a day; gap between sessions; posts per session), share of posts in Latest hours, creation pace of the account's id neighbours (a run at 25-42 s, evenly), display name vs username, style (lowercase share, giphy links, length), reply vs post mix, whether they ever reply to a citizen <= 2343 and get answered. Seeded citizens were active from creation and are online 1-5 min every ~2 days.
4. **Model.** A score in [0, 1] and two cuts: `NPC_TARGET_MIN` (for writing to them: favour **precision**, a team bot read as a citizen wastes a write) and `NPC_BLUE_MIN` (for Blue: favour **recall**, any plausible citizen is not reported). Report precision/recall on held-out labels for both cuts, and the score of the genuine-ruled authors.
5. **Census.** Score every account id > 2343 that posted in the last 72 h (from the snapshot plus a Latest-sized sample; no feed reads beyond what the bot already caches: `data/latest_snapshot.json`), and estimate how many citizens exist above 2343 and what share of Latest they write.

## Wire (all off by default)
- `src/swan_bot/npc.py` (pure scoring), `scripts/npc_scan.py` (`--dry` prints, otherwise writes `data/npc_scores.json`; read-only API), tests in `tests/test_npc.py` that need no network.
- `config.likely_citizen(id)`: `is_citizen(id)` **or** the cached score >= `NPC_TARGET_MIN`. `is_citizen` itself stays as it is (every metric uses it).
- Targeting: `NPC_EXTRA_ARM = False`. When on, `_consider` admits likely citizens as candidates in a switchback arm (`("arm_npc", ["base", "extra"], 3 * 3600)` in `SWITCHBACK`, plus `FREEZE_PIN["arm_npc"]`). Logged with a field (`npc_score`) so the read can split them. Outcomes for those writes must count their replies (the metric is points per write from the portal and our proxy, by arm).
- Blue: `BLUE_NPC_GUARD = False`. When on, `evidence.py`/`fleets.py` never treat an account scoring >= `NPC_BLUE_MIN` as a competitor; logged as a skip with its score.

## Read-out
Precision/recall per cut; the citizen count above 2343 and the share of Latest; the genuine-ruled authors' scores against the hidden ones; a dry run of `_consider` on the snapshot (how many more candidates an hour, of which class). **Do not push.** Commit on the worktree branch and report; Marc and the main session turn the flags on.

## Arms timetable (Marc, 27 Oct)
Test 28-30 Oct; every arm freezes at midnight Sydney on 1 Nov (`config.ARMS_FREEZE`); the x4 days run the winners.
