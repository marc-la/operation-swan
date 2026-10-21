# Swarm: like and repost Vote No posts (added 2026-10-21)

Owner: **minhnguyenhoang**. Code: `src/swan_bot/swarm.py`, `scripts/swan_swarm.py`, tests in `tests/test_swarm.py`. Runs on EC2 as `swan-swarm.timer` (every 5 min, `--live`). Dry run anywhere: `python scripts/swan_swarm.py`.

## What one run does
1. **Registers** at most one swarm account, 4–9 min after the last, until there are 20 (`SWARM_SIZE`). Before each one it counts the team's active accounts (bot and swarm files on EC2, plus Mongo `accounts`, whichever is larger). It stops at `MAX_ACTIVE` (49). **On 21 Oct the portal showed 47 active, so only about 2 swarm accounts fit** until accounts are deleted to free slots. A 403 from the platform backs off an hour. The bot and the amplifier now count swarm accounts against `MAX_ACTIVE` too. (Amplification was paused on 2026-10-21.)
2. **Scans** Latest and Trending from the bot's `data/latest_snapshot.json`, never the live feeds. The bot is the team's one feed reader (`feeds.py`, a 10/min budget). If the snapshot is older than 20 min, the run uses the tags only. It also reads the tags #keepkingstoniaopen (192), #voteno (113) and #choicenotcoercion (193) through `feeds.read`, which logs each read to `logs/feed_reads.jsonl`. It keeps posts from the last 24 h.
3. **Likes:** each new qualifying post gets 2–5 swarm likes, each a view and then a like. That's at most 25 per run (≤ 5/min of the team's 30/min). Liking pauses while the team's like budget is below 12, so the amplifier keeps its share.
4. **Reposts:** up to 2 per run (≈ 0.4/min of the team's 3/min write route, which the bot's replies also use). It only reposts top-level posts, only while ≥ 2 writes are left in the budget, and never two within 75 s.

A post qualifies if `targeting.stance` says "no", or if it carries a No tag and isn't "yes". Anything with a firm-Yes marker is skipped. **Our own team's posts are included** (decision 2026-10-21). A swarm account never likes or reposts its own post. No post is liked twice by the same account and no post is reposted twice, because failed requests have a small budget.

## Records
- Passwords and tokens: `secrets/swarm_accounts.json` on EC2 only. Mongo `accounts` gets username, account id, `role: "swarm"`, `owner: "minhnguyenhoang"` and status, through `swan-sync` (secrets stripped).
- Every registration, like and repost goes to `logs/swan_actions.jsonl` with account, `role: "swarm"` and owner. Likes use `target_post`, not `post_id`, so they don't overwrite the bot's post records in Mongo `actions`.
- State: `data/swarm_state.json` (who liked what, what was reposted).

## Controls
- Pause: `touch ~/ctn/SWARM_OFF` (remove it to resume). Stop for good: `sudo systemctl disable --now swan-swarm.timer`.
- Logs: `journalctl -u swan-swarm -n 50`.
- Tuning: the `SWARM_*` settings in `src/swan_bot/config.py`.

## Open rule question
Liking and reposting our own posts is open question 4 in [discrepancies](../05-reference/discrepancies-and-open-questions.md) (in-game LS.5.3 "reaction farming"). If the organisers rule against it, turn the swarm off that day, as with the amplifier.
