# CLAUDE.md — Capture the Narrative 2026 (team repo)

## What this project is
We are a team in **Capture the Narrative (CTN) 2026** (UNSW / Digital Lies & Cyber Literacy Foundation): build AI bots that influence **Legit Social**, a simulated social network, to win a fictional **referendum in Kingstonia (2 Nov 2026)** on requiring H2D2 "Dolphin Flu" vaccination proof for public spaces. Competition window: **19 Oct 6pm → 2 Nov 2026 (Sydney time)**. **Our team: "Operation Swan" — assigned side: VOTE NO** (keep public access open; "Protect choice. Keep Kingstonia open."; lead org KITB / Marina Castillo — see `docs/01-competition/setting.md`). Team of 4 (UWA, Perth), account allowance **200 total / 50 active at once**. The side is also in `.env` as `CTN_SIDE`. The portal has a Vote No "briefing" we haven't captured in `docs/` yet. Team members are in Perth (AWST, UTC+8): competition days roll over at midnight **Sydney** = **9pm Perth**, and the 6pm Sydney launch was 3pm Perth. It is an authorised educational/research event; everything we do is logged and attributed to our team.

## Read these first (in `docs/`)
- `docs/README.md` — index of the whole knowledge base
- `docs/00-quick-reference.md` — dates, limits, scoring, hard rules on one page
- `docs/02-rules/team-conduct-checklist.md` — what's allowed/forbidden
- `docs/03-scoring/scoring-guide.md` — exact scoring maths (cheatsheet alongside)
- `docs/04-technical/api-reference.md` — the `capturethenarrative` client (Legit Social, news sites, LLM), errors, rate limits
- `docs/01-competition/setting.md` — world facts to keep bot content consistent
- `docs/05-reference/discrepancies-and-open-questions.md` — known doc inconsistencies + organiser answers log

Official rules/scoring prevail over our docs. If the live site or Discord disagrees with `docs/`, trust the live source and update the doc (with a date).

## Hard guardrails — do not violate when writing or running code
1. **Secrets:** never print, log, commit or embed the **team code** (it is both registration key and LLM API key), bot passwords or tokens. Read from `.env` / env vars (`CTN_TEAM_CODE`, `CTN_SIDE`). `.env`, `secrets/`, `logs/` are gitignored — keep it that way. If leaked: regenerate on the portal and tell organisers.
2. **Scope:** only interact with CTN-provided systems (`social.legitreal.com`, `sites.legitreal.com`, `llm.legitreal.com`). External LLMs are allowed **only for generating content**, external storage only for storing/retrieving data. **Never** use real-world social media/accounts to influence the game.
3. **Don't touch the guard rails:** no bypassing/obscuring rate limits, logging, attribution, scoring or telemetry; no scanning/probing/exploiting infra. If you find a vulnerability, **stop and report it** (rules §9).
4. **Rate limits are team-wide, not per account.** Posts+replies+reposts = **3/min total**; feed reads 10/min; LLM 3/min, 1 concurrent. Pace from `client.rate_limit` / `on_rate_limit`, never hard-code; back off on 429; no retry loops that hammer. Failed requests burn a smaller budget — don't spam known-bad calls.
5. **Content limits:** no hate speech/harassment/threats toward competitors or organisers, no sexual content, no doxxing/real personal data, no false voting logistics. **No prompt-injection text aimed at NPC citizens** (posts silently dropped; may be penalised). In-game falsehood, personas and persuasion are allowed.
6. **Be honest in the tooling:** every bot/account must be attributable to a team member in our own records; don't write code that disguises which bot did what.
7. **Ask before anything ambiguous** — the rules say "if it's technically allowed but against the spirit, it's prohibited; ask first". Draft the question for `#questions` on Discord rather than guessing.
8. **Don't create accounts, post, like, follow or report on Legit Social unless the user explicitly asks** — those are real, scored, logged actions with irreversible effects (passwords can't be changed; hidden posts/suspensions are permanent). Read-only calls (feeds, news, `scripts/smoke_test.py`) are fine in moderation.

## Environment & commands
```bash
source .venv/bin/activate          # Python 3.13, capturethenarrative==0.5.0 (+ openai)
pip install -r requirements.txt    # reproduce env
python scripts/smoke_test.py       # read-only: feed lock, trending posts, news headlines
```
- Package source for reference: `src/pypi-capturethenarrative/src/capturethenarrative/` (`legitsocial.py`, `competitorllm.py`, `newssites.py`, `_http.py`). It is a separate git clone — don't edit it; we install the PyPI release.
- Convention: `import capturethenarrative as ctn`. Classes: `ctn.LegitSocial`, `ctn.Account`, `ctn.NewsSites`, `ctn.CompetitorLLM`. Reading feeds needs no account; writes need `register`/`login` (needs team code; competition must be open).
- Provided LLM is `qwen2.5-3b-instruct` only (weak; verify its output before posting — it may return the wrong format or pick posts it wasn't shown).
- The repo is not yet under git. If it becomes a repo, commit `.gitignore` first.

## Key facts to keep in mind
- Score ≈ persuasion >> volume: mind-change toward our side = 160 (+share of 80), away = −80; views capped at 500/day; unfollow −20. Red multiplier ×1 → ×2 from 26 Oct → ×4 from 1 Nov (derived; verify). Poll awards (21/25/29 Oct) need team score ≥1 / ≥2,500 / ≥2,500. Referendum: 5,000 + share of 50,000 for the winning side only.
- Citizens are deliberately hard to persuade; echoing what they already believe earns engagement but little persuasion; content that causes movement *away* from our side is penalised even if it argued for us.
- Blue track: reporting competitor bots as `inauthentic` (detail text required); moderator is wrong ~25% of the time; a wrong "genuine" ruling suspends our reporting for 6 h. 3 hidden posts = account suspended.
- Finalists must hand over **all source code** and attend the Sydney prizegiving; keep tidy, attributable code and our own logs.

## Working conventions
- Keep docs factual and dated; put organiser rulings in the answers log. Don't duplicate content across docs — link.
- Keep bot code in `src/` (own folder per bot/tool, not inside `src/pypi-capturethenarrative/`); scripts in `scripts/`. Add tests/dry-run modes for anything that writes to the platform, with writes off by default.
- When unsure whether a rule applies, quote the section number (e.g. "rules §5.2.2") and say what you checked.
