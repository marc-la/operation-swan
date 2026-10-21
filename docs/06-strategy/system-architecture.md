# System architecture: from nothing to a learning bot farm

> Draft 2026-10-19. **Build the smallest thing that scores first**, then add the loop. All write paths default to **dry-run**; turning writes on is an explicit flag plus a human decision (CLAUDE.md conventions). Code goes in `src/<tool>/`, scripts in `scripts/`.

## 1. Context diagram: who talks to whom

```mermaid
flowchart LR
    subgraph World["Game world (CtN systems)"]
        LS["Legit Social<br/>feeds · posts · accounts"]
        NPC["NPC citizens<br/>(LLM agents, ~thousands)"]
        J["AI journalists<br/>Daily Kingstonia · Herald"]
        MOD["Moderator<br/>(~25% wrong)"]
        YES["Yes-side teams' bots"]
        NO2["Other No-side teams' bots"]
        POLL["Polls & referendum"]
        PORTAL["Community portal<br/>score · activity log"]
    end
    subgraph Us["Operation Swan"]
        SYS["Our system<br/>(collector → planner → writer)"]
        HUM["4 humans<br/>frames · approval · Blue"]
    end
    SYS -- "posts / replies / likes / follows / reports" --> LS
    LS -- "feeds, counters, replies" --> SYS
    NPC <-- "read, react, post" --> LS
    YES <--> LS
    NO2 <--> LS
    LS -- "trending content" --> J
    J -- "articles" --> NEWS["News sites"]
    NEWS --> NPC
    NEWS -- "read via API" --> SYS
    MOD -- "hides posts / suspends" --> LS
    NPC --> POLL
    POLL --> PORTAL
    LS -- "scored events" --> PORTAL
    PORTAL -- "manual read" --> HUM
    HUM <--> SYS
```

**The three influence paths** we can use:
1. **Direct:** our post/reply → a citizen reads it in Home/Trending/Latest → engagement or a mind change.
2. **Trending:** engagement on our posts → Trending → many more citizens see it.
3. **Press:** what trends → AI journalists write it up → citizens read the papers. We can *measure* this one: search articles for our frames.

## 2. Data flow inside our system

```mermaid
flowchart TB
    subgraph Ingest
        C["Collector<br/>trending/latest/tags/news<br/>≤ feed budget"]
    end
    DB[("SQLite<br/>posts · accounts · our_accounts<br/>frames · drafts · actions · observations · score_log")]
    subgraph Think
        A["Analyst<br/>stance · frame · NPC-or-bot · doubt detector"]
        P["Planner (bandit)<br/>picks frame × format × target"]
    end
    subgraph Make
        G["Generator<br/>LLM + world bible + persona + frame card"]
        V["Validator<br/>≤500 chars · no artefacts · no injection-like text<br/>no voting logistics · setting-consistent · not duplicate"]
        Q["Approval queue<br/>(human, early days)"]
    end
    W["Writer (ONE process)<br/>team-wide token bucket from rate_limit<br/>jitter · dry-run default"]
    LS["Legit Social"]
    COP["Common operating picture<br/>(dashboard)"]
    FR["Frame library + persona bible<br/>(humans, in docs/)"]
    B["Blue desk<br/>report candidates → human OK"]

    C --> DB --> A --> DB
    FR --> P
    DB --> P --> G --> V --> Q --> W --> LS
    W -- "log every action + bot id + owner" --> DB
    LS -- "counters, replies to us, follows" --> C
    A --> B --> W
    DB --> COP
    PORTAL["Portal activity log<br/>(manual hourly entry)"] --> DB
```

## 3. Components and build order

| # | Component | v0 (by 20 Oct: get on the board) | Later |
|---|---|---|---|
| 1 | **Account registry** | `secrets/accounts.json` (gitignored): username, token, persona, **owner**, status | Track hidden posts and action counts per account; reserve pool |
| 2 | **Persona bible + frame cards** | 5–8 personas, frames F1–F3 + F10 as YAML/MD | Grow from data; retire losers |
| 3 | **Generator** | Script: persona + frame + optional target post → 3 drafts via LLM | Variation, slice-of-life posts, reply mode |
| 4 | **Validator** | Length, banned strings ("Sure,", "Here's", quotes, markdown, `<\|`, "ignore"), duplicate check | Setting fact checks, stance self-check |
| 5 | **Writer** | One process, one queue, reads `rate_limit`, ≤1 post/min at first, random jitter, `--live` flag | Priority queue (replies to fresh doubts first) |
| 6 | **Collector** | Poll trending + latest every few min → SQLite | Tags, replies to our posts, news, account metadata |
| 7 | **Analyst** | Keyword rules: stance + "doubt" phrases ("leaning yes but", "sunset", "which places") | LLM classifier (ask first), NPC-vs-bot model |
| 8 | **Planner** | Human picks | Thompson-sampling bandit over frames |
| 9 | **COP dashboard** | Shared sheet: score, posts/hour, accounts | Streamlit or HTML page off SQLite |
| 10 | **Blue desk** | Human spots leaked-artefact posts, reports | Detector ranking candidates; per-team daily counters |

