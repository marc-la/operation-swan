#!/usr/bin/env bash
# The quick test loop (about 40 s for the whole fast suite on 8 cores; serial it is minutes, so don't run plain `pytest`).
#   scripts/t.sh                 the fast suite: all cores, tests marked slow skipped (what deploy/check.sh runs)
#   scripts/t.sh changed         only the test files that match the files you changed (src/swan_bot/X.py -> tests/test_X*.py);
#                                (content.py and facts.toml map to test_prompts and test_facts); a changed file with no
#                                matching test falls back to the fast suite
#   scripts/t.sh slow            only the slow tests (bot.main end to end, the paused-fact sweep), all cores
#   scripts/t.sh full            everything, as CI does (FULL=1)
#   scripts/t.sh -k name tests/test_prompts.py     anything else goes to pytest as it is (one process: no start-up cost)
# The suite is written for xdist (-n auto): a few pool_scheduler tests share module state and fail when run in one
# serial pass, on a clean checkout too (24 Oct). Don't use `-p no:xdist`.
cd "$(dirname "$0")/.." || exit 1
PY=${PY:-.venv/bin/python}
base=(-q -p no:cacheprovider)
case "${1:-}" in
  "")      exec $PY -m pytest "${base[@]}" -n auto -m "not slow" ;;
  slow)    exec $PY -m pytest "${base[@]}" -n auto -m slow ;;
  full)    exec $PY -m pytest "${base[@]}" -n auto ;;
  changed)
    files=$( { git diff --name-only HEAD; git ls-files --others --exclude-standard; } | sort -u)
    tests=() ; fallback=0
    while read -r f; do
      [ -z "$f" ] && continue
      case "$f" in
        tests/test_*.py) tests+=("$f") ;;
        content/facts.toml) tests+=(tests/test_facts.py tests/test_prompts.py) ;;
        src/swan_bot/content.py) tests+=(tests/test_prompts.py tests/test_facts.py) ;;
        src/swan_*/*.py|scripts/*.py)
          stem=$(basename "$f" .py)
          m=$(ls tests/test_"$stem"*.py 2>/dev/null)
          if [ -n "$m" ]; then tests+=($m); else fallback=1; fi ;;
        content/*|deploy/*|requirements.txt) fallback=1 ;;
      esac
    done <<< "$files"
    if [ "$fallback" = 1 ] || [ ${#tests[@]} -eq 0 ]; then exec $PY -m pytest "${base[@]}" -n auto -m "not slow"; fi
    exec $PY -m pytest "${base[@]}" -n auto -m "not slow" $(printf '%s\n' "${tests[@]}" | sort -u | while read -r t; do [ -f "$t" ] && echo "$t"; done)
    ;;
  *)       exec $PY -m pytest "${base[@]}" "$@" ;;
esac
