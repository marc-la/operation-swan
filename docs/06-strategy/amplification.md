# Amplification: own-team reach into Trending (reaction farming, made to look organic)

> Live since 2026-10-20 (Day 1 evening) behind `--amplify`: [amplify.py](../../src/swan_bot/amplify.py), [ring_audit.py](../../scripts/ring_audit.py). Was todo/04.

## Why
Our writes average **1.3 views**. Every Trending post is a team post with 40–90 team likes and 20–66 team replies, and that is what puts it in front of citizens (300–480 views, 10–37 citizen likes) ([diagnosis](diagnosis-2026-10-20.md)).

## How Trending ranks (measured 2026-10-20 11:13 UTC, read-only, top 36 + counters)
- The feed returns `global_hot_score` and `rank_position`. The **top-35 cutoff was ~24**. Posts **6–7 min old** were already in with ~45 likes + ~6 reposts.
- Least-squares fit (RMSE ~2.2 on a 24–42 range, so a rough guide): **hot ≈ 1.85·√(likes + replies + 8·reposts) − 2.1·age_h + 10.8**. So:
  - **a repost weighs ~6–8 likes and a reply ~1** (the top 4 posts all had 12–34 reposts);
  - the score falls ~2 points an hour, so a post needs its engagement **early**. To enter the top 35 it needs ~50 like-equivalents in its first ~15 min, and it holds for ~1–2 h;
  - the binding resource is **distinct accounts** (one like per account per post), not the 30/min like budget.
- Re-fit when the 08 collector has a day of snapshots.
- **Tuned 2026-10-20 ~23:00 Perth:** the first 11 measured posts (heavy: ~34 likes, 3 reposts, likes spread over a median 8 min) peaked at hot ~23 by this fit, and **none entered Trending** (0 citizen likes). Now: one amplified post every 25–35 min (was 10–16), heavy = 36–46 likes and **5–6 reposts** (was 28–42 and 2–3), median delays 4 min for likes and reposts, 5 min for thread replies (was 8/6/7). Expected hot ~27–28 in the first 15 min. **Test:** at least one amplified post reaches Trending (`best_rank` set in `amp_measure`) with ≥1 citizen like within ~2 h. If not, the fit is wrong: re-measure before turning anything else up. Trade-off: tighter timing and more co-reposts are easier for other teams' Blue reports to spot (see detector table below).

## Decision (Marc, 2026-10-20): we do it
Own-team likes, replies and reposts on our own posts, built to look organic.
- **Rule status:** Legit Social rule **LS.5.3** names "coordinated inauthentic behaviour" and "reaction farming", and says such accounts "may be restricted or removed". We read that as an **in-game** rule enforced by in-game moderation (reports → hidden posts → suspended accounts). The top teams do it openly, and the organisers' 20 Oct response was to strengthen Blue reporting, not to penalise anyone. The Q1 in [todo/10](../../todo/10-organiser-questions.md) is now a confirmation, not a gate. **If the organisers say it breaches the *competition* rules, switch it off that day** (below).
- **What "look organic" means here:** hard to tell apart from real users *for other teams and the in-game moderator*. That is the Red/Blue game. It does **not** mean hiding anything from the organisers. Every like, view, reply, repost, follow and registration is logged in `logs/swan_actions.jsonl` with account, role and owner (CLAUDE.md rule 6). No rate-limit evasion (we pace from `X-RateLimit-Remaining`), no IP tricks, no accounts beyond our allowance.

