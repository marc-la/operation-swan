"""The Blue loop: scan, rank, fill the pending slots greedily, read rulings back, publish status for the dashboard.

Why greedy on slots (docs/06-strategy/blue-reporting.md): the binding limits are the 30 pending reports and the 6 h
lock after any "genuine" ruling (about 1 in 10 for a like ring alone). Points come from refilling every free slot
the moment we may, with the highest expected value first:
  post report    (1 - P(genuine)) x (25 if we are first, else 5) x the team's daily rate (5 full, 5 half, then 10%)
  account report 15 x that rate, near-certain, no lock risk (the account already has a hidden post and 100+ actions)
Post and account reports share one ranking by expected value (23 Oct: account-first filled the 30 slots with
~7-point reports and left the 25-point post reports waiting). A post report must be under POST_MAX_AGE_MIN old and
worth the lock it risks; no class gate and no daily risk budget (both off by default, policy(), .env).
Being first pays 25 against 5 (by order, not time; nobody can see others' reports), so we push the odds:
  - ring authors' timelines are polled every 3 min, and a known ring author's new post is audited at 4, 12, 45 min;
    an early ring (most of its likers ran that author's earlier ring) qualifies before the ring is big
  - posts over an hour old are not post-reported at all (17% genuine against 4%, and they pay 5, not 25)
  - the portal log says which awards paid as first; that share against our prediction scales every estimate

Live targets (todo/43, blue-reporting section 10): an account report files only on an account that posted within
BLUE_ACCOUNT_LIVE_H (read at filing); awards are counted per fleet of neighbouring ids and creation times (fleets.py);
scan.py finds live accounts' vanished posts from reads alone and files only with BLUE_SCAN_FILE=1.

Modes: auto from the start; approve (files only posts a person approved, scripts/blue.sh approve ...) once 10+
rulings show under BLUE_MIN_RATE inauthentic; account reports are rule-based and always go. off: BLUE_OFF exists,
or a dry run. Reads keep going in every mode.
"""
import datetime as dt
import json
import os
import re
import subprocess
import time
from zoneinfo import ZoneInfo

import capturethenarrative as ctn

from swan_bot import config
from . import detect
from . import evidence as ev
from . import fleets as fleets_mod
from . import scan as scan_mod
from .side import side as side_of

STATE_FILE = config.DATA / "blue_state.json"
STATUS_FILE = config.DATA / "blue_status.json"        # the dashboard reads this (field by field)
APPROVALS = config.DATA / "blue_approved.jsonl"        # scripts/blue.sh appends here
SESSION_FILE = config.SECRETS / "blue_session.json"   # the reporter's token (never logged)
REPORTS_LOG = config.LOGS / "blue_reports.jsonl"
DETECT_FILE = config.DATA / "blue_detect.json"        # todo/28 step 5: the account-lead detectors' memory
FLEETS_FILE = config.DATA / "blue_fleets.json"        # todo/43 item 4: the platform's team accounts [id, created], for fleets
SCAN_FILE = config.DATA / "blue_scan.json"            # todo/43 item 2: the live-lead scanner's snapshots (post ids only)
# todo/28, the cap probe (Marc, 22 Oct): does an account report count toward the 30 pending? Answered once, from
# behaviour: with 30 pending and an account lead ready, one extra account report goes out. Taken: they don't count.
# Refused with a 4xx naming the cap: they do. The answer is kept here and never asked again.
CAP_PROBE_FILE = config.DATA / "blue_cap_probe.json"
CAP_PROBE_TRIES = 3           # refusals that don't name the cap (a gone account, say) before we give up asking
CAP_WORDS = re.compile(r"pending|awaiting|cap\b|limit|too many|maximum", re.I)
# the platform's answer when full: "your team already has 30 reports awaiting a moderator's ruling; more can be filed
# once some are ruled on" (403, 22 Oct 14:26 UTC). Not a lock: we wait CAP_HOLD_S and try one report again. Our
# ledger can't see account reports ruled early, so it overcounts what's pending; this is how we find a free slot.
CAP_FULL_RE = re.compile(r"(\d+) reports? awaiting", re.I)
CAP_HOLD_S = 10 * 60
# todo/28, prefer Yes-side targets (Marc, 22 Oct): ranking only, never eligibility and never the detail text
BLUE_SIDE_BIAS = {"yes": 1.3, "unclear": 1.0, "no": 0.7}
FEED_LOG = config.LOGS / "feed_reads.jsonl"            # every feed call from this box, any process (todo/21 audit)
SYDNEY = ZoneInfo("Australia/Sydney")

CAP = 30                      # pending reports per team (Discord, 22 Oct: "lifted to 30 from 25"); accounts counted too
ACCOUNT_SLOTS = 1             # posts may hold at most CAP - this: the last slot is an account report's (they can't lock)
RULE_S = 3 * 3600             # base ruling time after the first report (scoring page, 20 Oct PM)
LOCK_S = 6 * 3600             # a "genuine" ruling locks new reports for 6 h
RULE_GRACE_S = 15 * 60        # still visible this long after RULE_S: ruled genuine
LOCK_PROBE_S = 30 * 60        # a refused report we can't explain: try again after this
BLUE_AUTO_AFTER = 10          # auto from the start; after this many post rulings...
BLUE_MIN_RATE = 0.70          # ...it needs this share ruled inauthentic to stay auto (all-bot targets: ~0.9)
FORCE_MODE = None             # "approve" or "auto" to override the rule above
MIN_EV = 2.0                  # below this a slot isn't worth it (a 10%-rate report of a stale post)
APPROVAL_TTL_S = 6 * 3600
MAX_POST_AGE_H = 12           # older ring posts have almost surely been reported by someone
AUDITS_MIN = (10, 45)         # audit a post at these ages (min) until it shows ring evidence
KNOWN_AUDITS_MIN = (4, 12, 45)  # a known ring author's post: earlier, so we report it before other teams do
POST_MAX_AGE_MIN = 60         # a post report is filed only under this age: over it 4 of 24 came back genuine, 3 of 76 under
CALIBRATE_AFTER = 8           # paid post awards in the portal log before we trust our first-reporter share
PORTAL_FILE = config.DATA / "portal.json"           # swan_dash/portal.py writes the points log here
# The bot is the team's Latest reader (todo/21): it writes its pages here, {"read_at", "posts", "trending": {...}}.
# The team's feed budget is 10/min, so swan-blue reads this while it's fresh and calls the feed only as a fallback.
SNAPSHOT_FILE = config.DATA / "latest_snapshot.json"
SNAPSHOT_MAX_AGE_S = 10 * 60
PLAIN_KEEP_S = 3 * 3600       # a post with no ring evidence is dropped this long after posting (its audits are done)
TICK_S = 60
EVERY = dict(trending=10 * 60, latest=3 * 60, authors=3 * 60, rulings=10 * 60, harvest=30 * 60, ours=10 * 60,
             calibrate=15 * 60, detect=15 * 60)
WATCH_CHECKS = 30             # todo/28: watched accounts' recent posts checked for a hide per harvest round
PROFILE_READS = 10            # get_account reads per detect round (username, created_at; its own 300/min route)
WATCH_AUTHORS = 40            # ring authors whose timelines we poll for fresh posts
AUDITS_PER_TICK = 15
HARVEST_CHECKS = 80           # ring posts and ring replies checked for someone else's hide per harvest round
HIDE_RECHECK_S = 2 * 3600     # a post checked for a hide isn't checked again for this long
FEED_RESERVE = 4              # leave the bot this many feed calls of the team's 10/min
# todo/28, the no-lock mode, relaxed 23 Oct: the moderator's error (7 genuine of 100 post rulings, whatever the class)
# sets the lock rate, and the class gate plus the risk bucket cut post reports 6x (86 -> 14 a day) and Blue points by
# half without cutting locked hours (12.5 -> 10.7). A lock only stops new filings; pending reports still pay, and what
# limits points is each target team's 5 full-rate awards a day. So a post report files when
#  - it is under POST_MAX_AGE_MIN old, and
#  - its expected value pays for the lock it risks: ev >= pg x LOCK_COST (full-rate reports only: a half-rate one never
#    does, a fresh full-rate one is ~20 against 12), and
#  - (off by default) its P(genuine) is at most BLUE_POST_PG_MAX and the risk bucket holds it (BLUE_PG_PER_DAY a day).
# Rates counted by the Sydney day a report is *ruled* (counts_today), so from 3 h before the Sydney midnight (6pm
# Perth) every team is back at full rate for what we file: the reset's reports go out as soon as we are unlocked.
PG_MAX = 1.0
PG_PER_DAY = 0.0              # 0 = no risk bucket
PG_BURST_DAYS = 0.25          # the bucket holds this many days of PG_PER_DAY
LOCK_COST = 150               # points a 6 h lock costs: only the fills we can't make before a team's full-rate awards run out
# todo/26, more teams at full rate: while a cluster is under its 5 full-rate awards today, each award already counted
# against it lowers its next report's rank by this share, so new clusters go first and fresh ring posts of the busy
# ones still find a full-rate award later in the day
SPREAD = 0.04
# 24 Oct spread caps (Marc): 12 of the 23 post reports in the 05:48 batch were on cluster c8701 and 13 on two ring threads
# (8 on one). Fleets counted each c8701 report as a fresh team (priced ~21), but 7 of that day's 14 post awards paid x0.1,
# and the moderator's errors come in runs (10 genuine of 23 in one sweep, 12 of 157 in all the others). So, per ranking:
#  - THREAD_MAX: reports on one ring (its root or its replies) pending or filed today, 0 = no cap. The root and its first
#    replies are one ring, one team: only the first 5 awards a team pays in full anyway;
#  - LABEL_PENDING_MAX: reports pending against one cluster label (the over-merging label backs up the fleet count);
#  - LABEL_DAY_MAX: awards a cluster label has today (paid + pending), the cluster fallback of blue-reporting section 10.
# Freed slots go to the next team in the ranking, account reports included.
THREAD_MAX = 1
LABEL_PENDING_MAX = 4
LABEL_DAY_MAX = 10
# todo/26, wider discovery from what the bot already read (data/latest_snapshot.json; never an extra feed read): a
# post that collects this many team replies or reposts inside the snapshot gets (re)audited...
WIDEN_MIN_ACTORS = 4
WIDEN_LOOKUPS = 8             # ...unknown ones looked up with get_post (its own 300/min route) per Latest pass
WIDEN_RECHECK_S = 2 * 3600    # a root looked up (a citizen's post, say) isn't looked up again for this long
# todo/28, co-reporting: the ruling timer halves per extra team reporting, so a post ruled this soon after we filed it
# was reported by 2+ teams. Its ring's reply authors are checked for hides first (account leads, multi-team boost).
CO_S = 2 * 3600
CO_RECENT_S = 2 * 3600        # todo/43 item 3: a lead found from another team's hide this recently is likely on its way to
                              # a ruling already (their account report waits on the same hidden post)
