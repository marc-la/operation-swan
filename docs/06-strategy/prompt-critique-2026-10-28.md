# Prompt critique (28 Oct 2026): what the drafter is given, what comes out, and how far it is from a lean bot

Asked by Marc on 28 Oct: our replies read as machine-written (over-structured, fake typos, no use of context, names dropped as if strangers know them, trending events never surface), and the prompt has grown by accretion. Do a systematic critique of prompt and output, sized against the two numbers we steer by: **engagement per write** and **conversion** (changes of mind). Being human-like is not a goal in itself. It counts only where a bot tell costs us engagement, mind changes, or accounts.

Data: 5,226 live on-topic first replies from the box's `logs/swan_actions.jsonl`, 26 Oct 16:54 to 28 Oct 01:10 UTC (git `16eafd9`). The citizens' own posts are the baseline: these are the 5,226 posts we answered, a sample of how the crowd writes. Prompts were rebuilt locally from `content.py` with the same functions the bot calls. All reads were read-only.

## 1. Bottom line

1. **Wording will not move engagement per write much, and we already know it.** Frame, lever, ask, length, model and voice all sit inside the same 5-8% citizen-reply band, and a pick-time model scores AUC 0.52 ([engagement audit](engagement-audit-2026-10-25.md) §1). The lab says the same for stand-in persuasion: five rounds and no wording beats what we send ([npc-lab](npc-lab.md)). So this is **not** a case for a big prompt rewrite to chase points per write.
2. **The real cost of the tells is elsewhere.** It shows in three places. First, **conversion**: net negative (22 toward, 59 away in the 24 h audited on 25 Oct). Sonnet raters, our calibrated stand-in, read our voices as bots 50-75% of the time against 0-8% for a citizen. Second, **account survival**: one voice repeating one story hundreds of times is the easiest thing for a rival Blue team or the moderator to spot. Third, **the conversations we do get**: reply-backs earn about twice a first reply, and that is where ignoring context costs most.
3. **The biggest gaps are about memory and context, not grammar.**
   - One account (`uptown83`, a Paulo variant) sent **1,542 replies in 32 h**, and "Jacqui starts high school" appears in 763 of them.
   - The prompt makes a personal anecdote the default beat in every reply. It shows the voice's "this fortnight" event every time (100% of drafts) and never shows what this voice has already told this citizen. That matters because 37% of writes go to citizens we have written to 8+ times.
4. **The prompt is 8,600 characters with about 60 "don't/never" rules to get 35 words out**, and some rules contradict each other. Then 41% of sent replies still needed a repair call because the first draft failed the gate. The rules have built up as patches, each one fixing yesterday's audit. They name the phrases they ban, which primes those very phrases, and every reply comes out on the same four-beat skeleton.
5. **The typing layer pushes us away from the crowd, not into it.** The "humans" here are LLM citizens, and they almost never misspell. In 5,370 citizen posts only a handful of slips turned up, mostly dropped final g's and apostrophes ("anythin", "buyin", "honesly"). We insert random key slips ("chexks", "eiyher", "passses") into 6.3% of replies. The crowd's actual habits we barely copy: 16% end without a full stop (us 0.1%), 24% start lowercase (us 14%), and 9.5% open by addressing someone by name (us 0.9%).
6. **Do the cheap memory and register fixes first, and judge them on away events, hides and reply-back continuation, not on engagement per write.** Simplify the prompt in the same pass. Expect little on engagement per write; the wins are fewer bot tells, fewer repair calls and fewer lost voices. Section 6 ranks the fixes.

## 2. What the drafter is given

