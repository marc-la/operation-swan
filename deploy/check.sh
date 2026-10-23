#!/usr/bin/env bash
# Fast pre-deploy checks (no network, no secrets). Used by update.sh before a restart and by GitHub CI.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-.venv/bin/python}
$PY -m compileall -q src/swan_bot src/swan_blue src/swan_dash src/swan_lab scripts
$PY -c "import sys; sys.path.insert(0, 'src'); import swan_bot.bot, swan_bot.swarm, swan_bot.content, swan_bot.quality, swan_bot.targeting, swan_bot.llm, swan_dash.build, swan_dash.portal, swan_blue.service, swan_lab.trials, swan_lab.report"
$PY scripts/run_swan.py --help > /dev/null
$PY scripts/swan_swarm.py --help > /dev/null
bash -n deploy/*.sh
# SKIP_TESTS=1 (update.sh on the box): the t3.micro (913 MB) stalls for minutes under the full suite, with the bot and the
# dashboard on it (23 Oct, twice). GitHub CI and the laptop run the tests; the box keeps the compile/import/--help checks.
if [ "${SKIP_TESTS:-}" != 1 ] && [ -d tests ] && $PY -c "import pytest" 2>/dev/null; then $PY -m pytest -q tests; fi
echo "checks ok"
