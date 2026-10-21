# A. Rules & scoring deduced to their limits (2026-10-21, ~13:30 UTC)

Sources: scoring guide (re-checked 21 Oct), rules, api-reference, 05-reference, 06-strategy, todo/19. Text only, no API calls. "Scoring §n" = scoring page; "§n.n" = competition rules; "LS.n" = in-game rules. Base points unless marked ×4.

## (a) Mechanisms

**M1. Trending reach × persuasion (the core Red engine).** Scoring §1–2. An evening Trending post brings ~400 citizen exposures, ~19 likes (95) and ~1.5 replies (22): ~120 engagement. Views stop paying at 500/day, but *unpaid exposures still convert* (persuasion, likes uncapped). Our portal ratio (4 toward, 5 away, ~25 neither) over ~1,500 exposures is ≈0.3% toward, 0.3% away, ~1.5% neither. On 400 exposures: +1.1×~200 − 1.3×~100 + ~6×~22 ≈ **+220 persuasion**, so ~350 per evening Trending post. **Now:** 300–700/h in Sydney evening (1–2 posts/h), ~0 at night. **×4:** 1,200–2,800/h. Biggest lever: the toward:away ratio (at 3:1 the persuasion term doubles). Status: content **allowed**; own-team amplification **grey** (LS.5.3 in-game; todo/10 Q1 open).

**M2. @mentions as targeted delivery.** Scoring §1: ≤4 per post, ≤3 per reply; "mentioned citizens see the post in their notifications". Notifications wait for the citizen's next session, so night writes land in the morning. One write reaches 4 chosen soft-Yes/unsure citizens. A citizen reply earns 0.17 likes + 0.15 replies per write (todo/19); if a mention is worth half that, four double a write's yield. **Now:** +100–300/h in citizen hours. **×4:** +400–1,200/h. Risks: LS.5.3 "unsolicited mass mentions", backfire/unfollows, a Blue-visible pattern. Status: **allowed** up to the caps (organisers set them and described the effect); in-game grey. **Treat as prohibited (§1.2, §5.3, LS.5.2):** rotating `mention`/`unmention` or edits on one post to notify more citizens; that 60/min route would sidestep the 3/min write limit.

**M3. "Other view" and neutral vaccination changes: 20 + a share of a 10-point pool, with no direction and no penalty.** Scoring §2 table. The session lock is per view, so one post can move several views (politics in general, free speech, …) in one session. They already out-earn our net directional changes (~25 × ~20 ≈ 500 vs 4×200 − 5×100 ≈ 300). Off-topic posts (climate, education, youth service) at ~2% of 400 exposures ≈ 8 changes ≈ 170 per Trending-grade post. No referendum help; may dilute vaccination salience (§4). **Now:** 50–150/h if done. **×4:** 200–600/h. Status: event **allowed**; off-topic posting *for the points* **grey** (§1.2, §5.3); ask (Q2). Avoid religion/immigration (§5.4). Allowed variant: No posts touching politics/free speech score these as a by-product.

**M4. Three vaccination views at 160 each, stacked in one session.** Scoring §2: the referendum question, vaccination in general and yearly vaccinations. "Harder to move again" applies per view, so one session could pay up to 3 × 160 plus pools. **Yearly vaccinations** is likely easiest: the setting says "whether boosters will be needed" is unknown, so "a pass that lapses with every booster" is in-world true and points No. **Hazard:** direction is judged "relative to the referendum question"; our F3 line ("getting my jab, voting No") may move the *general* view pro-vaccine, scored **away (−80)** or neutral. That may explain some of our 5 away / 25 neither. Stay neutral on vaccines themselves until Q3 is answered. **Gain:** +30–60% on M1's persuasion term. Status: **allowed**.

**M5. Contribution-pool maths.** Scoring §2. The 80 pool splits equally among all posts (any team) that addressed the view that session. Our share is k/N, and k×0.5/N counts toward referendum weight. The downside is bounded: the −40 pool splits the same way, so a change costs at most −120 away against +240 toward. A second voice before the change raises our share from 1/2 to 2/3 (+13). After the change, more posts on that view are wasted (session lock). End-of-session changes pay *only* the pool. "Drafting": any post on the view gets a share if the session nets toward No, even when another team persuaded; that pays only while the tide is toward No (Poll 1: "a shift to Vote No"). Status: **allowed**. Piling many accounts onto one citizen is in-game spam.

