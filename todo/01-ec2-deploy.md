# 01: Move swan_bot from the laptop to EC2: **done 2026-10-20 10:17 UTC**

The bot runs on EC2 under systemd. Everything about the box, the units and the commands is in [hosting](../docs/04-technical/hosting.md). The laptop tmux bot was stopped cleanly with Ctrl-C at the cutover, and its `secrets/`, `data/` and `logs/` were copied across.

## Still open (Marc, AWS console)
- [ ] Elastic IP (the auto-assigned IP changes on stop/start); then update `~/.ssh/config` and `hosting.md`.
- [ ] Termination protection on.
- [ ] Security group: SSH from team IPs only.
- [ ] Billing budget alert.
- [ ] Teammates' public SSH keys into `~ec2-user/.ssh/authorized_keys` (don't share the PEM).
- [ ] Alert channel: [11](11-alert-channel.md).
- [ ] If `journalctl -u swan-sync` shows a Mongo timeout: add the box's IP to Atlas Network Access.

## Rule that stays
**Never run a second `--live` bot** (laptop or anywhere). The write budget is team-wide and the accounts are shared. Dry runs (`--samples N`) on laptops are fine. They do use the shared Gemini key and feed-read budget, so keep them short.
