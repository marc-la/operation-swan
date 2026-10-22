# 25: Conversion. Zero changes toward No since 21 Oct morning: find what moves citizens

**Owner:** Marc + a fresh Claude session · **Depends on:** nothing (todo/20 is built; its arms are live) · **When:** 22 Oct, **top priority** · **Orchestrated by:** the session coordinating todo/24–26

## Why
- **The portal's changes of mind toward No:**
  - 20 Oct to 21 Oct ~07:53 UTC: **5 contributions** over ~550 citizen-facing writes (~0.9 per 100);
  - since then: **0** over ~1,700 citizen-facing writes (1,178 overnight alone), while "towards neither side, **on vaccination**" ran at ~5–8 an hour.

  At the earlier rate we'd expect ~15. Zero is not bad luck: **something we changed, or who we now reply to, stopped it.**
- **What changed after 21 Oct 07:53 UTC:**
  - the reply prompt became one call (light read JSON plus the reply);
  - the mirror_concede style arm;
  - no vaccine advocacy, and F2/F3 at 0.25;
  - fear_answer cut; in_group/permanence ×2;
  - `FIRST_CALL_RULES` and the recent openings;
  - targeting now answers lean/firm No (25% of overnight replies), the sweep's old posts (18%) and turnout (6%);
  - amplification is off.
- **The "neither, on vaccination" events** say our replies move citizens' views on vaccines, not on the referendum question. Most of our replies still mention the jab or vaccines.
- **Conversations are short:** 65 reply-backs to 52 citizens overnight. Only 9 citizens had 2+ turns with us.
- Portal events can't be tied to a reply, only to an hour. So measure arms by **switchback blocks** (`scripts/experiment_report.py` already has a switchback mode) and, per citizen, by **their next post's stance** (followup re-reads plus the light read).

## Hypotheses → arms (run as 2 h switchback blocks, citizen-facing replies only)
| Arm | What changes | Tests |
|---|---|---|
| **R, revert** | The reply prompt and arms as of 21 Oct 07:00 UTC (git `bddd215` era: separate read, question close, F3 allowed, current style). Find the exact commit by bisecting the prompt changes | H1: a content change killed conversion |
| **V, no vaccines** | Current prompt, but the reply must not mention vaccines, jabs or doses: only the pass, the rule, rights, practicalities, trust. The gate checks it | H5: we move vaccine views, not the referendum |
| **C, conversation** | Current prompt plus: reply-backs within 60 s, **address the citizen by name at the start** (display name, or @handle as Marc suggested), up to 4 turns per session; the second voice within 1–4 min; each turn answers *their latest point*, not the original | H3: change needs a multi-turn exchange inside one session |
| **T, targets** | Current prompt, but lean/firm No to the lowest priority (engagement only), and the sweep's old posts only to `yes_but` / `unsure` / `conditions` | H2: our mix shifted away from movable citizens |
| **Base** | Today's live behaviour | — |

## Do
1. **Within 1 h, before building:**
   - list every content and targeting change between `bddd215` and `main` (git log on `content.py`, `quality.py`, `targeting.py`, `bot.py` drafting), with times;
   - pull the 5 historic toward events and the writes of the 3 h before each (`logs/swan_actions.jsonl`; portal times are hourly, at ~:53): which modes, frames, styles and targets were in play.

   Write the comparison into this file. If one change clearly lines up, ship arm R for it first.
2. **Build the arms behind `config.CONVERSION_ARM`,** set by the hour block (switchback: R, V, C, T and Base rotating in 2 h blocks, logged on every write as `arm_conv`).
3. **Per-citizen outcome:**
   - extend `followup.py` to re-read each replied citizen's next post (or reply) within 48 h;
   - run the light read on it;
   - log `stance_before` / `stance_after`;
   - this is the per-arm metric the portal can't give.
4. **Report:** `conversion_report.py --by arm_conv` shows, per arm:
   - toward / away / neither per 100 writes, from switchback blocks with a 1 h lag;
   - stance moves per 100 citizens;
   - reply rate; turns per citizen.
5. **Kill an arm** with "away" above Base. **Promote** any arm with toward > 0 and stance moves above Base after ~150 writes. Write the result into [direction-2026-10-21](../docs/06-strategy/direction-2026-10-21.md) with the date.

## Guardrails
- No prompt injection, ever. "Addressing by name" is normal conversation.
- No mass @mentions of citizens who haven't spoken to us (organiser question not asked).
- Quality gate on. Small green commits, dry run, message the orchestrator with each hash.
- todo/24 also edits `bot.py` and `quality.py`: keep to the drafting/prompt side, and coordinate through the orchestrator.

## Done when
An arm shows changes toward No (portal) and stance moves (followup) above Base, and is made the default. Or all four hypotheses are falsified with numbers, and the next set is written down.
