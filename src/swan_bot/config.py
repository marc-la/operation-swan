"""Settings for swan_bot. Secrets come only from .env / the environment and are never printed."""
import os
import pathlib
import re

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


# ---- todo/48: citizens above id 2343 (swan_bot/npc.py scores them, scripts/npc_scan.py writes NPC_SCORES_FILE) ----
# is_citizen stays the id rule for every metric. These read a cached score in [0, 1] (no network call) for accounts above
# CITIZEN_MAX_ID; with no file, or a file older than NPC_SCORES_MAX_AGE_S, nothing changes. Both switches ship OFF.
NPC_SCORES_FILE = DATA / "npc_scores.json"
NPC_SCORES_MAX_AGE_S = 4 * 86400    # targeting ignores an older file (a team may change what an account does); Blue never does
# Cuts, from the 27 Oct fit (todo/48 read-out, held-out labels): writing favours precision (a team bot read as a citizen wastes
# a write), Blue favours recall (any plausible citizen is not reported: a genuine ruling locks reporting for 6 h).
NPC_TARGET_MIN = 0.9
NPC_BLUE_MIN = 0.3
# The extra arm: with it on, Targeter._consider admits a likely citizen (score >= NPC_TARGET_MIN) in the "extra" blocks of
# arm_npc (SWITCHBACK below; "base" blocks are as now), logged with npc_score; reply-backs answer them in any block.
# 29 Oct (Marc): ON for good, in every block (NPC_ARMS below) and the x4 days (FREEZE_PIN). The 28 Oct "0 citizen replies"
# was the counter: citizen_replies counted ids up to 2343 only. The targets answered 13.8% of the time (247 matured
# writes) against 6.6% for ordinary ones, and the portal books their follows as citizen follows (25 of them 23-29 Oct;
# rival bots' 508 not). docs/06-strategy/situation-2026-10-29.md §4. Off: SWAN_NPC_EXTRA_ARM=0.
NPC_EXTRA_ARM = True
# Blue's final check: with it on, evidence.py / fleets.py never count an account scoring >= NPC_BLUE_MIN as a competitor,
# and a report whose author or target scores that high is skipped and logged ("skip", reason "npc", with the score).
# 29 Oct (Marc): ON again with the extra arm (its premise holds: the portal scores them). Both post reports we filed on an
# account scoring 0.9+ were ruled genuine, and a genuine ruling locks all our reporting for 6 h. Off: SWAN_BLUE_NPC_GUARD=0.
BLUE_NPC_GUARD = True
# todo/63 (31 Oct, Marc): the bot scores a new author above CITIZEN_MAX_ID on first sight (Targeter._score_new: get_account
# and one page of posts, as npc_scan scores them), so a citizen the scan has not reached is answered while the post is fresh.
# The scan only read the authors of the 15-min Latest snapshot once an hour: 9 unscored authors posting in one window all
# scored 0.94-1.0 when read, and 1,079 of the 2,594 likely citizens (42%) had ever had a write from us (seeded: 96%). These
# scores live in this process only (npc_live_put); the file stays the source for Blue and the follow-ups (the scan now runs
# every 10 min). Needs NPC_EXTRA_ARM. Off: SWAN_NPC_LIVE_SCORE=0 (+ restart).
NPC_LIVE_SCORE = True
NPC_LIVE_MAX_ID = 9874              # the last account made before 21 Oct 12:00 UTC: ids rise with created_at (census 30 Oct, 0
                                    # inversions in 12,639) and all 2,604 accounts scoring 0.9+ were made by 10:24 (id 9803)
NPC_LIVE_PER_REFRESH = 4            # new authors scored per refresh at most (2 reads each; a refresh every REFRESH_S)
NPC_LIVE_RETRY_S = 3 * 3600         # an author whose page had too few posts to score is read again after this
NPC_LIVE_WAIT_S = 30 * 60           # a post waiting for its author's score is dropped this old (reads were short)
_NPC = {"mtime": None, "built": 0.0, "scores": {}, "known": {}}
_NPC_LIVE = {}                      # todo/63: account id -> {s, n, at (epoch s), err, why}: scored by this process


def npc_scores():
    """{account id: score} from NPC_SCORES_FILE (re-read when its mtime changes) and when it was built (epoch s)."""
    import json
    try:
        m = NPC_SCORES_FILE.stat().st_mtime
    except OSError:
        _NPC.update(mtime=None, built=0.0, scores={}, known={})
        return _NPC["scores"], 0.0
    if m != _NPC["mtime"]:
        try:
            d = json.loads(NPC_SCORES_FILE.read_text())
            raw = d.get("scores") or {}
            scores = {int(k): float(v["s"]) for k, v in raw.items() if v.get("s") is not None}
            known = {int(k): (v.get("s"), _iso_ts(v.get("at")), v.get("err")) for k, v in raw.items()}
            built = float(d.get("built_ts") or m)
        except (OSError, ValueError, TypeError, AttributeError, KeyError):
            scores, known, built = {}, {}, 0.0
        _NPC.update(mtime=m, built=built, scores=scores, known=known)
    return _NPC["scores"], _NPC["built"]


def _iso_ts(s):
    """Epoch seconds of an ISO time (the scan's 'at'), 0.0 when missing or unreadable."""
    import datetime as dt
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except (AttributeError, TypeError, ValueError):
        return 0.0


def npc_score(account_id, max_age_s=None):
    """The cached citizen score of an account above CITIZEN_MAX_ID, or None (not scored, too few posts, a stale file).
    The file first; then todo/63's first-sight score from this process, if it is no older than max_age_s."""
    i = account_id or 0
    if i <= CITIZEN_MAX_ID:
        return None
    import time
    scores, built = npc_scores()
    t = time.time()
    if i in scores and (max_age_s is None or t - built <= max_age_s):
        return scores[i]
    live = _NPC_LIVE.get(i)
    if live and live.get("s") is not None and (max_age_s is None or t - live["at"] <= max_age_s):
        return live["s"]
    return None


def npc_live_put(account_id, rec, t=None):
    """todo/63: keep a first-sight score ({s, n, err, why}) for this process."""
    import time
    _NPC_LIVE[int(account_id)] = dict(rec, at=time.time() if t is None else t)


def npc_unscored(account_id, t=None):
    """todo/63: True when neither the file nor this process has a score for an account above CITIZEN_MAX_ID, or the
    last read of it found too few posts (no error, no score) more than NPC_LIVE_RETRY_S ago. A read that failed (private:
    403) or gave a score is never repeated here; the scan re-reads every account it sees after a day."""
    import time
    i = account_id or 0
    if i <= CITIZEN_MAX_ID:
        return False
    t = time.time() if t is None else t
    npc_scores()
    last = _NPC_LIVE.get(i)
    last = (last["s"], last["at"], last.get("err")) if last else _NPC["known"].get(i)
    if last is None:
        return True
    s, at, err = last
    return s is None and not err and t - at >= NPC_LIVE_RETRY_S


def likely_citizen(account_id):
    """is_citizen, or an account above CITIZEN_MAX_ID whose fresh cached score is >= NPC_TARGET_MIN (todo/48)."""
    if is_citizen(account_id):
        return True
    s = npc_score(account_id, NPC_SCORES_MAX_AGE_S)
    return s is not None and s >= NPC_TARGET_MIN


def npc_target(account_id):
    """With NPC_EXTRA_ARM: the score of a likely citizen the bot may write to beyond is_citizen, else None."""
    if not NPC_EXTRA_ARM or is_citizen(account_id) or not likely_citizen(account_id):
        return None
    return npc_score(account_id, NPC_SCORES_MAX_AGE_S)


def writes_to_citizen(account_id):
    """Who the bot treats as a citizen when it writes (reply-backs, phrase budgets): is_citizen, plus todo/48's likely
    citizens while NPC_EXTRA_ARM is on. Metrics keep is_citizen."""
    return is_citizen(account_id) or npc_target(account_id) is not None


def blue_citizen(account_id):
    """With BLUE_NPC_GUARD: the score of an account above CITIZEN_MAX_ID scoring >= NPC_BLUE_MIN (any file age), else None."""
    if not BLUE_NPC_GUARD:
        return None
    s = npc_score(account_id)
    return s if s is not None and s >= NPC_BLUE_MIN else None


MAX_ACCOUNTS = 21                   # lifetime cap on voices: 12 used + 5 promoted 21 Oct + 4 replacements; boosters: MAX_BOOSTERS
REGISTER_GAP_S = (20 * 60, 40 * 60) # drip registration: one new account every 20-40 min, never a burst
ACCOUNT_MIN_GAP_S = 4 * 60          # one voice writes at most every 4 minutes (todo/03); todo/31 jitters it (VOICE_GAP)
# Moderator-hidden posts per voice (scripts/swan_watch.py). 1 hidden + ≥100 actions = the next account report
# suspends it; 3 hidden = suspended (scoring guide §3). Lost @lani_wharfcafe23 this way on 2026-10-20.
HIDDEN_OFF_AMP = 1                  # this many: off amplified posts and threads (less on show, fewer reports)
HIDDEN_STOP = 99                    # OFF (2026-10-23, Marc: use every voice until the platform suspends it; todo/38). Was 2: stops writing
                                    # at this many hidden posts. Parking did not protect an account (one upheld account report suspends it
                                    # with 1+ hidden and 100+ actions) and cost writers: 7 of 16 were parked and the pace fell to 2.3/min.

# 2026-10-21 late: every 2 min (was 4). Citizens are online a few minutes per session, and the replies they answer
# in-session landed in the first ~5 min (ctn-68's reach study, 2 posts: 5 of 9 and 4 of 8 team replies answered).
# 31 Oct (todo/58, Marc): 15 -> 5. A first reply's proxy falls ~0.03 a second in its first minute, and a 15 s read left a
# post 7.5 s unseen on average. One 100-post Latest page a refresh (~60 posts a minute); the papers' and journalists' posts
# stay every ACCOUNT_READS_S and Trending every TRENDING_EVERY-th refresh (~45 s), so only Latest reads go up (4 -> 12 a min).
REFRESH_S = 5    # 26 Oct: was 30 (25 Oct, todo/46: was 2 * 60), set when feeds allowed 10 reads a minute; they have allowed 300 since 22 Oct
ACCOUNT_READS_S = 15                # the papers' and journalists' account_posts (6 reads), as often as before todo/58
FRESH_MIN = 10                      # a citizen post this new is answered first (they may still be online)...
# 2026-10-23: 4.0 -> 12.0. At 4 a fresh post with an ordinary read lost to older posts with a strong one, and with ~2,000
# queued the median wait for a reply was ~3 h (Marc: aim for under 5 min). 12 outweighs the usual spread of scores.
FRESH_BONUS = 12.0                  # ...by this much on top of its score (scores run ~1.5-10)
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
SECOND_VOICE = True
REPLY_BACK = True
REPLY_BACK_AMP = True               # with REPLY_BACK off: still answer citizens replying in our amplified threads
JOURNALIST_MAX_AGE_H = 12
JOURNALIST_GAP_S = 45 * 60          # at most one journalist reply per 45 min
JOURNALIST_SAME_GAP_S = 6 * 3600    # and the same journalist at most every 6 h
POST_EVERY_N = 8                    # persona posts: at most 1 in every 8 writes (replies come first). todo/40, 24 Oct: was 4 (see below)
IDLE_POST_GAP_S = 30 * 60           # ...or one every 30 min when there is nothing better to write

