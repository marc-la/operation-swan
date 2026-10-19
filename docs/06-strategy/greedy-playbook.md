# Greedy playbook: what to do first, what to skip

> Written 2026-10-19 (Day 0) for the first build. It ranks our actions by points per unit of scarce budget, maps the cause-and-effect chains behind them, and gives the simplest automated loop that scores. Background: [scoring-roi](scoring-roi.md), [frames](frames-and-messengers.md), [architecture](system-architecture.md). Items marked **TEST** are assumptions to check in the first 48 h.

## 1. Our scarce resources

1. **3 text writes/min** (posts + replies + reposts), shared by the whole team. This is the main constraint.
2. **Human attention** (4 people, and approval is the bottleneck on day 1).
3. **Account health** (3 hidden posts = suspended; 50 active / 200 total).

Likes, follows and reports each have **their own** budgets, so they come "free" alongside the text budget.

## 2. Explicit vs implicit return (the key distinction)

- **Explicit** = points credited to *our team*: interactions with **our** posts, and mind changes where **our** post completed or contributed to the change. Only our posts earn these.
- **Implicit** = helps the **No side** win: polls (1,000 each), referendum base (5,000) and the chance that the 50,000 pool exists at all. Every No team shares this, including teams that did nothing for it.

So **journalist coverage, flooding Trending for "the cause" and general narrative-shaping are mostly *public goods*** for all No teams. If a news article persuades a citizen, **no team gets Red points for it**, because no team's post did it. The greedy choice is to **put the budget into explicit return** and treat side-level effects as a by-product. The exception is to piggyback on news (§3, chain C), which converts implicit attention into explicit credit.

## 3. The chains, followed through to points

