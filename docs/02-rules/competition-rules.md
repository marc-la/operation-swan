# CTN 2026 Competition Rules — v1.0.0 (effective 13 Oct 2026)

> Source: capturethenarrative.com/info/competitions/2026/rules/ (captured 2026-10-19). Section numbering is the organisers' own — **cite it when asking questions** (`#questions` on Discord). Wording is preserved; layout is cleaned. Where we've added commentary it is in *italic blockquotes marked "Note"*.
>
> **Authority:** by registering you agree to these rules. Organisers may interpret and enforce at their discretion; where interpretation is needed, theirs prevails (§11.2). This guide is for reference — the website/official channels govern. Rules may be amended; material changes are announced on Discord/platform (§11.1).
>
> Companion docs: [Legit Social platform rules](legit-social-platform-rules.md) · [team conduct checklist](team-conduct-checklist.md). §2 eligibility, §3 registration, §10.2–10.3 and the Real-World Engagement Award (E.1–E.8) are condensed or omitted because they don't affect bot work. See the source page.

---

## 1. Purpose and spirit

1.1 **Purpose.** Capture the Narrative ("CtN") is an educational, research-backed, CTF-style event exploring AI-driven social-media manipulation in a controlled environment.

1.2 **Good faith & spirit.** Act ethically, legally, and in the spirit of fair play. **Do not seek loopholes to gain unfair advantage. If unsure, ask first.**

1.3 **No real-world harm.** You must not harm others, damage systems, or violate laws inside or outside the competition scope.

## 2–3. Eligibility, registration, teams

Australian-university students or staff, 18+, `.edu`/`.edu.au` email, real name and university. Teams of 1–4; team changes need organiser permission. Every member must join the portal and Discord and complete the **pre-competition survey**. Until all members have, the team can't write (`403 not_ready_reasons`).

## 4. Consent, telemetry & ethics

4.1 **Informed consent.** Participation requires consent to data collection (telemetry) and research surveys.
- Study approved by the **UNSW Human Research Ethics Committee (iRECS no. 9499)**.
- Telemetry may include: **posts, prompts, model outputs, API calls, in-platform interactions, scores, and timing data.** Personal identifiers are minimised and handled per ethics protocol.
- Pre- and post-event surveys are part of participation; **incomplete surveys affect prize eligibility** (§7.5).

4.2–4.3 Withdrawal is possible at any time; data is anonymised after the competition.

## 5. Competition conduct

5.1 **In-scope systems.** When attempting competition-based manipulation, you must **only interact with systems, datasets, APIs and social-media spaces explicitly provided by CtN**, *except* that you may use **external AI models for creative content generation** and **external data sources for storing/retrieving information**. You may use personal machines or cloud services to develop and test, as long as you follow these rules and the **terms of service of any third-party services you use**.

### 5.2.1 Examples of allowed actions (non-exhaustive)

- Creating and managing in-competition social media accounts.
- Posting, commenting, liking, sharing and engaging with content within the competition platform.
- Using AI models (e.g. GPT-5, DeepSeek, Gemma) to generate text for posts/comments, so long as usage stays in-scope and **abides by their licences**.
- Using the provided LLM to generate content for the competition.
- Developing scripts or tools to automate interactions within the competition platform.
- Analysing in-competition data to inform strategies.
- **Impersonating public figures or personas within the competition environment**, provided it doesn't violate ethical guidelines or rules.
- **Prompt injection attacks aimed at other competitors' AI agents** within the competition environment.
- Pushing the boundaries of the fictional platform's own rules and conduct policies, as long as it stays within the competition environment.
- **Generating, posting and engaging with content known to be false or misleading**, provided it doesn't violate any other competition rule.
- **Coordinating with other teams** within the competition environment, provided it doesn't violate any other rules.

> **Note — prompt injection:** §5.2.1 permits it against *other competitors' AI agents*. The [scoring guide §7](../03-scoring/scoring-guide.md#7-posts-that-earn-no-points) says injection aimed at **NPC citizens** is **against the competition rules** and such posts are silently dropped from all feeds (repeat attempts may incur extra penalties). Treat NPCs as people to persuade, not AIs to manipulate.

### 5.2.2 Out-of-scope actions — **strictly prohibited**

- Attacking, disrupting or degrading the competition platform or infrastructure.
- Interfering with other teams' progress or data via means **external** to the competition platform.
- **Using real-world social media platforms or accounts to influence the competition environment.**
- **Sharing or leaking competition materials, challenges or solutions outside your team.**
- Attempting to de-anonymise or identify other participants or teams.
- Emailing/messaging other teams **outside the official Discord server** for collaboration/discussion without their consent.
- DDoS; brute-forcing; scanning or exploiting infrastructure not explicitly in scope; account takeovers; token-stealing; MFA bypass; phishing; social engineering; or any other cyberattack that directly harms or disrupts the platform, organisers or other participants.
- Creating or distributing malware, ransomware or destructive payloads.
- **Tampering with scoring, telemetry, rate limits or sandbox boundaries; attempting to disable logging or attribution.**
- Impersonating organisers, judges or other teams for deception or fraud **outside** the competition environment.
- Posting sexual images, videos or links.

5.3 **Edge cases.** If a behaviour feels "technically allowed but obviously against the spirit", **it's prohibited. Ask before acting.**

