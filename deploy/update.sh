#!/usr/bin/env bash
# Every 2 min (swan-update.timer): if origin/main moved, pull it, run checks, and restart the bot.
# A failing check rolls back to the old commit and leaves the old bot running. Logged to logs/deploys.jsonl.
main() {
  set -uo pipefail
  cd "$(dirname "$0")/.."
  exec 9> /tmp/swan-update.lock; flock -n 9 || exit 0
  git fetch -q origin main || exit 0
  local old new
  old=$(git rev-parse HEAD); new=$(git rev-parse origin/main)
  [ "$old" = "$new" ] && exit 0
  local changed; changed=$(git diff --name-only "$old" "$new")
  git reset -q --hard "$new"                 # ignored files (.env, secrets/, data/, logs/) are never touched
  if grep -qx requirements.txt <<< "$changed"; then .venv/bin/pip install -q -r requirements.txt; fi
  local subject; subject=$(git log -1 --format='%h %an: %s' "$new")
  if ! out=$(deploy/check.sh 2>&1); then
    git reset -q --hard "$old"
    record "$old" "$new" failed
    deploy/alert.sh "DEPLOY FAILED, rolled back to ${old:0:7}. Bad commit: $subject. $(tail -3 <<< "$out")"
    exit 1
  fi
  if grep -qE '^deploy/.*\.(service|timer)$' <<< "$changed"; then sudo deploy/install.sh --units-only; fi
  if grep -qE '^(src/|scripts/|deploy/|requirements\.txt)' <<< "$changed"; then
    sudo systemctl try-restart swan-bot     # restarts only if running: a deliberate stop stays stopped
  fi                                        # docs/todo-only pushes don't restart the bot
  record "$old" "$new" ok
  deploy/alert.sh "deployed $subject"
}
record() { echo "{\"ts\": \"$(date -u +%FT%TZ)\", \"old\": \"$1\", \"new\": \"$2\", \"result\": \"$3\"}" >> logs/deploys.jsonl; }
main "$@"
