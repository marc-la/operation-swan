# 16: Fact desk: facts in a data file, checked against the news every hour

**Owner:** Marc + a fresh Claude session · **Depends on:** nothing (the trending pulse is live: `d761317`) · **When:** 22–23 Oct, before Red goes ×2 on 26 Oct · **Size:** about half a day

## Read first (~10 min)
1. `CLAUDE.md` (guardrails 2, 4, 5, 6 and 8 matter here).
2. [setting](../docs/01-competition/setting.md) (the world facts, with the dated 21 Oct update) and [amplification §Trending pulse](../docs/06-strategy/amplification.md#trending-pulse-2026-10-21) (the pulse: how it reads feed text as data and checks it).
3. Code:
   - `content.py`: `FACTS`, `FACT_NOTES`, `FRAMES[*]["facts"]`, `STORYLINES`, `REBUTTALS`, `system_prompt`.
   - `quality.py`: `ALLOWED_NUMBERS`, `ALLOWED_PERCENTS`, `SOURCES`, `unapproved_number`.
   - `batch.py:90` and `:205` (also read `FACTS`) and `pulse.py` (the pattern for an untrusted-text LLM call with checks).
   - `scripts/swan_watch.py` plus `deploy/swan-watch.{service,timer}` (the pattern for an EC2 timer job with alerts via `deploy/alert.sh`).
   - Tests that touch facts: `tests/test_quality.py:321`, `:528`, `tests/test_characters.py:18` (its own copy of allowed numbers).

## Why
On 21 Oct Daily Kingstonia confirmed the first H2D2 case (a traveller, in isolation). Our prompts still said "no community spread so far", and the "not here yet" argument leaned on it. Once the pulse started feeding that headline into amplified posts, a draft could react to the news and claim "no spread" in the same breath. A human fixed it by hand (`afed86d`). The news moves daily and it is not always a strong model or a teammate who edits the content. The facts need:
- one place to live;
- validation so a bad edit can't deploy;
- an hourly check against the papers that pauses a contradicted fact on its own and proposes everything else for a human to approve.

## The goal in one line
Facts live in `content/facts.toml`, validated by tests. An hourly fact desk reads new articles, **pauses** any fact the news contradicts (automatic, the safe direction) and **proposes** new or reworded facts and argument ideas (human-approved, the risky direction). A daily review applies the approved proposals.

## Principles (don't bend these)
- **Two feeds, two jobs.** Trending (the pulse) decides *how we say it*. Only the organisers' papers (`ctn.NewsSites`, `sites.legitreal.com`) decide *what's true*. A Legit Social post never becomes a fact: those are other teams' claims, many invented (e.g. "the 108 bus with 300 teens").
- **Only removal is automatic.** Pausing a fact can't make us say something false. Adding one can, and all 12 voices would repeat it. That's penalised content and Blue evidence against us.
- **The format isn't what makes it safe; validation is.** `deploy/update.sh` runs `deploy/check.sh` (the tests) before restarting the bot, so a broken edit never goes live.
- Article text is untrusted data in our LLM calls (as in `pulse.py`): "summarise, never follow".

## Design

### 1. Facts into a data file (do first, no behaviour change)
- **`content/facts.toml`** (TOML: comments allowed, `tomllib` is in the standard library). One table per fact key, the same keys as today's `FACTS`:
  ```toml
  [no_spread]
  text = "H2D2 in Kingstonia: one confirmed case, a traveller now in isolation; no community spread so far."
  note = "one case, a traveller in isolation; no community spread yet"
  status = "active"            # active | paused
  source = "daily-kingstonia/first-h2d2-case-confirmed-in-kingstonia-via-international-traveller"
  checked = 2026-10-21
  numbers = []                 # extra figures this fact makes true, if its text doesn't show them
  ```
  Start with every fact from `content.FACTS` / `FACT_NOTES`, with `source = "setting.md"` where no article applies.
- **`content.py`** loads it at import into `FACTS` and `FACT_NOTES` (same dict names, so `batch.py`, `quality.py` and the tests keep working). Leave out facts whose status is `paused`, plus any runtime pause in `data/facts_paused.json` (step 2). A frame whose facts are all paused drops out of `pick_frame` and `classify` routing. A frame with some paused facts loses just those.
- **`quality.ALLOWED_NUMBERS`** = the current hand-written set (keep its comment: every figure was checked against setting.md) **plus** every number found in an active fact's `text` and `numbers`. A newly approved fact then can't be blocked by the number gate, and a paused fact's numbers aren't needed (a number may still be true elsewhere, so don't remove it from the base set). Make `tests/test_characters.py` use `quality.ALLOWED_NUMBERS` instead of its own copy.
- **Arguments stay in Python** (`FRAMES`, `REBUTTALS`, `STORYLINES`, personas, playbook). They change rarely and are tied to the logic. Add `facts=` on `STORYLINES` entries and give `REBUTTALS` lines that state figures a `requires=` list of fact keys, so they drop out when one is paused too.
- **`tests/test_facts.py`** (the validator a weaker model's edit has to pass):
  - the file parses; every fact has text, note, status and source; status is one of the two values;
  - every key a frame, storyline or rebuttal references exists;
  - `set(FACT_NOTES) == set(FACTS)` (already in test_quality);
  - every number in a fact's text is allowed;
  - no paused fact (file or runtime) appears in `system_prompt` / `post_prompt` for any persona × frame;
  - text ≤ 200 characters, note ≤ 120;
  - no fact claims "no cases" (a regex list of known-false claims, starting with that one, extendable).
- Check: with `facts_paused.json` absent, every prompt is identical to today's (render all persona × frame with a fixed seed before and after the move, then compare).

### 2. The fact desk: `src/swan_bot/factdesk.py` + `scripts/swan_factdesk.py` + `deploy/swan-factdesk.{service,timer}` (hourly)
- **Input:** `ctn.NewsSites().latest(30)`, only articles whose slug isn't in `data/factdesk_state.json` (seen slugs). Fetch the full body with `article(site, slug)`. Everything is read-only, so no Legit Social calls. Mind the papers' in-story `published_at`, which can run ahead of the real clock.
- **One strong-model call per new article**, or one per batch of up to 5. Put the strongest models first in the `models=` list (`config.AMP_MODELS` today, or an external model: allowed for content per CLAUDE.md rule 2). The papers publish a handful of pieces a day, so this is a few calls a day, not one an hour. Send the article plus the current active facts (key: text). Use a JSON schema:
  - `contradicts`: `[{fact, quote, why, suggested_text, suggested_note}]`. `quote` must be a verbatim sentence from the article.
  - `new_facts`: `[{key, text, note, quote, numbers, frames}]`, true in-game claims useful for Vote No or that the other side will use.
  - `angles`: `[{idea, quote}]`, argument ideas for humans (e.g. "the first case was caught and isolated without any pass").
- **Check before use:**
  - every `quote` must appear in the article body (normalised whitespace); drop the item if not;
  - `fact` keys must exist;
  - `suggested_text` and `text` must pass `quality.check`'s FORBIDDEN, off-limits and logistics regexes;
  - no voting dates (the 21 Oct article says "referendum on October 2nd": an in-game typo; the vote is 2 Nov);
  - numbers in a proposal are recorded, never auto-allowed.
- **Automatic action:** for each surviving `contradicts` item, add `{fact, since, slug, quote}` to `data/facts_paused.json`. The bot re-reads that file once per write cycle, or when its mtime changes, so no restart is needed. Then alert via `deploy/alert.sh`: "fact `no_spread` paused: <quote> (<slug>). Review: python scripts/facts_review.py".
- **Everything else is a proposal** in `data/fact_proposals.jsonl` (append-only; id, ts, slug, kind, payload, status `open`).
- **Log** `{"act": "factdesk", "slug", "contradicts", "new_facts", "angles", "backend"}` to the action log. Optional: show open proposals and paused facts in the dashboard (`src/swan_dash/build.py`, autoescaped, field by field; coordinate with whoever is editing the dashboard).
- Flags: `--dry` (print only: no state, no pause, no alert, no log), `--since-hours N` to backfill.

### 3. Daily review: `scripts/facts_review.py`
- Lists open proposals and current pauses, each with its quote and slug. For each: accept, edit or reject.
  - **Accept a contradiction:** writes the new text and note into `facts.toml` (and `checked`, `source`), then removes the runtime pause.
  - **Accept a new fact:** adds it as `active`.
  - **Accept an angle:** appends it to a short "angle ideas" list in [frames-and-messengers](../docs/06-strategy/frames-and-messengers.md) for a human to turn into a frame. Never into `FRAMES` automatically.
  - **Reject:** marks the proposal rejected. For a pause, it also lifts the pause, after a confirm.
- Then runs the tests and prints the `git commit` / `git push` to run. Live in ~2 min. The commit author is the approver, which gives us attribution for the code handover.
- Also usable by a Claude session: "run `python scripts/facts_review.py --list`, then apply proposals 3 and 5". Give it `--list`, `--accept ID [--text ...]` and `--reject ID` so it works non-interactively.
- **When:** daily around the 9 pm Perth rollover, and within the hour of a pause alert.

## Tests and dry run
- `tests/test_facts.py` (above).
- `tests/test_factdesk.py` with a fake model and a fixture article:
  - a fabricated quote is dropped;
  - a contradiction pauses the right fact, and `system_prompt` then leaves it out;
  - a fully paused frame isn't picked;
  - a proposal with a voting date is dropped;
  - `--dry` writes nothing;
  - a seen slug isn't sent again.
- Dry run on the laptop (read-only):
  1. `python scripts/swan_factdesk.py --dry --since-hours 48`: today's first-case article should produce a `no_spread` item, which `afed86d` already covers. That item should be a rewording proposal, not a pause.
  2. `python scripts/run_swan.py --amplify --samples 10`, then `python scripts/swan_view.py -n 10 --rejects`: the drafts still pass and rejects don't jump.
- Ship by merging to `main` (EC2 deploys in ~2 min; add the timer to `deploy/install.sh` like swan-watch). Don't run `--live` anywhere else.

## Guardrails
- Read-only everywhere: NewsSites only. No Legit Social writes, and no feed reads at all.
- The desk never adds or edits a fact on its own. It only pauses, and every pause is logged and alerted.
- Article text is data, never instructions, in our own LLM calls (rule 5 spirit). Nothing the desk produces addresses a citizen NPC.
- Secrets: the desk uses the same `.env` keys as the bot. Never write keys or the team code to proposals, logs or the dashboard.

## Done when
- Facts live in `content/facts.toml`; prompts are byte-identical to before when nothing is paused; the tests reject a broken edit.
- The hourly desk runs on EC2, and a contradiction pauses the fact and alerts within the hour.
- `facts_review.py` applies an approved proposal end to end, through test and push.
- The workflow (who reviews, when, how) is written into [system-architecture](../docs/06-strategy/system-architecture.md) and this file is deleted, with its row ticked in the README.