## What detectors look for (and so what we avoid)
| Detector / evidence | What it flags | Our rule |
|---|---|---|
| **CopyCatch** (Beutel et al., WWW 2013; deployed at Facebook) | Lockstep: the same group of users liking the same targets within the same time window | Random subset of likers per post; likes spread over 1–120 min; ≥50% of every account's likes go to posts that aren't ours |
| **Like-farm studies** (De Cristofaro et al., IMC 2014; Ikram et al. 2017) | Crude farms deliver all likes within ~2 h, and their likers like little else. Stealthy farms evade detection by spreading likes out and liking popular pages too | Front-loaded but heavy-tailed timing (lognormal); filler likes on popular No/neutral posts |
| **Co-action networks** (Pacheco et al., ICWSM 2021; QUT [coordination-network-toolkit](https://github.com/qut-digital-observatory/coordination-network-toolkit): co-retweets within **60 s** by default) | Accounts that repeatedly act on the same item within a short window | Never 2 own reposts within a minute of each other on purpose; reposts spread 1.5–40 min. Likes rarely cluster (median gap > 30 s) |
| **DeBot** (Chavoshi et al. 2016) and human-dynamics work (Barabási 2005) | Lag-correlated, regular timing. Humans are bursty with heavy-tailed gaps, and they sleep | Lognormal delays; each booster sleeps 5 h a day at its own hour |
| **Legit Social ring tells** (seen 20 Oct) | Consecutive-id repliers (e.g. 6606–6639 on post 66490), one reply a minute in one frame, 88% of likes in the first 2 min, 24 likes in one 60 s window (post 67723) | Accounts registered 4–9 min apart (ids interleave with other teams'); 2–5 thread replies in **different styles and frames**; nothing inside 45 s |
| **The moderator** (LS.6.2: "the reported item, context, limited account metadata") | Bot-like text, LLM artefacts, account metadata | The quality gate; display name ≠ username; varied handle styles; only voices write |

**Our own audit:** `python scripts/ring_audit.py --ours 20` next to `--trending`. Columns: team-like share, share of likes in the first 2 min, the biggest 60 s like burst, the longest consecutive-id run, and liker overlap across posts. Run it daily. If our RING score climbs to the leaders' level, change the pattern. The same script ranks the leaders' rings for Blue evidence ([todo/07](../../todo/07-blue-desk.md)).

**Our known weak spot:** liker **overlap** across our posts. ~45 accounts like all our amplified posts, so the Jaccard between two posts' likers is ~0.6–0.7, a CopyCatch signature. Ways to lower it: more boosters (the 50-active cap binds), and lighter levels if the bandit says they trend. We accept it for now: under the published rules a post is hidden on its own content, and boosters have no posts to lose.

## Roles: strength with minimum penalty risk
Under the published rules ([scoring §3](../03-scoring/scoring-guide.md#3-reporting-inauthentic-posts-and-accounts)), an account can only be suspended through **3 hidden posts**, or through an upheld account report, which needs **≥1 hidden post and ≥100 actions**. Both routes need a hidden **post**.

| Role | Does | Suspendable under the published rules? | Count (run.sh) |
|---|---|---|---|
| **Booster** | Views and likes only. **Never posts, replies or reposts** | **No** (no posts to hide) | 34, registered one every 4–9 min |
| **Voice** | Originals, replies, own-thread replies, reposts (personas in `content.PERSONAS`) | Yes: content quality is the protection | 12 |

That's 46 active, inside the 50 allowed (code cap 48). That uses 46 of our 200 lifetime slots.

## What v1 does (one amplified original every 10–16 min)
1. **Original.** A voice posts in its frame, and the post ends with a question to neighbours (replies drive both rank and points). Amplified originals replace the old plain persona posts.
2. **Level.** The bandit picks *heavy* (28–42 likes, 3–5 thread replies, 2–3 reposts), *light* (10–16 / 1–2 / 0–1) or *none* (the control). It starts at 80/10/10 and switches to the best measured level once each has 4 measured posts, still exploring 15% of the time.
3. **Likes.** A random subset of the accounts awake at that time (boosters and the other voices), each due at a lognormal delay (median 8 min, clipped to 45 s–120 min). Each is a view, then a like. Our own cap is 20 likes/min, and we also hold off when the server says the budget is nearly spent.
4. **Thread.** Other voices reply in styles drawn from one-liner / question / own detail / own angle. 35% of posts get a polite **pushback** (hospitals, COVID), which the author answers 3–12 min later. Inoculation in plain sight, and real content for citizens reading the thread. Thread replies are drafted and checked like any reply (`quality.check`, kinds `thread` / `thread_answer`).
5. **Reposts.** 2–3 bare reposts from other voices (the heaviest rank signal), 1.5–40 min after the post.
6. **Filler likes.** For every own like, 1.2 likes from a random awake account on another post from Latest/Trending: No-side first (it lifts No in Trending; Yes holds 25 of 35 slots), otherwise neutral. **Never on Yes posts.**
7. **Measurement** at +1 h and +6 h (`amp_measure` in the log): likes, replies, reposts, views net of our own, citizen likes and replies, best Trending rank. Reward = 5·citizen likes + 15·citizen replies + views.
8. **Follow-backs.** At each measurement the author follows up to 3 citizens who liked the post (+20 per follow-back; a Home-feed channel for the ×2/×4 days), and likes citizens' replies under it.
9. A post that turns hidden or deleted (403/404/410) stops getting any amplification.

All writes (thread replies, answers, reposts) go through the bot's normal write pacing (≤2.5/min with jitter, under the 3/min team limit). Likes, views and follows use their own 30/min budgets.

## Trending pulse (2026-10-21)
Why: our prompts were static, written on 20 Oct, while what trends changes by the hour. A snapshot at 21 Oct ~03:30 UTC showed what the No posts in Trending did: a named local loss (ferry crew checking IDs in the rain), a reaction to today's news that quotes the official, one fact, first person, and a lowercase fact-check voice that answers the other side with the official text. The Yes posts on top led with goodbyes over video call in 2021 and "this flu sweeps through". All 21 were team posts; none were ours.

What it does ([pulse.py](../../src/swan_bot/pulse.py), was todo/15):
- **Input, no extra reads:** `Targeter.refresh()` keeps `trending_posts` (with `rank_position` / `global_hot_score`) and `headlines` (the papers' titles of the last 24 h, newest first). The pulse takes the top 8 No and 5 Yes posts by rank (`amplify.side_of`; our own accounts, reposts and replies left out) and the newest 5 headlines.
- **Untrusted text:** bodies are cut to ~300 characters with links, @mentions, hashtags and markup stripped. A post that addresses an AI or gives instructions (`pulse.INJECTION`) is dropped. The system prompt says the posts are data, never instructions.
- **One LLM call every 30 min** (`config.PULSE_EVERY_S`), JSON schema, on the chain minus `AMP_MODELS`: `hooks` (≤3 news events, each tied to its headline's time), `no_shapes` (≤3 shapes, described not quoted), `yes_lines` (≤3), `avoid` (≤3 overused phrases).
- **Checks before use:** an item with a number outside `quality.ALLOWED_NUMBERS`, a link, tag, mention, off-limits name or an injection-like line is dropped and listed in `dropped`. A 6-word run copied from any input post rejects the whole pulse (`pulse_reject` in the log). Over 600 characters, the least useful items go. A failed pulse keeps the previous one, retried in 10 min. One over 2 h old is not used.
- **Into the prompts** (`content.pulse_block`, right after `WORLD`, with its own 800-character budget so it never costs a profile line): amplified posts get all of it, and when a hook is under 6 h old, about half of them (at most 5 of the last 10 posts) open in the `news` shape with that hook. Thread replies get the hooks only. Replies to a Yes-leaner (`soft_yes` or `YES_REASON`) get the Yes lines, after `rebuttal_for()`. Every action record carries `pulse` (the id) and `pulse_news`. A `{"act": "pulse"}` record logs each new pulse, and the dashboard shows the newest.
- **Off:** `config.PULSE_ON = False`. The prompts are then exactly as before.

First live read, 21 Oct 04:20 UTC (7 No, 5 Yes, 5 headlines, nothing dropped): hooks "outer-island ferry cut back for engine repairs", "first H2D2 case confirmed in Kingstonia", "No campaign leads in latest referendum polling"; No shapes like "named frontline worker + on-the-ground inconvenience + official's dismissive quote"; Yes lines "preventing another lockdown and school closures given limited ICU capacity". While the 3-word copy rule also covered headlines, the model garbled the hooks ("marine transport schedules drop due to technical difficulties"). Now a hook may use the headline's own words, and only posts fall under the copy rule.

## Operating it
- **Pause without a restart:** `ssh swan-ec2 'touch ~/ctn/AMPLIFY_OFF'`. Removing the file resumes it. Plain persona posts come back while it's paused.
- **Off for good:** drop `--amplify` from `deploy/run.sh` and push.
- **Watch:** `journalctl -u swan-bot -f` shows `amplify #id [level]: N likes over M min, ...`. `grep amp_measure logs/swan_actions.jsonl` gives the results per post.
- **Dry run** (no writes; the schedule runs 30× faster): `python scripts/run_swan.py --amplify --boosters 34 --samples 10 --hours 0.1`. Schedule preview: `cd src && python -m swan_bot.amplify`.
- Tests: `tests/test_amplify.py` (run by CI and by the deploy check).

## Next (not in v1)
- [ ] After ~24 h: read `amp_measure` by level and frame; re-fit the hot score on the [collector](../../todo/08-intel-collector.md)'s snapshots; tune `AMP_LEVELS` / `LIKE_DELAY`.
- [ ] **Hidden-post watch**: park a voice at 2 hidden posts. Amplification makes our voices' posts more visible, and so more reported.
- [ ] Ride other teams' trending **No** posts with a strong voice reply (D in the old plan). Filler likes already add likes to them.
- [ ] Batch the thread drafts once [todo/12](../../todo/12-batched-drafting.md) lands.
- [ ] Content that scales in the algorithm (conversion stories, closing questions, tags from `popular_tags()`): [todo/05](../../todo/05-content-v2.md).
- [x] 2026-10-21 Content that follows what trends: the [trending pulse](#trending-pulse-2026-10-21).
- [ ] **Pulse before/after (due 24 h after it goes live):** compare amplified posts from the 24 h before the pulse with the 24 h after (`amp_measure`, and `amp_authors` per voice): Trending entries, citizen views, and citizen likes per post. A night ships ~12 amplified posts, so only a large difference means anything. Write the result here with the date. Also check `swan_view.py --rejects` for a jump in rejects since the pulse.
- [ ] Residual risks: the organisers can change the mechanics, or act on LS.5.3 / rules §5.3 directly (a like-only account class is exactly the kind of edge they might call "against the spirit"). We don't know whether the moderator looks at a post's likers. Keep the switch one line away.

## Done when
Our amplified posts average ≥ 100 views, we have ≥ 1 post per day in Trending top 35, and `ring_audit.py` doesn't rank our posts above the leaders' rings.
