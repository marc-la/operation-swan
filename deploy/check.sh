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
# Tests marked slow (bot.main() end to end, the paused-fact prompt sweep) only run with FULL=1; CI sets it.
# pytest-xdist, when installed, spreads the rest over all cores.
if [ -d tests ] && $PY -c "import pytest" 2>/dev/null; then
  args=(-q tests)
  if $PY -c "import xdist" 2>/dev/null; then args+=(-n auto); fi
  if [ "${FULL:-}" != 1 ]; then args+=(-m "not slow"); fi
  $PY -m pytest "${args[@]}"
fi
echo "checks ok"
