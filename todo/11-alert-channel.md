# 11: Where bot alerts go (future work)

**Owner:** anyone · **Depends on:** EC2 (done) · **Effort:** 15 min for option A

The alert plumbing is built ([hosting: Alerts](../docs/04-technical/hosting.md#alerts)). `deploy/alert.sh` posts one-line messages to `ALERT_WEBHOOK_URL` from `~/ctn/.env` on the EC2 box. Today the URL is empty, so alerts only go to `logs/alerts.log`. Pick a channel:

| Option | How | Notes |
|---|---|---|
| **A. Discord team channel (recommended)** | In **our own** team server (not the competition server): channel → Edit → Integrations → Webhooks → New → copy URL → put `ALERT_WEBHOOK_URL=<url>` in `~/ctn/.env` on EC2 | Everyone in the channel gets a phone notification. `alert.sh` already speaks Discord's format |
| B. Slack channel | Incoming-webhook app → same `.env` key | `alert.sh` sends Slack's format for non-Discord URLs |
| C. Discord DM | Webhooks can't DM. Needs a Discord bot token + a user id + a small script calling the DM API | More moving parts than A for the same effect |
| D. GitHub notification | `alert.sh` opens an issue (`gh api repos/marc-la/ctn/issues`) and closes it on recovery. Assignees get email/mobile notifications | Needs a fine-grained PAT with Issues: write on the box (a new secret) |
| E. Phone push, no accounts | ntfy.sh: `curl -d "$msg" ntfy.sh/<random-topic>` and subscribe in the ntfy app | Anyone who guesses the topic can read it, so use a long random topic |
| F. Whole-VM dead-man switch | healthchecks.io free check → `HEALTHCHECK_PING_URL=` in `.env`. It emails/Discords us when pings stop | Covers what A–E can't: the instance itself dying. Do it alongside A |

## Done when
`deploy/alert.sh "test"` on the box shows up in the chosen channel, and `HEALTHCHECK_PING_URL` is set.
