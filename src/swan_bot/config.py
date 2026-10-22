"""Settings for swan_bot. Secrets come only from .env / the environment and are never printed."""
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
SECRETS = ROOT / "secrets"          # gitignored: account passwords and tokens
LOGS = ROOT / "logs"                # gitignored: every action we take
DATA = ROOT / "data"                # gitignored: working state
ACCOUNTS_FILE = SECRETS / "swan_accounts.json"
STATE_FILE = DATA / "swan_state.json"
STATUS_FILE = DATA / "status.json"    # live bot health for the dashboard (todo/09)
ACTIONS_LOG = LOGS / "swan_actions.jsonl"

LAUNCH_UTC = "2026-10-19T07:00"     # teams could only register from launch; earlier accounts are seeded citizens
CITIZEN_MAX_ID = 2343               # last pre-launch account id (checked 2026-10-19); covers private accounts
OFFICIAL_MAX_ID = 11                # ids 1-11: papers, journalists, campaign leads, politicians, moderation (verified)
NEWS_IDS = (1, 2)                   # DailyKingstonia, KingstoniaHerald: citizens reply under their article posts
JOURNALIST_IDS = (3, 4, 5, 6)       # amanda_rivera, muzhi_wong, julio_morales, lisa_podworth (verified)


def is_citizen(account_id):
    """The one id rule for 'a citizen did this' in every metric (todo/19): seeded before launch, not an organiser
    persona (1-11), or in a range of citizens added mid-game (EXTRA_CITIZEN_RANGES). Other ids above CITIZEN_MAX_ID
    are team accounts, ours or another team's."""
    i = account_id or 0
    return OFFICIAL_MAX_ID < i <= CITIZEN_MAX_ID or any(lo <= i <= hi for lo, hi in EXTRA_CITIZEN_RANGES)


MAX_ACCOUNTS = 21                   # lifetime cap on voices: 12 used + 5 promoted 21 Oct + 4 replacements; boosters: MAX_BOOSTERS
REGISTER_GAP_S = (20 * 60, 40 * 60) # drip registration: one new account every 20-40 min, never a burst
ACCOUNT_MIN_GAP_S = 4 * 60          # one voice writes at most every 4 minutes (todo/03); todo/31 jitters it (VOICE_GAP)
# Moderator-hidden posts per voice (scripts/swan_watch.py). 1 hidden + ≥100 actions = the next account report
# suspends it; 3 hidden = suspended (scoring guide §3). Lost @lani_wharfcafe23 this way on 2026-10-20.
HIDDEN_OFF_AMP = 1                  # this many: off amplified posts and threads (less on show, fewer reports)
HIDDEN_STOP = 2                     # this many: stops writing (one more hidden post would suspend it)

# 2026-10-21 late: every 2 min (was 4). Citizens are online a few minutes per session, and the replies they answer
# in-session landed in the first ~5 min (ctn-68's reach study, 2 posts: 5 of 9 and 4 of 8 team replies answered).
REFRESH_S = 2 * 60
FRESH_MIN = 10                      # a citizen post this new is answered first (they may still be online)...
FRESH_BONUS = 4.0                   # ...by this much on top of its score (scores run ~1.5-10)
# 2026-10-21: Latest runs at ~47 posts/min, nearly all team bots (500 posts in 10.7 min, 7 by citizens), so one
# 50-post read every 4 min saw ~1 min in 4. Each refresh now pages back to the newest post the last one saw.
LATEST_PAGES = 3                    # at most this many 100-post reads per refresh (~6 min of Latest)
FEED_READS_SPARE = 3                # stop paging when the team-wide feed budget (10/min) has this few left
TARGET_MAX_AGE_H = 36               # citizens' notifications are near-empty, so a day-old comment still lands
# Citizens replying under Trending posts: a reply there is read by the thread's viewers (300-480 views per Trending
# post), not just by the citizen. 2026-10-21: read 12 threads (was 6) and rank these targets above news replies.
TRENDING_THREADS = 12
TRENDING_THREAD_BONUS = 1.5
SECOND_VOICE_S = (10 * 60, 30 * 60) # a second persona follows up on the same doubt 10-30 min later
# 2026-10-21 late (todo/19): back on. Citizen likes / replies per write, all measured writes: reply 0.17 / 0.15,
# reply_back 0.11 / 0.07, second_voice 0.06 / 0.08, own-thread reply 0.03 / 0.03. Both beat the thread replies they
# had given their slots to, and citizen replies on the portal fell from 4-12/h to 1-4/h while they were off.
# 2026-10-22 (Marc, stealth): off. 294 of 730 citizens got two of our voices within 60 min, which reads as a reply
# ring to other teams' Blue reporters; 33 posts hidden, 16 voices hit. Its writes go to first replies (0.17 vs 0.06).
SECOND_VOICE = False
REPLY_BACK = True
REPLY_BACK_AMP = True               # with REPLY_BACK off: still answer citizens replying in our amplified threads
JOURNALIST_MAX_AGE_H = 12
JOURNALIST_GAP_S = 45 * 60          # at most one journalist reply per 45 min
JOURNALIST_SAME_GAP_S = 6 * 3600    # and the same journalist at most every 6 h
POST_EVERY_N = 4                    # persona posts: at most 1 in every 4 writes (replies come first)
IDLE_POST_GAP_S = 30 * 60           # ...or one every 30 min when there is nothing better to write

