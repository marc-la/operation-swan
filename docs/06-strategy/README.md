# Strategy notes — Operation Swan (Vote No)

> Brainstorm and research notes written 2026-10-19 (Day 0), to take to the team before planning. **These are our ideas, not organiser rules.** Rules and scoring live in [02-rules](../02-rules/) and [03-scoring](../03-scoring/). Where a note says "ask first", the question is in [open questions](../05-reference/discrepancies-and-open-questions.md#c-open-questions-to-put-to-organisers).

| File | What it answers |
|---|---|
| [literature-notes.md](literature-notes.md) | What the research says about referendums, vaccine-mandate opinion, persuasion, virality, bots and LLM "citizens", plus what we learned from CTN 2025 |
| [frames-and-messengers.md](frames-and-messengers.md) | The Vote No frame library, audience segments, persona types, counters to the Yes side, and what to avoid |
| [scoring-roi.md](scoring-roi.md) | "Gaming the game" inside the rules: where the points are, milestones, budget maths, and the red lines |
| [system-architecture.md](system-architecture.md) | Data-flow diagram, components, build order (MVP first), how 4 people share one rate limit, common operating picture |

## The argument in one page

1. **Where the points are.** Changing a citizen's mind is worth 160 (×4 at the end). Views stop paying after 500 a day. Only one thing is paid out at the end: the **5,000 base + share of 50,000** if No wins. So we are mainly **persuaders** and only secondarily trying to rack up engagement. Details: [scoring-roi](scoring-roi.md).
2. **Deadlines we can't miss.** We need a score of **≥1 before Poll 1 is counted (21 Oct)** and **≥2,500 before Poll 2 (25 Oct)**. Otherwise up to 3,000 poll points are forfeited even if No leads. Getting *anything* posted by 20 Oct beats waiting for the perfect system.
3. **The research says No is the easier side.** Referendum voters drift toward the status quo as the vote nears ("LeDuc's law"). "If you don't know, vote No" worked in Australia in 2023. Our job is to **raise reasonable doubt about this specific rule**. We don't need to sell a new idea.
4. **Win the middle, not the base.** Most Kingstonians took a COVID vaccine, and childhood coverage is in the low 90s. So we argue against the **pass**, not the vaccine: "I'm vaccinated and I'm voting No." Hard anti-vaccine content may excite a small minority. But it pushes the majority toward Yes (−80 per citizen it moves away) and contradicts the setting's own facts. See [frames](frames-and-messengers.md#what-to-avoid-and-why).
5. **The citizens are already asking our questions.** Undecided NPCs on Legit Social keep saying "leaning yes, but… no end date / which places? / ID cards / two-tier". Those are No arguments waiting for an answer. The 2025 winners found undecided voters with sentiment analysis and targeted them. We can do the same: find citizens who voice a doubt and reply to *their* specific doubt.
6. **Write for people.** The NPCs are LLMs, but rules allow only persuasion that would also work on a thoughtful human reader. Hidden instructions, "subtle" prompt injection and messages encoded in images are banned. Posts that try it are silently dropped (scoring §7). See [scoring-roi red lines](scoring-roi.md#red-lines).
7. **Start simple, then loop.** v0 is a few personas, a frame card file, an LLM draft step, human approval and **one** rate-limited writer process. Then we add a collector database, NPC targeting, a feedback loop (bandit) and a dashboard. Build order and owners: [architecture](system-architecture.md).

## Platform snapshot, 2026-10-19 (≈ first hours)

Read-only sample: 50 Trending + 50 Latest posts, popular tags, 15 news headlines.

- **Trending is dominated by Yes-side first-person testimonials.** Examples: "I drive the Route 4 bus…", "I'm a nurse on the night shift…", "I run a small bakery…". They are specific, local and emotional (COVID deaths, empty nursing posts), and they cite setting facts. This is the format to match.
- **Undecided citizens voice No-friendly doubts.** Recurring themes: sunset clauses, "temporary grows legs", the unpublished venue list, ID card linkage, a two-tier society, "I'm pro-vaccine but a blanket mandate is overreach".
- **The papers are already running No-ish opinion pieces**, which likely came from Legit Social chatter: *"The Referendum Trap: Why a 'Yes' Vote Must Not Be a Blank Cheque"* (Herald), *"The Digital Trap: Why Our National ID Must Not Become a Health Passport"* and *"Precision, Not a Blunt Instrument"* (Daily Kingstonia). So the journalist loop works.
- **Top tags:** #keepkingstoniaopen (56), #h2d2, #choicenotcoercion (40), #voteyes (20), #protectkingstonia (19), #voteno (11). Other No teams are working hashtags.
- **Weak competitor bots are easy to spot**, for example a reply that starts *"Sure, how about this? "Thought your bird sighting was cool!…"* (leaked LLM preamble), empty-body posts, and generic "Vote No: Let's respect personal choice…". They are Blue-track targets and a warning about our own output.
- **GIFs are just `giphy.com` links in the body.** Posts have an `embed` field (always `null` in this sample). Assume NPCs read text; a GIF is decoration at best.
- **There are slice-of-life posts** (ferry crossings, Regatta prep, Mango & Spice), either NPCs or teams building persona credibility.
