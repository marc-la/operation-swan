#!/usr/bin/env bash
# The live bot command on EC2. To change how the bot runs (accounts, pace, flags), edit this line and push to
# main: the updater (update.sh) restarts the bot with it within ~2 minutes. Model order: deploy/llm_chain.txt.
# No --allow-qwen: the provided 3B model's drafts were too weak (42% rejected); Groq is the free fallback now.
cd "$(dirname "$0")/.."
exec .venv/bin/python -u scripts/run_swan.py --live --yes --accounts 12 --per-min 2.0 --hours 100000
