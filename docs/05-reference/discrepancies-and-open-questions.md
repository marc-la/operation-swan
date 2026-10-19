# Discrepancies & Open Questions

> Ask the organisers in `#questions` (quote the section number) and record answers in the **Answers** table so every session has the ruling.

## A. Conflicts between sources

| # | Conflict | Working assumption |
|---|---|---|
| 1 | Launch webinar (15:00, 21:00): a successful report gets score, "that post will be deleted" and you can "kill that bot". Scoring guide §3: the ruling comes 1.5–24 h later and is wrong ~25% of the time. Suspension takes 3 permanently hidden posts, or an account ruling once the account has ≥1 hidden post and ≥100 actions | **The scoring guide governs.** The talk was a simplification |
| 2 | Rules §5.2.1 **allows** prompt injection against *other competitors' AI agents*. Scoring §7 says injection against **NPCs** breaks the rules, and such posts are silently dropped | Where is the line between persuasive text and text that manipulates an AI? Wording that resembles instructions or role-play may be filtered. Are injections against competitor bots logged or penalised? |
| 3 | Legit Social LS.3.1 says "one person, one account", yet each team runs many accounts | Presumably in-game flavour (inauthenticity, which moderation and Blue teams hunt), not a competition-rules breach. Confirm |
| 4 | §5.2.1 allows "coordinating with other teams". §5.2.2 bans messaging other teams outside Discord without consent | Coordinate only through the official Discord or in-game |

## B. Open questions to put to organisers

1. Does the **campaign-day multiplier** timeline match our derivation (×2 from 26 Oct, ×4 from 1 Nov)?
2. Is **editing a post** to re-screen it risk-free, i.e. no penalty for having tripped the injection screen?
3. Are **verified accounts** organiser-controlled personas (public figures, journalists)? Can a team account get verified?
4. Is it within the rules for our own accounts to **like or repost our own posts** (in-game LS.5.3 calls this "reaction farming")? Is the only consequence in-game (reports, hides)? See [scoring-roi](../06-strategy/scoring-roi.md#legitimate-edges-confirm-the-asterisked-ones).
5. May we use an **external LLM for analysis** (classifying the stance and topics of posts we read), or only for content generation (§5.1 vs §6.1)?
6. May we **automate reading our own portal activity log**, or should it be read manually?
7. Does the in-world **campaign silence** (00:00 1 Nov: paid ads, mass campaign messaging and rallies restricted) change how NPCs, the moderator or scoring treat campaign-style posts during the ×4 days?
8. Do NPCs perceive **GIF/image links** or the `embed` field, or only text?
9. What counts as "unique engagements" for the tie-break (§7.7)?

## Answers

| Date | Question | Answer | Source |
|---|---|---|---|
| 2026-10-19 | Account caps | **200 total, 50 alive at once** (matches the portal). Deleting an account frees an active slot, never a total slot | Launch webinar 21:13; client README |
| 2026-10-19 | Prizegiving date | **December 2026**, Sydney. Exact date TBC. The rules text "31 October 2025" is a 2025 leftover | Launch webinar slide 6 |
| 2026-10-19 | Client update | 0.5.1 fixes "rare issues with the LLM wrapper on certain installations". Organisers: no need to update if you get no errors. We pin 0.5.1 anyway ([environment](../04-technical/environment.md#notes)) | Discord #announcements, hammond, 19 Oct 18:53 |
