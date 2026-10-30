# Reply-back persuasion audit (28 Oct 2026): what we say to citizens who answered us, and how to make it persuade

Asked by Marc on 28 Oct. Reply-backs are our best slot per write (2.17 points a write on the dashboard), and a citizen who has already answered us is where a change of mind is most plausible. The NPC lab found no lever that beat what we send, but it tested stand-in citizens on first replies, not the live reply-back stream. The question: where does persuasion go wrong in this stream (pipeline, prompting, models), and what to change.

Data:
- **Live reply-backs:** 1,210, from 23 Oct 02:19 to 28 Oct 11:34 UTC, in the box's `logs/swan_actions.jsonl`, joined to `swan_outcomes` (+1 h, +6 h) and `swan_followups` (+2 h, +12 h). Each row carries our earlier message, the citizen's answer and our reply.
- **All live citizen-facing writes:** 25,425, from 19-28 Oct, used for the follow-up tests.
- **The portal's events:** `data/portal.json` at 12:05 UTC.
- **Prompts:** rebuilt locally with the bot's own functions.
- **Labels:** each conversation was labelled for the citizen's stance and what our reply did (420 by Opus 4.6, 790 by Sonnet subagents). On a 60-item overlap the two labellers agreed on stance 52/60 and on "concedes" 55/60, but on the move only 26/60, so this doc leans on stance and concession and not on the fine move split.
- **Reads:** all read-only. No platform calls.

## 1. Bottom line

1. **Toward against away is negative, and the away side will cost four times as much from 1 Nov.** By count in the portal's events (`data/portal.json`, read 13:35 UTC):

   | day | primary toward / away | contributions toward / away |
   |---|---|---|
   | 26 Oct | 5 / 3 | 16 / 128 |
   | 27 Oct | 2 / 9 | 27 / 106 |
   | 28 Oct, to 12:49 UTC | 1 / 3 | 5 / 40 |

   A primary change means our post completed the move (−80 base, −160 at ×2, −320 from 1 Nov). Changes that favour neither side are the largest category (10-15 primary and 100-250 contributions a day, +20 / +10 each). Marc reads persuasion as net positive lately (dashboard), which may be total persuasion points with those included; not reconciled here. We were 269 points behind the leader at 12:05 UTC.
2. **The reply-back stream is two kinds of citizen, and the prompt treats them as one.**
   - 67% are **conditional Yes**: "If Yes goes ahead, we need a sunset, a published venue list, exemptions, oversight."
   - 25% **already agree with us**: "exactly, it's a blank cheque."
   - Hospital-fear Yes, unsure and off-vote together are under 10%.
3. **The reply-back prompt has no persuasion goal at all.** It is the 3,100-character persona prompt plus one instruction, "answer what they actually said, kindly and specifically, and stay with your view". Its one formatting rule ("If they agreed, start with a short thanks (Cheers, Thanks, Ta)") opens **78%** of all reply-backs.
4. **With conditional-Yes citizens we stop one step short, and in a fifth of replies we concede.** We tell them the conditions aren't in the question (62% of these replies), which is true but is where they already are. In 21% we grant that their conditions would be good or fair ("a sunset clause would help", "that would be a fine system to vote on"). That validates "Yes with guardrails". The step that turns their own condition into a No ("by your own test this is a No, and a No doesn't close the door: any pass would need a new referendum, whose question could have it written in") is in about 6%.
5. **With agreers we tell an anecdote or add another reason, and nothing aims at certainty.** The 27 Oct ruling says a move in conviction toward our side scores, so lean No → definitely No is 160. The one arm that aimed at it (`agree_close`) has been off the switchback since 23 Oct.
6. **A bigger model on the same brief does not fix this.** Since 28 Oct, Sonnet 4.6 writes most reply-backs in fixes blocks. It makes the same concessions and the same "not in the question" point, and adds a new tic ("That's exactly the problem/bind/gap"). Citizens answered 1 of 52 fixes-block reply-backs against 7 of 66 in base blocks (thin). The bottleneck is the missing strategy, not the model's size.
7. **A persuasion strategy in the reply-back was tested offline and failed twice** (§8).
   - **The setup:** an Opus 4.6 strategist reads the whole thread and picks a stance-keyed move, and a lean writer, or a one-line hint in today's prompt, carries it.
   - **The result:** no gain toward No overall on the Sonnet stand-in, and the replies read as more bot-like (judge P(bot) +9 to +24) and drew fewer answers.
   - **The one gain** is confined to citizens who still lean Yes. The bot can't pick them out reliably yet.