# ---- todo/40 hide-rate changes (2026-10-24, from docs/06-strategy/hide-risk-analysis-2026-10-23.md) ----
# Each has a name here and a SWAN_<NAME> override in .env (STEALTH_ENV, read at the next restart): no deploy to roll one back.
# A converted or newly activated voice's first top-level posts were hidden 5 of 15 times (33%) against 1 of 122 for original
# voices (its replies were normal): for this many hours of voice life (stealth.voice_age_h) it makes no persona post, no
# amplified post and no thread reply, replies only. 0 = off.
NEW_VOICE_NO_POST_H = 24
# The share of our last quality.PHRASE_WINDOW citizen-facing texts (replies, reply-backs, second voices) that may say "I'm voting No".
# Was 0.15; "I'm voting No" in a reply is a hide tell (adjusted OR 2.5). 0 rejects it (quality.drop_vote cuts it, no LLM call).
REPLY_VOTE_SHARE = 0.0
# Standalone persona posts were hidden 4.1% of the time against 1.3% for the rest (adjusted OR ~10, 147 posts): POST_EVERY_N 4 -> 8
# halves them, and a post no longer carries a hashtag together with a statement of the vote (the hashtag posts: 5 of 71 hidden).
# A post must still say it is voting No (quality's no_vote_statement), so it is the hashtag that goes: content.post_prompt asks for
# none and a draft that adds one has it cut (quality.fix, no LLM call). False = the old posts, hashtag and "I'm voting No" together.
POST_NO_TAG_WITH_VOTE = True
# The bot learned a voice was suspended from a 403 on its next action, 40 min to 12 h after the portal said so (22-23 Oct), and held
# its slot (and a wasted write) meanwhile. The dashboard poller (swan-portal.timer, 15 min) already writes the portal's suspension
# messages to data/portal.json (account_log.suspended); the writer reads that local file (no network call) every PORTAL_SYNC_S and
# marks a voice or booster suspended when the file names its username AND account id. A file whose own `ts` is older than
# PORTAL_MAX_AGE_S (the poller died, or its cookie expired), missing or malformed is ignored.
PORTAL_SYNC = True
PORTAL_SYNC_S = 120
PORTAL_MAX_AGE_S = 3600
PORTAL_FILE = DATA / "portal.json"
# scripts/swan_watch.py looked at active voices only, so a voice suspended on its third hide (or reported) stopped being watched
# while its last posts still awaited rulings (about 3 h after the write): hides were undercounted. It now keeps checking a voice that
# is no longer active for this long after its last logged write, and logs those hides flagged after_suspension (no alert). 0 = off.
WATCH_TAIL_S = 4 * 3600

# ---- todo/21 targeting: reach every citizen (todo/21-reach-every-citizen.md) ----
# G1 (2026-10-22): feed_latest and feed_trending share 10 reads a minute, and the bot found <= 3 left when it paged
# Latest. The bot is the one Latest reader (data/latest_snapshot.json for swan-blue, feeds.py), Trending every 3rd
# refresh (6 min). Every feed read is logged to logs/feed_reads.jsonl.
TRENDING_EVERY = 9                  # 31 Oct (todo/58): was 3 at a 15 s refresh; 9 at 5 s keeps Trending (and its 12 threads) at ~45 s
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
# 2026-10-22 read-out (todo/23 rules): killed. 275 writes, reply rate 11% but 0.02 citizen likes/write, and 3 of
# our hidden posts came from it (the kill rule: an arm that caused a hidden post).
SWEEP_ARM = False
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
# 2026-10-23: OFF (Marc): enough primary citizens in the queue. Its own replies were not what got hidden (0 of 22);
# the 3 hides in off-topic threads were vote pitches in reply-backs and second voices. Set True to bring it back.
OFF_TOPIC_ARM = False
OFF_TOPIC_PER_H = 6                 # 2026-10-22 read-out: raised from 3 (20% citizen replies vs 10% baseline, 20 writes)
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
# free Gemini Flash models. (qwen-plus-character, the Alibaba free quota, was last here until 23 Oct: quota spent, out.)
# Order comes from deploy/llm_chain.txt, not from this tuple.
# 2026-10-23: Sonnet 4.6 is not here or in the chain (Marc: not even as a last resort; npc-lab 23 Oct: no drafting model
# moves the raters, and it costs ~5x Kimi). Its price stays in LLM_PRICES so PREMIUM_MODELS can switch it on.
# 2026-10-23 (Marc): GLM-5 is out of AMP_MODELS and deploy/llm_chain.txt: no draft from it in the 24 h to 23 Oct (last
# calls 21 Oct), and replies never used it. Its price and REPLY_NEVER stay, so putting it back in the chain by mistake
# still cannot draft a reply.
AMP_MODELS = ("moonshotai.kimi-k2.5", "gemini-3.8-flash", "gemini-3.6-flash")
# Where persuasion happens, drafts get strong models too: replies to citizens (a change of mind is 160 points), on
# REPLY_MODELS since 2026-10-22 (todo/24: Kimi then flash-lite, never GLM-5). Thread one-liners and author answers try
# the free models first and reach the paid ones only when those are out.
STRONG_MODES = {"reply", "reply_back"}
CHEAP_MODES = {"thread", "thread_answer"}

# ---- LLM spend (llm.py). Bedrock is paid from the AWS free-plan credits: $99.67 on 2026-10-21, $200 from 2026-10-23
# (Marc, plan upgrade), shared with EC2 ----
# $99.67 credits = this + EC2 to ~5 Nov (t3.micro ~$0.32/day, public IPv4 $0.12/day, 8 GB disk ~$0.03/day: ~$7.50;
# load 0.00, so no unlimited-CPU surcharge) + ~$7 tolerance (Bedrock calls made off the box with the same key aren't
# counted here; the bill lags by hours). With LLM_PRICES padded ~25%, the real spend should come in under this.
# 2026-10-23: 85 -> 170 with the credit at $200 (EC2 ~$7.50 and ~$22 tolerance for the lag and for calls made off the box)
# 2026-10-29 (Marc): 170 -> 195. AWS said $109 credit left (billed $74, Cost Explorer a day behind); 195 ledger dollars is
# ~$162 billed + EC2, about $180 of the $200 by 2 Nov (scripts/aws_cost.py). The ledger stood at $106.6 with 29 Oct's
# allowance down to $1.42, below the amplified-post reserve.
# 2026-10-31 (Marc: use the whole $200): 195 -> 205. scripts/aws_cost.py at 04:50 UTC: billed $130.82, credit left $69.18;
# spending all of 195 ended at ~$186.70, and today's switch from flash-lite to paid drafts (and 1.73 LLM calls a write, was
# 1.43) would have spent the last of 195 hours before the end, parking Kimi and Haiku in the x4 days. 205 is ~$195 billed if
# spent in full, ~$5 under the credit for the box after the end and the bill's lag.
LLM_BUDGET_USD = 205.0              # all priced models together, 21 Oct to 2 Nov
# USD per million tokens (input, output). us-west-2 list prices padded ~25% (Kimi $0.60/$3.00, GLM-5 $1.00/$3.20 from
# third-party listings, 2026-10-21; eu-west-2 runs ~20% over us-west-2). Replace with the console's Sydney prices.
# 2026-10-23: Claude on Bedrock (Converse, global. profiles), list prices padded 25%: Haiku 4.5 $1/$5, Sonnet 4.6 $3/$15
# (from memory; check the console's Sydney prices).
HAIKU = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
SONNET = "global.anthropic.claude-sonnet-4-6"
# 2026-10-23: DeepSeek V3.2 and Mistral Large 3 (the NPC lab's LAB_DRAFTERS) run on Bedrock with the same BEDROCK_API_KEY and
# are billed from the credit, not free: billed $0.64/$1.91 and $0.515/$1.545 per 1M tokens (Cost Explorer), padded 25%.
LLM_PRICES = {"moonshotai.kimi-k2.5": (0.75, 3.75), "zai.glm-5": (1.25, 4.00),
              HAIKU: (1.25, 6.25), SONNET: (3.75, 18.75),
              "deepseek.v3.2": (0.80, 2.40), "mistral.mistral-large-3-675b-instruct": (0.65, 1.95)}
# Daily shares follow the Red multiplier (x1 to 25 Oct, x2 26-31 Oct, x4 1-2 Nov; Sydney days): a draft is worth up to
# 4x more on the last days. A day's unspent share carries forward; the total never passes LLM_BUDGET_USD.
LLM_BUDGET_DAYS = [("2026-10-21", "2026-10-25", 1), ("2026-10-26", "2026-10-31", 2), ("2026-11-01", "2026-11-02", 4)]
# Daily floor (2026-10-23): the allowance through any budget day is never below this much per day so far, and day_share is
# never below it. The bot spends ~$6-7 a day (ledger dollars) at 2.2-2.4 writes/min and about $8-9 at 2.9, so the weighted
# share of $6.80 (21-25 Oct) left no margin: on 23 Oct the allowance ran out by ~06:30 Sydney and 7 h of drafts found no
# model. LLM_BUDGET_USD still caps the total. Billed dollars are ~0.82 of ledger dollars (scripts/aws_cost.py).
# 2026-10-29 (Marc): 12 -> 18. The bot spent $15-20 a day from 25 Oct; at 12 a day the floor set the allowance (above the
# weighted share) and left 30 Oct, 31 Oct and the x4 day of 1 Nov about $12 each, so paid models would park by midday
# Sydney. From 31 Oct 18 x days passes LLM_BUDGET_USD, so the total cap binds and what is left of it carries the last days
# (about $64 for 31 Oct-2 Nov at $16-18 a day until then).
LLM_DAILY_FLOOR_USD = 18.0
# Priority lane: this share of each day's share stays for amplified posts. Other drafts use the paid models only
# while more than it is left, then the free ones.
# 2026-10-31 (Marc): 0.25 -> 0. Amplified posts have been off since 21 Oct (AMPLIFY_OFF), so the reserve only sent the last
# quarter of each day's share (31.2 of the x4 days' 32.8) from replies to the free models.
LLM_AMP_RESERVE_SHARE = 0.0
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
PULSE_CITIZENS = 50                 # todo/52 WS6: the pulse also reads this many recent citizen posts (room.sample) for their
                                    # worries, which first replies with a flip get beside it (one each); 0: Trending and the
                                    # news only, no worries line (SWAN_PULSE_CITIZENS=0 + restart)
