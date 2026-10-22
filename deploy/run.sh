#!/usr/bin/env bash
# The live bot command on EC2. To change how the bot runs (accounts, pace, flags), edit this line and push to
# main: the updater (update.sh) restarts the bot with it within ~2 minutes. Model order: deploy/llm_chain.txt.
# No --allow-qwen: the provided 3B model's drafts were too weak (42% rejected); Groq is the free fallback now.
# --amplify (todo/04): own-team likes/thread/reposts on our originals. Pause it live without a restart:
#   touch ~/ctn/AMPLIFY_OFF   (rm it to resume). To switch it off for good, drop --amplify here and push.
# --per-min 2.9 (todo/24, 22 Oct; was 2.5): the writer aims at the team's 3/min and paces from X-RateLimit-Remaining,
# keeping config.WRITE_MARGIN writes for the swarm's reposts (bot.write_gap).
# --per-min 2.9 (todo/27, 22 Oct 05:00 UTC; was 2.9): fewer writes while other teams' Blue reports get our replies
# hidden (6 hides/h). Back to 2.9 once hides stay under 1/h for 6 h (config.py, todo/27 block).
# --boosters 24 (22 Oct; was 34): 10 boosters became voices (scripts/convert_boosters.py) after 13 of 17 voices were
# suspended; at 34 the drip registration would replace them. 23 Oct: 22, after 7 more became voices (kiri, rafa, leo
# and 4 re-styled).
cd "$(dirname "$0")/.."
exec .venv/bin/python -u scripts/run_swan.py --live --yes --accounts 16 --per-min 2.9 --amplify --boosters 22 --hours 100000