# ---- todo/21 targeting: reach every citizen (todo/21-reach-every-citizen.md) ----
# G1 (2026-10-22): feed_latest and feed_trending share 10 reads a minute, and the bot found <= 3 left when it paged
# Latest. The bot is the one Latest reader (data/latest_snapshot.json for swan-blue, feeds.py), Trending every 3rd
# refresh (6 min). Every feed read is logged to logs/feed_reads.jsonl.
TRENDING_EVERY = 3
# G10: citizens the organisers add mid-game, as (first_id, last_id). scripts/citizen_watch.py (hourly, in swan_watch)
# alerts on a run of ids that looks seeded; a person confirms it (ideally against a Discord announcement) and adds it
# here. Never automatic: a wrong range sends our replies to team bots and pollutes every metric.
EXTRA_CITIZEN_RANGES = []
# Unread Latest stretches kept for later refreshes (G2); beyond it, the oldest is logged as lost. 2026-10-22 (todo/24):
# 6 -> 60. At Sydney peak the feed budget (10/min, and the server's own buckets: X-RateLimit-Remaining 0-3 though
# our processes read ~1/min) allows one page a refresh, so each refresh at > 100 new posts leaves a band; 6 filled in
# 12 min on 21 Oct and 3 were dropped. A band is two numbers; they're read back once the budget allows (off-peak).
LATEST_MAX_BANDS = 60
# Per post and per session, not per author (was 72 h per author: a citizen answered on Monday who posted again on
# Wednesday was skipped, while other teams answer every post). One thread per citizen post (replied_posts), and at most
# SESSION_VOICES of our voices per citizen per session (~30 min: citizens are online 1-5 min every ~2 days).
CONTACT_COOLDOWN_S = 30 * 60        # one citizen session: the window for SESSION_VOICES
SESSION_VOICES = 2
ENGAGED_BONUS = 3.0                 # a citizen who replied to us before goes up the queue (they answer again)
DEEP_THREAD = 8                     # citizens rarely reply past this depth: skip deeper threads (G11)
# The firm-Yes arm (todo/21 design): concede-first replies (todo/20 maps job["arm"] to that style) to firm Yes posts,
# tested at x1 before the x2/x4 days. Stop rule: switch it off if "away" events per 100 writes rise over the baseline.
FIRM_YES_ARM = True
FIRM_YES_PER_H = 2                  # a few % of ~40-55 citizen-facing writes an hour at peak

# ---- todo/23 widen: every citizen group that can't cost us points, as capped and measured arms ----
# 2026-10-22 (Marc: "more is better: target everyone who won't lose us points"). Each group is an arm: a flag, a cap
# per hour (None: no cap), and a place below fresh on-topic citizens (they still get the in-session chance first:
# targeting.next_target hands out a group candidate only when no ordinary one can go). Candidates and funnel records
# carry the group; content.group_style(job) gives the reply its line (todo/20's hook). Kill an arm if its "away"
# events per 100 writes pass the on-topic baseline or it causes a hidden post; raise its cap when its citizen reply
# rate holds at or above the baseline for 24 h.
# A, the sweep: walk every citizen (ids 12-CITIZEN_MAX_ID plus EXTRA_CITIZEN_RANGES), read their last posts and queue
# their most recent post on the vote, any age. A reply lands in their notifications and is read at their next session.
SWEEP_ARM = True
SWEEP_PER_H = 20
SWEEP_NIGHT_PER_H = 40              # Sydney night (NIGHT_HOURS): few citizens post, the write budget is idle
NIGHT_HOURS = range(0, 7)           # Sydney hours (LOCAL_TZ)
SWEEP_READS_PER_REFRESH = 40        # account_posts + get_post reads per refresh (every 2 min): <= 20/min, cap 30/min
SWEEP_READS_SPARE = 100             # stop when an account_posts / get_post bucket (300/min, team-wide) is this low
SWEEP_QUEUE = 20                    # read citizens only while fewer sweep candidates than this wait
SWEEP_RECONTACT_S = 7 * 86400       # skip a citizen any voice wrote to in the last 7 days
SWEEP_REVISIT_S = 24 * 3600         # a citizen with nothing to answer is read again a day later
GROUP_QUEUE_S = 12 * 3600           # a swept (or engaged) candidate not handed out by then is lost (expired)
# B, older posts: unanswered citizen posts 36-72 h old stay queued (were lost at TARGET_MAX_AGE_H), at low priority.
OLDER_ARM = True
OLDER_MAX_AGE_H = 72
OLDER_PER_H = 10
# C, off-topic citizen posts: a warm reply on their topic, no pivot to the vote (content.off_topic_prompt). 2026-10-22:
# 1 of 4 dry-run drafts turned to the vote ("it's the pass I can't stand... Voting No"); now the off-topic system
# prompt leaves the referendum out and the gate rejects a turn to it (quality: off_topic_vote, 60-220 characters):
# 6 of 6 dry-run drafts on their topic, first call. On.
OFF_TOPIC_ARM = True
OFF_TOPIC_PER_H = 3
OFF_TOPIC_RECONTACT_S = 3 * 86400
# D, engaged quiet citizens: citizens who liked our voices' recent posts or follow a voice; we answer their most
# recent post from the voice they engaged with (job["prefer"], bot.candidate_voice). Their off-topic posts need
# OFF_TOPIC_ARM too. 2026-10-22 dry run: 32 reads, 4 candidates, 4 drafts passed the gate first time.
ENGAGED_ARM = True
ENGAGED_PER_H = 5
ENGAGED_RECONTACT_S = 2 * 86400
ENGAGED_POSTS_H = 48                # our posts this recent are read for citizen likers, one voice per refresh
# E, lean / firm No: answered as now (no cap), with the turnout line (why showing up matters; never logistics).
TURNOUT_ARM = True
# F, journalists: as now (JOURNALIST_GAP_S); this flag switches them off.
JOURNALIST_ARM = True
# Order among the groups once ordinary candidates are done (turnout is ordinary: it keeps its place)
GROUP_ORDER = ("engaged", "older", "sweep", "off_topic")

