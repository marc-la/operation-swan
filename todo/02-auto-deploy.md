# 02: Push to `main` → EC2 pulls, checks and restarts the bot: **built 2026-10-20**

How it works ([hosting](../docs/04-technical/hosting.md#what-runs-systemd-unit-files-in-deploy)):
- `swan-update.timer` runs `deploy/update.sh` every 2 min. If `origin/main` moved: `git reset --hard` to it (ignored files untouched), `pip install` if `requirements.txt` changed, then `deploy/check.sh`. Pass → reinstall units if a `deploy/*.service|timer` changed, then `systemctl try-restart swan-bot`. Fail → roll back, alert, and the old bot keeps running.
- Every deploy is logged to `logs/deploys.jsonl` and sent as an alert.
- Pull-based: EC2 reads GitHub with a read-only deploy key. GitHub never SSHes in.
- CI: `.github/workflows/ci.yml` runs the same `deploy/check.sh` on every PR and every push to `main`.
- **Seamless by default:** anyone who merges to `main` ships to the live bot within ~2 min. That includes `deploy/run.sh` (the bot's flags).

## Still open
- [ ] **Branch protection on `main`** (GitHub → Settings → Branches): require the `checks` CI job, and require PRs. Today a direct push with a logic bug (it compiles, but posts junk) goes live.
- [ ] **Real tests** in `tests/` (CI installs pytest; `check.sh` runs them when present). At minimum, `quality.check` on known-good and known-bad drafts, and `targeting.classify` on sample citizen posts. These catch "compiles but posts junk".
- [ ] Log the running git sha in every action record (`bot.py` `log()`), for attribution per code version.
- [ ] Graceful stop: today SIGINT → KeyboardInterrupt, which can land mid-request. Better: a flag set by a signal handler, checked at the top of the loop and in sleeps.
- [ ] A staging lane (optional): a `dryrun` branch that the box runs as `--samples 5` and posts the drafts to the alert channel, so a teammate can eyeball prompt changes before merging.
