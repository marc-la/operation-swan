# 02: Push to `main` → EC2 pulls, tests and restarts the bot

**Owner:** Marc · **Depends on:** 01 · **Unblocks:** a team workflow where anyone can ship a change through Claude Code and a PR

## Why
Marc wants a loop where anyone on the team changes the bot (usually with Claude Code), merges to `main`, and the live bot picks it up with no SSH. It has to be safe, because a bad push becomes live posts within minutes.

## Recommended design: pull-based (EC2 polls GitHub)
Pull is simpler and safer than GitHub Actions SSHing in. No inbound SSH from GitHub's IP ranges and no SSH key stored in GitHub secrets.

```
GitHub main ──(read-only deploy key)──> EC2: swan-deploy.timer (every 2 min)
                                             └─ deploy/update.sh
                                                  git fetch; if origin/main != HEAD:
                                                    git checkout <new sha> (into /opt/ctn)
                                                    pip install -r requirements.txt (if changed)
                                                    run checks (pytest + dry-run --samples 2)
                                                    pass → systemctl restart swan-bot; log sha
                                                    fail → git checkout <old sha>; keep old bot running; write deploy/FAILED
```

- `deploy/update.sh`, `deploy/swan-deploy.service` and `deploy/swan-deploy.timer` are committed. The `swan` user gets a narrow sudoers rule allowing only `systemctl restart swan-bot`.
- Every deploy appends `{ts, old_sha, new_sha, result}` to `logs/deploys.jsonl`. The dashboard (09) shows it, so we know which code version wrote which posts. Also log the running git sha in each action record (one-line change in `bot.py`) for attribution.

## GitHub Actions: CI only (no deploy)
`.github/workflows/ci.yml` on every PR and every push to `main`:
- `pip install -r requirements.txt`, then `python -m compileall src scripts`;
- `pytest` for whatever tests exist. Start with `tests/test_quality.py` (the quality gate on known-good and known-bad drafts) and `tests/test_targeting.py` (`classify`);
- **no secrets in CI** and no live calls. Tests that need the network are skipped.

Branch protection on `main`: require the CI check, and a PR rather than direct pushes. Two humans aren't needed; one green CI is enough.

## Restart safety
- On SIGTERM the bot must finish or abandon the current write cleanly and save state. Today `KeyboardInterrupt` is handled, SIGTERM isn't: add a handler that raises `KeyboardInterrupt`.
- A restart must not burst-register accounts. `Accounts.__init__` already spaces registration from the last `created`. Keep it that way.
- `--hours 10000` in the unit. The deploy restarts, not the hours timer.

## Alternative (only if Marc prefers push)
An Actions job on push to `main`: `appleboy/ssh-action` with `EC2_HOST` and `EC2_SSH_KEY` in repo secrets, running the same `deploy/update.sh`. It works, but needs SSH open to GitHub runners (wide IP ranges) or a self-hosted runner.

## Done when
A trivial PR (e.g. a comment change) merged to `main` shows up in `logs/deploys.jsonl` on EC2 within 3 minutes, and the bot restarts and keeps posting. A deliberately broken PR fails CI. A broken commit that sneaks through rolls back and leaves the old bot running.
