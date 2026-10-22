# Stealth: why our voices get hidden, and the switches (2026-10-22)

What came out of todo/27 and todo/31 (both done and removed). Code: `src/swan_bot/quality.py` (phrase budgets), `src/swan_bot/stealth.py` (a human day per voice), config `# ---- todo/27 fingerprint ----` and `# ---- todo/31 stealth ----`.

## The audit (22 Oct ~10:15 UTC, `logs/alerts.log` + `logs/swan_actions.jsonl`)
- **33 posts hidden on 16 voices; 13 of 61 accounts banned** (portal). Hides land in batches of 3–6 in the same minute: one rival team's batch of reports being ruled.
- **Text:** "I'm voting No" was in 57% of 1,886 writes in 24 h. 17 of 31 hidden posts used one skeleton (`F14_no_yes_but`): echo their "but" → "no end date / review / venue list until after" → "a Yes binds us" → the vote, or "Do you know anyone who's moved from Yes to No?".
- **Behaviour:** each voice wrote 100–200 times a day and was active 18–24 of 24 hours. 294 of 730 citizens got two of our voices within 60 min (second voices), the pattern our own Blue reports as a reply ring.

Follow-up audit of the suspensions on 22 Oct (46 hidden posts, 14 suspended voices): [hidden-post-audit-2026-10-23.md](hidden-post-audit-2026-10-23.md).

## What is live
| Change | Commit | Effect |
|---|---|---|
| No vote statement at the end of replies; worn phrases avoided | 5c07934, b029f65 | "voting no" 57% → 5% of writes |
| Phrase budgets on drafts (vote ≤ 15%, each template phrase ≤ 10% of our last 100) | 240c349 | — |
| Cross-citizen near-duplicate back to strict (0.4 → 0.3) | 01e1d19 | — |
| Converted boosters draft in another card's style, sleep on their own clock | f7296e9 | — |
| Hides per hour after the wording fix | — | 6 (04 UTC) → 4, 2, 1, 1 |

## The behaviour switches: OFF by team decision
**87c6e8e (Hoang Minh Nguyen for Marc, 22 Oct 11:50 UTC): throughput over stealth.** Writes had fallen under 2/min with most voices retired at 2 hidden posts. All the todo/31 behaviour rules are off, `SECOND_VOICE` is back on, and `--per-min` is 2.9. Each rule has its own switch, and `.env` overrides it without a commit (6995ad5), e.g.:

```
SWAN_VOICE_DAY_CAP=1  SWAN_VOICE_WRITES_PER_DAY=80   # a daily budget per voice
SWAN_VOICE_SLEEP=1                                   # a 7–8 h sleep window per voice (Sydney clock)
SWAN_ONE_VOICE_PER_CITIZEN=1                         # no second voice on a citizen within 24 h
```
Then `sudo systemctl restart swan-bot`. The cost in writes/day of each rule is in `stealth.py`'s docstring. **When hides climb again** (alerts.log "hidden by the moderator" > 2/h), bring the rules back one at a time, cheapest first: one voice per citizen, then the sleep window, then the daily budget.

## Still open (content, the todo/25 session)
Retire the F14 skeleton, rotate facts so no single fact is in more than ~8% of writes ("Central's 40 empty nursing posts" was 25%), drop the stock closing question, give each voice its own style, and a lab stealth score (overlap with `data/lab/hidden_corpus.jsonl`). None of these cost volume.
