"""The Blue loop: scan, rank, fill the pending slots greedily, read rulings back, publish status for the dashboard.

Why greedy on slots (docs/06-strategy/blue-reporting.md): the binding limits are the 30 pending reports and the 6 h
lock after any "genuine" ruling (about 1 in 10 for a like ring alone). Points come from refilling every free slot
the moment we may, with the highest expected value first:
  post report    (1 - P(genuine)) x (25 if we are first, else 5) x the team's daily rate (5 full, 5 half, then 10%)
  account report 15 x that rate, near-certain, no lock risk (the account already has a hidden post and 100+ actions)
The no-lock mode (todo/28, the default): account reports always first; post reports only at P(genuine) <= 2% (reply
rings), worth the lock they risk, and within a daily risk budget (policy(), settable in .env on the box).
Being first pays 25 against 5 (by order, not time; nobody can see others' reports), so we push the odds:
  - ring authors' timelines are polled every 3 min, and a known ring author's new post is audited at 4, 12, 45 min;
    an early ring (most of its likers ran that author's earlier ring) qualifies before the ring is big
  - the last FRESH_RESERVE free slots are kept for posts under an hour old
  - the portal log says which awards paid as first; that share against our prediction scales every estimate

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
from . import evidence as ev

STATE_FILE = config.DATA / "blue_state.json"
STATUS_FILE = config.DATA / "blue_status.json"        # the dashboard reads this (field by field)
APPROVALS = config.DATA / "blue_approved.jsonl"        # scripts/blue.sh appends here
SESSION_FILE = config.SECRETS / "blue_session.json"   # the reporter's token (never logged)
REPORTS_LOG = config.LOGS / "blue_reports.jsonl"
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
FRESH_MIN = 60                # a post report older than this is "stale" (the first-reporter odds drop)...
FRESH_RESERVE = 5             # ...and may not take the last this-many free slots: they wait for fresh ring posts
CALIBRATE_AFTER = 8           # paid post awards in the portal log before we trust our first-reporter share
PORTAL_FILE = config.DATA / "portal.json"           # swan_dash/portal.py writes the points log here
# The bot is the team's Latest reader (todo/21): it writes its pages here, {"read_at", "posts", "trending": {...}}.
# The team's feed budget is 10/min, so swan-blue reads this while it's fresh and calls the feed only as a fallback.
SNAPSHOT_FILE = config.DATA / "latest_snapshot.json"
SNAPSHOT_MAX_AGE_S = 10 * 60
PLAIN_KEEP_S = 3 * 3600       # a post with no ring evidence is dropped this long after posting (its audits are done)
TICK_S = 60
EVERY = dict(trending=10 * 60, latest=3 * 60, authors=3 * 60, rulings=10 * 60, harvest=30 * 60, ours=10 * 60,
             calibrate=15 * 60)
WATCH_AUTHORS = 40            # ring authors whose timelines we poll for fresh posts
AUDITS_PER_TICK = 15
HARVEST_CHECKS = 80           # ring posts and ring replies checked for someone else's hide per harvest round
HIDE_RECHECK_S = 2 * 3600     # a post checked for a hide isn't checked again for this long
FEED_RESERVE = 4              # leave the bot this many feed calls of the team's 10/min
# todo/28, the no-lock mode (the default): a genuine ruling locks ALL our reporting for 6 h, and the moderator's error,
# not our evidence, sets the floor. Account reports always go first (a dismissed one can't lock us). A post report
# files only when
#  - its P(genuine) (evidence.p_genuine) is at most BLUE_POST_PG_MAX: 2% lets reply rings through (0 genuine of 28
#    to 22 Oct) and keeps every like ring out (2 of 19);
#  - its expected value pays for the lock it risks: ev >= pg x LOCK_COST (a 10%-rate report never does); and
#  - the risk bucket holds its P(genuine): it refills BLUE_PG_PER_DAY a day (expected genuine rulings a day; 0.4 is
#    about 3 a week, todo/28's bar) and holds a quarter of that, so post reports spread over the day.
# BLUE_POST_PG_MAX and BLUE_PG_PER_DAY can be set in .env on the box (blue-reporting §8 has what each costs).
PG_MAX = 0.02
PG_PER_DAY = 0.4
PG_BURST_DAYS = 0.25          # the bucket holds this many days of PG_PER_DAY
LOCK_COST = 300               # points a 6 h lock costs: a quarter of a ~1,200-point Blue day (§2)
# todo/26, more teams at full rate: while a cluster is under its 5 full-rate awards today, each award already counted
# against it lowers its next report's rank by this share, so new clusters go first and fresh ring posts of the busy
# ones still find a full-rate award later in the day
SPREAD = 0.04
# todo/26, wider discovery from what the bot already read (data/latest_snapshot.json; never an extra feed read): a
# post that collects this many team replies or reposts inside the snapshot gets (re)audited...
WIDEN_MIN_ACTORS = 4
WIDEN_LOOKUPS = 8             # ...unknown ones looked up with get_post (its own 300/min route) per Latest pass
WIDEN_RECHECK_S = 2 * 3600    # a root looked up (a citizen's post, say) isn't looked up again for this long
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


def write_json(path, obj, private=False):
    path.parent.mkdir(exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=1))
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
        self.ours = {r["account_id"] for r in records + swarm if r.get("account_id")}
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

    # ---- the ledger ----
    def pending(self):
        return {k: r for k, r in self.s["reports"].items() if r["status"] == "pending"}

    def counts_today(self):
        """{team label: awards on the Sydney day a report filed now would be ruled} (paid + still pending)."""
        day, out = sydney_day(now() + RULE_S), {}
        for r in self.s["reports"].values():
            if (r["status"] in ("hidden", "ruled") and r.get("ruled_day") == day) or \
                    (r["status"] == "pending" and sydney_day(r["filed"] + RULE_S) == day):
                out[r["label"]] = out.get(r["label"], 0) + 1
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

    # ---- candidates, ranked by expected value ----
    def candidates(self):
        t, out = now(), []
        reported = set(self.s["reports"])
        for pid, p in self.s["posts"].items():
            a, cls = p.get("audit"), p.get("classes")
            if not cls or p.get("gone") or a["author"] in self.ours:
                continue
            age_min = (t - ev.ts(a["created"])) / 60
            if age_min > MAX_POST_AGE_H * 60:
                continue
            strong = 1.0 if len(cls) >= 2 else 0.95
            ring_why = ev.brief(a)
            if f"p{pid}" not in reported:
                out.append(dict(key=f"p{pid}", kind="post", target=int(pid), author=a["author"], label=p["label"],
                                age_min=round(age_min), trending=p["trending"], classes=cls,
                                detail=ev.post_detail(a), ring=int(pid), ring_why=ring_why,
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
                                    label=p["label"], age_min=round(r_age), trending=False, classes=["reply_ring"],
                                    detail=ev.reply_detail(r, a), ring=int(pid), ring_why=ring_why,
                                    pg=ev.p_genuine(a, ["reply_ring"], str(r["author"]) in self.s["harvest"]),
                                    base=(r_age, False, 0.95)))
                    if len(seen) >= 3:
                        break
        for aid, h in self.s["harvest"].items():
            if h.get("ready") and f"a{aid}" not in reported:
                out.append(dict(key=f"a{aid}", kind="account", target=int(aid), author=int(aid),
                                label=self.s["labels"].get(aid, f"c{aid}"), classes=["hidden_post"],
                                detail=ev.account_detail(int(aid), h["hidden_post"], h["actions"], h["ring_posts"]),
                                pg=0.0, ring=None, ring_why=f"post #{h['hidden_post']} already hidden, {h['actions']}+ actions"))
        return out

    def ranked(self):
        """Greedy order: the best expected value first, the team's count updated after every pick. Expected value
        counts P(genuine), and a cluster that already has awards today ranks a little lower (SPREAD) while it's still
        at full rate."""
        cands, counts, picked = self.candidates(), self.counts_today(), []
        while cands and len(picked) < 2 * CAP:
            for c in cands:
                n = counts.get(c["label"], 0)
                c["n_today"] = n
                c["ev"] = round(ev.account_ev(n) if c["kind"] == "account" else
                                ev.post_ev(*c["base"], n=n, scale=self.s["pf_scale"], pg=c["pg"]), 1)
                c["rank"] = c["ev"] * (1 - SPREAD * n if n < 5 else 1)
            best = max(cands, key=lambda c: c["rank"])
            if best["ev"] < MIN_EV:
                break
            cands.remove(best)
            picked.append(best)
            counts[best["label"]] = counts.get(best["label"], 0) + 1
        return picked

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
        if c["kind"] == "post":
            self.bucket()["level"] -= c.get("pg", ev.PG_BASE)

    def fileable(self, ranked):
        """What fill() may file, in order: account leads first (a dismissed account report pays nothing but can't
        lock us), then the post reports the no-lock mode allows (P(genuine) at most BLUE_POST_PG_MAX, worth the
        lock they risk). The risk bucket is fill()'s to check."""
        pg_max = policy()["pg_max"]
        accounts = [c for c in ranked if c["kind"] == "account"]
        posts = [c for c in ranked if c["kind"] == "post" and c.get("pg", ev.PG_BASE) <= pg_max
                 and c.get("ev", 0) >= c.get("pg", ev.PG_BASE) * LOCK_COST]
        return accounts, posts

    def fill(self, ranked, mode):
        """Fill the free slots. Locked: nothing, except one report right after we detect a genuine ruling ourselves
        (lock_confirm): the platform's answer gives the exact end of its lock, which is often earlier than our
        estimate (a ruling comes sooner when other teams reported the post too)."""
        confirm = self.locked() and self.s.get("lock_src") == "estimate" and self.s.get("lock_confirm")
        if mode == "off" or (self.locked() and not confirm):
            return
        pend = self.pending()
        free = CAP - len(pend)
        post_room = CAP - ACCOUNT_SLOTS - sum(r["kind"] == "post" for r in pend.values())
        ok = self.approved()
        accounts, posts = self.fileable(ranked)
        ranked = accounts if len(accounts) >= free else accounts + posts   # enough account leads: no lock risk
        for c in ranked:
            if free <= 0 or (self.locked() and not confirm):
                break
            if c["kind"] == "post" and post_room <= 0:
                continue                      # the last slot is left to account reports
            if c["kind"] == "post" and self.bucket()["level"] < c.get("pg", ev.PG_BASE):
                continue                      # the day's lock risk is spent: accounts only until it refills
            if c["kind"] == "post" and c.get("age_min", 0) > FRESH_MIN and free <= FRESH_RESERVE:
                continue                      # keep the last slots for fresh ring posts, where we can be first
            if mode == "approve" and c["kind"] == "post" and c["key"] not in ok:
                continue
            if confirm:
                if self.file(c):              # taken: the platform's lock is over, ours was too long
                    free -= 1
                    self.spent(c)
                    post_room -= c["kind"] == "post"
                    self.unlock("the platform took a report")
                elif self.s["reports"].get(c["key"], {}).get("status") == "refused":
                    continue                  # refused for that target only (gone, say): the next one asks
                self.s["lock_confirm"] = confirm = False
                continue
            if self.file(c):
                free -= 1
                self.spent(c)
                post_room -= c["kind"] == "post"

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

    def file(self, c):
        acc = self.session()
        if acc is None:
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
                                           classes=c["classes"])
        self.log({"act": "report", "key": c["key"], "kind": c["kind"], "target": c["target"], "author": c["author"],
                  "label": c["label"], "classes": c["classes"], "ev": c["ev"], "pg": pg, "n_today": c.get("n_today"),
                  "age_min": c.get("age_min"),
                  "detail": c["detail"], "reporter": self.reporter_name, "owner": config.operator(),
                  "response": resp if isinstance(resp, dict) else None})
        self.save()
        rl = acc.rate_limit                          # pace from the server's budget (3/min per report route)
        if rl and rl.remaining <= 1:
            time.sleep(max(1.0, rl.reset / max(rl.limit, 1)))
        return True

    def refused(self, c, e):
        msg = (e.message or "")[:300]
        self.log({"act": "refused", "key": c["key"], "status": e.status, "message": msg})
        self.error(f"report refused: {e.status} {msg[:120]}")
        low = msg.lower()
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
                    self.s["harvest"].setdefault(str(r["author"]), dict(hidden_post=r["target"], checked=0))
                continue
            if t >= r["filed"] + RULE_S + RULE_GRACE_S:
                self.ruled(key, r, "genuine", r["filed"] + RULE_S)
                why = f"#{r['target']} ruled genuine"
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
        self.log({"act": "ruling", "key": key, "outcome": outcome, "label": r["label"],
                  "hours": round((at - r["filed"]) / 3600, 1)})

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
                out.append((self.s["hide_checks"].get(str(post_id), 0), -age, post_id, author, ring))
        return [x[2:] for x in sorted(out)]           # never checked first, then oldest (likeliest ruled by now)

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
                                                          ring=ring or post_id)
                    self.log({"act": "lead", "account": author, "hidden_post": post_id, "ring": ring or post_id})
        for aid, h in self.s["harvest"].items():
            if h.get("ready") or int(aid) in self.ours or t - h.get("checked", 0) < 2 * 3600:
                continue
            h["checked"] = t
            try:
                n = len(list(self.social.iterate(self.social.account_posts, int(aid), max_items=100)))
                if n < 100:
                    n += len(list(self.social.iterate(self.social.account_likes, int(aid), max_items=100 - n)))
            except ctn.APIError:
                continue
            h["actions"] = n
            h["ring_posts"] = [int(k) for k, v in self.s["posts"].items() if v.get("classes") and int(aid) in ev.members(
                v["audit"]) | {v["audit"]["author"]}][:3]
            h["ready"] = n >= 100

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
            locked_until=iso(self.s["lock_until"]) if self.locked() else None, lock_why=self.s["lock_why"],
            lock_src=self.s.get("lock_src") if self.locked() else None,
            pending=len(pend), cap=CAP,
            # todo/26, todo/28: what would file now (accounts, and posts the no-lock mode allows)
            ready_ok=len(accounts) + len(posts), ready_accounts=len(accounts),
            pg_max=pol["pg_max"], pg_check=self.pg_check(), pg_by_class=self.pg_by_class(),
            # todo/28: the risk bucket: expected genuine rulings post reports may still take on now, its refill a day
            risk=dict(level=round(self.bucket()["level"], 3), per_day=pol["per_day"],
                      cap=round(pol["per_day"] * PG_BURST_DAYS, 3),
                      posts_now=sum(1 for _ in self._affordable(posts))),
            clusters=dict(today=len(counts), full=sum(n < 5 for n in counts.values()),
                          ready=len({c["label"] for c in ranked}),
                          new=len({c["label"] for c in ranked if counts.get(c["label"], 0) == 0})),
            widen=self.s["widen"],
            next_ruling=iso(pend[0]["filed"] + RULE_S) if pend else None,
            today=dict(filed=len(filed_today), hidden=sum(r["status"] == "hidden" for r in ruled_today),
                       genuine=sum(r["status"] == "genuine" for r in ruled_today),
                       accounts=sum(r["status"] == "ruled" for r in ruled_today),
                       refused=sum(r["status"] == "refused" and sydney_day(r["filed"]) == today for r in reps),
                       teams=len({r["label"] for r in filed_today})),
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
        self.scan()
        if self.due("rulings"):
            self.rulings()
        if self.due("harvest"):
            self.harvest()
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
    """The no-lock mode's settings (todo/28), from .env on the box or the defaults above."""
    def num(key, default):
        try:
            return float(os.environ.get(key, default))
        except ValueError:
            return default
    return dict(pg_max=num("BLUE_POST_PG_MAX", PG_MAX), per_day=num("BLUE_PG_PER_DAY", PG_PER_DAY))


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
