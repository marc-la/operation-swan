# 01: Move swan_bot from the laptop to EC2 (systemd) (today)

**Owner:** Marc · **Depends on:** an EC2 instance Marc already has · **Unblocks:** 02, 03, 09

## Why
The bot runs in tmux on a WSL laptop. It stops when Windows sleeps, and teammates can't see or restart it. Every hour offline costs points, and ×2/×4 starts 26 Oct.

## Where things are now
- Code: `src/swan_bot/`, entry `scripts/run_swan.py` (`--live --yes --accounts N --hours H`). Runbook: [swan-bot-runbook](../docs/04-technical/swan-bot-runbook.md).
- State that **must move with the bot** (all gitignored, copy with `scp`):
  - `secrets/swan_accounts.json` (passwords and tokens of our 12 live accounts, mode 600). Without it, the bot registers new accounts and abandons the old ones;
  - `data/swan_state.json` (who we contacted, pending second voices);
  - `logs/swan_actions.jsonl` (our attribution log; keep appending to it);
  - `.env` (`CTN_TEAM_CODE`, `CTN_SIDE`, `GEMINI_API_KEY`; add `CTN_OPERATOR=marc`).
- Repo: `https://github.com/marc-la/ctn.git` (private? check; the EC2 box needs a read-only **deploy key**).

## Where to keep the EC2 details
- Non-secret facts go in `docs/04-technical/hosting.md` (new): instance id, region, type, public IP or DNS, OS user, security-group rules, budget alert, and who has SSH access.
- **Not** in the repo: SSH private keys (`~/.ssh/` on each person's machine) or the deploy key's private half (on EC2 only).
- Local convenience: an `~/.ssh/config` entry `Host swan-ec2` so everyone can type `ssh swan-ec2`.

## Steps
1. Check the box: Ubuntu, `t3.small` or bigger is plenty (the bot is I/O bound). Security group: SSH from team IPs only. If 09 lands, add 443 (or 80) later. Set a Billing budget alert.
2. On EC2: `sudo apt install -y python3-venv git tmux`. Create user `swan`, clone to `/opt/ctn`, then `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`.
3. Copy `.env`, `secrets/`, `data/`, `logs/` from the laptop **after stopping the laptop bot** (Ctrl-C in `tmux attach -t swan`, wait for "done:"). Then `chmod 600 .env secrets/*`.
4. Dry-run on EC2: `.venv/bin/python scripts/run_swan.py --samples 3`, and read the drafts.
5. Install a systemd unit `deploy/swan-bot.service` (commit the unit file; it holds no secrets):
   - `User=swan`, `WorkingDirectory=/opt/ctn`, `ExecStart=/opt/ctn/.venv/bin/python scripts/run_swan.py --live --yes --accounts 12 --hours 10000`;
   - `Restart=on-failure`, `RestartSec=60` (not `always`: a crash loop must not hammer the API; also set `StartLimitBurst=5`);
   - `Environment=PYTHONUNBUFFERED=1`; stdout goes to `journalctl -u swan-bot -f`.
6. `sudo systemctl enable --now swan-bot`, then watch `journalctl` for 10 minutes and confirm writes appear in `logs/swan_actions.jsonl`.
7. Kill switch: `sudo systemctl stop swan-bot`. Then add a `PAUSE` file check in the loop (see 03) so non-admins can pause without sudo.
8. Write `docs/04-technical/hosting.md` and update the runbook's Hosting section to point at it.

## Guardrails
- **Never run the laptop and EC2 bots at the same time** (same accounts, shared 3/min, double replies to one citizen).
- Logins and registrations are 5/min per IP. The move changes our IP; that's fine, but don't re-login all 12 accounts in a burst (tokens resume via `account_from_token`).
- `.env` is mode 600, owned by `swan`, and never committed.

## Done when
`systemctl status swan-bot` is active, writes are logged from EC2, the laptop tmux is gone, and `hosting.md` says how to SSH in, stop, start and read logs.
