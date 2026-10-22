# Direction, 2026-10-21 night: where the points are and what to do overnight

> Written 2026-10-21 ~13:40 UTC (21:40 Perth) from five read-only research passes (rules, platform, our data, other teams, throughput), with raw notes in [research-2026-10-21/](research-2026-10-21/). Estimates are rough and labelled. Base points at ×1 unless marked.

## Bottom line
1. **No hidden loophole explains the leaders.** The leader had 28,192 at ~27 h, before any poll and while Blue rulings took 24 h: **~1,040 points/h of Red at ×1**. Views, likes, replies and follows can only add up to a few thousand of that. The rest has to be **changes of mind** (160 each plus pool shares), on the order of 100–250 in 2.5 days ([A](research-2026-10-21/A-rules.md#b-leader-decomposition-43252--3000-poll-1--40250-in-54-h), [D](research-2026-10-21/D-competitors.md#b-best-deduction-how-the-leaders-score)).
2. **Our gap is conversion, not reach.** Persuasion is **2.7%** of our non-poll points (121 of 4,555). We have had **0 primary changes toward No**, 6 small contributions, 8 away, and 37 "towards neither side, on vaccination" ([C §1](research-2026-10-21/C-ourdata.md#1-points-by-source-portal-19-oct-1909-to-21-oct-1253-utc)).
3. **The engine is the citizen reply loop.** Every citizen post draws 2–9 team replies, the first within 0.1–1 min. Citizens answer replies to their own post (notifications), like and reply in the same second, and follow the account they're talking to ([B](research-2026-10-21/B-platform.md#headline-findings), [D §2–4](research-2026-10-21/D-competitors.md#a-observed-tactics-with-evidence-and-citizen-yield)). Our best write, a reply to a fresh citizen post, earns **~3.1 points**. A heavy amplified post earns **0.28 per write**.
4. **What limits us is the supply of citizens, not the write budget.** Latest is ~98% team bots. At full coverage there are ~40–55 useful citizen-facing writes an hour at peak (~0.8/min), not 3/min ([E](research-2026-10-21/E-throughput.md#a-bottlenecks-with-numbers)). Citizens act at all hours of the Sydney day ([C §6](research-2026-10-21/C-ourdata.md#6-hours-sydney-time)), so overnight Perth is not dead.
5. **Polls and the referendum are the big prizes** (×1): Poll 2 on 25 Oct pays 6,000 if No leads beyond 52–48 (3,000 if closer, needs ≥7,000; we have 7,555). The referendum pays 20,000 plus a share of 100,000 to the winning side, by persuasion weight. Every change toward No feeds both.

## Marc's questions
- **How much does self-amplification help?** Almost not at all. 42 heavy posts cost 1,420 own likes and 506 writes and returned ~140 points (0.28/write), and none ever reached Trending. Own likes on our replies to citizens were never tried (a cheap test, todo/20).
- **Should we write at 3/min to target voters?** There aren't that many to reach. Answer every reachable citizen within minutes (~0.8/min at peak). More writes to bots or cold targets earn ~0.03 likes each and add hidden-post risk.
- **Multiple swan_bot processes?** No. The 3/min is team-wide, so a second writer adds no budget. Both would rewrite `swan_state.json`, the account `last_write` fields and `llm_spend.json`, causing double replies, broken voice gaps and an overrun spend cap. A setup whose purpose is more writes reads as circumventing a limit (LS.5.2). Drafting the next reply while the pacing timer runs fits in one process ([E §b](research-2026-10-21/E-throughput.md#b-marcs-three-questions)).
- **Can the API keys and LLMs cope?** At realistic volume, yes: Kimi costs ~$0.0011 per call, ~$0.80–1.60/day at full coverage once its length rejects are fixed, inside today's $2.55/day reply share. The free Gemini flash-lite (500/day) runs out every afternoon (Sydney 2:30–6pm, every free model parked). **Enabling Gemini billing with a spend cap** is the cheap fix (Marc's call).
- **The loophole?** None needed, and none found that explains the leader. The real edges: Blue account reports never trigger the 6 h lock (in use); "other view" changes pay 20 in any direction (grey); @mentions reach chosen citizens (grey). See the grey list below.

## Ranked plan (expected points/h for us)
| # | Move | Now (×1) | At ×4 (1–2 Nov) | Status | Who / next step |
|---|---|---|---|---|---|
| 1 | **Ship todo/19:** citizen reply before any thread job; Latest every 2 min, paged to the last seen post; fresh posts first; classify keeps "Yes, with conditions" (43 of 53 brought back); reply-backs and second voices on | 15–25 → **250–500** at peak (120–250 measured at 25% coverage) | ~1,000–2,000 | Allowed | **Shipped** 2026-10-21 (d99bd34) |
| 2 | **Replies that convert** ([todo/20](../../todo/20-replies-that-convert.md)): the style citizens answer (mirror their detail, concede it, one anchor or fact, state No; 150–280 characters); the levers that worked; drop the weak frames; no pro-vaccine praise until Q3 is answered | Unknown, the biggest ceiling. One toward change an hour ≈ +200; the leaders' implied pace is ~4/h | ×4 | Allowed | New session tonight |
| 3 | **Blue account-first reporting:** account reports can't lock us; each suspension pays 15 to every open reporter. Leads are post authors and reply-ring repliers (pure likers never get a hidden post). A lock delays a lead rather than losing it, and our own post hides create leads, so post reports still matter | 25–100, ×1 for the rest of the game | same (Blue stays ×1) | Allowed | **Live** (`swan-blue`, 8cd57ac: only account reports go out when there are enough leads to fill every free slot) |
| 4 | **Fix Kimi's length rejects** (47 of its 64 rejects; 2.8 calls per accepted reply) | +25–75 (10–25% more replies saved, drafting 17 s → ~8 s) | ×4 | Allowed | todo/20 step |
| 5 | **LLM headroom:** replies already draft on Kimi/GLM first (Bedrock credits). Full coverage costs ~$0.8–1.6/day against a $2.55/day reply share | Protects ~3.5 h/day of peak | ×4 | Allowed | **Gemini billing not needed now** (Marc, 2026-10-22). Revisit only if `llm_spend.json` shows the daily share running out, or second voices stall when flash-lite runs out (then move `second_voice` to the strong models) |
| 6 | **@mentions,** ≤3 per reply, to profiled "Yes, but" citizens who share the doubt answered; never the same citizen twice | 100–300 (another team: ~0.37 citizen likes per mention) | ×4 | **Grey** (LS.5.3 "unsolicited mass mentions") | Post the question tonight; build only after a yes |
| 7 | **No-side alliance on the official Discord:** co-like and repost No posts, co-report evidenced rings | Mostly a ×2/×4 lever (Trending in Sydney evenings, faster Blue rulings) | high | **Grey** (§5.2.1 allows coordination; LS.5.3 and LS.6.5 in-game) | Ask first (Q4) |

## The plan: changes of mind at volume (22 Oct → 2 Nov)
The leaders' points are changes of mind at volume. That needs three things, in this order: **reach every citizen** (volume), **say what moves them** (conversion), and **measure the result honestly** (feedback). No separate sentiment system: a cheap, loose first pass in code decides *who* (priority, not filters), and the drafting call reads the citizen and decides *what*.

| Layer | Where | What | Target |
|---|---|---|---|
| Volume | [todo/19](../../todo/README.md) (shipped), todo/21 (shipped 2026-10-21: 8446cbf, a035e4f, c35ac3c) | Read Latest every 2 min; fresh posts first; hard-skip only non-citizens, off-topic, hostile and replied posts; the stance sets priority; per-post and per-session limits, not 72 h per author; citizen replies count as targets too | ≥ 80% of citizen items answered; 40–55 citizen-facing writes/h at peak |
| The light read | [todo/20](../../todo/20-replies-that-convert.md) step 2 | One drafting call returns stance, doubt, frame and reply (or skip); the stance picks the approach; logged | Calibrated against the regex class in a day |
| Conversion | todo/20 steps 3–8 | Concede-and-anchor style A/B; weak frames out; no vaccine advocacy; reply-backs within minutes, up to 3 turns; a second voice inside the session; one own like A/B | "Towards your side" per 100 citizen-facing writes > "away" + "neither" |
| Feedback | todo/20 step 1 | Portal hourly events joined to writes; per-class and per-arm reply rates; skip reasons; followup re-reads | A daily read-out, then winners become defaults |
| Blue (steady) | `swan-blue` (live) | Account leads first | 25–100/h at ×1 |

**Timeline (Sydney days):**
- **22 Oct:** todo/21 and todo/20 built and shipped; arms running.
- **23–24 Oct:** first read-out; winning style and classes become defaults; the stop rules applied.
- **25 Oct, Poll 2:** 6,000 to No teams if No leads beyond 52–48 (3,000 if closer); we're above the 7,000 threshold.
- **26–31 Oct (×2):** scale what converts; keep voices alive (hidden-post alerts).
- **1–2 Nov (×4):** everything at full volume on the proven style. No experiments, no backfire-prone classes.

**Decision rules:**
- An arm that raises "away" per 100 writes is switched off that day.
- A target class with a reply rate below half the average for 48 h drops to the lowest priority.
- If "towards your side" stays at 0 after ~1,000 citizen-facing writes on the new style, stop and rethink the content with fresh eyes, rather than adding volume.

## Stop doing (tonight)
- **Heavy amplification:** 0.28 points/write, and its filler likes are camouflage only. **Paused 2026-10-21 14:12 UTC** (`~/ctn/AMPLIFY_OFF` on swan-ec2; remove the file to resume). Plain persona posts come back at most 1 in 4 writes, behind citizen replies. Trending pushes are **dropped** (Marc, 2026-10-22; old todo/18 deleted). The dose, if ever revisited, is in [amplification](amplification.md#re-fit-and-diagnosis-2026-10-21-evening-09001340-utc-read-only).
- **Proactive follows:** 1–2 of 80 followed back. Follows come 0–2 min after our *reply* to the citizen, and mass-following reads as spam (LS.4.2).
- **Journalist replies** (0 of 13 answered) and **news-thread reads** (0 citizen replies under post-launch paper posts; small follow-up to todo/19).

## Grey or prohibited, with questions to post in `#questions` tonight
Drafts are in [A (Q2–Q5)](research-2026-10-21/A-rules.md#c-top-7) and [B](research-2026-10-21/B-platform.md#draft-for-questions-discord):
- **Mentions:** may a reply mention ≤3 citizens who haven't talked to us, if each mention is relevant and never repeated? **Treat re-pointing an existing post with `mention`/`unmention` as prohibited:** that route uses the 60/min budget and would sidestep the 3/min limit (LS.5.2, rules §1.2).
- **"Other view" changes** (20 in any direction, no penalty): may personas post on non-referendum topics knowing those changes score? Not seen in use by other teams.
- **Direction on "vaccination in general" and "yearly vaccinations":** if a citizen grows more pro-vaccine but less pro-requirement, which way does the general-view change score? Our "I'm vaccinated, voting No" lines may be scoring as neutral or away, which would explain the 37 "neither, on vaccination" events.
- **Same-side coordination** (alliance): allowed by §5.2.1, but is LS.5.3/LS.6.5 the only risk?
- Still open: Q1, own-team likes and reposts (reaction farming) ([open questions](../05-reference/discrepancies-and-open-questions.md)).

## Overnight checklist (Perth)
1. ~~Push todo/19~~ **done** (d99bd34).
2. **Marc:** pause amplification (`AMPLIFY_OFF`, above).
3. Questions: **not posted for now** (Marc, 2026-10-22), so mentions, the alliance and "other view" posting stay off, and todo/20 takes the safe path on vaccine talk.
4. **Start [todo/20](../../todo/20-replies-that-convert.md) and todo/21 (shipped 2026-10-21: 8446cbf, a035e4f, c35ac3c)** in fresh sessions. They touch the same files: small commits, `git diff` first.
5. ~~Gemini billing~~: not needed now (row 5).
6. **Morning check (~07:00 Perth):**
   - `data/portal.json` events: ≥150 points/h and ≥5 citizen replies/h;
   - any "towards your side" events;
   - refresh records show candidates > 0 and `citizen_latest_*` counts.

## Caveats
- Samples are small: 20 citizens, 4 mention posts, 5 engaged competitor replies.
- The portal counts ~2.5× more likes and replies than our own reads find, so trust the rankings, not the absolute numbers.
- The two analyses differ on where the leaders' persuasion happens: Trending exposure in Sydney evenings ([A](research-2026-10-21/A-rules.md)) versus the 1:1 reply loop ([D](research-2026-10-21/D-competitors.md)). Both say the points are changes of mind. Our data can only test the reply loop for now.
- We did not and won't try to work out which accounts belong to which team (rules §5.2.2).

## Morning check, 2026-10-22 ~00:00 UTC (8am Perth), after todo/19–23
| | Overnight (15:45–24:00 UTC) |
|---|---|
| Points | **3,226 in ~8 h (~400/h; was 15–25/h before the fixes)**: ~65% engagement (views, likes, replies, follows), ~35% Blue (49 awards). Rank 23 → **18** (10,882; leader 46,999) |
| Volume | ~1,120 citizen-facing writes (reply 555, sweep 216, second voice 204, turnout 65, reply-back 65, off-topic 11, older 3, engaged 2); 2.2–2.3 writes/min, steady |
| Coverage | 22:00 UTC: 168 citizen items seen, 130 answered, 0 lost. 23:00: 166 seen, 93 answered, 54 waiting, as the queue grew at Sydney morning (oldest 29 min) |
| Gate | First-call 83% overall: Kimi 89% (n=857), flash-lite 86%, **GLM-5 0% (n=69)**. Lost to the gate: 2 |
| Conversion | **0 toward No**, ~45 "neither, on vaccination". The last toward event was 21 Oct 07:53 UTC |
| Blue | 52 filed, 44 hidden, 2 genuine (96%). Stopped by a genuine ruling's 6 h lock until 02:01 UTC, not by a cap |

**Next:**
- [todo/24](../../todo/24-throughput-to-three.md): ~2.9 writes/min, GLM out, no wasted drafts.
- [todo/25](../../todo/25-conversion-what-moves-them.md): conversion, top priority.
- [todo/26](../../todo/26-blue-widen.md): fewer locked hours, more teams at full rate.
