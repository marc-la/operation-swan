# 14: Prompt steering: cut the reject rate (length, copied facts) without losing the content-v2 gains

**Owner:** Marc + a fresh Claude session · **Depends on:** content v2 (05) and the 13 prompt changes, both live (`5047fe8`) · **When:** 21 Oct, before 13's experiments (rejects waste the arms)
**When done:** delete this file, remove its row from [README](README.md), and record the before/after numbers in [13](13-overnight-experiments.md) "Evidence".

## Status (2026-10-21 ~00:45 Perth, pushed on top of todo/13's `5eb8cd9`)
**Done (steps 1–5 and both "also pending" items):**
- **Repair-on-reject:** `bot.draft_checked` is the one draft loop (`swan_screen.py` calls it too). On a reject, `quality.repair_note` returns a fix (length → cut to N sentences, copied phrase quoted, tags, closing question, vote statement, spelled number) and the draft goes back with it. Other rejects get a fresh draft. `repair` is logged on action and reject records.
- **Beat budget:** each post gets one of stake / lever / turning point (`meta["beat"]`, logged as an arm), with `lever=None` when no lever is used. Conversion and defiance get no facts beat, and nor do number and did_you_know, whose opening already carries a fact. A concession replaces the facts beat. The catchphrase is drawn only without a concession, still about 1 in 3. `WORLD` is now 3 sentences, with no numbers, labelled "Background (don't restate it)".
- **Length by words:** `experiment.LENGTH_BANDS` is now (sentences, lo, hi) in words, and `experiment.VERSION = 2`. `llm.complete` takes `max_tokens` and `temperature`. The bot uses a 600-token cap: flash-lite spends no thinking tokens, and a 120 cap finished "stop" at 73. Temperature is 0.7, or 0.9 for own-thread replies.
- **Notes, not prose:** `content.FACT_NOTES` and `FRAMES[*]["gist"]` are what the prompts show. `quality` still checks copying against the full sentences, and a test checks that no note trips that check. The two fear rebuttals now say "ONE of these".
- **Contradiction audit:** the voices no longer give sentence counts, fact counts or endings. Endings are the `ask_kind` arm, and warm's "grant the other side" had been conceding in every post, confounding 13's `concede` arm. `test_one_length_and_ending_instruction_per_prompt` covers this.
- **Closing fingerprint:** a new `close` arm (`experiment.CLOSES`) puts the question before the verdict in ~1 in 4 posts. `ask_kind="none"` is re-enabled for posts, since the gate now takes `closing_question` from meta (it had been rejecting every such post). Prompts ask for contractions, and the gate rejects spelled-out figures (`spelled_number`).
- Isla: "lowercase is fine" dropped from her style, since `humanize.py` already types 85% of her drafts in lowercase.

**Still to do:**
- **A proper same-seed before/after on flash-lite.** The 00:00 baseline (`data/screen-before.json`) mostly ran on gpt-oss-120b and qwen3.8, because flash-lite was timing out (silent 120 s parks), so it isn't comparable. Rerun both with `LLM_CHAIN=gemini:gemini-3.5-flash-lite`. The after-smoke (`data/screen-after.json`, flash-lite only, seed 7, 4 posts + 2 replies) passed 6 of 6 on the first or repair call, using 8 calls. Both rejects were `copied_fact`, and both repairs passed. There were 0 length rejects (posts 266–431 characters, replies 217–220), 0 "when my turn comes" and 0 condition questions. Six drafts is too few to call the 70% target met. Seen in the drafts: one post says "voting No" twice, a repair left "There's no local cases yet", and a reply uses "I am voting No" uncontracted.
- **Step 6, measure per ingredient,** from EC2's `logs/swan_actions.jsonl` once a night of `exp: 2` records exists (reject records now carry every arm plus `repair`).
- The teammate read-through of 10 drafts, and the EC2 check that rejects drop in `journalctl -u swan-bot`.

## Read first (~15 min)
1. `CLAUDE.md` (guardrails). Never run `--live` locally: EC2 is the only writer, and a push to `main` is live on EC2 within ~2 min.
2. [message-playbook](../docs/06-strategy/message-playbook.md) §5 (post anatomy) and §6 (voices): what the prompts implement.
3. Code: `src/swan_bot/content.py` (`WORLD`, `LEVERS`, `system_prompt`, `post_prompt`, `reply_prompt`, `second_voice_prompt`), `src/swan_bot/playbook/voices.py` (the voice instructions), `src/swan_bot/bot.py` (the draft-and-check loop: `for _ in range(... 2)` around `gen.complete`), `src/swan_bot/llm.py` (`complete`, `_call`), `src/swan_bot/quality.py` (`check`, `LENGTHS`, `_SOURCE_SHINGLES`).