5.4 **Hate speech and harmful content.** The competition explores manipulation, which may involve provocative or controversial content, but there is a limit — tolerated by (a) the platform and (b) the competition itself. You must not create, share or promote hate speech, harassment, threats, or harmful/illegal material **aimed at other competitors or the organisers**. All content must comply with the ethical guidelines and respect the dignity of all individuals and groups. Prohibited examples:
- Attacking competitors based on race, ethnicity, nationality, religion, caste, disability, sex, gender identity, sexual orientation, serious disease, or immigration/refugee status.
- Slurs, dehumanising comparisons or harmful stereotypes tied to those characteristics.
- Mocking victims of hate crimes, mass violence or tragedies.
- Calling for violence, exclusion or segregation of people based on those characteristics.

5.5 **Reporting violations.** Report witnessed/suspected violations to organisers via the official Discord or designated channels.

5.6 **Keys & secrets.** **Never share competition API keys or credentials beyond your team; rotate compromised keys immediately and notify organisers.** *(Your "team code" is both your API key for the LLM and the registration key — see [environment](../04-technical/environment.md#secrets).)*

5.7 **Professional conduct.** Do not bring CtN, staff, competitors, UNSW or the ICT profession into disrepute.

5.8 **Respectful communication.** Keep Discord and non-competition communications civil and on-topic.

## 6. AI agents & automation

6.1 **Permitted use.** You may use AI agents, bots or automated scripts for content generation, data analysis or social media interactions, provided they comply with all rules and ethical guidelines.

6.2 **AI attribution.** The platform **logs and attributes** actions by AI agents/scripts to the team that deployed them. **You are responsible for all actions your AI agents take**, including rule violations. **Do not obscure or misattribute agent actions or bypass the platform's attribution/logging.**

6.3 **Rate limits and API usage.** Respect rate limits and API usage policies. Excessive or abusive API use may lead to penalties or disqualification. *(Numbers: [api-reference](../04-technical/api-reference.md#rate-limits).)*

6.4 **Prompt/content logging.** Prompts, outputs and decision logs may be collected for research and anti-abuse review.

## 7. Scoring and prizes

7.1 **Scoring.** Points are awarded for:
- **Red Teaming** — attracting citizen attention, engagement, and changing minds.
- **Blue Teaming** — identifying and reporting competitor-controlled accounts.
- **Polling** — your assigned side's success in official polls and the referendum.

→ Details in the [scoring guide](../03-scoring/scoring-guide.md). The scoring guide is a reference; **the official rules prevail in any dispute**, and organisers may adjust scoring during the competition (they'll notify competitors).

7.2 **Leaderboard.** A public leaderboard tracks team scores. Organisers may adjust scores for fairness or error correction.

7.3 **Victory.** The **three highest-scoring teams** at the end become **finalists**. They are invited to present strategies/achievements to a **panel of judges** at the final prizegiving in **Sydney, Australia** (*printed as "31 October 2025", a 2025 leftover; the launch webinar says **December 2026***). Judges then order the three finalists 1st–3rd based on presentations and overall performance.

7.4 **Prizes** (top three teams):
| Place | Prize |
|---|---|
| First | **$5,000 AUD** |
| Second | **$2,500 AUD** |
| Third | **$1,500 AUD** |

All finalist teams also get a **certificate of achievement** and **one night's hotel accommodation in Sydney** on the night of the prizegiving; teams located **outside Sydney** are also offered **economy return flights** to Sydney.

7.5 **Prize eligibility.** To be eligible as a finalist, **all team members** must:
- complete **both** the pre-competition and post-competition surveys;
- **provide a copy of all source code, scripts and tools** used during the competition to the organisers (see §10.1);
- **attend the final prizegiving event in Sydney**.

7.6 **Finalist substitution.** If a finalist can't meet eligibility, the next highest-scoring team may be invited, at organisers' discretion.

7.7 **Score tie-breaking** (in order, plus organiser discretion):
1. Highest number of **unique engagements** (likes, shares, comments) from simulated NPCs.
2. The team that **reached its final score first**.
3. The team with the **fewest rule violations or penalties**.

## 8. Withdrawal & disqualification

8.1 **Withdrawal** any time (see §4.2).
8.2 **Warnings** may be issued for minor issues; repeated issues may escalate.
8.3 **Disqualification** by organisers at any time for rule breaches. **Decisions are final and not subject to appeal.** Disqualified individuals may be barred from future events.

> **Note:** don't count on getting warnings before disqualification. Organisers monitor 24/7 and delete risky posts immediately.

## 9. Vulnerability disclosure

9.1 **Report immediately.** If you find a vulnerability in CtN infrastructure, **do not exploit it** — report via the designated channel. Good-faith reporting is never penalised.
9.2 **No exploitation** for competitive advantage or disruption.

## 10. Intellectual property & media

10.1 **Your content.** You retain rights to original content you create; you grant organisers a worldwide, royalty-free licence to use competition artefacts (posts, prompts, outputs, screenshots, recordings) for education, research and promotion, with credit where feasible. **Finalists who provide source code further grant a non-exclusive licence** for organisers to use, modify and share it for **non-commercial research and educational purposes**.

10.4 **Publishing your bots.** You *may* publish your team's agents/scripts/tools (e.g. GitHub) if you comply with laws, regulations and ethics, include **proper disclaimers on usage** given what the bots can do in the competition platform, and accept responsibility for consequences. Organisers appreciate a link to published code.

> **Note — vs §5.2.2 "leaking":** publishing *your own bot code* after the event is explicitly allowed (§10.4). Don't publish competition **materials/challenges/solutions** during the event, and **never** commit team codes/credentials.

## 11. Changes & interpretation

11.1 **Updates.** Rules may be amended; material changes announced on Discord and/or the platform.
11.2 **Authority.** Organisers' interpretation prevails.

## 12. Contact & questions

12.1 **Questions & approvals:** use **`#questions`** on Discord. For confidential ethics concerns, contact the designated ethics liaison: **rahat.masood@unsw.edu.au**.
