# 44 — Rival census: finish it, repeat it at 24 h, and use it to find live Blue targets

Updated 2026-10-24 (Marc + Claude). Read `CLAUDE.md` first. Findings so far: [rival-census-2026-10-23](../docs/06-strategy/rival-census-2026-10-23.md). Data: `data/rival_census/` (gitignored; its README lists every file and the row format). Scripts (read-only, run from the repo root): `scripts/rival_census.py` (account list), `rival_pull.py` (post histories), `rival_survive.py`, `rival_feat.py`, `rival_side.py` (analysis; they read `data/rival_census/`).

Rules for every step: public data, analysis only, nothing posted and nothing learned from other teams' text is aimed at anyone (CLAUDE.md §2). No login. Stay at or under about 90 `account_posts` reads a minute; `rival_pull.py` backs off when the shared 300/min bucket is low (the bot's own sweep uses up to about 30 a minute; Blue about 150 across routes). Never run two pulls at once.

## State at 2026-10-24 ~01:00 Perth
- Census of all 10,324 accounts done (7,981 team accounts, 840 private). Full histories: 150 random, our 30 voices, 295 Blue leads, 96 dead truncated accounts. First pass (newest 100 posts each) of the remaining readable team accounts was at about 5,900 of 6,962 and still running in the original session's scratchpad (`.../scratchpad/ctrl/rest.jsonl`); `data/rival_census/rest.jsonl` holds an earlier copy. **First action for a cold session:** check `wc -l data/rival_census/rest.jsonl` against 6,962 (+ about 150 pilot); if it is short, re-run `python scripts/rival_pull.py <ids.txt> data/rival_census/rest.jsonl 90 1` for the missing ids (the script skips ids already in the output file; ids = readable team accounts in `census.jsonl`, minus the pilot, ours and the leads).
- The first pass was collected 23 Oct about 14:00–19:00 UTC.

## To do
1. **Second snapshot, 24 h after the first** (24 Oct about 15:00–19:00 UTC): re-pull the first page of every account that had posted within 24 h of the first snapshot (about 1,500; 17–20 min). This turns idle into evidence: an account that posted in snapshot 1 and not in snapshot 2 died in between; and it gives real survival times with a known state and the hazard by pace, age and side. Name the files by date (`rest-2026-10-24.jsonl`); keep the first.
2. **Hidden-post detection (feeds [43](43-blue-live-targets.md) item 2).** In the same diff, a post id present in snapshot 1 and missing in snapshot 2 from an account that is still posting is a moderator-hidden candidate (an author's delete looks the same). Produce `live_leads.json`: account, vanished post ids, posts/h, last post time, fleet. Count them per hour and per fleet: this is the first measure of how many live account leads the scanner would give Blue, against the 21 live of 189 now. Check a few by `get_post` (404) before trusting it.
3. **Calibrate on ours.** Run the same classification (silent for ≥24 h after steady posting) on our 72 accounts (`ours_all.json`) and report how well it recovers our known bans (portal `account_log.suspended`).
4. **Matched comparisons that were only started:** survivors vs dead at the same pace, age and side (text features, cadence regularity, active hours, reply targets); posts at death vs pace with an unbiased pace (posts in the first 12 h, not n ÷ span, which inflated the earlier slope); fleets from id adjacency plus creation time, with fleet-level survival.
5. **A daily "field" line on the dashboard** (accounts active in the last 24 h, registrations a day: 2,584 → 341 over 19–23 Oct) to see whether other teams are running out of accounts.
6. Keep the data out of git. If the team shares it, share the folder.

## Questions it can answer next
- Do the slow, steady, long-lived fleets (e.g. ids 2544, 3417, 3512, 4985, 4990: 150–440 posts over 4 days at 2–5 posts an hour) follow a schedule we could learn from (hour-of-day, gaps), or were they just not reported?
- Do survivors have lower per-post hide rates than ours, or fewer reporters? (Needs hidden-post counts per rival: item 2 gives a proxy.)
- Is the fate-sharing of id-neighbours (74% vs 51%) a team effect (behaviour) or a registration-batch effect? It decides whether our staggering matters (todo/39 item 3).
