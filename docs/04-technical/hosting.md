# Hosting: the EC2 box that runs swan_bot (set up 2026-10-20)

The bot moved from Marc's laptop (tmux) to EC2 on 2026-10-20 at 10:17 UTC. **It is the team's only live writer**, so never start another `--live` run anywhere else.

## The box
| | |
|---|---|
| Instance | `i-06471b75b0166b3c7` (`ctn_server`), region **ap-southeast-2** (Sydney) |
| Type | t3.micro: 2 vCPU, 913 MB RAM + 1 GB swap (`/swapfile`); credit spec *unlimited* |
| OS | Amazon Linux 2023, user **`ec2-user`**, Python 3.13 venv at `~/ctn/.venv` |
| Address | `3.107.41.124` / `ec2-3-107-41-124.ap-southeast-2.compute.amazonaws.com`. **Auto-assigned, so it changes if the instance is stopped and started.** Attach an Elastic IP to keep it |
| SSH | key pair `ctn_server_key` (Marc holds the PEM). Teammates: send Marc your **public** key to add to `~ec2-user/.ssh/authorized_keys`; don't share the PEM |
| GitHub access | read-only deploy key `~/.ssh/ctn_deploy` on the box (GitHub deploy key id 167049318) |

Local SSH config (`~/.ssh/config`):
```
Host swan-ec2
    Hostname 3.107.41.124
    User ec2-user
    IdentityFile ~/.ssh/ctn_server_key.pem
```

## What runs (systemd; unit files in `deploy/`)
| Unit | What | When |
|---|---|---|
| `swan-bot.service` | `deploy/run.sh`: the live bot. Restarts 60 s after a crash; gives up after 5 crashes in 30 min | always (enabled at boot) |
| `swan-update.timer` | `deploy/update.sh`: if `origin/main` moved, pull, run `deploy/check.sh`, restart the bot. A failed check rolls back | every 2 min |
| `swan-health.timer` | `deploy/healthcheck.sh`: alerts if the bot is down, logs nothing for 20 min, or makes no live write for 90 min | every 10 min |
| `swan-sync.timer` | `scripts/swan_sync_mongo.py`: copies our records to the team MongoDB | every 15 min |

**To change how the bot runs** (accounts, pace, flags), edit `deploy/run.sh` and push to `main`. To change the code, push to `main`. Either way it's live in about 2 minutes, unless checks fail.

## State on the box (gitignored, never in git)
`~/ctn/.env` (600), `~/ctn/secrets/swan_accounts.json` (600), `~/ctn/data/swan_state.json`, `~/ctn/logs/` (`swan_actions.jsonl` = the attribution log, `deploys.jsonl`, `alerts.log`). Back up `secrets/` and `logs/` now and then: `scp -r swan-ec2:ctn/secrets swan-ec2:ctn/logs ./backup/`.

## Alerts
`deploy/alert.sh` posts to `ALERT_WEBHOOK_URL` in `.env` (a Discord or Slack incoming webhook) and always writes `logs/alerts.log`. Alerts fire on: crash, systemd giving up, bot hung, no writes, deploy done, deploy failed, and recovery. `HEALTHCHECK_PING_URL` (optional, e.g. healthchecks.io) is pinged while healthy, so the whole VM dying is caught too. **Neither is set yet.** Options: [todo/11](../../todo/11-alert-channel.md). Open AWS/GitHub items: [todo/README](../../todo/README.md#ops-leftovers-small-marc).

## Everyday commands
```bash
ssh swan-ec2
journalctl -u swan-bot -f                    # live output (drafts, posts, errors)
systemctl status swan-bot                    # up?
sudo systemctl stop swan-bot                 # KILL SWITCH (stays stopped; deploys won't restart it)
sudo systemctl start swan-bot                # back on
cat ~/ctn/logs/deploys.jsonl | tail          # what code is live
cd ~/ctn && git log -1 --oneline
```
Stopping sends SIGINT. The bot saves state and pending reply-backs, then exits. A stop that lands mid-request can, rarely, lose the log line for that one post.

## To do on the AWS side (Marc)
- Attach an **Elastic IP**, then update `~/.ssh/config` and this file.
- Turn on **termination protection**.
- Security group: SSH only from team IPs.
- **Budget alert** (Billing → Budgets, e.g. $10/month). t3 *unlimited* credits can bill if CPU stays high; the bot is I/O bound, so it shouldn't.
- MongoDB Atlas: if `swan-sync` fails with a timeout, add `3.107.41.124` (or the Elastic IP) to Atlas *Network Access*.
