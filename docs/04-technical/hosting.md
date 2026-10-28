# Hosting: the EC2 box that runs swan_bot (set up 2026-10-20)

The bot moved from Marc's laptop (tmux) to EC2 on 2026-10-20 at 10:17 UTC. **It is the team's only live writer**, so never start another `--live` run anywhere else.

## The box
| | |
|---|---|
| Instance | `i-06471b75b0166b3c7` (`ctn_server`), region **ap-southeast-2** (Sydney) |
| Type | t3.micro: 2 vCPU, 913 MB RAM + 1 GB swap (`/swapfile`); credit spec *unlimited* |
| OS | Amazon Linux 2023, user **`ec2-user`**, Python 3.13 venv at `~/ctn/.venv` |
| Address | **Elastic IP `13.210.120.238`** (attached 2026-10-21; stays the same across stop/start). Was auto-assigned `3.107.41.124` before |
| SSH | key pair `ctn_server_key` (Marc holds the PEM). Teammates: send Marc your **public** key to add to `~ec2-user/.ssh/authorized_keys`; don't share the PEM |
| GitHub access | read-only deploy key `~/.ssh/ctn_deploy` on the box (GitHub deploy key id 167049318) |

Local SSH config (`~/.ssh/config`):
```
Host swan-ec2
    Hostname 13.210.120.238
    User ec2-user
    IdentityFile ~/.ssh/ctn_server_key.pem
```

