# Engagement per write (todo/33)

Built and deployed 2026-10-23 at Marc's request (the todo/33 handoff is deleted; see git history). Why we do it: the portal paid ~13,700 points
in 44 h for NPC likes, replies and follows and a handful for persuasion, so the arms are scored on points per write and
per hour, with persuasion as a guardrail.

## What runs

| lever | how it is assigned | what it does | code |
|---|---|---|---|
| `engagers_first` (budget lever) | 2 h switchback blocks, `arm_eng` in `config.SWITCHBACK` with `base` | candidates go: citizens who answered us before, then unsure/unclear, then the freshest posts (a reply within `FRESH_MIN`), then the rest. Groups (sweep, older...) still go after ordinary candidates | `targeting.Targeter.next_target` |
| `follow` (free lever) | per citizen: `engage.cell(citizen_id)`, sha256 of the id mod 4 over `none / follow / like / follow+like` | the replying persona follows the citizen 8-40 s after our **first reply** | `engage.plan`, `bot.engage_actions` |
| `like` (free lever) | same cell | the replying persona views, then likes, the post we answered 90-300 s after the reply | same |
| reply-back follow | every cell | the older behaviour (follow a citizen who answers us), now through the same gates | `config.ENG_FOLLOW_ANSWERED` |

Follows and likes cost no write: they have their own 30/min budgets. The queue lives in `state["eng_queue"]` (saved with the bot state, so a restart
keeps it) and runs in both loops next to `own_likes`.

The conversion arms (`fresh_facts`, `target_order`, `agree_close`) are off the switchback; their code and tests stay, and `arm_conv` logs `base`.

## Limits (todo/33 section 3), all in `config.py`

- At most `ENG_FOLLOWS_PER_DAY` = 40 follows a day per persona, any reason (also reply-backs and the amplifier's follow-backs), and `ENG_FOLLOW_GAP_S` = 60 s between two.
- A follow and a like for the same citizen are never within `ENG_PAIR_GAP_S` = 60 s: the delays make it rare, and the gate puts the later one back a minute.
- Pace comes from the route's own `X-RateLimit-*` headers (`engage.budget_wait`, margin `ENG_BUDGET_MARGIN`); a 429 puts the action back (`ENG_RETRIES` = 3, then it is dropped and logged as `eng_skip`).
- A persona that is parked, gone or asleep (`stealth.asleep`) does nothing. No unfollows, ever.
- Switches: `ENG_FOLLOW`, `ENG_LIKE` (per lever, for every cell), `ENG_FOLLOW_ANSWERED`, or `SWITCHBACK = []` for the arms. All writes stay off in dry runs and in tests.

## What is logged

- Every citizen-facing write: `eng_cell` (the citizen's cell) and `arm_eng` (the block's arm), plus `block_id`.
- `follow` / `like` rows with `purpose` `eng_follow` / `eng_like`, `eng_cell`, `citizen_id`, `why` (`first_reply`, `answered`, or the mode for a like), `voice_id`, `username`, `owner`. A follow row's `account_id` is the citizen followed, as before. No `persona` key, so `followup.py` doesn't read them as voices.
- `eng_skip` rows (why an action was dropped), `follow_failed` / `like_failed` rows.
- `logs/swan_engagement.jsonl` (`followup.py`, every 30 min): per citizen, at +6 h and +24 h after our first reply, whether they follow the replying voice (`followed_back`; `null` when the follower read hit the 1,500-id cap before finding them). One followers read per voice for all its due citizens.
- `citizen_likers` on the post outcome reads (+1 h and +6 h), so the report can say which citizen liked our first reply.

## Reading it: `scripts/engagement_report.py`

```bash
python scripts/engagement_report.py --hours 48        # on the box
```

- **Budget arms:** per `arm_eng`, over its whole blocks (the portal's lines 1 h after each block, as `conversion_report.py` does): writes, hours, likes / replies / reposts / follows, unfollows, persuasion, away, **points per write and per hour**, and a verdict.
- **Free cells:** per `eng_cell`: citizens, follows and likes we made, follow-back rate with a 90% interval, citizen liked / answered our first reply, unfollows, hidden replies, **points per citizen** (like 5, reply 15, follow-back 20, an unfollow after a follow-back nets zero) with its standard error, and a verdict.
- Verdicts follow todo/33 section 4: **kill** an arm whose away events per write beat base or whose unfollows plus away cost more than it gained; **kill** a cell whose unfollow penalty beats its gain, or flag one with more hidden replies per citizen than `none` (then check the ledger for follows or likes); **promote** an arm that beats base per write (needs >= 6 blocks each) and a cell that beats `none` by more than the 90% interval over >= 300 citizens each. Thin numbers are marked thin; the call is a human one.

## Deviations from the todo, and what is not measured

- Citizen likes and replies on our first reply come from the existing +6 h outcome read, not a 24 h one: a 24 h read of every post would take most of the follow-up's 600-reads-per-run budget. Follow-backs are read at 6 h and 24 h as asked.
- Cells act on `reply` and `reply_back` only (not second voices, so one persona acts per citizen). A like on a reply-back is on the citizen's answer.
- The report's per-cell "follow-back" is the replying voice only; a citizen who follows another of our voices is not counted.
- The hourly portal split by kind is parsed from the message text (`analysis.parse_activity`); engagement points are counts times the base points times the line's multiplier, views left out (capped).
- Not tested live: whether a follow or like brings the citizen to our posts. The cells measure it per citizen; nothing here changes how Home ranks.

## Organiser question (draft for #questions, optional)

"Is there any limit or rule on how many citizens an account may follow, or on following citizens who haven't interacted with us?"