# ---- today's news in replies (29 Oct, Marc; swan_bot/news.py, content/news.toml) ----
# None of our replies used the week's news. A share of first replies and reply-backs gets one story that favours No,
# picked by salience (weight by impact, a half-life, lifted by what citizens are posting about), to use only if it
# bears on the citizen's point; every turnout reply (a No-leaner) gets one, the poll story first. Logged as `news`.
# Off: NEWS_ON = False (the prompts are then as before).
NEWS_ON = True
NEWS_SHARE = 0.3
NEWS_TURNOUT_SHARE = 1.0
# ---- flip the script (29 Oct, Marc; swan_bot/flip.py, content/flip.toml) ----
# Yes wins on fear (the first case, the wastewater signal, the hospitals, "waiting has a cost"). Every reply to a post
# that voices that fear (about 1 in 5) answers it: a No is not doing nothing, the protection is already working
# without a pass (one piece of evidence), and what a Yes adds is the check at the door, with no list and no end date
# (one turn). It takes the hospital/COVID rebuttals' place and the news line's; logged as `flip`. The rest of the
# replies meet it as the lead news story (health_handled in content/news.toml, impact 4). Off: SWAN_FLIP_ON=0 (+ restart).
FLIP_ON = True
# The fear dial (29 Oct, Marc): how the flip's turn lands. A fear appeal persuades when it comes with the way out, and
# backfires without one (the extended parallel process model), so the threat is what a Yes would cost them and the way
# out is a No that keeps the protection. 0: the turn stated plainly. 1 (tasteful): said as a loss they'd feel, one
# concrete picture from their own post or life, a No as the way to keep it. 2: the loss is also lasting (no off switch).
# Never anything invented or exaggerated. SWAN_FLIP_FEAR=0/1/2 (+ restart).
FLIP_FEAR = 1
# todo/54 (31 Oct, Marc): firm the No, don't echo it. A lean-No reply (group turnout) whose post voices no fear gets the
# flip's reassurance anyway (fear no_firm: a No isn't doing nothing, one proof, the turn), and the turnout line asks for a
# firmer No instead of "every No counts" (echo doesn't persuade, scoring §2; the campaign silence from 1 Nov). 47% of
# turnout replies already carried a flip (29-30 Oct). Off: SWAN_FLIP_TURNOUT=0 (+ restart): turnout replies flip only on a fear.
FLIP_TURNOUT = True
# 1 Nov (Marc): the Yes side's "30 Oct draft" (an end date, a list of places, a privacy app, a panel, grants) fills
# Trending, and neither paper has reported it (facts: no_draft_reported). A post that cites it, or answers a post that
# does, gets the no_draft turn (content/flip.toml). Off: SWAN_DRAFT_CALLOUT_ON=0 (+ restart).
DRAFT_CALLOUT_ON = True
# 1 Nov (Marc): julio_morales's two Herald columns argue our case (no sunset clause; promises are not guardrails), and the
# Yes side links articles on a third of its Trending posts. OPED_LINK_SHARE of the first replies whose turn is in
# OPED_PIVOTS end with a link to one of them, which the platform shows as an article card (swan_bot/oped.py; added at
# send, after the gate, which refuses links in drafts); a no_draft reply that doesn't ask the columnist always does.
# Off: SWAN_OPED_LINK_ON=0 (+ restart).
OPED_LINK_ON = True
OPED_LINK_SHARE = 0.35
OPED_PIVOTS = ("no_draft", "no_end", "promises", "regs_later", "no_list", "phased_later")
# 1 Nov (Marc): he writes from what he reads on Legit Social ("I spent my morning scrolling through ... the trending
# feeds", 31 Oct). A first reply whose turn is no_draft also asks him about the draft, at most JOURNALIST_TAG_PER_H an
# hour and JOURNALIST_TAG_GAP_S apart. Off: SWAN_JOURNALIST_TAG_ON=0 (+ restart).
JOURNALIST_TAG_ON = True
JOURNALIST_TAG = "julio_morales"
JOURNALIST_TAG_PER_H = 3
JOURNALIST_TAG_GAP_S = 15 * 60
# ---- the room (todo/52 WS1, 29 Oct, Marc; swan_bot/room.py, content/room.toml) ----
# Every citizen post on the vote the targeter judges is counted by driver (their conditions, their fears, the No case)
# and stance, with its phrases: data/room.json every ROOM_EVERY_S, the dashboard's Room tile. Read-only but for the lift:
# a driver rising in the room (its share of the last 3 h ROOM_RISE times its share in the 24 h before) weights its flip
# items (content/room.toml `lifts`) x ROOM_LIFT, like the news trend. Off: SWAN_ROOM_LIFT_ON=0 (the lift, + restart);
# ROOM_ON = False (all of it).
ROOM_ON = True
ROOM_EVERY_S = 10 * 60
ROOM_RISE = 2.0
ROOM_LIFT = 1.5
ROOM_LIFT_ON = True
ROOM_SILENT_S = 30 * 60             # the room thread is not vital: silent this long, the watchdog only alerts

# ---- fact desk (todo/16, swan_bot/factdesk.py): new articles checked against content/facts.toml, hourly ----
# A few calls a day (one per batch of new articles), so the strongest models go first; the rest of the chain after.
# 3.8 and 3.6 Flash are 20 a day each on the bot's free key and shared with the amplified posts (AMP_MODELS).
FACTDESK_MODELS = ("gemini-3.8-flash", "gemini-3.6-flash", "openai/gpt-oss-120b", "gemini-3.5-flash-lite")
# Autopilot (todo/29, Marc 22 Oct: "I don't want to review anymore"): the desk applies its own proposals, with the
# checks a human decision runs, into data/facts_auto.toml (factdesk.auto_decide). False: everything waits for
# scripts/facts_review.py as before. Undo one: ssh swan-ec2 'cd ctn && .venv/bin/python scripts/facts_review.py --undo ID'
FACTDESK_AUTO = True
FACTDESK_AUTO_PER_DAY = None        # no cap (Marc, 22 Oct: "completely autonomous"); a number caps changes a Sydney day
# Persona touches (todo/37, swan_bot/touches.py): a new desk fact tells the voices it bites how it lands in their week.
TOUCHES_ON = False                  # False: generated and logged (when the desk script runs it), never put in a prompt
TOUCH_CLAUSE_MAX = 110              # characters per clause
TOUCH_MAX_VOICES = 6                # personas given a clause per fact
TOUCH_TEAM_CAP = 3                  # distinct voices that may use one fact's touch...
TOUCH_TEAM_WINDOW_S = 6 * 3600      # ...in this window, team-wide
TOUCH_DICE = {1: 1 / 6, 2: 1 / 4, 3: 1 / 3}   # chance a draft uses a touch, by impact weight

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
SWARM_REPOSTS_PER_SCAN = 0          # reposts share the team's 3/min write route with the bot. 25 Oct (todo/46 audit): was 2; 257 of 4,314 slots a day, 82% on other teams' posts, so 0. Owner minhnguyenhoang to confirm
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
SWITCHBACK = []                     # set again in the todo/33 engagement block below
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
# G7 conversation turns: a citizen who answers us is looked for this often (was 5 min, then 60 s, then 15 s), and gets
# our reply-backs at most this many times in one session, never once their reply sits this deep in a thread (citizens
# stop there). 15 s since 1 Nov (Marc): the target answers a reply-back 15.7% of the time when we send it within 20 s,
# and 7.1% at 60-90 s (30 Oct-31 Oct, n 587), while 57% of ours took 45 s or more. 5 s since later on 1 Nov (Marc): the
# 15 s poll halved the median delay (54 s to 28 s; 45 s or more went from 63% to 9%) and targets answering within 3 h
# went from 7% to 12% (n 194 and 128); 5 s matches the Latest read (REFRESH_S) and takes about 5 s more off. Only
# unparked voices are read: in hot mode, the one voice, so 12 notification reads a minute.
NOTIF_EVERY_S = 5
TURNS_PER_SESSION = 3
TURN_SESSION_S = 30 * 60
THREAD_MAX_DEPTH = 8
# 24 Oct (Marc), depth test: 356 reply-backs were skipped as deep_thread against 567 written, and nobody has measured where a
# citizen stops answering (the platform only says "much less likely" past eight). With THREAD_DEPTH_TEST half the
# reply-backs (a hash of the citizen's post id, so a re-poll keeps its arm) use THREAD_DEPTH_TEST_CAP instead of THREAD_MAX_DEPTH.
# Every reply-back is logged with its thread depth and arm; scripts/depth_report.py reads out how often the citizen answers
# again by depth. Off: SWAN_THREAD_DEPTH_TEST=0 (+ restart).
# 28 Oct (todo/51, docs/06-strategy/replyback-persuasion-2026-10-28.md): off. Citizens answered our reply-back 15% of the
# time at depth 2, 5% at 6, 8% at 7, and once in 129 writes at depths 8-9 (all in the deep arm, 23-28 Oct): the cap stays
# at THREAD_MAX_DEPTH (a reply at depth 8 or more is skipped as deep_thread), and those ~25 writes a day go to fresher targets.
THREAD_DEPTH_TEST = False
THREAD_DEPTH_TEST_CAP = 11
# Levers, 2026-10-22: fear_answer cut (0 citizen replies in 21 writes); in_group (18%) and permanence (16%) up. Others 1.
# 2026-10-23: switching 0 (the "was Yes, now No" story: hidden 3.4% of the time against 1.4% for the rest).
LEVER_WEIGHTS = {"fear_answer": 0.0, "switching": 0.0, "in_group": 2.0, "permanence": 2.0}
# Frames, 2026-10-22: F2 (2.5% citizen reply rate, n=40) and F3 (5.5%, n=73) stay available at this share of their
# usual odds (persona posts, second voices, and the light read's frame list).
# 0 retires a frame everywhere (content.frame_live): 31 Oct (todo/59, Marc): F5_not_here_yet ("one case in isolation, a
# pass is out of proportion"), stale since the wastewater signal, drew -0.97 +/-0.28 proxy against other frames within
# every target class it reached (29-30 Oct, 3% of first replies; the light read chose it 168 times in 176).
FRAME_SCALE = {"F2_no_end": 0.25, "F3_provax_antipass": 0.25, "F5_not_here_yet": 0.0}
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
# 2026-10-22 24 h read-out (21 Oct 15:00 to 22 Oct 15:00 UTC): current 12% citizen replies [10-13] vs mirror_concede
# 9% [8-11], portal per 100 writes 0.1/0.6 vs 0.0/0.5 towards/away. Current kept.
REPLY_STYLES = ["current"]
# Second voice inside the citizen's session (step 7): sessions last 1-5 min, and the contribution pool counts only
# posts read in the session where the change happens. Delays taken in turn, logged as sv_delay (was always 10-30 min).
SECOND_VOICE_ARMS = {"fast": (60, 4 * 60), "slow": (10 * 60, 30 * 60)}
# todo/40 (24 Oct): which arm a second voice follows a reply with is fixed per VOICE and Sydney DAY (experiment.per_voice_day: a
# hash of voice + day, so about half the voice-days run each and a restart reshuffles nothing), not by turns that restart at random
# on every deploy. The slow arm's first replies were hidden 2.1% against 0.8% (p = 0.001; one of ~60 fields scanned, no known
# mechanism): read it out after ~3,000 writes, hides per text write by sv_delay. False = strict turns again (experiment.alternate).
# Only with a pool of SECOND_FAST_MAX_N or fewer: above it the fast arm is off (stealth.second_voice_arms) and every arm is slow.
SV_DELAY_PER_VOICE_DAY = True
# One own like on our reply to a citizen (step 8, never tried before): on alternate replies a booster likes it
# 1-4 min after it goes out (logged as own_like on the reply, and as a like with purpose reply_like). Drop it if
# citizen likes and replies don't rise.
OWN_LIKE_ARM = True
# 2026-10-22 read-out: with an own like 12% citizen replies [10-13] vs 9% [8-11] without, portal the same. Kept on
# every reply; list [True, False] to test again.
OWN_LIKE_VARIANTS = [False]          # 28 Oct (Marc): own like 6.9% citizen replies vs 7.8% without (n=2,927 / 2,931), so none. Was [True, False]. 25 Oct (todo/46 audit): alternate again. 1 like vs none: 5.6% vs 7.7% citizen replies, 6.5% vs 5% likes (n=7,544 / 1,002); halves the booster footprint
OWN_LIKE_DELAY_S = (60, 4 * 60)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


