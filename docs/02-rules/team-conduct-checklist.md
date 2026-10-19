# Team Conduct Checklist — read this before you run a bot

> A one-page digest of the [competition rules](competition-rules.md), [ethics](ethics.md) and [Legit Social rules](legit-social-platform-rules.md) for **everyone on the team**. It is a summary, not a replacement — the numbered rules govern. **Unsure? Ask in `#questions` on Discord *before* acting** (§1.2, §5.3).
>
> Consequences: warnings → disqualification (final, no appeal, §8.3), possible ban from future events. **You are responsible for everything your bots do (§6.2).**

## ✅ Allowed (in the competition environment only)

- Create and manage in-game accounts (up to your team's cap) and automate them with scripts/bots.
- Post, reply, repost, like, follow, tag, report — via the provided API.
- Use the provided LLM **and** external AI models (GPT, Claude, DeepSeek, Gemma…) to *generate content*, within their licences/ToS.
- Use external services to *store/retrieve* data (databases, logs).
- Analyse in-competition data; read the in-game newspapers.
- Persona play, including **impersonating public figures/personas inside the game**, and **posting content known to be false or misleading** (it's a disinformation simulation) — provided no other rule is broken.
- **Coordinate with other teams** *inside* the competition environment / official Discord.
- Prompt-inject **other competitors' agents** (§5.2.1).
- Push the *fictional platform's* own conduct rules (expect in-game moderation consequences).
- Publish your bots **after** the event with disclaimers (§10.4).

## ⛔ Never

| Don't | Rule |
|---|---|
| Touch anything outside CtN-provided systems (except external AI for content, external storage) | §5.1 |
| Use **real-world** social media/accounts to influence the competition | §5.2.2 |
| Share/leak competition materials, challenges or solutions **outside your team** | §5.2.2 |
| Share the **team code / API keys / credentials** beyond your team (rotate + notify organisers if leaked) | §5.6 |
| Attack/disrupt/degrade the platform; DDoS, brute-force, scan, exploit, account takeover, phishing, social engineering, malware | §5.2.2 |
| **Tamper with scoring, telemetry, rate limits, sandbox boundaries; hide or misattribute your bots' actions; bypass logging** | §5.2.2, §6.2 |
| Exceed/circumvent rate limits or spam the API | §6.3, LS.5.2 |
| Prompt-inject the **NPC citizens** (posts are silently dropped; repeats may be penalised) | Scoring §7 |
| Post **sexual** images/videos/links | §5.2.2, LS.2.5 |
| Hate speech, harassment, threats aimed at competitors/organisers; slurs, dehumanising comparisons, mocking tragedy victims, calls for exclusion/violence | §5.4 |
| Doxx, or try to identify/de-anonymise other participants/teams | §5.2.2, LS.4.2 |
| Message other teams (email/DM) **outside the official Discord** without consent | §5.2.2 |
| Impersonate organisers/judges/other teams for deception **outside** the game | §5.2.2 |
| Use false civic-process logistics (fake voting times/places/eligibility) — moderator may label/remove | LS.8.2 |
| Exploit a platform vulnerability — **report it, don't use it** | §9 |
| Use a loophole that's "technically allowed but obviously against the spirit" | §1.2, §5.3 |
| Bring CtN, UNSW, staff, competitors or the ICT profession into disrepute | §5.7 |
| Bad-faith/brigade reporting (reports are for genuinely suspected competitor bots) | LS.6.5 |

## 📋 Team obligations (for the prize **and** for staying in the game)

- Every member: real name + university, `.edu`/`.edu.au` email, 18+ (§2–3).
- Every member completes the **pre-** and **post-competition surveys** (finalist eligibility, §7.5).
- **Keep your source code** — finalists must hand over *all* source, scripts and tools (§7.5, §10.1).
- Finalists must **attend the Sydney prizegiving** (§7.5).
- Your prompts, outputs, API calls and decisions are **logged** for research (§4.1, §6.4).

## 🧭 Our operating principles (project policy, derived from the above)

1. **One human accountable per bot** — every bot account is tagged to a team member in our own records.
2. **Pace from `rate_limit`, never hard-code** limits; back off on `429`. No retry storms.
3. **No secrets in git** — team code, bot passwords and tokens live in `.env` / a gitignored `secrets/` folder.
4. **Don't deceive about being automated outside the game.** In-game deception is fine; the logging/attribution layer is untouchable.
5. **Keep content inside the game.** Never post real-world personal data, real people's private info, or anything that would be harmful outside the sim.
6. **Persuade citizens, don't hack them.** Write for people, not for an LLM's weaknesses.
7. **When in doubt → `#questions`**, and save the answer in `docs/05-reference/` so the team has it.
