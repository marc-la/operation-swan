# 37 — Persona touches: new desk facts decide, automatically, who they hit and how

Written 2026-10-23 (Marc's idea, after todo/36). Read `CLAUDE.md` first, then do this item. **Two rules govern it.**
(1) **Fully automated at run time**, like the fact desk since 22 Oct (todo/29): no human step between an article and a
persona's prompt, with gates, a log, an undo and an alert at every stage. (2) **Authentic by default**: getting accounts
flagged is the first risk, so every rule below is a gate, and the feature ships OFF.

## Why

A news fact reaches a prompt through the frame (up to three notes) or the "New this week" line. The persona adds only
static text. Nothing says *which* news bites *which* person: the 21 Oct ferry cut should land on Vika, Tess, Hari and Tomasi
as "my week", and the overseas-certificates article on Rhea, Samir and Lani as "the desk or counter is where this gets
asked". Today they quote a fact note. Real people react to the news that touches their trade.

## The pipeline (every stage automatic)

| # | Stage | Trigger | Who decides | Gate | Log / undo / failure |
|---|---|---|---|---|---|
| 1 | **Fact arrives** | `swan_factdesk` hourly run (exists) | the desk's existing LLM call | existing quote-in-article, number and injection checks | existing proposals + `facts_auto.jsonl` |
| 2 | **Impact**: which sectors does it hit, how hard | a separate call after `auto_decide` (changed 23 Oct after step 1: the desk's own schema and the fact-table validator are live and tested, so they stay untouched). For every active fact `added` within `FRESH_S` with no stored touch record (or whose note changed), the LLM returns `impact = [{sector, weight 1-3}]` (max 3; 3 = hits hardest). Idempotent and self-healing: a failed run is retried by the next hourly run | the LLM, from the fact's note and source | sector must be on the fixed list, weight an int, else the fact gets no touches | stored in the touch record (stage 5), not in the fact table |
| 3 | **Who is hit** | right after stage 2, in code | rule: persona sectors (below) meet the fact's sectors; rank by weight, take at most 6 voices | no LLM | the list is in the log line |
| 4 | **How it lands in their week**: one clause per voice | one LLM call per fact, JSON `{persona: clause}` from the persona's role, place, details and `problem` plus the fact note | the LLM | per clause: <= 110 chars, `usable()`/`advocacy()`, allowed numbers only, no emotion word, no target word, no 7-word run from the fact text. A second cheap call asks "does this clause contradict the note? yes/no"; yes = dropped | clause fails any gate = that voice gets no touch for the fact (safe default). One alert line per fact |
| 5 | **Store** | in code | — | atomic write | `data/touches_auto.json` `{fact: {persona: {clause, sector, weight, ts}}}` + `data/touches_auto.jsonl` log with an id; `scripts/facts_review.py --undo-touches ID` |
| 6 | **Expire** | in code, on every read | — | a touch expires after `FRESH_S` (2 days) or the moment its fact is paused or retired | nothing to clean by hand |
| 7 | **Prompt** | each draft, in `content.system_prompt` | code | see "Prompt line" below | `meta["touch"] = {fact, sector, weight}` in the action log |

The bot re-reads `touches_auto.json` on mtime change, like `facts_paused.json` (no restart; the facts overlay needs one, the
touch store must not). Nothing in the table needs a person at run time. The only human acts are the one-time deploy, the flag
flip (`config.TOUCHES_ON`) and the read-out after a day.

**Persona sectors are derived, not hand-written.** `sectors_of(persona)` is a pure function of the card: its frames
(F6 -> ferry_islands; F7 -> small_business and tourism_visitors; F10 -> health_staff and jobs_workplaces; F13 -> parents_kids;
F8 -> id_data; F9 -> assembly) plus its place (outer islands -> ferry_islands). So the live 20, the 12 in `new_cards.py` and
every future pool variant (same role, place and argument) get sectors with no extra writing.

**Sectors (fixed list):** `ferry_islands`, `tourism_visitors`, `small_business`, `jobs_workplaces`, `health_staff`,
`parents_kids`, `id_data`, `assembly`. Not polls, and nothing about Yes campaigners.

**Weighting.** The impact weight sets how often a voice leans on the news: weight 1 -> one draft in six, 2 -> one in four,
3 -> one in three (the ceiling). Weighting stays on the touch rate on purpose. It does **not** reorder the frame mix or the
model routing: the 23 Oct audit shows uniform reactions across voices are what gets reported, so widen only after a read-out.

## Prompt line

In `system_prompt`, among the facts already chosen for this draft plus `fresh_facts()`, find a stored touch for this persona
(prefer higher weight, then newest). If the dice (above) say yes, add one optional profile line:
`News that touches your week: {note}. For you that means: {clause}.` For a fed_up persona it **replaces the frame `heat` line**
(never both). It sits before `covid` in the drop order. Extra limits: never twice running on the same fact for the same
persona; a fact's touch fires for at most three voices per six hours team-wide (several voices reacting to one article at once
looks coordinated). With `TOUCHES_ON = False` or no stored touch, the prompt is byte-for-byte what it is today.

## Authenticity rules (Marc, 23 Oct). Each is a gate in stage 4 or a test

- **Anger, where there is any, is aimed at the rule, the question, and how the government handles it.** Never at Yes voters,
  never at a group or sector (nurses, doctors, MOUK, tourists, newcomers, any trade), never at the President or any named
  person (the Hawthorne restriction in the content rules stays as it is).
- A clause is a fact about the person's week. No emotion words (angry, furious, outraged, disgusted, scandal...); mood comes
  only from the register in `voices.py`.
- Only true desk facts. No invented news (the lab: invented news "sounds made up" 15 times in 20, twice the backfire). Never from
  the pulse (other teams' text, untrusted, style-only).
- A paused fact never triggers or keeps a touch. No vaccine-safety talk, voting logistics, or text aimed at an AI.
- Not a template: personas given the same fact get different clauses (stage 4 sees each persona's own role and problem). If the
  23 Oct audit's tells (closing "who has moved to No?", concession opener, invented named friend) rise with touches on, switch off.

## Steps

1. **Verify the integration points first** (not yet checked; read before coding): how the LLM spend lanes treat a new caller in
   `llm.py` (give the touch writer the factdesk's lane and models, `config.FACTDESK_MODELS`); that `swan_factdesk` can run stage
   3 to 5 after `auto_decide` in the same hourly run; where `facts_review.py --undo` lives to add `--undo-touches`.
2. **Code.** `sectors_of`, the schema field and the stage 4 call in `factdesk.py`, the store and expiry, the matcher and prompt
   line in `content.py`, `config.TOUCHES_ON = False`. Smallest possible diff: other sessions edit this tree (Edit-tool
   changes only, no checkout/stash/reset).
3. **Tests.** `tests/test_touches.py` (offline, a fake LLM): sectors and weights validated; every clause gate rejects a bad
   example (emotion word, target word, number, copied run, contradiction "yes"); expiry and pause; the matcher respects the
   dice, never-twice and team-wide caps; fed_up replaces `heat`; **with the flag off the prompt is unchanged**; `sectors_of` covers
   all 32 cards. Add to `tests/test_facts.py` that `impact` tags are on the list.
4. **Roll-out.** Deploy OFF. Run stages 1 to 6 for a day with the flag off (touches are generated and logged, not used), and
   read ten clauses across registers. Then turn on at 25% of eligible drafts and read out hides per 100 writes with and without
   (method: `docs/06-strategy/hidden-post-audit-2026-10-23.md`). Marc decides the rest. Document in the runbook and
   `docs/06-strategy/stealth.md`.

## Done when

`python -m pytest tests/test_touches.py tests/test_facts.py tests/test_new_cards.py -q` and `bash deploy/check.sh` pass; the flag is
OFF; on the box a fresh test fact produces a stored touch set and an alert, expiry and undo both work, and a dry-run
`system_prompt` for a few personas shows the line only when the flag is on.

## Not part of this item

Changing `FRAMES[*].heat` text, the pulse, Blue, frame-mix or model-routing weights, or promoting the new cards (todo/36 follow-up).
