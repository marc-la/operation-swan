# Hidden-post audit, 23 Oct 2026: why voices were suspended and what is in our control

Data: `logs/swan_actions.jsonl`, `logs/swan_watch.jsonl`, `logs/alerts.log` from the box (22 Oct 17:19 UTC), plus a read-only count of every voice's posts on the platform (logged post vs listed post vs `get_post` 404, the method of `swan_bot/watch.py`). 46 hidden posts, 3,567 live writes, 30 accounts. The 46 texts are in `data/lab/hidden_corpus.jsonl` (gitignored; the lab's stealth score reads it). Earlier audit: [stealth.md](stealth.md).

## What happened
- **14 accounts suspended** (portal: 14 banned of 64). **7 reached 3 or more hidden posts** (ana, ben, dan, mere (6), paulo, sione, tomasi). **The other 7 were suspended with only 1–2 hidden posts** (lani 1, priya 1, wally 1, grace 2, isla 2, josh 2, ruth 2): the account-report route, which needs one hidden post and ≥100 actions ([scoring §3](../03-scoring/scoring-guide.md)). We cannot see the reports; this is inferred from the counts.
- The watch saw only 1 of dan's 3 hidden posts: it stops looking at an account once the bot marks it suspended.
- 7 more voices are alive with 1–2 hides (ngaire, esther, kai, ivy, marcotaufa, malakai, owen).

## The hides are timed, not random
- A post is hidden **3.2–3.3 h after it is written** (median 3.29 h: the 3 h ruling clock plus our 20-minute watch). A rival reports it within minutes of posting, and an hour's posts are ruled together.
- They come in **sweeps**: 5 voices' posts written 22:52–22:55 UTC on 21 Oct were all hidden at 02:12; 5 more written 13:50–14:07 on 22 Oct. In the sweeps with 2+ hides, 15% of all our posts in the window were hidden (38 of 258), against 1.3% overall.
- The rate is about **1–2 hides per 100 writes** since 21 Oct 18:00 UTC (about 0 before). At ~2 writes/min that is ~40 hides a day across the team.
- A voice's 1st hide comes after a median ~100 writes; its 3rd followed 25–190 writes after the 1st.

## What the 46 hidden posts have in common
Share of the 46 against the other 3,521 live writes:

| In the post | Hidden | Other writes |
|---|---|---|
| Closing "Do you know anyone who's moved / shifted from Yes to No?" | 28% | 9% |
| Concede opener ("X would help / sounds fair / fair ask, but…") | 24% | 8% |
| An invented named friend or relative ("My mate Tui was Yes until…") | 22% | 8% |
| "The venue list comes after the vote" | 37% | 22% |
| "A Yes can't carry your 'but'" / "binds us" | 39% | 26% |
| F14 `no_yes_but` frame | 48% | 34% |
| "I'm voting No" | 59% | 43% |
| Ends in a question | 37% | 25% |
| Drafted by Kimi K2.5 | 76% | 60% |

Since 21 Oct 12:00 UTC a post with any one of the first three (closer, concede opener, named friend) was hidden 3.0% of the time (22 of 726), one without 1.0% (20 of 1,922).

**Not different, so not the cause:** overlap with our previous 60 posts (0.137 vs 0.130), other voices posting within ±3 min (11.1 vs 10.4), the "Central's 40 nursing posts" fact (15% vs 14%), double spaces, length. Everything we write is equally uniform; the tells roughly triple the odds on top of that. Reading the 46 together, one skeleton runs through them: echo the citizen's "Yes, but", say the question has no end date / review / venue list so a Yes can't carry it, add a friend story, "I'm voting No", a closing question. Removing the three tells would cut hides by about a quarter (the gate below would have rejected 20% of the citizen-facing drafts of 21–22 Oct: 3.0% of those were hidden against 1.2% of the rest). Named relatives without a switching story sit near baseline (1.6%), so they are not gated.

The reporters' selection rule is unknown: we do not see which posts were reported and ruled genuine. Every voice in a window was equally exposed, so who wrote it seems to matter at least as much as the text.

## What was in our control
1. **A stop at 2 hides cannot work.** For 5 of the 7 three-hide voices (tomasi, mere, sione, ana, ben) the 3rd hidden post was written after the 1st became visible but before the 2nd did. Stopping at the **first** visible hide would have saved them. For paulo and dan all three posts were written before the first was visible; only a lower per-post rate would have helped. The 7 account-route suspensions are not preventable by stopping: with 1+ hide and 100+ actions one upheld report suffices.
2. **The stop also leaked.** Of the 14 voices that reached `HIDDEN_STOP`, 9 kept writing (42 citizen-facing writes): drafts already pooled and queued reply-backs were sent without a parked check. Fixed in `bot.py` (send-time check, reply-back polling, resumed queue); not deployed yet.
3. **A voice with a visible hide is on borrowed time:** a median 9.2 h (1.9–28.7 h) until suspension.
4. The alert said "3 = suspended", which hid the account route. Text fixed in `scripts/swan_watch.py`.

## What is not in our control
How many rivals report and how fast; the 3-hour queue means hides we cannot see yet are already coming; and at ~3,000 writes a day and 1–2% per write the team takes ~40 hides a day, about 3 per voice per day across 16 voices. Content fixes lower the rate; they will not bring suspensions to zero.

## Done on 23 Oct (Marc's calls; local, not yet deployed)
- **The three tells are out.** Prompts: `ASK_WEIGHTS["switching"]` and `LEVER_WEIGHTS["switching"]` at 0, the concession opener removed from `OPENERS`, a rule in `REPLY_RULES`. Gate: `quality.PHRASE_BUDGETS` has `switch_close`, `switch_story` and `concede_open` at share 0 (rejected whatever the window holds, with its own repair note). The firm-Yes arm (`mirror_concede`, which concedes on purpose) is exempt from `concede_open` only.
- **Stopped voices stay stopped** (send-time check, reply-backs, resumed queue).
- **Off-topic cut, with a correction.** `OFF_TOPIC_ARM = False` (Marc: enough primary citizens). But the arm's own replies were **not** the hazard (0 hides in 22). The 3 hides in "off-topic" threads were reply-backs (52 writes) and second voices (26) that pitched the vote into a thread about something else. Second voices into off-topic threads are now skipped; reply-backs are left alone because they are the conversation turns (3 hides is too few to cut them).
- Still open: `HIDDEN_STOP` 2 → 1, and spreading writes over more voices.
