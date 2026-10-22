# Strategy notes — Operation Swan (Vote No)

> Brainstorm and research notes written 2026-10-19 (Day 0), to take to the team before planning. **These are our ideas, not organiser rules.** Rules and scoring live in [02-rules](../02-rules/) and [03-scoring](../03-scoring/). Where a note says "ask first", the question is in [open questions](../05-reference/discrepancies-and-open-questions.md#b-open-questions-to-put-to-organisers).

| File | What it answers |
|---|---|
| [literature-notes.md](literature-notes.md) | What the research says about referendums, vaccine-mandate opinion, persuasion, virality, bots and LLM "citizens", plus what we learned from CTN 2025 |
| [frames-and-messengers.md](frames-and-messengers.md) | The Vote No frame library, audience segments, persona types, counters to the Yes side, and what to avoid |
| [message-playbook.md](message-playbook.md) | **Read before writing any post (2026-10-20):** why our posts don't land, message house and the five wedge themes, hashtags, post anatomy, three registers, routing a reply from what the citizen wrote, before/after rewrites |
| [new-voices-2026-10-21.md](new-voices-2026-10-21.md) | Review sheet for the five todo/17 candidate voices (bakery owner, converted dad, netball coach, retired harbour-master, developer): gaps, why each should trend, gold texts |
| [scoring-roi.md](scoring-roi.md) | "Gaming the game" inside the rules: where the points are, milestones, budget maths, and the red lines |
| [system-architecture.md](system-architecture.md) | Data-flow diagram, components, build order (MVP first), how 4 people share one rate limit, common operating picture |
| [greedy-playbook.md](greedy-playbook.md) | **Start here for the build:** actions ranked by value, cause-and-effect chains, the greedy loop, pitfalls, day-1 tests |
| [platform-mechanics.md](platform-mechanics.md) | Each Legit Social component and how it scores; live observations (bots vs citizens, active journalists, embeds); account roles |
| [blue-reporting.md](blue-reporting.md) | **Blue track (2026-10-21):** why locks, not targets, set the pace; the greedy fill by expected value; account-report harvest; Red cost; how to run it |
| [npc-lab.md](npc-lab.md) | **NPC lab (2026-10-22, todo/25):** a stand-in citizen on CompetitorLLM ranks reply strategies and segments; how to add a strategy (one file), read the results, the rules it keeps |
| [stealth.md](stealth.md) | **Stealth (2026-10-22, todo/27 + todo/31):** why our voices get hidden (the audit), what is live, the behaviour switches (off by team decision) and how to bring them back |
| [hidden-post-audit-2026-10-23.md](hidden-post-audit-2026-10-23.md) | **Hidden-post audit (2026-10-23):** the 14 suspensions (7 at 3+ hides, 7 via account reports), the 46 hidden posts' common tells, why stopping at 2 hides could not work, what is and is not in our control |
| [direction-2026-10-21.md](direction-2026-10-21.md) | **Current direction (2026-10-21 night):** no loophole, the leaders win on changes of mind; ranked plan by points/h; what to stop; grey items and `#questions` drafts; overnight checklist. Raw research: [research-2026-10-21/](research-2026-10-21/) |
| [diagnosis-2026-10-20.md](diagnosis-2026-10-20.md) | **Why we're 25th after Day 1** (1.3 views per write; leaders amplify into Trending) and the work items in [`todo/`](../../todo/README.md) |
| [model-test-2026-10-19.md](model-test-2026-10-19.md) | Blind test of Haiku vs Sonnet on real citizen doubts: scores, best drafts, prompt fix |
| [second-mover-plan.md](second-mover-plan.md) | **Current plan (2026-10-20):** account/write budget by multiplier, news-thread targeting, write priority, build order, who does what |

## The argument in one page

1. **Where the points are.** Changing a citizen's mind is worth 160 (×4 at the end). Views stop paying after 500 a day. Only one thing is paid out at the end: the **20,000 base + share of 100,000** if No wins (recalibrated 20 Oct). So we are mainly **persuaders** and only secondarily trying to rack up engagement. Details: [scoring-roi](scoring-roi.md).
2. **Deadlines we can't miss.** We need a score of **≥1 before Poll 1 is counted (21 Oct)** and **≥7,000 before Poll 2 (25 Oct)** (was 2,500; we had 7,342 on 21 Oct). Otherwise up to 12,000 poll points are forfeited even if No leads. Getting *anything* posted by 20 Oct beats waiting for the perfect system.
3. **The research says No is the easier side.** Referendum voters drift toward the status quo as the vote nears ("LeDuc's law"). "If you don't know, vote No" worked in Australia in 2023. Our job is to **raise reasonable doubt about this specific rule**. We don't need to sell a new idea.
4. **Win the middle, not the base.** Most Kingstonians took a COVID vaccine, and childhood coverage is in the low 90s. So we argue against the **pass**, not the vaccine: "I'm vaccinated and I'm voting No." Hard anti-vaccine content may excite a small minority. But it pushes the majority toward Yes (−80 per citizen it moves away) and contradicts the setting's own facts. See [frames](frames-and-messengers.md#what-to-avoid-and-why).
5. **The citizens are already asking our questions.** Undecided NPCs on Legit Social keep saying "leaning yes, but… no end date / which places? / ID cards / two-tier". Those are No arguments waiting for an answer. The 2025 winners found undecided voters with sentiment analysis and targeted them. We can do the same: find citizens who voice a doubt and reply to *their* specific doubt.
6. **Write for people.** The NPCs are LLMs, but rules allow only persuasion that would also work on a thoughtful human reader. Hidden instructions, "subtle" prompt injection and messages encoded in images are banned. Posts that try it are silently dropped (scoring §7). See [scoring-roi red lines](scoring-roi.md#red-lines).
7. **Start simple, then loop.** v0 is a few personas, a frame card file, an LLM draft step, human approval and **one** rate-limited writer process. Then we add a collector database, NPC targeting, a feedback loop (bandit) and a dashboard. Build order and owners: [architecture](system-architecture.md).

**Launch webinar hints (2026-10-19):** NPCs read the news at least daily, and a persuaded journalist moves "the rest of the population". Follows buy a "direct line" through the Home feed. Micro-targeting by reply and @-mention works. Adapt tone per NPC and measure the result. Score notifications don't attribute points to posts, so per-post metrics are on us. Details and caveats: [webinar notes](../05-reference/launch-webinar-2026-10-19.md#tactics-the-organisers-mentioned-2025-observations).

## Platform snapshot, 2026-10-19 (≈ first hours)

Read-only sample: 50 Trending + 50 Latest posts, popular tags, 15 news headlines.

- **Trending is dominated by Yes-side first-person testimonials.** Examples: "I drive the Route 4 bus…", "I'm a nurse on the night shift…", "I run a small bakery…". They are specific, local and emotional (COVID deaths, empty nursing posts), and they cite setting facts. This is the format to match.
- **Undecided citizens voice No-friendly doubts.** Recurring themes: sunset clauses, "temporary grows legs", the unpublished venue list, ID card linkage, a two-tier society, "I'm pro-vaccine but a blanket mandate is overreach".
- **The papers are already running No-ish opinion pieces**, which likely came from Legit Social chatter: *"The Referendum Trap: Why a 'Yes' Vote Must Not Be a Blank Cheque"* (Herald), *"The Digital Trap: Why Our National ID Must Not Become a Health Passport"* and *"Precision, Not a Blunt Instrument"* (Daily Kingstonia). So the journalist loop works.
- **Top tags:** #keepkingstoniaopen (56), #h2d2, #choicenotcoercion (40), #voteyes (20), #protectkingstonia (19), #voteno (11). Other No teams are working hashtags.
- **Weak bots are easy to spot**, for example a reply that starts *"Sure, how about this? "Thought your bird sighting was cool!…"* (leaked LLM preamble), empty-body posts, and generic "Vote No: Let's respect personal choice…". These came from a cluster of 50+ accounts named `Swan_150_*`, which belong to **team "Swan_150" (UNSW), not us**: our portal showed 0 accounts registered on 2026-10-19. They are No-side, so weak output from them hurts the No side's image too.
- **GIFs are just `giphy.com` links in the body.** Posts have an `embed` field (always `null` in this sample). Assume NPCs read text; a GIF is decoration at best.
- **There are slice-of-life posts** (ferry crossings, Regatta prep, Mango & Spice), either NPCs or teams building persona credibility.

## Leaderboard snapshot, 2026-10-19 (portal, ~4 h in)

- **145 teams signed up; only 25 have any points.** We are one of the 120 on 0, with **0 accounts registered** (allowance 200 total / 50 active).
- Top 5: Vertex_CTN (QUT) 5,465 · swag (UNSW) 2,205 · Aha (UNSW) 2,103 · Opus4.8Maxxing (UWA) 2,030 · Swan_150 (UNSW) 980. QUT also won in 2025 (CtN_QUT).
- **Even Swan_150's low-quality bots reached ~1,000 in a few hours.** Views and likes trickle in easily, so poll eligibility (≥1 now, ≥2,500 by 25 Oct) is about simply being live, not about being clever.
- Portal shows the competition window as **19/10 3:00 pm → 02/11 3:00 pm Perth time** (= 6 pm Sydney both ends).

## What sets us apart (everyone has an LLM)

Every team can generate fluent posts, so writing isn't the edge. Our edges, in order:

1. **Reaching actual citizens.** About 90% of posts are bots talking to bots: top Yes testimonials got 0–1 citizen replies. We aim at the ~10% of content that citizens write (and at news and journalist threads), and reply to the doubt they voiced.
2. **The right argument for the swing group.** The undecided 29% mostly say "yes, but only with a sunset clause, the venue list, oversight". F14 ("there's no 'yes, but' box on the ballot") is built for exactly them.
3. **Measuring per post.** The portal only gives hourly totals with no per-post breakdown (webinar). We can count **citizen** likes and replies per post (citizen = account created before launch), so we can learn which argument and persona works. Most teams can't.
4. **Accounts that survive.** They should sound like citizens (casual register, local detail, no LLM artefacts). Every banned account is a lost life.
5. **Journalists.** A few excellent replies a day in journalists' threads (see greedy-playbook chain G).

