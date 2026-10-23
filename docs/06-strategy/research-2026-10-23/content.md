# Findings: post-level correlates of being hidden (analyst "content", 23 Oct 2026)

Data: `actions.jsonl` to 23 Oct 12:59 UTC, hides from `swan_watch.json` + `swan_watch.jsonl` + `alerts.log` + `data/lab/hidden_corpus.jsonl`. Read-only, no platform calls. Scripts in `WORK=.../scratchpad/work/content/` (list at the end).

## 1. The answer in 6 lines
1. **The true rate is not 0.9%, it is about 1.3-1.5% of text writes** (4,664 uncensored voice writes, 64 hides = 1.37% [1.08, 1.75]; 1.58% since 21 Oct 12:00 when rivals' reporting began; last 24 h 1.40% [0.94, 2.10]; after the tells fix 22 Oct 18:03: 13/1,012 = 1.28% [0.75, 2.19]). 0.9% appears only if the 553 booster reposts are put in the denominator (1.14% last 24 h). 0.6% is rejected for the post-fix period (P of 13+ hides at a true 0.6% = 0.009); 0.9% is not (P = 0.13); 0.3% is out of reach of anything seen so far.
2. **The deploys moved the rate little.** The phrase-budget fix (22 Oct 05:30) took "I'm voting No" from 64% to 3-5% of writes and the hide rate stayed at 1.7% (32/1878 before, 15/879 after). The tells fix (22 Oct 18:03) coincides with 1.70% to 1.28% (RR 0.75; trend-adjusted OR 0.55, p = 0.045; but within-voice only OR 1.15 [0.40, 3.4]): suggestive, not proven.
3. **What changed is the shape of the risk.** Early hides (21 Oct evening) were content-blind sweeps: "I'm voting No" was in 64% of writes and hid at 1.8% vs 1.5% without it. Since 22 Oct the hides are more selective: the residual 66 writes that still say "voting No" were hidden 12% of the time (8/66) vs 1.1% for the rest, and risk concentrates in a **15% slice of writes that holds 54% of the hides**: explicit vote statements, standalone persona posts (always a hashtag plus a vote statement), first-person job claims ("I run/drive/work...") and the switch closer (5.3% hidden vs 0.81% for the rest, 22 Oct 05:30 on).
4. **Things in our control that carry risk (adjusted for 6 h window):** lived-experience anecdote/kin lines (RR 1.8), "naming the exact thing they asked" opener (1.9) vs "open with the fact itself" (0.30, protective), "Yes" in our own text (1.9), replying to posts that ask a question (2.7) or mention Yes (1.8) vs replying to posts that already lean No (0.32), longer replies (3+ sentences 1.6, 2 or fewer 0.8%).
5. **One unexplained but large effect: `sv_delay = slow`** on the first reply (a 50/50 strictly alternating arm that, for 91% of replies, never leads to any second voice): slow 37/1748 = 2.1% vs fast 13/1626 = 0.8% (Fisher p = 0.001), growing over time (22 Oct 05:30 onward: 20 vs 3 hides). Text, voice, backend, latency are identical across the arms. Treat as a lead to test (pin the arm), not as a cause.
6. **Not risk factors** (checked, flat): the 40-nursing-posts fact, venue list/end date/after-the-vote/binds skeletons, overlap with the voice's last 60 posts or with other voices' posts that day, target being a rival/new account, voice identity (heterogeneity p = 0.28 after controlling the 6 h window), a voice's cumulative writes or its writes in the last 24 h, rate after its first hide became visible. The spelling "hand" is not protective (1.67% with a marker vs 1.22% without).

## 2. Labelled dataset, coverage, true rate
- **Writes** = `reply, post, reply_back, second_voice, thread` + persona reposts with text (live only; 10 dry-run rows dropped). 5,957 live rows, 5,404 from `owner=marc`; the 553 `minhnguyenhoang` rows are booster reposts without text, 0 hidden. Censored tail dropped: writes after 08:59 UTC 23 Oct (2 of the 66 known hides were written 09:27-09:30 and are excluded). Result: 4,664 text writes (excluding all reposts), 64 hides.
- **Hide labels**: union of four sources = **66** post_ids, all matched to a logged write: 42 in all four sources, 20 in watch+alerts only, **4 only in the hidden corpus** (lani, one of mere's, two of dan's; these are the recovered blind-spot cases). Alerts' "N hidden" counters agree with the id lists for every voice except dan (alert said 1, 3 known) and mere (alert 5, 6 known).
- **Known blind spot**: after the bot marks a voice suspended the watch stops looking. 241 writes fall in the 3.5 h before a suspension (5 hides among them); dropping them changes the rate from 1.37% to 1.33%, so the bias is small in aggregate, but per-voice counts for suspended voices are lower bounds. Hide delay: median 3.30 h (min 3.06); 14 of 62 were first seen later than 3.7 h after the write (watch outages, e.g. four 23 Oct 04-06 UTC hides first seen at 10:35), so "seen" times are an upper bound on the ruling time.
- **Rate over time** (text writes, Wilson 95%):

| UTC day | n | hides | rate |
|---|---|---|---|
| 19 Oct | 146 | 0 | 0 [0, 2.6] |
| 20 Oct | 562 | 3 | 0.53% [0.18, 1.56] |
| 21 Oct | 1,624 | 20 | 1.23% [0.80, 1.89] |
| 22 Oct | 1,719 | 30 | 1.75% [1.23, 2.48] |
| 23 Oct (to 09:00) | 816 | 11 | 1.35% [0.75, 2.40] |

By 6 h: 0.0 / 0.99 / 0.62 / 0.52 / 0.0 / 0.56 / 0.92 (21 12h) / **1.85 / 2.07** (21 18h, 22 00h) / 1.32 / 1.80 / 0.99 / 1.19 / 1.52 (23 06h). The 20 Oct figure is low because rivals were not reporting yet, so earlier regimes are not comparable.

- **Interrupted series around deploys** (text writes):

| Segment | n | hides | rate [CI] |
|---|---|---|---|
| B: 21 12:00 to 22 05:30 (before phrase budgets) | 1,878 | 32 | 1.70% [1.21, 2.40] |
| C: 22 05:30 to 18:03 (vote statement cut, budgets) | 879 | 15 | 1.71% [1.04, 2.80] |
| D1: 22 18:03 to 23 05:23 (tells gated) | 526 | 6 | 1.14% [0.52, 2.47] |
| D2: 23 05:23 to 09:00 (3 drafters) | 486 | 7 | 1.44% [0.70, 2.94] |

  Caveats: no concurrent control series; the same days saw 13 booster-to-voice conversions (22 Oct 12:26 and 16:51), the 87c6e8e behaviour switches (11:58), Blue changes and rival behaviour. Logistic with a linear trend and step terms (clustered by 6 h): phrase-budget step OR 0.72 (ns), tells step OR 0.55 [0.30, 0.99]. Within the 12 voices present before and after, Mantel-Haenszel OR 1.15 [0.40, 3.4]. **Verdict: no detectable harm, a possible 25-45% fall after the tells fix, not distinguishable from a calming of the rivals.** The share of writes with a switch closer fell to 0 (gate works); my looser "named friend/concede" regexes did not fall (13.7% and 8.7%).

## 3. Univariate and adjusted effects
Adjusted = Mantel-Haenszel across 6 h windows (exact-time control); voice x 6 h strata give the same picture where cells allow. Matched case-control (each hide vs 15 same-voice writes within 12 h, or vs 15 writes of any voice within 3 h; conditional logit) agrees. Rates are per write; "share of hides" is hides with the feature / 64. Full table: `risk_table.csv`.

| Feature | n | hides | rate | rest | adj OR [CI] | share of hides |
|---|---|---|---|---|---|---|
| Hashtag (only on standalone posts) | 71 | 5 | 7.0% | 1.3% | 10.6 [3.8, 29.6] | 7.8% |
| Standalone persona post (any) | 147 | 6 | 4.1% | 1.3% | 9.7 [3.4, 27.2] | 9.4% |
| Switch closer ("know anyone who moved from Yes") | 164 | 8 | 4.9% | 1.2% | 3.8 [1.75, 8.4] | 12.5% |
| Explicit vote statement ("I'm voting No") | 1,558 | 34 | 2.2% | 1.0% | 2.5 [1.4, 4.4] | 53% |
| First-person job claim ("I run/drive/work/I'm a...") | 298 / 188 | 9 / 7 | 3.0% / 3.7% | 1.3% | 2.3 [1.1, 4.8] / 2.8 [1.3, 6.4] | 14% / 11% |
| Mentions "Yes" in our text | 1,462 | 30 | 2.1% | 1.1% | 1.9 [1.15, 3.1] | 47% |
| Anecdote/kin/lived-experience line | 1,291 | 27 | 2.1% | 1.1% | 1.8 [1.1, 3.0] | 42% |
| Opener "name the exact thing they asked for" | 572 | 14 | 2.4% | 1.2% | 1.9 [1.03, 3.5] | 22% |
| Opener "with the fact itself" (protective) | 591 | 3 | 0.5% | 1.5% | 0.30 [0.09, 0.99] | 5% |
| Reply to a post that asks a question | 273 | 7 | 2.6% | 1.3% | 2.7 [1.2, 6.1] | 11% |
| Reply to a post that mentions Yes | 866 | 17 | 2.0% | 1.2% | 1.8 [1.0, 3.1] | 27% |
| Reply to a post classed lean_no (protective) | 602 | 3 | 0.5% | 1.5% | 0.32 [0.09, 1.16] | 5% |
| 3+ sentences (vs 1-2) | 3,139 | 52 | 1.7% | 0.8% | 1.6 [0.85, 3.0] | 81% |
| `sv_delay` slow vs fast (replies) | 1,748 | 37 | 2.1% | 0.9% (fast 0.8%) | 1.8 [1.1, 3.1]; time-matched 2.1-2.7 | 58% |
| Frame F2_no_end | 299 | 7 | 2.3% | 1.3% | 1.8 [0.8, 4.0] | ns |
| Frame F14_no_yes_but | 1,515 | 24 | 1.6% | 1.3% | 1.27 [0.76, 2.1] | ns |
| Concede opener (text) / named friend | 463 / 466 | 9 / 10 | 1.9% / 2.1% | 1.3% | 1.4 / 1.5 (ns) | ns |
| Kimi vs other backends | 3,025 | 51 | 1.69% | 0.79% | 1.4 [0.7, 2.8] | ns |
| arm_conv `base` vs other arms | 1,200 | 27 | 2.25% | 1.07% | 2.5 [1.2, 5.1] | 42% (low confidence) |

Structured fields with no signal after control: frame (only F2 borderline; F3/F5/F9 0 hides but n 95-212), lever, ask_kind (switching 2.9% raw, ns once time-matched), length_band, style, reply_mode, close, source, engaged, own_like, soft_yes, group, theme/pillar/voice, llm_calls/repairs/fixes, hand marker, exp. `reply_back` 1.15%, `second_voice` 0.45% (2/442), `thread` 0.70%: the conversational and amplifying writes are the safest by act.

**Multivariate** (conditional logit, 8 random control draws, strata = hide plus 15 writes within +-3 h, 17 features): `act_post` 18.7 [3.2, 110] (hashtag/vote statement are collinear with it), first-person job claim 3.2 [1.4, 7.4], `sv_slow` 2.1 [1.2, 3.8], vote statement 2.65 [1.2, 6.0], target asks a question 3.05 [1.2, 7.9], target mentions Yes 2.1 [1.1, 4.0], our own "Yes" 1.9 [1.0, 3.4], apostrophe-less/typo-like text 2.5 [1.0, 6.4]; switch closer 2.4 [0.8, 7.3] (gated, so n small); lean_no target 0.39 [0.11, 1.4]; kin_ref 1.8, ends-in-question 1.6, concede opener 1.5, F2 1.6 (all ns). The voice-matched design gives the same ranking. Sentence count loses its effect once these are in (OR 0.87/SD), i.e. long replies are riskier mostly through carrying more claims.

**Shares explained** (sum overlaps heavily; do not add): vote statement 31%, sv_slow 26-30%, anecdote 19%, "Yes" mention 22%, hashtag/posts 8-9%, first-person claim 8%, switch closer 7-9%, question-asking target 7%. A rule that removes `risky_text` (vote statement, standalone post, first-person job claim, switch closer, hashtag) is *in-sample*: remainder 0.81% [0.47, 1.38] (22 Oct 05:30 on, n = 1,607) and 0.67% in D; adding `sv_slow` leaves 1/865 = 0.12% [0.02, 0.65] (data-snooped, validate forward before quoting).

**Dose/response and voice effects.** Hides per voice since 21 Oct 12:00: sione 6.0%, mere 5.9%, malakai 3.7%, ivy 3.0%... down to 0 for liam_f70 and rwalker84, but a permutation test (labels shuffled inside each 6 h window) gives chi-square 29.4 vs null 26.4 (p = 0.28): **no detectable voice effect beyond time and chance**, with the obvious power limit (each voice has 1-3 hides). Rate by voice's writes in prior 24 h: 1.2 / 2.0 / 0.6 / 1.7 / 2.7 / 1.6% (no trend); by cumulative writes 1.5 / 1.7 / 1.9 / 1.1 / 0.8%; after the voice's first hide became visible 1.58% vs 1.60% before. Team writes in the previous 10 minutes: flat.

## 4. Text features (matched controls)
- **Absent by design, so untestable**: em-dashes, exclamation marks, emoji, URLs, @mentions, quoted slogans (3), Marina/KITB (3), hedging openers (127 writes, 0 hides, 0% [0, 2.9]), triads (25, 0). The gate has removed LLM-style tells; remaining variance is in structure.
- **LLM-ish signals**: "not X, it's Y" 49 writes, 2 hides (4.1% [1.1, 13.7], adj OR 2.0, ns); uniform sentence length does not raise risk (low sentence-length CV, i.e. most uniform quartile, has the *lowest* rate: 0.64% vs 1.8-2.3%, but this is confounded by 1-2 sentence replies); similarity to the voice's previous 60 posts: no gradient (0.67-1.7% across quintiles, middle lowest); similarity to other voices' posts in the last 24 h: no gradient (1.7% to 1.2%); near-duplicate (>0.5) occurs in 20 writes only (gate removes it). Similarity to the target text: slight upturn in the top quintile (2.0% vs 1.0-1.5%, ns).
- **Spelling hand**: marker present 1.67% vs 1.22% (OR 1.2, ns); "apos" (dropped apostrophes) 7/273 = 2.6%, "dots" 2.0%, `typo_like` regex 8/209 = 3.8% (adj OR 2.9 [1.35, 6.1]; p = 0.004 but a post-hoc regex mixing apostrophe drops and tripled letters). Not protective; the evidence is weak either way. Repeated typos such as "stalll/weeend/reallly" are visible in the data and are probably algorithmic.
- **N-gram enrichment** (1-4 grams, hidden vs all, window-stratified): "# / ?# end" (hashtag posts), "(know) anyone who's moved from yes to no" (4 of 62, 6.5%), "I'm voting No" (adj OR 2.1), "review (built in)" 2.2 [1.2, 3.8], "once" 3.5 [1.7, 7.3] (219 writes, mostly "once it's Yes" stories), "us" 2.3, "choice" 4.2, "someone", "then", "at her". Most are fragments of the three already-known skeletons; after FDR, only the hashtag, switch-closer and voting-No grams stand out. Topic phrases (nurses40, venue list, end date, sunset, binds) are not enriched: **the skeleton, not the facts, is what gets hit**.
- **Length**: <=145 chars 0.96%; 221-254 chars 1.8%; >=254 1.65%; 1-2 sentences 0.8%; 3 1.3%; 4 1.9%; 6+ 5.6% (n = 89).

## 5. Target features
- Citizen targets 1.32% vs team-account targets (threads on our own amplified posts) 0.70% (2/286); depth (reply to a reply) 1.53% vs 0.73% for direct replies (adj OR 1.4 [0.6, 3.1], ns); target length no gradient; hostile targets: 2 (untestable). Per-citizen: 51 of 1,295 citizens targeted had a hidden reply; two of our replies to the same citizen are not riskier (1st 1.3%, 2nd 0.8%, 3rd 1.2%, 4th+ 1.7%).
- **Target class**: conditions 1.73% (28/1,620), unclear 2.1%, off_topic 2.1%, yes_reason 1.1%, unsure 0.9%, **lean_no 0.50% (3/602)**. A reply that agrees with a No-leaning citizen is the safest write; replies that argue with a doubter or Yes voter on their post are the risky ones.
- **Target asks a question** 2.6% (7/273; adj OR 3.0 [1.3, 6.8]); **target mentions "Yes"** 2.0% (OR 1.9 [1.1, 3.4]).
- Frame matched to the read frame: 1.53% (48/3,129) vs the rest (not testable beyond that).
- Not available in the log: whether other teams had already replied, target author being a rival bot (only the id range is logged: ids > 2343 are team accounts, 286 writes). **Needs**: platform thread snapshot at write time.

## 6. Sweeps
- A permutation test (hide labels shuffled inside each 6 h window) puts 47 of 64 hides within 15 min of another voice's hide vs 33 expected (95% null 24-41, p = 0.0005; same with voice x 6 h kept fixed). So the excess clustering is only ~14 hides (22% of the mass); much "clustering" is just the team's write density (~20 writes per 10 min).
- Sweeps (>=2 hides from >=2 voices within a 12-min write span): **13 clusters, 45 hides (70%)**; the windows around them hold 712 writes and 6.3% were hidden. By era: B 7 clusters / 29 hides, C 4 / 11, D 2 / 5. Singletons now dominate: B 3, C 4, D 8 of 13. In a sweep window a median 33% of the voices that wrote were hit (range 15-67%).
- What distinguishes sweep windows: team density 21.4 vs 16.3 writes per 10 min and 11.1 vs 9.2 voices (partly selection), otherwise no shared frame/fact/opener or share of facts; the feature shares of the non-hidden writes in sweep windows equal elsewhere in the same era. **Which of our posts in a sweep window gets hidden follows the same content signals** (within-sweep MH, 13 windows): anecdote/kin 2.3 [1.2, 4.3], switch closer 4.2 [1.6, 11.2], `sv_slow` 2.3 [1.2, 4.4], "Yes" mention 1.8 [1.0, 3.3], ends in a question 1.85 [0.98, 3.5]; vote statement 1.7 (ns). So in a sweep the reporter has a batch and the ruling picks (or the batch pre-selects) posts that carry these.

## 7. Ranked list of phrases/structures/framings to ban or budget
Ranked by hides avoided per 1,000 writes at current prevalence (prevalence in D x 1.3% x (OR - 1)); "conf" = my confidence that it is a cause or a stable marker. Cost = expected loss of volume or conversion.

| # | Ban/budget | adj RR [CI] | prevalence now | hides avoided /1000 | conf | Lever in code | Cost |
|---|---|---|---|---|---|---|---|
| 1 | Anecdote/kin/lived-experience line ("my cousin runs...", "I drive the loop", "my neighbour's twins") | 1.8 [1.1, 3.0] | 42% (rose from 13% as the vote line was cut) | ~3.7 | medium-low | add a `kin` budget to `quality.PHRASE_BUDGETS` (share 0.10-0.15); drop the "Open with a short line from your own experience" opener | none in volume; some warmth |
| 2 | `sv_delay` slow arm | 1.8 [1.1, 3.1] (time-matched 2.1-2.7) | 48% | ~3.6 (if causal) | low (mechanism unknown) | `config.PIN["sv_delay"]="fast"` or `SECOND_VOICE=False` (second voices are 8.5% of replies) | second-voice conversion (unknown; second voices are rare) |
| 3 | Long replies (3+ sentences, >=250 chars) | 1.6 [0.85, 3.0] | 71% | ~3.4 | low-medium | `experiment.LENGTH_BANDS`: shift to "short" and "mirror" | possible small conversion loss; test |
| 4 | Opener "name the exact thing they asked for" | 1.9 [1.03, 3.5] | 25% | ~2.7 | low-medium | `OPENERS` weights; raise "Open with the fact itself" (RR 0.30) | none |
| 5 | Our own "Yes" ("a Yes locks in...", "a Yes can't carry...") | 1.9 [1.15, 3.1] | 23% | ~2.2 | medium | phrase budget on `\byes\b` (<= 10% of window); retire F14 as the default skeleton | frame diversity |
| 6 | Replying to question-asking and Yes-saying posts; prefer lean_no/unsure targets | 2.7 / 1.8 vs 0.32 | 5% / 18% | ~1.1 / ~1.7 | medium | targeting priority (todo/21 score): add a small penalty for target `?` and Yes mentions | these are the persuadable citizens: **real conversion cost**; do only the question/Yes-flagging for drafting tone, not skip |
| 7 | Explicit vote statement (all forms) | 2.5 [1.4, 4.4]; in D (n = 26) 19% hidden | 2.6% | ~0.4 but **19% hit rate when it leaks** | high | `PHRASE_BUDGETS["vote"]` 0.15 to 0.0 for replies; `no_vote_statement` rule for posts (quality.py) | none visible (already 3%) |
| 8 | Standalone persona posts with hashtag + vote statement | 9.7 [3.4, 27]; 4.1% hidden | 3% (D 0.9%) | ~1.0 | high | `config.POST_EVERY_N` up (4 to 8+), or posts without hashtag/vote statement | persona posts' reach; they are 9% of hides from 3% of writes |
| 9 | First-person job claim ("I'm a nurse", "I run/drive/work...") | 2.3 [1.1, 4.8] | 6-9% | ~1.4 | medium | `identity` / `PERSONAL_KINDS` rule in `quality.py`; budget at <= 3% | persona authenticity |
| 10 | Switch closer and story | 3.8 [1.75, 8.4] | 0% (gated) | 0 | high | keep `PHRASE_BUDGETS` share 0 | none |
| 11 | Ends-in-question; F2_no_end; concede opener; named friend | 1.3-1.8, all ns | 5-48% | <1.6 | low | monitor only | - |

Untouched by evidence (leave as is): the 40-nursing-posts fact, venue list, end date, sunset, "after the vote", "binds" skeleton, own-history/cross-voice similarity.

## 8. Recommended changes (expected effect per cost)
1. **Pin `sv_delay` to `fast` (or off) for 12 h and compare** (`config.PIN`; `experiment.alternate` honours it). Free; if the effect is real the post-fix rate could fall from 1.3% toward 0.7%; if parity of the reply counter is just a proxy for something else we learn that too. Do first because the signal is the cleanest quasi-randomised contrast we have (balanced in every 6 h block, p = 0.001 overall, 0.006 in D alone).
2. **Zero the vote statement everywhere** (replies 0.15 to 0 in `PHRASE_BUDGETS`, and let posts say No without "I'm voting No" + hashtag) and **cut persona posts to 1 in 8+** (`POST_EVERY_N`): touches 5 of the 13 D hides (each carried a vote statement; 2 were posts) at no measurable conversion cost.
3. **Budget the anecdote line and the "Yes" mention** (new `PHRASE_BUDGETS` keys at 0.10-0.15) and raise the plain "fact itself" opener; replace "own experience" openers. Expected: 1.28% to ~1.0% (range 0.8-1.2) for a small loss in warmth.
4. **Shorter replies** (1-2 sentences ~0.8%): potentially the largest single dial (RR 0.63 [0.33, 1.2]) but conversion risk is unknown; run as an arm.
5. Prospective check: log `risky_text`, `anecdote` and `yes_mention` flags at write time and re-estimate after ~3,000 more writes (only ~30-40 hides expected, CIs will still be wide); a rate of 0.3% needs ~10 hides in 3,300 writes and is, on this evidence, reachable only if the rival reporting itself drops.
6. Revisit the "no tells" claim: tells are gated at zero but anecdotes and kin stories replaced them (kin_ref 6% to 28%; first-person claims 3% to 9%).

## 9. What could not be determined
- Mechanism of the `sv_delay` effect (needs the bot's counters: possible correlation with another per-reply alternation or with the order in which the Blue reporters see threads). Could be chance (one of ~60 fields scanned; Bonferroni ~ 0.05-0.08), but the contrast has the same sign on each of the 3 UTC days (21 Oct 9 vs 6, 22 Oct 16 vs 6, 23 Oct 10 vs 1) and in the three eras (B 15 vs 10, C 10 vs 2, D 10 vs 1).
- Whether a reporter chooses the post or only the author (we do not see reports or "genuine" rulings). Per-post content effects are therefore effects on being ruled hidden, not on being reported.
- Rival-bot targets, other teams' replies already in the thread, and thread depth at write time are not logged.
- Per-voice effects for suspended voices (watch blind spot); 23 Oct instant suspensions are outside this package.
- Pre/post estimates have 13 hides after the tells fix; the 95% interval for the true post-fix rate is 0.75-2.2%.

## Files (WORK = scratchpad/work/content/)
`extract.py`, `labels.py`, `master.py`, `rates.py` (dataset, labels, rates), `uni.py` (univariate by field), `feats.py` (text features and similarities, writes `t3.pkl`), `cc.py` and `multi.py` and `final.py` (matched case-control and conditional logit), `mh.py` and `table.py` (Mantel-Haenszel; writes `risk_table.csv`), `its.py` (before/after), `sweeps.py`, `sweeps2.py`, `sweep3.py` (sweeps), `target.py` (targets), `voice.py` (voice/exposure), `ngram.py` (phrases), `sv*.py` (the `sv_delay` checks), `anec.py`, `dvote.py`, `clean.py`, `blind.py`, `kimi.py`, `typo.py`, `llm.py`. Risk table: `risk_table.csv`.
