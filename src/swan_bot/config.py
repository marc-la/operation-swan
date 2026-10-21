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

REFRESH_S = 4 * 60                  # collect targets every 4 min (cheap reads)
TARGET_MAX_AGE_H = 36               # citizens' notifications are near-empty, so a day-old comment still lands
CONTACT_COOLDOWN_S = 72 * 3600      # first contact with a given citizen at most every 3 days
SECOND_VOICE_S = (10 * 60, 30 * 60) # a second persona follows up on the same doubt 10-30 min later
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
AMP_POST_GAP_S = (25 * 60, 35 * 60) # one amplified original every 25-35 min
# per level: own likes, own-thread replies, reposts (ranges, inclusive). Likes are capped by the accounts awake.
AMP_LEVELS = {"heavy": dict(likes=(36, 46), replies=(3, 5), reposts=(5, 6)),
              "light": dict(likes=(10, 16), replies=(1, 2), reposts=(0, 1)),
              "none": dict(likes=(0, 0), replies=(0, 0), reposts=(0, 0))}
AMP_PRIOR = {"heavy": 0.8, "light": 0.1, "none": 0.1}   # until the bandit has 4 measured posts per level
AMP_EXPLORE = 0.15
# delays after the post, lognormal (median min, sigma, clip lo, clip hi): front-loaded, heavy tail, never instant
LIKE_DELAY = (4, 0.8, 0.75, 60)
THREAD_DELAY = (5, 0.6, 2, 30)
REPOST_DELAY = (4, 0.7, 1.5, 20)
PUSHBACK_SHARE = 0.35               # share of amplified posts where one thread reply pushes back and the author answers
LIKES_PER_MIN = 20                  # our own cap; the server's is 30/min team-wide (we also read X-RateLimit-Remaining)
FILLER_RATIO = 1.2                  # likes on other people's No/neutral posts per own like: ≥50% of each liker's likes
SLEEP_H = 5                         # each booster sleeps 5 h a day, at its own random hour
LOCAL_TZ = "Australia/Sydney"
REPOST_MIN_GAP_S = 60               # a voice may repost a minute after its last write
MEASURE_AT_S = (3600, 6 * 3600)
FOLLOW_BACK_MAX = 3                 # per measurement, the author follows up to 3 citizens who liked the post

# ---- experiments (todo/13-overnight-experiments.md; swan_bot/experiment.py) ----
PIN = {}                            # pin a dimension to one arm, e.g. {"lever": "loss"}; wins over SWITCHBACK
# One switchback at a time: the dimension, its arms, the block length. The arm rotates per block (and shifts a day).
SWITCHBACK = [("reply_mode", ["reason_first", "conditions_first"], 2 * 3600)]
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
