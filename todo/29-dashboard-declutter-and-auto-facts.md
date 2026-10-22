# 29: Dashboard declutter, a throughput metric, and facts on autopilot

**Owner:** orchestrator (ctn-9c) + a background agent · **When:** 22 Oct · Marc's review of the live dashboard, 22 Oct ~05:00 UTC

## Why
Marc reads the dashboard on his phone. Several sections give too much detail, or the wrong number. And he no longer wants to review facts by hand.

## Do: dashboard (`src/swan_dash`, `tests/test_dash*.py`)
1. **Reach: replace "Longest wait in our queue".** It swings with the time of day and the number of citizens, so it says little. In its place, a **throughput efficiency** row:
   - writes per minute over the last full hour against the theoretical maximum: `team write budget` (3/min, from the rate-limit headers when known) and the bot's configured pace (`deploy/run.sh --per-min`);
   - e.g. "1.6/min of 3.0 (53%) · pace 2.4". Target ≥ the configured pace;
   - and make "Citizens answered" a share of citizens who posted (e.g. 60% of 208) as well as the count.
   Keep the verdict logic consistent (no row may turn the pill red on its own when it's only time of day). Keep the "In hand" notes.
2. **Score & targets: the portal's details in place.** The team page's score events (`data/portal.json` → `events`) show today under Activity, where they get lost. Put them under each score line as a collapsed `<details>`: e.g. "Persuasion +X" opens to the events behind it, grouped by kind (persuasion, views, Blue awards, penalties) with counts and the last few lines. Remove them from Activity once they're shown here.
3. **Blue:**
   - **Pending:** one line per pending report is too much. Summarise ("25 pending · oldest rules 14:10 · 3 accounts") with the rows collapsed under it, grouped by cluster.
   - **"By competition day":** doesn't fit a phone. Make it a stacked card per day (or fewer columns) under 480 px; no horizontal page scroll.
   - **"Reports since 9pm":** too many rows. Group in place by outcome (hidden / pending / genuine / refused), each a collapsed group with its count, genuine open by default.
   - Read any new fields todo/28 adds to `data/blue_status.json` (its file lists them).
4. **Trending pulse:** demote to a single summary line at the bottom (or remove it if nothing reads it; check `swan_bot` first). Marc: "OK, but not particularly useful."
5. Check every change at 375 px wide (render the page from the live data on EC2, read-only, as the last dashboard change did) and run the dashboard tests.

## Do: facts on autopilot (`scripts/swan_factdesk.py`, `src/swan_bot/factdesk.py`, `scripts/facts_review.py`)
Today: a contradiction pauses a fact automatically. Rewordings, new facts and ideas wait for a human ([system-architecture §9](../docs/06-strategy/system-architecture.md#9-fact-desk-who-reviews-when-how-2026-10-21)). Marc (22 Oct): **"I don't want to review anymore. Auto mode for the facts."**
1. **`FACTDESK_AUTO = True` (config):** the desk applies its own proposals, with the same checks a human decision runs:
   - **rewording or date fix of an existing fact:** accept in place (`--same-key` semantics);
   - **contradiction:** accept as the new wording under a new key when the paper's quote is unambiguous, else retire. The old fact's dependants stay out, as today;
   - **new fact:** only from a news article (never an opinion column) with a verbatim quote, and only if `tests/test_facts.py` passes with it;
   - **ideas:** stay ideas (logged only; frames are code).
2. **The EC2 box can't push,** so decide how an auto decision goes live and say why in the doc. Either a local overlay the bot reads (`data/facts_auto.toml`, merged over `content/facts.toml`, mirrored to Mongo), or a deploy key with push rights scoped to this repo. Prefer the overlay unless push is clearly simpler. Either way, every decision is recorded in `content/fact_decisions.jsonl` or the overlay with `by: "factdesk-auto"`, so git or Mongo still show who decided.
3. **Safety rails:** a dry-run flag; a daily cap (e.g. ≤ 5 auto changes a day, the rest wait); an alert line per auto decision; the dashboard's Facts section becomes a log of auto decisions with a one-click-free undo command. Paused facts still drop out of prompts immediately, as today.
4. Update system-architecture §9 (dated) to say what is now automatic.

## Ownership
`src/swan_dash/*`, `scripts/swan_factdesk.py`, `src/swan_bot/factdesk.py`, `scripts/facts_review.py`, `tests/test_dash*.py`, `tests/test_facts.py`, `tests/test_factdesk*.py`, system-architecture §9. Don't edit `content.py` (the todo/25 session), `quality.py` or the writer (todo/27), or `src/swan_blue` (todo/28). Rebase on `origin/main` before every push; `deploy/check.sh` must pass.