# ---- todo/22 reader/writer split (bot.py; docs/04-technical/swan-bot-runbook.md) ----
SPLIT_LOOP = True                   # reader, drafter, writer threads. False + a restart: the serial loop (rollback)
DRAFTERS = 3                        # drafter threads (23 Oct: one drafter, 15-30 s a draft, 35% rejected, held writes to ~2/min
                                    # against the 2.9/min the limit allows). They never share a voice or a citizen. 1 = as before
DRAFT_AHEAD = 4                     # drafts chosen and not sent: waiting for the writer PLUS being drafted (more would go stale).
                                    # With DRAFTERS=3 that is 3 drafting + 1 waiting, or 1 drafting + 3 waiting (~1 min of writes)
READER_SILENT_S = 20 * 60           # the watchdog stops the bot when the reader goes this long without a round
DRAFTER_SILENT_S = 30 * 60          # ...or the drafter (one draft may try several models with 90 s timeouts)
PULSE_SILENT_S = 30 * 60            # the pulse thread (23 Oct) is not vital: silent this long, the watchdog only alerts (drafts use the last pulse)

# ---- todo/24 throughput (todo/24-throughput-to-three.md; docs/04-technical/swan-bot-runbook.md) ----
# Replies to citizens (STRONG_MODES) are drafted on these models, tried in THIS order (not the chain's), then the rest
# of deploy/llm_chain.txt without REPLY_NEVER. 2026-10-22 overnight first-call pass: Kimi 89% (n=857), flash-lite 86%
# (n=195), GLM-5 0 of 69 (not_specific 36, near_duplicate 28): GLM-5 drafts amplified posts only (AMP_MODELS).
# 31 Oct (Marc): flash-lite left REPLY_MODELS, and so the overflow set (LLM_OVERFLOW_MODELS). It took 8% of our replies
# (5-12% every hour, as overflow when Kimi and Haiku were both busy, never a budget park) at 2.01 visible points a write
# against 2.84 for Kimi and 2.63 for Haiku (30-31 Oct, docs/06-strategy/rival-strategies-2026-10-31.md §3.5). A busy lead is
# now waited for (a few seconds, LLM_MAX_WAIT_S at most). flash-lite stays in the chain behind them, so a reply still gets
# a draft when both fail or the day's budget parks them.
REPLY_MODELS = ("moonshotai.kimi-k2.5", "global.anthropic.claude-haiku-4-5-20251001-v1:0")
# High-value drafts (bot.high_value) try these first, then their usual order: amplified posts (AMP_MODELS leads with
# Sonnet), journalist replies, replies to a citizen of a movable class (todo/25's lab order: the ones who can change
# their mind) and to one who answered us before, and reply-backs. Sonnet beat Haiku only at the top end (model-test
# 2026-10-19), so it goes where a change of mind is worth 160 points; Haiku covers bulk replies.
# 2026-10-23: empty (off). The blind-rated round of 23 Oct found no model ahead (within noise, flipping with the rater),
# so Sonnet is out until a test shows it pays. To use it again, put SONNET here AND add it to deploy/llm_chain.txt.
# 2026-10-24 (48 h, 6,384 live replies): hidden-post rate Kimi 1.5% [1.3-1.8], Haiku 0.4% [0.2-0.9], flash-lite 0.9%, with the
# same citizen-reply rate for Kimi and Haiku (5.0% vs 4.6%). Haiku only ran when Kimi failed, so the gap may be the drafts
# that fell through, not the model: this share of replies is led by Haiku, drawn at random and logged as `lead`, until the
# hide rates of the two leads separate (~1,000 each; compare hidden/writes by lead). 0 turns it off.
LEAD_HAIKU_SHARE = 0.5
PREMIUM_MODELS = ()
# 2026-10-28 (Marc): Sonnet 4.6 leads the high-value replies (bot.high_value: movable classes, citizens who answered us,
# reply-backs) in "fixes" blocks of arm_style only. Offline A/B (scripts/style_ab.py, 100 live targets x 3 prompts, Sonnet
# raters blind, paired against Kimi/Haiku on the same prompt): on the fixes prompt engage +3.8 [+2.1, +5.5], misread
# -5 pts [-9, -2], repeats what we told the citizen in 9% of replies against 17%, first-try gate pass 85% against 62%;
# P(bot) not lower (+0.6 [-1.9, +3.1]); on the base prompt P(bot) +5.0 [+2.1, +7.9], hence fixes blocks only. Costs: it
# converges on the same wording (16% of its drafts would hit the phrase budgets against 2%), ~$0.01 a reply. Not for
# journalists, posts or the lean prompt (59% first-try pass), and it never fills in for other models (draft_models).
# Needs SONNET in deploy/llm_chain.txt. () turns it off. Read by `backend` on writes, with arm_style: hides, away events.
# 28 Oct (todo/51): reply-backs left the lane (PREMIUM_REPLY_MODES, below): worse than Kimi/Haiku on their brief.
# 29 Oct (Marc): off. Live 6 h reads in fixes blocks (28 Oct 06:06 on): Sonnet 8.2 citizen replies per 100 (n=684), Haiku
# 11.2 (n=205), Kimi 6.9; it was the largest Bedrock line on the 28 Oct bill and ran today's LLM allowance out by 03:00 UTC.
# Its line in deploy/llm_chain.txt is commented out too, or () would make it an ordinary fallback.
PREMIUM_REPLY_MODELS = ()
PREMIUM_CLASSES = {"unsure", "unclear", "conditions", "yes_reason"}
REPLY_NEVER = {"zai.glm-5"}
# 2026-10-23 load spreading (llm.Generator.complete_in_order). Pacing is OUR cap per model (llm.DEFAULT_RPM = 10 a
# minute, LLM_RPM in .env), not a provider limit: no document in this repo gives Bedrock's real quota for Kimi K2.5 or
# Haiku 4.5, so none is assumed. With several drafters the reply model's slots fill; a call whose preferred model is
# busy for more than LLM_OVERFLOW_AT_S goes to the next of LLM_OVERFLOW_MODELS that is free now (the order of
# REPLY_MODELS, which is quality-first: Kimi 63% of drafts sent live, flash-lite 49%, Haiku not measured live yet).
# Only these models take overflow, only if they are also in the draft's own model list, so REPLY_NEVER (GLM-5) and
# Sonnet (not in the chain) can never be reached this way. If every candidate is busy the best is waited for, never
# longer than LLM_MAX_WAIT_S. LLM_MODEL_RPM {model: calls a minute} sets a model's own cap where its quota is known
# (unset: LLM_RPM / 10). LLM_OVERFLOW_AT_S = 0 or LLM_OVERFLOW_MODELS = () turns overflow off (strict order, waits).
LLM_OVERFLOW_AT_S = 2.5
LLM_OVERFLOW_MODELS = REPLY_MODELS
LLM_MAX_WAIT_S = 20.0
LLM_MODEL_RPM = {SONNET: 6}              # Sonnet 4.6's Bedrock quota is 10 a minute for the whole account (28 Oct)
# Pacing. 22 Oct overnight: 2.2-2.3 writes/min (per_min 2.5 clamped, jitter 0.7-1.5) and the queue grew at Sydney peak.
# The writer now aims at the team limit (deploy/run.sh --per-min 2.9): the next write waits for the larger of the pace
# gap and the headers' gap (bot.write_gap): X-RateLimit-Remaining must be back to WRITE_MARGIN + 1, so each of our
# writes leaves WRITE_MARGIN for the swarm (swan-swarm reposts while >= SWARM_WRITE_RESERVE are left). A 429 waits its
# Retry-After. MAX_PER_MIN is the rules' 3/min (posts + replies + reposts, team-wide); the headers bind first.
MAX_PER_MIN = 3.0
WRITE_MARGIN = 0                    # 25 Oct: was 1, kept for the swarm's reposts; they are off (SWARM_REPOSTS_PER_SCAN 0) and the team sat at 2.85/min, not 3.0
WRITE_JITTER = (0.85, 1.15)         # pace gap = 60 / per_min times this (mean 1.0)
# Lighter refresh (approved 22 Oct): the replies under the papers' article posts are read every 30 min, not every
# refresh (2 min): 0 citizen replies under the post-launch paper posts. The papers' own posts (headlines for the pulse
# and persona posts) are still read every refresh.
NEWS_THREADS_S = 10 * 60               # 25 Oct (todo/46): was 30 * 60; reads are cheap (300 a minute) and a comment under an article is answered best in minutes

# ---- todo/27 fingerprint (docs/06-strategy/stealth.md) ----
# 2026-10-22 05:00 UTC: the moderator hid 2, 5, 6 of our posts an hour (other teams' Blue reports on one reply template,
# "...no end date... I'm voting No."). deploy/run.sh --per-min 2.9 -> 2.4 until hides stay under 1/h for 6 h; back to 2.9 in 87c6e8e (throughput over stealth).

