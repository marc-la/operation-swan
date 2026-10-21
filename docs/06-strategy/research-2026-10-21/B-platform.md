# B. Platform channels: how citizens see content (2026-10-21, ~13:25–13:45 UTC)

Method: client source (`legitsocial.py`, `_http.py`, `newssites.py`), api-reference, platform-mechanics, `targeting.py`, plus about 200 read-only calls: 2 feed reads, 4 `tag_posts`, and the rest per-account and per-post reads. Raw JSON is in `scratchpad/research/braw/`. Samples are small (20 random citizens, ids 12–2343), so treat the numbers as rough estimates.

## Headline findings

1. **Only two things notify a citizen: a reply to their post and an @mention.** The notification API has `kind` = `"reply" | "mention"` and nothing else. Follows, likes and reposts create no notification.
2. **Notifications drive about half of all citizen replies.** In our sample, 30 of 30 post-launch citizen replies went to *team* posts. 14 of the 30 answered a notification: 13 were replies to the citizen's own post and 1 was a 4-mention post. The other 16 came from browsing: 9 top-level team posts and 7 team replies in other threads.
3. **Citizens log in rarely and briefly.** On average a citizen had about 1 session in the ~54 h since launch (4 of 19 had none). A session lasts a few minutes, and the citizen posts, likes and replies within the same 1–5 minutes. Notifications wait for the next session: mentioned citizens liked the post **12 h and 23 h later**.
4. **Teams pile onto every citizen post.** Citizen post 91590 got 9 team replies within 0–12 min, and the author answered 5 of them 3–6 min after posting, all in the same session. Post 36683 got 8 team replies (lags 1, 1, 2, 4, 9, 25, 49 and 358 min). **A reply has to land in the first ~5 minutes to be answered in-session.**
5. **Follow-backs don't happen.** Three citizens had 88, 69 and 9 team followers and followed back none of them. Every follow a citizen made went to a team account that had *never* followed them, mostly the author of a post they had just read or liked. Citizens follow about 1 paper and 0–3 team accounts.
6. **News threads on Legit Social are now dead for citizens.** 7 paper posts from after launch had **0 citizen replies** and 0–12 citizen likers. The pre-launch article posts had 13–21 citizen replies and 86–90 citizen likers. The bot's own log agrees (`citizen_news_replies_last_hour: 0`). Yet `targeting.py` step 1 still reads news threads first.
7. **4-mention posts reach their targets.** Another team (acct 4999, still posting at 13:24 today) posts 4-mention posts. Across 4 of them (16 mentions), views ≈ the number mentioned, there were **6 citizen likes, all from mentioned citizens**, and ≥1 citizen reply. That is ~0.37 likes per mention, versus 0.17 likes per write for our replies.

## (a) Channel table

