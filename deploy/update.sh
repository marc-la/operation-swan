#!/usr/bin/env bash
# Every 2 min (swan-update.timer): if origin/main moved, check the new commit, then move the box onto it and restart the bot.
# The check runs in a throwaway worktree (data/deploy-check), so the live tree stays on the old commit until it has passed:
# a failing or killed check leaves the old tree and the old bot untouched. Logged to logs/deploys.jsonl.
# A bad commit fails once (record + alert; its sha goes in logs/deploy_failed_sha) and is then skipped until origin/main moves.
# A run killed after the reset but before the record is healed by the next tick (catch_up). todo/34 item 6.
main() {
  set -uo pipefail
  cd "$(dirname "$0")/.." || exit 1
  local root=$PWD wt=$PWD/data/deploy-check
  exec 9> "${SWAN_UPDATE_LOCK:-/tmp/swan-update.lock}"; flock -n 9 || exit 0
  mkdir -p logs data
  catch_up                                   # first, so a tree left on an unrecorded commit is settled even offline
  git fetch -q origin main || exit 0
  local old new
  old=$(git rev-parse HEAD); new=$(git rev-parse origin/main)
  [ "$old" = "$new" ] && exit 0
  [ "$(cat logs/deploy_failed_sha 2>/dev/null)" = "$new" ] && exit 0   # failed (and alerted) already: wait for a newer push
  local changed subject out
  changed=$(git diff --name-only "$old" "$new")
  subject=$(git log -1 --format='%h %an: %s' "$new")

  # ---- 1. check the candidate in a throwaway worktree; the live tree is not touched ----
  rm -rf "$wt"; git worktree prune           # leftovers of a run that was SIGKILLed
  # shellcheck disable=SC2064   # expanded now on purpose: the locals are gone when the trap fires
  trap "rm -rf '$wt'; git -C '$root' worktree prune" EXIT
  trap 'exit 143' TERM; trap 'exit 130' INT; trap 'exit 129' HUP    # so the EXIT trap runs when systemd or a person kills us
  if ! out=$(git worktree add -q --detach "$wt" "$new" 2>&1 \
             && { ! grep -qx requirements.txt <<< "$changed" || .venv/bin/pip install -q -r "$wt/requirements.txt" 2>&1; } \
             && cd "$wt" && PY="$root/.venv/bin/python" deploy/check.sh 2>&1); then
    # The box runs the fast suite (-m "not slow", serially: no xdist on the box; 124 s on 24 Oct). It is the only gate before a
    # restart: CI runs beside it and blocks nothing (25 Oct uptime check; it had run since 23 Oct, when check.sh lost the
    # SKIP_TESTS test). The 23 Oct stalls were the 913 MB t3.micro; the t3.medium has 3.8 GB. SKIP_TESTS=1 here skips it.
    # The venv is shared, so a changed requirements.txt is installed before the check (the new code may import it).
    echo "$new" > logs/deploy_failed_sha
    record "$old" "$new" failed
    deploy/alert.sh "DEPLOY FAILED, staying on ${old:0:7} (the box was not touched). Bad commit: $subject. $(tail -3 <<< "$out")"
    exit 1
  fi

  # ---- 2. it passed: move the live tree, restart if needed, record ----
  git reset -q --hard "$new"                 # ignored files (.env, secrets/, data/, logs/) are never touched
  rm -f logs/deploy_failed_sha
  apply_changes "$changed" now
  record "$old" "$new" ok
  deploy/alert.sh "deployed $subject"
}

# Units and the bot/Blue restart for the files in $1. $2 = "late" in catch_up, where the tree moved some time ago.
apply_changes() {
  local hit
  if grep -qE '^deploy/.*\.(service|timer)$' <<< "$1"; then sudo deploy/install.sh --units-only; fi
  hit=$(grep -vE '^(content/lab/|src/swan_dash/)' <<< "$1" | grep -E '^(src/|scripts/|deploy/|content/|requirements\.txt)')   # no -q: pipefail + SIGPIPE
  # docs/todo-only pushes don't restart the bot (content/facts.toml does); content/lab/ (the lab's strategies, cards) is
  # reread by the lab itself
  [ -n "$hit" ] || return 0
  if [ "${2:-}" != late ] || bot_older_than_tree; then
    sudo systemctl try-restart swan-bot swan-blue   # only if running: a deliberate stop stays stopped
  fi
  revive_gave_up
}
# src/swan_dash/ runs from its own once-a-minute timer and nothing in the bot or Blue imports it (checked 24 Oct):
# a dashboard-only push needs no restart.

# A unit systemd gave up on (a crash loop: 20 starts in 30 min, Result=start-limit-hit) is not running, so try-restart
# skipped it and no push could bring the bot back (25 Oct uptime check). New code is the fix someone pushed: start it again.
# Only start-limit-hit: a deliberate stop ends inactive (or, if it hung past TimeoutStopSec, Result=timeout) and stays stopped.
revive_gave_up() {
  local u
  for u in swan-bot swan-blue; do
    [ "$(systemctl show "$u" -p Result --value 2>/dev/null)" = start-limit-hit ] || continue
    systemctl is-active --quiet "$u" && continue
    sudo systemctl reset-failed "$u"; sudo systemctl start "$u"
    deploy/alert.sh "$u had stopped (systemd gave up after a crash loop): started it again on the new code. If it crashes again: journalctl -u $u -n 100"
  done
}

# True when swan-bot started before the live tree last moved (the reflog of HEAD), i.e. it runs older code than the tree.
# False when it is stopped or the time can't be read: a deliberate stop stays stopped.
bot_older_than_tree() {
  local moved started
  moved=$(stat -c %Y .git/logs/HEAD 2>/dev/null) || return 1
  started=$(systemctl show swan-bot -p ActiveEnterTimestamp --value 2>/dev/null)
  [ -n "$started" ] || return 1
  started=$(date -d "$started" +%s 2>/dev/null) || return 1
  [ "$started" -lt "$moved" ]
}

# The tree is on a commit with no ok record (a run killed after the reset, or a manual git reset): finish the job.
# Restarts only when the commits since the last recorded one changed code AND the bot is older than the tree.
catch_up() {
  local head last changed subject
  head=$(git rev-parse HEAD)
  last=$(grep '"result": "ok"' logs/deploys.jsonl 2>/dev/null | tail -1 | sed -n 's/.*"new": "\([0-9a-f]*\)".*/\1/p')
  [ "$last" = "$head" ] && return 0
  if [ -n "$last" ] && git cat-file -e "$last^{commit}" 2>/dev/null; then changed=$(git diff --name-only "$last" "$head")
  else changed=src/; fi                      # unknown base: assume code changed (the bot-age test still guards the restart)
  subject=$(git log -1 --format='%h %an: %s' "$head")
  apply_changes "$changed" late
  record "$last" "$head" ok catch-up
  deploy/alert.sh "deployed $subject (catch-up)"
}

record() { echo "{\"ts\": \"$(date -u +%FT%TZ)\", \"old\": \"$1\", \"new\": \"$2\", \"result\": \"$3\"${4:+, \"note\": \"$4\"}}" >> logs/deploys.jsonl; }
main "$@"