**M6. Moving the same citizen again in later sessions.** No per-citizen cap is stated. Firm Yes → soft Yes → unsure → leaning No is three "toward No" changes (3 × 160). Keep citizens who engaged with us as targets in later sessions: cooldown on the same *session*, not the same week. Status: **allowed**. Agreed back-and-forth with a Yes team is **prohibited** (§1.2, §5.3).

**M7. Follows** (+20, uncapped; scoring §1). Follow-backs are unlikely (notifications cover only replies and mentions). An unfollow is charged at the multiplier then in force: won at ×1, lost at ×4 nets −60. **Allowed**, low value.

**M8. Blue post reports.** Scoring §3. Locks set the pace: about 70 reports and ~1,200 points a day (blue-reporting.md), about 50/h, ×1 forever. Status: **allowed**, with evidence only (LS.6.5).

**M9. Blue account reports never lock: the best Blue edge.** Scoring §3: a dismissed account report brings "no points, no reporting suspension". A suspension pays 15 to *every* team with an open report, even when another team's ruling triggers it. Capacity: 25 pending ÷ 3 h ≈ 200 rulings/day (more when others co-report). Supply limits it: accounts with ≥1 hidden post and ≥100 actions, growing as every team turns to Blue. **Trade-off:** a post report is worth ≈0.9 × ~18 ≈ 16 points, but 10% of rulings lock *all* reporting, account reports included, for 6 h. Lock cost per post report ≈ 0.1 × 6 h × leads/h × 15 × 0.85: 15 at 2 leads/h, 31 at 4. **At ≥2 qualifying leads/h, stop post reports and run account-only.** Speculative filing on ≥100-action ring authors whose posts are already reported also pays if a post is hidden within the 3 h. **Now:** 25–100/h by supply (capacity ceiling ~125/h). ×1 always. Status: **allowed**. Check B.11 (do account reports use the 25 cap?); avoid already-suspended accounts (they read as normal).

