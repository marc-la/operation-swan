# 09: Common operating picture: one page for the team (primary objective, 21 Oct)

**Owner:** Marc · **Depends on:** EC2 (done), Elastic IP · **Not** on 08: v1 reads files already on the box

**Status 2026-10-21:** built (`src/swan_dash/`, `deploy/swan-dash.*`, `deploy/nginx-swan.conf`, `deploy/dash_setup.sh`, `scripts/score.sh`, `tests/test_dash.py`). Left: the one-time setup on the box (below). No Discord alert channel: decided 2026-10-21 that the page is enough (old todo/11 dropped).

## What the page is for
A teammate opens it on their phone and in **five seconds** knows three things, in this order:
1. **Is anything wrong right now?** (do I need to act)
2. **Are we winning?** (score, rank, next milestone)
3. **What is the bot doing?** (its output, as it happens)

Anything that doesn't answer one of those stays off the page. Analysis (Trending, rivals, Blue, per-frame results) belongs in the morning report and notebooks, not here.

## Layout (one column, works on a phone, refreshes every 60 s)
```
SWAN · as of 14:32 Perth (1 min ago)
┌──────────────────────────────────────────────────────────┐
│ ● RUNNING · last post 2 min ago                          │  1 banner
└──────────────────────────────────────────────────────────┘
 SCORE 3,140    RANK 14 / 145    +620 since 9pm              2 scoreboard
 Next: 2,500 by Sat 25 Oct 9pm Perth ✓ · ×2 multiplier in 4d 7h
 (entered by marc, 2 h ago)

 WRITES LAST HOUR   ACCOUNTS            LLM                ERRORS LAST HOUR
 142 / 180          12 live · 0 banned  flash-lite         0 rate-limited
                    13 of 200 used      1st of 7 · 812 today  4 drafts rejected   3 vitals

 ACTIVITY (latest 30 actions)                                4 log
 14:30  priya    reply      "Twelve thousand doses land…"  ↗
 14:27  lani     post       "Ferry was late again, and…"  ↗
 14:21  —        LLM        gemini-3.8-flash parked (daily quota)
 ...
 footer: running a1b2c3d (deployed 11:02) · page built 14:32:05
```

### 1. Banner: one line, one colour, says what's wrong in plain words
| Colour | When | Example text |
|---|---|---|
| **Red** | service not active; nothing logged for 20 min or no live write for 90 min (`deploy/healthcheck.sh`); every LLM parked | `DOWN: swan-bot stopped at 13:40. Check journalctl -u swan-bot` |
| **Amber** | the bot hasn't reported for 5 min; on a fallback LLM; an account suspended in the last 24 h; any 429 in the last hour | `DEGRADED: on fallback LLM gpt-oss-120b (Gemini quota spent until 3pm)` |
| **Green** | none of the above | `RUNNING · last post 2 min ago` |

Red reuses `data/health_state` from `deploy/healthcheck.sh` (it runs every 10 min whether or not an alert channel is set), so the wording matches `logs/alerts.log`.

### 2. Scoreboard
Score, rank out of N teams, change since the day rolled over (9pm Perth), the next poll milestone with how much is still needed, and when the multiplier next changes. **Always show who entered the score and how long ago**, so a stale number looks stale.

**Source:** typed in by hand for now: `ssh swan-ec2 'ctn/scripts/score.sh 3140 14 145 kim'` (score, rank, teams, who) appends to `data/score.json`. **Next step:** an hourly fetch of the portal leaderboard with a saved login session on the box, once the organisers confirm automated reads of the portal are fine ([discrepancies](../docs/05-reference/discrepancies-and-open-questions.md) Q6). The fetcher writes the same `data/score.json`, so the page doesn't change.

### 3. Vitals: four tiles, each a number against its limit
- **Writes last hour / 180** (the team cap is 3/min). Low means we're wasting budget; near 180 means any manual post will 429.
- **Accounts:** live (of 50), banned, used (of 200). Banned is a lost life, so it's on the front page.
- **LLM:** the model answering now and its place in the chain, calls today. Names only, never keys. A parked model shows in the activity log when it parks, not as a permanent grid.
- **Errors last hour:** 429s and rejected drafts. A rising reject count is the earliest sign the LLM has gone bad.

If the bot can't know a number yet (e.g. whether an account was suspended), **leave the tile out rather than show a guess.**