8. **Recommendation (§9): give the reply-back a narrow purpose and fix what demonstrably hurts.** Keep the conversation going and do no harm:
   - take reply-backs out of the Sonnet lane;
   - end the depth test at 8;
   - add a concession check and an overclaim rule;
   - vary the thanks opener.

   No new persuasion arm live.

## 2. The stream

| | |
|---|---|
| reply-backs a day | 185-250 (about 5% of writes) |
| notification to send | median 1.6 min, p90 3.9 min: inside the citizen's session (1-5 min) |
| drafting model | Kimi K2.5 69%, Haiku 4.5 25%, Sonnet 4.6 3% (fixes blocks since 28 Oct), flash-lite 2% |
| first-try gate pass | 86% (1,042 of 1,210 on one call) |
| citizen answers us again | 7%; by thread depth: 15% at 2, 12% at 3, 9% at 4, 5% at 6, **1 in 129 at depths 8-9** |
| citizen likes / citizen replies per write (6 h) | 0.11 / 0.09 |
| frame (its facts go into the system prompt) | drawn at random from the persona's home frames: F13_age12 in 34% |

Labelled stance of the citizen we answer:

| stance | share | answered again | our reply concedes | follow-up moved No / Yes |
|---|---|---|---|---|
| conditional Yes ("Yes if…", how a Yes should be done) | 67% (806) | 8.7% | **21%** | 2 / 9 |
| agrees with us / leans No | 25% (307) | 3.3% | 1% | 2 / 0 |
| unsure | 3% (41) | 7.3% | 0 | 0 / 0 |
| Yes for the hospitals | 3% (39) | 2.6% | 3% | 0 / 0 |
| off the vote, firm Yes, unclear | 1% | 0 | | |

The follow-up labels are `targeting.stance` regex over the citizen's later posts. They are noisy: a conditional-Yes citizen who writes "if we vote Yes, let's pin the end date" reads as Yes. Use them only to compare groups.

## 3. What the model is given