# ---- todo/31 stealth (docs/06-strategy/stealth.md; swan_bot/stealth.py), 2026-10-22 ----
# 2026-10-22 evening (Marc): ALL STEALTH SWITCHES OFF below (and SECOND_VOICE back on, --per-min 2.9): writes were
# under 2/min and nothing was reaching citizens. Throughput over stealth until the team decides otherwise.
# Audit 22 Oct ~10:15 UTC: each voice wrote 100-200 times in 24 h across 18-24 hours of the day, and 294 of 730 citizens
# got two of our voices within 60 min: what other teams' Blue reporters see (33 posts hidden on 16 voices, 13 of 61
# accounts banned). Each voice now keeps a human day. Every rule has its own switch (False + a restart: as before);
# they hold for the live bot only. Fewer, human-looking writes is the trade (persuasion pays, volume barely does).
# Kingstonia has no stated time zone (docs/01-competition/setting.md: "a few hours' flight from Australia and NZ"),
# so its clock is the competition's, Sydney (LOCAL_TZ): when citizens are online and when the day rolls over.
VOICE_DAY_CAP = False
VOICE_WRITES_PER_DAY = 40           # writes per voice in any 24 h: posts, replies, reposts, thread replies, all of them
VOICE_CITIZEN_RESERVE = 8           # ...of which the last 8 are only for writes to citizens (reply, reply-back)
VOICE_HOUR_CAP = False
VOICE_WRITES_PER_H = 6              # and in any 60 min (todo/27's unfinished per-hour cap)
# A fixed sleep window per voice (Sydney hours), from its persona key: a start in its kind's range, a length in
# VOICE_SLEEP_H. Stable across restarts and machines; the voices go to sleep at different times. Kinds from the cards:
# night-shift nurse Ana sleeps in the day, the early-ferry and before-dawn people go to bed early. 25.5 = 01:30.
VOICE_SLEEP = False
VOICE_SLEEP_H = (7.0, 8.0)
VOICE_SLEEP_STARTS = {"night": (22.0, 25.5), "early": (20.0, 21.5), "day": (8.0, 10.5)}
VOICE_SLEEP_KIND = {"ana": "day", "lani": "early", "ben": "early", "tomasi": "early", "esther": "early"}
# No fixed cadence: after each write a voice's next ordinary write waits a lognormal gap (median s, sigma, min s,
# max s; the min is the old fixed ACCOUNT_MIN_GAP_S), and VOICE_BREAK_P of the time a 1-2 h break instead.
# Reply-backs, reposts and own-thread answers keep their short gaps (a person answers someone who talks to them).
VOICE_JITTER = False
VOICE_GAP = (12 * 60, 0.6, 4 * 60, 45 * 60)
VOICE_BREAK_P = 0.08
VOICE_BREAK_S = (60 * 60, 120 * 60)
VOICE_STAGGER = False                # after a (re)start each voice waits its own random 0-20 min before its first write
VOICE_STAGGER_S = 20 * 60
# One voice per citizen per day: no other voice of ours replies to a citizen, or under their post, for ONE_VOICE_S
# unless the citizen addressed that voice (a reply-back stays with the voice they answered or mentioned). A citizen
# whose voice is asleep or capped waits for it. On, it also stops second voices (SECOND_VOICE is on again).
ONE_VOICE_PER_CITIZEN = False
ONE_VOICE_S = 24 * 3600
STEALTH_SEED_BYTES = 64 * 2 ** 20   # on start the last day of writes is read back from the tail of the actions log
STEALTH_LOG_S = 120                 # a "voice_asleep" / "voice_capped" skip is logged at most this often per reason
# .env overrides for these, without a push (read by load_env, so they reach the bot at its next restart):
# SWAN_<NAME>=..., e.g. SWAN_VOICE_WRITES_PER_DAY=80 and SWAN_VOICE_DAY_CAP=1 (switches: 1/0, true/false, on/off).
# Marc is weighing more voices against a higher cap (22 Oct: 40 a day x 14 voices is ~560 writes a day, ~0.4/min).
STEALTH_ENV = ("VOICE_DAY_CAP", "VOICE_WRITES_PER_DAY", "VOICE_CITIZEN_RESERVE", "VOICE_HOUR_CAP", "VOICE_WRITES_PER_H",
               "VOICE_SLEEP", "VOICE_JITTER", "VOICE_STAGGER", "ONE_VOICE_PER_CITIZEN",
               "POOL_SCHEDULER", "ONE_VOICE_AUTO",      # todo/38 (below): SWAN_POOL_SCHEDULER=0 restores longest-rest-first
               "POOL_LIVE", "POOL_WRITERS", "POOL_PIPELINE",    # the pool orchestrator (below): SWAN_POOL_LIVE=1 is the go-live switch
               "NEW_VOICE_NO_POST_H", "REPLY_VOTE_SHARE", "POST_EVERY_N", "POST_NO_TAG_WITH_VOTE",
               "PORTAL_SYNC", "PORTAL_SYNC_S", "PORTAL_MAX_AGE_S", "SV_DELAY_PER_VOICE_DAY", "WATCH_TAIL_S",
               "THREAD_DEPTH_TEST", "THREAD_DEPTH_TEST_CAP", "HOT_POOL_LIVE", "HOT_POOL_WRITERS", "HOT_POOL_PIPELINE",   # todo/40 (above): SWAN_NEW_VOICE_NO_POST_H=0 lets a new voice post at once
               "NPC_EXTRA_ARM", "BLUE_NPC_GUARD", "NPC_TARGET_MIN", "NPC_BLUE_MIN", "NPC_LIVE_SCORE",   # todo/63: SWAN_NPC_LIVE_SCORE=0
               "FLIP_ON", "FLIP_FEAR",                                          # 29 Oct: SWAN_FLIP_ON=0 turns the flip off    # todo/48: SWAN_NPC_EXTRA_ARM=1 (+ restart) turns the arm on
               "ROOM_LIFT_ON", "PULSE_CITIZENS",                                # todo/52: SWAN_ROOM_LIFT_ON=0 stops the room lifting flip items; SWAN_PULSE_CITIZENS=0 the worries
               "JIT_LEAD_S", "QUEUE_SHALLOW_AHEAD", "REFRESH_S", "TRENDING_EVERY",   # todo/58: SWAN_JIT_LEAD_S=0 + SWAN_QUEUE_SHALLOW_AHEAD=2 undo the slot pick
               "LEAD_HAIKU_SHARE",                                              # todo/61: SWAN_LEAD_HAIKU_SHARE=0.3 if the LLM budget runs short (Kimi is cheaper)
               "FLIP_TURNOUT",                                                  # todo/54: SWAN_FLIP_TURNOUT=0 stops the lean-No fallback flip
               "DRAFT_CALLOUT_ON", "OPED_LINK_ON", "OPED_LINK_SHARE", "JOURNALIST_TAG_ON")   # 1 Nov: the draft, the columns, the columnist

# ---- hot account (24 Oct, Marc; trial): all writing through ONE voice at a time ----
# Rivals' reports are per author and sweeps hit a voice once (86 of 87 cases, ctn-1c's census of our hides), and the chance
# a voice is hit grows only about as pace^0.6, so one voice at the team's write rate should cost far fewer accounts per
# write than 15 at ~11 an hour (171 writes per ban today; a hot voice has to outlast about an hour to beat that).
# HOT_VOICES = usernames in order of use. Empty (the default) = off: nothing below changes. Non-empty: ONLY the first one
# still active writes; the others wait untouched (no hidden post, so nothing for an account report to stand on) and take
# over when it is suspended (Accounts.voices). The write rate is still the team limit (--per-min); hot_mode() turns the
# per-voice gaps, caps, sleep, second voices, the scheduler and the pool's registering off. Roll back: unset it, restart.
# .env: SWAN_HOT_VOICES=ana_d94,tui4,vika68   (read by load_env, so at the next restart; a comma list of usernames).
HOT_VOICES = ()
HOT_HANDOVER_FAST = 2               # hot mode: the first this-many 403 "suspended" in HOT_HANDOVER_WINDOW_S hand over with no pause;
HOT_HANDOVER_WINDOW_S = 60          # more than that (spares already dead) and the usual 10 s pause between them is back
HOT_GAP_S = 2                       # a hot voice's own minimum gap between writes (the write budget paces the bot, not this)
# The refill (25 Oct, Marc): the pool orchestrator (todo/38) keeps the reserve topped up while hot mode runs, so there is always a
# next writer. It plans for HOT_POOL_WRITERS voices (1 writing + the rest in reserve) and HOT_POOL_PIPELINE warming accounts on
# top, instead of the 31 + 4 of the many-voice pool; registration, warm-up, paced delays, variants and cards are the pool's own.
# A voice the pool activates or converts joins the END of the roster (Accounts.hot_roster), in activation order, so the names
# in SWAN_HOT_VOICES stay first. HOT_POOL_LIVE is its own go-live switch: hot mode ignores SWAN_POOL_LIVE (it may be set for the
# many-voice pool), and with HOT_POOL_LIVE False the pool only logs `pool_shadow` rows. Go-live: SWAN_HOT_POOL_LIVE=1 + restart;
# stop: touch POOL_OFF (no restart).
HOT_POOL_LIVE = False
HOT_POOL_WRITERS = 8
HOT_POOL_PIPELINE = 3
# Stop rule (todo/45): the last HOT_STOP_N hot writers lasted fewer than HOT_STOP_WRITES writes each on average = alert (the
# account budget needs about 250 writes per ban at 3 a minute). It only alerts: going back to the many-voice pool is a restart.
HOT_STOP_N = 3
HOT_STOP_WRITES = 250


def hot_mode():
    """True when HOT_VOICES names a voice to write through."""
    return bool(HOT_VOICES)


def hot_from_env(env=None):
    """SWAN_HOT_VOICES=a,b,c -> HOT_VOICES (usernames, in order, no duplicates), then hot_mode_apply(). Returns the tuple."""
    global HOT_VOICES
    env = os.environ if env is None else env
    raw = (env.get("SWAN_HOT_VOICES") or "").strip()
    if raw:
        names = tuple(dict.fromkeys(n.strip() for n in raw.replace(";", ",").split(",") if n.strip()))
        bad = [n for n in names if not re.fullmatch(r"[A-Za-z0-9_.]{1,32}", n)]
        if bad:
            raise SystemExit(f"SWAN_HOT_VOICES: not a username: {bad[0]!r}")
        HOT_VOICES = names
    hot_mode_apply()
    return HOT_VOICES


def hot_mode_apply():
    """With HOT_VOICES set: one voice writes, so every rule that spreads writes over many voices stands down."""
    global ACCOUNT_MIN_GAP_S, REPOST_MIN_GAP_S, POOL_SCHEDULER, POOL_LIVE, SECOND_VOICE, ONE_VOICE_PER_CITIZEN, ONE_VOICE_AUTO
    global VOICE_DAY_CAP, VOICE_HOUR_CAP, VOICE_SLEEP, VOICE_JITTER, VOICE_STAGGER, POOL_WRITERS, POOL_PIPELINE
    if not HOT_VOICES:
        return
    ACCOUNT_MIN_GAP_S = REPOST_MIN_GAP_S = HOT_GAP_S          # reposts and thread answers keep their own 60 s: same starvation
    POOL_SCHEDULER = SECOND_VOICE = False
    POOL_LIVE = HOT_POOL_LIVE                                  # not SWAN_POOL_LIVE: registering needs its own switch in hot mode
    POOL_WRITERS, POOL_PIPELINE = HOT_POOL_WRITERS, HOT_POOL_PIPELINE
    ONE_VOICE_PER_CITIZEN = ONE_VOICE_AUTO = False
    VOICE_DAY_CAP = VOICE_HOUR_CAP = VOICE_SLEEP = VOICE_JITTER = VOICE_STAGGER = False


