#!/usr/bin/env bash
# One-time setup on the EC2 box (run as ec2-user with sudo): sudo deploy/install.sh
# --units-only: just (re)install the systemd units (update.sh calls this when a unit file changes).
set -euo pipefail
cd "$(dirname "$0")"
install -m 644 swan-bot.service swan-alert@.service swan-update.service swan-update.timer \
  swan-health.service swan-health.timer swan-sync.service swan-sync.timer \
  swan-followup.service swan-followup.timer swan-watch.service swan-watch.timer /etc/systemd/system/
# dashboard units only once deploy/dash_setup.sh has made the web root (todo/09)
if [ -d /var/www/swan ]; then install -m 644 swan-dash.service swan-dash.timer swan-certbot.service swan-certbot.timer swan-portal.service swan-portal.timer /etc/systemd/system/; fi
systemctl daemon-reload
systemctl enable --now swan-update.timer swan-health.timer swan-sync.timer swan-followup.timer swan-watch.timer
[ "${1:-}" = "--units-only" ] && exit 0
systemctl enable swan-bot      # starts at boot; start it by hand the first time: sudo systemctl start swan-bot
echo "installed. sudo systemctl start swan-bot to go live"
