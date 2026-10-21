"""The Blue loop: scan, rank, fill the pending slots greedily, read rulings back, publish status for the dashboard.

Why greedy on slots (docs/06-strategy/blue-reporting.md): the binding limits are the 25 pending reports and the 6 h
lock after any "genuine" ruling (about 1 in 10, so a full batch of 25 almost always ends in one). Points come from
refilling every free slot the moment we may, with the highest expected value first:
  post report    0.9 x (25 if we are first, else 5) x the team's daily rate (5 full, 5 half, then 10%)
  account report 15 x that rate, near-certain, no lock risk (the account already has a hidden post and 100+ actions)
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
SYDNEY = ZoneInfo("Australia/Sydney")

CAP = 25                      # pending reports per team (Discord, 20 Oct); account reports counted too, to be safe
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
TICK_S = 60
EVERY = dict(trending=10 * 60, latest=3 * 60, authors=3 * 60, rulings=10 * 60, harvest=30 * 60, ours=10 * 60,
             calibrate=15 * 60)
WATCH_AUTHORS = 40            # ring authors whose timelines we poll for fresh posts
AUDITS_PER_TICK = 15
HARVEST_CHECKS = 40           # unreported ring posts re-checked for a hide per harvest round
FEED_RESERVE = 4              # leave the bot this many feed calls of the team's 10/min


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
                         lock_until=0, lock_why=None, last_error=None, pf_scale=1.0, first=None).items():
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
        self.ours = {r["account_id"] for r in records if r.get("account_id")}
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
        if rl and rl.remaining < FEED_RESERVE:
            self.feed_hold = now() + rl.reset          # leave the rest of the minute to the bot
        return page

    def note(self, post, source):
        """Remember a post worth auditing: a team author, not ours, not a reply on one of our posts."""
        if not ev.is_team(post["author_id"], self.ours) or post.get("repost_of_post_id"):
            return
        pid = str(post["post_id"])
        p = self.s["posts"].setdefault(pid, dict(post=post, first_seen=now(), audits=0, trending=False))
        p["known"] = str(post["author_id"]) in self.s["author_ring"]      # its author ran a confirmed ring before
        if source == "trending":
            p["trending"] = True

    def scan(self):
        if self.due("ours"):
            self.load_ours()
        if self.due("trending"):
            for post in self.feed(self.social.feed_trending)[:35]:
                self.note(post, "trending")
        if self.due("latest"):
            for post in self.feed(self.social.feed_latest):
                if not post.get("reply_to_post_id"):
                    self.note(post, "latest")
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
            if age > MAX_POST_AGE_H * 3600 or p.get("gone") or i >= len(sched) or (i and p.get("classes")):
                continue
            if not (age >= sched[i] * 60 or (i == 0 and p["trending"])) or (i and age > 3 * 3600):
                continue
            try:
                a = ev.audit(self.social, p["post"], self.ours)
            except ctn.APIError as e:
                if e.status == 404:
                    p["gone"] = True
                continue
            done += 1
            p["audits"] += 1
            prior = self.s["author_ring"].get(str(a["author"]))
            if prior and prior["post"] != int(pid):
                a["overlap"], a["prior_post"] = len(ev.members(a) & set(prior["members"])), prior["post"]
            p["audit"], p["classes"] = a, ev.classes(a)
            if p["classes"]:
                p["label"] = ev.label_for(a, self.s["labels"])
                self.s["authors"][str(a["author"])] = t
                for r in a["reply_posts"]:
                    self.s["labels"].setdefault(str(r["author"]), p["label"])
            if {"like_ring", "reply_ring"} & set(p["classes"]):          # a confirmed ring: remember who ran it
                self.s["author_ring"][str(a["author"])] = dict(post=int(pid), members=sorted(ev.members(a)), t=t)

    def prune(self):
        cut = now() - 36 * 3600
        self.s["posts"] = {k: v for k, v in self.s["posts"].items() if v["first_seen"] >= cut}
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
                                    base=(r_age, False, 0.95)))
                    if len(seen) >= 3:
                        break
        for aid, h in self.s["harvest"].items():
            if h.get("ready") and f"a{aid}" not in reported:
                out.append(dict(key=f"a{aid}", kind="account", target=int(aid), author=int(aid),
                                label=self.s["labels"].get(aid, f"c{aid}"), classes=["hidden_post"],
                                detail=ev.account_detail(int(aid), h["hidden_post"], h["actions"], h["ring_posts"]),
                                ring=None, ring_why=f"post #{h['hidden_post']} already hidden, {h['actions']}+ actions"))
        return out

    def ranked(self):
        """Greedy order: the best expected value first, the team's count updated after every pick."""
        cands, counts, picked = self.candidates(), self.counts_today(), []
        while cands and len(picked) < 2 * CAP:
            for c in cands:
                n = counts.get(c["label"], 0)
                c["n_today"] = n
                c["ev"] = round(ev.account_ev(n) if c["kind"] == "account" else
                                ev.post_ev(*c["base"], n=n, scale=self.s["pf_scale"]), 1)
            best = max(cands, key=lambda c: c["ev"])
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

    def fill(self, ranked, mode):
        if mode == "off" or self.locked():
            return
        free = CAP - len(self.pending())
        ok = self.approved()
        accounts = [c for c in ranked if c["kind"] == "account"]
        if len(accounts) >= free:            # enough account leads for every slot: no post report, so no lock risk
            ranked = accounts
        for c in ranked:
            if free <= 0 or self.locked():
                break
            if c["kind"] == "post" and c.get("age_min", 0) > FRESH_MIN and free <= FRESH_RESERVE:
                continue                      # keep the last slots for fresh ring posts, where we can be first
            if mode == "approve" and c["kind"] == "post" and c["key"] not in ok:
                continue
            if self.file(c):
                free -= 1

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
        self.s["reports"][c["key"]] = dict(kind=c["kind"], target=c["target"], author=c["author"], label=c["label"],
                                           filed=t, status="pending", ev=c["ev"], detail=c["detail"], pf=pf)
        self.log({"act": "report", "key": c["key"], "kind": c["kind"], "target": c["target"], "author": c["author"],
                  "label": c["label"], "classes": c["classes"], "ev": c["ev"], "age_min": c.get("age_min"),
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
            self.s["lock_why"] = "reporter account suspended"
            self.alert("reporter", f"the reporter account is suspended ({msg[:120]}). Blue stopped; a person decides.")
            return False
        # anything else on a report (403 and the like): most likely the 6 h reporting suspension or the pending cap
        self.s["lock_until"] = max(self.s["lock_until"], now() + LOCK_PROBE_S)
        self.s["lock_why"] = f"refused: {e.status} {msg[:120]}"
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
                until = r["filed"] + RULE_S + LOCK_S
                if until > self.s["lock_until"]:
                    self.s["lock_until"], self.s["lock_why"] = until, f"#{r['target']} ruled genuine"
                    self.log({"act": "lock", "until": iso(until), "why": self.s["lock_why"]})

    def ruled(self, key, r, outcome, at):
        r.update(status=outcome, ruled=at, ruled_day=sydney_day(at))
        self.log({"act": "ruling", "key": key, "outcome": outcome, "label": r["label"],
                  "hours": round((at - r["filed"]) / 3600, 1)})

    # ---- account harvest: authors with a moderator-hidden post and 100+ actions ----
    def harvest(self):
        t, checks = now(), 0
        reported = {r["target"] for r in self.s["reports"].values() if r["kind"] == "post"}
        for pid, p in self.s["posts"].items():            # ring posts someone else got hidden
            if checks >= HARVEST_CHECKS:
                break
            if not p.get("classes") or p.get("gone") or int(pid) in reported:
                continue
            checks += 1
            try:
                self.social.get_post(int(pid))
            except ctn.APIError as e:
                if e.status == 404:
                    p["gone"] = True
                    self.s["harvest"].setdefault(str(p["audit"]["author"]), dict(hidden_post=int(pid), checked=0))
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
            h["ring_posts"] = [int(k) for k, v in self.s["posts"].items()
                               if v.get("classes") and int(aid) in [v["audit"]["author"], *v["audit"]["liker_ids"]]][:3]
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
        write_json(self.status_file, dict(
            ts=iso(), live=self.live, mode=mode, why=why, reporter=self.reporter_name,
            locked_until=iso(self.s["lock_until"]) if self.locked() else None, lock_why=self.s["lock_why"],
            pending=len(pend), cap=CAP,
            next_ruling=iso(pend[0]["filed"] + RULE_S) if pend else None,
            today=dict(filed=len(filed_today), hidden=sum(r["status"] == "hidden" for r in ruled_today),
                       genuine=sum(r["status"] == "genuine" for r in ruled_today),
                       accounts=sum(r["status"] == "ruled" for r in ruled_today),
                       refused=sum(r["status"] == "refused" and sydney_day(r["filed"]) == today for r in reps),
                       teams=len({r["label"] for r in filed_today})),
            precision=self.precision(), ready=len(ranked), first=self.s["first"], pf_scale=self.s["pf_scale"],
            waiting=[c["key"] for c in waiting], rings=rings(waiting),
            queued=len([k for k in ok if k not in self.s["reports"]]),       # approved, not filed yet
            ledger=[dict(key=k, target=r["target"], kind=r["kind"], team=r["label"], status=r["status"],
                         at=iso(r["filed"] + RULE_S if r["status"] == "pending" else r.get("ruled") or r["filed"]))
                    for k, r in sorted(self.s["reports"].items(), key=lambda kv: kv[1]["filed"])
                    if r["status"] == "pending" or sydney_day(r["filed"]) == today],
            last_error=self.s["last_error"], last_error_ts=self.s.get("last_error_ts")))

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