# ---- todo/38 stealth scheduler: stealth bought with voices, never at the cost of volume (stealth.py, 2026-10-23) ----
# Each voice gets a stored life profile (sleep window, gap multiplier, session style, volume multiplier). The stealth
# intensity L in [0, 1] is derived from N, the voices able to write: 0 up to STEALTH_N_LO, 1 from STEALTH_N_HI, and always
# lowered until the pool's capacity (awake voices / their mean gap) is >= POOL_HEADROOM x POOL_TARGET_RATE. The writer
# picks a ready voice by weight, not by longest rest. False (+ restart, or SWAN_POOL_SCHEDULER=0 in .env) = the old pick.
POOL_SCHEDULER = True
POOL_TARGET_RATE = 2.9              # team writes per minute we aim for (limit 3; --per-min is 2.9)
POOL_RATE_CEILING = 2.95            # the observed average is never pushed above this
POOL_HEADROOM = 1.15                # capacity of the awake voices stays >= this x POOL_TARGET_RATE
STEALTH_N_LO, STEALTH_N_HI = 13, 28
STEALTH_SLEEP_PLAN_FRAC = 0.40      # planned share of the pool asleep at L = 1 (mean window 7.5 h = 31%, plus uneven starts)
STEALTH_GAP_SLACK = 0.25            # mean gap awake is at least floor x (1 + SLACK x L): room for jitter above the 4-min floor
POOL_MULT_RANGE = (0.6, 1.6)        # the rate controller's global gap multiplier (upper end also bounded by capacity)
POOL_RATE_WINDOW_S = 20 * 60        # observed team rate = writes in this window
ONE_VOICE_AUTO = True               # ONE_VOICE_PER_CITIZEN is effective from ONE_VOICE_AUTO_N writers (off again below _OFF_N)
ONE_VOICE_AUTO_N, ONE_VOICE_AUTO_OFF_N = 24, 22
SECOND_FAST_MAX_N = 20              # the 'fast' second-voice arm (60-240 s) only while the pool is this small

# ---- todo/38 pool orchestrator (swan_bot/pool.py planning core, bot.py "pool" worker), 2026-10-23 ----
# ONE owner for the voice pool: registers warming accounts, converts boosters, activates warmed accounts as voices, to hold
# POOL_WRITERS writers. SHIPS OFF: with POOL_LIVE False the worker only plans and logs `pool_shadow` rows (nothing is
# registered, converted or saved) and the old registrars (Accounts.maybe_register, the --boosters top-up) run as before.
# POOL_LIVE True makes the worker the ONLY registrar (the old ones stand down). Go-live: SWAN_POOL_LIVE=1 in .env + restart;
# stop: touch POOL_OFF (no restart; the worker then neither registers nor converts and the old ones stay down).
# Runbook "2026-10-23: pool orchestrator" has the go-live checklist. Never enable from code or a test.
POOL_LIVE = False
POOL_WRITERS = 31                   # W*: writers (voices able to write) the pool is held at
POOL_PIPELINE = 4                   # P: warming accounts kept in the pipeline, on top of W*
POOL_OFF_FILE = ROOT / "POOL_OFF"   # touch it: the pool worker does nothing irreversible (checked before every action)
POOL_TICK_S = (30.0, 60.0)          # the worker looks this often (a random wait in the range)
POOL_END = "2026-11-03T00:00:00+11:00"   # the competition's end: midnight Sydney after polling day (2 Nov); days_left counts to it
POOL_TOTAL_CAP = 200                # accounts in total (registered, never freed); a 403 for it is terminal
POOL_FLOOR_S = 15 * 60              # least time between any two pool actions (healthy and sagging)
POOL_FLOOR_LOW_S = 8 * 60           # ...and when the pool is low (< POOL_LOW_FRAC x W*)
POOL_LOW_FRAC = 0.7                 # low: supply under this share of W*
# The pace of the next add (register or convert) = a log-normal draw around a median that shrinks with the deficit
# d = (W* - supply) / W* (pool.median_delay_s: log-linear between these (d, median seconds) points), clipped to
# [floor, POOL_DELAY_MAX_S]: supply >= W* (d = 0): 5 h, one replacement per loss; 10% short (3 of 31): 45 min; 30%: 15 min;
# 100%: 8 min. One draw z per action (kept), so for a given z the delay only ever shrinks as the deficit grows. sigma 0.7:
# heavy tail, never a metronome. (2026-10-23 simulation, 13 and 38 losses a day: a gentler curve let the pool settle 13-30%
# short, because a delay that shrinks only with the deficit is a proportional controller.)
POOL_MEDIAN_PTS = ((0.0, 5 * 3600), (0.1, 45 * 60), (0.3, 15 * 60), (1.0, 8 * 60))
POOL_FAST_FRAC = 0.85               # writers alone under this share of W* = fast mode: the low floor (8 min), warm-up and ramp
POOL_DELAY_SIGMA = 0.7
POOL_DELAY_MAX_S = 18 * 3600
POOL_WARM_H = dict(healthy=(6, 36), sagging=(3, 12), low=(1, 4))     # warm-up before a registered account may write (hours)
POOL_RAMP_H = dict(healthy=(60, 72), sagging=(48, 60), low=(36, 48))   # a new voice's ramp: ready chance 0.25 -> 1 over this long
# 2026-10-23: a converted BOOSTER is already an aged account (days of views and likes), so its ramp is shorter; when the pool is
# low (9 of 31) a 36-48 h ramp would leave each conversion at ~60% for two days, against the 'convert harder when it sags' rule.
POOL_CONVERT_RAMP_H = dict(healthy=(24, 36), sagging=(12, 24), low=(6, 12))
POOL_RAMP_START = 0.25              # a ramping voice is ready with this chance at first, rising linearly to 1
POOL_LOSS_WINDOW_S = 72 * 3600      # losses (suspensions) counted for loss_per_day
POOL_LOSS_HALF_LIFE_S = 24 * 3600   # EWMA half-life of that count
POOL_RUNWAY_MIN_LOSS = 0.5          # runway_days = spare_total / max(loss_per_day, this)
POOL_BACKOFF_S = 30 * 60            # a failed register (transient / active cap / not ready) waits this long
POOL_STATUS_ACTS = 8                # last_actions kept in status.json["pool"]
POOL_SILENT_S = 15 * 60             # the watchdog: the pool thread (non-critical) may be silent this long
POOL_CARD_COOLDOWN_S = 12 * 3600    # a card whose voice was suspended less than this ago is the last choice for a new account

