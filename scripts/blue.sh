#!/usr/bin/env bash
# Blue track on EC2 (src/swan_blue, todo/07). From a laptop:
#   ssh swan-ec2 'ctn/scripts/blue.sh approve all'             # what the dashboard's Blue section lists now
#   ssh swan-ec2 'ctn/scripts/blue.sh approve 145823,145850'   # some of them (a<id> for an account)
# Stop filing: touch ~/ctn/BLUE_OFF (rm to resume). The service is swan-blue.service.
cd "$(dirname "$0")/../src" && exec ../.venv/bin/python -m swan_blue "$@"