| Chain | Path | Who gets credit | Verdict |
|---|---|---|---|
| **A. Targeted reply** | Citizen posts a doubt → our persona replies within minutes → citizen is notified and reads it → moves | **Us**: 160 + possible reply (15) / follow (20) | **Best ratio.** The audience is exactly a persuadable person, addressed on the exact objection they raised. **TEST:** do NPCs read replies / reply back? |
| **B. Reply under a busy thread** | Trending Yes post or news post → our two-sided reply → readers of that thread see it | Us, for readers moved in that session | **High.** We borrow someone else's audience. The Yes-thread audience leans Yes, so use measured tone (backfire risk). **TEST:** do NPCs open reply threads? |
| **C. News piggyback** | No-friendly article appears (e.g. "Blank Cheque") → news account posts it to Legit Social (they trend) → we reply/quote with persona commentary in minutes | **Us**, on our reply/quote | **High and cheap.** It converts the journalist chain into explicit credit. Poll `news.latest()` every few minutes. |
| **D. Original post → Trending** | Persona post → Latest (sinks within minutes; ~7,400 posts in the first hours) → if early engagement → Trending → many citizens | Us, if it gets there | **Medium.** A lottery ticket: most posts die in Latest. Specific first-person stories have the best odds (that's what trends now). |
| **E. Followers → Home feed** | Citizen follows a persona (+20) → our later posts get Home prominence for them → persuasion at ×2/×4 | Us | **Medium now, high later.** Builds reach for the end-game. Unfollow is −20, so stay on-brand. |
| **F. Following doubters** | We follow a doubting citizen → maybe they follow back → E | Us (indirect) | **Unknown, cheap** (own 30/min budget). **TEST** follow-back rate on 20 citizens. |
| **G. Journalist steering** | Our posts and replies reach journalists → AI journalist writes a No-leaning piece → **every citizen reads the news at least daily** (launch webinar) | Nobody's Red points directly; moves the whole electorate (polls, referendum win) | **Medium-high (revised 2026-10-19).** The organisers called journalist persuasion "a huge impact on the rest of the population", and a 2025 team got a journalist to write their story. The baseline is 35.2/35.2/29, so the referendum is a toss-up and the 5,000 + 50,000-pool upside depends on it. Journalists (`julio_morales`, `amanda_rivera`, …) reply in threads and already lean No-ish ([platform-mechanics](platform-mechanics.md)): a few high-quality replies in *their* threads per day, plus chain C. |
| **H. Contribution "drafting"** | Our posts sit in sessions where minds move toward No (even when another No team's post completes it) → we get a pool share; referendum pool counts it too | Us (share of 80) | **Medium, free.** Be present in the same hot threads and doubts as successful No content. |
| **I. Blue reports** | Spot a sloppy competitor bot → report → upheld after 1.5–24 h → 25 pts and the post is hidden | Us (25), and the side if it's a Yes bot | **High in week 1.** Separate budget, ×1 always (worth relatively most now), helps reach 2,500 by 25 Oct, and hides Yes content. Only report high-confidence cases (wrong = 6 h ban). |
| **J. Self-likes to seed Trending** | Our accounts like our posts → trending score | Us (via D) | **Ask first** (LS.5.3 "reaction farming"; report risk). |
| **K. Volume / slogans / hashtags** | Many generic posts → Latest → views | Views (capped 500/day) | **Low.** Capped, no persuasion, looks like a bot farm. Hashtags only help discovery a little. |
| **L. Broad data mining** | Scrape everything → dashboards → insights | — | **Low in week 1.** Narrow scraping (find doubters, news, bot tells) is all we need now. |

## 4. Value tiers

| Tier | Do |
|---|---|
| **High** | A. Reply to fresh doubts · B. two-sided replies under trending and news threads · C. news piggyback · I. Blue reports on obvious bots · **coordinated push**: 2–3 personas on the same doubt within ~30 min (complex contagion + contribution stacking) · clearing the score milestones |
| **High (side-level)** | G. A handful of strong, specific replies per day in journalists' threads (revised after the launch webinar) |
| **Medium** | D. Specific first-person persona posts (2–4/day per persona) · E. follower building · H. being present in hot No threads · F. follow-back test · quote-reposts of No-friendly articles |
| **Low** | K. Bare reposts · likes on citizen posts (no points, no notification) · hashtag stuffing · generic slogans · L. broad analytics · chasing views |
| **Negative** | Fabricated medical harms · insulting Yes voters · replying to the same citizen repeatedly (spam → unfollow/report) · duplicated or LLM-artefact text (reports → suspension) · anything aimed at the model rather than the reader (silently dropped) |

## 5. Specific, relevant, timely, coordinated

These are the real-world campaign levers, translated to this game:

- **Specific:** answer *the objection the citizen stated* with **one concrete in-world fact**. Specificity means matching their doubt, not inventing claims.
- **Relevant:** the persona matches the citizen (a parent answers a parent; a shop owner answers a shop owner). Use the doubt → frame map below.
- **Timely:** reply **within minutes** of the doubt being posted, while the citizen is likely still in session. Post when NPCs are active and rivals quiet (measure NPC activity by hour).
- **Coordinated:** a second persona adds a different angle on the same doubt ~10–30 min later. **Never** use identical wording, and never pile 5 accounts onto one citizen.

### Doubt → frame map (starter keyword detector)

| Citizen says something like… | Frame | Reply angle |
|---|---|---|
| "sunset", "end date", "temporary", "permanent", "forever" | F2 No end date | "There's no end date on the ballot paper. 'Temporary' needs to be written down." |
| "which places", "list", "designated", "details", "vague" | F1 Blank cheque | "The list comes *after* the vote. If you don't know, vote No." |
| "ID card", "track", "privacy", "data" | F8 Powers outlive governments | "Separate today; the law can change and the system stays." |
| "two-tier", "fair", "outer island", "access" | F6 Two-tier island | Ferry + weekly GP reality |
| "hospital", "nurses", "beds", "ICU" | F10 Fix the hospitals | "40 empty posts; a QR code fills none." |
| "pro-vaccine but", "I'll get it but", "not anti-vax", "overreach", "blanket" | F3 Pro-vaccine, anti-pass | "Same. Getting mine, voting No." |
| "kids", "school", "my daughter/son" | F13 Kids at the school gate | 12+ covered; school named in the question |
| "business", "shop", "tourists", "jobs" | F7 Livelihoods & tourism | Enforcer burden; visitors covered |
| "leaning yes", "undecided", "not sure", "idk", "on the fence" | F1 or F2 | Lowest-backfire frames |

Reply shape (≤ ~280 chars): **grant the concern → one concrete fact → a short genuine question** (questions invite replies, +15).

## 6. The greedy loop (v0, buildable in a day)

```
every ~20 s, while writes are on and the PAUSE flag is off:
  refresh candidates (one collector, within the 10/min feed budget):
      latest + trending feeds, news.latest()
  score each candidate action:
      reply_to_doubt       if post has doubt keywords, author not ours, likely NPC
                           (account created before 2026-10-19T07:00Z, not verified),
                           age < 30 min, author not replied to by us in last 24 h
      reply_to_news        if a news post (or No-friendly article) is < 60 min old
      reply_to_trending    if a Yes post in top-10 trending without our reply yet
      second_voice         if one of our doubt replies is 10–30 min old and the thread is live
                           (thread ≤ 8 messages deep: citizens rarely reply beyond that)
      persona_post         filler when nothing above qualifies (rotate personas/frames)
  pick the highest-priority action whose persona hasn't posted in the last N min
  draft with LLM (persona + frame card + target text + setting facts)
  validate (length, artefacts, duplicates, injection-like strings, voting logistics,
            @mentions ≤ 4 per post / ≤ 3 per reply)
  if APPROVAL_MODE: ask a human (y/n/edit) in the terminal
  send via the single writer (pace from rate_limit; jitter; back off on 429)
  log: action, account, persona, frame, target, owner, timestamp
in parallel, on their own budgets:
  Blue desk: flag leaked-preamble / duplicate / empty-body competitor posts → human OK → report
```

Priority order (greedy): **reply_to_doubt > reply_to_news > second_voice > reply_to_trending > persona_post**. Re-rank after the first 48 h using what earned replies, follows and portal score deltas.

**Persona hygiene:** about 6–8 personas on day 1. Spread writes so no account posts more than ~1 every 10–15 min. Mix in 1 slice-of-life post per persona per few hours.

## 7. Common pitfalls (what other teams will do that we won't)

1. Spending day 1 building infrastructure and posting nothing. **Ship the loop with human approval first.**
2. Four people running separate scripts against one shared rate limit → 429s and a burned failed-request budget. **One writer.**
3. Slogan volume and hashtag floods: capped views, no persuasion, easy Blue targets.
4. Unchecked LLM output ("Sure, here's…", quotes, duplicates) → reported → 3 hidden posts → suspended.
5. Preaching to the No base: engagement but almost no persuasion points.
6. Going hard anti-vax or attacking Yes voters → backfire (−80 each) and a lower No win chance.
7. Over-engineering (RL, big dashboards, full-platform analytics) before we have any signal.
8. Ignoring Blue in week 1, when it's relatively most valuable.
9. "Clever" model-targeted tricks → silently dropped; you just see zero views.
10. Relying on qwen-3B alone (3/min, weak). Use an external model for drafting; keep qwen as backup.

## 8. Tests to run in the first 48 h (cheap, decisive)

| Question | Test |
|---|---|
| Do citizens read and answer replies? | 30 doubt replies → count NPC replies back / follows |
| Can we tell NPCs from bots by `created_at`? | Sample 50 authors; check against obvious bots |
| Do follows get followed back? | Follow 20 doubting citizens; check in 24 h |
| When are citizens active? | Count NPC-looking posts per hour |
| Which frame earns more? | Alternate F1-heavy and F2-heavy 2 h blocks; log portal deltas by hand |
