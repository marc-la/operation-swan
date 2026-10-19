# Scoring ROI: "gaming the game" inside the rules

> Analysis 2026-10-19, derived from the [scoring guide](../03-scoring/scoring-guide.md) and [rules](../02-rules/competition-rules.md). Numbers are base points before the Red multiplier unless stated. Organisers can change scoring: re-check Discord.

## 1. Where the points actually are

| Source | Size | Capped? | Comment |
|---|---|---|---|
| Views | 1 each | **500/day** (max 500 ×1, 1,000 ×2, 2,000 ×4) | Saturates fast: **don't optimise for views** |
| Likes / reposts / replies / follows | 5 / 10 / 15 / 20 | No | Replies (15) and follows (20) are the best engagement events |
| **Change of mind toward No** | **160** (+ share of 80) | No | ×4 at the end = **640 per citizen** |
| Change away from No | −80 (−40 pool share) | No | Penalty is **half** the reward (see §4) |
| Polls 1–3 | 1,000 each if No leads (500 if ≤52–48) | Needs score ≥1 / ≥2,500 / ≥2,500 at count time | **Cheap to qualify, expensive to miss** |
| Referendum | **5,000 base + share of 50,000** | No side wins → only the winning side's teams get anything | **The biggest single prize**, counted by persuasion events (change = 1, contribution = 0.5/N) |
| Blue reports | 25 first / 5 later / 15 account suspension | Diminishing per target team per day; 6 h ban on a "genuine" ruling | ×1 always, so worth relatively more early |

**Exchange rate:** 1 change of mind = 32 likes = 8 follows = a third of a day's views (at ×1).

## 2. Milestones (don't miss these)

| When (Sydney / Perth) | Need | Prize at stake |
|---|---|---|
| **Before Poll 1 is counted, 21 Oct** (be safe: by 20 Oct 9pm Perth) | Score **≥ 1** | 1,000 (or 500) |
| **Before Poll 2, 25 Oct** | Score **≥ 2,500** | 1,000 + also locks in referendum base eligibility |
| Poll 3, 29 Oct | Stay ≥ 2,500 | 1,000 |
| 2 Nov count | ≥ 2,500 **or** ≥1 qualifying persuasion | 5,000 base + pool share |

2,500 by 25 Oct ≈ 6 days × ~420 points/day. That is achievable from views (500/day) + engagement alone, even before we persuade anyone.

## 3. The write budget is the scarce resource

- Posts + replies + reposts: **3/min for the whole team** = 180/h = 4,320/day. Everything that writes text competes for it.
- Likes, follows and views have their **own** 30/min budgets: amplification and relationship-building don't cost post slots.
- Failed writes burn a smaller separate budget (20): validate before sending.
- **Implication:** each text slot should go where the expected persuasion is highest. Suggested starting split, to tune: **~50% targeted replies** (to doubting citizens and under trending Yes posts), **~35% original persona posts**, **~15% quote-reposts**. Tune by measured return.

## 4. Persuasion maths and the backfire question

Expected value of a post (one citizen) ≈ 160·P(moves toward) − 80·P(moves away) + engagement.

- The per-citizen penalty is half the reward, so **slightly polarising content is not automatically negative in points**.
- **But** every citizen pushed toward Yes also lowers P(No wins), and the referendum is worth 5,000 + a share of 50,000 to every No team. **Net effect: backfire is more expensive than the −80 suggests.** Prefer the low-variance frames (F1–F3, F10).
- **Echo has low value:** "repeating what a citizen already believes … unlikely to get persuasion points". Our own base gives engagement and follows (useful for reach), not persuasion.
- **Contributions stack.** When a citizen changes their mind, every post of ours that addressed that view in the session gets a share of 80. So **2–3 of our personas hitting the same doubt in one session** (complex contagion) earns more and persuades better than one. *Limit (scoring §2, clarified 2026-10-19):* once a citizen has changed that view in the session, they're much harder to move on it again before signing out. Stacking pays **before** the change, not after. Don't keep sending the same frame to a citizen who has just shifted.

## 5. Timing: build early, harvest late

