#!/usr/bin/env bash
# The live bot command on EC2. To change how the bot runs (accounts, pace, flags), edit this line and push to
# main: the updater (update.sh) restarts the bot with it within ~2 minutes. Model order: deploy/llm_chain.txt.
# No --allow-qwen: the provided 3B model's drafts were too weak (42% rejected); Groq is the free fallback now.
# --amplify (todo/04): own-team likes/thread/reposts on our originals. Pause it live without a restart:
#   touch ~/ctn/AMPLIFY_OFF   (rm it to resume). To switch it off for good, drop --amplify here and push.
# --per-min 2.9 (todo/24, 22 Oct; was 2.5): the writer aims at the team's 3/min and paces from X-RateLimit-Remaining,
# keeping config.WRITE_MARGIN writes for the swarm's reposts (bot.write_gap).
cd "$(dirname "$0")/.."
exec .venv/bin/python -u scripts/run_swan.py --live --yes --accounts 16 --per-min 2.9 --amplify --boosters 34 --hours 100000
