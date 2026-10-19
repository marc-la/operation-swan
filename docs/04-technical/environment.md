# Our Dev Environment

How *this repo* is set up. The client's API is in [api-reference.md](api-reference.md).

## Layout

```
ctn/
├── CLAUDE.md                  # context for Claude Code sessions (read first)
├── requirements.txt           # capturethenarrative==0.5.1 (pinned; pulls in openai)
├── .env.example → .env        # CTN_TEAM_CODE, CTN_SIDE  (.env is gitignored)
├── .gitignore                 # secrets, .venv, logs
├── .venv/                     # local virtualenv (not shared)
├── scripts/smoke_test.py      # read-only check that the servers answer
├── docs/                      # all competition knowledge (start at docs/README.md)
└── src/
    └── pypi-capturethenarrative/   # clone of the official client (reference only, v0.5.0)
```

## Setup (each team member)

```bash
git clone <repo> && cd ctn
python3 -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                # then fill in CTN_TEAM_CODE and CTN_SIDE
python scripts/smoke_test.py        # should print trending posts and news headlines
```

Status (2026-10-19): Python 3.13, `capturethenarrative 0.5.1`, `openai 3.35.1`. The smoke test passes against the live servers (no account needed).

## Secrets

| Secret | Where from | Where it goes |
|---|---|---|
| **Team code** (16 chars) | Community portal → team page | `.env` as `CTN_TEAM_CODE` — **never in git, chat screenshots, public gists** (rules §5.6). If leaked: team leader → *Generate a new code* + tell organisers |
| Bot usernames/passwords | You choose at registration (password **cannot be changed**) | `secrets/accounts.json` (gitignored) — record which human owns each bot |
| Session tokens | `account.token` | `secrets/` (gitignored); resume with `social.account_from_token()` to avoid rate-limited logins |

Load in code:
```python
import os
TEAM_CODE = os.environ["CTN_TEAM_CODE"]   # load .env with python-dotenv or `set -a; source .env; set +a`
SIDE = os.environ["CTN_SIDE"]
```

## Notes

- The `src/pypi-capturethenarrative/` folder is its own git clone of the official repo (`origin` = github.com/capturethenarrative/pypi-capturethenarrative). We install the **PyPI** release (pinned) rather than that clone so everyone has the same version. Use the clone to read source (`legitsocial.py`, `competitorllm.py`, `newssites.py`, `_http.py`). Not committed to our repo (gitignored); re-create it with `git clone https://github.com/capturethenarrative/pypi-capturethenarrative.git src/pypi-capturethenarrative`.
- To check for a newer client: `pip index versions capturethenarrative`. *Updated 2026-10-19:* pinned to **0.5.1**. Its only change from 0.5.0 is that `CompetitorLLM` sends `Accept-Encoding: gzip, deflate`. This avoids `TypeError: process() takes no keyword arguments` on `llm.ask` when an old `brotli` (< 1.2) is installed, because the CDN brotli-compresses replies. If you see that error, run `pip install -r requirements.txt` again. (0.4.0 was the 2025 client.)
- **Everything your bots do is logged and attributed to the team** (rules §6.2). Don't wrap the client in anything that hides which account/bot did what.
- Keep **your own logs** of what each bot posted and why (they help post-event reflection and satisfy source-code handover for finalists, rules §7.5). Put them in `logs/` (gitignored — they may contain team-sensitive content).
- External LLMs for content generation are allowed (rules §5.1) subject to their ToS; keep keys in `.env`.
