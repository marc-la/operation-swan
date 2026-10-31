# 60 — Reply-backs: we answer two in three, and the "missing" replies aren't on our posts (todo/53 P7)

Written Sat 31 Oct 2026, ~03:15 Perth (30 Oct 19:15 UTC), by Claude for Marc. **Status: closed (Marc approved, 31 Oct): no bot change; §3's doc corrections shipped in 4363550.**
The optional organiser question ([todo/55](55-persuasion-and-the-pool.md) Q16) was not posted. This finding also
changes how P5 and P4 read.

Read first: [todo/53](53-the-last-three-days.md) §3 P7, [engagement-audit](../docs/06-strategy/engagement-audit-2026-10-25.md) finding 2.

## 1. What the data says

**The premise compared two different things.** todo/53 put our 14-18 reply-backs an hour against the portal's about 45
citizen replies an hour. But the portal's replies aren't all on our posts as the platform lists them:
- **Hourly totals.** Over 53 hours (28 Oct 06:00-30 Oct 10:00 UTC) the portal booked **44.8 citizen replies an hour**. On
  the writes of the matching hours our 6 h outcome reads see **19.6**. Likes show the same ratio: portal 54.5 against 23.5
  visible (29-30 Oct).
- **Not late arrivals.** Our 6.3 h check sees 21.5 citizen replies an hour, and the 1.3 h check already sees 20.8. Between
  1.3 h and 6.3 h almost nothing arrives.
- **Not later arrivals either.** On 30 Oct 18:00 UTC, 59 of our posts written 6-25 h earlier (three voices, all suspended
  since) were read again. They had **exactly the 7 citizen replies the 6.3 h check had seen**: 5 within 6 minutes, 2 within
  6 h, none after a suspension. `counters()` agreed (7 = 7).
- **Not hidden from the listings.** 9 of 9 citizen replies to our posts seen in a Latest snapshot were in their post's
  `replies()` list. Every snapshot post was `public`.
- **The extra half rises with the same writes our proxy favours.** By hour, portal replies correlate +0.50 with our visible
  replies, +0.49 with reply-backs, +0.34 with odd-depth and top-of-thread writes, and −0.51 with even-depth writes.

**Conclusion.**
- The portal books about twice the replies and likes that exist on our posts. Whatever the extra is (thread activity
  below our posts, NPC replies that aren't published…), we can't see it, and we can't reply to it.
- The engagement audit's "71% of replies arrive after 6 h" (a public read on 24 Oct, in the many-voice days) doesn't hold
  in the hot-voice days.

**Of the citizen replies we can see, we answer two in three, within about 2 minutes.** Every visible (post, citizen
replier) pair, 29 Oct 04:00-30 Oct 11:00 UTC (n 666, 21.5 an hour):

| what happened | share |
|---|---|
| answered by a reply-back | **67%** (443) |
| skipped `deep_thread`: their reply sits at depth ≥ 8 | 21% (139) |
| unexplained in the logs | 6% (43) |
| skipped `turn_cap` (3 reply-backs to them in 30 min) | 4% (26) |
| voice suspended within 1.5 h of our write | 1% (8) |
| deep by depth arithmetic, no skip row | 1% (7) |

- **Speed:** reply-backs go out fast. 369 of about 450 were sent within 2 minutes of the citizen's reply.
- **Payoff:** reply-backs at depth 7 (ours at 8) earned 1.33 (n 45). The scoring page: past eight messages citizens
  "become much less likely to continue". The deep skip is right.
- **The `lost` `expired:reply_back` rows** (106 in 41 h) are citizen replies the reader saw in Latest and left to the
  reply-back path, which never answered them. Not traced. They are probably the skipped and unexplained rows of the
  table above, seen a second time from the Latest side.

## 2. Recommendation
- **No change to reply-backs.** The remaining leak is small:
  - 4% turn cap, about 0.8 an hour;
  - 6% unexplained, about 1.4 an hour.
- **Don't** revive late replies (LATE_REPLY: 0.71 vs 1.62 on 27 Oct), raise `THREAD_MAX_DEPTH`, or keep voices alive
  longer ([todo/57](57-one-voice.md)). None reaches visible engagement that exists.
- **The turn cap (3 in 30 min):** leave it. 26 pairs in 31 h. A citizen on their fourth turn in half an hour is rare, and
  the value is unknown.
- **Optional** (a cold session with 30 minutes): trace the 43 unexplained pairs through the log (notification read?
  `replied_at_send`? gate rejects?). If one cause covers most of them, fix that alone.

## 3. Doc corrections (do with the next docs push; no restart)
- **[situation-2026-10-29](../docs/06-strategy/situation-2026-10-29.md) §3, point 5 ("Lag. The portal pays a write over
  about two days…"):** add a dated note.
  > *31 Oct: not in the hot-voice days. Our posts' replies arrive within minutes and none after 6 h or after a suspension;
  > the portal's extra half is engagement not visible on our posts ([todo/60](../../todo/60-reply-backs.md)).*
- **[engagement-audit-2026-10-25](../docs/06-strategy/engagement-audit-2026-10-25.md) finding 2:** the same note. The
  24 Oct read stands for its time (many long-lived voices).
- **todo/53 §3 P5 and P7:** the "portal pays about 2.3 times the proxy" still holds as a ratio. It isn't lag, so the proxy
  stays the right thing to optimise: the extra correlates with the same writes.

## 4. What it is worth
- **On reply-backs:** nothing to gain. The value of this item is that no one spends the last day building late-reply or
  multi-voice machinery for replies that don't exist.
- **On the portal's extra half:** organiser question 16 (todo/55) could tell us what it is.
  - It's unlikely to be activity in busy threads below our posts: hours heavy in even-depth writes book *fewer* portal
    replies (−0.51).
  - Until we know, the visible proxy is the guide. It moves with the extra (+0.50).
