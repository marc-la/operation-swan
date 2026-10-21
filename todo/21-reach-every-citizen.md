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

**Citizen replies need their parent post** (checked 2026-10-22):
- `refresh()` calls `_consider(p, "latest")` with **no context**. A citizen reply from Latest therefore passes only if its own body has referendum keywords and a frame match, so short replies ("exactly, that's my worry too") are dropped.
- For each citizen item with `reply_to_post_id`, read the parent (`get_post`, 1 cheap read) and pass its first ~200 characters as `context`, as the thread path already does. Check thread depth (≤ 8).
- Replies are ~75 of the ~100 citizen items an hour, so this is most of the volume.
- Citizen replies **to us** come through notifications (the reply-back path). Check that path also uses the same loose first pass.

**Citizens added mid-game** (the organisers said more NPCs may be added; [overview](../docs/01-competition/overview.md), [platform-mechanics](../docs/06-strategy/platform-mechanics.md)):
- `config.is_citizen` is `12 ≤ id ≤ 2343`, so a new citizen gets a high id and is treated as a team bot: never answered, never counted.
- `get_account` has no field that tells NPCs from team accounts (checked: `username`, `display_name`, `avatar_url`, `verified`, `private`, `created_at` only).
- **Do:**
  1. Add `config.EXTRA_CITIZEN_RANGES = []` (id ranges) and make `is_citizen` honour it.
  2. Write a read-only hourly detector (`scripts/`, run by `swan-watch`): walk `accounts()` from the last id seen. Flag runs of ≥ 20 consecutive ids created at a steady seeding pace that contain none of our accounts. The original 2,331 citizens were seeded at ~8/min over ~5 h; team registrations interleave between teams.
  3. Alert, then a human confirms (ideally against a Discord announcement) and adds the range.
- Never auto-add: a wrong range sends our replies to bots and pollutes every metric.

**Log every skip with its reason** (a todo/19 leftover): `not_citizen`, `off_topic`, `hostile`, `replied`, `session_cap`, `no_voice`, `deep_thread`. Per hour, that gives the share of citizen items we answer.

## Do
1. Change `next_target` / `classify` / `classify_target` to the table above. Keep the regex classes as `target_class` for logging and priority.
2. Swap the per-author cooldown for the per-post and per-session rules. Keep `state["contacted"]` for the session cap and for the engaged bonus.
3. Turn the firm-Yes arm on with a flag (`config.FIRM_YES_ARM`, default **on** at ×1, a few % of writes). It uses todo/20's concede-first style.
4. Add the skip log and an hourly coverage line to the refresh record: citizen items seen, answered, skipped by reason.
5. Parent context for citizen replies from Latest, and the reply-back path on the same loose first pass.
6. New-citizen detection: `EXTRA_CITIZEN_RANGES` plus the detector and its alert (human confirms).
7. Tests: no-frame posts are kept; a repeat author is answered on a new post; the session cap holds; firm Yes only under the flag. Dry-run, then ship via `main`.

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
