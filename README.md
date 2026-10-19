# Capture the Narrative 2026 — team workspace

Team repo for **CTN 2026** (UNSW / DLCL, 19 Oct – 2 Nov 2026). Start with **[docs/README.md](docs/README.md)** — it indexes the full rules, scoring, setting, API reference and team conduct checklist.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in CTN_TEAM_CODE + CTN_SIDE (never commit .env)
python scripts/smoke_test.py  # read-only server check
```

⚠️ Everyone on the team: read [docs/02-rules/team-conduct-checklist.md](docs/02-rules/team-conduct-checklist.md) before running any bot. Never share the team code outside the team.

Claude Code sessions: see [CLAUDE.md](CLAUDE.md).
