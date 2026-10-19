# API Reference — `capturethenarrative` Python package (v0.5.x = CTN 2026; we pin 0.5.1)

> Source: the official package README (PyPI `capturethenarrative` 0.5.0; GitHub `capturethenarrative/pypi-capturethenarrative`, local clone in `src/pypi-capturethenarrative/` at commit `ffa3a7c`). Method list cross-checked against `legitsocial.py`. If the organisers publish a newer version, re-diff it against this file. *Updated 2026-10-19:* 0.5.1 is out. Its only change is the LLM brotli fix in [environment](environment.md#notes). The API is otherwise identical to 0.5.0, so this file still applies.
>
> A small Python client for the **Legit Social** social network, the in-universe **news sites**, and the **competition LLM**. Python ≥ 3.9; only dependency `openai>=1.0`. Convention: `import capturethenarrative as ctn`.
>
> **Servers are only reliably up during the competition.** Check Discord for status.

## Default endpoints

| Constant | Value |
|---|---|
| `ctn.DEFAULT_LEGIT_SOCIAL_URL` | `https://social.legitreal.com/api` |
| `ctn.DEFAULT_NEWS_SITES_URL` | `https://sites.legitreal.com` |
| `ctn.DEFAULT_COMPETITOR_LLM_URL` | `https://llm.legitreal.com/v1` |

Pass `url=` to any constructor to target a different, API-compatible server (e.g. a local mock). Legit Social and the news sites return **plain dicts/lists exactly as the servers send them** — what you see in the browser network tab is what you get.

Classes: `ctn.LegitSocial`, `ctn.Account`, `ctn.NewsSites`, `ctn.CompetitorLLM` (also under `ctn.legitsocial`, `ctn.newssites`, `ctn.competitorllm`).

---

## Legit Social

```python
social = ctn.LegitSocial(url=None, timeout=20.0, max_retries=5, on_rate_limit=None)
```

### Accounts & sign-in
`register`, `login`, `account_from_token` each return a `ctn.Account`.

```python
ada = social.register("ada_username", "a-really-secure-password", "MYTEAMCODE123456", display_name="Ada L.")
ada = social.login("ada_username", "a-really-secure-password")
ada = social.account_from_token(saved_token)     # resume without the password

ada.account_id, ada.username, ada.display_name
ada.profile        # account dict as last sent by server
ada.me()           # {"account", "role", "team"}; refreshes ada.profile
ada.token, ada.expires_at
```

- **Save `ada.token`** and resume via `account_from_token` to avoid a login each run (logins are rate-limited). Expired token → `APIError` status **401** → `login` again.
- The team key is **checked once at registration and never stored**. Passwords **8–72 bytes**. Usernames **≤ 32 chars**, unique site-wide. Password can't be changed later (per getting-started).
- The portal shows how many accounts your team may have at once and how many may be active at once.

### Feeds
```python
social.feed_latest()     # newest first
social.feed_trending()   # ranked feed
ada.feed_home()          # personalised (needs login)
```
Listings return a **`Page`**: a list with a `.next_cursor` (`None` when finished). A page that exactly fills `limit` can still carry a cursor, and the next page is then empty. Pass `cursor=` back, or walk everything:
```python
for post in social.iterate(social.feed_trending, max_items=200): ...
```
Default `limit=50`.

### Reading posts and accounts (work on `social` and any account)
```python
social.get_post(post_id)
social.counters(post_id)          # like/reply/repost/view counts
social.replies(post_id)
social.likers(post_id)
social.tags(); social.post_tags(post_id)
social.popular_tags()                       # up to 15, most used in last 24h
social.tag_posts(tag_id)                    # most recently tagged first
social.tag_posts(tag_id, sort="trending")   # hottest first, trending posts only
social.post_mentions(post_id)

social.accounts(q="ada")          # username prefix search, any case
social.accounts(verified=True)    # only verified-badge accounts
social.get_account(account_id)
social.followers(account_id); social.following(account_id)
social.account_posts(account_id); social.account_likes(account_id); social.account_mentions(account_id)
social.feed_lock()                # {"locked", "reason", "updated_at"}
```
- **Private accounts** (`"private": True`): the five per-account reads (followers, following, posts, likes, mentions) return **403** unless you're that account or an organiser; `get_account` omits `created_at`. Their posts still appear in feeds and they can still be followed.
- While the feed is **locked** (by a moderator, or because the competition ended) **every write returns 403** except `view` and resolving notifications.

### Posting
```python
post  = ada.post("Vote early, vote often. #referendum")     # optional visibility=
reply = ada.reply(post["post_id"], "Replying to myself")
reply = ada.reply_to(some_post_dict, "Keeps the thread's root for you")
rp    = ada.repost(post["post_id"])                          # bare repost
rp    = ada.repost(post["post_id"], "With commentary")

ada.update_post(post_id, body="edited", visibility="public")
ada.delete_post(post_id)      # deleting a repost undoes it
ada.view(post_id)             # register a view
```
- `#word` in a body → tag automatically; `@username` → mention that account. A reply notifies the replied-to author; a mention notifies the mentioned account.
- Empty/whitespace-only body is stored as **no body**. **Max 500 characters** (per getting-started).
- An account may hold **one live repost** of a given post; a second is **409** until the first is deleted. Reposting a repost reposts the original.
- `update_post` **replaces the whole body** (omit `body` and it clears). Tags/mentions are **re-derived** from the new body, dropping any added via `tag_post`/`mention` that the body doesn't carry.
- ⚠️ *Editing a post triggers re-screening for prompt-injection* ([scoring §7](../03-scoring/scoring-guide.md#7-posts-that-earn-no-points)).

### Likes, tags, mentions, follows
```python
ada.like(post_id); ada.unlike(post_id)
ada.my_likes([1, 2, 3])        # -> set of ids ada has liked
ada.my_reposts([1, 2, 3])      # -> {post_id: ada's repost_id}

ada.create_tag("referendum")
ada.tag_post(post_id, "#referendum"); ada.untag_post(post_id, tag_id)

ada.mention(post_id, account_id, start_offset=None, end_offset=None)
ada.unmention(post_id, account_id)

ada.follow(account_id); ada.unfollow(account_id)
```

### Notifications
Queue of replies to your posts and posts that mention you, newest first (self-reply/mention never notifies).
```python
ada.unresolved_notification_count()            # -> 3
page = ada.notifications(unresolved=True)      # a Page
for n in page:
    n["kind"]                  # "reply" | "mention"
    n["actor"]["username"]
    n["post"]["post_id"]       # trimmed; get_post() for the whole thing
    ada.resolve_notification(n["notification_id"])

ada.resolve_all_notifications()                                    # -> count resolved
ada.resolve_all_notifications(up_to_id=page[0]["notification_id"]) # only ids ≤ that
```
Entries vanish when the post is deleted/hidden, an edit removes the mention, or while you've unfollowed the author (following again restores them). `resolve_all_notifications` also resolves currently-hidden entries.

### Profile
```python
ada.update_profile(display_name="Ada Lovelace")      # omitted fields keep values
ada.update_profile(avatar_url="https://example.com/ada.png")
ada.set_private()      # or set_private(False); ada.private says which
ada.delete()           # delete the account
```

### Reporting (Blue track)
```python
ctn.POST_REPORT_REASONS     # ("hate_speech", "illegal_content", "inauthentic", "other")
ctn.ACCOUNT_REPORT_REASONS  # ("harassment", "impersonation", "inauthentic", "other")

ada.report_post(post_id, "inauthentic",
    "I think that this content is inauthentic (bot) activity because five accounts posted the same words")
ada.report_account(account_id, "inauthentic",
    "I think that this account is conducting inauthentic (bot) activity because it posts every 20 seconds")
```
- **Detail is required.** Begin: `"I think that this content is <reason> because..."` (post), `"I think that this account is conducting <reason> because..."` (account), `"...should be reviewed because..."` for `"other"`. A blank detail = **400** whose message gives the opening for your reason — **and the refused attempt still burns your 3/min report budget.**
- A post reported by enough different teams hides itself until a moderator rules. An account reported `"inauthentic"` is ruled on by automated moderation: **suspended if it already has a moderator-hidden post and ≥100 actions; otherwise the report is dismissed** and the account may be re-reported. Scoring: [scoring §3](../03-scoring/scoring-guide.md#3-reporting-inauthentic-posts-and-accounts).
- Only **`inauthentic`** reasons earn Blue points; others go to human moderators for no points. Bad-faith reporting is a violation (LS.6.5).

### Errors

Any non-2xx raises `ctn.APIError` with `.status`, `.message`, `.json`.

| Status | Meaning |
|---|---|
| **400** on a report | Reason not in vocabulary, or detail missing/blank (`e.message` says how to begin it) |
| **401** | Token expired → log in again |
| **403** + `e.not_ready_reasons` | Team not cleared to compete — writes to posts (post, edit, delete, like, mention, tag, report, and undoing those) refused. List says what to fix in the portal. **On `register`: the competition hasn't started yet** |
| **403** on `register`, no reasons | Team's account allowance is used up; `e.message` says total cap vs active cap. Deleting an account frees an *active* slot but never a *total* slot |
| **403** "account suspended" | Moderator suspended it: can read but can't log in or write |
| **403** "the feed is locked" | Read-only (moderator, or competition ended); `feed_lock()` says which |
| **403** "prefers their privacy" | Private account's followers/following/posts/likes/mentions not readable |
| **409** | Username taken, or you already reposted that post |
| **429** | Rate limited — client sleeps `Retry-After`, retries up to `max_retries`, then raises `ctn.RateLimited` (subclass of `APIError`) with `.retry_after` |

### Rate limits

Per minute, **separate budget per route, shared by every account on your team**:

| Route | Per minute |
|---|---|
| `post`, `reply`, `reply_to`, `repost` (**one shared route**) | **3** |
| `like`, `unlike`, `view`, `follow`, `unfollow`, `delete_post` | 30 each |
| `report_post`, `report_account` | 3 each |
| feeds (`feed_latest`, `feed_trending`, `feed_home`) | **10 between them** |
| `tag_posts` | 10 (separate from the feeds) |
| every other read | 300 each |
| every other write | 60 each |

- **Failed requests draw from a separate, smaller budget**: **20** for posting, **10** for the others (and on like-style routes that second budget is the tighter one) — so retrying something that will fail (duplicate like, deleted post) runs you out sooner.
- `register` and `login`: **5 successes/min each, counted per network address**, plus registrations per team key.
- **Organisers may scale every limit — pace from `.rate_limit`, not these numbers.** Set `max_retries=0` to handle 429s yourself.

Pacing from headers:
```python
social.feed_trending()
social.rate_limit        # RateLimit(limit=10, remaining=9, reset=58)
```
`limit` = budget for that route; `remaining` = requests left; `reset` = seconds until whole again. The bucket refills **steadily** (a spent one is good for another request after ≈ `reset/limit` s). `remaining == 0` ⇒ next call is a 429. `rate_limit` is `None` until a response arrives (a few errors like 401 carry no headers). Callback for the whole team:
```python
def pace(limit):
    if limit.remaining == 0:
        print("out of budget; a slot frees in", limit.reset / limit.limit, "s")

social = ctn.LegitSocial(on_rate_limit=pace)   # shared by every account made from `social`
```

---

## News sites

The newspapers/campaign sites the narrative publishes on. **No key needed**; every page is also JSON.

```python
news = ctn.NewsSites()
news.sites()                           # [{"id","name","sub_url","url","tagline","about","logo_url"}, ...]
news.front_page("kingstonia-herald")   # {"site","categories","articles"}
news.articles("kingstonia-herald")     # front-page pieces, newest first, no bodies
news.article("kingstonia-herald", "ferry-strike-enters-third-day")   # one piece, markdown "body"
news.author("kingstonia-herald", "amanda-rivera")        # {"site","author","articles"}
news.category("kingstonia-herald", "transport")          # {"site","category","articles"}
news.latest(20)                        # newest across every site; each has a "site" key
```
A site argument is the publication's `sub_url` (the path in the browser) or a site dict from `sites()`. Article `published_at` is the **in-story date**, which may run ahead of the real clock. (Example slugs above come from the README and may not exist in 2026 content.)

---

## Competition LLM

One model: **`qwen2.5-3b-instruct`**, OpenAI-compatible, **team code = API key**. `CompetitorLLM` is the standard `openai.OpenAI` client pre-wired.

```python
llm = ctn.competitorllm.CompetitorLLM(url=None, team_code="QK7XJ4M2P9RTZC8W", max_retries=3)
llm.ask("Name three rivers.")                                    # -> str
llm.ask("Summarise this post: ...", system="Be terse.", max_tokens=100)

stream = llm.chat.completions.create(
    model=ctn.competitorllm.MODEL,            # the only accepted model
    messages=[{"role": "user", "content": "Write a limerick about ferries."}],
    max_tokens=200, stream=True)
for chunk in stream:
    if chunk.choices and chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```
- Constructor **refuses to start without a team code**, so it can never fall back to `OPENAI_API_KEY` in your environment.
- **Limits (team-wide, shared across all your scripts):** 3 req/min (burst 2), **1 request at a time**, ≤1024 generated tokens, `n` = 1. A 429 is retried `max_retries` times after `Retry-After`, then raised as `openai.RateLimitError`.
- Errors: **401** `AuthenticationError` (bad team code), **403** `PermissionDeniedError` (team can't compete now — message says why), **400** `BadRequestError` (other model, or `n` > 1).
- **Every request is logged by the organisers.**

> **External LLMs** (GPT, Claude, DeepSeek, Gemma…) are *allowed for creative content generation* (rules §5.1/§5.2.1), subject to their licences/ToS. The provided qwen 3B model is weak and heavily rate-limited (3/min vs 3 posts/min); an external model is likely needed to keep post quality up. Anything sent to an external model is still your responsibility and is in-scope for attribution/logging.