# ---- amplification (docs/06-strategy/amplification.md). On only with --amplify; touch AMPLIFY_OFF to pause it live ----
AMP_OFF_FILE = ROOT / "AMPLIFY_OFF"
MAX_BOOSTERS = 36                   # like-only accounts (never post, so they can't be suspended under the published rules)
MAX_ACTIVE = 49                     # the platform allows 50 alive at once; 1 is a team member's own (portal 47 vs our 46, 21 Oct)
BOOSTER_REGISTER_GAP_S = (4 * 60, 9 * 60)
# 2026-10-20 late: 11 measured posts peaked at hot ~23 vs a top-35 cutoff ~24 (0 entered Trending). Fewer posts,
# each pushed over the line: a repost weighs ~8 likes, and the engagement has to land in the first ~15 min.
# 2026-10-21: 16 heavy posts at 36-46 likes, 3-5 replies, 4-8 reposts: 0 in Trending, 0 citizen views. The posts that
# trend carry 40-90 team likes AND 20-66 team replies. So: one post an hour, every one heavy, ~15-20 thread replies
# (each voice may reply twice) on top of the reposts (the fit's heaviest signal; the write budget was 83% idle).
AMP_POST_GAP_S = (50 * 60, 70 * 60) # one amplified original an hour
# per level: own likes, own-thread replies, reposts (ranges, inclusive). Likes are capped by the accounts awake.
# 2026-10-21 late (todo/19): heavy back to 4-6 thread replies (was 15-20 for ~8 h: 0 Trending entries in 40 posts,
# 0.03 citizen likes per thread reply, and the citizen replies starved). todo/18's booster reposts take those slots.
AMP_LEVELS = {"heavy": dict(likes=(36, 46), replies=(4, 6), reposts=(5, 6)),
              "light": dict(likes=(10, 16), replies=(1, 2), reposts=(0, 1)),
              "none": dict(likes=(0, 0), replies=(0, 0), reposts=(0, 0))}
AMP_PRIOR = {"heavy": 1.0, "light": 0.0, "none": 0.0}   # 2026-10-21: always heavy (was 0.8 / 0.1 / 0.1)
AMP_EXPLORE = 0.0
THREAD_PER_VOICE = 2                # thread replies one voice may write under one amplified post
# priority lane: other writes wait this long after an amplified post (thread first). Citizen replies never wait
# (bot.pick_job puts them first); it holds second voices, journalist replies and plain posts. 2026-10-21: 20 -> 5 min.
AMP_PRIORITY_S = 5 * 60
# The amplified post is our best content: drafted on the strongest models first, the usual chain if they are out.
# The bot's key is on the free project: 3.8 and 3.6 Flash have 20 requests a day each (deploy/llm_chain.txt).
# 2026-10-21: Kimi K2.5 and GLM-5 on Bedrock lead (best drafts in llm_compare, paid from the AWS credits); then the
# free Gemini Flash models and qwen-plus-character (Alibaba free quota, 1M tokens to 2027-01-20).
# Order comes from deploy/llm_chain.txt, not from this tuple.
AMP_MODELS = ("moonshotai.kimi-k2.5", "zai.glm-5", "gemini-3.8-flash", "gemini-3.6-flash", "qwen-plus-character")
# Where persuasion happens, drafts get strong models too: replies to citizens (a change of mind is 160 points), on
# REPLY_MODELS since 2026-10-22 (todo/24: Kimi then flash-lite, never GLM-5). Thread one-liners and author answers try
# the free models first and reach the paid ones only when those are out.
STRONG_MODES = {"reply", "reply_back"}
CHEAP_MODES = {"thread", "thread_answer"}