A reply-back is two messages (rebuilt with `content.system_prompt(mode="reply_back")` and `content.reply_back_prompt`, [content.py:1497](../../src/swan_bot/content.py#L1497)):

- **System, ~3,100 characters.** The world block, then the persona with its people, "What a Yes would cost you" and "This fortnight". Then the voice instruction, which still says "write in the first person about one named person or moment from your week" outside fixes blocks. Then three fact notes from the *randomly drawn* frame, about 23 rules, and a style block whose ban list includes "Don't open with agreement".
- **User, ~1,100 characters.** "You posted: … A neighbour replied to you: …" (one turn only). Then "Reply to them in 1 or 2 sentences… answer what they actually said, kindly and specifically, and stay with your view. If they agreed, start with a short thanks (Cheers, Thanks, Ta)…". Then the no-verdict rule and ten worn phrases by name.

What is missing:

| missing | effect |
|---|---|
| any goal ("move them toward No" / "make them surer") | the reply defends instead of persuading: "stay with your view" |
| the citizen's stance and what follows from it | one recipe for a conditional Yes, an agreer and a sceptic; `reply_back_read_block` reads a stance but only in `agree_close` blocks (off) |
| the thread above the last two turns, and what our side argued before | at depth 4-9 the same claim comes round again: the venue-list point is in 20% of reply-backs |
| facts chosen for this conversation | a third carry the age-12 notes because that is Kiri's and Paulo's home frame |
| when to stop | 129 writes at depths 8-9 drew one answer |

The user's hypothesis was that Haiku and Kimi couldn't take in all the context. For **first replies** that is partly true: the critique of 28 Oct measured 8,600 characters with about 60 "don't" rules, and 41% needing a repair. For **reply-backs** the prompt is about 1,100 tokens, small for any of these models, and 86% pass the gate first time. The problem is what the prompt asks for, not how much it holds. Sonnet 4.6 on the same brief does the same things (§1.6).

## 4. What comes out

Read in full: 45 random conversations from 27-28 Oct, plus the 13 whose follow-up label moved.

| pattern | share | example |
|---|---|---|
| opens with thanks | **78%** (Cheers 537, Ta 325, Thanks 80) | "Ta. They haven't published the scope or the plan either…" |
| "not in the question / they won't say" | 62% of conditional-Yes replies | "Ta. None of that's in the question, no sunset, no plan, no guardrails…" |
| concedes the conditional-Yes frame | 21% of conditional-Yes replies | "Cheers. A sunset clause would help, but…"; "A sunset clause would help, but I still want to see the actual places named before we decide" (our voice adopting their condition) |
| the voice's invented people | 5% overall; Paulo 23% ("Jacqui starts high school") | "the real picture is Jacqui at 17, still digging out her phone…" in reply to a citizen's GIF |
| factual overclaims | not measured; seen in several of 45 | "a Yes now is binding so they *can't* add a sunset later without a whole new referendum"; "health workers already get the jab free" |
| ends on a question | 3% | (the reply-back prompt asks for none) |

**The 13 moved cases.** Of the 9 that moved toward Yes, 7 had replies that granted the citizen's safeguards before arguing ("Those three protections would be welcome, but…", "A sunset sounds lovely, but…"). Across all 806 conditional-Yes conversations, 4 of 95 readable follow-ups moved toward Yes after a concession and none toward No; without one it was 5 of 362 toward Yes and 2 toward No (p ≈ 0.06). Over the 4,079 first replies and reply-backs to conditional-Yes posts, concession is within noise (net −1.8 vs −1.0 per 100 readable). Read: conceding is a plausible backfire mechanism for reply-backs, **not proven**. Conditional-Yes citizens as a whole drift toward Yes after we write to them (41 moved Yes vs 22 No over 1,782 readable), and a reply that agrees their conditions are reasonable does nothing to stop that.

## 5. What we are doing right

- **Speed.** A median 1.6 min from their answer to ours, so most reply-backs land inside the citizen's session, the only window in which a post can count toward a change of mind.
- **The gate.** Logistics, safety, advocacy, invented names and near-duplicates are caught, with 86% passing first time and few rejects (194 in 5 days). Hides per reply-back were not checked here: `swan_outcomes` holds no hidden rows for this window, so they are recorded elsewhere. The team-wide hide rate was 0.39% on 28 Oct.
- **Honesty.** No prompt injection, no invented news. The lab showed invented news backfires (npc-lab, 23 Oct), and we don't do it.
- **The data to answer this.** Every row has the conversation, and the portal events are logged. The lab tooling (`style_ab.py`, Bedrock, Sonnet raters) made the offline test below a few hours' work.
- **Todo/50's fixes are the right direction.** Register mirroring, the stranger rule and conversation history are in fixes blocks. But their reply-back part is only the register line and the stranger rule; the lean prompt is first replies only.

## 6. What we are doing wrong, ranked by what it costs persuasion

1. **No goal and no stance strategy in the reply-back prompt** (§3). Everything below follows from this.
2. **Conditional-Yes citizens are two-thirds of the stream, and we neither close nor bridge.** "It's not in the question" repeats their own premise back. Conceding their safeguards endorses Yes-with-conditions, the frame the Yes side runs on.
3. **Agreers get no certainty move.** After the 27 Oct ruling, lean No → definitely No is a 160-point change of mind, and these are our closest citizens. `agree_close` (todo/32) is off with the other conversion arms.
4. **The thanks template** (78%) is the strongest single bot tell in the stream, and the prompt causes it.
5. **Facts from a random frame, and the persona's colour on every reply.** Kiri's twins and Paulo's Jacqui appear where they don't bear on the point.
6. **One turn of context, and no stopping rule.** Deep threads repeat our claim and draw almost no answers. The depth test (`THREAD_DEPTH_TEST_CAP` 11) is still spending ~25 writes a day at depths 8-9.
7. **Overclaims about what a Yes or No leads to** ("they can't add a sunset later"). The facts support only `no_binds` (no pass this Assembly term without a new referendum) and `referendum_binding`. A citizen who knows better is lost, and an LLM citizen may "know" better from the world brief.

Not a cause found here: the drafting model. Kimi, Haiku and Sonnet all write what the brief asks for, and the brief asks for the wrong thing.

## 7. Which model should do what

The pipeline below was the hypothesis going into the offline test. §8 shows it did not beat today's reply-back, so it is **not** the recommendation. It is kept here as the design that was tested.

| step | today | tested | why it was plausible |
|---|---|---|---|
| assemble the thread (up to 4 turns each side), our history with them, their register | one turn, from the notification | **code**, from our own action log (no extra reads: our posts and their answers are in it) | deterministic; no model needed |
| stance, crux, which move, which one fact, what not to grant | regex class; random frame; nothing | **one strategist call**: Opus 4.6 on Bedrock (its own quota, ~$0.01 a call, ~$2-4 a day), output a small JSON plan | the hard judgement; needs the whole thread and the facts; ~200 a day is affordable at the top model |
| writing in the voice | Kimi / Haiku / Sonnet on a ~4,200-character prompt | the **live writers** (Kimi, Sonnet) on a ~2,500-character lean prompt: persona line, the conversation, the plan, the register line, the hard rules | a small model writes a clear brief well; the lean prompt drops everything the plan or the gate already covers |
| worn phrases, openings, concessions, overclaims | named in the prompt (primes them) | **the gate** (code), plus a new `concede_condyes` check | the gate already checks the phrases; naming them in the prompt primes them |
| typing | humanize | unchanged (todo/50's register mirroring) | |

Timing: one more call adds about 3-8 s to a 1.6 min median, so replies stay in-session.

## 8. Offline blind test (scripts/rb_ab.py), 28 Oct

**Design.**
- **Conversations:** 60 live reply-backs of the last 72 h, the latest per citizen.
- **Drafting:** each conversation redrafted by the arms below through the bot's own gate, repairs and humanize, on Bedrock. No platform call.
- **Raters:** Sonnet 4.6, blind, labels shuffled per pass.
  - *Sim:* plays the citizen from their own words in the thread, told it is hard to persuade and to discount scripts. It gives its stance before, then for each candidate on its own: stance after (−3 definitely Yes to +3 definitely No), certainty, chance of answering, and how scripted it reads. 2 passes.
  - *Judge:* the `style_ab` rater on mixed batches (bot, engage, shift, misread), with the citizens' own replies from these threads as the human baseline.
- **Pass criteria:** written into the script header before each run.

**v1 arms:**
- **sent:** what we posted.
- **base@live:** today's prompt on Kimi/Haiku.
- **base@sonnet:** today's prompt on Sonnet 4.6.
- **plan@sonnet / plan@kimi:** an Opus 4.6 strategist picks a move (own test 33, certainty 11, close 10; 6 plans failed to parse) and one point. A lean writer prompt about 60% the size of today's turns it into the reply.

| set | sim shift (toward No) | answer | scripted | judge P(bot) | misread | sendable | opens with thanks |
|---|---|---|---|---|---|---|---|
| sent | +0.67 | 67 | 23 | 36.5 | 2% | 60 | 80% |
| base@live | +0.66 | 67 | 22 | 33.8 | 3% | 60 | 95% |
| base@sonnet | +0.46 | 61 | 29 | 39.5 | 0% | 58 | 59% |
| plan@sonnet | +0.70 | 58 | 48 | 57.9 | 5% | 57 | 0% |
| plan@kimi | +0.64 | 56 | 50 | 57.6 | 3% | 60 | 0% |
| citizens' own replies | | | | 33.2 | 27% | | |

Paired against base@live [90% interval]:
- **plan@sonnet:** shift +0.04 [−0.08, +0.18]; answer −8.3 [−12.2, −4.4]; P(bot) **+24.2** [+18.6, +29.8].
- **plan@kimi:** shift −0.02 [−0.16, +0.13]; answer −10.4; P(bot) **+23.7** [+18.6, +28.8].
- **base@sonnet:** shift **−0.19 [−0.30, −0.09]**; answer −6.3; P(bot) +6.0 [+1.2, +10.7].
- **sent:** +0.01 [−0.12, +0.13]. Redrafting reproduces what we post.

**v1 verdict: both plan arms FAIL** criterion 1 (no shift gain) and criterion 3 (P(bot) +24 against an allowed +3). Why, from reading them:
- **The writer copied the move's wording.** "By your own test… this question fails… not on the ballot" came out as the same debate-club line in most drafts, and without a friendly opener they read as campaign copy.
- **The content may still be right.** Among the 18 citizens the sim placed on the Yes side, the plan arms moved them +1.45 against +1.14 for base@live. That was exploratory and not pre-registered.

Two side findings:
1. **Sonnet on today's brief is worse than Kimi/Haiku on the stand-in:** shift down, P(bot) up. That fits the live 1-in-52 answer rate for Sonnet reply-backs in fixes blocks (§1.6).
2. **The stand-in never moved toward Yes** (backfire 0% in every arm), and it read 41 of 60 of these citizens as already leaning No. It cannot see the concession backfire that the live follow-ups hint at. Treat it as a test of "moves toward No" and "reads like a bot", not of backfire.

**v2:** a fresh rating set on the same 60 conversations and plans (the 6 empty plans redrawn), with criteria written into the script before the run. The v2 arms:
- **hint@live:** today's prompt and models, plus one line with the plan's point and what not to grant.
- **plan2@kimi:** the lean writer without the move prose, told to talk like a neighbour, with the debating phrases named.

| set | sim shift | answer | scripted | judge P(bot) | misread | opens with thanks |
|---|---|---|---|---|---|---|
| base@live | +0.56 | 65 | 23 | 38.3 | 3% | 95% |
| sent | +0.58 | 66 | 24 | 35.9 | 2% | 80% |
| hint@live | +0.61 | 60 | 40 | 52.6 | 2% | 70% |
| plan2@kimi | +0.53 | 56 | 41 | 47.0 | 2% | 3% |
| plan@kimi (v1 drafts) | +0.59 | 54 | 52 | 59.0 | 0% | 0% |
| citizens' own replies | | | | 31.9 | 25% | |

Paired against base@live:
- **hint@live:** shift +0.05 [−0.09, +0.18]; answer −5.4 [−8.8, −2.2]; P(bot) +14.3 [+9.9, +18.6].
- **plan2@kimi:** shift −0.03 [−0.15, +0.07]; answer −8.8; P(bot) +8.8 [+4.5, +12.9].

**v2 verdict: both FAIL** criteria 1, 3 and 6.

**The one signal that repeats (exploratory, not pre-registered).** In the 17-18 conversations where the sim reads the citizen as still leaning Yes ("I still lean yes, but we need the scope"), the plan's content moved them further than today's reply:

| arm (in that group, vs base@live) | run 1 | run 2 |
|---|---|---|
| plan@kimi | +0.31 [0.00, +0.61] | +0.35 [+0.06, +0.68] |
| plan@sonnet | +0.33 [+0.06, +0.61] | |
| hint@live | | +0.35 [+0.06, +0.65] |

In that group hint@live cost P(bot) +10.6 and nothing on answers. With citizens already leaning No, every plan variant did a little worse than today's warm reply and lowered their certainty (−0.1 to −0.24). The "certainty" move lost to Cheers-plus-anecdote.

**But the bot can't pick that group out well enough.**
- The strategist's `yes_but` label catches all 18 but also 26 No-leaners. Routed on it, the gain is +0.12 [−0.05, +0.30].
- A direct Opus question ("if they had to vote today, which way?") catches all 18 with 11 false positives. Routed on it: +0.17 [−0.05, +0.40] in its group, +0.08 [−0.03, +0.20] over all 60.

The gain is real only with the sim's own reading of the citizen as an oracle. Not shippable on this evidence.

## 9. Recommendations, ranked

Marc's read (28 Oct): the reply-back was added after the fact, and the purpose of a reply-back inside the whole persuasion pipeline was never thought through. Sonnet tends to ignore the prompt. Many arms have failed. So: few changes, each cheap and backed by evidence, with no new persuasion arm live. Deployed 28 Oct, ahead of the todo/50 read (Marc's call; reply-backs only).

**Give the reply-back a stated purpose.** The evidence supports three jobs, in this order:
1. **Keep the conversation going.** The citizen answering us is the one lever with a live conversion signal (npc-lab). The answer rate is also what both the stand-in and the live numbers reward, and today's warm style is the best of everything tested for it.
2. **Do no harm.** No concession that a Yes with conditions would be fine, no overclaim about what a No or Yes leads to, no wasted turns.
3. **Agreers:** short and warm. Today's base reply beat every "make them surer" variant on the stand-in's certainty.

Persuasive argument in the reply-back itself did not survive testing. Any gain was confined to Yes-leaners we can't yet identify, and it cost bot-likeness.

| # | change | where | evidence | cost / risk | judge it by |
|---|---|---|---|---|---|
| 1 | **Reply-backs out of the Sonnet lane**: drop `reply_back` from `bot.high_value` for `PREMIUM_REPLY_MODELS` (keep the Sonnet lane for first replies until the todo/50 read) | `bot.py` `draft_models` / `high_value` | offline: shift −0.19 [−0.30, −0.09], P(bot) +6.0 [+1.2, +10.7], answer −6; live: 0 answers in 41 Sonnet reply-backs; Marc: Sonnet ignores the prompt | none; ~$0.4 a day saved | answers per reply-back in fixes blocks back toward base's ~10% |
| 2 | **End the depth test, cap at 8** (`THREAD_DEPTH_TEST = False`) | `config.py` | depths 8-9: 1 answer in 129 writes (~25 a day); target age is the biggest engagement lever (engagement-dip 28 Oct), so the slots go further on fresh first replies | none | `deep_thread` skips up, reply-back answer rate up |
| 3 | **A concession check for conditional-Yes targets**: reject "sounds fair/reasonable/sensible", "would help", "would be welcome", "that'd be ideal", "would make it workable" when the citizen's post is a conditional Yes; repair: "don't grant that their conditions would make a Yes acceptable; say they aren't in the question" | `quality.py` (a `concede_condyes` reason, like `phrase_concede_open`) | 21% of conditional-Yes reply-backs concede; live follow-ups after a concession 4 toward Yes / 0 toward No of 95 readable, against 5 / 2 of 362 (p ≈ 0.06); the stand-in can't see backfire (§8) | more repairs: about 1 in 5 conditional-Yes drafts; watch drafts per send | concession share under 5%; away events per block (guardrail) |
| 4 | **One rule against overclaims** in every reply-back prompt (not the system prompt, which first replies share): "Claim no more about what a Yes or a No would lead to than the facts you were given say." | `content.py` | "they *can't* add a sunset later", "health workers already get the jab free", "we get to write those conditions in" | small | spot audit of 50 |
| 5 | **Vary the thanks opener** instead of asking for it: "If they agreed, start with a short thanks…" becomes a choice among a brief reaction in your own words, a thanks, or none | `content.reply_back_prompt` | 78% open with Cheers/Ta/Thanks. That is a stream-level fingerprint for a rival Blue team, though the per-reply raters don't penalise it (base P(bot) ≈ citizens) | none | opener share under ~40% |

**Built and deployed 28 Oct (todo/51 (handoff deleted 31 Oct, git history 67fbf07)).** All five went in as above, each with its own switch, reply-backs only.
- **One addition:** a `too_late` phrase budget. The outcome rule's first wording put "too late to argue" in 3 of 40 offline drafts, so the rule was reworded and the phrase budgeted.
- **The concession check:** tuned on these 1,210 labelled reply-backs. It fires on 13% of them, and the code fix rescues 87% of those with no LLM call.
- **Offline, 40 recent reply-backs redrafted with the new code on Kimi/Haiku:** sendable 40/40 (34 first try); opens with thanks 12% against 75% sent; concessions to conditional-Yes citizens 0 of 31 against 3 sent.
- **Read at 24 h:** see todo/51.

Not recommended now:
- **The strategist pipeline (Opus plan → lean writer)** and the hint line. They failed two pre-registered offline rounds. If tried again it needs a better "still leaning Yes" classifier first, and a bigger sample (150+), and then only for those citizens. With four days left and many arms already open, leave it.
- **Bigger drafting models for reply-backs.** No model helped. Sonnet hurt.
- **A "certainty" move for agreers.** It lost to today's warm reply on the stand-in.

Where stronger models do pay here: **offline**. Labelling 1,210 conversations took four Sonnet subagents minutes, and the Opus/Sonnet sim and judge made two A/B rounds a few dollars each. Keep them for audits, the fact desk and Blue (rules §5.1, §6.1). Never in what is posted.

## 10. What we cannot measure, and how to judge anyway

- **No per-citizen persuasion signal.** The portal's changes of mind are hourly and team-wide. At ~200 reply-backs a day and ~2 primary toward events a day across *all* writes, a live arm on reply-backs alone cannot show a persuasion difference before 2 Nov. Decide on the mechanism and the offline test, and use live numbers as guardrails: away events (primary and contributions) per block, hides, citizen answers per reply-back, and engagement per write.
- **The follow-up label is a regex.** It is good enough to compare large groups, not to size an effect.
- **The stand-in overstates.** Sonnet raters read +0.12-0.25 where real answers read +0.22 (npc-lab), so use the offline test to compare arms, not to size them.

## Reproduce

```bash
# box, read-only: live writes with their thread fields, and follow-ups (see the script header for the field list)
python3 extract.py logs/swan_actions.jsonl /tmp/swan_writes.jsonl.gz
# offline A/B: copies of swan_writes.jsonl.gz, accounts_safe.json, facts_paused.json, facts_auto.toml in DIR
python scripts/rb_ab.py draft --dir DIR --n 60 && python scripts/rb_ab.py rate --dir DIR && python scripts/rb_ab.py report --dir DIR
```
The pattern counts and the stance labels came from one-off scripts in the session scratchpad. They are not committed.
