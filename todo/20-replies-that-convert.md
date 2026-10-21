# 20: Replies that convert: changes of mind toward No, not just engagement

**Owner:** Marc + a fresh Claude session · **Depends on:** todo/19 (shipped 2026-10-21, d99bd34) · **Pairs with:** [todo/21](21-reach-every-citizen.md) (who we reply to) · **When:** tonight, 21–22 Oct

## Status (2026-10-21 ~15:20 UTC): built and live; the 24 h read-out is due ~22 Oct 15:00 UTC
| Item | Commit | Live since (UTC) |
|---|---|---|
| G9 gate: code fixes (trim, drop the sentence with a bad number or advocacy, drop a shared opening), up to 3 repairs with the exact problem, model switch after 2 fails, cap in characters | 413be20 | 21 Oct 14:29 |
| G8 failed drafts requeued (`targeter.requeue`) or logged `lost(reason)`; G7 reply-backs every 60 s, 10 jobs, mentions, resolve after queueing, 3 turns per citizen per 30 min, depth < 8 | 1b80f82 | ~14:45 |
| Step 1: followup counts only posts we wrote (test); Trending read via `feeds.read` | b05a412, 1bf2a04 | ~14:50 |
| Step 5: fear_answer cut, in_group/permanence ×2, F2/F3 at 0.25, no vaccine advocacy (gate + prompt rule + `get_jab` theme off) | 00ca381 | ~14:50 |
| Steps 2–4: the light read (JSON stance/doubt/frame/reply or skip), `mirror_concede` vs `current` in turn, reply-backs in the same style; exemptions note no longer scripts a sentence | 693ebb7 | 14:56 |
| Steps 7–8: second voice fast (1–4 min) vs slow (10–30 min); one booster like on alternate replies; todo/23 `content.group_style` hook | 0926de7 | 15:00 |
| Step 1: `scripts/conversion_report.py`; the read skips only hostile or plainly unrelated posts | 0c7edc4 | ~15:20 |