# ---- LLM spend (llm.py). Bedrock is paid from the AWS free-plan credits: $99.67 on 2026-10-21, shared with EC2 ----
# $99.67 credits = this + EC2 to ~5 Nov (t3.micro ~$0.32/day, public IPv4 $0.12/day, 8 GB disk ~$0.03/day: ~$7.50;
# load 0.00, so no unlimited-CPU surcharge) + ~$7 tolerance (Bedrock calls made off the box with the same key aren't
# counted here; the bill lags by hours). With LLM_PRICES padded ~25%, the real spend should come in under this.
LLM_BUDGET_USD = 85.0               # all priced models together, 21 Oct to 2 Nov
# USD per million tokens (input, output). us-west-2 list prices padded ~25% (Kimi $0.60/$3.00, GLM-5 $1.00/$3.20 from
# third-party listings, 2026-10-21; eu-west-2 runs ~20% over us-west-2). Replace with the console's Sydney prices.
LLM_PRICES = {"moonshotai.kimi-k2.5": (0.75, 3.75), "zai.glm-5": (1.25, 4.00)}
# Daily shares follow the Red multiplier (x1 to 25 Oct, x2 26-31 Oct, x4 1-2 Nov; Sydney days): a draft is worth up to
# 4x more on the last days. A day's unspent share carries forward; the total never passes LLM_BUDGET_USD.
LLM_BUDGET_DAYS = [("2026-10-21", "2026-10-25", 1), ("2026-10-26", "2026-10-31", 2), ("2026-11-01", "2026-11-02", 4)]
# Priority lane: this share of each day's share stays for amplified posts. Other drafts use the paid models only
# while more than it is left, then the free ones.
LLM_AMP_RESERVE_SHARE = 0.25
AMP_AUTHOR_EXPLORE = 0.2            # share of amplified posts by a random ready voice, not the best-measured one
AMP_AUTHOR_PRIOR = (2, 40.0)        # (pseudo-posts, reward each) for a voice not yet measured: try it early
# delays after the post, lognormal (median min, sigma, clip lo, clip hi): front-loaded, heavy tail, never instant
LIKE_DELAY = (4, 0.8, 0.75, 60)
THREAD_DELAY = (6, 0.6, 2, 40)
REPOST_DELAY = (4, 0.7, 1.5, 20)
PUSHBACK_SHARE = 0.35               # share of amplified posts where one thread reply pushes back and the author answers
LIKES_PER_MIN = 20                  # our own cap; the server's is 30/min team-wide (we also read X-RateLimit-Remaining)
FILLER_RATIO = 1.2                  # likes on other people's No/neutral posts per own like: ≥50% of each liker's likes
SLEEP_H = 5                         # each booster sleeps 5 h a day, at its own random hour
LOCAL_TZ = "Australia/Sydney"
REPOST_MIN_GAP_S = 60               # a voice may repost a minute after its last write
MEASURE_AT_S = (3600, 6 * 3600)
FOLLOW_BACK_MAX = 3                 # per measurement, the author follows up to 3 citizens who liked the post

# ---- trending pulse (todo/15, swan_bot/pulse.py): what's working in Trending now, as data in the prompts ----
PULSE_ON = True                     # False: the prompts are exactly as before the pulse
PULSE_EVERY_S = 30 * 60             # one LLM call per pulse, on the chain without AMP_MODELS
PULSE_MAX_AGE_S = 2 * 3600          # an older pulse is not used
PULSE_MAX_CHARS = 600               # all its notes together
PULSE_HOOK_FRESH_S = 6 * 3600       # a hook from a headline this new may open an amplified post (the news shape)...
PULSE_NEWS_SHARE = 0.5              # ...about this share of the time

# ---- fact desk (todo/16, swan_bot/factdesk.py): new articles checked against content/facts.toml, hourly ----
# A few calls a day (one per batch of new articles), so the strongest models go first; the rest of the chain after.
# 3.8 and 3.6 Flash are 20 a day each on the bot's free key and shared with the amplified posts (AMP_MODELS).
FACTDESK_MODELS = ("gemini-3.8-flash", "gemini-3.6-flash", "openai/gpt-oss-120b", "gemini-3.5-flash-lite")
# Autopilot (todo/29, Marc 22 Oct: "I don't want to review anymore"): the desk applies its own proposals, with the
# checks a human decision runs, into data/facts_auto.toml (factdesk.auto_decide). False: everything waits for
# scripts/facts_review.py as before. Undo one: ssh swan-ec2 'cd ctn && .venv/bin/python scripts/facts_review.py --undo ID'
FACTDESK_AUTO = True
FACTDESK_AUTO_PER_DAY = None        # no cap (Marc, 22 Oct: "completely autonomous"); a number caps changes a Sydney day

