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
# todo/61 (31 Oct): a slow writer (LLM slowness, rejects, a stuck drafter) was silent: under this many text writes in the
# last 30 min (75 = 2.5 a minute; the cap is 3.0, the bot runs 2.9-3.0) is a problem too, once the bot has been up 30 min
SLOW_N=${SWAN_SLOW_WRITES_30M:-$(grep -E '^SWAN_SLOW_WRITES_30M=[0-9]+$' .env 2>/dev/null | tail -1 | cut -d= -f2)}
SLOW_N=${SLOW_N:-75}
REMIND_S=3600
now=$(date +%s); problem=""
if ! systemctl is-active --quiet swan-bot; then
  problem="BOT OFFLINE: swan-bot is $(systemctl is-active swan-bot)"
else
  last_any=$(stat -c %Y logs/swan_actions.jsonl 2>/dev/null || echo 0)
  # the last live TEXT write, and how many there were in the last 30 min (reads back from the end only that far)
  read -r last_write writes_30m < <(tac logs/swan_actions.jsonl 2>/dev/null | grep -F '"live": true' | python3 -c 'import sys,json,time,datetime as d
W = {"post", "reply", "reply_back", "second_voice", "journalist", "thread", "thread_answer", "repost"}
now, last, n = time.time(), 0, 0
for l in sys.stdin:
    try:
        r = json.loads(l)
    except ValueError:
        continue
    if r.get("act") in W and r.get("role") != "swarm":
        t = d.datetime.fromisoformat(r["ts"]).timestamp()
        last = last or int(t)
        if t < now - 1800:
            break
        n += 1
print(last, n)')
  last_write=${last_write:-0}; writes_30m=${writes_30m:-0}
  up_since=$(date -d "$(systemctl show swan-bot -p ActiveEnterTimestamp --value 2>/dev/null)" +%s 2>/dev/null || echo "$now")
  if [ $((now - last_any)) -gt 1200 ]; then
    problem="BOT HUNG: nothing logged for $(((now - last_any) / 60)) min (service is up)"
  elif [ $((now - last_write)) -gt "$NO_WRITE_S" ]; then
    problem="BOT NOT WRITING: no post or reply for $(((now - last_write) / 60)) min (LLM quota? feed lock? a stuck voice? check journalctl -u swan-bot)"
  elif [ "$writes_30m" -lt "$SLOW_N" ] && [ $((now - up_since)) -gt 1800 ]; then
    problem="SLOW: $((writes_30m / 30)).$(( writes_30m * 10 / 30 % 10 )) writes/min over the last 30 min ($writes_30m writes, alarm under $SLOW_N; the cap is 3.0/min). Paid models parked? gate rejects? an empty queue? Dashboard tiles, then journalctl -u swan-bot"
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
