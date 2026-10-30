# 62 — China and Yeah: what we may learn, and the race we can win (todo/53 P9)

Written Sat 31 Oct 2026, ~03:30 Perth (30 Oct 19:30 UTC), by Claude for Marc. **Status: no separate build.** The answer to P9
is [todo/58](58-speed.md) (speed) and [todo/54](54-firm-the-no.md) (the No pool split). This file holds the race maths and
the limits on looking at rivals.

Read first: [todo/53](53-the-last-three-days.md) §1 and §3 P9. Rules §5.2.1 and §5.2.2 (CLAUDE.md quotes them).

## 1. The race, red points only (board 30 Oct 17:32 UTC)
Finish = score + pace × (19.5 h at ×2 to 31 Oct 13:00 UTC + 2 × 42 h at ×4) = score + pace × 103.5. Poll awards are already
paid, and the referendum is not included.

| team | score | 24 h pace (todo/53) | finish | last-12 h pace (6 h blocks, 30 Oct 01-13 UTC) | finish |
|---|---|---|---|---|---|
| Operation Swan | 358,564 | 2,232 | **~590k** | 2,278 | **~594k** |
| i wanna go to china | 356,534 | 2,298 | ~594k | 2,606 | ~626k |
| Yeah | 341,688 | 2,483 | ~599k | 2,677 | ~619k |

**On red alone we're third on both paces.** China's 12 h pace passes us about 7 h after the board read, around 31 Oct
00:30 UTC.
- **+5-6% engagement** (todo/58's planning figure) is about +11k: ~601-605k.
- **+11%** is about +22k: ~612-616k. Both apply to about 200k of engagement still to come once it's live.
- **Then the count.** If No wins, Yeah gets nothing from it, and we and china split the No pool by persuasion on 31 Oct-2 Nov
  (todo/53 §2). If Yes wins, Yeah adds 20,000 plus a share of the Yes pool.

## 2. What we know about china (allowed: their score; not allowed: their accounts)
- **The step.** 6 h paces of 1,750-2,050 an hour on 29 Oct, then **2,611 and 2,600 from 30 Oct 01:00 UTC**, against our
  2,199 and 2,356. A step like that is a deploy on their side, not drift.
- **It didn't come out of our citizens.**
  - Our yield on extra citizens (ids above 2343) was 3.09 ± 0.20 a write in the 20 h before 01:00 and 2.96 ± 0.26 after.
  - Classic citizens: 2.29 → 2.16.
  - The target answered us 13.0% → 12.1% (extra) and 8.8% → 8.9% (classic), with the same 41 s median latency.
  - If they had started racing us to the same citizens, our first-reply rates would have dropped.
- **What a No team could switch on for +30%:** extra citizens (+36% a write for us), reply speed, more reply-backs. We
  already do the first and the third. **Speed is the one we haven't pushed** (todo/58).

## 3. What we know about Yeah
- **Above us all week.** Yeah has run 5-15% above our pace.
- **The tide pays them in persuasion.** Our contributions away (93-115 a day) are sessions where a citizen we talked to
  moved toward Yes. A Yes team posting in those sessions shares **+80** per change (we share −40), and takes the 160 when its
  post completes the change.
  - At about 100 such sessions a day across the Yes side, that's a few hundred points an hour for the Yes teams in them.
- **We can't take it from them.** All we can do is stay out of the way: no backfire, and [todo/56](56-backfire.md) found
  none from the flip.

## 4. Looking at rivals: what the rules allow, and why it isn't worth it now
- **Allowed (§5.2.1):** analysing public posts and what draws citizen replies, whoever wrote them, in aggregate.
- **Not allowed (§5.2.2):** de-anonymising or identifying other teams. So no grouping of bot accounts by team, no "china's
  accounts", and nothing in Blue keyed on a team.
- **A fair aggregate read is:**
  - pull Latest for 2-3 h;
  - re-read every bot reply's replies 6 h later (thousands of reads at about one a second, on the box);
  - relate reply features (length, question, @mention, depth, speed) to citizen replies.
- **It would land on 1 Nov,** inside ×4 and the freeze, and the only use would be a prompt change without a test. That is
  what the final-days rule rules out.
- **Two findings already cover most of it:**
  - our replies drew 14.0 citizen replies per 100 in 48 minutes on 29 Oct against 7.5 for rival replies (situation §1);
  - the steepest gradient in our data is speed.
- **Recommendation: skip.** If someone has idle hours on 1 Nov, the read is harmless analysis. Nothing it finds should ship
  before the end.

## 5. Watch
- The dashboard's 3 h pace column for #1-#3 (it exists since 29 Oct).
- After todo/58 goes live, our 3 h pace against china's, the same hours a day earlier, is the plainest read of whether
  speed closed the gap.
