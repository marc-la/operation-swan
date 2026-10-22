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

## The logs, before and after (2026-10-22 ~00:30 UTC, box logs to 00:08 UTC)
Data: the box's `logs/swan_actions.jsonl` (every write carries `git_sha`), `swan_outcomes.jsonl`, `swan_followups.jsonl`, `deploys.jsonl`, `data/portal.json`. These numbers support the echo diagnosis for "neither", but they add three things it doesn't explain.

1. **A bundle lines up, not one change.**
   - The last toward events (21 Oct 06:53, 07:53) ran on `842ea78` (deployed 05:52).
   - 08:00–14:00 UTC had ~6 citizen-facing writes/h, so ~1 event was expected. Its zero says nothing.
   - The drop starts **14:29–15:49 UTC**, when ~25 commits deployed together (todo/19–23, the split).
2. **The same Sydney clock hours on two nights (14:00–24:00 UTC):**

   | | 20 Oct | 21 Oct |
   |---|---|---|
   | citizen-facing writes | 122 | 1,180 |
   | own posts / own-thread replies / reposts | 22 / 67 / 79 | 13 / 0 / 0 |
   | reply model | qwen3.8-27b 68%, flash-lite 22% | Kimi 77%, flash-lite 17%, GLM 6% |
   | portal toward / away / neither | 1 / 5 / 12 | 0 / 0 / 46 |
   | citizen views / likes / replies (portal) | 217 / 54 / 47 | 316 / 72 / 84 |

   - **Away stopped too.** Toward + away went 6 → 0 while writes went ×10. At 20 Oct's rate per write we'd expect ~59; at its rate per hour ~6 (P(0) ≈ 0.25%). Echo explains "neither" rising, but not away vanishing. Our posts stopped being read in sessions where a referendum view moved at all.
   - **Engagement is not fine.** 10× the writes bought 1.3–1.8× the citizen engagement. Per reply, age-matched (under 3 h): views 1.87 → 1.27, citizen likes 0.086 → 0.038, citizen replies 0.104 → 0.053. The citizen reply rate is 5–8% by arm (`conversion_report.py`, 14:11–00:11), against 16% for replies in the 24 h to 21 Oct 08:00.
   - **Echo isn't new.** F14 (yes-but) was 34% of writes before and 37% after.
3. **Changed in the same bundle, so a lab can't test them, only live arms can:**
   - the reply model (qwen / flash-lite → Kimi);
   - own posts, own-thread replies and reposts stopped (amplification off 14:12; citizen writes first);
   - lean/firm No now answered (~31% by `read_stance`). The old targeter skipped them;
   - the sweep's old posts (citizen reply rate 2%).
4. **The vaccine-words idea is weak.** Only ~10% of citizen-facing writes mention vaccines, jabs, doses or boosters, in both eras. F3 + F13 fell from ~20% to ~7% of writes, yet "neither, on vaccination" per hour rose ~4×, roughly with volume. The No-vaccine variant is cheap; expect little from it.
5. **A parser gap.** The 21 Oct 17:53 line has "1 contribution to a change of mind" (no side, no "on vaccination"). `analysis.parse_activity` files it as `mind_contribution_other`, which `conversion_report.py` drops. By the guide's wording it's an "other view" change (20 / pool 10), ~2 h after todo/23 C (off-topic) went on. Not a toward event.
6. **Our followup agrees.** Stance labels on replied citizens: before 14:00 moved_no 3, moved_yes 1; after, moved_no 0, moved_yes 3.
7. **Scale.** The old regime's persuasion paid little: toward contributions ~7–8 points each, away −1 to −7, about +16 net in the 24 h to 21 Oct 08:00. **We have never had a primary toward (160).** The lab should aim at primaries, not at getting the old contribution rate back.

## Phase 1: the NPC lab (offline, no writes, ~half a day)
1. **The stand-in NPC:** use the organisers' LLM (`ctn.CompetitorLLM`, qwen2.5-3b at llm.legitreal.com; 3/min, 1 at a time; `docs/04-technical/api-reference.md`). It's provided to competitors and our bot no longer uses it. **The stand-in NPC and the classifier both run only on CompetitorLLM.** CLAUDE.md rule 2: external LLMs (Kimi, Gemini, GLM) may generate content, here the reply variants under test, but not play the citizen or judge it (that's analysis; open question #5).
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
5. **Run** within CompetitorLLM's budget (3/min ≈ 180 calls/h, 2 per trial: the session plus the classifier): start with **12 personas × the 6 most promising strategies × 3 seeds ≈ 216 trials ≈ 2.5 h**, then a second round on the top 3 with more personas. Report: toward No / neither / toward Yes per 100, by stance class. Write the table into [direction-2026-10-21](../docs/06-strategy/direction-2026-10-21.md) with the date and caveats: the lab is a proxy; only live results count.

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

## The lab is a team tool, not a script (Marc, 2026-10-22)
- **Package and service:** `src/swan_lab/` running on swan-ec2 as `swan-lab.service`:
  - a queue runner with the rate limit built in (CompetitorLLM 3/min, 1 concurrent, backing off on 429);
  - state and results in `data/lab/` (jsonl), synced to the team MongoDB by `swan_sync_mongo` (`lab_trials`, `lab_personas`).
- **Personas library:** `content/lab/personas/*.toml`, built by a script from real citizens' post histories (read-only, ≤ 30 reads/min). Each card holds occupation, place, family, values, concerns, and the referendum and vaccination views in their own words, plus the stance class. Rebuild weekly or on demand.
- **Strategies library:** `content/lab/strategies/*.toml`, one per strategy: name, author, the instruction added to the reply prompt, and which stance classes it targets. **Any teammate adds a strategy with one file and a push.** The service queues trials for new strategies automatically (personas × seeds).
- **Lab page on the dashboard** (`/lab.html`, behind the same password), rebuilt every minute by swan_dash from `data/lab/`:
  - one row per strategy: trials, toward No / neither / toward Yes per 100, by stance class, and its rank against Base;
  - click through to example drafts plus the simulated citizen's reaction.
  - Separate template `lab.html.j2`; the main page gets one link.
- **Model switch:** `config.LAB_MODEL` = "competitor" (default). "local-qwen2.5-3b" (an OpenAI-compatible endpoint, e.g. llama.cpp or ollama) stays off until the organisers answer question #5 (an external LLM for analysis). The simulated NPC and its classifier never use Kimi, Gemini or GLM.
- **Docs:** `docs/06-strategy/npc-lab.md`: what it is, how to add a strategy, how to read the page, the caveat (a proxy; live results decide).
