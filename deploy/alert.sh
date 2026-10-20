#!/usr/bin/env bash
# Send a one-line alert to the team webhook (ALERT_WEBHOOK_URL in .env: a Discord or Slack incoming webhook).
# Always appends to logs/alerts.log. Never include secrets in the message.
cd "$(dirname "$0")/.."
msg="[swan-ec2] $*"
mkdir -p logs && echo "$(date -u +%FT%TZ) $msg" >> logs/alerts.log
url=$(grep -E '^ALERT_WEBHOOK_URL=' .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d "\"'")
[ -z "$url" ] && exit 0
key=text; case "$url" in *discord*) key=content ;; esac
body=$(python3 -c 'import json,sys; print(json.dumps({sys.argv[1]: sys.argv[2][:1900]}))' "$key" "$msg")
curl -fsS -m 15 -H 'Content-Type: application/json' -d "$body" "$url" > /dev/null || echo "alert send failed" >> logs/alerts.log
