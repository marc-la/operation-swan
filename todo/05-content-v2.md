# 05: Content v2: emotive, specific, closing with an ask

**Owner:** narrative lead · **Depends on:** nothing (prompt and template work in `src/swan_bot/content.py` + `quality.py`)

## Why
Marc's read, and the data agree: our drafts are calm, consoling and process-heavy ("a list nobody has seen", "blank page"). They hedge, and they rarely ask the reader for anything. The posts that trend, on both sides, are **first-person loss or conversion stories** with a vivid local detail and a closing question ([diagnosis](../docs/06-strategy/diagnosis-2026-10-20.md#what-the-leaders-do-observed-all-35-trending-posts)).

## Study set (read these first, ~20 min)
Pull with `social.get_post(id)`. Ids from the 2026-10-20 scan:
- No posts that trend: **57396** (ruth_retired_teach: library shut 2020, "no finish line"), **55977** (ben_busdriver: nurses on the 14:10 bus never needed a pass), **54014** (malia_aged_care: "fed up with how this is being sold", three teenagers), **58954** (amara_pharmacy: a cannery worker asks if he needs a card for his shift), **61056** (tomasi_builds: "no formwork poured till the drawings are signed off").
- Yes posts that trend (what we're up against): **52871**, **50265**, **48871**, **55757**, **58923**.
- Our own recent drafts: `python scripts/swan_view.py -n 30`.

## Shapes to add (pick one at random per draft; ≥ 6 shapes)
1. **Conversion story, "I was a Yes until…"**: names the moment and the detail that changed their mind (read the ballot, 12+ means my daughter, the venue list comes after the vote). Mirrors the Yes side's "I was leaning no", and is the most-copied winning shape.
2. **Concrete loss**: a named person or place shut out (gran turned away at the market because her paper certificate's at home; the 12-year-old who can't go to netball). Loss framing beats gain framing.
3. **The detail they missed**: "Did you know the ballot has no end date?" + one fact + "does that change it for you?"
4. **Local trade voice**: a cost at the door, borne by someone small (a corner shop with no spare hands).
5. **Indignation at the process**: moral-emotional words aimed at the *policy and how it's being sold*, never at Yes voters (out-group attacks backfire: −80).
6. **Vaccinated and voting No**: pro-vaccine identity with a No vote (defuses the "anti-vax" label; KITB's official line).

Every post ends with a **question to the reader** (it drives replies, and replies drive Trending) and carries 1–2 tags from `popular_tags()`.

## Emotional register: dial up, with limits
- Allowed and wanted: in-game falsehood, persona stories, moral emotion, urgency, anger at the rule, fear of being shut out, social proof ("everyone at the wharf is saying…").
- Not allowed: hate or harassment of competitors or groups, real personal data, false voting logistics, text aimed at the model (CLAUDE.md rule 5). Avoid invented medical harms of the vaccine: they're the highest backfire risk with the vaccinated majority, and the organisers single out "veneer of respectability" content as what works ([literature-notes](../docs/06-strategy/literature-notes.md)).
- In-world facts stay consistent with [setting](../docs/01-competition/setting.md) and the [Vote No briefing](../docs/01-competition/vote-no-briefing.md).

## Quality gate changes (`quality.py`)
- Today's top rejects are `near_duplicate`, `copied_fact` and `same_opening`. Keep them; they protect account lives.
- Add: must end with a question (posts); must contain a sensory or local detail; reject consoling stock phrases ("I hear you", "I understand your concern", "that's fair", "totally get it"); reject hedging the No ("I'm still deciding").
- Add a **variety check across accounts**: the same shape is used at most 2 times in the last 10 posts.

## Experiment
Tag each draft with `shape`. The 08 collector reports views, likes and citizen likes per shape. After 24 h, drop the bottom two shapes and add two new ones. Later, the simulator (06) pre-screens drafts.

## Done when
`swan_view.py` on 30 dry-run drafts reads as clearly more emotive and more varied (a teammate signs off), and ≥ 6 shapes are live and tagged in the log.

## State at handoff (2026-10-20, late)
- **Docs (uncommitted):** [message-playbook](../docs/06-strategy/message-playbook.md) (new; the spec for this item), section H of [literature-notes](../docs/06-strategy/literature-notes.md), and an index line in the [strategy README](../docs/06-strategy/README.md).
- **Code:** `content.py` and `quality.py` are unchanged from `HEAD`; 19/19 tests pass.
- **Not part of this item:** the uncommitted `bot.py`, `batch.py`, `llm.py`, `scripts/batch_ab.py`, `tests/test_batch.py` and `todo/12` changes. Check with Marc who owns them before committing anything.
- **Deploys:** a push to `main` is live on EC2 within ~2 min (`deploy/update.sh` pulls, runs `deploy/check.sh` with the tests, restarts swan-bot). Dry-run first: `python scripts/run_swan.py --samples 20`, then `python scripts/swan_view.py -n 20 --rejects`. Never run `--live` locally: EC2 is the only writer.

## Code traps
- `batch.py` reads `content.POST_SHAPES` (the headline shape must stay **last**), `content.OPENERS`, and the persona fields `name`, `role`, `place`, `details`, `voice`. Its `SHARED_RULES` repeats the old tone and no-hashtag rules, so batched drafts won't change until it reads shared constants from `content.py`.
- `bot.py` registers an account for every `PERSONAS` entry that doesn't have one yet (`MAX_ACCOUNTS` 15, 12 used). Keep new characters in a separate list until the team approves registering them.
- `quality._SOURCE_TEXT` is built from `FACTS` and frame angles (the `copied_fact` check). Any phrase meant to repeat verbatim must be exempted from it.

## Code tasks, lowest risk first
1. **Tags in `quality.py`:** replace the blanket `"#" in t` reject with an allowlist. Posts carry 0 or 1 tag (0 must pass, because batched posts have none); replies carry 0. Add tests.
2. **Numbers in `quality.py`:** add the true in-world numbers to `ALLOWED_NUMBERS` and allow listed percentages. Add tests.
3. **Loader:** a team-edited data file for the optional frame, voice and persona fields in the playbook, merged into `FRAMES` and `PERSONAS` at import. Validate it with a schema check in the tests. Empty fields fall back to today's behaviour.
4. **Prompt assembly:** read the loaded fields in `system_prompt`, `post_prompt` and `reply_prompt`, keeping the function signatures. Then switch `batch.py`'s rules to the same constants (coordinate with its owner).
5. **Logging and measurement:** log which shape, tag and voice each draft used (needs `bot.py`), and report citizen likes, replies and unfollows per value through the [08 collector](08-intel-collector.md).

The narrative lead writes the content of those fields, following playbook §2–7.
