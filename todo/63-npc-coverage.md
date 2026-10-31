# 63 — Who we can see: citizens above id 2343 and on-vote posts skipped as off topic

Written Sat 31 Oct 2026, ~10:30 Perth (02:30 UTC), by Claude for Marc. **Status: shipped (Marc approved all three, Claude
built and deployed; 0c08db3, live 02:36 UTC).** Not a switchback arm: it widens who and what the bot can see; how we answer is unchanged.

## 1. What the data said (31 Oct, read-only)
**Coverage.** The bot targets ids 12-2343 (2,332) plus accounts above 2343 that `npc.py` scores 0.9+ (2,594 on 31 Oct): 4,926
of the "just over 6,000". Ever written to: 2,249 of the seeded ids (96%) and **1,079 of the 2,594 (42%)**, though these
answer a write 13.8% of the time against 6.6% ([situation-2026-10-29 §4](../docs/06-strategy/situation-2026-10-29.md)).
In 24 h, 3,887 first replies went to 1,394 citizens and none to a non-citizen. The light read called 85% of targets yes_but,
12% lean or firm No and under 1% firm Yes. The keyword classes agree with it: 97% of lean_no targets were read as No.

**Gap 1: the scan saw a quarter of the clock.** `scripts/npc_scan.py` scores the authors of the bot's 15-min Latest snapshot
once an hour, so a citizen who posts a few minutes every day or two is often missed, and an unscored author's posts never
enter the queue. In one window, 9 unscored authors with ids up to 9,874 posted. Read once each, all scored 0.94-1.0 (6-15
posts in 12 days). 24 scored extra citizens posted in the same window.

**Gap 2: on-vote posts skipped as off topic.** About 2,530 off_topic skips a day. The rule read only the post and the first 200
characters of its parent; rival-bot parents rarely say "referendum". In one 15-min window, 47 of 238 citizen posts were
skipped and about 28 were on the vote ("a pass doesn't fix the staffing crisis", "not just checks at the door").

## 2. What shipped
1. **The scan every 10 min** (`deploy/swan-npcscan.timer`, was 1 h). It overlaps the 15-min snapshot, so every author is seen.
   Known accounts are re-read only after a day (`--fresh-h 24`), so a run is a few dozen reads.
2. **First sight in the bot** (`Targeter._score_new`, `config.NPC_LIVE_*`). After each Latest read, an author with an id from
   2344 to `NPC_LIVE_MAX_ID` (9,874) that neither the file nor this run has scored is read (get_account and one page of
   posts, 2 reads) and scored as the scan does. A score of 0.9+ puts the post in the queue in the same refresh.
   - At most 4 authors a refresh, newest first. A 429 stops the round and the rest wait (at most 30 min).
   - Ours, reposts, seeded ids and private accounts (their posts answer 403) are never read past the profile.
   - Every score is logged as `npc_live`, with `author_id`.
   - Scores live in the bot process only. The file stays the source for Blue and the follow-ups, and the 10-min scan
     writes the same accounts there.
   - Why 9,874: ids rise with `created_at` (census 30 Oct, 0 inversions in 12,639). All 2,604 accounts scoring 0.9+ were
     made by 21 Oct 10:24 UTC (id 9,803); 9,874 is the last account made before 12:00 that day.
3. **On the vote in other words** (`targeting.on_vote`, a wider `ON_VOTE`).
   - The pass, the checks, the rules and the law in the citizens' words.
   - Also on the vote: a parent or a thread's first post (`root_post_id`, one cached get_post, read only when the post and
     its parent say nothing) that is on the vote, when the reply argues or agrees (`thread_engages`; warmth-only stays out).
   - The drafter still sees the parent as its context, not the root.

## 3. The replay (before the push)
320 random off_topic skips from the 24 h to 31 Oct ~02:05 UTC, with parents and roots read (806 get_post reads, paced).
Labelled by hand (Claude):
- **Admitted: 169 of 320 (53%; 2 then skipped as hostile),** about 55 more fresh citizen posts an hour.
  - Paths: 81 by their own words, 46 by the parent, 42 by the first post.
  - Classes: unclear 77, yes_reason 32, unsure 22, conditions 17, lean_no 17. unclear and unsure keep `DOWNRANK_MIN`.
- **Held out** (the last 111, unseen while the words were chosen): 53 admitted, 2 of them small talk ("omg a flat white for
  sure... if i'm feeling fancy"), all through the first post. About 96% precision. About 20 on-vote posts were still
  missed, about 72% recall ("doses", "a straight No", "'staged' rollout": left out, so the held-out figures stay true).
- **Posts we already answer:** 16 of 3,886 first-reply targets change class against HEAD. 15 go from unclear to unsure
  (their own words now count). 1 goes from yes_reason to lean_no, and it is a No-leaner.

## 4. Live read-outs (to do after the deploy)
- Every hour, `act: npc_live` rows: how many, the share scoring 0.9+, and the writes with `npc_score` to authors first
  scored that way.
- Funnel `skipped.off_topic` an hour: about 105 before (2,530 a day). Expect about half.
- Light-read skips (`act: skip`, `why: read`): 0 in the 24 h before. A rise means small talk getting through.
- Engagement per write on the portal, the hours against the same hours a day earlier.

**First read, 02:37-02:51 UTC (14 min, Claude).**
- Every write came from 0c08db3, at 2.71 a minute (2.67 in the hour before). No errors in the journal.
- The scan ran at 02:36 and 02:46, about a minute each; the next was due at 02:56.
- off_topic skips: 65 an hour, against 167 in the hour before. No light-read skips.
- First sight: 15 accounts read, 9 scoring 0.9+, 5 private.
  - Their 10 posts reached the queue 1-10 s after posting, like everyone's (median 5 s).
  - None was answered yet. Every pick in their first 2 minutes went to a newer post (newest first); none was skipped
    by a filter.
  - In the same minutes: 23% of seeded citizens' posts answered, 44% of file-scored extra citizens'. Read the share
    again after a few hours.
- 2 of 40 first replies went to posts the old rule skipped as off topic. Both sat in threads on the rules and
  gatekeeping, the light read called both lean_no, and our replies stayed on the vote.

## 5. Off switches
- First sight: `SWAN_NPC_LIVE_SCORE=0` in `.env`, then restart.
- The scan: back to `OnUnitActiveSec=1h`, then push.
- The wider words: revert the `ON_VOTE` and `on_vote` parts of the commit. There is no flag.