Baseline (24 h to 21 Oct 15:00 UTC, the box's logs): 255 citizen-facing writes; portal towards 1.6, away 2.4, neither 9.0 per 100 writes. Before G9, Kimi needed 2.8 calls per accepted reply; 74 of the 92 citizen-facing drafts rejected live on 21 Oct pass the new gate with no extra call (offline replay).

**Read-out (step 9 "Measure"):** on the box, `python scripts/conversion_report.py --split 2026-10-21T15:00 --hours 24 --out docs/06-strategy/conversion-2026-10-22.md`, then write the result into the message-playbook and the direction doc, and pin the winning style in `config.REPLY_STYLES` (Marc's call). Not done yet: the read-out itself, and calibrating the read against the regex class (the report has the cross-table).

## Read first
`CLAUDE.md`, [direction-2026-10-21](../docs/06-strategy/direction-2026-10-21.md) (why this is the top lever), [research C: our data](../docs/06-strategy/research-2026-10-21/C-ourdata.md) §5, [research D: other teams](../docs/06-strategy/research-2026-10-21/D-competitors.md) §8, [research A: rules](../docs/06-strategy/research-2026-10-21/A-rules.md) M4–M6, [message-playbook](../docs/06-strategy/message-playbook.md), [frames](../docs/06-strategy/frames-and-messengers.md). Code: `src/swan_bot/content.py` (reply prompts, frames, levers, reply modes), `quality.py` (the gate, length checks, `repair_note`), `bot.py` (reply_back, second voice), `followup.py`.

## Why (measured 2026-10-21)
- **Persuasion is 2.7% of our non-poll points** (121 of 4,555). Portal since launch: **0 primary changes toward No**, 6 contributions toward, 8 away, and 37 "towards neither side, **on vaccination**". The leaders' ~1,040 points/h on Day 1 can only come from changes of mind.
- **What citizens answered** (another team's replies that got a citizen like or reply, n=5, weak signal): they mirror the citizen's own detail, concede it, add one personal anchor or checkable fact, then state the position plainly. Median ~260 characters, and **none ended with a question** (29 of 73 unanswered ones did).
- **Our own reply rates** (share of citizen-facing writes that got a citizen reply; cells under 40 writes are only suggestive):
  - better: `conditions_first` 18% and `reason_first` 16% reply modes; `in_group` 18% and `permanence` 16% levers; 120–280 characters 12%; personas priya, mere, dan ~15%;
  - worse: frames **F3 provax_antipass 5.5%** and **F2 no_end 2.5%**; lever **fear_answer 0%** (n=21); **under 120 characters 6.5%**; target class `unsure` 0% (n=12).
- **Possible backfire:** the direction of a change is judged relative to the referendum. Lines that praise vaccination ("getting my jab, voting No") may move a citizen's *vaccination in general* view pro-vaccine, which scores neutral or **away (−80)**. That would fit our 37 "neither, on vaccination" events. Organiser question Q3 is open.
- **Kimi K2.5 needs 2.8 calls per accepted reply:** 47 of its 64 rejects were length checks, and ~20 reply jobs a day fail both tries, so those citizens are lost ([research E](../docs/06-strategy/research-2026-10-21/E-throughput.md) §a.3).

## Do, in order
1. **Measurement first:**
   - Every reply record carries `style`, `frame`, `lever`, `reply_mode`, length and model (most already do).
   - Add a small report (`scripts/` or `analysis.py`) that joins the portal's hourly events to the writes of the 0–3 h before, plus per-write citizen outcomes via the shared `is_citizen` (todo/19). It's weak inference, so use it to compare arms, not to prove effects.
   - Fix the **followup.py bug:** `run()` puts posts we only *liked* into `our_ids` (like rows carry `live` and `post_id`), which inflates `replied_to_us` and fills the trending records with other teams' posts.
2. **The light read, inside the drafting call (no extra LLM call, no separate sentiment system):**
   - The reply prompt returns JSON: `{"stance": firm_yes|yes_but|unsure|unclear|lean_no|firm_no, "doubt": "<their concern in ≤10 words>", "frame": "<one of content.FRAMES>", "reply": "..."}`, or `{"skip": "<reason>"}` for posts that are hostile or not really about the referendum.
   - Validate the JSON, fall back to the regex class, and log every field.
   - **The stance picks the approach:**
     - yes_but / unsure: answer their condition and make the No case on it;
     - firm_yes: concede first, never attack (todo/21's arm);
     - lean_no / firm_no: affirm in their own terms, plus one reason that matters on the day.
   - It replaces the regex's job of choosing a frame (todo/21: no frame match no longer means skip). Compare the read with the regex class for a day to calibrate both.
3. **Conversation turns:** a citizen who answers us gets our next turn within minutes, in the same style (`REPLY_BACK` is on: check the reply-back path picks citizen replies to us before anything else, author's own voice first), up to 3 turns per session, and never past a thread depth of 8. Citizens who engaged get priority on their next post (todo/21's engaged bonus).
4. **Reply style arm** (A/B: alternate replies, logged as `style="mirror_concede"` against the current style):
   1. mirror one concrete detail the citizen wrote;
   2. concede what's fair in it;
   3. one anchor: a personal detail of the persona, or one setting fact from `content/facts.toml`;
   4. state No plainly.
   - 150–280 characters. No closing question (the current prompt asks for one; drop it in this arm).
   - Same quality gate and content rules; no text aimed at the model (scoring §7).
5. **Frames and levers:**
   - Cut fear_answer.
   - Down-weight F2 no_end and F3 provax_antipass (keep them available, at a fraction of the current weight).
   - Raise the weight of the conditions_first / reason_first modes and the in_group / permanence levers.
   - **Until Q3 is answered, avoid praising vaccination itself.** "Vaccinated" as part of a persona's identity is fine; advocacy ("get your jab", "I'd tell anyone to get it") is not. Log the change with the date in config.
6. **Fix Kimi's length rejects** (`quality.py` / the length line in the `content.py` prompt):
   - give the limit in characters in the prompt;
   - if a draft is too long, trim it at a sentence boundary when what's left still passes the gate, instead of rejecting it and drafting again.
   Target: ≤1.5 calls per accepted Kimi reply.
7. **Second voice inside the session:** citizen sessions last 1–5 min, and the contribution pool only counts posts read in the session where the change happens. Test `SECOND_VOICE_S` at (1, 4) min against today's (10, 30) min, alternating.
8. **One own like on our reply to a citizen** (never tried: n=0). A/B on alternate replies, logged with role and owner. Measure whether citizen likes and replies rise. Drop it if not.
9. **Dry-run, tests, ship via `main`.** Coordinate with the todo/21 session: both touch `targeting.py`, `bot.py` and `config.py` (`git diff` first, small commits).

## Measure (24 h after shipping; compare with the 24 h before)
- Portal: "towards your side" contributions and primary changes per 100 citizen-facing writes; "away" and "neither, on vaccination" per 100.
- Per arm: citizen reply rate, citizen likes per write, follows.
- Kimi calls per accepted reply, and reply jobs lost to double rejects.
- Write the results with the date into [message-playbook](../docs/06-strategy/message-playbook.md) (style) and [direction-2026-10-21](../docs/06-strategy/direction-2026-10-21.md) (the outcome against the plan).

## Guardrails
- Content rules (CLAUDE.md 5): no prompt injection, no false voting logistics, no harassment.
- The quality gate stays on.
- No new kinds of writes. The own-like test uses the like budget and is logged per account.
- Watch the hidden-post alerts.

## Done when
- Both arms run for ≥24 h with results written down.
- Kimi is at ≤1.5 calls per accepted reply.
- The followup.py bug is fixed with a test.
- The winning style is the default in config.

## Coordination: todo/20 and todo/21 run at the same time (2026-10-22)
- **Work in your own git worktree on a branch** (`git worktree add ../ctn-20 -b todo-20`, likewise `ctn-21`), not in the shared `/home/marc/ctn` tree. Merge to `main` in small commits: rebase on `main`, run the tests, push. A push to `main` deploys to swan-ec2 in ~2 min, so push only green, dry-run-checked commits.
- **File ownership:**

  | Owner | Files and functions |
  |---|---|
  | **21** | `targeting.py` (classify, classify_target, undecided, next_target, candidates, refresh logging) and in `bot.py`: `citizen_reply` plus the `contacted` / cooldown logic |
  | **20** | `content.py`, `quality.py`, `followup.py`, the reply-drafting path in `bot.py` (draft, parse, reply-back, second voice), and new analysis scripts |
  | **Shared: `config.py`** | each session adds its own block with a header comment (`# ---- todo/21 targeting ----` / `# ---- todo/20 conversion ----`), and never edits the other's lines |

- **Interface (agree on it; don't redesign it):**
  - The job dict from 21 carries `target_class` (the regex class), `priority`, and `frame` = a frame key, or **`None` when no regex frame matched**. 20's drafting call must accept `frame=None` (the light read then picks one) and any `target_class`, including `lean_no` and `firm_yes`.
  - 21 sets `job["arm"] = "firm_yes"` for the firm-Yes arm; 20 maps that to the concede-first style.
  - 20's light read logs `read_stance`, `read_doubt`, `read_frame` on the action record, next to 21's `target_class`, so the two can be compared.
- **Acceptance checks (the orchestrating session runs these on swan-ec2 after both ship):**
  - **Speed:** median ≤ 3 min from a citizen's post to our reply (reply records against `get_post(...).created_at`).
  - **Volume:** ≥ 80% of citizen Latest items answered or skipped for a logged hard reason; citizen-facing writes ≥ 2× the 6 h before todo/21 ships (peak hours compared with peak hours).
  - **Conversion:** both arms running and logged (`style`, `arm`, `read_*`); Kimi ≤ 1.5 calls per accepted reply; no rise in "away" events per 100 writes. The real conversion read-out comes at +24 h.

## Gap screen (2026-10-21 ~14:30 UTC: code at 5211060 plus the live log since todo/19 shipped)
Every point where a citizen item can be lost between "a citizen writes" and "we reply and measure it". **Owner** says which session fixes it. **Done means each one is fixed and covered by the skip/loss log (G12).**

| # | Gap | Evidence | Fix | Owner |
|---|---|---|---|---|
| G1 | **The feed budget starves Latest paging** | Every refresh since 14:00 read **1 page**, and 3 of 7 hit `latest_gap`: the 10/min team feed budget is ≤ 3 by the time the bot pages. Consumers: bot Latest + Trending every 2 min, `swan-blue` Latest + Trending, followup Trending, swan_watch, **and dev dry runs reading live feeds** | One Latest reader: the bot writes its pages to `data/latest_snapshot.json`; swan-blue reads that instead of the feed. Bot Trending every 3rd refresh. Dev dry runs use a cached fixture, not live feeds. Log `rl.remaining` per consumer | 21 (bot side), Blue session (its side) |
| G2 | **Unread pages are lost for good** | `_latest` sets `latest_seen` to the newest post even when it stopped early, so the band between is never read | Keep a backfill cursor: the next refresh resumes where the last one stopped before reading new posts | 21 |
| G3 | **A restart loses the queue and the read position** | `latest_seen` and `candidates` live only in memory; 5 deploys between 13:40 and 14:14 UTC; the first refresh reads 1 page | Persist `latest_seen`, the backfill cursor and `candidates` in `swan_state.json`; on start, page back to the saved position | 21 |
| G4 | **Pre-filters drop citizens** | `_consider`: needs referendum keywords in the body (Latest gets no context), a frame regex match, age ≤ 36 h. `targeter.is_citizen` calls `get_account`; on RateLimited it returns `{}`, the item counts as not a citizen and is never seen again | Parent context for replies (item 5); no-frame posts kept (item 1); citizen check by `config.is_citizen` (id rule, no read); keep anything we couldn't judge for retry | 21 |
| G5 | **One firm phrase skips a citizen forever** | `undecided()` caches "firm" per author for the life of the process, from any of their last 15 posts | Priority, not skip (the design above), worked out per post | 21 |
| G6 | 72 h per-author cooldown | Repeat posters skipped | Per-post and per-session limits (the design above) | 21 |
| G7 | **Reply-backs are slow and leaky** | `reply_back_jobs` runs every **300 s**, max **3 jobs** per poll; `kind == "mention"` notifications ignored; the notification is resolved in `finally` even when `get_post` failed (lost); uses the created_at citizen check | Poll every ~60 s, ~10 jobs; handle mentions of our voices; resolve only after the job is queued; `config.is_citizen` | 20 |
| G8 | **A failed draft loses the citizen** | Since 10:00 UTC: 22 reply targets rejected, **10 never answered**. Main path: `if not text: continue` drops replies (only reply-backs retry). All models parked (backend None) also drops the target | Put the candidate back with backoff until it ages out; never drop on backend None. 21 exposes `targeter.requeue(cand, why)` | 20 (drafting path) + 21 (requeue API) |
| G9 | **The quality gate rejects good Kimi replies** | 13:40–14:00 UTC: 25 reply rejects vs 2 replies sent. Reasons: `length_306…382` (cap 290), `copied_fact`, `unapproved_num`, `near_duplicate` | Length: trim at a sentence boundary, or state the cap in characters in the prompt. Review the `copied_fact` / `unapproved_num` rules against `facts.toml` (too strict?). Target ≤ 1.5 calls per accepted reply, ≤ 10% of reply targets lost at the gate | 20 (**first**) |
| G10 | Citizens added mid-game | `is_citizen` is id ≤ 2343 | Item 6 above | 21 |
| G11 | Deep threads | Thread depth isn't checked; citizens rarely reply past 8 | Skip with reason `deep_thread` | 21 |
| G12 | **No proof of coverage** | No skip or loss reasons are logged | Every citizen item seen ends as `answered`, `skipped(reason)` or `lost(reason)` in the log; a per-hour funnel line in the refresh record; the dashboard shows it | 21 (targeting) + 20 (drafting losses) |

Not a gap: at Sydney night (01:00) Latest held 0–2 citizen items per refresh. Low supply is real, and the funnel line will show it.

## G9 in full: no citizen lost to the gate (Marc, 2026-10-22: "we cannot afford a rejection")
A rejected draft may never cost us the citizen. Today: one repair try, then the target is dropped. The new pipeline, in order:
1. **Split the checks:**
   - **Hard** (rules or facts): endorses Yes, prompt-injection-like text, links or @mentions, hate or harassment, false voting logistics, a number not in `facts.toml`.
   - **Soft** (style): length, `near_duplicate`, `same_opening`, `copied_fact` wording, consoling or generic.
2. **Fix soft failures in code, with no LLM call:**
   - too long → cut at the last sentence boundary under the cap, if the rest still states No;
   - too short → allowed if ≥ 60 characters and it states No;
   - same opening → drop the first clause.
   - `near_duplicate` and `copied_fact` go to step 3.
3. **Repair with feedback** (the existing `repair_note`): give the model the exact problem and the failed text, and ask for the corrected version. Up to **3 repairs**, switching model after the second (Kimi → GLM-5 → the next in the chain).
4. **Hard failures:** repair as in step 3. A number problem can also be fixed in code: drop the sentence that holds the number, if the rest still stands.
5. **Last resort, never dropped:** put the target back (G8) with a note, and draft it again on the next slot with the strongest model free. It is lost only when it ages out, and it's logged as `lost(gate)`.
6. **Measure:** reply targets lost at the gate ≤ **5%** (today ~45%); calls per accepted reply ≤ 1.5; log the repair count and which fix worked on each write.
7. Loosen any soft check that fails more than 20% of drafts: re-check its threshold against what citizens actually answered (D §8: engaged replies ran ~260 characters).

Hard checks stay hard: they protect our voices from hidden posts and our score from backfire.