- The multiplier is fixed **when the score is recorded** (citizen session end), not when we post. Posts that keep circulating into 1–2 Nov earn ×4.
- **Followers are capital.** A follow is +20 now, and Home gives followed accounts prominence. A follower base built in week 1 is our distribution channel at ×4. Protect it: on-brand content only (unfollow −20 at the multiplier then in force).
- LeDuc drift helps No late, and that's when ×4 applies. **Keep the best-performing frames for 30 Oct–2 Nov** and scale replies then.
- In-world campaign silence from 00:00 1 Nov restricts "mass campaign messaging" but **not ordinary people posting their views**. Persona voices fit; KITB-branded slogans may not. Ask first.
- Post while rivals are quiet (2025 lesson). Perth is 3 h behind Sydney; NPC activity hours are unknown. Log hourly NPC activity and find out.

## 6. Blue track: cheap points and a strategic weapon

- 3 reports/min have their own budget. First reporter gets 25, later reporters 5. Five teams reporting = temporary hide.
- Moderator is wrong ~25% of the time. A wrong "genuine" ruling = **6 h reporting ban**. Report only high-confidence cases: leaked LLM preambles, duplicated text across accounts, inhuman cadence, wrong-context replies.
- **Strategic value:** each upheld report on a **trending Yes-side bot post** permanently hides it. That helps the referendum, not just Blue points. Spread reports across target teams (diminishing returns per team per day).
- Don't report genuine citizens. Bad-faith reporting is a violation (LS.6.5).
- **Report posts on evidence, not by team.** Rules §5.2.2 prohibit *attempting to identify other participants or teams*, so we don't try to work out which accounts belong to a leading team in order to target them. Prioritising by **content** (Yes-side, clearly automated) is fine.
- **Distinguishing NPCs from competitor bots:** competitor accounts can only exist from 19 Oct 6pm Sydney. `get_account` returns `created_at` (except for private accounts), so pre-launch accounts are likely NPCs or organiser personas. Verify this heuristic before relying on it.
- **Defence:** 3 permanently hidden posts = account suspended; ≥100 actions + 1 hidden post = account-report suspension. Keep amplifier accounts (lots of likes) separate from voice accounts, and keep text clean.

## Legitimate edges (confirm the asterisked ones)

| Edge | Status |
|---|---|
| Hit the poll thresholds early; qualify for everything | ✅ |
| Spend post slots on replies to doubting citizens (persuasion) rather than broadcast | ✅ |
| Build followers in week 1 for the ×4 window | ✅ |
| Multiple personas per frame per session (contribution stacking) | ✅ |
| External LLM for content generation | ✅ rules §5.1 |
| Coordinate with **other No teams** via official Discord (shared frames, cross-amplification, splitting segments). All No teams gain from a No win | ✅ §5.2.1 (only via official Discord/in-game) |
| Our accounts liking and reposting our own posts to seed Trending* | ⚠️ Allowed by competition rules as far as we can tell, but breaches the in-game LS.5.3 ("reaction farming") → report/hide risk. **Ask first** |
| External LLM for *analysis* (classifying stance/frames)* | ⚠️ §6.1 allows AI for data analysis; §5.1 names external AI "for creative content generation". **Ask first** |
| Scraping our own portal activity log automatically* | ⚠️ Portal is a CtN system, but automation is unstated. **Ask first**; manual hourly entry until then |
| GIF/image links* | ⚠️ Fine as decoration; NPCs probably read text only. Never put messages *for the model* in them |

## Red lines

These are never strategy, however they're framed. Rules: §5.2.2, §6.2–6.3, §9, scoring §7.

- Prompt injection at NPCs in **any** form: instructions, role-play setups, chat markup, field names, hidden/zero-width text, **messages encoded in images or GIFs "only an LLM can read"**. Silently dropped; repeat attempts are penalised.
- Getting around rate limits: multiple team codes, extra IPs, parallel uncoordinated scripts, retry storms.
- Exceeding the account cap; hiding which bot did what; tampering with logging, scoring or telemetry.
- Probing or exploiting platform bugs. If we find one: **stop and report** (§9).
- False voting logistics (where/when/who can vote).
- Hate speech, harassment, doxxing, sexual content; real-world social media to influence the game.
