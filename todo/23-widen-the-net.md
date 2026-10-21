# 23: Widen the net: every citizen group that can't cost us points, as capped and measured arms

**Owner:** Marc + a fresh Claude session · **Depends on:** todo/21 (shipped), todo/20 (in progress: the light read and the reply style) · **When:** 22 Oct

## Read first
`CLAUDE.md`, [direction-2026-10-21](../docs/06-strategy/direction-2026-10-21.md), [todo/20](20-replies-that-convert.md), [platform-mechanics](../docs/06-strategy/platform-mechanics.md) (the dated todo/21 section), [research B](../docs/06-strategy/research-2026-10-21/B-platform.md) (sessions, notifications) and [research D](../docs/06-strategy/research-2026-10-21/D-competitors.md) (late replies get answered at the next session). Code: `targeting.py` (`hard_skip`, `_consider`, `next_target`, the funnel), `config.py` (the todo/21 block), `content.py`.

## Why
After todo/21, every on-topic citizen item gets a reply, but that is only ~25–100 items an hour, and near zero at Sydney night. We use ~1 of our 3 writes a minute. Marc, 2026-10-22: **"more is better: target everyone who won't lose us points."** A reply to a citizen's own post lands in their notifications and is read at their next session, often a day later. So citizens who aren't posting right now are still reachable. Spare night budget is free.

## The groups, in the order to build them
Every group is an **arm**: a flag, a cap per hour, a priority **below** fresh on-topic citizens (they still get the in-session chance first), and a `group` field on every write and funnel record.

| # | Group | Today | What to do | Cap to start | Why it can't cost points (and the risk to watch) |
|---|---|---|---|---|---|
| A | **Uncontacted citizens** (~2,000 of ~2,330 have never heard from us) | Only reached if they post on topic while we watch | **Sweep:** walk the citizens (`accounts()` / ids 12–2343 plus `EXTRA_CITIZEN_RANGES`), read each one's last posts (`account_posts`, 300/min bucket), and reply to their **most recent on-topic post, any age**. Skip private accounts, hostile posts, deep threads, and anyone contacted in the last 7 days | 20/h, more at Sydney night | A normal reply on their own post; read at their next session. Watch the reply rate on old posts and "away" events |
| B | **Older unanswered posts** (36–72 h) | `TARGET_MAX_AGE_H` 36 cuts them | Keep 36–72 h posts at low priority if we haven't answered them. Other teams answer old posts too (research D: 90–1,650 min lag) | 10/h | Same as A |
| C | **Off-topic citizen posts** | Hard skip `off_topic` | Warm reply on **their** topic in the persona's voice; light humour welcome. **No forced pivot to the referendum.** A natural nod only when the topic genuinely connects (festival, ferries, work, kids, small business, island life: our frames) | 3/h | Engagement (reply 15, like 5, follow 20) plus relationship → follow → Home feed for ×2/×4. **Risk:** spam optics (LS.4.2 "mass unsolicited outreach") and annoyance → hidden posts or away moves. The cap and the no-pivot rule are the guard |
| D | **Engaged quiet citizens:** citizens who liked or followed our voices but don't write | Not targeted (no post to answer) | Reply to their most recent post (any topic, style C if off topic) from **the voice they engaged with** | 5/h | They already chose us: highest reply odds. Use the citizen likers of our posts (`likers`) and voices' citizen followers |
| E | **Lean / firm No** | Priority 0 (answered when nothing better) | Keep. Add a **turnout** angle: why showing up matters, in their own terms. **Never voting logistics** (LS.8.2) | as now | Turnout is part of the referendum (scoring §4: "how likely they are to vote"). Little persuasion, no backfire |
| F | **Journalists** (verified ids 1–11) | Separate path, 0 of 13 answered | Keep at most 1 per 45 min; apply todo/20's style; measure by whether papers pick up No angles | as now | "Persuading a journalist has a huge impact" (launch webinar); low volume |

**Already covered elsewhere:** firm Yes (todo/21's arm, 2/h, concede-first); mid-game citizens (todo/21 G10).
**Out:** @mentions and alliance boosts (grey, organiser questions not asked); hostile posts; anyone a voice has already had 3 turns with this session.

## Measure and kill rules
- Per group, per day: writes, citizen reply rate, likes, follows, and the portal's toward / away / neither (joined to writes, as in todo/20 step 1). Hidden posts per group.
- **Kill a group's arm** if its "away" events per 100 writes exceed the on-topic baseline, or it causes a hidden post. **Raise a cap** when a group's reply rate is ≥ the on-topic baseline for 24 h.
- The funnel gains `group`: the coverage line for groups A–D shows citizens reached per hour.

## Coordination (todo/20 is still running)
- **This session owns:** the new collectors (the sweep, older posts, engaged quiet), the group priorities and caps in `targeting.py`, a `# ---- todo/23 widen ----` block in `config.py`, and `scripts/` for the sweep if separate.
- **The reply style for C and D is todo/20's domain (`content.py`).** Add the job field `group` ("off_topic", "engaged", "sweep", …) and ask ctn-f5 (todo/20) for the style hook, or agree it through the orchestrating session (ctn-2a). Don't edit `content.py` without that agreement.
- Work in your own git worktree; small green commits; dry-run first; push to `main` deploys in ~2 min.
- **Message the orchestrating session (ctn-2a) with each commit hash.**

## Guardrails
- Replies only: no new kinds of writes, no mentions, no follows-for-follow-back.
- One writer, pacing from the rate-limit headers.
- The read budget: `account_posts` / `get_account` have their own 300/min buckets; keep the sweep ≤ 30 reads/min, and **never touch the feed budget** (10/min, per route).
- Quality gate on (todo/20's G9). No prompt injection.

## Done when
Groups A–F are behind flags with caps and the `group` field. The first 24 h per-group numbers are written into [direction-2026-10-21](../docs/06-strategy/direction-2026-10-21.md) with the date. Caps have been raised or cut by the kill and raise rules.
