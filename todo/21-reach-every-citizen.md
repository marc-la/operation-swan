# 21: Reach every citizen: a loose first pass, priority instead of filters

**Owner:** Marc + a fresh Claude session · **Depends on:** todo/19 (shipped, d99bd34) · **When:** 22 Oct · **Pairs with:** [todo/20](20-replies-that-convert.md) (what we say). This item covers who we say it to.

## Read first
`CLAUDE.md`, [direction-2026-10-21](../docs/06-strategy/direction-2026-10-21.md) (the plan), [research B](../docs/06-strategy/research-2026-10-21/B-platform.md) and [research E](../docs/06-strategy/research-2026-10-21/E-throughput.md), `src/swan_bot/targeting.py` (`classify`, `classify_target`, `undecided`, `next_target`), `bot.py` (`citizen_reply`, the `contacted` cooldown), `config.py` (`CONTACT_COOLDOWN_S`, `FRESH_*`).

## Why: citizens are scarce, and our filters still throw them away
- **Supply:** ~25 citizen posts and ~75 citizen replies an hour across the whole platform (~98% of Latest is team bots). Every one of them notifies its author when we reply. A citizen has a session about every 2 days, lasting 1–5 min.
- **Budget:** writes are 3/min; at full coverage, replies to citizens use ~0.8/min. A wrong "yes" (replying to someone hard to move) costs one spare write. A wrong "no" costs a citizen we may not reach again for days. **So favour reaching everyone over picking the best.**
- **What still drops citizens after todo/19:**
  1. `classify()` returns `(None, None)`, i.e. skip, when no frame regex matches. A citizen post about the referendum in words outside our keyword lists is never answered.
  2. `classify_target` → `next_target` skips `lean_no`, `firm_yes` and `off_topic`. `undecided(author)` drops authors whose history looks decided.
  3. **The 72 h cooldown is per author** (`CONTACT_COOLDOWN_S`). A citizen we answered on Monday and who posts again on Wednesday is skipped. The other teams reply to every citizen post. The rules allow moving the same citizen again in a later session (the "harder to move again" limit is per session: [research A](../docs/06-strategy/research-2026-10-21/A-rules.md) M6).

## The design
**Hard skips only** (cheap code, no LLM):
- not a citizen (`config.is_citizen`);
- a repost, or our own post;
- a post we have already replied to;
- off the referendum topic entirely (`ON_TOPIC`, kept broad);
- `HOSTILE` / abusive;
- a thread deeper than 8 (citizens stop replying past that).

**Everyone else is a candidate.** The regex read sets **priority**, not eligibility:

| Read (regex prior) | Priority | Why |
|---|---|---|
| conditions / yes-but / unsure / yes_reason | highest | the people we can move toward No |
| unclear (on topic, no stance) | high | unknown, often movable |
| lean_no / firm_no | low | engagement (~3 points per write) and possible lean→firm moves; no backfire |
| firm_yes | lowest, **arm** | backfire risk (−80); test a concede-first reply now at ×1, measured by "away" events, before the ×2/×4 days |

On top: a freshness bonus (posts under 10 min, already in), and an **engaged bonus** for citizens who answered or liked us before (they answer again).

**No frame match → no skip.** The drafting call picks a frame from the list (todo/20, the light read).

**Cooldown per post and per session, not per author:**
- Drop the 72 h author cooldown.
- Keep: one thread per citizen post.
- Add: at most 2 of our voices per citizen per ~30 min (one session).
- Keep `CONTACT_COOLDOWN_S` only as the session cap.

**Citizen replies are targets too** (a reply to them notifies them). Check that Latest items with `reply_to_post_id` become candidates, with the thread context passed to the draft.

**Log every skip with its reason** (a todo/19 leftover): `not_citizen`, `off_topic`, `hostile`, `replied`, `session_cap`, `no_voice`, `deep_thread`. Per hour, that gives the share of citizen items we answer.

## Do
1. Change `next_target` / `classify` / `classify_target` to the table above. Keep the regex classes as `target_class` for logging and priority.
2. Swap the per-author cooldown for the per-post and per-session rules. Keep `state["contacted"]` for the session cap and for the engaged bonus.
3. Turn the firm-Yes arm on with a flag (`config.FIRM_YES_ARM`, default **on** at ×1, a few % of writes). It uses todo/20's concede-first style.
4. Add the skip log and an hourly coverage line to the refresh record: citizen items seen, answered, skipped by reason.
5. Tests: no-frame posts are kept; a repeat author is answered on a new post; the session cap holds; firm Yes only under the flag. Dry-run, then ship via `main`.

## Measure (24 h before vs after)
- Coverage: share of citizen Latest items we answer (target ≥ 80% at peak).
- Citizen-facing writes/h (target 40–55 at peak).
- Per target class: reply rate, citizen likes, and the portal's "towards / away / neither" per 100 writes.
- **Stop rule:** if the firm-Yes arm or lean-No replies raise "away" events per 100 writes over the baseline, switch that class off.

## Guardrails
- One writer, pacing from the rate-limit headers, the quality gate on.
- No mentions: grey; organiser question not asked.
- Watch the hidden-post alerts: more replies means more content on show.

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
