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
