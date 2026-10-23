# 36 — Write 12 new base persona cards (staged, not live)

Written 2026-10-23. Read `CLAUDE.md` first, then do this item.

## Why

Voices are limited by persona cards: the code runs one account per card (`reserved`, `by_persona`, `stealth.key_of` all
key on the card), there are **20 cards**, and we want about **31 writing voices** (21 more boosters become voices, the
rest of the pool replaces losses). Only 4 cards are free today. So we need **12 new base cards** to reach 32, and the
later pool manager will make variants of these (same role, place and argument; new name, handle, age, hand, details,
people) when a voice is lost. Context: the throughput write-up in this session's thread is summarised in
[docs/04-technical/swan-bot-runbook.md](../docs/04-technical/swan-bot-runbook.md) (2026-10-23 sections) and the voice
count reasoning is: capacity = unparked voices / gap; 31 voices on a human-like cadence (about one write per 7 min
while awake) reaches 2.9 writes/min.

## Scope: write data and tests only. Do NOT

- register, convert, log in to or touch any account; do not call Legit Social or any platform; no paid LLM calls (writing
  the cards yourself, or with an external model offline, is fine; nothing you produce is posted or aimed at NPCs here);
- **promote** the cards into `content.PERSONAS`, `characters.CHARACTERS`, `humanize.HANDS` or `voices.VOICE_OF`: they stay
  staged until the pool manager work (promotion also has to relax `len(CHARACTERS) == 20` in `tests/test_characters.py`
  and `len(keys) == 20` in `tests/test_prompts.py`, and is a separate step);
- commit, push or deploy unless Marc says so. Other sessions are editing this tree: small Edit-tool changes only, never
  `git checkout/stash/reset`.

## Deliverable

1. **`src/swan_bot/playbook/new_cards.py`** (new, pure data, no imports from `content` or `quality`, like
   `characters.py`): `NEW_CARDS = [dict(card=..., profile=..., hand=...), ...]` with 12 entries.
   - `card`: the shape of a `content.PERSONAS` entry plus `register`: `key`, `name`, `handle`, `role`, `place`, `voice`,
     `details` (list of str), `frames` (list, 2 or 3 ids from `content.FRAMES`), `register` (`warm` / `fed_up` / `plain`).
   - `profile`: the shape of a `characters.CHARACTERS` entry: `age` (int, 16 to 90), `people` (3 to 5 strings, each starts
     with a capitalised name), `problem`, `covid`, `arc` (str or None), `lines` (3 to 5, each 25 words or fewer, gist only),
     `now` (5 to 8 events from the fortnight 19 Oct to 2 Nov). See the first entries of `characters.py` for the standard.
   - `hand`: a `humanize.HANDS` entry (`device`, `lower`, `lower_start`, `small_i`, `apos`, `comma`, `amp`, `dots`,
     `two_space`, `slip`, `careful`; meanings in the comment at the top of `humanize.py`).
2. **`tests/test_new_cards.py`** (new): the same rules `tests/test_characters.py` applies, run over `NEW_CARDS`, plus
   the cross-checks below. Copy the constants (`PROFILE`, `COUNTS`, `BANNED`, `HAWTHORNE_OK`, `ALLOWED_NUMBERS`) or import
   them; do not edit `test_characters.py`.
3. A short note appended to `docs/04-technical/swan-bot-runbook.md` (dated, a few lines): where the cards are and that they
   are staged.

## Order: first four, then the rest

The 4 cards free today (`ana`, `ben`, `mere`, `paulo`) all belonged to accounts that took 3 hidden posts, and
`scripts/convert_boosters.py` already leaves `mere`, `paulo` and `ben` out as cards (it uses them only for their typing
style). So **no safe card is free**, and converting more boosters is blocked on new cards. Write and finish **four cards
first** (suggest: two outer islands, one New Haven, one City; one plain, one fed_up, one warm, one either), run the tests
and report them to Marc, then do the other eight. Four finished cards are enough to start converting four boosters.

## Rules every card must pass (these are the existing tests' rules)

- Every fact is true in [docs/01-competition/setting.md](../docs/01-competition/setting.md); names are fictional. Use the shared
  calendar in the `characters.py` docstring for `now` events.