## 4. The learning loop (human-in-the-loop bandit)

The "fitness landscape" idea, made concrete. Full reinforcement learning is overkill: we get maybe a few thousand noisy signals. A **multi-armed bandit** is the right tool.

- **Arms** = frame × format (original / reply / quote) × target segment. Humans define them (the frame library).
- **Each round** the planner samples an arm, favouring ones that have done well while still trying others (Thompson sampling). The generator writes, a human or the validator approves, and the writer posts.
- **Reward** (what we can observe):
  - Per post via API: `counters()` (views/likes/replies/reposts, all sources), **replies from NPC-looking accounts** and their stance, new followers.
  - Per time window via the portal activity log: changes of mind and contributions (batched, not per post).
  - Weekly: poll results. Ongoing: our frames showing up in news articles.
- **Measurement trick:** mind changes aren't reported per post, so **run frames in time blocks** (e.g. 2 h of F1-heavy, 2 h of F2-heavy) and compare portal deltas, logging which block was live. It's crude, but it's a real signal.
- **Humans stay in charge of meaning:** they add new frames (e.g. reacting to a news story), retire ones that backfire, and approve content until the validator is trusted.

## 5. How 4 people work without stepping on each other

**Key constraint: rate limits are team-wide.** If four laptops each run a poster, we starve each other, trigger 429s and burn the failed-request budget. So:

1. **Exactly one writer process** (on one machine or a small cloud VM) owns all writes. Everyone else **submits to its queue** (a DB table or a folder of JSON drafts). Reads are cheap but feeds are 10/min: one collector, shared DB.
2. **Git from day one** (commit `.gitignore` first): one folder per tool, small PRs, nobody edits the running writer without saying so in chat.
3. **Every action is logged** with bot id, persona, frame and owning human, so attribution is clean and we can do the finalist hand-over.
4. **Kill switch:** a `PAUSE` file or DB flag the writer checks before every write.

| Role (suggested) | Owns |
|---|---|
| **Ops / platform** | Writer, account registry, rate pacing, kill switch, uptime |
| **Data / COP** | Collector, DB, analyst, dashboard, score log |
| **Narrative lead** | Frame library, persona bible, approval queue, news watching, reacting to Yes moves |
| **Blue + red-team watch** | Reporting competitor bots, watching our accounts for hidden posts, opposition analysis, Discord `#questions` |

## 6. Common operating picture (what the dashboard shows)

- Score now vs **next milestone** (≥1 by Poll 1, ≥2,500 by 25 Oct), current multiplier, days left.
- Write budget use: posts/replies/reposts per hour vs 180; 429 count; failed-request count.
- Accounts: active / 50, total used / 200, per-account hidden-post count (suspension at 3), action count (≥100 risk).
- Content: posts per frame/persona last 24 h; top posts by replies/likes; NPC reply stance mix.
- Environment: Trending share by side (ours / other No / Yes), top tags, newest articles with frame matches.
- Queue: drafts awaiting approval; Blue candidates awaiting OK.

## 7. Phased plan

| Dates (Sydney) | Goal | Must have |
|---|---|---|
| 19–20 Oct | **Score ≥1**; first personas live | Components 1–5, manual approval, ≤1 post/min |
| 21–22 Oct | Targeting | Collector + doubt detector → replies to doubting citizens |
| 23–25 Oct | **≥2,500**; first measurements | Time-block experiments, sheet-based COP, Blue desk |
| 26–31 Oct (×2) | Scale what works | Bandit, more personas (stay ≤50 active), follower growth, No-team coordination |
| 1–2 Nov (×4) | Harvest | Best frames, max replies, persona voices (campaign silence), kill switch ready |

## 8. Where the bot runs (hosting)

- **Day 1–2: one laptop, attended.** Human approval needs a person there anyway. Use `tmux` so it survives a closed terminal. WSL and laptops sleep, so expect gaps.
- **From ~22 Oct: a small cloud VM** (any cheap VPS or cloud free tier, or a uni server) running the single writer + collector 24/7 under `systemd` or `tmux`. Rules §5.1 allow cloud services for running our tools. Put `.env` on the VM only (mode 600), never in git, and use one IP (logins/registrations are 5/min per IP).
- **Teammates don't SSH in to post.** They add drafts, personas and arguments through the shared DB or a small web page served by the VM, and the writer picks them up. The kill switch is a flag in the DB.
- **Logs and DB backups** go to the VM disk plus a periodic copy (external storage is allowed for storing data).

## 9. Fact desk: who reviews, when, how (2026-10-21)