# ---- swarm (src/swan_bot/swarm.py, docs/04-technical/swarm.md): like + repost other Vote No posts every 5 min ----
SWARM_ACCOUNTS_FILE = SECRETS / "swarm_accounts.json"   # its own file: the bot process never writes it
SWARM_STATE_FILE = DATA / "swarm_state.json"
SWARM_OFF_FILE = ROOT / "SWARM_OFF"  # touch it to pause the swarm (no registrations, likes or reposts)
SWARM_SIZE = 20                     # lifetime swarm accounts; registration also stops at MAX_ACTIVE (team total)
SWARM_OWNER = "minhnguyenhoang"     # accountable team member for every swarm account and action
SWARM_REGISTER_GAP_S = (4 * 60, 9 * 60)  # one registration per run at most, 4-9 min apart
SWARM_TAGS = {192: "keepkingstoniaopen", 113: "voteno", 193: "choicenotcoercion"}
SWARM_MAX_AGE_H = 24                # only posts from the last day
SWARM_LIKERS_PER_POST = (2, 5)      # swarm accounts that like each new qualifying post
SWARM_LIKES_PER_SCAN = 25           # likes per run (a run every 5 min, so <= 5/min of the team's 30/min)
SWARM_LIKE_RESERVE = 12             # stop liking when the team's like budget drops below this (amplifier's share)
SWARM_REPOSTS_PER_SCAN = 2          # reposts share the team's 3/min write route with the bot
SWARM_WRITE_RESERVE = 2             # repost only while >= this many writes are left in the team budget
SWARM_LIKE_GAP_S = (3, 9)           # pause between likes inside a run
SWARM_REPOST_GAP_S = 75             # never two swarm reposts within this many seconds


def swarm_active():
    """Active swarm accounts (read from their own file), so the bot counts them against MAX_ACTIVE."""
    import json
    try:
        recs = json.loads(SWARM_ACCOUNTS_FILE.read_text())
    except (FileNotFoundError, ValueError):
        return 0
    return sum(1 for r in recs if r.get("status", "active") == "active")


# ---- experiment arms (swan_bot/experiment.py). The overnight experiments stopped 2026-10-21 (too little data) ----
PIN = {"reply_mode": "reason_first"}   # pin a dimension to one arm, e.g. {"lever": "loss"}; wins over SWITCHBACK
# One switchback at a time: the dimension, its arms, the block length. The arm rotates per block (and shifts a day).
SWITCHBACK = []                     # set again in the todo/25 conversion block below
ARM_WEIGHTS = {}                    # {dim: {arm: weight}}: reweight arms (the bandit, from night 2). Empty = as drawn
FOLLOWUPS_LOG = LOGS / "swan_followups.jsonl"   # scripts/swan_followup.py: citizens' stance after we replied
OUTCOMES_LOG = LOGS / "swan_outcomes.jsonl"     # ...and per-post citizen engagement at OUTCOME_AT_S
FOLLOWUP_STATE = DATA / "swan_followup_state.json"
FOLLOWUP_AT_S = (2 * 3600, 12 * 3600)  # re-read a citizen we replied to this long after the reply
OUTCOME_AT_S = (3600, 6 * 3600)        # read each of our posts' likes, replies and views this long after
FOLLOWUP_MAX_READS = 600               # per run (every 30 min); the read budgets are 300/min per endpoint