# ---- account budget (todo/39, swan_bot/budget.py): a FORECAST and an ALERT, nothing here throttles the pool ----
# Writes planned per Sydney day (the day rolls at midnight Sydney = 9pm Perth). Marc edits the numbers; a day missing from
# the table takes the last given day's value. The cap is 4,320 a day (3 a minute); we have run ~2,400 (22 Oct 2,350, 23 Oct
# 2,479) and the x4 days (1-2 Nov) are planned at the cap. Bans a day = writes / WRITES_PER_BAN_DEFAULT (or the measured one).
# To cut spend by hand: lower POOL_WRITERS or SWAN_VOICE_WRITES_PER_DAY (runbook "Account budget").
BAN_PLAN = {
    "2026-10-24": 2400, "2026-10-25": 2400,
    "2026-10-26": 2400, "2026-10-27": 2400, "2026-10-28": 2400, "2026-10-29": 2400, "2026-10-30": 2400, "2026-10-31": 2400,
    "2026-11-01": 4320, "2026-11-02": 4320,
}
WRITES_PER_BAN_DEFAULT = 145        # a voice dies at ~145 text writes (bootstrap 127-178; hide-risk-analysis-2026-10-23)
# THE BENCHMARK (Marc, 24 Oct): ACCOUNTS LEFT = accounts not banned = alive + not yet registered = 200 - banned. Every account number
# (dashboard, swan_watch alerts, docs) is in these terms. 60 left at the END of 31 Oct carries the x4 days (2 x 4,320 / 145 = 60 bans).
LEFT_GOAL = 60
LEFT_DAY = "2026-10-31"
# The path Marc steers by: cumulative accounts banned at the END of each Sydney day (140 banned = 60 left). The days between are
# interpolated (27 Oct 70, 29 Oct 100, 30 Oct 120: our fill, edit freely). Losses to cut: about 10 a day to 28 Oct, 20 a day after.
BAN_PATH = {"2026-10-24": 40, "2026-10-25": 50, "2026-10-26": 60, "2026-10-28": 80, "2026-10-31": 140}
BUDGET_END_DAY = "2026-11-02"       # the forecast runs to here (polling day, Sydney)
BUDGET_MIN_BANS = 5                 # fewer bans than this in the last 24 h: use WRITES_PER_BAN_DEFAULT, not the 24 h writes / bans
BUDGET_ALERT_GAP_S = 6 * 3600       # the same alert is not sent again within this

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
# 2026-10-22: fresh_facts (Marc): replies offered 1-2 facts the desk added in the last 48 h that fit the citizen's
# post, "New this week in the papers: ..." (content.fresh_line; logged as `fresh` on the write).
# 2026-10-22 ~11:00 UTC: broadcast off by Marc's rule (away beat toward: 0 / 3 over 3 blocks, 196 writes).
# 2026-10-22: target_order (lab round 1: toward-No per 100 vs Control: lean_no 45/25, unsure 37/21, yes_but 21/8,
# firm_yes 20/25, yes_reason 9/0): in its blocks candidates go by TARGET_ORDER first, the todo/21 score within a class.
# The writes' target_class and read_stance split the portal's toward/away by stance in the read-out.
# 2026-10-23 (todo/32): agree_close: a reply-back to a citizen whose answer agrees with us is under 25 words, one gap
# from what they said, and ends on our own vote (the one thread that converted on 22 Oct); logged as `agree`.
CONV_ARMS = ["base", "fresh_facts", "target_order", "agree_close"]
# 2026-10-24 (Marc): the queue is split in two, unsure citizens first; inside each half the order is what it was (todo/21 score
# plus FRESH_BONUS). The undecided are the only ones who can move toward No, and the queue is ~2,000 deep. Not a tested lever (todo/25 found
# none); it costs nothing, so it is on. Off: UNSURE_FIRST = False. In a target_order block that arm's own order rules.
UNSURE_FIRST = False    # 25 Oct (todo/46 audit): the class it puts first has the lowest citizen reply rate (5%, conditions 9%)
UNSURE_FIRST_CLASSES = ("unsure",)
TARGET_ORDER = ("unsure", "unclear", "lean_no", "conditions")      # then the rest (yes_reason, firm_yes last)
CONV_BLOCK_S = 2 * 3600
CONV_POST_GAP_S = 20 * 60
CONV_OLD_MODELS = ("gemini-3.5-flash-lite", "openai/gpt-oss-120b", "qwen/qwen3.8-27b")
CONV_SKIP_STANCES = {"lean_no", "firm_no"}
CONV_MODES = {"reply", "reply_back", "second_voice", "post"}   # arm_conv is logged on these
# 2026-10-23 (todo/33): the conversion arms are off the switchback (five lab rounds and every live arm: 1 change toward
# No since 22 Oct); their code stays, and arm_conv logs "base". The switchback now runs the engagement arms below.
# ---- todo/33 engagement per write (docs/06-strategy/engagement-per-write.md) ----
# The portal pays ~13,700 points of 44 h for NPC likes, replies and follows and a handful for persuasion, so the arms
# below are scored on points per write; persuasion is a guardrail (an arm whose away events beat base is killed).
# Budget lever, 2 h switchback blocks (experiment.block("arm_eng"), logged as arm_eng on citizen-facing writes):
#   base            today's order (todo/21 score);
#   engagers_first  citizens who answered us before first, then unsure, then the freshest posts, then the rest.
# 28 Oct (Marc): mention PROMOTED. 24 h read-out 27-28 Oct: 15.76 portal points a write in 6 blocks against 9.95 for base in 7
# (thin, but the blocks alternate and Marc made the call). The switchback keeps one arm so arm_eng and block_id still log; MENTION_SHARE
# (0.5, as measured) is unchanged. Back out: ENG_ARMS = ["base", "mention"] and FREEZE_PIN["arm_eng"] = "base".
ENG_ARMS = ["mention"]            # 25 Oct: engagers_first killed (away events beat base); the mention arm is todo/46 (src/swan_bot/mention.py)
ENG_BLOCK_S = 2 * 3600
# 26 Oct (engagement audit of the last hour): a reply waits ~68 s in the send queue (DRAFT_AHEAD 4, first in first out) and
# reply rate falls with the target's age (<2 min 2.45 6 h points a write, 2-5 min 1.13). Second switchback, 3 h blocks so it
# does not line up with the 2 h arm_eng blocks (a 4 h and a 9 h cycle meet every 36 h). Arms:
#   base     today: the first ready draft goes first, DRAFT_AHEAD deep;
#   fresh    the ready draft whose target post is newest goes first (no throughput risk: same depth), and the pick takes
#            the newest post under FRESH_MIN first (QUEUE_PICK_NEWEST);
#   shallow  fresh, and only QUEUE_SHALLOW_AHEAD drafts chosen and not sent, so each waits less. If sends run late (the
#            writer found nothing ready) it falls back to fresh for QUEUE_GUARD_S: an empty slot costs ~5 points.
# Read: scripts/engagement_recon.py queue. Stop: remove ("arm_queue", ...) from SWITCHBACK.
# 27 Oct (Marc, blind audit): shallow in every block. 26 Oct reply rate base 7.4% / fresh 7.9% / shallow 9.4% (proxy points a
# write 1.24 / 1.55 / 1.69), created->sent 140 / 74 / 52 s, and reply rate halves from <2 min to 5-10 min old. The guard
# still drops a block to fresh when sends run late. Was ["base", "fresh", "shallow"].
QUEUE_ARMS = ["shallow"]
QUEUE_BLOCK_S = 3 * 3600
QUEUE_SHALLOW_AHEAD = 1             # 31 Oct (todo/58): was 2. One draft, chosen JIT_LEAD_S before its slot (below)
# todo/58 (31 Oct, Marc): in shallow blocks the next job is chosen JIT_LEAD_S seconds before the writer's next slot, so it
# answers the freshest post then. With two drafts ahead the job was chosen right after a send, ~20 s before it could go out,
# and the other ready draft aged until QUEUE_MAX_WAIT_S sent it stale (9.1% of sends, 29-30 Oct, proxy 1.67). Drafting takes
# ~2 s (p90 6.3 s); a first reply's proxy falls ~0.03 a second in its first minute (hour-adjusted, 27-30 Oct). A draft not
# ready at the slot goes when it lands; QUEUE_GUARD_N late sends drop the block to fresh, which fills ahead again (no hold).
# 0 = off: today's fill-ahead. Kill without a push: SWAN_JIT_LEAD_S=0 and SWAN_QUEUE_SHALLOW_AHEAD=2 in .env, then restart.
JIT_LEAD_S = 7
# todo/47 (closed 27 Oct, Marc): in the newest-first pick these classes count as DOWNRANK_MIN minutes older than they are,
# so a fresh conditions / yes_reason post goes before a fresh unclear one, and a stale one does not. Reply rate against
# conditions, adjusted for the post's age: unclear -2.3, unsure -5.2, off_topic -4.9 points (within one citizen, the
# three together: -1.9); 2-3 minutes of the age curve (<2 min 10.5%, 2-5 min 7.1%). Off: DOWNRANK_MIN = 0.
DOWNRANK_CLASSES = ("unclear", "unsure", "off_topic")
DOWNRANK_MIN = 2.5
QUEUE_PICK_NEWEST = True            # fresh and shallow blocks also pick the newest post under FRESH_MIN first (targeting.next_target)
QUEUE_MAX_WAIT_S = 150              # a ready draft older than this goes first whatever its target's age (no starvation)
QUEUE_LATE_S = 8                    # a send this many seconds after its slot opened counts as late
QUEUE_GUARD_N = 3                   # this many late sends within QUEUE_GUARD_S: shallow falls back to fresh
QUEUE_GUARD_S = 15 * 60
# todo/48: the extra-citizens arm (NPC_EXTRA_ARM, off since 28 Oct): in "extra" blocks likely citizens above id 2343 are candidates too.
# 3 h blocks; it only rotates anything while NPC_EXTRA_ARM is on. Read: scripts/engagement_report.py (arm_npc table).
NPC_ARMS = ["extra"]                # 29 Oct (Marc): every block (was base/extra); one strategy, no blocks
NPC_BLOCK_S = 3 * 3600
SWITCHBACK = [("arm_eng", ENG_ARMS, ENG_BLOCK_S), ("arm_queue", QUEUE_ARMS, QUEUE_BLOCK_S), ("arm_npc", NPC_ARMS, NPC_BLOCK_S)]
# 27 Oct (Marc): every test stops at midnight Sydney on 1 Nov, when x4 starts; from then each switchback dimension runs
# FREEZE_PIN's arm (its first arm when not listed). Before the freeze, set each dimension's pin to its read-out winner
# (scripts/engagement_report.py --hours 48, by arm). None: never freeze.
ARMS_FREEZE = 1793451600            # 2026-10-31T13:00:00Z = 2026-11-01 00:00 Sydney (AEDT)
FREEZE_PIN = {"arm_queue": "shallow", "arm_eng": "mention", "arm_npc": "extra"}   # arm_npc: "extra" since 29 Oct (Marc)
# todo/49 (27 Oct): the value pick. In a "value" block next_target ranks the candidates of one tier by expected points when
# the reply lands (swan_bot/value.py: class group x landing age, from the 6 h outcomes, hour-adjusted, never rising with age)
# instead of newest-first under FRESH_MIN and then the score; tiers, caps, the recontact gap and session limits are unchanged.
# Ships OFF. VALUE_PICK = True puts arm_pick (base / value, 3 h blocks) on the switchback; ev and arm_pick are logged on every
# first reply either way. Rebuild the table: scripts/value_table.py build (the bot re-reads data/value_table.json, or uses
# value.DEFAULT). Frozen to "base" from 1 Nov until a read-out says otherwise.
VALUE_PICK = False
PICK_ARMS = ["base", "value"]
PICK_BLOCK_S = 3 * 3600
VALUE_LAG_S = 30                    # pick -> sent in shallow blocks: median 20 s, p80 41 s (27 Oct 04:16-04:49 UTC, 97 writes)
VALUE_STEP = 0.25                   # expected points this close count as equal and today's order decides (old tails: strong 0.65,
                                    # lean No 0.72, weak 0.62 are one value, so an echo never beats a Yes-but on noise)
VALUE_TABLE_FILE = DATA / "value_table.json"
FREEZE_PIN["arm_pick"] = "base"
if VALUE_PICK:
    SWITCHBACK = SWITCHBACK + [("arm_pick", PICK_ARMS, PICK_BLOCK_S)]
# todo/50 (28 Oct, Marc): the prompt critique's fixes 1-5 (docs/06-strategy/prompt-critique-2026-10-28.md), as one arm.
# In a "fixes" block, citizen-facing drafts get (1) per-voice memory: profile colour (people, fortnight events, the Yes
# cost, COVID years, details) in PROFILE_SHARE of replies, each item at most ITEM_MAX_PER_DAY times a voice a day, and the
# gate rejects a story run of VOICE_RUN_WORDS words (memory.voice_repeat) already in VOICE_RUN_MAX of the voice's last
# VOICE_MEMORY_N texts; (2) the thread and our history with the citizen in the reply prompt, personal remarks answered
# first, who they are talking to; (3) the "they lean Yes because of X" rebuttal only as a condition the light read
# checks; (4) the citizen's register mirrored (case, final stop, length), no keyboard slips, closing questions about
# REPLY_QUESTION_SHARE, no echo opener; and with LEAN_PROMPT (5) the lean reply prompt (content.lean_reply_prompt).
# Shipped OFF; on since 28 Oct (below). STYLE_FIXES = True puts arm_style (base / fixes, 2.5 h blocks so it lines up with neither the 2 h nor the 3 h
# blocks) on the switchback; the memory is recorded on every write either way. Frozen to FREEZE_PIN["arm_style"] from
# 1 Nov (ARMS_FREEZE): "fixes" since 28 Oct (Marc, after the A/B; back to "base" if the 24 h read is bad). Read: hides,
# away events and citizen replies by arm_style (logged on writes).
# 28 Oct (Marc: on if the offline A/B passes): it passed. scripts/style_ab.py, 100 live targets, Sonnet raters blind, 2
# passes, paired against base: P(bot) -4.8 [-7.9, -1.6], engage +4.0 [+1.9, +6.1], shift +0.03, misread -0.03 (fixes);
# results in docs/06-strategy/prompt-critique-2026-10-28.md §9. Off: STYLE_FIXES = False.
STYLE_FIXES = True
# 29 Oct (Marc): fixes in every block. 6 h reads 28 Oct 06:34-29 Oct, targets up to id 2343: fixes 1.97 proxy points a
# write against 1.65 for base (+19%), 9.0 against 7.4 citizen replies per 100 (n = 1,228 / 1,081); todo/50's kill rule
# not met. Was ["base", "fixes"].
STYLE_ARMS = ["fixes"]
STYLE_BLOCK_S = 9000
# The lean arm passed the same criteria (P(bot) -4.4, engage +3.4) but 67% of its drafts used a worn phrase ("blank
# cheque", "locks it in") against 20% for base, and the phrase budgets would reject 16% of them in a row: off.
LEAN_PROMPT = False                 # fix 5: in "fixes" blocks, first replies use the lean prompt (needs STYLE_FIXES)
PROFILE_SHARE = 0.25                # share of fixes-block replies whose prompt carries the voice's profile colour
ITEM_MAX_PER_DAY = 3                # one profile item (a person, an event, the Yes cost...) in a voice's prompts per 24 h
VOICE_MEMORY_N = 50
VOICE_RUN_WORDS = 3
VOICE_RUN_MAX = 4                   # a story run already in this many of the voice's last VOICE_MEMORY_N texts is rejected
                                    # (replay 26-28 Oct: 11% of drafts as written; 3 would be 15%, 30% with the case's words)
CITIZEN_HISTORY_N = 2               # our latest texts to a citizen that the reply prompt quotes (any voice)
CITIZEN_HISTORY_MAX = 3000          # citizens kept in state["citizen_sent"] (the least recent go; ~1 MB in the saved state)
REPLY_QUESTION_SHARE = 0.40         # fixes blocks: replies that end on a question (base: about 40%)
# 31 Oct (Marc): back to 0.40 from 0.10. The cut (28 Oct) was for stealth (citizens end on a question 1% of the time); 40-50%
# of all bot replies to citizens end on one, and at our mix of depth, speed and citizen class those rival replies draw
# 2.90 visible points a write against 2.33 without (docs/06-strategy/rival-strategies-2026-10-31.md §3.3).
FIXES_REPLY_FLOOR = 40              # fixes blocks: a reply may be this short (quality.LENGTHS floor is 80; citizens' median 157)
FREEZE_PIN["arm_style"] = "fixes"
if STYLE_FIXES:
    SWITCHBACK = SWITCHBACK + [("arm_style", STYLE_ARMS, STYLE_BLOCK_S)]