## What runs (systemd; unit files in `deploy/`)
| Unit | What | When |
|---|---|---|
| `swan-bot.service` | `deploy/run.sh`: the live bot. Restarts 60 s after a crash; gives up after 20 starts in 30 min (a crash loop). Since 25 Oct the next code push starts it again (`update.sh` `revive_gave_up`, only for `Result=start-limit-hit`: a deliberate stop stays stopped) | always (enabled at boot) |
| `swan-blue.service` | `python -m swan_blue --live` (from `src/`): the Blue track ([blue-reporting](../06-strategy/blue-reporting.md)). Reports competitor ring bots from one reserved booster (`config.blue_reporter`); report routes only. Writes `data/blue_state.json`, `data/blue_status.json` (dashboard), `logs/blue_reports.jsonl`, token in `secrets/blue_session.json`. Approve: `ctn/scripts/blue.sh approve all`. `touch ~/ctn/BLUE_OFF` stops filing | always (enabled by `install.sh`) |
| `swan-update.timer` | `deploy/update.sh`: if `origin/main` moved, check the new commit in a throwaway worktree (`deploy/check.sh`: compile, import and `--help` checks, then the fast test suite, serially: 124 s on 24 Oct. It is the only gate before a restart, since CI runs beside it and blocks nothing. The suite has run on the box since 23 Oct, when `check.sh` lost its `SKIP_TESTS` test; kept on purpose 25 Oct, the t3.medium has the memory. `SKIP_TESTS=1` skips it), then move the tree onto it and restart the bot and swan-blue (not for docs, todo, `content/lab/` or `src/swan_dash/` only; the bot saves its state on the stop signal and keeps quota parks in `data/llm_parks.json`, 24 Oct). A failed check leaves the box untouched, alerts once and is skipped until the next push; a run killed after the reset is settled by the next tick | every 2 min |
| `swan-health.timer` | `deploy/healthcheck.sh`: alerts if the bot is down, logs nothing for 20 min, or makes no text write (post, reply, reply-back, second voice, journalist, thread, repost; not likes, follows or the swarm) for 15 min (`SWAN_NO_WRITE_ALERT_S` in `.env`, seconds; was any `live` row for 90 min until 25 Oct, which booster likes kept green). Alerts when a problem starts, hourly while it lasts, once when it clears | every 10 min |
| `swan-sync.timer` | `scripts/swan_sync_mongo.py`: copies our records to the team MongoDB | every 15 min |
| `swan-watch.timer` | `scripts/swan_watch.py` (read-only): finds our voices' moderator-hidden posts (alert; the bot takes a voice with 1 off amplification, stops it writing at 2) and, hourly, scores our amplified posts against Trending with `ring_audit.py` (alert when we look as coordinated as the leaders). Writes `data/swan_watch.json`, `logs/swan_watch.jsonl` | every 20 min |
| `swan-factdesk.timer` | `scripts/swan_factdesk.py` (read-only: the papers only, no Legit Social calls): new articles checked against `content/facts.toml`. A contradicted fact is paused at once in `data/facts_paused.json` (the bot picks it up on its next draft, no restart) and alerted; everything else is proposed in `data/fact_proposals.jsonl` and the Mongo `fact_proposals` / `fact_pauses` collections. Review on a laptop with `scripts/facts_review.py` ([workflow](../06-strategy/system-architecture.md#9-fact-desk-who-reviews-when-how-2026-10-21)) | hourly |
| `swan-dash.timer` | `src/swan_dash/build.py`: the team dashboard page, served by nginx behind a password ([todo/09](../../todo/09-dashboard-cop.md)). Installed by `deploy/dash_setup.sh`, not `install.sh` | every minute |
| `swan-portal.timer` | `src/swan_dash/portal.py`: our rank, score, account counts and points log from the CTN portal, with the session cookie in `secrets/portal_cookie` ([todo/09](../../todo/09-dashboard-cop.md)). The timer fires every minute with `--auto` and the program reads only when due (`portal.plan`): a full read (leaderboard, team page, points log) at :02 and :32, and a short one (no team page) once a minute from 40 s after the minute the portal posts its hourly points (about :19, read from the points log) until the board's scores change, 12 min at most | every minute (reads about 3 an hour) |
| `swan-swarm.timer` | `scripts/swan_swarm.py --live`: the swarm ([swarm.md](swarm.md)) registers up to 20 accounts for minhnguyenhoang, then likes and reposts Vote No posts. `touch SWARM_OFF` pauses it | every 5 min |

**To change how the bot runs** (accounts, pace, flags), edit `deploy/run.sh` and push to `main`. To change the code, push to `main`. Either way it's live in about 2 minutes, unless checks fail.

## State on the box (gitignored, never in git)
`~/ctn/.env` (600), `~/ctn/secrets/swan_accounts.json` (600), `~/ctn/data/swan_state.json`, `~/ctn/data/facts_paused.json` (the fact desk's pauses: never edit it to lift one, see the workflow above), `~/ctn/logs/` (`swan_actions.jsonl` = the attribution log, `deploys.jsonl`, `alerts.log`). Back up `secrets/` and `logs/` now and then: `scp -r swan-ec2:ctn/secrets swan-ec2:ctn/logs ./backup/`.

## Alerts
`deploy/alert.sh` posts to `ALERT_WEBHOOK_URL` in `.env` (a Discord or Slack incoming webhook) and always writes `logs/alerts.log`. Alerts fire on: crash, systemd giving up, bot hung, no writes, deploy done, deploy failed, and recovery. `HEALTHCHECK_PING_URL` (optional, e.g. healthchecks.io) is pinged while healthy, so the whole VM dying is caught too. **Neither is set** (decided 2026-10-21: the team dashboard shows the same health state, [todo/09](../../todo/09-dashboard-cop.md)); the alerts still land in `logs/alerts.log` and on the page. Open AWS/GitHub items: [todo/README](../../todo/README.md#ops-leftovers-small-marc).

## Everyday commands
```bash
ssh swan-ec2
journalctl -u swan-bot -f                    # live output (drafts, posts, errors)
systemctl status swan-bot                    # up?
sudo systemctl stop swan-bot                 # KILL SWITCH (stays stopped; deploys won't restart it)
sudo systemctl start swan-bot                # back on
touch ~/ctn/AMPLIFY_OFF                       # pause amplification only (likes/thread/reposts), no restart; rm to resume
journalctl -u swan-blue -f                   # the Blue track
touch ~/ctn/BLUE_OFF                          # stop filing reports (scan and rulings carry on); rm to resume
cat ~/ctn/logs/deploys.jsonl | tail          # what code is live
cd ~/ctn && git log -1 --oneline
```
Stopping sends SIGINT. The bot saves state and pending reply-backs, then exits. A stop that lands mid-request can, rarely, lose the log line for that one post.

## To do on the AWS side (Marc)
- [x] Elastic IP `13.210.120.238` attached (2026-10-21).
- Turn on **termination protection**.
- Security group: SSH only from team IPs.
- **Budget alert** (Billing → Budgets, e.g. $10/month). t3 *unlimited* credits can bill if CPU stays high; the bot is I/O bound, so it shouldn't.
- MongoDB Atlas: `13.210.120.238` must be in Atlas *Network Access*, or `swan-sync` times out (the old `3.107.41.124` can be removed).