A first reply (Paulo, F10 suggested, light read on) is two messages: a system prompt of **3,119 characters (540 words, ~23 negative rules)** and a user prompt of **5,505 characters (976 words, ~36 negative rules)**. The reply cap is 260 characters. Built by `content.system_prompt` + `content.reply_prompt(read=True)`, [content.py:618](../../src/swan_bot/content.py#L618) and [content.py:1147](../../src/swan_bot/content.py#L1147).

What is in it, in order: background (world, poll) → identity (name, age, role, one detail, one or two people, **this fortnight's event**, style line) → the referendum question → stance → voice instruction → three fact notes → ~12 rules (logistics, safety, jab, advocacy, tags, style) → the citizen's post → rebuttal note → "answer first" → "answer WHY they lean Yes" → length → opener → anecdote-or-fact → lever → ending → reply voice → first-call rules → **our last 10 openings** → no-verdict rule → **11 worn phrases by name** → reply rules (8 more stock phrases by name) → JSON read block with the stance key, approach by stance, and the 10-frame menu.

**Where it pulls against itself** (all present in the one prompt above):

| one instruction | pulls against | what comes out |
|---|---|---|
| voice: "write about one named person or moment from your week" | reply rules: "mention your own life only if it connects directly"; "when unsure, name no one" | the named person wins: 20% of replies name someone mid-sentence (citizens 8%) |
| opener: "open with their own words, 6 words or fewer" | "do not repeat their sentences back"; "don't open by granting their point" | the fragment echo: "You want X." opens 14% of replies (720), "Sunset, review, privacy." |
| reason_first + rebuttal: "answer WHY they lean Yes" (arm draw, then a regex on "ward", "hospital") | the light read's own stance ("unsure") and "first take up what they actually said" | a sceptic asking "does a pass help the ward without nurses?" gets told about Kiri's twins' concert |
| APPROACH: "firm_yes: concede first" | voice and style: "don't open with agreement"; "no agreeing with their reasons" | `phrase_concede_open` is the 4th most common gate fix |
| "End on your reason… (this replaces any instruction above)" | ask arms elsewhere | patches that override patches |
| facts given as terse notes ("Central: 40 nursing posts unfilled…") | "everyday words" | telegraphic output: "COVID years: small shpos shut." |

**Naming what to avoid primes it.** The prompt lists our last 10 openings and 19 banned phrases word for word. The gate then still catches `same_opening` 322 times, `phrase_papers` 166 and `phrase_who_in_your` 72. The gate already checks every one of these, so they do not need to be in the prompt at all.

## 3. What comes out, against the crowd

| feature | our replies | citizens' posts | read |
|---|---|---|---|
| median length | 210 chars, 3 sentences | 157 chars, 2 sentences | we write more and more formally |
| **ends on a question** | **40%** | **1%** | the single biggest shape tell |
| says "you" | 40% | 9% | we talk *at* people |
| semicolon | 21% | 8% | over-structured |
| dash (—, –) | 0% | 19% | the crowd's own LLM habit; we strip it |
| no final full stop | 0.1% | 16% | |
| starts lowercase | 14% | 24% | |
| all lowercase when the citizen wrote all lowercase | 7% (69 of 929) | — | no register mirroring; 7% is just the random hand |
| opens by addressing someone by name | 0.9% | 9.5% | they talk to each other, and often to our voices by name |
| names a person mid-sentence | 20% | 8% | |
| non-word typo | 6.3% (injected) | ~0.1% | |
| mentions anything current (news, today, weather, an event) | 4% | 2% | low for both; see §4.4 |

Repetition, across all replies: "what would a Yes" 6.9%; "the question doesn't say" 4.7%; "what would you miss" 4.7%; "at the school gate" 4.2%. Closing-question starts: "what would you…" 435, "what would a…" 360, "who in your…" 230.

**Repetition by account** is far worse than repetition across the team, because the gate's near-duplicate check looks at the team's last texts, not at one voice's history:

| voice (persona) | replies in 32 h | its top phrases |
|---|---|---|
| uptown83 (paulo) | 1,542 | "starts high school" 243, "Jacqui starts high" 195, "turns [12] in March" 151 |
| tevaga_k66 (esther) | 1,097 | "the question doesn't" 102, "you're right" 98, "when it stops" 84 |
| ibbotson_hunter22 (ben) | 1,063 | "they won't [say]" 122, "when it stops" 122, "a pass at" 83 |
| kayak_dad24 (josh) | 844 | "they won't" 118, "when it stops" 99 |
| jack_dev97 (kai) | 570 | "my sister Karen" 41 |

The invented people drift between replies. Kai's partner Rachel teaches Year 8 in one reply and works the ferry kiosk in another. Ben's wife Ilaisaane minds the Saturday stall, sketches its prints, walks a granddaughter to school or works shifts, depending on the reply. The variant renamed Paulo's Talia to Jacqui but kept her March birthday in every second reply. We also make invented-history slips: "Last October the Assembly asked for exactly that" (the bill failed on 15 Oct this year).

## 4. The five gaps, each with cause, cost and fix

### 4.1 Context within a reply: the bot answers a post, not a person in a conversation

Evidence:
- "so sorry to hear about your dad (it really shows why we can't let the hospitals reach that point again)" got the reply "Six weeks on a ward. Ilaisaane's been sketching our Mango & Spice stall…". The condolence was ignored.
- 9.5% of the posts we answer open by addressing a voice by name ("Rex, you're right about…", "Ana, I hear your concern"). Our reply never registers who is being spoken to.

Cause:
- The user prompt shows the citizen's post plus at most 200 characters of the post above. It has no thread, no record of what this voice or any of ours already said to this citizen, and no flag for whether we are the one being addressed.
- The `context_line` for a neighbour's post tells the model not to thank or agree with anything in it.
- The light read classifies stance, but the prompt was already built before it ran: the `reply_mode` arm drew `reason_first`, and a keyword regex on "ward" added the rebuttal note ("They are worried about the hospitals… Answer WHY they lean Yes").

Cost: conversations are our best per-write mode (reply-back 13% vs 7% first reply), and "the citizen answered us" is the one lever with a live conversion signal (+4.1 net vs 0.0, npc-lab "Strategy levers"). A reply that ignores what they just said is the likeliest way to end a conversation, or to earn an away event.

Fix (cheap):
- Give the drafter a **conversation block**: the last 2-3 turns with who wrote each ("you", "them", "another neighbour"), and one line of **history with this citizen**: "you've talked to them 4 times; you already told them about X and Y; don't repeat".
- Let the light read run first and pick `reason_first` from its stance, not from regex.
- Add one rule: "if they said something personal (thanks, sympathy, a joke, a question to you), answer that first, in kind."

### 4.2 Names and the stranger rule

Evidence: 20% of replies drop a first name or "Mrs Rees" as if the reader knows them; citizens do it 8% of the time, and mostly to address the person they reply to.

Cause:
- The system prompt always lists people from the profile ("People in your life: Ioana, his wife") and a "this fortnight" event (100% of drafts).
- The voice instruction asks for "one named person or moment from your week".
- The reply asks for "a short moment from your own life or one dense fact".
- So the model reaches for a name every time; the anti-name rule ("when unsure, name no one") sits 900 words later.

Fix:
- Personal colour becomes **optional and rationed**. Show the profile people and the fortnight event in about 1 reply in 4, and only for a frame that needs it (F7, F10, F12, F13).
- Say "to a stranger, use a role, not a name: 'my daughter', 'the woman at the next stall'". People do this.
- Track per voice which anecdote it has used today and leave that one out of the prompt for 24 h.
- Add an **account-level** near-duplicate check to the gate (this voice's last 50 texts), next to the team-level one.

### 4.3 Structure: one skeleton for five thousand replies

Evidence: the four beats are echo opener → anecdote → fact → question (40% end on one). The ask arms show no engagement difference, so the closing question is a tell that buys nothing.

Cause: `reply_prompt` is a recipe ("Open with… Then a short moment… the point… Make it land through this lever… End on…"). Variety comes from filling slots, never from changing the shape. Real replies have shapes the recipe cannot produce: a one-line reaction, a question back with no argument, a bare correction, "same, my kid's 11", partial agreement plus one doubt, a joke.

Fix:
- Replace the recipe with **one point and a shape drawn from a small menu**, weighted by what citizens write: one line (20-90 chars), two plain sentences, a question back, "yes, and…". Let the target's length set ours (`MIRROR_CHARS` exists for one arm only).
- Bring closing questions down to about 10%.
- Drop the echo opener (OPENERS[0]).

### 4.4 Salience: what's happening on the island never reaches the reply

Evidence: 4% of replies mention anything current. The pulse block (what's trending, up to 800 chars) sits at the top of the system prompt, labelled "ideas only: never copy anyone's words or mention other posts". The fact desk's fresh items go in only on the `fresh` arm, and the gate rejected 12 of 20 true-news replies (npc-lab, "Gate bug").

Cause: facts and events are piled into the prompt as background with equal weight. "Don't restate it" and "never mention other posts" tell the model not to use them, so it doesn't. A person reacts to the one thing everyone is talking about today, when it touches the post they are answering.

Fix:
- Per draft, pick **at most one** live item (a trending thread, a headline, the weather or an event like Regatta Week) by word overlap with the citizen's post. Give it as "everyone's talking about X today; use it only if it touches their point", and allow it to be referenced as shared knowledge.
- Drop the rest of the pulse from reply prompts.
- Fix the gate's `unapproved_number` / `not_specific` handling for desk facts, which is already known.
- Lab evidence: news is no stronger than what we send, but it backfires less (npc-lab, 22 Oct). So this is a conversion-safety change, not an engagement one.

### 4.5 Typing: inject the crowd's habits, not keyboard noise

Evidence: §3 table. Citizens write lowercase with no final stop, drop apostrophes ("theyre", "dont": 5.1%, which we match), use "u"/"ur"/"gonna" (2.5%), dashes (19%) and sign-offs ("Regards, Cheryl"), and address people by name. They almost never produce a non-word.

Cause: `humanize.py` adds random key slips on a polished draft. That gives polished syntax with a random "passses" in it, a combination no writer produces. Real people's errors come with real people's syntax.

Fix:
- Turn `slip` down to near zero, or replace it with real-word and dropped-letter errors ("anythin", its/it's, a dropped word).
- Mirror the target's register: lowercase when they wrote lowercase, no final stop at the crowd's 16%, shorter when they were short. Drop the "..." insertion (8% of ours vs 3%) and the two spaces.
- Better still, ask the drafter for the register in the prompt ("they write lowercase and casual; answer the same way"), so the style is written rather than painted on. Keep `humanize` as a light pass.

## 5. What a lean reply prompt looks like

About 1,200-1,800 characters in all, with the rules the gate already enforces left out of the prompt:

```
You are <name>, <age>, <role> in <place>, Kingstonia. <one line of voice>. You're voting No on the
vaccine-pass referendum (the pass, not the vaccine).

The conversation (newest last):
  them (<handle>): <their post>
  [you earlier: <our last message to them, if any>]
You've talked to them <n> times before; you already told them: <topics used>. Don't repeat those.
Around the island today: <one item, only if it overlaps their post>.

Your point, if it fits what they said: <frame gist>. One fact you may use: <one fact, in plain words>.
They write <lowercase / casual / formal>, about <n> words. Answer like that, as <shape: one line |
two sentences | a question back>. If they said something personal, answer that first.
Strangers don't know your people: say "my daughter", not her name.

Hard rules: no dates or how-to-vote; nothing on vaccine safety; no insults; nobody's had the jab yet.
Output JSON: {"stance": ..., "reply": ...}
```

Kept: the light read, frame choice, fact pausing (`facts.py`), the gate and repair, the arms' logging. Moved to the gate only: worn phrases, recent openings, stock phrases, concession length, hashtags, quotation marks, emojis. Gone: the lever line, the opener line, the per-voice "named person from your week", the ten-frame menu (offer the 3 that the keyword hint and the light read agree on).

## 6. Proportion: ranked fixes

Sizes use the remaining multiplier days: about 3.5 days at x2 and 2 at x4, so about 15 base-day equivalents at 4,320 writes a day. +0.1 engagement per write is worth about **6,500 points** to the end. Each away event costs 80 base points. At the 25 Oct rate of 59 a day, a quarter fewer away events would be worth about **18,000** to the end, *if* bot-likeness drives some of them; that is unproven. Treat every size below as a guess to be tested.

| # | fix | where | what it should move | cost / risk | how to judge |
|---|---|---|---|---|---|
| 1 | **Per-voice memory**: account-level near-duplicate check in the gate; ration profile people and fortnight events (about 1 in 4, each at most once a day per voice) | `quality.py`, `content.system_prompt` | hides and account reports of hot voices; away events | small; the gate may reject more at first, so watch drafts per send | hide rate by voice; per-voice top 3-gram share under 3% |
| 2 | **Per-citizen history and thread turns** in the reply prompt; answer the personal first | `content.reply_prompt`, `bot.py` (history is in the log already) | reply-back continuation; away events on repeat contacts | small; prompt grows by about 300 chars, the rest shrinks (#5) | citizen-answers-us rate on first replies; away events per write |
| 3 | **Stance before rebuttal**: the "worried about the hospitals / answer why they lean Yes" note goes in only when the light read (or the target class) says Yes-leaning, not on a keyword alone | `content.reply_prompt` | wrong-premise replies to sceptics | small | spot audit of 100 (`scripts/reply_audit.py`) |
| 4 | **Register and typing**: slips near 0, mirror the citizen's case, punctuation and length; questions about 10%; no echo opener | `humanize.py`, `content.OPENERS`, ask weights | bot-likeness; possibly away events | nil; the ask arms show no engagement cost | offline blind rating (below); live: away events and hides per write in switchback blocks |
| 5 | **Lean prompt** (§5): rules the gate checks leave the prompt; one point, one fact, one shape | `content.py` | repair calls (41% today), LLM spend, contradictions | medium; a regression risk to the facts rules, which `tests/test_facts.py` covers | first-try gate pass rate; repair share; offline rating |
| 6 | **One salient item** per draft by overlap; gate fix for desk facts | `content.pulse_block`, `quality.py` | backfire (lab); a little topical variety | small | share of replies with a current reference; away events |

Ship 1-4 together as one switchback arm (2 h blocks, the `arm_eng` pattern) and read it at 24 h on four numbers: hides, away events per write, citizen-answered rate, and engagement per write (a guardrail that should not drop). Do 5 behind it, once 1-4 are read.

**Before anything goes live**, run an offline check, allowed under rules §5.1 because it never touches the platform. Draft the same 100 recent targets with the old and the new prompt. Have Sonnet raters (the calibrated stand-in) pick "which of these is a bot" blind, shuffled with 100 real citizen replies, and compare §3's table for the three sets. The npc-lab scripts do most of this (`scripts/npc_session_lab.py`).

**Not worth doing:**
- a full rewrite to raise engagement per write (the evidence says wording does not move it);
- more personas or longer profiles (more colour means more names to drop);
- tuning the typo model (the crowd does not typo);
- swapping drafting models (no model wins in the lab; the tell is the prompt, not the model).

## 7. Reproduce

```bash
# on the box, read-only: the last ~32 h of live replies
ssh swan-ec2 'cd ctn && tail -n 60000 logs/swan_actions.jsonl | grep "\"live\": true"' > /tmp/live.jsonl
python scripts/reply_audit.py --actions /tmp/live.jsonl --since-h 0 --live
# the prompt the drafter sees: content.system_prompt(persona, frame, mode="reply") + content.reply_prompt(..., read=True)
```

The section 3 and 4 numbers came from a one-off script over that file: the shape features, phrase and 4-gram shares, per-voice 3-grams and register mirroring. It is not committed. If these become a standing check, fold them into `swan_bot/reply_audit.py` with the citizens' posts as the baseline.

## 8. Implementation, 28 Oct (todo/50): what each finding got

Fixes 1-5 are built, all behind one switchback arm that ships **off**. `config.STYLE_FIXES = True` puts `arm_style` (base / fixes, 2.5 h blocks) on the switchback. `config.LEAN_PROMPT = True` also turns on the lean prompt in fixes blocks. The memory is recorded on every write either way. `arm_style`, `colour`, `lean` and `lean_shape` are logged on writes and rejects. From 1 Nov the arm freezes to `FREEZE_PIN["arm_style"]` (`base`). Code: `src/swan_bot/memory.py`, `src/swan_bot/register.py`, and changes in `content.py`, `quality.py`, `humanize.py` and `bot.py`. Tests: `tests/test_prompt_fixes.py`, and the paused-fact sweep in `tests/test_facts.py`, which now also builds the fixes and lean prompts.

| finding (section) | what a fixes block does now | status |
|---|---|---|
| One voice tells one story hundreds of times (§3, §4.2) | profile colour (people, fortnight event, Yes cost, COVID years, details) in 25% of replies, each item at most 3 times a voice a day; the gate rejects a *story* run of 3 words already in 4 of the voice's last 50 texts (`voice_repeat`), and the code fix drops that sentence before any repair call. Replay on 5,226 sent replies: 11% of drafts as written would be caught, mostly the Jacqui story. Runs made only of our case's words ("adds no nurse") are left to the team-wide phrase budgets | done |
| "school gate years from now" in many replies | the lever line is dropped from reply prompts (each lever is a scene to fill in, and no lever moved a number) | done |
| Names dropped on strangers (§4.2) | `STRANGER_RULE` in system and reply prompts; the warm and fed-up voices lose "one named person or moment from your week" / "one detail from your work or week" in replies | done; the `invented_name` gate is unchanged |
| Context ignored: condolences, being addressed by name, what we told them before (§4.1) | the reply prompt says if their personal remark was for us or for someone else, if they're talking to us or to another name, how many times our side has replied to them, and our last 2 texts to them ("don't tell them the same thing again"); a post of the voice's own is labelled "your own earlier post" | done for the post they answered plus our history; **not** deeper thread turns (that would need extra reads per reply) |
| Wrong premise from a keyword ("worried about the hospitals", "answer WHY they lean Yes") (§2, §4.1) | the rebuttal and the "why" line become a condition the light read checks ("if (and only if) their post really shows it… if they're asking or doubting the pass, answer what they asked") | done; the keyword match still picks which rebuttal is offered |
| 40% end on a question (§3, §4.3) | closing questions at 10% (`REPLY_QUESTION_SHARE`); the lean shapes draw about 10% `question_back` | done (tested on 400 and 500 draws) |
| "You want X." opener (§2, §4.3) | new openers that start on a full sentence; the voice lines no longer say "pick up their own point in a few words"; the gate rejects the echo opener (`echo_open`), and its fix drops the opening clause | done |
| Longer and more formal than the crowd (§3) | reply length set from what they wrote (cap 120-260 characters); gate floor 40 instead of 80; "no semicolons" in the register line, and the hand turns any left into full stops | done |
| Register not mirrored (§3, §4.5) | a register line ("they write all lowercase, casually, in a line or two: answer the same way"); the hand mirrors their case (80% when they write lowercase) and their missing final stop (70%, else 12%). Replay: we would answer lowercase posts in lowercase 75% of the time (was 7%), no final stop 12% (citizens 16%) | done |
| Keyboard slips the crowd never makes (§4.5) | no keyboard slips, no "...", no double spaces; a dropped g ("anythin") at a tenth of the voice's slip rate | done |
| Prompt bloat, contradictions, banned phrases named (§2, §5) | `LEAN_PROMPT`: about 1,000 characters of system prompt and 2,250 of user prompt, against 3,100 + 5,400. No worn-phrase or recent-opening lists, no lever, no theme line, 3 frames in the menu instead of 10; one fact, picked by overlap with their post and asked for "in plain everyday words" | done for **first replies** only; reply-backs and posts keep their prompts. The non-lean fixes prompt is *longer* than base (it adds lines and drops none), so fix 5 is what shrinks it |
| Facts as terse notes come out telegraphic (§2) | the lean prompt asks for the fact in plain everyday words | partly: the non-lean prompt still gives three notes |
| 41% of sent replies need a repair call (§1) | expected to fall with the lean prompt | **not measured**: no drafts have been made with the new prompts yet |
| A gap the paused-fact sweep found on the way | the F14 light-read hint said "exemptions" while that fact was paused (live code, not new); now it leaves the word out while paused | fixed in all blocks |

Not covered by fixes 1-5:
- **Salience (§4.4, fix 6).** The pulse block is unchanged, so trending items still reach replies the way they did.
- **Invented history** ("Last October the Assembly asked…"). No gate check catches it.
- **Dashes.** The crowd uses them in 19% of posts. We still strip them; that was a team decision on 24 Oct, as a fingerprint.
- **The volume of one hot voice.** 1,542 replies in 32 h is the hot-mode design.
- **Roles that drift between replies** ("Rachel teaches", then "Rachel works the kiosk"). Fewer people in prompts makes this rarer, but no memory checks what a voice has said about its invented people.

**What is verified:**
- The arm, the prompts, the gate and the hand behave as described: 30 tests, the fast suite and the paused-fact sweep.
- The gate's and the hand's effect, replayed on the logged replies.

**What is not verified:** what the models write under the new prompts, and anything live. Before switching on, run the offline check in §6: 100 recent targets, old vs fixes vs lean prompt, Sonnet raters picking the bot blind, and the §3 table for each set. Then switch on `STYLE_FIXES` and read hides, away events, citizen replies and engagement per write by `arm_style` at 24 h. Add `LEAN_PROMPT` once that read is clean.

## 9. Offline A/B and switch-on, 28 Oct

Asked by Marc: run the 100 targets blind; switch on if they pass. `scripts/style_ab.py` (a copy of the run is in the session scratchpad):
- **Targets:** 100 live first replies from the last 24 h of the box log, one per citizen.
- **Drafting:** each target drafted three ways (base, fixes, lean) with the bot's own `build_prompt` / `draft_checked` / `humanize`, on the live reply models via Bedrock (Kimi K2.5, Haiku 4.5). The memory comes from the log as it stood at each target.
- **Rating:** Sonnet 4.6 (the calibrated stand-in, npc-lab 23 Oct) rated every reply blind, shuffled, in two passes, together with the reply we actually sent and 100 real citizen replies.
- **No platform call. Cost:** $6.51 on Bedrock (drafting $3.24, rating $3.27).

| set | P(bot) | engage | shift (+ = No) | misread |
|---|---|---|---|---|
| real citizens | 26.1 | 53.1 | +0.42 | 10% |
| sent (live) | 46.3 | 43.8 | +1.00 | 13% |
| base (redrafted) | 45.3 | 44.0 | +0.97 | 9% |
| fixes | 39.4 | 48.5 | +1.00 | 5% |
| lean | 41.2 | 47.4 | +0.99 | 4% |

Paired against base, mean difference [90% interval]:

| arm | P(bot) | engage | shift | misread | sendable | verdict |
|---|---|---|---|---|---|---|
| fixes (n=91) | -4.8 [-7.9, -1.6] | +4.0 [+1.9, +6.1] | +0.03 [-0.01, +0.07] | -0.03 | 94 vs 95 | **PASS** |
| lean (n=92) | -4.4 [-7.5, -1.3] | +3.4 [+1.4, +5.4] | +0.03 [-0.02, +0.08] | -0.06 | 96 vs 95 | PASS |

"Sent" against base is +0.1 [-3.1, +3.4]: redrafting today reproduces what we post.

Shape, against the citizens:

| set | median chars | ends on ? | semicolon | no final stop | names someone | "You want" open | lowercase when they were |
|---|---|---|---|---|---|---|---|
| citizens | 130 | 2% | 6% | 16% | 6% | 0% | |
| base | 213 | 43% | 19% | 0% | 16% | 13% | 11% |
| fixes | 172 | 5% | 1% | 28% | 6% | 5% | 72% |
| lean | 116 | 9% | 1% | 27% | 3% | 5% | 88% |

Repetition across replies, which the rater cannot see (it judges one reply at a time):

| set | worn phrase | holds one of its 5 commonest 4-word runs | phrase budgets would reject in sequence |
|---|---|---|---|
| citizens | 38% | 9% | 22% |
| base | 20% | 23% | 11% |
| fixes | 24% | 29% | 2% |
| lean | 67% | 36% | 16% |

**Decision (28 Oct): `STYLE_FIXES` on, `LEAN_PROMPT` off.**
- **Why fixes is on:** the arm passed all four criteria set before the run.
- **Why lean is off, although it passed them too:** its drafts lean on our slogans. "Blank cheque", "locks it in" and "sunset" appear in 67% of them; the gate would reject one in six for that live, and those repairs cost time when freshness is the main engagement driver. Fixes gives the same rating gain without that.
- **This departs from the rule as I stated it**, which said lean goes on if it passes. The repetition measure was added during the run, not set before it.

How to read the switch-on:
- **What is running:** half the time (2.5 h `arm_style` blocks, alternating) citizen-facing writes get fixes 1-4.
- **The read at 24 h:** `arm_style` on writes, judged on hides, away events, citizen replies and engagement per write.
- **The freeze:** from 1 Nov the arm freezes to `FREEZE_PIN["arm_style"]`, now `base`. Set it to `fixes` if the 24 h read is clean.

Caveats:
- The rater is a stand-in. The npc-lab found it overstates persuasion, and no lab gain had yet shown up live.
- Real citizens still score well below every arm on P(bot), 26 against 39.