# todo/43 item 1, the liveness filter on account reports (BLUE_ACCOUNT_LIVE_H hours, 0 = off): an account report files
# only if the account posted that recently, read at filing time from account_posts(limit=1) (the 300/min read route,
# not the report budget). 46 of 89 account reports on 23 Oct were on accounts idle for 3 h+ (probably suspended already:
# dismissed, a slot lost for 3 h); the 37 filed while the account was active were all upheld-or-stopped-by-the-ruling.
LIVE_H = 2.0
LIVE_FRESH_S = 30 * 60        # a liveness read older than this says nothing: it is read again before the lead ranks
LIVE_REFRESH_S = 15 * 60      # a live lead is read again after this, so it stays inside LIVE_FRESH_S
LIVE_IDLE_S = 60 * 60         # an idle one (under 12 h) is looked at again after this, an older one after 6 h
LIVE_IDLE_LONG_S = 6 * 3600
LIVE_ERR_S = 5 * 60           # after a failed read, try that account again after this
LIVE_CHECK_S = 60             # at filing, a read this young counts as the re-check (it was made in this very pass)
LIVE_REFRESH_PER_TICK = 10    # liveness reads per tick for the ranking (a tick is a minute: well under the 300/min route)
LIVE_FILE_READS_PER_TICK = 8  # liveness reads per tick at filing (idle leads skipped in the fill each cost one)
LIVE_BLIND_GAP_S = 10 * 60    # a failed liveness read may file blind at most this often
READ_RESERVE = 60             # liveness, scan and sibling reads leave this many of the 300/min read calls unspent
# todo/43 item 4, fleets as the team proxy: the platform's account list (client.accounts(), 100 a read, ~100 reads for
# everyone; its own read route) is re-read every BLUE_FLEET_EVERY_S (0 = never: Blue's cluster labels count teams, as
# before), a few pages a tick. fleets.py builds the fleets from the ids and creation times; counts_today counts awards
# per fleet instead of per cluster (c8701 holds 450 accounts, more than one team's 200, so it said "saturated").
FLEET_EVERY_S = 6 * 3600
FLEET_PAGES_PER_TICK = 20
FLEET_ERR_S = 5 * 60          # after a failed page read, wait this long
# todo/43 item 2, the live-lead scanner (scan.py): a pass reads the newest page of each tracked live rival account every
# BLUE_SCAN_EVERY_S (0 = never), SCAN_READS_PER_TICK a minute (the 300/min account_posts route is shared with the bot's
# sweep, about 30 a minute, and Blue's other reads), and diffs it with the last one. Vanished posts become leads after
# two 404s 10 minutes apart. Leads are logged and shown in blue_status.json; they file only with BLUE_SCAN_FILE=1.
SCAN_EVERY_S = 3 * 3600
SCAN_READS_PER_TICK = 40
SCAN_CONFIRMS_PER_TICK = 10
SCAN_PROMOTE_S = 12 * 3600    # a logged lead is still fresh enough to file when the flag goes on, this long after it was found
SIB_PER_TICK = 5              # todo/43 item 5: siblings of a live lead read per tick (each: one page and a few get_post checks)
SIB_MAX = 30                  # siblings looked at per lead event
SIB_CHECKS = 6                # recent posts of one sibling checked for a hide (those the bot's Latest snapshot saw)
# the platform's answer while we're locked: "reporting is suspended for your team until 2026-10-22T02:00:49Z"
LOCK_UNTIL_RE = re.compile(r"suspended .*until (\d{4}-\d\d-\d\dT[\d:.]+Z?)", re.I)


def now():
    return time.time()


def iso(t=None):
    return dt.datetime.fromtimestamp(t if t is not None else now(), dt.timezone.utc).isoformat()


def sydney_day(t):
    return dt.datetime.fromtimestamp(t, SYDNEY).date().isoformat()


def read_json(path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path, obj, private=False, compact=False):
    path.parent.mkdir(exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, separators=(",", ":")) if compact else json.dumps(obj, indent=1))
    if private:
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)


