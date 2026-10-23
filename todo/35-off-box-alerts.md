# 35: Off-box alerts. Hear within minutes when the box stalls or the bot stops writing, from somewhere that is not the box

**Written 2026-10-23 by Claude at Marc's request (item 1 of [todo/34](34-box-robustness.md)). Owner: whoever picks it up.
Priority: high, before the x2 multiplier on 26 Oct. Needs: one decision from Marc (which service, see "Decide first").**

## Why

23 Oct: the bot wrote ~0.4/min instead of 2.9/min for about 2 hours, and the box was unreachable for most of it. We
found out because Marc opened the dashboard and the site was slow. Everything that could have warned us lives on the
box: the dashboard, `alert.sh`, the health timer. A starved box cannot send its own alarm.

Two checks we already have did **not** fire, and need tightening as well as moving:

- `deploy/healthcheck.sh` (every 10 min) alerts "BOT NOT WRITING" only after **90 min** with no live write, and counts
  reposts. On 23 Oct replies had stopped but reposts carried on, so it never fired. The target is ~2.9 writes/min.
- "BOT HUNG" needs 20 min without any log line; the box was hung but the log was not stale at first.

## What we can and cannot use (checked 23 Oct)

- The IAM user `ctn-user` (`.env`: `EC2_ACCESS_KEY`, `EC2_SECRET_ACCESS_KEY`) has EC2 and can read CloudWatch (metrics and
  `describe-alarms`: there are none). It is **not allowed SNS or EventBridge**, so a CloudWatch alarm cannot email or
  message us. It may or may not be allowed `cloudwatch:PutMetricAlarm`: test with a harmless alarm, delete it after.
- An alarm *action* of `arn:aws:automate:ap-southeast-2:ec2:reboot` (or `:recover`) needs no SNS. It reboots on
  `StatusCheckFailed_Instance`. Useful for a dead VM, but on 23 Oct the status checks **passed** while the OS was starved
  (swap, EBS burst gone), so it would not have fired. Treat it as a bonus, not the answer.
- The dashboard is behind nginx basic auth (`deploy/nginx-swan.conf`); only `/robots.txt` is open. An outside probe can
  check that the box answers TLS, and the SSH banner, without any secret.
- `deploy/alert.sh` posts to `ALERT_WEBHOOK_URL` (a Discord or Slack webhook, set in the box's `.env`; it is not in the
  laptop's `.env`). Reuse that webhook for every new alert so the team sees one stream.
- `deploy/healthcheck.sh` already pings `HEALTHCHECK_PING_URL` (box `.env`) every 10 min **only when healthy**. A
  dead-man service that alerts when the pings stop is the missing half. Nothing sets that URL yet.

## Decide first (Marc)

1. **Which dead-man service?** Healthchecks.io (free tier, period 10 min, grace 10 min, alerts to Discord/email/SMS) is the
   least work: it is what `healthcheck.sh` was written for. It receives only "I am alive" pings from our box; no game data,
   no credentials, nothing that touches Legit Social. CLAUDE.md guardrail 2 says "only interact with CTN-provided systems"
   and means the game; this is our own monitoring, but it is an external service, so Marc says yes or no. The alternative with
   nothing third-party is the GitHub Actions probe in step 3 (GitHub is already used for CI).
2. **Where should the alerts go?** Probably the same Discord channel as `alert.sh`; confirm, and say whether a phone push
   (the service's app or SMS) is wanted for the night hours (the team is in Perth, the platform on Sydney time).

## Steps

1. **Dead-man ping (30 min).** Create the check (period 10 min, grace 10 min), put its ping URL in the **box's** `.env` as
   `HEALTHCHECK_PING_URL` (never in git), point its alert channel at the team webhook. Test it for real: `sudo systemctl
   stop swan-health.timer`, wait for the alert, start the timer, wait for "recovered".
2. **Make `healthcheck.sh` mean something (1 h).** It should withhold the ping, and alert, when any of these hold (each with
   its own message, once per episode as it does now):
   - **writes below target:** fewer than ~1 live write a minute over 15 min (not 90 min), counting replies and posts
     separately from reposts (`"act": "reply"` and `"post"` as `"live": true`); reposts alone do not count as writing;
   - **memory:** `MemAvailable` under ~150 MB on two consecutive runs (read `/proc/meminfo`);
   - **OOM kills:** a new `Out of memory` line since the last run (`journalctl -k --since`, or `dmesg`);
   - **no model:** the bot already alerts "NO MODEL" (todo/34 item 5); also check the dashboard's drafting level or count
     `no_model` rows in the last 10 min so it holds the ping if the bot's own alert path is the thing that broke;
   - **disk:** root filesystem over 85% (the log grows ~40 MB a day).
   Read the log with `swan_bot.jsonl.Reader` or `tail -c`, never the whole file (todo/34 item 2). Keep it in bash/python3
   with no new dependencies; the box has 3 GB free now but the check must stay cheap.
3. **A probe from outside the box (1 h).** A scheduled GitHub Actions workflow (`on: schedule`, every 5-10 min; GitHub's
   minimum is 5, and it can be late) that: opens TCP 22 and requires an `SSH-2.0` banner within 10 s (a starved box accepts
   the connection and never sends one: that was the exact symptom on 23 Oct); requests `https://<dashboard host>/robots.txt`
   within 10 s; and on two failures in a row posts to the Discord webhook (a repository secret, never in the repo). It needs
   the dashboard host (the `HOST` in `deploy/nginx-swan.conf`) and the box IP; ask Marc. No credentials of ours leave the box.
4. **Optional self-heal.** A CloudWatch alarm on `StatusCheckFailed_Instance` (2 x 5 min) with the `ec2:reboot` action, if
   `PutMetricAlarm` is allowed. Does not need SNS. Say in the alarm name that it reboots the box.
5. **Money.** `CPUSurplusCreditsCharged` (Unlimited mode) and Bedrock spend are not alertable without SNS. Until that is
   fixed: the 24 Oct check from todo/34 item 7, and the dashboard's Drafting banner for the LLM budget.

## Done when

- Stop `swan-health.timer` on the box: an alert arrives within ~20 min and a "recovered" when it is started again.
- Block port 22 from the outside for a minute (security group) or stop the box: the GitHub probe alerts within ~15 min.
- Run a fake `no_model` or low-write episode on a dry box (or lower the threshold temporarily) and see the alert name the
  cause, once, then "recovered".
- The 23 Oct stall, replayed on paper (writes drop at 23:19 UTC, memory gone at 02:44), alerts us in under 20 minutes.

## Not in scope

Moving the dashboard off the box, a second box, or anything that changes what the bot does on Legit Social.
