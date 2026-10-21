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

MAX_ACCOUNTS = 15                   # lifetime cap on voices (persona accounts); boosters: MAX_BOOSTERS
REGISTER_GAP_S = (20 * 60, 40 * 60) # drip registration: one new account every 20-40 min, never a burst
ACCOUNT_MIN_GAP_S = 4 * 60          # one voice writes at most every 4 minutes (todo/03)
# Moderator-hidden posts per voice (scripts/swan_watch.py). 1 hidden + ≥100 actions = the next account report
# suspends it; 3 hidden = suspended (scoring guide §3). Lost @lani_wharfcafe23 this way on 2026-10-20.
HIDDEN_OFF_AMP = 1                  # this many: off amplified posts and threads (less on show, fewer reports)
HIDDEN_STOP = 2                     # this many: stops writing (one more hidden post would suspend it)

REFRESH_S = 4 * 60                  # collect targets every 4 min (cheap reads)
TARGET_MAX_AGE_H = 36               # citizens' notifications are near-empty, so a day-old comment still lands
# Citizens replying under Trending posts: a reply there is read by the thread's viewers (300-480 views per Trending
# post), not just by the citizen. 2026-10-21: read 12 threads (was 6) and rank these targets above news replies.
TRENDING_THREADS = 12
TRENDING_THREAD_BONUS = 1.5
CONTACT_COOLDOWN_S = 72 * 3600      # first contact with a given citizen at most every 3 days
SECOND_VOICE_S = (10 * 60, 30 * 60) # a second persona follows up on the same doubt 10-30 min later
SECOND_VOICE = False                # 2026-10-21: off. ~2 views each; the write slots go to amplified threads
REPLY_BACK = False                  # 2026-10-21: off, same reason (~2 views, 0.07 citizen replies each)
REPLY_BACK_AMP = True               # ...except to citizens replying in our amplified threads, where people are reading
JOURNALIST_MAX_AGE_H = 12
JOURNALIST_GAP_S = 45 * 60          # at most one journalist reply per 45 min
JOURNALIST_SAME_GAP_S = 6 * 3600    # and the same journalist at most every 6 h
POST_EVERY_N = 4                    # persona posts: at most 1 in every 4 writes (replies come first)
IDLE_POST_GAP_S = 30 * 60           # ...or one every 30 min when there is nothing better to write

# ---- amplification (docs/06-strategy/amplification.md). On only with --amplify; touch AMPLIFY_OFF to pause it live ----
AMP_OFF_FILE = ROOT / "AMPLIFY_OFF"
MAX_BOOSTERS = 36                   # like-only accounts (never post, so they can't be suspended under the published rules)
MAX_ACTIVE = 48                     # the platform allows 50 alive at once; 2 spare for a human
BOOSTER_REGISTER_GAP_S = (4 * 60, 9 * 60)
# 2026-10-20 late: 11 measured posts peaked at hot ~23 vs a top-35 cutoff ~24 (0 entered Trending). Fewer posts,
# each pushed over the line: a repost weighs ~8 likes, and the engagement has to land in the first ~15 min.
# 2026-10-21: 16 heavy posts at 36-46 likes, 3-5 replies, 4-8 reposts: 0 in Trending, 0 citizen views. The posts that
# trend carry 40-90 team likes AND 20-66 team replies. So: one post an hour, every one heavy, ~15-20 thread replies
# (each voice may reply twice) on top of the reposts (the fit's heaviest signal; the write budget was 83% idle).
AMP_POST_GAP_S = (50 * 60, 70 * 60) # one amplified original an hour
# per level: own likes, own-thread replies, reposts (ranges, inclusive). Likes are capped by the accounts awake.
AMP_LEVELS = {"heavy": dict(likes=(36, 46), replies=(15, 20), reposts=(5, 6)),
              "light": dict(likes=(10, 16), replies=(1, 2), reposts=(0, 1)),
              "none": dict(likes=(0, 0), replies=(0, 0), reposts=(0, 0))}
AMP_PRIOR = {"heavy": 1.0, "light": 0.0, "none": 0.0}   # 2026-10-21: always heavy (was 0.8 / 0.1 / 0.1)
AMP_EXPLORE = 0.0
THREAD_PER_VOICE = 2                # thread replies one voice may write under one amplified post
AMP_PRIORITY_S = 20 * 60            # priority lane: other writes wait this long after an amplified post (thread first)
# The amplified post is our best content: drafted on the strongest models first, the usual chain if they are out.
# The bot's key is on the free project: 3.8 and 3.6 Flash have 20 requests a day each (deploy/llm_chain.txt).
# 2026-10-21: Kimi K2.5 and GLM-5 on Bedrock lead (best drafts in llm_compare, paid from the AWS credits); then the
# free Gemini Flash models and qwen-plus-character (Alibaba free quota, 1M tokens to 2027-01-20).
# Order comes from deploy/llm_chain.txt, not from this tuple.
AMP_MODELS = ("moonshotai.kimi-k2.5", "zai.glm-5", "gemini-3.8-flash", "gemini-3.6-flash", "qwen-plus-character")
# Where persuasion happens, drafts get AMP_MODELS too: replies to citizens (a change of mind is 160 points). Thread
# one-liners and author answers try the free models first and reach the paid ones only when those are out.
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

# ---- experiment arms (swan_bot/experiment.py). The overnight experiments stopped 2026-10-21 (too little data) ----
PIN = {"reply_mode": "reason_first"}   # pin a dimension to one arm, e.g. {"lever": "loss"}; wins over SWITCHBACK
# One switchback at a time: the dimension, its arms, the block length. The arm rotates per block (and shifts a day).
SWITCHBACK = []
ARM_WEIGHTS = {}                    # {dim: {arm: weight}}: reweight arms (the bandit, from night 2). Empty = as drawn
FOLLOWUPS_LOG = LOGS / "swan_followups.jsonl"   # scripts/swan_followup.py: citizens' stance after we replied
OUTCOMES_LOG = LOGS / "swan_outcomes.jsonl"     # ...and per-post citizen engagement at OUTCOME_AT_S
FOLLOWUP_STATE = DATA / "swan_followup_state.json"
FOLLOWUP_AT_S = (2 * 3600, 12 * 3600)  # re-read a citizen we replied to this long after the reply
OUTCOME_AT_S = (3600, 6 * 3600)        # read each of our posts' likes, replies and views this long after
FOLLOWUP_MAX_READS = 600               # per run (every 30 min); the read budgets are 300/min per endpoint

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


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