| Channel | Reach per write/action (evidence) | Rate budget | Rule status |
|---|---|---|---|
| **Reply to a citizen's post** | 1 targeted citizen, notified. Answered in-session if we land in the first ~5 min (896 answered 5 of 9; 2172 answered 4 of 8). Our measured average is 0.15 replies and 0.17 likes per write | Writes: 3/min, shared with posts and reposts | Allowed (rules §5.2.1 "posting, commenting") |
| **@mention in a new post** (≤4) or reply (≤3) | 4 targeted citizens per post (3 per reply, plus the replied-to author = 4). Seen at their next session, up to a day later. ~0.37 likes per mention | Writes 3/min. The mentions are created with the post | **Grey**: allowed up to the ≤4/≤3 cap (scoring guide, 19 Oct note), but LS.5.3 bans "unsolicited mass mentions" and LS.4.2 bans "mass unsolicited outreach" |
| **`mention(post_id, account_id)` on an existing own post** | Presumably notifies the newly mentioned account (the docs say "posts that mention you" notify). `unmention` probably withdraws the notification, as an edit that drops a mention does | **"Every other write" 60/min**, separate from the 3/min post budget (api-reference). The server checks *every* bucket a route belongs to (`_http.RateLimit` docstring), so a hidden shared bucket can't be ruled out without testing | **Likely prohibited if used to re-point.** Rotating mentions on one post turns 3/min into 60/min of outreach: LS.5.2 (circumventing limits), LS.5.3, rules §1.2. Untested. Ask first (draft below) |
| **Follow a citizen** | ~0. No notification kind, and 0 of 166 team follows were returned | Follow 30/min | Allowed, but low value. Mass following may count as "reaction farming" (LS.5.3) |
| **Being followed → Home** | Persistent. Home gives followed accounts prominence, and a citizen's follow list is tiny (1 paper + 0–3 teams), so a follow buys strong Home placement for every later session. Follows come from reading our posts (3 of 12 sampled follows went to an author whose post they liked) | n/a (earned) | Allowed |
| **Trending** | Mostly bots. Top-12 posts: 583 likers, of which 21 citizens (3.6%, 10 unique) between 23:00 and 00:30 Sydney. Our earlier measurement: ~19 citizen likes per post in the evening, ~3 at night | Writes plus seeding likes (30/min) | Allowed. |
| **Latest** | ~47 posts/min. 0 of 100 posts were by citizens at 00:27 Sydney. A post sinks in about 2 min | Writes | Allowed |
| **Tags / `popular_tags` / `tag_posts`** | Citizens rarely tag (5 of 73 citizen posts had a #). 1 citizen post in 400 `tag_posts` results. No sign that citizens browse tags | `tag_posts` 10/min (own bucket), `tag_post` 60/min | Allowed. Little reach |
| **Repost a citizen's post** | No notification. The citizen gains reach, we gain nothing | Writes 3/min | Allowed. Wastes a write |
| **Like a citizen's post** | No notification. It only raises their post's hot score | Like 30/min | Allowed. Little value, and likes from our IDs are reaction-farming optics |
| **News sites** (`NewsSites`) | Read-only JSON with no comments field (article keys: slug, title, summary, byline, body…). The only route in is **linking an article** in a post, which renders as a card | None (separate host) | Allowed |

## (b) Citizen activity and finding persuadable citizens

**Population.** Only ~2,330 citizen accounts exist (ids 12–2343). The "~6,000 citizens" are not all visible as accounts. About 5% are private (1 of 20; their posts, likes and follows return 403). Profiles have no bio: username, display name, avatar and `created_at` only.

**Activity rate.** Since launch, the 19 public sampled citizens made 46 posts or replies (12 top-level, 32 replies, 2 reposts) over ~54 h. That is ~0.045 writes per citizen-hour, or about **100 citizen writes/h platform-wide (~1.7/min, ≈3.5% of Latest)**, of which **~25/h are top-level posts**. Sessions run about **0.45 per citizen per day, or ~40 citizen sessions/h**.

**By hour (Sydney), from the sample's post-launch likes plus posts:** events spread over 01, 05–09 and 11–18, plus 23, with gaps at 02–04, 10 and 19–22. Session starts are spread across the day without a clear peak (n≈26 sessions, too thin to rank hours). The Trending likers we saw were all at 23:00–00:30 (the time of reading). **Recommendation:** log the bot's `citizen_latest_*` refresh fields (in the code, not yet in `swan_actions.jsonl`) for 48 h before changing the schedule.

**Finding persuadable citizens without waiting for them to post:**
- **Enumerate:** `accounts()` lists every account by id, 50 per page (~47 calls for all citizens). Then per citizen, `account_posts` and `account_likes` (each item has `liked_at`, which gives last-active time and stance). At 300/min per route, a slow crawl of all 2,330 at ~20 calls/min takes ~4 h of background reads per pass.
- **Stance signal:** the posts are long, first-person and explicit. 5 of the 19 sampled are visibly "Yes, but…" (896, 2172, 1531, 2111, 295: sunset clause, published thresholds, exemptions), which is exactly F14's target. `targeting.classify` can score them offline.
- **Last session:** max(post `created_at`, `liked_at`). Because sessions are ~1 per 2 days, a citizen who was active in the last few hours is unlikely to be back soon, and one inactive for 24–48 h is "due". A mention placed now is read at that next session.
- **What we can't see:** who *viewed* what, or the private 5%.

## (c) Top 5 reach levers, ranked by targeted citizens reached per hour

1. **Catch every citizen post within ~3 min and reply first.** The ceiling is ~25 top-level citizen posts/h plus ~75 citizen replies/h, all of which notify. Today the targeter sees ~25% of Latest. Reading `feed_latest(limit=100)` every ~100 s (≈0.6 feed calls/min, well inside 10/min) covers ~100%, which is **~4× more reachable citizens** (~25 → ~100/h). Answering in-session is what gets the ~50% answer rate. Rule status: allowed.
2. **Add up to 3 @mentions to replies and posts aimed at pre-profiled "Yes, but" citizens** who share the doubt being answered ("@a @b you asked about the sunset too"). That gives up to 4 targeted citizens per write instead of 1, reaching citizens who aren't posting, at their next session. At 1 write/min devoted to this, it is up to **~240 targeted citizens/h**, with ~0.37 likes per mention measured on another team. Rule status: **grey (LS.5.3). Get a ruling first.** Keep it 1:1 relevant, never the same citizen twice, and log every mention.
3. **Stop reading news threads (targeting step 1) and move those reads to Latest coverage and profiling crawls.** Post-launch news threads hold 0 citizen replies. This doesn't add reach directly, but it frees ~10–20 reads per refresh.
4. **Earn follows by writing posts that fit citizens' "Yes, but" register,** so later posts sit prominently in a near-empty Home feed. A follow is +20 now, and Home placement compounds into the ×2/×4 days. About 2 follows per citizen session go to authors they just read. Don't follow citizens to get followed back: 0 of 166.
5. **Trending in the Sydney evening only, with article links.** Trending is 96% bot likers at night. Spend amplification on 17:00–23:00 Sydney windows and link No-friendly articles (card embed), since news posts themselves no longer draw citizens.

## Draft for #questions (Discord)

> Hi organisers. Operation Swan question on LS.5.3 ("unsolicited mass mentions") and the scoring guide's ≤4 mentions per post / ≤3 per reply. (1) Is it within the rules for a post or reply to @mention citizens who haven't interacted with us, if each mention is relevant to something that citizen has said, we never mention the same citizen twice, and we stay within 4/3 per post? (2) Is it acceptable to use `Account.mention(post_id, account_id)` to add mentions to an *existing* post after publishing? We assume that rotating mentions on one post (unmention/mention to reach new people) would circumvent the posting limit (LS.5.2) and plan not to do it unless you say otherwise. (3) Is the `mention` endpoint subject to the 4-per-post cap? Thanks!

## Caveats
- I tested no writes. The mention endpoint's notification behaviour, cap and bucket are inferred from the docs and source.
- n=20 citizens, 4 mention posts and 2 pile-on threads. Rough estimates only.
