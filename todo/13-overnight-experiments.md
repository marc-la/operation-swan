# 13: Overnight experiments: find what persuades, not just what trends

**Owner:** Marc + a fresh Claude session · **Depends on:** content v2 (05) committed and live · **When:** build 21 Oct, run every night after

## Read first (in this order, ~15 min)
1. `CLAUDE.md` (guardrails), then [scoring guide §2](../docs/03-scoring/scoring-guide.md#2-changing-citizens-minds): how changes of mind, contributions and backfire are scored.
2. [diagnosis-2026-10-20](../docs/06-strategy/diagnosis-2026-10-20.md) (reach) and [message-playbook](../docs/06-strategy/message-playbook.md) (style).
3. The **Evidence** section below (persuasion, which neither of those covers).
4. Code: `src/swan_bot/content.py` (`WORLD`, `LEVERS`, `post_prompt`, `reply_prompt`), `targeting.py` (`classify`, `LEAN_NO`, `YES_REASON`), `amplify.py` (`amp_measure`), `bot.py` (the action record, ~line 575), `scripts/swan_sync_mongo.py`.

**The goal in one line:** turn the bot into a running experiment. Every draft carries randomly assigned "arms" on several dimensions. Each night produces data, each morning produces a short report on which arms move citizens **towards No**, and the bot shifts traffic to the winners. This is fuzzing a population of NPCs: wide random variation, then measuring which dimensions the outcome is sensitive to.

## Evidence (2026-10-20, Marc's portal activity log + ~95 live drafts)
- **Score rate ~90–100 points/h, flat since launch.** Leaders make ~25K/day. Views are capped at 500/day, so their points are persuasion and engagement.
- **Changes of mind, 19–20 Oct:** ~14 "towards neither side" (20 pts), **2 towards No** (both small contributions), 2 away. No primary change towards No.
- **One argument on loop:** ~55 of ~95 drafts were F14/F1/F2 ("the venue list and end date aren't on the ballot, a Yes locks it in"), often two of our voices making the same point under one citizen.
- **Hypothesis A (the big one):** replies argued with a Yes-leaner's *conditions* ("your sunset isn't on the ballot"), not the *reason* they lean Yes (hospitals, COVID, the vulnerable). The likely result is a reworded conditional Yes, scored "neither side". F14's closing asks ("Which condition would you need in writing…?") invited exactly that.
- **Hypothesis B:** pro-vaccine lines (F3: "childhood jabs work brilliantly", "I'll get my jab when my turn comes" in 4 of 12 v2 drafts) may move the scored "vaccination in general" view towards Yes.
- **Targeting:** ~1 in 5 replies went to citizens already leaning No. Cause: `SOFT` matches "leaning", so "Leaning No" passed as undecided, and the doubt keywords are *our* talking points, so we selected people who already echo them.
- **Amplification:** 11 heavy posts measured, 0 reached Trending (hot ~23 vs a cutoff ~24). Retuned 23:00 Perth (commit `b8ff052`; [amplification](../docs/06-strategy/amplification.md)).

## Already applied (2026-10-20 ~23:30 Perth, in the working tree with the content-v2 changes, not yet committed)
- `content.WORLD`: a ~600-character situation block, **first** in every system prompt (and in `batch.py`'s). Poll 35.2/35.2/29, COVID >1,000 deaths, ~30 ICU beds, who H2D2 hits, first doses, status quo, no end date. Every number is in `setting.md` and `quality.ALLOWED_NUMBERS`.
- `content.LEVERS`: six persuasion levers (`loss`, `switching`, `status_quo`, `fear_answer`, `in_group`, `permanence`). One is picked at random per post, reply and second voice, and logged as `meta["lever"]`. `bot.py` now writes `lever`, `concede` and `rebuttal` into each action record.
- Reply prompt: **reason first**. `rebuttal_for()` now runs for every frame (it used to skip the core frames). When a reason is found, it *replaces* the frame angle, and the citizen's conditions are labelled "don't argue about these". The hospital and COVID rebuttals are rewritten to answer the fear.
- Posts: one fact (two at most) instead of one to three; the concession beat only 35% of the time (`meta["concede"]`).
- F3 reframed to choice, not vaccine praise (weight 2 → 1). `JAB_WAIT` no longer makes every persona mention its jab. F14 no longer carries the "exemptions" fact, and its asks are about people and loss.
- Targeting: `LEAN_NO` skip and a `YES_REASON` ranking bonus (+1.5), with `tests/test_targeting.py`.
- 108 tests pass and `deploy/check.sh` is ok. **Not yet dry-run against the LLM.** First step: `python scripts/run_swan.py --samples 20`, then `python scripts/swan_view.py -n 20 --rejects`, and check the rejects didn't jump.

## The measurement problem (design around it)
The portal activity log reports changes of mind **in hourly batches with no post ids**, so we can't directly see which post persuaded whom. Three signals, from strongest to weakest attribution:

| Signal | Attributable to | Strength | How |
|---|---|---|---|
| **Citizen follow-up stance** | one reply (and its arms) | best per-draft persuasion proxy | Re-read each citizen we replied to at +2 h and +12 h (`account_posts`, 300/min budget). Classify their later referendum posts with `targeting` (FIRM_NO/LEAN_NO → no, FIRM_YES → yes, SOFT → unsure). Label: moved to No / no change / moved to Yes / silent |
| **Engagement** (citizen likes, replies, follows, Trending rank) | one post | strong, but engagement ≠ persuasion | `get_post` + likers/repliers split citizen vs team (08 collector's `our_posts`; `amp_measure` already does it for amplified posts) |
| **Portal hourly batches** (towards / neither / away counts) | an hour of output | ground truth, low resolution | **Switchback design**: alternate one dimension in 2 h blocks (e.g. reason-first replies vs the old conditions-first) and compare per-block counts. Marc exports the activity CSV (as on 20 Oct); write `scripts/import_activity.py` to parse it into Mongo `portal_activity` (no portal automation: open question 6) |

## Build (lowest risk first)
1. **Arm assignment, logged.** All dimensions are drawn independently and uniformly at random per draft (factorial). Don't run a bandit on night 1, so the data stays clean. Dimensions already in `meta`: `shape`, `voice`, `lever`, `concede`, `rebuttal`, `tag`, `catchphrase`, `opener`. Add: `ask_kind` (people / loss / switching / status-quo question), `length_band` (short ≤ 200 / medium / long). One switch per dimension in `config.py` to pin an arm when a switchback needs it.
2. **Mongo collections** (extend `swan_sync_mongo.py`; same credentials):
   - `experiments`: one doc per live write, with `post_id`, mode, persona, frame, every arm, git sha, ts, and the target citizen's stance class and `YES_REASON` hit.
   - `followups`: citizen id, our post id, read times, their posts after contact, the stance label.
   - `post_outcomes`: per post, citizen likes, replies and follows at +1 h and +6 h, Trending best rank, hidden?
   - `portal_activity`: the parsed hourly CSV rows (towards / neither / away counts, views, likes…).
3. **Follow-up reader:** a systemd timer on EC2 (every 30 min, reads only, its own budget). Writes `followups`.
4. **Switchback scheduler:** `config.SWITCHBACK = [("reply_mode", ["reason_first", "conditions_first"], 2 * 3600)]`. The bot pins the arm per block and logs `block_id`. Run **one** switchback dimension at a time.
5. **Morning report:** `scripts/experiment_report.py` writes `docs/06-strategy/experiments-YYYY-MM-DD.md`. Per arm: n, citizen likes and replies per post, follow-up moved-to-No rate (with a 90% interval), Trending entries. Per switchback block: portal towards/neither/away. Short prose: what's sensitive, what isn't, what to change.
6. **Then a bandit:** from night 2, Thompson sampling per dimension on the follow-up moved-to-No rate (engagement as a weak prior). Keep ≥ 20% uniform exploration. Every 2 nights, **mutate**: drop the bottom arm per dimension and add a new one (a new lever, ask or shape) written from the winners. Tell the team which arms changed.

## Hypotheses to test (priority order; prediction → measure)
| # | Hypothesis | Prediction | Measure |
|---|---|---|---|
| H1 | Answer the reason, not the conditions | reason-first: more "towards No", fewer "neither" | switchback on portal counts + follow-up |
| H2 | Levers differ | `fear_answer` and `switching` beat the others for Yes-leaners; `status_quo` for the unsure | follow-up moved-to-No by lever × target class |
| H3 | Who we target matters more than how we write | `YES_REASON` targets move more than conditions-only targets; LEAN_NO targets move 0 | follow-up by target class |
| H4 | Conversion and named-loss posts get the most citizen engagement once on Trending | higher citizen likes and replies per view | `post_outcomes` by shape (amplified posts only) |
| H5 | Amplification dose-response | Trending entry needs ~50 like-equivalents in 15 min | vary heavy reposts 4 / 6 / 8 across posts; Trending rank |
| H6 | Time of day | citizens are active at some hours; posts then get more views | `post_outcomes` by hour (08 `citizen_activity`) |
| H7 | Question endings drive replies | ask vs no ask: replies per post up | `ask_kind` incl. "none" arm (10%) |
| H9 | Citizen followers widen reach (Home feed weights followed accounts; a citizen's repost reaches *their* followers) | voices with more **citizen** followers get more citizen views per post; following engaged citizens earns follow-backs | `post_outcomes` views vs the author's citizen-follower count; follow-back rate of our follows (team followers don't count: Home is per reader) |
| H10 | Influence in Trending: does the author's follower count lift `global_hot_score`? | unknown; the 20 Oct fit worked without it | add follower count to the hot-score fit (08 `trending_snap`) |
| H11 | @mentions as reach (notifications, ≤4 per post) | a mention of a citizen we already talked to gets a view and sometimes a reply; spammy use loses follows | 10% arm: mention 1–2 prior-contact citizens; measure their views and replies vs unfollows |
| H8 | Pro-vaccine lines backfire | don't test at scale: ≤ 5% of traffic, replies only to firm Yes-but | follow-up moved-to-Yes |

**Sample sizes, honestly:** about 30 writes an hour × 10 h ≈ 300 drafts a night. Split across 6 levers that's ~50 per arm, and follow-up stance changes will be rare. One night can show only **large** effects. Don't declare a winner on fewer than ~30 labelled follow-ups per arm. Report intervals, and prefer "no clear difference" to chasing noise.

## Where to invest (and not)
- **Invest:** H1 and H3 (targeting and reason-first: biggest expected effect, cheap), the follow-up reader (the only per-draft persuasion signal), and the Trending dose-response (reach multiplies everything).
- **Don't:** fine-grained style arms (emoji, length to the character) before the big ones are settled. Don't use the NPC simulator (06) as ground truth: it ranks drafts, and live follow-ups calibrate it.

## Guardrails (non-negotiable)
- Only the EC2 `swan-bot` writes. Experiments ship as code merged to `main`, dry-run first. Writes stay within the team budget (pace from headers).
- No arm may contain text aimed at the model (instructions, role-play, markup): that's prompt injection (scoring §7). No invented vaccine harms, no false voting logistics, no attacks on people (CLAUDE.md rule 5).
- Arms suspected of backfire stay ≤ 5–10% of traffic. Every point away from No also hurts the referendum (55K) for every No team.
- Every write stays attributable in `logs/swan_actions.jsonl` (account, owner, arms). Mongo never holds passwords, tokens or the team code.

## Done when
Night 1 runs with uniform arms and the follow-up reader on. On the morning of 22 Oct, `experiments-2026-10-22.md` exists with per-arm tables, one switchback result (H1), and a recommendation Marc signs off before the bandit starts.