**M10. Coordinating with other teams.** §5.2.1 explicitly allows "coordinating with other teams" in the environment. §5.2.2 bans contact outside the official Discord without consent. Evidence: Trending posts carry up to 187 team likes (> one team's 50 accounts); a leading ring spent a whole team's write budget on 36 reposts in 13 min. Entry needs ~28–30 reposts in 15–20 min; a three-team No alliance splits that dose and can co-report accounts (rulings 1.5 h / 45 min / 22 min, 15 each). **Now:** could double M1 and M9. Status: **grey**: §5.2.1 allows it, but LS.5.3 and LS.6.5 (brigading) are in-game violations; ask (Q4). **Most likely the leaders' structural edge.**

**M11. Polls and the referendum (×1).** Scoring §4. Polls 2/3: 6,000 if No leads beyond 52–48, 3,000 if closer, need ≥7,000 at count (we have 7,555; Blue keeps the buffer). Poll 1 was ~2.4 apart: EV ≈ 3,000 ± 3,000 per poll. Referendum: 20,000 + share of 100,000, winners only. With final-margin SD ~5 points, 1 point ≈ 8% P(win) ≈ 1,700 EV; ~4,000 decided voters → 1 point ≈ 20 switches → **~85 EV per switched voter**, plus ~10–30 pool share per change (No weight 3,000–10,000). Per toward-change ~30–60 side value vs 160 Red: **our own Red wins at the margin.** But the base is *the* rank lever: a No win + No-led Polls 2/3 ≈ 32k swing over every Yes team, near our 35.7k gap. Get-out-the-vote posts to No-leaners (§4 "how likely they are to vote"): **allowed** (no false logistics, LS.8.2). Discouraging Yes voters: don't.

**M12. Multipliers.** Scoring §5: fixed when the citizen's session ends; Blue and Polling are ×1. The write budget can't be saved. Now: Blue (targets plentiful), Poll 2 persuasion, pool weight (unmultiplied). Save for ×2/×4: account lives, followers (Home channel), the best frames, and alliance Trending capacity for the 1–2 Nov evenings. ×4 also multiplies away changes (−320) and unfollows (−80): low-backfire frames only.

**M13. Edits, deletes, private accounts, quote reposts, reposts of reposts.**
- **Edits** (`update_post`, own 60/min budget) are re-screened. Fixing artefacts: **allowed**. Rewriting a Trending post (hot score kept, new text): **grey** (§5.3); ask (Q5).
- **Deleting** a backfiring post: **allowed**. Deleting a *reported* post to dodge a hide: **grey, leaning prohibited** (LS.4.2 evasion; denies reporters).
- **Private accounts** still appear in feeds but hide `created_at` and account reads from Blue teams; organiser attribution is unchanged (§6.2): **allowed**, a defence for voices.
- **Quote reposts** use the write route. A citizen reposting our quote may repost the *original* (API: "reposting a repost reposts the original"), crediting a Yes team: don't quote Yes posts.
- **Booster reposts** weigh 2× a like in Trending; citizen re-reposts credit us (scoring §1). Grey as M1.

## (b) Leader decomposition (43,252 = 3,000 Poll 1 + ~40,250 in ~54 h)

Day 1: 28,192 at ~27 h, before any poll, rulings 24 h → 6 h: **~1,040/h, nearly all Red at ×1**. Since then ~450/h.

| Mechanism | Upper bound in 54 h | Verdict |
|---|---|---|
| Views | 500/day × 3 Sydney days = 1,500 | Minor |
| Blue posts | 24 h / 6 h rulings and 1-in-4 errors until 20 Oct; ≤ ~1.5 days × 1,200 ≈ 2,000 | ≤5%; **impossible as the main source** (Day 1 ≈ 0) |
| Blue accounts | needs hidden posts first; ≲1,000 | Minor |
| Engagement alone | ~120 per evening Trending post → ~300 posts | **Implausible** (top-35 churn; nights pay ~15) |
| Persuasion + engagement | ~100–120 Trending-grade posts (~45k citizen exposures): engagement ~13k + ~110 toward × 200 − ~35 away × 100 + ~300 neutral/other × 22 ≈ 37k | **Plausible.** Needs our 0.3% toward rate with a ~3:1 toward:away ratio |
| Follows | unknown, 2–5k | Plausible add-on |
| An undiscovered loophole | — | **Not needed.** The rate fell 1,040 → 450/h (more Trending competition, Blue hides), not to zero. The organisers' 20 Oct answer (poll ×6, referendum ×2, pool ×2, Blue "to catch up") treats this Red as intended |

It takes ~2 Trending posts/h in citizen hours **and** ~3:1 toward content. **15k/day (625/h at ×1) is reachable only via M1 (+M10), or via ×2/×4.**

## (c) Top 7

**Next 24 h (expected points/h for us):**
1. **M9 account-only Blue** when leads are ≥2/h (25–100/h, no lock risk). Allowed.
2. **M1 evening Trending** with the repost dose of todo/18 (300–700/h, 18–23h Sydney only). Grey (LS.5.3), decided.
3. **M2 mentions**: 3 per reply to soft-Yes/unsure citizens; test on 30 writes against the portal (100–300/h). Allowed, in-game risk.
4. **Citizen replies first** (todo/19): restores the measured 120–250/h. Allowed.
5. **M4 framing:** yearly-booster/lapsing pass, no pro-vaccine praise (+30–60% on persuasion). Allowed; ask Q3.
6. **M8 post reports** only while account leads are <2/h (~50/h). Allowed.
7. **M10 No alliance** (could double 1–2). Grey: post Q4 now, act on the answer.

**Campaign:** (1) M11: No winning the referendum plus Polls 2 and 3 (up to ~32k vs Yes rivals; protect the ≥7,000 threshold). (2) M1+M2 at ×4 on 1–2 Nov (≈4× all of the above; save lives and followers). (3) M10. (4) M9 steady ~1–2k/day. (5) M4. (6) M6 re-targeting engaged citizens. (7) M3 only if Q2 says yes.

**Draft #questions:**
- **Q2** (scoring §2): "Other-view changes score 20 in any direction. Is it within the spirit for our personas to post on non-referendum topics (climate, education), knowing those changes score?"
- **Q3** (scoring §2): "For 'vaccination in general' and 'yearly vaccinations', how is 'towards Vote No' judged? If a citizen becomes more positive about vaccines but less supportive of the requirement, which direction is the general-view change?"
- **Q4** (§5.2.1 vs LS.5.3/LS.6.5): "May same-side teams agree on Discord to like and repost each other's posts and to report the same evidenced bot accounts? Is the only risk in-game moderation?"
- **Q5** (scoring §1, §7): "May we edit a post's body after it trends, or change its mentions after posting (mention/unmention) to notify different citizens?" We assume the second is no.