# ---- todo/20 conversion (replies that change minds; todo/20-replies-that-convert.md) ----
# G9 (2026-10-22, "we cannot afford a rejection"): LLM calls per draft before it is given up, by mode: the first draft
# and then repairs with the exact problem. A model that failed twice is left out of the next call (Kimi -> flash-lite ->
# the next in the chain; todo/24). Code fixes (quality.fix: trim, drop a sentence) cost no call. Other modes: 2.
GATE_TRIES = {"reply": 4, "reply_back": 4, "second_voice": 3}
# G7 conversation turns: a citizen who answers us is looked for this often (was 5 min), and gets our reply-backs at
# most this many times in one session, never once their reply sits this deep in a thread (citizens stop there).
NOTIF_EVERY_S = 60
TURNS_PER_SESSION = 3
TURN_SESSION_S = 30 * 60
THREAD_MAX_DEPTH = 8
# Levers, 2026-10-22: fear_answer cut (0 citizen replies in 21 writes); in_group (18%) and permanence (16%) up. Others 1.
LEVER_WEIGHTS = {"fear_answer": 0.0, "in_group": 2.0, "permanence": 2.0}
# Frames, 2026-10-22: F2 (2.5% citizen reply rate, n=40) and F3 (5.5%, n=73) stay available at this share of their
# usual odds (persona posts, second voices, and the light read's frame list).
FRAME_SCALE = {"F2_no_end": 0.25, "F3_provax_antipass": 0.25}
# No vaccine advocacy until organiser Q3 says how a pro-vaccine move on "vaccination in general" scores (2026-10-22):
# it may score away (-80). Being vaccinated may be part of who a persona is; urging anyone to get the jab, or praising
# the vaccine, is rejected by the gate (content.ADVOCACY), and the get_jab theme ("Get the jab. Vote No.") is off.
NO_VACCINE_ADVOCACY = True
THEMES_OFF = {"get_jab"}
# The light read (todo/20 step 2): a reply to a citizen is drafted as JSON with their stance, their doubt and the
# frame that answers it (content.read_block / parse_read), or a skip; the stance picks the approach. False: plain
# replies, the frame from the keyword match only.
LIGHT_READ = True
# Reply style arm, taken in turn per reply (experiment.alternate): "mirror_concede" (mirror one detail, concede, one
# anchor, state No; 150-280 characters, no question) against "current". The firm-Yes arm (todo/21) is always
# mirror_concede. To keep a winner, list only it here.
REPLY_STYLES = ["mirror_concede", "current"]
# Second voice inside the citizen's session (step 7): sessions last 1-5 min, and the contribution pool counts only
# posts read in the session where the change happens. Delays taken in turn, logged as sv_delay (was always 10-30 min).
SECOND_VOICE_ARMS = {"fast": (60, 4 * 60), "slow": (10 * 60, 30 * 60)}
# One own like on our reply to a citizen (step 8, never tried before): on alternate replies a booster likes it
# 1-4 min after it goes out (logged as own_like on the reply, and as a like with purpose reply_like). Drop it if
# citizen likes and replies don't rise.
OWN_LIKE_ARM = True
OWN_LIKE_DELAY_S = (60, 4 * 60)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


# ---- todo/22 reader/writer split (bot.py; docs/04-technical/swan-bot-runbook.md) ----
SPLIT_LOOP = True                   # reader, drafter, writer threads. False + a restart: the serial loop (rollback)
DRAFT_AHEAD = 2                     # drafts waiting for the writer, at most (more would go stale)
READER_SILENT_S = 20 * 60           # the watchdog stops the bot when the reader goes this long without a round
DRAFTER_SILENT_S = 30 * 60          # ...or the drafter (one draft may try several models with 90 s timeouts)

# ---- todo/24 throughput (todo/24-throughput-to-three.md; docs/04-technical/swan-bot-runbook.md) ----
# Replies to citizens (STRONG_MODES) are drafted on these models, tried in THIS order (not the chain's), then the rest
# of deploy/llm_chain.txt without REPLY_NEVER. 2026-10-22 overnight first-call pass: Kimi 89% (n=857), flash-lite 86%
# (n=195), GLM-5 0 of 69 (not_specific 36, near_duplicate 28): GLM-5 drafts amplified posts only (AMP_MODELS).
REPLY_MODELS = ("moonshotai.kimi-k2.5", "gemini-3.5-flash-lite")
REPLY_NEVER = {"zai.glm-5"}
# Pacing. 22 Oct overnight: 2.2-2.3 writes/min (per_min 2.5 clamped, jitter 0.7-1.5) and the queue grew at Sydney peak.
# The writer now aims at the team limit (deploy/run.sh --per-min 2.9): the next write waits for the larger of the pace
# gap and the headers' gap (bot.write_gap): X-RateLimit-Remaining must be back to WRITE_MARGIN + 1, so each of our
# writes leaves WRITE_MARGIN for the swarm (swan-swarm reposts while >= SWARM_WRITE_RESERVE are left). A 429 waits its
# Retry-After. MAX_PER_MIN is the rules' 3/min (posts + replies + reposts, team-wide); the headers bind first.
MAX_PER_MIN = 3.0
WRITE_MARGIN = 1
WRITE_JITTER = (0.85, 1.15)         # pace gap = 60 / per_min times this (mean 1.0)
# Lighter refresh (approved 22 Oct): the replies under the papers' article posts are read every 30 min, not every
# refresh (2 min): 0 citizen replies under the post-launch paper posts. The papers' own posts (headlines for the pulse
# and persona posts) are still read every refresh.
NEWS_THREADS_S = 30 * 60

# ---- todo/27 fingerprint (todo/27-stop-the-fingerprint.md) ----
# 2026-10-22 05:00 UTC: the moderator hid 2, 5, 6 of our posts an hour (other teams' Blue reports on one reply template,
# "...no end date... I'm voting No."). deploy/run.sh --per-min 2.9 -> 2.4 until hides stay under 1/h for 6 h.

