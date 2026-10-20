#!/usr/bin/env bash
# Every 10 min (swan-health.timer): is the bot running, and is it alive (refreshes every ~4 min) and writing?
# Alerts once when a problem starts and once when it clears (state in data/health_state).
cd "$(dirname "$0")/.."
now=$(date +%s); problem=""
if ! systemctl is-active --quiet swan-bot; then
  problem="BOT OFFLINE: swan-bot is $(systemctl is-active swan-bot)"
else
  last_any=$(stat -c %Y logs/swan_actions.jsonl 2>/dev/null || echo 0)
  last_write=$(tac logs/swan_actions.jsonl 2>/dev/null | grep -m1 -E '"live": true' | python3 -c 'import sys,json,datetime as d
l=sys.stdin.readline()
print(int(d.datetime.fromisoformat(json.loads(l)["ts"]).timestamp()) if l else 0)')
  if [ $((now - last_any)) -gt 1200 ]; then
    problem="BOT HUNG: nothing logged for $(((now - last_any) / 60)) min (service is up)"
  elif [ $((now - last_write)) -gt 5400 ]; then
    problem="BOT NOT WRITING: no live write for $(((now - last_write) / 60)) min (LLM quota? no targets? check journalctl -u swan-bot)"
  fi
fi
prev=$(cat data/health_state 2>/dev/null || echo "")
mkdir -p data
if [ -n "$problem" ] && [ "$problem" != "$prev" ]; then deploy/alert.sh "$problem"; fi
if [ -z "$problem" ] && [ -n "$prev" ]; then deploy/alert.sh "recovered: bot running and writing again"; fi
echo -n "$problem" > data/health_state
# optional external dead-man switch (e.g. a healthchecks.io ping URL), catches the whole VM dying
ping=$(grep -E '^HEALTHCHECK_PING_URL=' .env 2>/dev/null | cut -d= -f2- | tr -d "\"'")
if [ -n "$ping" ] && [ -z "$problem" ]; then curl -fsS -m 10 "$ping" > /dev/null || true; fi
exit 0
