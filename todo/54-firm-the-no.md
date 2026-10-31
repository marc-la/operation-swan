# 54 — Firm the No, don't echo it (todo/53 P1: the count)

Written Sat 31 Oct 2026, ~02:30 Perth (30 Oct 18:30 UTC), by Claude for Marc. **Status: shipped 31 Oct 00:15 UTC (4363550; Marc approved the design, Claude built it).** §3 items 1-3 are live (`FLIP_TURNOUT`, fear `no_firm`, logged `flip_fallback`); item 4 (optional) was not built.
**Priority 2 of the 31 Oct designs.** It's a content change plus about 10 lines of code. Ship it in the same push as
[todo/59](59-prune.md)'s content changes, so the bot restarts once, before the 06:00 UTC last deploy. It must be live
before the campaign silence and ×4 begin (31 Oct 13:00 UTC).

Read first: CLAUDE.md, [todo/53](53-the-last-three-days.md) §2 and §3 P1, [situation §5](../docs/06-strategy/situation-2026-10-29.md#5-persuasion-conviction-and-the-count) and §13
(the flip), `src/swan_bot/flip.py`, `content/flip.toml`.

## 1. What the data says

**The queue is not the problem.** `READ_PRIORITY` gives `lean_no` 0.0, but the pick is newest-first, so priority only
breaks ties among old posts. In the 31 h to 30 Oct 11:00 UTC:
- **Volume:** 451 first replies went to `lean_no` posts, 9% of first replies (about 14.5 an hour).
- **Speed:** median age at send was 0.7 min (p80 1.7 min), the same as `conditions` and `yes_reason`.
- **Losses:** only 15 `lean_no` items expired unanswered.

Raising the priority would change nothing. **We already answer nearly every lean-No post in under two minutes. It's what
we say to them.**

**What we say is the echo the scoring page warns about.**
- **Every** `lean_no` first reply goes out as the `turnout` group (`targeting.next_target`, line ~1132), with
  `GROUP_STYLES["turnout"]` (`content.py:1232`): *"They already lean No. Affirm it in their own terms, then say why turning
  up matters this time: it's close and every No counts."*
- The scoring page: *"Agreement alone is not a change of mind: a post that repeats what a citizen already believes may
  get engagement but is unlikely to get persuasion points."*
- What scores is a **firmer** No. The organiser ruled on 27 Oct that lean No → definitely No is a change of mind toward No
  (160 × the multiplier, and weight 1 in the 400,000 pool).

**The turnout replies contradict themselves.** 384 turnout replies, 29 Oct 13:30-30 Oct 17:00 UTC:
- **47% (181) also carry a flip line.** The `conditional_yes` fear in 74, hospitals in 55, act_early in 15. The model is
  told both "they already lean No, affirm it" and "answer the fear behind their Yes".
- **Most of the rest (203) carry a news story:** `health_handled` 94, `poll_narrows` 83, `no_is_this_assembly` 26.
- **Proxy:** turnout replies **with** a flip earned 2.40 ± 0.49 (n 146), **without** 1.89 ± 0.34 (n 169). Not significant,
  but the direction supports giving every one of them the reassurance.

**Some "lean No" posts lean Yes.** The light read calls 13 of the 384 `yes_but` (3%). A hand sample of 14 soft `lean_no`
targets on 30 Oct found three more that read as Yes:
- "PEOPLE THINK A NO VOTE FIXES EVERYTHING BUT IT JUST LEAVES US IN LIMBO!!!" matched `LEAN_NO`'s "a no vote".
- "It's all about keeping those beds available for emergencies by stopping the influx in the first place."
- "the nursing shortage is the actual bottleneck here. paperwork can be sorted once the surge is managed."

Telling these citizens "you already lean No, every No counts" is wrong on its face.

**Two more facts.**
- **Firm No:** 81 of the 384 (21%) match `FIRM_NO` ("I'm voting No", #voteno). They are already definite on the
  referendum view, so for them this is engagement only.
- **Hidden posts:** the turnout group is **not** over-represented. It has 8 of our 93 hidden posts since 26 Oct (9%) and is 9%
  of first replies. The 28-29 Oct "kill (hidden post)" came from 4 hidden in 242 writes.

**The campaign silence begins at ×4.** `setting.md`: from 00:00 1 Nov Sydney (31 Oct 13:00 UTC), "mass campaign messaging
... restricted", while "ordinary people posting their own views online are not".
- The citizens' models likely carry the setting, and "every No counts" is a campaign line.
- How NPCs treat campaign-style posts during the silence is open question B.7 (never answered).
- Dropping the line removes the risk at no cost.

## 2. Recommendation
Turn the turnout line from **affirm and turn out** into **firm it**: answer the one doubt that could still pull a No-leaner
to a Yes, with a fact. That doubt is the one the flip already answers for conditional Yes posts: that a No means doing
nothing.

**Every lean-No reply carries the flip's reassurance:**
- the core line: a No isn't doing nothing; the testing, the tracing and the free vaccine all carry on;
- one proof;
- the turn when they named a condition.

No "every No counts", no turnout pitch, nothing about when or how to vote.

## 3. Design

1. **The style line** (`content.GROUP_STYLES["turnout"]`, `content.py:1232`). The key and group stay `turnout`, so logs
   and reports stay comparable.
   > "They seem to lean No; if their post actually leans Yes or is unsure, ignore this line. Don't just agree with them,
   > and don't tell them to vote or how: firm it up. Find the one thing that could still pull them toward a Yes (most often
   > the worry that a No means doing nothing) and settle it with the point below, in their own words."

   - The line states no fact, so it needs nothing from `facts.SAYS`.
   - It must not match `quality.WRONG_LOGISTICS` or the "vote" phrase budget's `VOTES_NO`. Test both.
2. **A flip on every turnout reply** (`bot.flip_choice`, `bot.py:858`).
   - When `job.get("group") == "turnout"` and `flip.choose(body)` returns None, use the `conditional_yes` fear as a fallback.
   - Add `flip.choose(text, fallback=None)`. With `fallback="conditional_yes"`, a post that voices no fear gets that fear,
     its live evidence (weighted as now) and a turn: the post's own condition if it names one, else a general one, as now.
   - The rest of `choose` is unchanged. A paused fact still drops an item, and `opposes_pass` still returns None (3 of the
     384 targets).
   - Log as now (`flip` = fear/evidence/pivot). A fallback flip adds `flip_lift` unchanged and a new field
     `flip_fallback: true`, so a read can split them.
3. **News:**
   - The flip, when present, already takes the slot from news (`story = None if fl`), so turnout replies stop getting
     the poll story.
   - Leave `NEWS_TURNOUT_SHARE` as is (it's moot), or set it to `NEWS_SHARE` for tidiness.
   - Keep `poll_narrows` in `news.toml` for the rest.
4. **Optional, only if time allows:** keep obvious Yes-leaners out of the turnout group. In `next_target`, a `lean_no`
   candidate whose post matches `YES_REASON` and not `FIRM_NO` goes out as an ordinary candidate, so the flip treats it
   as a fear.
   - Check the share on 24 h of rows before shipping; expect a few percent.
   - The conditional style line in (1) already covers the miss, so skip this if short of time.

**Tests:**
- `GROUP_STYLES["turnout"]` has no `WRONG_LOGISTICS` hit and no `\bcounts?\b|turn(ing)? up|polls?` wording.
- `flip_choice` returns a `conditional_yes` choice for a turnout job on a No post with no fear word ("No sunset, no list,
  no thanks."), and None for an `opposes_pass` post.
- A turnout job on a hospital-fear post still gets the hospitals fear, not the fallback.
- **Run the slow paused-fact sweep** (`scripts/t.sh slow`, about 2.5 min on 8 cores). Flip lines now reach a new group's
  prompts, and the box's deploy check skips the slow tests (todo/61).

**Rollback:** `SWAN_FLIP_ON=0` removes every flip (too broad). Better: revert the commit. Turnout replies keep working
without the fallback, and the old line returns.

## 4. How we judge it

| KPI | source | baseline | bar |
|---|---|---|---|
| changes of mind toward No, primary and contributions, a Sydney day | portal lines (`todo/53` §7) | 29 Oct: 2 + 3; 30 Oct: 3 + 8 | any rise. This can't be read inside a day; it's a bet on an asymmetric payoff (§5) |
| turnout proxy, 6 h read | outcomes, `group` turnout | 2.03 (29-30 Oct) | ≥ 1.9 |
| hidden posts on turnout replies | `swan_watch.json` hidden × our writes | about 2 a day | ≤ 3 in 12 h |
| away contributions per 1,000 writes | portal | 20-26 (28-30 Oct) | ≤ 30 over 12 h |

**Kill** (revert the commit): turnout proxy under 1.6 over 12 h, or hidden posts or away contributions over their bar.

## 5. What it is worth (assumptions stated)
- **The volume:** about 350 lean-No first replies a day, about 275 of them not already firm. From a 03:00 UTC deploy to
  the end that's about 600 firmable citizens.
- **A primary change:** worth 640 red points at ×4. If No wins, it also adds weight 1 in the 400,000 pool.
  - Our toward weight now is about 3-4 units a day, so about 10-12 units over the 3 days.
  - The No side's total weight is unknown. At 60-150 units, one unit is worth 2.7k-6.7k if No wins.
- **If 1 in 200 firming replies makes a primary change toward No:** about +3 changes, worth about +2k red. If No wins,
  that's also +3 units: about +8k to +20k.
  - At a 40% chance that No wins, that's **about +5-10k expected**, plus whatever it does for the count itself (firmer
    No-leaners turn out; scoring §4).
- **The downside is small:** turnout is 9% of first replies, and the flip-carrying half already earns as much as the rest.

## 6. Not doing
- **Raising `READ_PRIORITY["lean_no"]`:** no effect (above).
- **Writing more to lean-No citizens:** there's no more supply. We already answer them all.
- **Yearly-vaccination or booster angles** (scoring §2 lists "yearly vaccinations" as a scored view, and boosters are an
  open question in-game, `setting.md`): they would read as vaccine doubt. The brief says "not against the vaccination".
- **Any "vote No" or voting-day line:** the gate's `WRONG_LOGISTICS` and the campaign silence both rule it out.