# ---- todo/31 stealth (todo/31-stealth.md; swan_bot/stealth.py), 2026-10-22 ----
# Audit 22 Oct ~10:15 UTC: each voice wrote 100-200 times in 24 h across 18-24 hours of the day, and 294 of 730 citizens
# got two of our voices within 60 min: what other teams' Blue reporters see (33 posts hidden on 16 voices, 13 of 61
# accounts banned). Each voice now keeps a human day. Every rule has its own switch (False + a restart: as before);
# they hold for the live bot only. Fewer, human-looking writes is the trade (persuasion pays, volume barely does).
# Kingstonia has no stated time zone (docs/01-competition/setting.md: "a few hours' flight from Australia and NZ"),
# so its clock is the competition's, Sydney (LOCAL_TZ): when citizens are online and when the day rolls over.
VOICE_DAY_CAP = True
VOICE_WRITES_PER_DAY = 40           # writes per voice in any 24 h: posts, replies, reposts, thread replies, all of them
VOICE_CITIZEN_RESERVE = 8           # ...of which the last 8 are only for writes to citizens (reply, reply-back)
VOICE_HOUR_CAP = True
VOICE_WRITES_PER_H = 6              # and in any 60 min (todo/27's unfinished per-hour cap)
# A fixed sleep window per voice (Sydney hours), from its persona key: a start in its kind's range, a length in
# VOICE_SLEEP_H. Stable across restarts and machines; the voices go to sleep at different times. Kinds from the cards:
# night-shift nurse Ana sleeps in the day, the early-ferry and before-dawn people go to bed early. 25.5 = 01:30.
VOICE_SLEEP = True
VOICE_SLEEP_H = (7.0, 8.0)
VOICE_SLEEP_STARTS = {"night": (22.0, 25.5), "early": (20.0, 21.5), "day": (8.0, 10.5)}
VOICE_SLEEP_KIND = {"ana": "day", "lani": "early", "ben": "early", "tomasi": "early", "esther": "early"}
# No fixed cadence: after each write a voice's next ordinary write waits a lognormal gap (median s, sigma, min s,
# max s; the min is the old fixed ACCOUNT_MIN_GAP_S), and VOICE_BREAK_P of the time a 1-2 h break instead.
# Reply-backs, reposts and own-thread answers keep their short gaps (a person answers someone who talks to them).
VOICE_JITTER = True
VOICE_GAP = (12 * 60, 0.6, 4 * 60, 45 * 60)
VOICE_BREAK_P = 0.08
VOICE_BREAK_S = (60 * 60, 120 * 60)
VOICE_STAGGER = True                # after a (re)start each voice waits its own random 0-20 min before its first write
VOICE_STAGGER_S = 20 * 60
# One voice per citizen per day: no other voice of ours replies to a citizen, or under their post, for ONE_VOICE_S
# unless the citizen addressed that voice (a reply-back stays with the voice they answered or mentioned). A citizen
# whose voice is asleep or capped waits for it. Second voices can't run under it (SECOND_VOICE is off anyway).
ONE_VOICE_PER_CITIZEN = True
ONE_VOICE_S = 24 * 3600
STEALTH_SEED_BYTES = 64 * 2 ** 20   # on start the last day of writes is read back from the tail of the actions log
STEALTH_LOG_S = 120                 # a "voice_asleep" / "voice_capped" skip is logged at most this often per reason