**Coordination (2026-10-21 ~01:00 Perth):** a parallel session is building todo/13 (experiments, follow-ups) in the same files: `bot.py`, `content.py`, `targeting.py`, and the new `experiment.py` and `followup.py`. Start from whatever is committed on `main`. Re-read those files before editing; line references here are approximate. If 13 assigns arms in `post_prompt`/`reply_prompt`, keep its `meta` keys and add yours beside them.

## The problem
The prompts gained an ingredient at every layer: world block, profile, voice paragraph, opening style, turning point, stake, frame angle, lever, facts, concession, catchphrase, question, tag. A small model (`gemini-3.5-flash-lite`) treats each one as a must-include. Drafts get long and read as stitched together.

| Read-only dry pass (`scripts/swan_screen.py`) | Passed | Rejected | Length | Copied fact | Other |
|---|---|---|---|---|---|
| 2026-10-20 ~00:00 Perth, content v2 before todo/13 changes | 12 | 12 | 7 | 5 | 0 |
| 2026-10-20 ~00:50 Perth, after todo/13 changes (`WORLD`, `LEVERS`) | 5 | 12 | 9 | 1 | 2 generic, 1 artefact |

- **Length** rejects cluster in the conversion and defiance openings and the warm voice: 554–657 characters against a gate max of 495 for posts, 290 for replies. Mere/Priya replies on hospital fears ran 346–542, with every `WORLD` number packed in.
- **Copied fact:** the model pastes the frame angle and the fact text verbatim, e.g. "Keep Kingstonia open: the ordinary island life you love shouldn't need papers at the door", "the vaccine is free, voluntary and available whatever the result", "no community spread here yet".
- **Retries repeat the failure:** the second try sends the identical prompt. The same persona failed twice in a row with near-identical drafts 5 times.
- Plain voice (Isla) produced **all-lowercase** drafts: her persona `voice` is "casual, lowercase is fine", which plain's calm register then turns into a whole lowercase post. Decide whether to drop "lowercase" from her style or cap it to the occasional lowercase reply.
- What improved and must not regress: "I'll get my jab when my turn comes" 4 of 12 → 0; closing questions about *conditions* → 0.

## The pitfalls (why it happens)
1. **Every draft gets every ingredient.** Each beat is read as an instruction to include it, so all of them get included.
2. **Background reads as content.** `WORLD` is full of numbers; the model can't tell "true context" from "say this".
3. **Character counts don't steer this model.** "between 240 and 420 characters (count them)" is ignored. Sentences and words work.
4. **Contradictions get "satisfied" by saying more:**
   - The plain voice says "add one or two more [facts]", but `post_prompt` says "one fact (two at most)".
   - The fed-up `reply_instruction` says "two or three short sentences", but second voices ask for 1 or 2.
   - `WORLD` lists seven numbers, but the post asks for one fact.
5. **Source text written as polished prose gets copied:** angles, facts and stakes are full sentences.
6. **Identical retries:** a reject never tells the model what went wrong.
7. **`llm.py` ignores `max_tokens`:** `complete(max_tokens=220)` has the argument, but `_call` hard-codes `max_tokens=4096` (8192 in JSON mode) and `temperature=0.9`.

## Do, in order (measure after 1–3, then after 4–6)
Baseline first: `LLM_RPM=6 python scripts/swan_screen.py data/screen-before.json --replies 4 --posts 6 --seed 7`, with the code as committed. Then rerun with the same seed after each group of changes.