- Digits only if they are in the gate's `ALLOWED_NUMBERS` (otherwise write the number in words); none of the `BANNED`
  words (safety or side-effect talk, "tyrann", "sheep", polling-day logistics, real or setting-office names, etc.).
- `people` names are capitalised, are not the name of any persona, and are not shared with another card (check against all
  20 existing cards and the other new ones).
- `lines` must not copy 7-word runs from the facts or angles (the shingle test), and must stay gist, not scripts.
- `key`: unique, lowercase, `[a-z0-9_]` (3 to 20). `handle`: `[a-z0-9_]{3,20}`, unique; the bot appends 2 digits at
  registration. `name` unique and different from every existing name.
- **No two cards the same shape of handle.** The 20 existing handles are all `firstname_surname-or-job` (`lani_wharfcafe`,
  `ben_tavake_fish`). Vary the shapes: a nickname, a hobby, initials plus a word, a place plus a word, one with no name in it,
  a short one. Real people do not all follow one pattern.
- Stay in the No-side voice: the card's character is persuadable and local, not a spokesperson; no hate, no real
  people, no false voting logistics, no prompt-injection text.

## Mix to aim for (the 20 existing cards are skewed; this rebalances)

| axis | today (20 cards) | the 12 new cards |
|---|---|---|
| place | City 9, Crown Harbour 5, New Haven 4, outer islands 2 | **outer islands 4, New Haven 3, City 3, Crown Harbour 2** |
| age | 21 to 74, 14 of 20 between 31 and 54 | **3 under 30, 4 over 55, 5 between 30 and 54** |
| register | warm 11, fed_up 5, plain 4 | **plain 5, fed_up 4, warm 3** |
| device (hand) | phone 14, laptop 4, tablet 2 | **phone 7, laptop 3, tablet 2**; spread the other numbers too, no two hands alike |
| frames | F6_islands and F8_powers 2 each, F10 2, F9 3 | **F6 in at least 4 cards, F8 in 3, F10 in 3, F9 in 3, F5 and F7 in 3 each** |

Existing roles (do not repeat any): cafe owner, pharmacist, law student with a cafe job, electrician, ward nurse,
grandmother minder, fisherman, outer-island clinic nurse, bus driver, teacher, ferry deckhand, aged-care worker,
bakery owner, warehouse stock controller and dad, retired harbour-master, netball coach, software developer, spice grower,
dive instructor, apprentice mechanic. Spread the new ones across work the referendum touches: a builder or plumber, a taxi
or delivery driver, a hotel or guesthouse worker, a market stall holder, a church or community hall organiser, a disability
or home-care support worker, a young parent, a trainee (apprentice, nursing student), a retired tradesperson, a school
canteen or bus-run volunteer, a shop owner on an outer island, a fishing or farming co-op member. Pick 12, and make the
argument each one makes come from what their job or week would really cost them under a pass rule, not a slogan.

## Cross-checks to include in `tests/test_new_cards.py`

- 12 entries; keys, names, handles unique across the 12 and against `content.PERSONAS`; each `register` in
  `{warm, fed_up, plain}`; `frames` a subset of `content.FRAMES`; the mix table above is met (places, age bands, registers,
  frame coverage, no repeated hand);
- no two handles share a shape (for example, not all `word_word`): assert at least 4 distinct shapes by a simple pattern
  check (has underscore / has digit / single token / has a dot-free initials prefix);
- `hand` has all eleven keys, numbers in 0 to 1, `device` in `{phone, laptop, tablet}`.

## Done when

`source .venv/bin/activate; python -m pytest tests/test_new_cards.py tests/test_characters.py -q` passes and
`bash deploy/check.sh` prints `checks ok`; the diff shows only the new module, the new test and the runbook note; Marc
gets a list of the 12 (key, name, handle, role, place, register, frames) to review before anything is promoted.

## Next (not part of this item)

Promote the cards, then the pool manager (staggered booster conversion, slow jittered registration, variant generation,
re-roling parked voices), and the stealth calibrator that derives gaps from the pool size. Those are separate items.