# ---- todo/25 conversion (todo/25-conversion-what-moves-them.md) ----
# Toward + away went 6 -> 0 between the nights of 20 and 21 Oct, when one deploy changed the reply model, stopped
# broadcast and started answering No-leaners. Each arm runs a whole 2 h block (experiment.block), logged as arm_conv
# on every citizen-facing write, so the portal's hourly lines can be compared block by block:
#   base         today's behaviour;
#   old_models   replies and reply-backs drafted on the 20 Oct free chain (CONV_OLD_MODELS) while any of it answers;
#   no_leaners   a reply whose target reads lean/firm No (regex class, or the light read) is skipped, not answered;
#   broadcast    a plain persona post (no amplification) ahead of citizen replies every CONV_POST_GAP_S (20 Oct ran
#                2-3 posts/h). Marc, 2026-10-22: off the same day if "away" beats "toward" in broadcast blocks.
# To stop the experiment: SWITCHBACK = []. To keep a winner, list only it in CONV_ARMS.
# 2026-10-22 10:30 UTC: old_models and no_leaners killed by the rule "away above base" (block table at 10:14 UTC,
# portal lines 1 h after: base 2 blocks 0 toward / 0 away; old_models 2 blocks 1 / 5; no_leaners 1 block 0 / 2;
# broadcast 1 block 0 / 0, kept). old_models was the only arm touching the referendum view, but net away.
CONV_ARMS = ["base", "broadcast"]
CONV_BLOCK_S = 2 * 3600
CONV_POST_GAP_S = 20 * 60
CONV_OLD_MODELS = ("gemini-3.5-flash-lite", "openai/gpt-oss-120b", "qwen/qwen3.8-27b")
CONV_SKIP_STANCES = {"lean_no", "firm_no"}
CONV_MODES = {"reply", "reply_back", "second_voice", "post"}   # arm_conv is logged on these
SWITCHBACK = [("arm_conv", CONV_ARMS, CONV_BLOCK_S)]
# The NPC lab (src/swan_lab, docs/06-strategy/npc-lab.md): a stand-in citizen scores reply strategies offline.
# The stand-in and its classifier run on LAB_MODEL only: "competitor" is the organisers' qwen2.5-3b (CompetitorLLM).
# External models may draft the replies under test (content), never play or judge the citizen (CLAUDE.md rule 2).
# "local": the same model family (qwen2.5:3b-instruct-q8_0 on Ollama, Marc's laptop) through an SSH tunnel to the
# box, allowed since 2026-10-22 (CLAUDE.md rule 2: offline analysis and testing). No rate limit, 1 at a time, and
# "competitor" takes over while the tunnel is down. Tunnel confirmed 2026-10-22 ~01:30 UTC: q4_K_M (~8 tokens/s on the
# laptop, ~80-100 trials/h); q8_0 is pulled too, for a fidelity spot check (run --local-model).
LAB_MODEL = "remote"                # 2026-10-22 ~05:30 UTC: Modal verified; the laptop tunnel died at ~04:50 UTC
LAB_LOCAL_URL = "http://127.0.0.1:11434/v1"
LAB_LOCAL_MODEL = "qwen2.5:3b-instruct-q4_K_M"
# "remote": full-precision Qwen/Qwen2.5-3B-Instruct on Modal (vLLM on an L4, Marc's account, scales to zero),
# OpenAI-compatible behind a bearer key. LAB_REMOTE_URL (with /v1) and LAB_REMOTE_KEY live in .env, never here.
LAB_REMOTE_MODEL = "qwen2.5-3b-instruct"
LAB_CONCURRENCY = {"remote": 16, "local": 1, "competitor": 1}   # trials at once, by stand-in kind (Modal: 32 max)
LAB_LLM_PER_MIN = 3                 # CompetitorLLM's team limit: 3/min, 1 at a time (the headers can only lower it)
LAB_READS_PER_MIN = 30              # the persona builder's read pace (per-endpoint budgets, never the feed budget)
LAB_SEEDS = 6                       # trials per persona x strategy (6 since remote: the 0.7-temperature noise needs pairs)
# Drafting models a strategy file may name (drafter = "..."), added to the lab's chain on Bedrock's OpenAI-compatible
# endpoint: the drafting-model factor of round 2. Kimi K3 isn't served there (404, 2026-10-22).
LAB_DRAFTERS = ("deepseek.v3.2", "mistral.mistral-large-3-675b-instruct")
LAB_DIR = DATA / "lab"
LAB_PERSONAS = ROOT / "content" / "lab" / "personas"
LAB_STRATEGIES = ROOT / "content" / "lab" / "strategies"

# ---- Blue track (todo/07, src/swan_blue): a separate process reports from one booster the bot no longer uses ----
BLUE_OFF_FILE = ROOT / "BLUE_OFF"       # touch it to stop filing reports (the scan and rulings carry on)


def blue_reporter(records):
    """The account swan_blue reports from: the lowest-id active booster. Both processes call this, so they agree;
    the bot leaves it out of its boosters and its drip registration tops the likers back up."""
    boosters = [r for r in records if r.get("role") == "booster" and r.get("status", "active") == "active"
                and r.get("account_id")]
    return min(boosters, key=lambda r: r["account_id"]) if boosters else None


def load_env(path=ROOT / ".env"):
    """Minimal .env loader (strips quotes). .env wins over the shell, so a stale exported key can't shadow it."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip().strip('"').strip("'")


def assigned_side():
    """This bot is written for Vote No only. Refuse to run for anything else."""
    side = os.environ.get("CTN_SIDE", "").lower().replace("_", " ")
    if "no" in side.split():
        return "no"
    raise SystemExit(f"CTN_SIDE is {side!r}; swan_bot only campaigns for Vote No. Fix .env first.")


def team_code():
    code = os.environ.get("CTN_TEAM_CODE", "")
    if len(code) != 16:
        raise SystemExit("CTN_TEAM_CODE missing or not 16 characters (check .env).")
    return code


def operator():
    """Team member accountable for accounts created by this run (attribution rule)."""
    return os.environ.get("CTN_OPERATOR", "marc")