1. **Repair-on-reject retries** (`bot.py` draft loop; mirror the change in `scripts/swan_screen.py`'s `draft()`). On a reject, the second call sends the draft back with the reason and asks for the smallest edit, not a fresh roll. Map reasons to repair notes:
   - `length_N` → "Too long (N characters). Cut to 4 sentences, keep the opening, the No and the question."
   - `copied_fact` → "This phrase copies the brief: «…» (from `quality.copied_runs`). Say it in your own words."
   - `tag_*` → "Exactly one hashtag, last: #X" (posts) / "No hashtags" (replies).
   - `no_closing_question` → "End with one question the reader answers from their own life."
   - `no_vote_statement` → "Say plainly that you're voting No."
   - anything else → the old fresh retry.

   Keep it to one repair call: a repaired draft goes through `quality.check` as before. Log `repair: <reason>` on the action record, so 13's report can count repairs.
2. **Per-shape beat budget** (`content.post_prompt`): at most 4 content beats besides the fixed close ("voting No" → question → tag).
   - Pick ONE of {stake, lever, turning point}. Conversion uses the turning point; named_loss uses the stake; the others choose at random.
   - Conversion and defiance get no extra facts beat.
   - The catchphrase replaces the concession, never joins it.

   Cut `WORLD` to 2–3 sentences with no numbers, under a label like "Background (don't restate it):". The numbers stay available through the frame's facts list and the hospital/COVID rebuttals.
3. **Length by structure, not characters:**
   - Posts: "4 sentences, under 70 words"; one-liner shapes are separate. Replies: "2 sentences, under 45 words".
   - Make `_call` honour `complete(max_tokens=...)` and pass a cap from `bot.py`. Check first whether flash-lite spends thinking tokens out of `max_tokens`, since todo/12 found Gemini 3.x can't fully turn thinking off. If it does, a tight cap truncates: watch `gen.last_finish == "length"`, and start around 600, not 220.
   - Temperature 0.7 for posts and replies, 0.9 kept for own-thread one-liners. Make it a `complete(temperature=...)` argument, default 0.9, so other callers don't change.
4. **Facts and angles as fragments.** In `system_prompt` and the post/reply prompts, give facts as terse fragments ("no end date · places picked after the vote · first doses → health workers, high-risk") built from `FACTS` keys. Use a short gist for the angle, not the full `angle` sentence. Either add a `gist` field per frame in `content.FRAMES` (humans own that file: keep it factual) or derive it. Keep `quality._SOURCE_TEXT` built from the full sentences, so copying is still caught.
5. **Contradiction audit.** Render one prompt per mode × voice (`content.system_prompt` + `post_prompt`/`reply_prompt`/`second_voice_prompt`/`journalist_prompt` with `meta={}`; `tests/test_prompts.py` shows how) and read them end to end. Fix every place two instructions disagree on length, fact count or sentence count. Known ones are in pitfall 4. Add a test that the fed-up reply instruction and `second_voice_prompt` agree on sentence count.
6. **Measure per ingredient.** From `logs/swan_actions.jsonl` (EC2 has the live one: `ssh swan-ec2`, `~/ctn/logs/`), tabulate reject reason × `lever`, `shape`, `voice`, `concede`, `rebuttal`. Drop or rewrite any arm with a reject rate more than ~2× the average. Note: reject records carry only `shape` and `voice` today; add `lever` and `concede` to the reject `log()` call in `bot.py` as part of step 1.

Also pending, from the same review (do if time allows):
- **Spelled-out numbers.** The gate doesn't check numbers written as words: "Twelve thousand doses" (for 120,000) was only caught because it also copied a phrase. Reject spelled "hundred/thousand" figures in `quality.check` and add "write numbers as digits" to the rules.
- **Closing pattern fingerprint.** Every post ends "question? #Tag", and 11 of 12 said "I am voting No" uncontracted. Vary where the verdict sits. Let ~1 in 4 posts end on the verdict or catchphrase with the question earlier, which needs a matching `quality` option (today posts must end on a question). Ask for contractions explicitly in the post beats.

## Done when
- Same-seed screen: **≥ 70% of drafts pass on the first or repair call** (baseline: 5 of 17 attempts ≈ 30%), **length rejects ≤ 1 per 10 drafts**, no new reject class.
- The two gains above hold: 0 "when my turn comes", 0 condition questions.
- A teammate reads 10 drafts from the after-run (`python scripts/swan_view.py` reads the action log; the screen JSON has `drafts` with full text and meta) and agrees they read as one voice each, not stitched.
- All tests pass, then commit and push. After ~3 min, verify on EC2: `ssh swan-ec2 'cd ~/ctn; git log --oneline -1; systemctl is-active swan-bot'`, and the rejects in `journalctl -u swan-bot` drop.

## Limits that bite while doing this
- **The Gemini key is shared by EC2 and local runs** (same key, checked by hash 2026-10-20). The free project allows 15 requests/min. `llm.py` paces each model to `LLM_RPM` (default 10). Keep local runs at `LLM_RPM=6` or lower, and screen in small passes (10 drafts ≈ 15–25 calls). The README says the project is on paid Tier 1 and `deploy/llm_chain.txt` says the key is on the free project: check which before planning big runs.
- `swan_screen.py` reads the live feeds once per run (2 feed reads + per-author reads). That's fine at this size; don't loop it.
- Don't fan out many sub-agents at once: about 20 concurrent agents hit the account session limit on 2026-10-20. Do this in one session, sequentially.
