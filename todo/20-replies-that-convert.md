# 20: Replies that convert: changes of mind toward No, not just engagement

**Owner:** Marc + a fresh Claude session · **Depends on:** todo/19 (shipped 2026-10-21, d99bd34) · **Pairs with:** [todo/21](21-reach-every-citizen.md) (who we reply to) · **When:** tonight, 21–22 Oct

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