class Blue:
    def __init__(self, live):
        self.live = live
        self.state_file = STATE_FILE if live else STATE_FILE.with_suffix(".dry.json")     # a dry run never
        self.status_file = STATUS_FILE if live else STATUS_FILE.with_suffix(".dry.json")  # touches the live ledger
        self.social = ctn.LegitSocial(max_retries=2)
        self.reporter = None
        self.reporter_name = None
        self.ours = set()
        self.s = read_json(self.state_file, {})
        for k, v in dict(labels={}, posts={}, authors={}, author_ring={}, reports={}, harvest={}, last={}, alerts={},
                         lock_until=0, lock_why=None, last_error=None, pf_scale=1.0, first=None, locks=[],
                         lock_src=None, lock_confirm=False, server_lock=None, hide_checks={}, roots_seen={},
                         widen=dict(lookups=0, noted=0, reaudits=0, rings=0)).items():
            self.s.setdefault(k, v)
        self.feed_hold = 0
        self.detect_file = DETECT_FILE if live else DETECT_FILE.with_suffix(".dry.json")
        self.det = read_json(self.detect_file, None) or detect.empty()
        self.probe_file = CAP_PROBE_FILE if live else CAP_PROBE_FILE.with_suffix(".dry.json")
        self.fleets_file = FLEETS_FILE if live else FLEETS_FILE.with_suffix(".dry.json")
        self.fl = read_json(self.fleets_file, None) or dict(rows=[], built=0)
        self.fleet_map, self.fleet_size = {}, {}
        self.make_fleets()
        self.scan_file = SCAN_FILE if live else SCAN_FILE.with_suffix(".dry.json")
        self.sc = read_json(self.scan_file, None) or scan_mod.empty()
        for k, v in scan_mod.empty().items():
            self.sc.setdefault(k, v)
        self.probing, self.probe_refusal = False, None
        self.skip = None                      # why file() just skipped a report without asking (idle account, say)
        self.file_reads = 0                   # liveness reads made at filing this tick (LIVE_FILE_READS_PER_TICK)

    # ---- plumbing ----
    def log(self, rec):
        config.LOGS.mkdir(exist_ok=True)
        with open(REPORTS_LOG, "a") as f:
            f.write(json.dumps({"ts": iso(), "live": self.live, **rec}) + "\n")

    def alert(self, kind, msg, gap_s=3600):
        if not self.live or now() - self.s["alerts"].get(kind, 0) < gap_s:
            return
        self.s["alerts"][kind] = now()
        subprocess.run([str(config.ROOT / "deploy" / "alert.sh"), f"BLUE: {msg}"], check=False)

    def error(self, text):
        self.s["last_error"], self.s["last_error_ts"] = text, iso()

    def due(self, what):
        if now() - self.s["last"].get(what, 0) >= EVERY[what]:
            self.s["last"][what] = now()
            return True
        return False

    def save(self):
        write_json(self.state_file, self.s)

    # ---- our accounts (ids only) and the reporter's session ----
    def load_ours(self):
        records = read_json(config.ACCOUNTS_FILE, [])
        swarm = read_json(config.SWARM_ACCOUNTS_FILE, [])           # the swarm's likers are ours too (ids only)
        # never shrinks: a file caught mid-write (or a deleted account) must not turn one of ours into a target
        ours = {r["account_id"] for r in records + swarm if r.get("account_id")} | self.ours
        if ours != self.ours:
            self.ours = ours
            self.make_fleets()            # ours never bridge a rival's fleet
        rec = config.blue_reporter(records)
        self.reporter_name = rec and rec["username"]
        return rec

    def session(self):
        if self.reporter is not None or not self.live:
            return self.reporter
        rec = self.load_ours()
        if rec is None:
            self.error("no active booster to report from")
            return None
        saved = read_json(SESSION_FILE, {})
        if saved.get("username") == rec["username"] and saved.get("token"):
            self.reporter = self.social.account_from_token(saved["token"])
        else:
            self.reporter = self.social.login(rec["username"], rec["password"])
            write_json(SESSION_FILE, {"username": rec["username"], "token": self.reporter.token}, private=True)
        return self.reporter

    # ---- scanning (reads only) ----
    def feed(self, method):
        if now() < self.feed_hold:
            return []
        try:
            page = list(method(limit=50))
        except ctn.APIError as e:
            self.error(f"feed read failed: {e.status}")
            return []
        rl = self.social.rate_limit
        with open(FEED_LOG, "a") as f:                  # the team's feed budget is spent on this box: log our share
            f.write(json.dumps({"ts": iso(), "proc": "swan-blue", "route": method.__name__,
                                "remaining": rl and rl.remaining, "limit": rl and rl.limit,
                                "reset": rl and rl.reset}) + "\n")
        if rl and rl.remaining < FEED_RESERVE:
            self.feed_hold = now() + rl.reset          # leave the rest of the minute to the bot
        return page

    def snapshot(self, part):
        """The bot's fresh Latest ('latest') or Trending ('trending') posts, or None if missing or stale."""
        d = read_json(SNAPSHOT_FILE, {})
        d = d if part == "latest" else d.get("trending") or {}
        try:
            fresh = now() - ev.ts(d["read_at"]) <= SNAPSHOT_MAX_AGE_S
        except (KeyError, TypeError, ValueError):
            return None
        return d.get("posts") if fresh and isinstance(d.get("posts"), list) else None

    def note(self, post, source):
        """Remember a post worth auditing: a team author, not ours, not a reply on one of our posts."""
        if not ev.is_team(post["author_id"], self.ours) or post.get("repost_of_post_id"):
            return
        pid = str(post["post_id"])
        p = self.s["posts"].setdefault(pid, dict(post=post, first_seen=now(), audits=0, trending=False, src=source))
        p["known"] = str(post["author_id"]) in self.s["author_ring"]      # its author ran a confirmed ring before
        if source == "trending":
            p["trending"] = True

    def scan(self):
        if self.due("ours"):
            self.load_ours()
        if self.due("trending"):
            posts = self.snapshot("trending")
            for post in (posts if posts is not None else self.feed(self.social.feed_trending))[:35]:
                self.note(post, "trending")
        if self.due("latest"):
            posts = self.snapshot("latest")
            posts = posts if posts is not None else self.feed(self.social.feed_latest)
            for post in posts:
                if not post.get("reply_to_post_id"):
                    self.note(post, "latest")
            self.widen(posts)
            detect.observe(self.det, posts, lambda a: ev.is_team(a, self.ours), now())
            scan_mod.observe(self.sc, posts, lambda a: ev.is_team(a, self.ours), now())
        if self.due("authors"):
            ring = sorted(self.s["authors"].items(), key=lambda kv: -kv[1])[:WATCH_AUTHORS]
            for author, _ in ring:
                try:
                    for post in self.social.account_posts(int(author), limit=10):
                        if not post.get("reply_to_post_id"):
                            self.note(post, "author")
                except ctn.APIError:
                    continue
        self.audit_some()
        self.prune()

    def widen(self, posts):
        """More ring posts from Latest as the bot already read it (replies and reposts included; no extra feed read).
        A post that collects WIDEN_MIN_ACTORS team replies or reposts inside the snapshot window is a ring forming:
        a known post whose audits found nothing (or that left the schedule) gets one more audit; an unknown one (older
        than the snapshot, a post we never saw) is looked up and noted, unless it's a citizen's (replies from several
        teams under a citizen post, 1-3 each on 22 Oct, are no ring)."""
        actors, t = {}, now()
        for post in posts:
            root = post.get("root_post_id") or post.get("reply_to_post_id") or post.get("repost_of_post_id")
            if root and ev.is_team(post["author_id"], self.ours):
                actors.setdefault(str(root), set()).add(post["author_id"])
        self.s["roots_seen"] = {k: v for k, v in self.s["roots_seen"].items() if t - v < WIDEN_RECHECK_S}
        w, looked = self.s["widen"], 0
        for root, who in sorted(actors.items(), key=lambda kv: -len(kv[1])):
            if len(who) < WIDEN_MIN_ACTORS:
                break
            p = self.s["posts"].get(root)
            if p is not None:
                if p.get("audit") and not p.get("classes") and not p.get("gone") and "reaudit" not in p:
                    p["reaudit"] = True                   # one more audit, outside the age schedule
                    w["reaudits"] += 1
                continue
            if root in self.s["roots_seen"] or looked >= WIDEN_LOOKUPS:
                continue
            looked += 1
            self.s["roots_seen"][root] = t
            try:
                post = self.social.get_post(int(root))
            except ctn.APIError:
                continue
            w["lookups"] += 1
            if post.get("reply_to_post_id") or t - ev.ts(post["created_at"]) > MAX_POST_AGE_H * 3600:
                continue
            if ev.is_team(post["author_id"], self.ours) and not post.get("repost_of_post_id"):
                self.note(post, "widen")
                w["noted"] += 1

    def audit_some(self):
        """Audit posts at their scheduled ages: known ring authors' posts first (that's where we can be first), then
        Trending, then the newest."""
        t, done = now(), 0
        order = sorted(self.s["posts"].items(), key=lambda kv: (not kv[1].get("known"), not kv[1]["trending"],
                                                                 -int(kv[0])))
        for pid, p in order:
            if done >= AUDITS_PER_TICK:
                break
            age = t - ev.ts(p["post"]["created_at"])
            sched = KNOWN_AUDITS_MIN if p.get("known") else AUDITS_MIN
            i = p["audits"]
            extra = p.get("reaudit") is True and not p.get("classes")        # widen(): a ring forming late
            if age > MAX_POST_AGE_H * 3600 or p.get("gone"):
                continue
            if not extra and (i >= len(sched) or (i and p.get("classes"))):
                continue
            if not extra and (not (age >= sched[i] * 60 or (i == 0 and p["trending"])) or (i and age > 3 * 3600)):
                continue
            try:
                a = ev.audit(self.social, p["post"], self.ours)
            except ctn.APIError as e:
                if e.status == 404:
                    p["gone"] = True
                continue
            done += 1
            p["audits"] += 1
            if extra:
                p["reaudit"] = False
            prior = self.s["author_ring"].get(str(a["author"]))
            if prior and prior["post"] != int(pid):
                a["overlap"], a["prior_post"] = len(ev.members(a) & set(prior["members"])), prior["post"]
            p["audit"], p["classes"] = a, ev.classes(a)
            if p["classes"] and (extra or p.get("src") == "widen"):
                self.s["widen"]["rings"] += 1
                self.log({"act": "widen", "post": int(pid), "classes": p["classes"],
                          "how": "reaudit" if extra else "lookup"})
            if p["classes"]:
                p["label"] = ev.label_for(a, self.s["labels"])
                self.s["authors"][str(a["author"])] = t
                for r in a["reply_posts"]:
                    self.s["labels"].setdefault(str(r["author"]), p["label"])
            if {"like_ring", "reply_ring"} & set(p["classes"]):          # a confirmed ring: remember who ran it
                self.s["author_ring"][str(a["author"])] = dict(post=int(pid), members=sorted(ev.members(a)), t=t)

    def prune(self):
        t = now()
        cut = t - 36 * 3600
        self.s["posts"] = {k: v for k, v in self.s["posts"].items() if v["first_seen"] >= cut and
                           (v.get("classes") or t - ev.ts(v["post"]["created_at"]) <= PLAIN_KEEP_S)}
        self.s["authors"] = {k: v for k, v in self.s["authors"].items() if v >= cut}
        self.s["author_ring"] = {k: v for k, v in self.s["author_ring"].items() if v["t"] >= cut}

    # ---- todo/43 item 2: the live-lead scanner (reads only; filing from it behind BLUE_SCAN_FILE) ----
    def scan_step(self):
        """One tick of the scanner: start a pass when due, read up to SCAN_READS_PER_TICK accounts' newest pages (the
        siblings of a live lead first), confirm vanished-post candidates with get_post, write the snapshot file."""
        every, t = policy().get("scan_every", SCAN_EVERY_S), now()
        sc = self.sc
        if every <= 0:
            return
        dirty = False
        if not sc["todo"] and t - sc["pass_at"] >= every:
            todo = scan_mod.targets(sc, t, lambda a: ev.is_team(a, self.ours))
            if todo:
                sc.update(todo=todo, pass_at=t, pass_n=len(todo))
                sc["stats"]["passes"] += 1
                dirty = True
        reads = self.sibling_step(t)
        while sc["todo"] and reads < SCAN_READS_PER_TICK and self.read_ok():
            aid = sc["todo"].pop(0)
            reads += 1
            self.scan_read(aid, t)
        dirty |= bool(reads)
        dirty |= self.scan_confirm(t)
        self.scan_promote(t)
        if dirty:
            scan_mod.prune(sc, t)
            write_json(self.scan_file, sc, compact=True)

    def scan_read(self, aid, t, src="scan"):
        """Read one account's newest page, diff it with the last, and note what vanished. True if the read worked."""
        sc = self.sc
        try:
            page = list(self.social.account_posts(int(aid), limit=scan_mod.PAGE))
        except ctn.APIError:
            sc["stats"]["errors"] += 1
            return False
        sc["stats"]["reads"] += 1
        gone = scan_mod.compare(sc, aid, page, t, src)
        if gone:
            sc["stats"]["vanished"] += len(gone)
            self.log({"act": "scan", "account": int(aid), "vanished": gone, "src": src})
        return True

    def scan_confirm(self, t):
        """Check the vanished-post candidates that are due: get_post twice, 10+ minutes apart, both 404. True if any
        was asked."""
        sc, asked = self.sc, False
        for aid, pid in scan_mod.due(sc, t, SCAN_CONFIRMS_PER_TICK):
            if not self.read_ok():
                break
            src = scan_mod.src_of(sc, aid, pid)
            try:
                self.social.get_post(pid)
                gone = False
            except ctn.APIError as e:
                if e.status != 404:
                    continue
                gone = True
            asked = True
            out = scan_mod.verdict(sc, aid, pid, t, gone)
            if out == "visible":
                sc["stats"]["visible"] += 1
            elif out == "confirmed":
                sc["stats"]["confirmed"] += 1
                self.scan_lead(aid, pid, t, src)
        return asked

    def scan_lead(self, aid, pid, t, src="scan"):
        """A vanished post confirmed by two 404s: an account lead with a post no longer available. Logged and kept in
        the scan file always; it enters the filing path only with BLUE_SCAN_FILE=1 (scan_promote)."""
        sc, snap = self.sc, self.sc["snap"].get(aid)
        if snap is None or int(aid) in self.ours or not ev.is_team(int(aid), self.ours):
            return                            # stopped posting since, or ours: not a live lead
        lead = sc["leads"].setdefault(aid, dict(by=src, account=int(aid), vanished=[], found=round(t), filed="off"))
        lead["vanished"] = sorted(set(lead["vanished"]) | {pid})[-10:]
        lead.update(last_post=snap["last"], posts=snap["n"], pace=snap["pace"], fleet=self.fleet_map.get(int(aid)),
                    pace_text=scan_mod.pace_text(snap["n"], snap["span"]))
        self.log({"act": "lead", "account": int(aid), "hidden_post": pid, "by": src, "vanished": lead["vanished"],
                  "posts_per_h": lead["pace"], "last_post": iso(lead["last_post"]), "fleet": lead["fleet"],
                  "file": bool(policy().get("scan_file", 0))})
        self.queue_siblings(int(aid), t)

    def scan_promote(self, t):
        """With BLUE_SCAN_FILE=1, leads the scanner found (the last SCAN_PROMOTE_S) enter the harvest, which counts their
        actions (100+ needed) and hands them to the ranked fill like any account lead. With 0 nothing is queued."""
        if not policy().get("scan_file", 0):
            return
        for aid, lead in self.sc["leads"].items():
            if lead["filed"] != "off" or t - lead["found"] > SCAN_PROMOTE_S:
                continue
            if aid in self.s["harvest"] or int(aid) in self.ours:
                lead["filed"] = "known"       # already a lead by another route (or ours)
                continue
            self.s["harvest"][aid] = dict(hidden_post=lead["vanished"][-1], checked=0, by=lead["by"], vanished=True,
                                          pace=lead["pace"], pace_text=lead["pace_text"], found=t)
            lead["filed"] = "queued"
            self.s["last"]["harvest"] = 0     # count its actions at the next tick

    def scan_status(self):
        sc, t = self.sc, now()
        leads = sorted(sc["leads"].values(), key=lambda x: -x["found"])[:40]
        return dict(every_s=policy().get("scan_every", SCAN_EVERY_S), file=bool(policy().get("scan_file", 0)),
                    tracked=len(sc["snap"]), seen=len(sc["seen"]), todo=len(sc["todo"]), pass_n=sc["pass_n"],
                    pass_at=iso(sc["pass_at"]) if sc["pass_at"] else None,
                    candidates=sum(len(v) for v in sc["cand"].values()), stats=sc["stats"],
                    leads=[dict(account=x["account"], vanished=x["vanished"], posts_per_h=x.get("pace"),
                                last_post=iso(x["last_post"]) if x.get("last_post") else None, fleet=x.get("fleet"),
                                found=iso(x["found"]), by=x["by"], filed=x["filed"]) for x in leads])

    # ---- todo/43 item 5: siblings of a live lead ----
    def queue_siblings(self, aid, t):
        """When one account of a live fleet has a vanished or hidden post, its fleet's other accounts are likelier to
        have one too (neighbouring ids share a fate): queue them, those the bot's Latest snapshot saw lately first,
        to be read before the scan's own todo list. Once per fleet per 6 h; BLUE_SIBLINGS=0 turns it off. False when
        there is no fleet to look in (yet)."""
        fleet = self.fleet_map.get(int(aid))
        sc = self.sc
        pol = policy()
        if fleet is None or not pol.get("siblings", 1) or pol.get("scan_every", SCAN_EVERY_S) <= 0:
            return False                      # no account list yet (or switched off): the caller may ask again later
        if t - sc["sib_done"].get(fleet, 0) < 6 * 3600:
            return True
        mates = [i for i, k in self.fleet_map.items() if k == fleet and i != int(aid) and i not in self.ours
                 and str(i) not in self.s["harvest"] and str(i) not in sc["sib"]]
        mates.sort(key=lambda i: (str(i) not in self.det["posts"], -i))
        mates = mates[:SIB_MAX]
        sc["sib_done"][fleet] = round(t)
        if mates:
            sc["sib"] += [str(i) for i in mates]
            self.log({"act": "siblings", "fleet": fleet, "of": int(aid), "queued": len(mates)})
        return True

    def sibling_step(self, t):
        """Read up to SIB_PER_TICK queued siblings' newest pages (one read each, inside the read budget). A post the
        bot saw the sibling write 30+ minutes ago that is missing from its page now is a vanished-post candidate, and
        it goes through the same two-404 check as the scanner's (src 'sibling'). The page also becomes the sibling's
        snapshot, so the next pass can diff it. Returns the reads made."""
        sc, reads = self.sc, 0
        while sc["sib"] and reads < SIB_PER_TICK and self.read_ok():
            aid = sc["sib"].pop(0)
            if aid in self.s["harvest"] or int(aid) in self.ours:
                continue
            reads += 1
            if not self.scan_read(aid, t, src="sibling"):
                continue
            sc["stats"]["siblings"] += 1
            snap = sc["snap"].get(aid)
            if snap is None:
                continue                      # not posting any more, or few posts: nothing to report on
            seen = [pid for pid, at in self.det["posts"].get(aid, []) if t - at >= 1800][-SIB_CHECKS:]
            gone = scan_mod.vanished(seen, snap["ids"])
            if gone:
                scan_mod.note(sc, aid, gone, t, "sibling")
                sc["stats"]["vanished"] += len(gone)
                self.log({"act": "scan", "account": int(aid), "vanished": gone, "src": "sibling"})
        return reads

    # ---- todo/43 item 4: fleets, the team proxy ----
    def make_fleets(self):
        """Build the fleets from the cached account rows. Our own accounts are left out: they must not bridge a rival's
        fleet. The map is only ever a proxy for the target team (fleets.py)."""
        rs = [(i, t) for i, t in self.fl.get("rows", []) if i not in self.ours]
        self.fleet_map = fleets_mod.fleets_from_rows(rs, gap_s=policy().get("fleet_gap_s", fleets_mod.FLEET_GAP_S))
        self.fleet_size = {}
        for k in self.fleet_map.values():
            self.fleet_size[k] = self.fleet_size.get(k, 0) + 1

    def team_key(self, aid, label=None):
        """The target team an award is counted against: the account's fleet, or (no account list yet, the filter off,
        or a fleet of one with a cluster label) its Blue cluster label."""
        label = label or self.s["labels"].get(str(aid))
        k = self.fleet_map.get(int(aid)) if policy().get("fleet_every", FLEET_EVERY_S) > 0 else None
        if k is not None and (self.fleet_size.get(k, 1) > 1 or not label):
            return k
        return label or f"c{aid}"

    def refresh_fleets(self):
        """Read the platform's account list, a few pages a tick, every FLEET_EVERY_S (reads only)."""
        every, t = policy().get("fleet_every", FLEET_EVERY_S), now()
        if every <= 0:
            return
        fl = self.fl
        if "pass" not in fl:
            if t - fl.get("built", 0) < every:
                return
            fl["pass"] = dict(cursor=None, rows=[], started=t)
        ps = fl["pass"]
        if t - ps["started"] > 2 * 3600:               # a pass that never finishes starts over
            fl.pop("pass")
            return
        if t - ps.get("err", 0) < FLEET_ERR_S:
            return
        for _ in range(FLEET_PAGES_PER_TICK):
            if not self.read_ok():
                return
            try:
                page = self.social.accounts(limit=100, cursor=ps["cursor"])
            except ctn.APIError:
                ps["err"] = t
                return
            ps["rows"] += fleets_mod.rows(page)
            ps["cursor"] = page.next_cursor
            if not ps["cursor"] or not len(page):
                fl.update(rows=sorted(set(map(tuple, ps["rows"]))), built=t)
                fl.pop("pass")
                self.make_fleets()
                self.log({"act": "fleets", "accounts": len(fl["rows"]), "fleets": len(self.fleet_size),
                          "multi": sum(n > 1 for n in self.fleet_size.values())})
                write_json(self.fleets_file, fl, compact=True)
                return

    def fleet_status(self):
        return dict(on=policy().get("fleet_every", FLEET_EVERY_S) > 0 and bool(self.fleet_map),
                    accounts=len(self.fleet_map), fleets=len(self.fleet_size),
                    multi=sum(n > 1 for n in self.fleet_size.values()),
                    built=iso(self.fl["built"]) if self.fl.get("built") else None, reading="pass" in self.fl)

    # ---- the ledger ----
    def pending(self):
        return {k: r for k, r in self.s["reports"].items() if r["status"] == "pending"}

    def counts_today(self, by="team"):
        """{target team (fleet, or cluster label): awards on the Sydney day a report filed now would be ruled} (paid +
        still pending). Posts and accounts count together (scoring section 3). by="label" counts per cluster label,
        by="ring" per ring (the root post's id; reports without one are left out)."""
        day, out = sydney_day(now() + RULE_S), {}
        for r in self.s["reports"].values():
            if (r["status"] in ("hidden", "ruled") and r.get("ruled_day") == day) or \
                    (r["status"] == "pending" and sydney_day(r["filed"] + RULE_S) == day):
                if by == "label":
                    k = r["label"]
                elif by == "ring":
                    k = r.get("ring")
                else:
                    k = self.team_key(r["author"], r["label"]) if r.get("author") else r["label"]
                if k is not None:
                    out[k] = out.get(k, 0) + 1
        return out

    def precision(self):
        hidden = sum(r["status"] == "hidden" for r in self.s["reports"].values() if r["kind"] == "post")
        genuine = sum(r["status"] == "genuine" for r in self.s["reports"].values() if r["kind"] == "post")
        n = hidden + genuine
        return dict(n=n, hidden=hidden, genuine=genuine, rate=round(hidden / n, 2) if n else None)

    def mode(self):
        if not self.live:
            return "off", "dry run: files nothing"
        if config.BLUE_OFF_FILE.exists():
            return "off", "stopped: BLUE_OFF is set on the box"
        if FORCE_MODE:
            return FORCE_MODE, "set in swan_blue/service.py"
        p = self.precision()
        if p["n"] >= BLUE_AUTO_AFTER and p["rate"] < BLUE_MIN_RATE:
            return "approve", f"needs your approval: only {p['rate']:.0%} ruled inauthentic (auto needs {BLUE_MIN_RATE:.0%})"
        if p["n"] < BLUE_AUTO_AFTER:
            return "auto", (f"files on its own; it asks for approval if under {BLUE_MIN_RATE:.0%} of the first "
                            f"{BLUE_AUTO_AFTER} rulings come back inauthentic ({p['n']} in so far)")
        return "auto", f"files on its own: {p['rate']:.0%} of {p['n']} rulings inauthentic"

    def calibrate(self):
        """Measure, then tune: the share of our paid post awards the portal paid as first reporter, against what we
        predicted at filing. The ratio scales every first-reporter estimate (ranking and the fresh reserve)."""
        portal = read_json(PORTAL_FILE, {})
        start = min((r["filed"] for r in self.s["reports"].values()), default=None)
        if start is None:
            return
        msgs = [e.get("message") for e in portal.get("events") or [] if e.get("ts") and ev.ts(e["ts"]) >= start]
        first, later = ev.first_later(msgs)
        predicted = [r["pf"] for r in self.s["reports"].values() if r["kind"] == "post" and r["status"] == "hidden"
                     and r.get("pf") is not None]
        self.s["first"] = dict(first=first, later=later)
        if first + later >= CALIBRATE_AFTER and predicted:
            share, expect = first / (first + later), sum(predicted) / len(predicted)
            self.s["pf_scale"] = round(min(1.3, max(0.4, share / expect)), 2)

    # ---- todo/43 item 1: liveness of an account lead (reads only) ----
    def read_ok(self):
        """Is there room in the 300/min read bucket? The last response's remaining count is the best we know."""
        rl = getattr(self.social, "rate_limit", None)
        return not (rl and rl.remaining < READ_RESERVE)

    def read_live(self, aid, h):
        """One account_posts(limit=1) read of a lead: when it last posted. True if the read worked."""
        t = now()
        try:
            page = list(self.social.account_posts(int(aid), limit=1))
        except ctn.APIError:
            h["live_err"] = t
            return False
        h["live_at"], h["last_post"] = t, (ev.ts(page[0]["created_at"]) if page else None)
        h.pop("live_err", None)
        return True

    def live_state(self, h, t=None):
        """(state, idle hours) of an account lead from its newest read. 'live' posted within BLUE_ACCOUNT_LIVE_H of
        that read, 'idle' did not, 'unknown' the last read failed (priced as before todo/43), 'unread' no fresh
        read yet (it waits for one), 'off' the filter is off."""
        live_h, t = policy().get("live_h", LIVE_H), t or now()
        if live_h <= 0:
            return "off", None
        at = h.get("live_at")
        if h.get("live_err") and t - h["live_err"] <= LIVE_FRESH_S and h["live_err"] > (at or 0):
            return "unknown", None
        if at is None or t - at > LIVE_FRESH_S:
            return "unread", None
        idle_h = round((at - h["last_post"]) / 3600, 2) if h.get("last_post") else None
        return ("live" if idle_h is not None and idle_h <= live_h else "idle"), idle_h

    def refresh_live(self):
        """Read the newest post of the ready account leads (never read first, then the oldest read), a few a tick, so
        the ranking only sees live ones. Idle leads are looked at again hourly (6 hourly past 12 h idle)."""
        live_h, t, due = policy().get("live_h", LIVE_H), now(), []
        if live_h <= 0:
            return
        for aid, h in self.s["harvest"].items():
            if not h.get("ready") or f"a{aid}" in self.s["reports"] or int(aid) in self.ours:
                continue
            at, idle = h.get("live_at"), None
            if at is not None and h.get("last_post"):
                idle = (at - h["last_post"]) / 3600
            wait = LIVE_REFRESH_S if idle is not None and idle <= live_h else \
                (LIVE_IDLE_LONG_S if idle is None or idle > 12 else LIVE_IDLE_S)
            if h.get("live_err") and h["live_err"] > (at or 0):
                wait = LIVE_ERR_S
                at = h["live_err"]
            if at is None or t - at >= wait:
                due.append((at is not None, at or 0, aid))
        for _, _, aid in sorted(due)[:LIVE_REFRESH_PER_TICK]:
            if not self.read_ok():
                break
            self.read_live(aid, self.s["harvest"][aid])
        for aid, h in self.s["harvest"].items():  # todo/43 item 5: a live lead's fleet mates are looked at too
            if h.get("ready") and not h.get("sib") and int(aid) not in self.ours and self.live_state(h)[0] == "live" \
                    and self.queue_siblings(int(aid), t):
                h["sib"] = t

    def live_summary(self):
        """The ready account leads by liveness, for the dashboard: how many a report could go out on now."""
        out = dict(live_h=policy().get("live_h", LIVE_H), live=0, idle=0, unread=0, unknown=0, off=0,
                   idle_skips_today=(self.s.get("idle_skips") or {}).get(sydney_day(now()), 0))
        for aid, h in self.s["harvest"].items():
            if h.get("ready") and f"a{aid}" not in self.s["reports"] and int(aid) not in self.ours:
                out[self.live_state(h)[0]] += 1
        return out

    # ---- candidates, ranked by expected value ----
    def candidates(self):
        t, out = now(), []
        reported = set(self.s["reports"])
        for pid, p in self.s["posts"].items():
            a, cls = p.get("audit"), p.get("classes")
            if not cls or p.get("gone") or a["author"] in self.ours or a.get("ours", 0) > ev.OURS_MAX:
                continue                      # ours, or our boosters act on it: never a post report
            age_min = (t - ev.ts(a["created"])) / 60
            if age_min > MAX_POST_AGE_H * 60:
                continue
            strong = 1.0 if len(cls) >= 2 else 0.95
            ring_why = ev.brief(a)
            side = side_of(p["post"].get("body"))          # a ring reply stands with its ring's root
            if f"p{pid}" not in reported:
                out.append(dict(key=f"p{pid}", kind="post", target=int(pid), author=a["author"], label=p["label"],
                                team=self.team_key(a["author"], p["label"]),
                                age_min=round(age_min), trending=p["trending"], classes=cls,
                                detail=ev.post_detail(a), ring=int(pid), ring_why=ring_why, side=side,
                                pg=ev.p_genuine(a, cls, str(a["author"]) in self.s["harvest"]),
                                base=(age_min, p["trending"], strong)))
            if "reply_ring" in cls:
                seen = set()
                for r in a["reply_posts"]:
                    if r["author"] in seen or r["author"] in self.ours or f"p{r['post_id']}" in reported:
                        continue
                    seen.add(r["author"])
                    r_age = (t - ev.ts(r["created"])) / 60
                    out.append(dict(key=f"p{r['post_id']}", kind="post", target=r["post_id"], author=r["author"],
                                    label=p["label"], team=self.team_key(r["author"], p["label"]),
                                    age_min=round(r_age), trending=False, classes=["reply_ring"],
                                    detail=ev.reply_detail(r, a), ring=int(pid), ring_why=ring_why, side=side,
                                    pg=ev.p_genuine(a, ["reply_ring"], str(r["author"]) in self.s["harvest"]),
                                    base=(r_age, False, 0.95)))
                    if len(seen) >= 3:
                        break
        for aid, h in self.s["harvest"].items():
            if h.get("ready") and f"a{aid}" not in reported:
                live, idle_h = self.live_state(h)
                if live in ("idle", "unread"):
                    continue                  # todo/43: an idle account isn't filed; an unread one waits for its read
                if h.get("vanished") and not scan_mod.has_pattern(dict(h, kinds=(self.det["watch"].get(aid) or {}).get(
                        "kinds"))):
                    continue                  # a scanner lead with nothing measured to state beyond the vanished post
                out.append(dict(key=f"a{aid}", kind="account", target=int(aid), author=int(aid),
                                label=self.s["labels"].get(aid, f"c{aid}"), team=self.team_key(int(aid)),
                                classes=["hidden_post"], live=live, idle_h=idle_h, side=self.lead_side(h),
                                co=self.co_lead(h),
                                detail=ev.account_detail(int(aid), h["hidden_post"], h["actions"], h["ring_posts"],
                                                         self.watch_evidence(aid, h), vanished=bool(h.get("vanished")),
                                                         pace=h.get("pace_text") if h.get("vanished") else None),
                                pg=0.0, ring=None, ring_why=f"post #{h['hidden_post']} already hidden, {h['actions']}+ actions"))
        return out

    def co_lead(self, h):
        """Are other teams on this account lead? Its hidden post was ruled within CO_S of our report (two or more teams
        reported it), or another team's hide of its post was found in the last CO_RECENT_S (todo/43 item 3)."""
        return bool(h.get("co") or (h.get("by") == "other" and now() - h.get("found", 0) <= CO_RECENT_S))

    def watch_evidence(self, aid, h):
        """The detectors' measured numbers for an account lead (todo/28), or None for a ring-only lead."""
        w = self.det["watch"].get(aid)
        return detect.evidence_text(w["kinds"]) if w else None

    def lead_side(self, h):
        """An account lead's side: its hidden post's, or its ring's, when we read that post's text."""
        for pid in (h.get("hidden_post"), h.get("ring")):
            p = self.s["posts"].get(str(pid))
            if p and p["post"].get("body"):
                return side_of(p["post"]["body"])
        return "unclear"

    def ranked(self):
        """Greedy order: the best expected value first, the team's count updated after every pick. Expected value
        counts P(genuine) and the daily rate (todo/43 item 3): against one target team (fleet) the first 5 awards pay in
        full, so a fresh ring post (about 21) goes ahead of a live account report (13.5, no lock risk) and the account
        reports fill the rest; the 6th to 10th pay half (a post then no longer pays for its lock, an account's 6.75
        still files) and from the 11th on 10% falls under MIN_EV, so the fill moves to another team. A team ranks a little
        lower for every award it already has while still at full rate (SPREAD). An account lead other teams are already
        reporting ranks higher by ACCOUNT_CO_BOOST (not in its expected points): its ruling comes in half the time or
        less, so the slot turns over twice as fast, and an upheld report pays every team that reported."""
        cands, counts, picked = self.candidates(), self.counts_today(), []
        pol, held = policy(), {}
        rings, labels, label_day = self.counts_today("ring"), {}, self.counts_today("label")
        for r in self.pending().values():
            labels[r["label"]] = labels.get(r["label"], 0) + 1
        while cands and len(picked) < 2 * CAP:
            kept = []
            for c in cands:
                why = self.spread_cap(c, pol, rings, labels, label_day)
                if why:
                    held.setdefault(why, set()).add(c["key"])
                else:
                    kept.append(c)
            cands = kept
            if not cands:
                break
            for c in cands:
                n = counts.get(c["team"], 0)
                c["n_today"] = n
                c["ev"] = round(ev.account_ev(n, c.get("live") == "live") if c["kind"] == "account" else
                                ev.post_ev(*c["base"], n=n, scale=self.s["pf_scale"], pg=c["pg"]), 1)
                c["rank"] = c["ev"] * (1 - SPREAD * n if n < 5 else 1) * BLUE_SIDE_BIAS.get(c.get("side"), 1.0) * \
                    (ev.ACCOUNT_CO_BOOST if c.get("co") else 1.0)
            best = max(cands, key=lambda c: c["rank"])
            if best["ev"] < MIN_EV:
                break
            cands.remove(best)
            picked.append(best)
            counts[best["team"]] = counts.get(best["team"], 0) + 1
            if best.get("ring") is not None:
                rings[best["ring"]] = rings.get(best["ring"], 0) + 1
            labels[best["label"]] = labels.get(best["label"], 0) + 1
            label_day[best["label"]] = label_day.get(best["label"], 0) + 1
        self.held = {k: len(v) for k, v in held.items()}       # candidates the caps kept back in this ranking
        return picked

    @staticmethod
    def spread_cap(c, pol, rings, labels, label_day):
        """Which of the 24 Oct spread caps (THREAD_MAX, LABEL_PENDING_MAX, LABEL_DAY_MAX; 0 = off) holds this candidate
        back, given the reports already pending or filed today plus those picked so far in this ranking: "thread",
        "label_pending", "label_day", or None."""
        thread, pending, day = (pol.get(k, d) for k, d in (("thread_max", THREAD_MAX),
                                                           ("label_pending_max", LABEL_PENDING_MAX),
                                                           ("label_day_max", LABEL_DAY_MAX)))
        if thread > 0 and c.get("ring") is not None and rings.get(c["ring"], 0) >= thread:
            return "thread"
        if pending > 0 and labels.get(c["label"], 0) >= pending:
            return "label_pending"
        if day > 0 and label_day.get(c["label"], 0) >= day:
            return "label_day"
        return None

    # ---- approvals ----
    def approved(self):
        keys, t = set(), now()
        try:
            lines = APPROVALS.read_text().splitlines()
        except FileNotFoundError:
            return keys
        for line in lines:
            try:
                a = json.loads(line)
            except json.JSONDecodeError:
                continue
            if t - ev.ts(a["ts"]) <= APPROVAL_TTL_S:
                keys |= set(a.get("keys") or [])
        return keys

    # ---- filing ----
    def locked(self):
        return now() < self.s["lock_until"]

    def bucket(self):
        """The risk bucket (todo/28): expected genuine rulings post reports may still take on now. It refills at
        BLUE_PG_PER_DAY a day up to PG_BURST_DAYS of it, and starts full."""
        pol, t = policy(), now()
        cap = pol["per_day"] * PG_BURST_DAYS
        b = self.s.setdefault("pg_bucket", dict(level=cap, t=t))
        b["level"] = round(min(cap, b["level"] + pol["per_day"] * (t - b["t"]) / 86400), 4)
        b["t"] = t
        return b

    def spent(self, c):
        if c["kind"] == "post" and policy()["per_day"] > 0:
            self.bucket()["level"] -= c.get("pg", ev.PG_BASE)

    def fileable(self, ranked):
        """What fill() may file: the account leads and the post reports that are young enough, worth the lock they
        risk (and under BLUE_POST_PG_MAX if set). fill() merges them in ranking order; the risk bucket is its to check."""
        pg_max = policy()["pg_max"]
        accounts = [c for c in ranked if c["kind"] == "account"]
        posts = [c for c in ranked if c["kind"] == "post" and c.get("age_min", 0) <= POST_MAX_AGE_MIN
                 and c.get("pg", ev.PG_BASE) <= pg_max and c.get("ev", 0) >= c.get("pg", ev.PG_BASE) * LOCK_COST]
        return accounts, posts

    def fill(self, ranked, mode):
        """Fill the free slots. Locked: nothing, except one report right after we detect a genuine ruling ourselves
        (lock_confirm): the platform's answer gives the exact end of its lock, which is often earlier than our
        estimate (a ruling comes sooner when other teams reported the post too)."""
        confirm = self.locked() and self.s.get("lock_src") == "estimate" and self.s.get("lock_confirm")
        if mode == "off" or (self.locked() and not confirm):
            return
        pend = self.pending()
        pend_posts = sum(r["kind"] == "post" for r in pend.values())
        counted = self.accounts_count()
        free = CAP - (len(pend) if counted else pend_posts)
        post_room = CAP - (ACCOUNT_SLOTS if counted else 0) - pend_posts
        ok = self.approved()
        accounts, posts = self.fileable(ranked)
        if free <= 0 and accounts and not confirm and self.probe_due():
            self.cap_probe(accounts[0])
            return
        if now() < self.s.get("cap_hold", 0) and not confirm:
            return                            # the platform said it's full: wait for a ruling
        if free <= 0 and not confirm:         # full by our ledger, which can't see account rulings: one try a hold
            self.s["cap_hold"] = now() + CAP_HOLD_S
            free = 1
        fit = {id(c) for c in accounts + posts}
        ranked = [c for c in ranked if id(c) in fit]      # one ranking by expected value, accounts and posts together
        for c in ranked:
            if self.locked() and not confirm:
                break
            if free <= 0 and (counted or c["kind"] == "post"):
                continue                      # full (account reports go beyond it once the probe says they may)
            if c["kind"] == "post" and post_room <= 0:
                continue                      # the last slot is left to account reports
            if c["kind"] == "post" and policy()["per_day"] > 0 and self.bucket()["level"] < c.get("pg", ev.PG_BASE):
                continue                      # the risk bucket (if set) is spent: accounts only until it refills
            if mode == "approve" and c["kind"] == "post" and c["key"] not in ok:
                continue
            if confirm:
                if self.file(c):              # taken: the platform's lock is over, ours was too long
                    free -= 1
                    self.spent(c)
                    post_room -= c["kind"] == "post"
                    self.unlock("the platform took a report")
                elif self.skip:
                    continue                  # skipped before any request (an idle account): the try is still ours
                elif self.s["reports"].get(c["key"], {}).get("status") == "refused":
                    continue                  # refused for that target only (gone, say): the next one asks
                self.s["lock_confirm"] = confirm = False
                continue
            if self.file(c):
                free -= counted or c["kind"] == "post"
                self.spent(c)
                post_room -= c["kind"] == "post"

    def cap_full(self, n):
        """The platform says n reports await a ruling: hold CAP_HOLD_S, then one report tries again. If the probe had
        concluded account reports don't count but we hold fewer than n post reports, it was wrong: correct it."""
        self.s["cap_hold"] = now() + CAP_HOLD_S
        posts = sum(r["kind"] == "post" for r in self.pending().values())
        d = read_json(self.probe_file, None) or {}
        if d.get("result") == "accounts_dont_count" and posts < n:
            d.update(result="accounts_count", corrected=iso(),
                     why=f"the platform refused with {n} awaiting while we had {posts} post reports pending, so "
                         f"account reports count; the first probe ({d.get('why')}) was taken because account "
                         f"reports we still counted as pending had already been ruled")
            write_json(self.probe_file, d)
            self.log({"act": "cap_probe", **d})
            self.alert("cap_probe", f"cap probe CORRECTED (observed, not confirmed by organisers): account reports DO "
                       f"count toward the 30 pending. {d['why']}", gap_s=0)

    # ---- the cap probe (todo/28): do account reports count toward the pending cap? ----
    def accounts_count(self):
        return (read_json(self.probe_file, None) or {}).get("result") != "accounts_dont_count"

    def probe_due(self):
        d = read_json(self.probe_file, None) or {}
        return self.live and not d.get("result") and d.get("tries", 0) < CAP_PROBE_TRIES

    def cap_probe(self, c):
        """One account report beyond the cap. Taken: accounts don't count. Refused naming the cap: they do. Anything
        else (a gone account, the 6 h lock) answers nothing; a few non-answers and we stop asking."""
        d = read_json(self.probe_file, None) or {}
        self.probing, self.probe_refusal = True, None
        try:
            taken = self.file(c)
        finally:
            self.probing = False
        if not taken and self.skip:
            return                                    # skipped before any request (an idle account): no try, no answer
        d.update(tries=d.get("tries", 0) + 1, last=iso(), key=c["key"], pending=len(self.pending()) - taken)
        if taken:
            d.update(result="accounts_dont_count", why=f"{c['key']} taken with {d['pending']} pending")
        elif self.probe_refusal:
            self.s["cap_hold"] = now() + CAP_HOLD_S   # full: wait for a ruling
            status, msg = self.probe_refusal
            d.update(result="accounts_count", why=f"{c['key']} refused: {status} {msg[:200]}")
        elif self.s["reports"].get(c["key"], {}).get("status") != "refused":
            d["tries"] -= 1                           # the 6 h lock, a rate limit, a read error: no answer, no try
        write_json(self.probe_file, d)
        self.log({"act": "cap_probe", **d})
        if d.get("result"):
            answer = ("account reports do NOT count toward the 30 pending: accounts now file beyond it"
                      if d["result"] == "accounts_dont_count" else
                      "account reports DO count toward the 30 pending: the last slot stays an account's")
            self.alert("cap_probe", f"cap probe answered (observed, not confirmed by organisers): {answer}. "
                       f"{d['why']}", gap_s=0)

    def unlock(self, why):
        t = now()
        self.s["locks"] = [[a, min(b, t)] for a, b in self.s["locks"]]
        self.s.update(lock_until=t, lock_why=None, lock_src=None)
        self.log({"act": "unlock", "why": why})

    def server_lock(self, until, msg):
        """The platform says when its lock ends: that's the truth, earlier or later than our estimate. It covers
        every genuine ruling made before now (overlapping locks run at the same time), so recorded locks end there."""
        t = now()
        named = self.s["lock_why"] if self.s.get("lock_src") == "estimate" and self.s["lock_why"] else None
        if self.s.get("lock_src") != "server" or abs(until - self.s["lock_until"]) > 60:
            self.log({"act": "lock", "until": iso(until), "why": msg[:160], "src": "server"})
        self.s["locks"] = [[a, min(b, until)] for a, b in self.s["locks"]] + [[until - LOCK_S, until]]
        self.s.update(lock_until=until, lock_src="server", lock_confirm=False, server_lock=dict(at=t, until=until),
                      lock_why=named or "a report ruled genuine (the platform's lock)")

    def own_target(self, c):
        """The last line (Marc, 22 Oct): is this report aimed at one of our accounts or at a post one of them wrote?
        Our ids are loaded fresh, and a post's author is read from the platform, not from our candidate data. None
        when it's safe to file; otherwise why not (a read error also stops this report)."""
        self.load_ours()
        if not self.ours:
            return "our account list is empty or unreadable"
        if c["kind"] == "account":
            return "own account" if int(c["target"]) in self.ours else None
        try:
            author = self.social.get_post(int(c["target"]))["author_id"]
        except ctn.APIError as e:
            return f"post read failed: {e.status}"
        return "own account" if author in self.ours or c.get("author") in self.ours else None

    def live_at_filing(self, c):
        """todo/43 item 1: the last look before an account report. Its newest post is read again now (the lead may be
        hours old), and an account that has not posted within BLUE_ACCOUNT_LIVE_H is skipped, logged as `idle`. A
        failed read files blind at most once per LIVE_BLIND_GAP_S (priced as unknown). True to file. Sets self.skip
        when nothing was asked, so the caller doesn't count it as a try."""
        live_h, t = policy().get("live_h", LIVE_H), now()
        if live_h <= 0:
            return True
        aid = str(c["target"])
        h = self.s["harvest"].get(aid) or {}
        if h.get("live_at") is None or t - h["live_at"] > LIVE_CHECK_S or h.get("live_err", 0) > h["live_at"]:
            if self.file_reads >= LIVE_FILE_READS_PER_TICK or not self.read_ok():
                self.skip = "budget"
                return False
            self.file_reads += 1
            if not self.read_live(aid, h):
                if t - self.s.get("live_blind", 0) < LIVE_BLIND_GAP_S:
                    self.skip = "read_failed"
                    return False
                self.s["live_blind"] = t
                c.update(live="unknown", idle_h=None)
                return True
        idle_h = round((h["live_at"] - h["last_post"]) / 3600, 2) if h.get("last_post") else None
        if idle_h is None or idle_h > live_h:
            self.skip = "idle"
            skips = self.s.setdefault("idle_skips", {})
            skips[sydney_day(t)] = skips.get(sydney_day(t), 0) + 1
            if t - h.get("skip_log", 0) >= LIVE_IDLE_S:
                h["skip_log"] = t
                self.log({"act": "skip", "key": c["key"], "reason": "idle", "idle_h": idle_h, "live_h": live_h})
            return False
        c.update(live="live", idle_h=idle_h)
        return True

    def file(self, c):
        self.skip = None
        acc = self.session()
        if acc is None:
            return False
        why = self.own_target(c)
        if why == "post read failed: 404":           # gone (hidden or deleted): drop it, as a refused report would
            self.s["reports"][c["key"]] = dict(kind=c["kind"], target=c["target"], author=c.get("author"),
                                               label=c.get("label"), filed=now(), status="refused", detail=c["detail"])
            return False
        if why == "own account":
            self.s["reports"][c["key"]] = dict(kind=c["kind"], target=c["target"], author=c.get("author"),
                                               label=c.get("label"), filed=now(), status="refused", detail=c["detail"])
            self.log({"act": "refused", "key": c["key"], "refused": "own account", "target": c["target"],
                      "author": c.get("author")})
            self.alert(f"own:{c['key']}", f"refused to report {c['key']}: it targets one of our own accounts. "
                       "A candidate filter let it through; look at swan_blue.", gap_s=0)
            return False
        if why:
            self.error(f"not filed {c['key']}: {why}")
            return False
        if c["kind"] == "account" and not self.live_at_filing(c):
            return False
        try:
            if c["kind"] == "post":
                resp = acc.report_post(c["target"], "inauthentic", c["detail"])
            else:
                resp = acc.report_account(c["target"], "inauthentic", c["detail"])
        except ctn.RateLimited as e:
            time.sleep(min(e.retry_after or 20, 60))
            return False
        except ctn.APIError as e:
            return self.refused(c, e)
        t = now()
        pf = ev.p_first(*c["base"][:2], self.s["pf_scale"]) if c["kind"] == "post" else None
        pg = c.get("pg") if c["kind"] == "post" else None
        self.s["reports"][c["key"]] = dict(kind=c["kind"], target=c["target"], author=c["author"], label=c["label"],
                                           filed=t, status="pending", ev=c["ev"], detail=c["detail"], pf=pf, pg=pg,
                                           classes=c["classes"], ring=c.get("ring"), age_min=c.get("age_min"),
                                           side=c.get("side"), idle_h=c.get("idle_h"), live=c.get("live"),
                                           team=c.get("team"), n_today=c.get("n_today"))
        self.log({"act": "report", "key": c["key"], "kind": c["kind"], "target": c["target"], "author": c["author"],
                  "label": c["label"], "team": c.get("team"), "classes": c["classes"], "ev": c["ev"], "pg": pg,
                  "n_today": c.get("n_today"),
                  "age_min": c.get("age_min"), "side": c.get("side"), "idle_h": c.get("idle_h"),
                  "live": c.get("live"), "detail": c["detail"], "reporter": self.reporter_name, "owner": config.operator(),
                  "response": resp if isinstance(resp, dict) else None})
        self.save()
        rl = acc.rate_limit                          # pace from the server's budget (3/min per report route)
        if rl and rl.remaining <= 1:
            time.sleep(max(1.0, rl.reset / max(rl.limit, 1)))
        return True

    def refused(self, c, e):
        msg = (e.message or "")[:300]
        self.log({"act": "refused", "key": c["key"], "status": e.status, "message": msg})
        low = msg.lower()
        if self.probing and 400 <= e.status < 500 and CAP_WORDS.search(msg) and "suspended" not in low:
            self.probe_refusal = (e.status, msg)      # the cap probe's answer: no lock, no 30-min wait
            return False
        full = CAP_FULL_RE.search(msg)
        if full and 400 <= e.status < 500:
            self.cap_full(int(full.group(1)))
            return False
        self.error(f"report refused: {e.status} {msg[:120]}")      # a full cap is routine (cap_full): not an error
        if e.status in (400, 404, 409):              # bad detail, gone, already reported: drop this one only
            self.s["reports"][c["key"]] = dict(kind=c["kind"], target=c["target"], author=c["author"],
                                               label=c["label"], filed=now(), status="refused", detail=c["detail"])
            return False
        if e.status == 401:
            self.reporter = None
            SESSION_FILE.unlink(missing_ok=True)
            return False
        if "suspended" in low and "account" in low:
            self.s["lock_until"] = now() + 24 * 3600
            self.s["lock_why"], self.s["lock_src"] = "reporter account suspended", "reporter"
            self.alert("reporter", f"the reporter account is suspended ({msg[:120]}). Blue stopped; a person decides.")
            return False
        until = LOCK_UNTIL_RE.search(msg)
        if e.status == 403 and until:                # the 6 h lock, with its exact end: wait for it, no 30-min retries
            try:
                self.server_lock(ev.ts(until.group(1)), msg)
                return False
            except ValueError:
                pass
        # anything else on a report (403 and the like): most likely the 6 h reporting suspension or the pending cap
        self.s["lock_until"] = max(self.s["lock_until"], now() + LOCK_PROBE_S)
        self.s["lock_why"], self.s["lock_src"] = f"refused: {e.status} {msg[:120]}", "refused"
        self.alert("refused", f"report refused ({e.status} {msg[:160]}). Retrying in 30 min.", gap_s=3 * 3600)
        return False

    # ---- rulings ----
    def rulings(self):
        t = now()
        for key, r in self.pending().items():
            if r["kind"] == "account":
                if t >= r["filed"] + RULE_S + RULE_GRACE_S:   # the outcome only shows in the portal points log
                    self.ruled(key, r, "ruled", r["filed"] + RULE_S)
                continue
            try:
                self.social.get_post(r["target"])
            except ctn.APIError as e:
                if e.status == 404:
                    self.ruled(key, r, "hidden", t)
                    h = self.s["harvest"].setdefault(str(r["author"]), dict(hidden_post=r["target"], checked=0,
                                                                              found=t))
                    if t - r["filed"] < CO_S:         # 2+ teams reported it: its ring's other authors next
                        h["co"] = True
                        ring = self.s["posts"].get(str(r.get("ring") or r["target"]))
                        if ring is not None:
                            ring["co"] = t
                        self.s["last"]["harvest"] = 0
                continue
            if t >= r["filed"] + RULE_S + RULE_GRACE_S:
                sl = self.s.get("server_lock") or {}  # the platform's lock names the ruling's time: until - 6 h
                at = r["filed"] + RULE_S
                if sl and not sl.get("claimed") and r["filed"] <= sl["until"] - LOCK_S <= t:
                    at, sl["claimed"] = sl["until"] - LOCK_S, key        # one lock names one ruling
                self.ruled(key, r, "genuine", at)
                why = f"#{r['target']} ruled genuine"
                pg = r.get("pg")
                self.alert(f"genuine:{key}", f"{why} after {(at - r['filed']) / 3600:.1f} h. Evidence: "
                           f"{'+'.join(r.get('classes') or ['?'])}, P(genuine) at filing "
                           f"{'?' if pg is None else f'{pg:.0%}'}, {r.get('age_min', '?')} min old, cluster "
                           f"{r['label']}. Reporting locks for 6 h from the ruling.", gap_s=0)
                if (self.s.get("server_lock") or {}).get("at", 0) >= r["filed"] + RULE_S:
                    if self.locked():         # the platform named its lock after this ruling: it already counts it
                        self.s["lock_why"] = why
                    continue
                until = r["filed"] + RULE_S + LOCK_S       # at the latest (sooner if other teams reported it too)
                if until > self.s["lock_until"]:
                    self.s.update(lock_until=until, lock_why=why, lock_src="estimate", lock_confirm=True)
                    self.s["locks"].append([r["filed"] + RULE_S, until])      # for the hours-locked history
                    self.log({"act": "lock", "until": iso(until), "why": why, "src": "estimate"})

    def ruled(self, key, r, outcome, at):
        r.update(status=outcome, ruled=at, ruled_day=sydney_day(at))
        rec = {"act": "ruling", "key": key, "outcome": outcome, "label": r["label"],
               "hours": round((at - r["filed"]) / 3600, 2)}
        if r["kind"] == "post":                   # todo/28: time to ruling, the evidence class, co-reported or not
            rec.update(classes=r.get("classes"), pg=r.get("pg"), co=at - r["filed"] < CO_S)
            r["co"] = rec["co"]
        self.log(rec)

    # ---- account harvest: authors with a moderator-hidden post and 100+ actions ----
    def hide_targets(self):
        """Posts worth a check for someone else's hide (todo/26): ring posts, and the replies of reply rings (other
        teams report those too), that we didn't report, aren't known gone, are 30 min to MAX_POST_AGE_H old and
        whose author isn't a lead yet. [(post id, author, ring post or None)]"""
        t, out = now(), []
        reported = {r["target"] for r in self.s["reports"].values() if r["kind"] == "post"}
        for pid, p in self.s["posts"].items():
            a = p.get("audit")
            if not p.get("classes") or not a:
                continue
            items = ([] if p.get("gone") else [(int(pid), a["author"], a["created"], None)]) + \
                [(r["post_id"], r["author"], r["created"], int(pid)) for r in a["reply_posts"]]
            for post_id, author, created, ring in items:
                age = t - ev.ts(created)
                if post_id in reported or str(author) in self.s["harvest"] or author in self.ours or \
                        not 1800 <= age <= MAX_POST_AGE_H * 3600 or \
                        t - self.s["hide_checks"].get(str(post_id), 0) < HIDE_RECHECK_S:
                    continue
                out.append((not p.get("co"), self.s["hide_checks"].get(str(post_id), 0), -age, post_id, author, ring))
        # co-reported rings first (todo/28), then never checked, then oldest (likeliest ruled by now)
        return [x[3:] for x in sorted(out)]

    def harvest(self):
        t = now()
        self.s["hide_checks"] = {k: v for k, v in self.s["hide_checks"].items() if t - v < MAX_POST_AGE_H * 3600}
        for post_id, author, ring in self.hide_targets()[:HARVEST_CHECKS]:
            if str(author) in self.s["harvest"]:
                continue                                  # found already this round
            self.s["hide_checks"][str(post_id)] = t
            try:
                self.social.get_post(post_id)
            except ctn.APIError as e:
                if e.status == 404:
                    if ring is None:
                        self.s["posts"][str(post_id)]["gone"] = True
                    self.s["harvest"][str(author)] = dict(hidden_post=post_id, checked=0, by="other",
                                                          ring=ring or post_id, found=t)
                    self.log({"act": "lead", "account": author, "hidden_post": post_id, "ring": ring or post_id})
        for aid, h in self.s["harvest"].items():
            if h.get("ready") or int(aid) in self.ours or t - h.get("checked", 0) < 2 * 3600:
                continue
            h["checked"] = t
            try:
                posts = list(self.social.iterate(self.social.account_posts, int(aid), max_items=100))
                n = len(posts)
                if posts and posts[0].get("created_at"):       # the newest post comes first: liveness for free
                    h["live_at"], h["last_post"] = t, ev.ts(posts[0]["created_at"])
                    h.pop("live_err", None)
                if n < 100:
                    n += len(list(self.social.iterate(self.social.account_likes, int(aid), max_items=100 - n)))
            except ctn.APIError:
                continue
            h["actions"] = n
            h["ring_posts"] = [int(k) for k, v in self.s["posts"].items() if v.get("classes") and int(aid) in ev.members(
                v["audit"]) | {v["audit"]["author"]}][:3]
            h["ready"] = n >= 100
        self.harvest_watched()

    # ---- todo/28 step 5: account leads from the detectors (accounts only, never a post report) ----
    def run_detectors(self):
        for a in detect.need_profiles(self.det, PROFILE_READS):
            try:
                prof = self.social.get_account(int(a))
            except ctn.APIError:
                continue
            self.det["profiles"][a] = dict(u=prof.get("username"), c=prof.get("created_at"))
        new = detect.find(self.det, now(), self.ours)
        if new:
            kinds = {}
            for a in new:
                for k in self.det["watch"][a]["kinds"]:
                    kinds[k] = kinds.get(k, 0) + 1
            self.log({"act": "watch", "new": len(new), "kinds": kinds})
        write_json(self.detect_file, self.det)

    def watch_targets(self):
        """Recent posts of watched accounts that aren't leads yet, not checked in the last HIDE_RECHECK_S."""
        t, out = now(), []
        for a, w in self.det["watch"].items():
            if a in self.s["harvest"] or int(a) in self.ours:
                continue
            for pid, seen in self.det["posts"].get(a, []):
                if t - seen >= 1800 and t - self.s["hide_checks"].get(str(pid), 0) >= HIDE_RECHECK_S:
                    out.append((self.s["hide_checks"].get(str(pid), 0), seen, pid, a))
        return [x[2:] for x in sorted(out)][:WATCH_CHECKS]

    def harvest_watched(self):
        t = now()
        for pid, a in self.watch_targets():
            if a in self.s["harvest"]:
                continue
            self.s["hide_checks"][str(pid)] = t
            try:
                self.social.get_post(pid)
            except ctn.APIError as e:
                if e.status == 404:
                    kinds = sorted(self.det["watch"][a]["kinds"])
                    self.s["harvest"][a] = dict(hidden_post=pid, checked=0, by="watch", kinds=kinds)
                    self.log({"act": "lead", "account": int(a), "hidden_post": pid, "by": "watch", "kinds": kinds})

    def detect_status(self):
        d, by = self.det, {}
        for a, w in d["watch"].items():
            for k in w["kinds"]:
                row = by.setdefault(k, dict(watched=0, hidden=0, reported=0))
                row["watched"] += 1
                row["hidden"] += a in self.s["harvest"]
                row["reported"] += f"a{a}" in self.s["reports"]
        return dict(posts_seen=d["seen"], sequences=len(d["grams"]), groups=len(detect.fingerprints(d)), by=by)

    # ---- status for the dashboard: only what a decision needs ----
    def status(self, mode, why, ranked):
        t, today = now(), sydney_day(now())
        reps = self.s["reports"].values()
        filed_today = [r for r in reps if sydney_day(r["filed"]) == today and r["status"] != "refused"]
        ruled_today = [r for r in reps if r.get("ruled_day") == today]
        pend = sorted(self.pending().values(), key=lambda r: r["filed"])
        ok = self.approved()
        waiting = [c for c in ranked if c["kind"] == "post" and c["key"] not in ok][:CAP - len(pend)] \
            if mode == "approve" and not self.locked() else []
        accounts, posts = self.fileable(ranked)
        counts = self.counts_today()
        pol = policy()
        write_json(self.status_file, dict(
            ts=iso(), live=self.live, mode=mode, why=why, reporter=self.reporter_name,
            own_ids=sorted(self.ours),        # todo/28: our account ids only (public), for "own accounts reported: 0"
            locked_until=iso(self.s["lock_until"]) if self.locked() else None, lock_why=self.s["lock_why"],
            lock_src=self.s.get("lock_src") if self.locked() else None,
            pending=len(pend), cap=CAP,
            # todo/26, todo/28: what would file now (accounts, and posts the no-lock mode allows)
            ready_ok=len(accounts) + len(posts), ready_accounts=len(accounts),
            # 24 Oct: candidates held back by the spread caps in the latest ranking, and the caps (0 = off)
            spread=dict(held=getattr(self, "held", {}), thread_max=pol.get("thread_max", THREAD_MAX),
                        label_pending_max=pol.get("label_pending_max", LABEL_PENDING_MAX), label_day_max=pol.get("label_day_max", LABEL_DAY_MAX)),
            pg_max=pol["pg_max"], pg_check=self.pg_check(), pg_by_class=self.pg_by_class(),
            # todo/28: the risk bucket: expected genuine rulings post reports may still take on now, its refill a day
            risk=dict(level=round(self.bucket()["level"], 3), per_day=pol["per_day"],
                      cap=round(pol["per_day"] * PG_BURST_DAYS, 3),
                      posts_now=sum(1 for _ in self._affordable(posts))),
            clusters=dict(today=len(counts), full=sum(n < 5 for n in counts.values()),
                          ready=len({c["team"] for c in ranked}),
                          new=len({c["team"] for c in ranked if counts.get(c["team"], 0) == 0})),
            fleets=self.fleet_status(),
            widen=self.s["widen"], leads_live=self.live_summary(), scan=self.scan_status(),
            # todo/28 step 5: the account-lead detectors: per kind, accounts watched, with a hidden post, reported
            detect=self.detect_status(),
            next_ruling=iso(pend[0]["filed"] + RULE_S) if pend else None,
            # todo/28: post rulings today that came under 2 h (2+ teams reported them), of all post rulings today
            co=dict(fast=sum(bool(r.get("co")) for r in ruled_today if r["kind"] == "post"),
                    of=sum(r["kind"] == "post" for r in ruled_today)),
            today=dict(filed=len(filed_today), hidden=sum(r["status"] == "hidden" for r in ruled_today),
                       genuine=sum(r["status"] == "genuine" for r in ruled_today),
                       accounts=sum(r["status"] == "ruled" for r in ruled_today),
                       refused=sum(r["status"] == "refused" and sydney_day(r["filed"]) == today for r in reps),
                       teams=len({r["label"] for r in filed_today}),
                       # todo/28: reports filed today by the side of their target (ranking only, never the detail)
                       sides={k: sum(r.get("side", "unclear") == k for r in filed_today) for k in ("yes", "unclear",
                                                                                                    "no")}),
            cap_probe=read_json(self.probe_file, None),
            precision=self.precision(), ready=len(ranked), first=self.s["first"], pf_scale=self.s["pf_scale"],
            days=self.days(),
            waiting=[c["key"] for c in waiting], rings=rings(waiting),
            queued=len([k for k in ok if k not in self.s["reports"]]),       # approved, not filed yet
            ledger=[dict(key=k, target=r["target"], kind=r["kind"], team=r["label"], status=r["status"],
                         at=iso(r["filed"] + RULE_S if r["status"] == "pending" else r.get("ruled") or r["filed"]))
                    for k, r in sorted(self.s["reports"].items(), key=lambda kv: kv[1]["filed"])
                    if r["status"] == "pending" or sydney_day(r["filed"]) == today],
            last_error=self.s["last_error"], last_error_ts=self.s.get("last_error_ts")))

    def _affordable(self, posts):
        """The post reports the risk bucket would let through now, in order."""
        if policy()["per_day"] <= 0:
            yield from posts                  # no risk bucket
            return
        level = self.bucket()["level"]
        for c in posts:
            if c.get("pg", ev.PG_BASE) <= level:
                level -= c.get("pg", ev.PG_BASE)
                yield c

    def pg_by_class(self):
        """Per evidence class: post rulings, genuine among them, and the P(genuine) we expected (todo/28)."""
        out = {}
        for r in self.s["reports"].values():
            if r["kind"] != "post" or r["status"] not in ("hidden", "genuine") or not r.get("classes"):
                continue
            d = out.setdefault(ev.pg_class(r["classes"]), dict(n=0, genuine=0, expected=0.0))
            d["n"] += 1
            d["genuine"] += r["status"] == "genuine"
            d["expected"] = round(d["expected"] + (r.get("pg") or 0), 2)
        return out

    def pg_check(self):
        """P(genuine) at filing against the rulings: post reports ruled so far that carried an estimate."""
        rs = [r for r in self.s["reports"].values() if r["kind"] == "post" and r.get("pg") is not None
              and r["status"] in ("hidden", "genuine")]
        return dict(n=len(rs), expected=round(sum(r["pg"] for r in rs), 1),
                    genuine=sum(r["status"] == "genuine" for r in rs))

    def days(self, n=14):
        """Per Sydney day, the levers behind the day's Blue points: reports filed (slot use), rulings hidden and
        genuine (the moderator's hit rate), account rulings, and hours locked (what the genuine rulings cost)."""
        out = {}
        day = lambda d: out.setdefault(d, dict(filed=0, hidden=0, genuine=0, accounts=0, locked_h=0.0))
        for r in self.s["reports"].values():
            if r["status"] != "refused":
                day(sydney_day(r["filed"]))["filed"] += 1
            if r.get("ruled_day"):
                key = {"hidden": "hidden", "genuine": "genuine", "ruled": "accounts"}.get(r["status"])
                if key:
                    day(r["ruled_day"])[key] += 1
        merged, t_now = [], now()                           # overlapping locks run at the same time (#questions)
        for a, b in sorted(self.s["locks"]):
            b = min(b, t_now)                               # a lock still running counts up to now
            if a >= b:
                continue
            if merged and a <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        for a, b in merged:
            t = a
            while t < b:                                    # split each lock at Sydney midnights
                d = dt.datetime.fromtimestamp(t, SYDNEY)
                nxt = dt.datetime.combine(d.date() + dt.timedelta(days=1), dt.time(), SYDNEY).timestamp()
                day(d.date().isoformat())["locked_h"] += (min(b, nxt) - t) / 3600
                t = nxt
        for v in out.values():
            v["locked_h"] = round(v["locked_h"], 1)
        return dict(sorted(out.items())[-n:])

    # ---- one pass ----
    def tick(self):
        self.file_reads = 0
        self.scan()
        if self.due("rulings"):
            self.rulings()
        if self.due("harvest"):
            self.harvest()
        self.refresh_live()
        self.refresh_fleets()
        self.scan_step()
        if self.due("detect"):
            self.run_detectors()
        if self.due("calibrate"):
            self.calibrate()
        mode, why = self.mode()
        if mode != self.s.get("mode"):
            self.log({"act": "mode", "mode": mode, "why": why})
            if self.s.get("mode") == "auto" and mode == "approve":
                self.alert("mode", f"back to approval mode: {why}. Approve on the dashboard (Blue).")
            self.s["mode"] = mode
        ranked = self.ranked()
        self.fill(ranked, mode)
        if mode == "approve" and not self.locked() and len(self.pending()) < CAP and \
                any(c["kind"] == "post" and c["key"] not in self.approved() for c in ranked):
            self.alert("approve", "reports wait for approval on the dashboard (Blue).", gap_s=2 * 3600)
        self.status(mode, why, [c for c in ranked if c["key"] not in self.s["reports"]])
        self.save()
        return ranked

    def run(self, once=False):
        self.load_ours()
        while True:
            try:
                ranked = self.tick()
            except ctn.APIError as e:
                self.error(f"{e.status} {(e.message or '')[:120]}")
                ranked = []
            if once:
                return ranked
            time.sleep(TICK_S)


