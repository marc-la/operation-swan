#!/usr/bin/env bash
# Fast pre-deploy checks (no network, no secrets). Used by update.sh before a restart and by GitHub CI.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-.venv/bin/python}
$PY -m compileall -q src/swan_bot scripts
$PY -c "import sys; sys.path.insert(0, 'src'); import swan_bot.bot, swan_bot.content, swan_bot.quality, swan_bot.targeting, swan_bot.llm"
$PY scripts/run_swan.py --help > /dev/null
bash -n deploy/*.sh
if [ -d tests ] && $PY -c "import pytest" 2>/dev/null; then $PY -m pytest -q tests; fi
echo "checks ok"