### 4. Activity log
Newest first, last 30: time (Perth), persona, action, the first ~60 characters, a link to the post on Legit Social. LLM parks, deploys and alerts are interleaved as grey rows so cause and effect sit together. Rejected drafts and dry-run rows are not shown (they're counted in vitals).

### Labels
Times are always Perth (AWST) and say so once in the header. "Today" always means "since 9pm Perth" (when the competition day rolls over). Numbers are shown against their limit (`142 / 180`, not `142`).

### Deliberately left out
Trending, rival clusters, Blue reports, per-frame/per-persona tables, charts, persona-to-account details beyond usernames, token counts, anything from `.env` or `secrets/`. Add one only when someone has asked the same question twice and the page couldn't answer it.

## Build: static page, no app server
- **Bot:** the live bot writes `data/status.json` at most every 30 s (temp file + rename): the LLM chain with each model's park time and reason, 429s in the last hour, account counts. Model parks are also logged (`act: llm_park`). Dry runs don't write it, so a test run on the box can't overwrite the live bot's status.
- **`src/swan_dash/build.py`** (`swan-dash.timer`, every minute): reads `data/status.json`, the tail of `logs/swan_actions.jsonl`, `logs/alerts.log`, `logs/deploys.jsonl`, `data/health_state`, `data/score.json` and `systemctl is-active swan-bot`. It renders `templates/index.html.j2` with Jinja2 (autoescape on) and writes `/var/www/swan/index.html` (temp file + rename). Local preview: `cd src && ../.venv/bin/python -m swan_dash.build --out /tmp/swan`.
- **No JavaScript.** Refresh with `<meta http-equiv="refresh" content="60">`. Inline CSS only.
- nginx serves `/var/www/swan/` and nothing else.

## Security: the page must not become a way into the box
The box holds the team code, every bot password and the only live writer, so this is the design constraint, not an afterthought. The page also lists our bot usernames, and a rival with that list could report them all on the Blue track.

**Why this design is low-risk:** the web server only sends static files. Nothing on the web side runs code, takes input or can write anywhere. The things that read secrets (the bot, the builder) never listen on a port. An attacker gets at most what's on the page, and only past the password.

| Risk | Control |
|---|---|
| Someone reads the page | HTTPS + nginx basic auth. One long random password (≥20 chars) shared in the team password manager or a DM, never in git or Discord channels. `limit_req` on the location to slow guessing |
| No domain for a certificate | Use `3-107-41-124.sslip.io` (resolves to our IP) with certbot/Let's Encrypt. Needs the Elastic IP first, or the name breaks when the IP changes |
| Secrets end up on the page | The builder never opens `.env` or `secrets/`; it renders an explicit list of fields, not whole records. `swan-dash.service` makes `.env`, `secrets/` and `~/.ssh` inaccessible to it and gives it no network. `tests/test_dash.py` puts a fake team code in `.env`, `secrets/` and the environment and fails if it appears on the page |
| Untrusted text (rivals' and citizens' posts in `target_text`, LLM output) carries script | Jinja autoescape on; we don't render `target_text` at all; header `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; img-src 'self'` so no script can run even if escaping fails |
| nginx itself has a bug | Security group opens only 80 (redirect + certificate renewal) and 443. nginx runs as its own user and can read only `/var/www/swan`. `dnf-automatic` applies security updates. `server_tokens off`, `autoindex off`, no proxy or CGI blocks |
| A form or button later becomes a write path | v1 has none. Score entry is over SSH. A pause button would be a new design and needs its own review |
| SSH is the real door | Unchanged: keys only, no passwords. The AWS item "SSH from team IPs only" in [todo/README](README.md#ops-leftovers-small-marc) is still worth doing even though the page doesn't need it |
| Search engines | `X-Robots-Tag: noindex` and a `robots.txt` that disallows everything |

**Higher-assurance alternative (if we want no public port at all):** teammates join a Tailscale network and nginx listens only on the Tailscale interface; port 443 stays closed to the internet. It costs each teammate an app install. Pick this if the team would rather not have any public page.

## Setup on the box (once, Marc)
1. AWS console: attach an **Elastic IP** to `ctn_server`, update `~/.ssh/config` and [hosting](../docs/04-technical/hosting.md).
2. Security group: allow inbound **80 and 443 from anywhere** (80 is for the certificate check and the redirect).
3. On the box, after the code is on `main`: `cd ~/ctn && sudo deploy/dash_setup.sh <elastic-ip-with-dashes>.sslip.io`. It installs nginx, asks you to choose the password (user `swan`), gets the certificate, installs the timers and turns on automatic security updates.
4. Check: `systemctl status swan-dash`, open `https://<ip-with-dashes>.sslip.io` on a phone, and send the URL and password to the team privately.

## Done when
- A teammate opens the HTTPS URL on their phone, enters the password and sees all four sections; the page is never more than 2 min old.
- Stopping `swan-bot` turns the banner red within 2 min.
- `tests/test_dash.py` passes, and the security group shows only 22, 80 and 443.
