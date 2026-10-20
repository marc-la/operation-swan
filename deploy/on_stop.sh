#!/usr/bin/env bash
# ExecStopPost of swan-bot: alert if the bot stopped for any reason other than a clean stop/restart.
cd "$(dirname "$0")/.."
if [ "${SERVICE_RESULT:-success}" != "success" ]; then
  deploy/alert.sh "BOT CRASHED (result=$SERVICE_RESULT code=$EXIT_CODE status=$EXIT_STATUS) at $(git rev-parse --short HEAD); systemd restarts it in 60 s. Logs: journalctl -u swan-bot -n 50"
fi
