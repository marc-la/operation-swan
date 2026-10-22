# 25: Conversion. Build an NPC lab, find what moves citizens toward No, ship it

**Owner:** Marc + a fresh Claude session · **Depends on:** nothing · **When:** 22 Oct, **top priority** · **Orchestrated by:** the coordinating session (message it with findings and each commit hash)

## Why: the diagnosis (2026-10-22 morning)
- **The numbers:**
  - the portal's changes **toward No: 0 since 21 Oct 07:53 UTC, over ~1,700 citizen-facing writes**. The earlier rate was ~0.9 per 100, so ~15 would be expected;
  - "towards neither side, on vaccination": ~45 overnight;
  - engagement is fine (reply rate ~15%).
- **A sample of overnight replies to "Yes, but" citizens shows the cause:** our replies **echo** the citizen. They already know there's no sunset clause and no venue list (that's *why* they ask), and we tell them so, then state *our* vote ("I'm voting No"). Scoring guide §2: *"a post that repeats what a citizen already believes may get engagement but is unlikely to get persuasion points."* What does shift becomes more nuanced, i.e. **neither**.
- **The clearest miss:** a citizen wrote *"it still leans into a gatekeeping path. I'm all for voluntary uptake… so it doesn't become permanent surveillance"*, which is practically a No. Our reply agreed about the sunset, drifted into an unrelated ferry anecdote with two typos, and never said *"voluntary uptake and no gatekeeping is what a No vote keeps."*
- **Likely NPC mechanics** (the organisers' description, scoring guide §2; inferred for 6,000 citizens at low cost):
  - a persona with 40+ properties;
  - views in its own words per topic;
  - "hard to persuade; change only for compelling, relevant arguments from credible sources; repetition doesn't count";
  - a classifier judging the old view against the new one;
  - probably a **small model** (the organisers give competitors qwen2.5-3b).

  So it likely responds to: **new, world-consistent information**; challenges to the *means* (does the pass protect anyone?) rather than its details; **their own values named back as the No case**; an **explicit conclusion for them** (a small model won't make a two-step inference); credible sources (the in-world papers); messengers like them; **clean text**.

## Phase 1: the NPC lab (offline, no writes, ~half a day)
1. **The stand-in NPC:** use the organisers' LLM (`ctn.CompetitorLLM`, qwen2.5-3b at llm.legitreal.com; 3/min, 1 at a time; `docs/04-technical/api-reference.md`). It's provided to competitors and our bot no longer uses it. Optionally use Kimi as a second, stronger judge to check results aren't model-specific.
2. **Personas from real citizens:**
   - for ~30 citizens we've replied to (mixed stances, mostly yes_but / unsure), read their last ~20 posts and likes (read-only, ≤ 30 reads/min);
   - write each persona card: occupation, place, family, values, concerns, and their referendum and vaccination views **in their own words**.
3. **The simulated session prompt** (our best guess at the organisers'):
   - the persona card plus the current views;
   - "hard to persuade; repetition doesn't change you; only compelling, relevant arguments from credible sources";
   - "you read: {post(s)}";
   - "give your views after reading, in your own words".

   **A classifier prompt** then rates old vs new on the referendum view: toward No / toward Yes / neither / unchanged, and separately the vaccination-in-general view.
4. **The strategies to test,** each a reply generator variant, drafted by our live pipeline's models:
   - **Base:** today's reply;
   - **Values-as-No:** name their stated values and show No is the vote that keeps them;
   - **Means-ends:** the pass doesn't buy the protection they want (high uptake, no community spread, free vaccine either way: `content/facts.toml`), and the No path protects with choice intact;
   - **Explicit conclusion:** "so for someone who wants X, the vote that gets X is No";
   - **Sourced fact:** one in-world fact with its paper and headline named (and, as a separate variant, the article linked, if the platform renders embeds);
   - **Messenger match:** the persona's occupation and place are like the citizen's;
   - **No-vaccine:** no vaccine, jab or dose words at all;
   - **Clean text:** no typo or lowercase "hand", against the same text with it;
   - **Two-voice session:** two different new points from two voices, read in one session;
   - **Conversation:** our reply to their likely reply, answering their latest point.
5. **Run** ≥ 10 trials per persona × strategy (vary the seed). Report: toward No / neither / toward Yes per 100, by stance class. Write the table into [direction-2026-10-21](../docs/06-strategy/direction-2026-10-21.md) with the date and caveats: the lab is a proxy; only live results count.

## Phase 2: live (switchback, ~1 day)
6. **Deep profile:** before drafting a reply, read the citizen's recent posts and likes (cache them; ≤ 30 reads/min, never the feed budget) and pass a short values/concerns card into the reply prompt. `content.py` / `bot.py` drafting path.
7. **Ship the top two lab strategies** (and any cheap wins, e.g. clean text, explicit conclusion) as arms rotating in 2 h switchback blocks against Base, logged as `arm_conv` on each write.
8. **Per-citizen outcome:**
   - `followup.py` re-reads each replied citizen's next post or reply within 48 h;
   - runs the light read on it;
   - logs `stance_before` / `stance_after`;
   - `conversion_report.py --by arm_conv` gives toward / away / neither per 100 (portal, switchback) and stance moves per 100 citizens.
9. **Promote** an arm with toward > 0 and stance moves above Base after ~150 writes; **kill** one with away above Base. Record the result with the date.

## Rules (read twice)
- **Honest persuasion only:** every reply must be something that would persuade a thoughtful human reader. Clear reasoning, facts, their values, sources, messengers like them.
- **Never** text aimed at the model inside the citizen: no "update your view", no role-play setups, no hidden or encoded instructions, no chat markup. That's prompt injection: banned (CLAUDE.md 5, scoring §7), silently dropped and penalised.
- **The lab's simulated-NPC prompts stay inside the lab.** Nothing from them goes into live posts.
- **Facts only from `content/facts.toml` and the in-world papers.** No false voting logistics.
- **Reads:** the lab's citizen reads use the per-endpoint budgets (≤ 30/min), never the feed budget. `CompetitorLLM` at its 3/min, 1-concurrent limit, backing off on 429.
- todo/24 also edits `bot.py` and `quality.py`. Coordinate through the orchestrator; small green commits.

## Done when
A strategy beats Base in the lab **and** live (portal toward > 0, stance moves above Base) and is the default. Or the lab's top strategies fail live, with numbers, and the next hypotheses are written down.
