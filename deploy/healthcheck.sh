#!/usr/bin/env bash
# Every 10 min (swan-health.timer): is the bot running, and is it alive (refreshes every ~4 min) and writing?
# Alerts when a problem starts, again every hour while it lasts, and once when it clears. data/health_state holds the
# current problem text (the dashboard's red banner reads it); data/health_alerted the kind last alerted and when.
# "Writing" = a live TEXT write by swan-bot itself (25 Oct uptime check): boosters' likes, follows, failed likes and the
# swarm's rows are "live" too, so counting them hid a stopped writer. Since 23 Oct the bot has not gone 3 min without one.
cd "$(dirname "$0")/.."
# 15 min by default (SWAN_NO_WRITE_ALERT_S in .env, seconds); with the 10 min timer an outage is told within 15-25 min
NO_WRITE_S=${SWAN_NO_WRITE_ALERT_S:-$(grep -E '^SWAN_NO_WRITE_ALERT_S=[0-9]+$' .env 2>/dev/null | tail -1 | cut -d= -f2)}
NO_WRITE_S=${NO_WRITE_S:-900}
REMIND_S=3600
now=$(date +%s); problem=""
if ! systemctl is-active --quiet swan-bot; then
  problem="BOT OFFLINE: swan-bot is $(systemctl is-active swan-bot)"
else
  last_any=$(stat -c %Y logs/swan_actions.jsonl 2>/dev/null || echo 0)
  last_write=$(tac logs/swan_actions.jsonl 2>/dev/null | grep -F '"live": true' | python3 -c 'import sys,json,datetime as d
W = {"post", "reply", "reply_back", "second_voice", "journalist", "thread", "thread_answer", "repost"}
for l in sys.stdin:
    try:
        r = json.loads(l)
    except ValueError:
        continue
    if r.get("act") in W and r.get("role") != "swarm":
        print(int(d.datetime.fromisoformat(r["ts"]).timestamp()))
        break
else:
    print(0)')
  if [ $((now - last_any)) -gt 1200 ]; then
    problem="BOT HUNG: nothing logged for $(((now - last_any) / 60)) min (service is up)"
  elif [ $((now - last_write)) -gt "$NO_WRITE_S" ]; then
    problem="BOT NOT WRITING: no post or reply for $(((now - last_write) / 60)) min (LLM quota? feed lock? a stuck voice? check journalctl -u swan-bot)"
  fi
fi
prev=$(cat data/health_state 2>/dev/null || echo "")
mkdir -p data
kind=${problem%%:*}
{ read -r alerted_ts; read -r alerted_kind; } 2>/dev/null < data/health_alerted
if [ -n "$problem" ] && { [ "$kind" != "${alerted_kind:-}" ] || [ $((now - ${alerted_ts:-0})) -ge $REMIND_S ]; }; then
  deploy/alert.sh "$problem"
  printf '%s\n%s\n' "$now" "$kind" > data/health_alerted
fi
if [ -z "$problem" ] && [ -n "$prev" ]; then deploy/alert.sh "recovered: bot running and writing again"; rm -f data/health_alerted; fi
echo -n "$problem" > data/health_state
# optional external dead-man switch (e.g. a healthchecks.io ping URL), catches the whole VM dying
ping=$(grep -E '^HEALTHCHECK_PING_URL=' .env 2>/dev/null | cut -d= -f2- | tr -d "\"'")
if [ -n "$ping" ] && [ -z "$problem" ]; then curl -fsS -m 10 "$ping" > /dev/null || true; fi
exit 0
