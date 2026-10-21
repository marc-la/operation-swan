# 14: Prompt steering: what's left (two checks)

**Owner:** Marc + a teammate · **When:** 21 Oct, after 15:00 Perth (flash-lite's daily quota resets at midnight Pacific)
**When done:** delete this file and remove its row from [README](README.md). The live numbers are already in [13](13-overnight-experiments.md) "Evidence".

## Done (2026-10-21, commits `cd6de12`, `531aad3`, `9bff6bb`)
Steps 1–6 of the plan and both "also pending" items: repair-on-reject (`bot.draft_checked`, `quality.repair_note`), one beat per post (`beat` arm), lengths in words (`experiment.LENGTH_BANDS`, `VERSION = 2`), `max_tokens`/`temperature` in `llm.complete`, a numberless `WORLD`, `FACT_NOTES` and frame `gist`s, the contradiction audit (voices carry no counts or endings), the `close` arm, `spelled_number`, and the fixes from the first night's live rejects. The before/after live numbers are in 13 "Evidence". For the full plan as written, see this file in git history at `b4c62f1`.

## 1. Same-seed screen on flash-lite (blocked on quota until ~15:00 Perth)
On 21 Oct the quota ran out after 5 calls of the before-run. The key is shared with EC2: run this only when the bot isn't relying on flash-lite, or late in the Pacific day.
```bash
git worktree add /tmp/before 5eb8cd9 && ln -s "$PWD/.env" /tmp/before/.env && ln -s "$PWD/data" /tmp/before/data
git show cd6de12:scripts/swan_screen.py > /tmp/before/scripts/swan_screen.py
# in /tmp/before/scripts/swan_screen.py: replace draft() with the old loop (two fresh tries, quality.check, no
# repair) and import ARMS, Accounts, build_prompt, load_json from swan_bot.bot, as at 5eb8cd9
export LLM_RPM=6 LLM_CHAIN=gemini:gemini-3.5-flash-lite
(cd /tmp/before && python scripts/swan_screen.py data/screen-before.json --replies 4 --posts 6 --seed 7)
python scripts/swan_screen.py data/screen-after.json --replies 4 --posts 6 --seed 7
git worktree remove /tmp/before
```
Pass mark: **≥ 70% of drafts pass on the first or repair call**, **length rejects ≤ 1 per 10 drafts**, no new reject class, 0 "when my turn comes", 0 questions about conditions. Add the two rows to 13 "Evidence".

## 2. A teammate reads 10 live drafts
`ssh swan-ec2 'cd ~/ctn; python scripts/swan_view.py -n 30 --rejects'`. Look at drafts after 21 Oct 00:11 Perth (`exp: 2`), prefer flash-lite ones once the quota resets, and agree they read as one voice each, not stitched together. Watch for: a verdict said twice, "I am" where it should be "I'm", every fact packed into one post, and a catchphrase together with a concession.