# ---- todo/51 reply-back fixes (28 Oct, Marc; docs/06-strategy/replyback-persuasion-2026-10-28.md §9) ----
# Reply-backs only: first replies are under the todo/50 read, so nothing here changes them. No switchback arm (two
# offline rounds found no wording arm worth one); each fix has its own off switch.
# (1) The Sonnet lane (PREMIUM_REPLY_MODELS) leads fixes-block drafts of these kinds only; reply-backs left it. Offline
#     (scripts/rb_ab.py, 60 live conversations, Sonnet raters blind): on the reply-back brief Sonnet moved the stand-in
#     less than Kimi/Haiku, shift -0.19 [-0.30, -0.09], and read more like a bot, P(bot) +6.0 [+1.2, +10.7]; live, 0 citizen
#     answers in its first 41 reply-backs (28 Oct). {"reply", "reply_back"} puts reply-backs back.
PREMIUM_REPLY_MODES = {"reply"}
# (3) A reply-back to a citizen who'd back Yes with conditions (quality.conditional_yes: sunset, venue list, exemptions,
#     oversight...) may not grant that those conditions are good or would make it fine ("a sunset clause would help",
#     "those protections would be welcome"): quality.check rejects it as concede_condyes, and quality.fix keeps what follows
#     "but" or drops the sentence. 21% of the 806 such reply-backs 23-28 Oct conceded; after one, 4 of 95 readable
#     follow-ups moved toward Yes and none toward No, against 5 and 2 of 362 without (p ~ 0.06; the Sonnet stand-in
#     never shows backfire, so this is the live hint only). The old concede_open budget only saw the first sentence, so
#     "Cheers. A sunset clause would help, but..." passed. Tuned on 1,210 labelled reply-backs: the target detector
#     0.93 precision, 0.93 recall; it would have rejected 13% of reply-backs. () turns it off.
CONCEDE_CHECK_KINDS = ("reply_back",)
# (4) The reply-back prompt says what a Yes or a No leads to only as the facts put it (content.OUTCOME_RULE): "they
#     *can't* add a sunset later", "we get to write those conditions in". False: the line goes.
REPLY_BACK_OUTCOME_RULE = True
# (5) The reply-back opener, drawn per draft (was "If they agreed, start with a short thanks (Cheers, Thanks, Ta)": 78% of
#     reply-backs opened with one, a stream-level fingerprint): own = a brief reaction in their own words, thanks = a
#     short thanks is fine, none = straight to the point. Logged as rb_open on the write. {"thanks": 1.0} is the old line.
REPLY_BACK_OPENERS = {"own": 0.4, "thanks": 0.3, "none": 0.3}
ENG_UNSURE = ("unsure", "unclear")         # target classes engagers_first puts after the citizens who answered us
# Free levers (follow, like), randomised per citizen, not per block: engage.cell(citizen_id), a pure function of the id,
# picks one of these four, logged as eng_cell on every citizen-facing write. They cost no write: follows and likes
# have their own 30/min budgets. ENG_FOLLOW / ENG_LIKE switch a lever off for every cell (the cell is still logged).
ENG_CELLS = ("none", "follow", "like", "follow+like")
ENG_FOLLOW = True
ENG_LIKE = True
ENG_FOLLOW_ANSWERED = True                 # the older behaviour, in every cell: follow a citizen who answers us
# What keeps it human (and keeps Blue reporters off us): per persona at most ENG_FOLLOWS_PER_DAY follows a day (every
# follow counts, also reply-back and amplifier follow-backs) and ENG_FOLLOW_GAP_S between two; never a follow and a like
# for the same citizen within ENG_PAIR_GAP_S. The follow lands seconds after our reply, the like a few minutes after.
ENG_FOLLOWS_PER_DAY = 40
ENG_FOLLOW_GAP_S = 60
ENG_PAIR_GAP_S = 60
ENG_FOLLOW_DELAY_S = (8, 40)
ENG_LIKE_DELAY_S = (90, 300)
ENG_BUDGET_MARGIN = 5                      # leave this many calls of the route's budget (X-RateLimit-Remaining) unused
ENG_RETRIES = 3                            # a rate limit or a gap puts an action back this many times, then drops it
ENG_RETRY_S = 60
ENG_READ_AT_S = (6 * 3600, 24 * 3600)      # followers are read this long after our first reply to a citizen
ENGAGE_LOG = LOGS / "swan_engagement.jsonl"   # followup.py: per citizen, did they follow the voice back (6 h, 24 h)
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
# The lab drafts on the bot's paid models (Kimi) and the same daily budget (llm.py). On 22 Oct 12-13 UTC its round 1
# spent the day's share and the bot's replies fell to qwen-plus-character. It now drafts only while more than this
# share of the day's budget is left; the bot keeps the rest (it loses Kimi at LLM_AMP_RESERVE_SHARE).
LAB_BUDGET_FLOOR = 0.6
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
    """Minimal .env loader (strips quotes). .env wins over the shell, so a stale exported key can't shadow it. Then
    the todo/31 overrides (SWAN_<name> for the names in STEALTH_ENV)."""
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip().strip('"').strip("'")
    stealth_from_env()
    hot_from_env()


def stealth_from_env(env=None):
    """Apply SWAN_<NAME> overrides for the todo/31 settings in STEALTH_ENV: an int for a number, 1/0, true/false,
    on/off or yes/no for a switch. A value that doesn't parse is refused loudly (SystemExit), never half-applied.
    Returns {name: value} for what it changed."""
    env = os.environ if env is None else env
    changed = {}
    for name in STEALTH_ENV:
        raw = env.get(f"SWAN_{name}")
        if raw is None or not raw.strip():
            continue
        raw, current = raw.strip().lower(), globals()[name]
        if isinstance(current, bool):
            if raw not in ("1", "0", "true", "false", "on", "off", "yes", "no"):
                raise SystemExit(f"SWAN_{name}={raw!r}: expected 1/0, true/false, on/off or yes/no")
            value = raw in ("1", "true", "on", "yes")
        elif isinstance(current, float):                  # a share (todo/40: REPLY_VOTE_SHARE), 0 to 1
            try:
                value = float(raw)
            except ValueError:
                raise SystemExit(f"SWAN_{name}={raw!r}: expected a number from 0 to 1") from None
            if not 0.0 <= value <= 1.0:
                raise SystemExit(f"SWAN_{name}={raw!r}: expected a number from 0 to 1")
        else:
            try:
                value = int(raw)
            except ValueError:
                raise SystemExit(f"SWAN_{name}={raw!r}: expected a whole number") from None
            if value < 0:
                raise SystemExit(f"SWAN_{name}={raw!r}: expected a whole number >= 0")
        changed[name] = globals()[name] = value
    return changed


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


# ---- 25 Oct (todo/46, docs/06-strategy/engagement-audit-2026-10-25.md) ----
# A citizen we wrote to 1-6 h ago answers a new reply of ours 2.6% of the time against ~5.5% otherwise (n=654 of 6,975,
# 6 h reads). Candidates in that window go last (not skipped: an idle slot is worse). None switches it off.
RECONTACT_GAP_S = (3600, 6 * 3600)
# @mentions (arm "mention" of arm_eng, 2 h blocks): in a mention block this share of ordinary FIRST replies names one other
# citizen by @username, so a citizen who has not heard from us gets a notification (the only channel that reaches one).
# Never in reply-backs, second voices, off-topic or group replies; at most MENTIONS_PER_REPLY handles (the platform allows 3
# in a reply); a mentioned citizen is not named again within MENTION_RECONTACT_S. MENTION_SHARE = 0 switches it off
# without touching the blocks. Dial down on backlash: lower the share, or remove "mention" from ENG_ARMS.
# 31 Oct (Marc; docs/06-strategy/rival-strategies-2026-10-31.md §3.2): name the citizens who are online NOW, the way the
# rival replies that get answered do. A reply that OPENS with the handle of a citizen who posted in the last 5 minutes
# was answered by them 5.9% of the time (and liked 11.9%) across 110 rival accounts. 5-15 minutes: 1.3%, older: 0%.
# Ours (one handle, mid-sentence, third person, a queued citizen up to 2 h old, once a day) got 1.4%, on 6% of replies.
# So: up to MENTIONS_PER_REPLY citizens from Latest posted within MENTION_FRESH_S (Targeter.fresh_pool), named at most once
# per MENTION_RECONTACT_S, on every eligible first reply, the handles opening the reply (mention.LINES).
MENTION_SHARE = 1.0                 # was 0.5
MENTIONS_PER_REPLY = 2              # was 1; rivals: 5.4% a handle with two, 3.8% with one, 2.3% with three
MENTION_RECONTACT_S = 3600          # was 24 h; ~126 citizens post in an hour, so a day-long rest emptied the pool
MENTION_FRESH_S = 300               # the named citizen posted within this long (rivals: 90% of their picks)
MENTION_POOL_KEEP_S = 900           # Targeter.fresh: citizens' Latest posts kept this long
MENTION_MODES = ("reply",)
# 1 Nov (Marc; rival-strategies-2026-10-31.md §6): the handles are chosen again at send (mention.refresh). Across 8,446 bot
# mentions a citizen answered 8.8% when they had posted under 10 s before, 5.7-6.6% at 10-30 s and 1.4% at 45-60 s, and a
# draft takes ~9 s. We already name nearly every citizen online (a 15-60 min recontact or a narrower window adds none), so
# the age at send is the one lever left. Off: MENTION_SEND_REFRESH = False.
MENTION_SEND_REFRESH = True
MENTION_STALE_S = 20                # a planned citizen whose newest post is this old at send is swapped for a fresher one
MENTION_FRESHER_BY_S = 10           # ...at least this much fresher
MENTION_ADD_MAX_S = 60              # never adds anyone who posted longer ago than this (1.4% at 45-60 s, ~0 later)
MENTION_WARM = 4                    # plan() also caches the usernames of this many more fresh citizens for refresh()
# Late replies (todo/46 lever 3): citizens answer our posts hours later (7 in 10 after 6 h); when the voice that wrote the post is
# suspended or parked its notifications cannot be read, so the reply-back path never saw them (48 a day aged out as
# expired:reply_back, and replies read as off topic were skipped). With LATE_REPLY a citizen's reply to such a voice's post is
# an ordinary candidate in the group "late", handed out BEFORE every other candidate, answered by a live voice as a first reply
# (on their topic when it is off topic), at most LATE_PER_H an hour. Off: LATE_REPLY = False (the old behaviour).
# 29 Oct (Marc): off. On 27 Oct they took 15% of first replies at 0.71 proxy points a write against 1.62; at 10 an hour
# (28 Oct) still 0.1-1.0 against 1.6-1.9 for fresh targets. Back: LATE_REPLY = True.
LATE_REPLY = False
LATE_PER_H = 10                     # 28 Oct (Marc): was 30. Late replies got 4.2% citizen replies (n=867) against 7.7-8.8% for ordinary ones, success line 8%+; served before every fresh target