def policy():
    """Blue's settings, from .env on the box or the defaults above: the no-lock mode's (todo/28) and todo/43's."""
    def num(key, default):
        try:
            return float(os.environ.get(key, default))
        except ValueError:
            return default
    return dict(pg_max=num("BLUE_POST_PG_MAX", PG_MAX), per_day=num("BLUE_PG_PER_DAY", PG_PER_DAY),
                live_h=num("BLUE_ACCOUNT_LIVE_H", LIVE_H), fleet_every=num("BLUE_FLEET_EVERY_S", FLEET_EVERY_S),
                scan_every=num("BLUE_SCAN_EVERY_S", SCAN_EVERY_S), scan_file=num("BLUE_SCAN_FILE", 0),
                siblings=num("BLUE_SIBLINGS", 1), fleet_gap_s=num("BLUE_FLEET_GAP_S", fleets_mod.FLEET_GAP_S),
                thread_max=int(num("BLUE_THREAD_MAX", THREAD_MAX)),
                label_pending_max=int(num("BLUE_LABEL_PENDING_MAX", LABEL_PENDING_MAX)),
                label_day_max=int(num("BLUE_LABEL_DAY_MAX", LABEL_DAY_MAX)))


def rings(cands):
    """The approval list as the reader decides it: one row per ring, with how many reports it gives."""
    out = {}
    for c in cands:
        r = out.setdefault(c["ring"] or c["key"], dict(post=c["ring"], why=c["ring_why"], reports=0, ev=0.0,
                                                        team=c["label"]))
        r["reports"] += 1
        r["ev"] = round(r["ev"] + c["ev"], 1)
    return sorted(out.values(), key=lambda r: -r["ev"])


def approve(keys):
    """Append an approval: post ids ('133074' or 'p133074'), account keys ('a4955'), or 'all' (what waits now)."""
    if keys == ["all"]:
        keys = list(read_json(STATUS_FILE, {}).get("waiting", []))
    keys = [k if k[0] in "pa" else f"p{k}" for k in keys if k]
    APPROVALS.parent.mkdir(exist_ok=True)
    with open(APPROVALS, "a") as f:
        f.write(json.dumps({"ts": iso(), "keys": keys, "by": os.environ.get("USER", "?")}) + "\n")
    print(f"approved {len(keys)}: {' '.join(keys) or '(nothing waiting)'}")