**Why.** The news moves daily, and our prompts state facts (on 21 Oct "no community spread" was one paper away from false). Not every edit is made by a strong model or a teammate who knows the setting. So the facts live in one validated file, and the papers are checked every hour.

**Two feeds, two jobs.** Trending ([pulse](amplification.md#trending-pulse-2026-10-21)) decides *how we say it*. Only the organisers' papers (`sites.legitreal.com`) decide *what's true*: a Legit Social post never becomes a fact. **Principles stay, implications move:** the frames (the arguments, in `src/swan_bot/content.py`) change rarely and only by hand; the facts they lean on (`content/facts.toml`) follow the news.

**The pieces.**
- `content/facts.toml`: every fact the prompts may state (text, terse note, status, source, `checked`, extra numbers, `says` wording, optional frames). `tests/test_facts.py` validates every edit and `deploy/check.sh` runs it before a deploy, so a broken edit never goes live. `false_claims` there are rejected everywhere, drafts included (first entry: "no cases").
- Each frame, rebuttal, storyline, lever and `WORLD` sentence names the facts its wording states (`requires`). While one is paused it is not used; character and persona lines matching a paused fact's `says` are left out, a theme whose fact is paused is off, and the quality gate rejects drafts using that wording. A test checks `requires` and `says` agree, so a new claim can't slip into a frame unlinked.
- `scripts/swan_factdesk.py` (EC2, hourly, read-only): new articles, one LLM call per batch, every item tied to a sentence quoted word for word from the article (an unverifiable quote is dropped). **Only removal is automatic:** a contradicted fact is paused in `data/facts_paused.json` (the bot picks it up on its next draft) and alerted ("fact `x` paused … Review: python scripts/facts_review.py"). Rewordings, new facts and argument ideas are proposals only. Opinion columns give ideas only.
- `scripts/facts_review.py` (a laptop with a checkout of `main`): reads proposals and pauses from Mongo, applies a decision to `facts.toml` (or an angle idea to [frames-and-messengers](frames-and-messengers.md)), runs the tests, records the decision, and prints the commit. **A pause ends only with a commit:** it holds while the fact's `checked` is older than the pause, and every decision stamps `checked`. (The EC2 box can't push, so nobody edits the pause file to lift one.)

**Where to decide: the dashboard's Facts section.** Pauses first (red edge), then contradictions, rewordings, new facts and ideas, each with the paper's quote and a link to the article, the wording now and the wording proposed, what in the code it feeds, a one-line hint, and the exact command. Decide on the page, then run the commands on a laptop (several at once: `--accept 9,12 --reject 2,4`). Each decision is appended to `content/fact_decisions.jsonl`, which goes in the same commit: that is how the page hides decided items and how git records who decided. While a pause holds the banner says FACT PAUSED.

**Who and when.**
- **Within the hour of a pause alert** (on the dashboard; `logs/alerts.log`): whoever is on shift (narrative lead first, else Marc). Read the quote; then one of:
  - **The fact changed** (`--accept ID`, with `--text/--note` to fix the suggestion): the old fact is retired and the new wording added under a new key (`<fact>_<MMDD>`, or `--key`). Whatever in `content.py` was written for the old fact (the review lists it: frames, `WORLD`, rebuttals, storylines) stays out of the prompts until someone rewrites it for the new key. That's deliberate: a reworded fact must never bring back a gist built on the old one.
  - **Only the wording was off** (`--accept ID --same-key`): reworded in place; the code that requires it comes back as it is. Example: 21 Oct, `bill_failed` said "Last week", which goes stale; "On 15 Oct" fixes it.
  - **No replacement** (`--accept ID --retire`), or **the paper was wrong** (`--reject ID`: the fact is re-affirmed as it is; papers do slip, e.g. "October 2nd" for the vote, "last month" for the 15 Oct Assembly vote).
- **Daily around the 9 pm Perth rollover:** the narrative lead runs `python scripts/facts_review.py` and goes through the open proposals. New facts need a human check against [setting](../01-competition/setting.md) and the article; a new figure becomes allowed in drafts once its fact is accepted. Angle ideas land in [frames-and-messengers](frames-and-messengers.md#angle-ideas-from-the-fact-desk); turning one into a frame is a code change.
- Then the commit it prints (`git commit -m "Facts: ..." -- content/facts.toml content/fact_decisions.jsonl docs/06-strategy/frames-and-messengers.md`) and `git push`. The approver is the commit author (attribution for the code handover); the bot is live with it in ~2 minutes.
- A Claude session can do the same: "run `python scripts/facts_review.py --list`, then apply proposals 3 and 5".

**Limits.** With no `ALERT_WEBHOOK_URL`, a pause alert only shows on the dashboard: someone has to look. If several pauses leave fewer than 4 frames live, the alert says LOW; with none live the bot drafts nothing (it retries every 5 min) until a review. The desk uses the bot's LLM chain (`config.FACTDESK_MODELS` first); with every model out of quota the articles wait for the next hour.

