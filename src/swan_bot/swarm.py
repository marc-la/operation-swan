"""Swarm: 20 like-and-repost accounts that back other Vote No posts. DRY-RUN BY DEFAULT (nothing written without
live=True). Spec and runbook: docs/04-technical/swarm.md. Run once per 5 min by deploy/swan-swarm.timer.

Each run:
  1. registration: at most one new swarm account, 4-9 min after the last, until SWARM_SIZE exist. Before each one
     it counts the team's live accounts (bot + swarm files here, and the Mongo `accounts` collection) and stops at
     MAX_ACTIVE, so it never takes a slot the platform would refuse;
  2. scan: Latest and Trending from the bot's data/latest_snapshot.json (the bot is the team's one feed reader,
     feeds.py; the feeds share 10 reads/min), plus the three No tags (#keepkingstoniaopen, #voteno,
     #choicenotcoercion) through feeds.read (tag_posts is its own 10/min route), last 24 h;
  3. like: every new qualifying post gets 2-5 swarm likes (each a view, then a like), at most SWARM_LIKES_PER_SCAN
     per run, stopping while the team's like budget is below SWARM_LIKE_RESERVE (the amplifier's share);
  4. repost: up to SWARM_REPOSTS_PER_SCAN of the best top-level posts, only while the team's write budget (shared
     with the bot's replies) has >= SWARM_WRITE_RESERVE left, never two within SWARM_REPOST_GAP_S.

"Supports No" uses targeting.stance plus the tags: a post qualifies if its stance is "no", or it carries one of
the No tags and its stance isn't "yes". Anything with a firm-Yes marker (#voteyes, "mandate now", ...) is skipped,
which also drops Yes posts that mock a No tag. Our own team's posts count (the swarm never likes its own posts).

Passwords and tokens stay in secrets/swarm_accounts.json (never Mongo; scripts/swan_sync_mongo.py strips them).
Every registration, view, like and repost goes to logs/swan_actions.jsonl with username, account id, role
"swarm" and owner (CLAUDE.md rule 6). Touch SWARM_OFF in the repo root to pause.
"""
import datetime as dt
import random
import secrets
import sys
import time

import capturethenarrative as ctn

from . import config, feeds
from .amplify import booster_identity
from .bot import load_json, log, now_iso, save_json
from .targeting import FIRM_YES, stance

TAG_WORDS = tuple("#" + t for t in config.SWARM_TAGS.values())


def age_h(post):
    created = dt.datetime.fromisoformat(post["created_at"].replace("Z", "+00:00"))
    return (dt.datetime.now(dt.timezone.utc) - created).total_seconds() / 3600


def supports_no(post, from_tag=False):
    """Does this post argue for Vote No? Reposts never qualify (we act on originals)."""
    if post.get("kind") == "repost":
        return False
    body = post.get("body") or ""
    if FIRM_YES.search(body):
        return False
    s = stance(body)
    if s == "no":
        return True
    tagged = from_tag or any(t in body.lower() for t in TAG_WORDS)
    return tagged and s != "yes" and bool(body.strip())


def score(c):
    """Repost priority: in Trending, carried by several No tags, fresh, already liked, written by a citizen."""
    p = c["post"]
    s = 2.0 * max(0.0, 1 - age_h(p) / config.SWARM_MAX_AGE_H) + 0.7 * len(c["tags"])
    if c.get("rank") is not None:
        s += 3.0 + 2.0 * (1 - c["rank"] / 50)
    s += min(3.0, (p.get("like_count") or p.get("likes") or 0) / 10)
    if config.OFFICIAL_MAX_ID < p.get("author_id", 0) <= config.CITIZEN_MAX_ID:
        s += 1.0
    return s


SNAPSHOT_MAX_AGE_S = 20 * 60        # an older snapshot means the bot isn't reading: skip feeds, keep the tags


def scan(social, say=print, snapshot_path=None):
    """{post_id: {"post", "tags", "rank"}} for qualifying posts. Reads: 1 tag_posts per tag (feeds from the
    bot's snapshot, never live)."""
    found = {}

    def add(p, tag=None, rank=None):
        if not p or not p.get("post_id") or age_h(p) > config.SWARM_MAX_AGE_H or not supports_no(p, tag is not None):
            return
        c = found.setdefault(p["post_id"], dict(post=p, tags=set(), rank=None))
        if tag:
            c["tags"].add(tag)
        if rank is not None:
            c["rank"] = rank
    snap = feeds.read_snapshot(snapshot_path, max_age_s=SNAPSHOT_MAX_AGE_S)
    if snap is None:
        say("no fresh latest_snapshot.json (is swan-bot running?): tags only this run")
    else:
        for i, p in enumerate((snap.get("trending") or {}).get("posts") or []):
            add(p, rank=i)
        for p in snap.get("posts") or []:
            add(p)
    for tag_id, word in config.SWARM_TAGS.items():
        try:
            for p in feeds.read(social, "tag_posts", "swan-swarm", tag_id=tag_id, limit=50, sort="recent"):
                add(p, tag=word)
        except ctn.APIError as e:
            say(f"tag {word} ({tag_id}): {e.status} {e.message}")
    return found


class Swarm:
    def __init__(self, social, live, owner=config.SWARM_OWNER, code=None, say=print, sleep=time.sleep):
        self.social, self.live, self.owner, self.code, self.say, self.sleep = social, live, owner, code, say, sleep
        self.records = load_json(config.SWARM_ACCOUNTS_FILE, [])
        self.state = load_json(config.SWARM_STATE_FILE, {})
        for key, default in (("liked", {}), ("reposted", {}), ("planned", {}), ("dead_posts", []),
                             ("next_register", 0.0), ("last_repost", 0.0)):
            self.state.setdefault(key, default)
        self.open = {}
        self.done = {"like": 0, "repost": 0}
        if not live and not self.records:            # dry run before any registration: pretend the swarm exists
            self.records = [dict(role="swarm", username=f"(dry)swarm{i:02d}", account_id=None, status="active")
                            for i in range(config.SWARM_SIZE)]

    # ---- bookkeeping --------------------------------------------------------------------------
    def save(self):
        if not self.live:
            return
        save_json(config.SWARM_ACCOUNTS_FILE, self.records, private=True)
        st = self.state
        st["liked"] = {u: ids[-2000:] for u, ids in st["liked"].items()}
        st["dead_posts"] = st["dead_posts"][-2000:]
        cutoff = time.time() - 3 * 86400
        st["planned"] = {k: v for k, v in st["planned"].items() if v > cutoff}
        save_json(config.SWARM_STATE_FILE, st)

    def active(self):
        return [r for r in self.records if r.get("status", "active") == "active"]

    def record(self, rec):
        if rec["act"] in self.done:
            self.done[rec["act"]] += 1
        log({**rec, "role": "swarm", "owner": self.owner, "live": self.live})

    # ---- registration -------------------------------------------------------------------------
    def team_active(self):
        """Live count of the team's active accounts: the larger of this machine's files and Mongo."""
        bot = [r for r in load_json(config.ACCOUNTS_FILE, []) if r.get("status", "active") == "active"]
        local = len(bot) + len(self.active())
        try:
            sys.path.insert(0, str(config.ROOT / "scripts"))
            from swan_sync_mongo import connect
            remote = connect().accounts.count_documents({"status": "active"})
        except (Exception, SystemExit) as e:         # Mongo down or no team code: the local count still holds
            self.say(f"mongo count unavailable ({type(e).__name__}); using local count {local}")
            remote = 0
        return max(local, remote)

    def maybe_register(self):
        if len(self.records) >= config.SWARM_SIZE or time.time() < self.state["next_register"]:
            return None
        n = self.team_active()
        if n >= config.MAX_ACTIVE:
            self.say(f"register: team has {n} active accounts (cap {config.MAX_ACTIVE}); swarm stays at "
                     f"{len(self.records)}")
            self.state["next_register"] = time.time() + 1800
            return None
        taken = {r["username"] for r in self.records} | {r["username"] for r in load_json(config.ACCOUNTS_FILE, [])}
        username, name = booster_identity(taken)
        self.state["next_register"] = time.time() + random.uniform(*config.SWARM_REGISTER_GAP_S)
        if not self.live:
            self.say(f"[dry] would register {username} ({name}) for {self.owner}: team active {n}, "
                     f"swarm {len(self.records)}/{config.SWARM_SIZE}")
            return username
        password = secrets.token_urlsafe(18)
        try:
            acc = self.social.register(username, password, self.code, display_name=name)
        except ctn.APIError as e:
            self.say(f"register {username}: {e.status} {e.message}")
            if e.status == 403:                      # allowance used up (or not cleared): back off an hour
                self.state["next_register"] = time.time() + 3600
            return None
        rec = dict(role="swarm", persona=None, username=username, display_name=name, password=password,
                   token=acc.token, account_id=acc.account_id, owner=self.owner, created=now_iso(), status="active")
        self.records.append(rec)
        self.open[username] = acc
        self.save()
        self.record({"act": "register", "username": username, "account_id": acc.account_id})
        self.say(f"registered {username} (id {acc.account_id}) for {self.owner}: swarm "
                 f"{len(self.records)}/{config.SWARM_SIZE}")
        return username

    # ---- sessions -----------------------------------------------------------------------------
    def session(self, rec):
        acc = self.open.get(rec["username"])
        if acc is None:
            try:
                acc = self.social.account_from_token(rec["token"])
            except ctn.APIError as e:
                if e.status != 401:
                    raise
                acc = self.social.login(rec["username"], rec["password"])
                rec["token"] = acc.token
            self.open[rec["username"]] = acc
        return acc

    def mark_error(self, rec, e):
        if e.status == 403 and "suspend" in (e.message or "").lower():
            rec["status"] = "suspended"
            self.record({"act": "suspended", "username": rec["username"], "account_id": rec.get("account_id")})

    # ---- plan ---------------------------------------------------------------------------------
    def plan_likes(self, found):
        """[(post_id, username)] for posts not planned before, best first, capped per run."""
        plan, st = [], self.state
        accounts = self.active()
        for pid, c in sorted(found.items(), key=lambda kv: -score(kv[1])):
            key = str(pid)
            if key in st["planned"] or pid in st["dead_posts"]:
                continue
            pool = [r for r in accounts if r.get("account_id") != c["post"].get("author_id")
                    and pid not in st["liked"].get(r["username"], [])]
            k = min(len(pool), random.randint(*config.SWARM_LIKERS_PER_POST))
            if k == 0:
                continue
            if len(plan) + k > config.SWARM_LIKES_PER_SCAN:
                break                                # the rest waits for the next run
            plan += [(pid, r["username"]) for r in random.sample(pool, k)]
            st["planned"][key] = time.time()
        random.shuffle(plan)                         # interleave posts and accounts
        return plan

    def plan_reposts(self, found):
        st, accounts, out = self.state, self.active(), []
        if config.SWARM_REPOSTS_PER_SCAN <= 0:        # 25 Oct: reposts off (todo/46)
            return out
        for pid, c in sorted(found.items(), key=lambda kv: -score(kv[1])):
            p = c["post"]
            if str(pid) in st["reposted"] or pid in st["dead_posts"] or p.get("reply_to_post_id"):
                continue
            used = {u for _, u in out}
            pool = [r for r in accounts if r.get("account_id") != p.get("author_id") and r["username"] not in used]
            if not pool:
                continue
            out.append((pid, random.choice(pool)["username"]))
            if len(out) >= config.SWARM_REPOSTS_PER_SCAN:
                break
        return out

    # ---- act ----------------------------------------------------------------------------------
    def rec_of(self, username):
        return next((r for r in self.active() if r["username"] == username), None)

    def like(self, pid, username, author):
        rec = self.rec_of(username)
        if not rec:
            return True
        self.state["liked"].setdefault(username, []).append(pid)   # never retry: failed requests have a small budget
        if not self.live:
            self.say(f"[dry] like #{pid} by {username}")
            self.done["like"] += 1
            return True
        try:
            acc = self.session(rec)
            acc.view(pid)
            acc.like(pid)
        except ctn.RateLimited:
            self.say("like budget exhausted (429): stopping likes this run")
            return False
        except ctn.APIError as e:
            self.say(f"like #{pid} by {username}: {e.status} {e.message}")
            if e.status in (404, 410):
                self.state["dead_posts"].append(pid)
            self.mark_error(rec, e)
            return True
        self.record({"act": "like", "target_post": pid, "target_author": author, "username": username,
                     "account_id": rec.get("account_id")})
        rl = acc.rate_limit
        if rl is not None and rl.remaining < config.SWARM_LIKE_RESERVE:
            self.say(f"team like budget at {rl.remaining}/{rl.limit}: leaving the rest to the amplifier")
            return False
        return True

    def repost(self, pid, username, author):
        rec = self.rec_of(username)
        if not rec:
            return True
        wait = self.state["last_repost"] + config.SWARM_REPOST_GAP_S - time.time()
        if wait > 0 and self.live:
            self.sleep(wait)
        self.state["reposted"][str(pid)] = username
        if not self.live:
            self.say(f"[dry] repost #{pid} by {username}")
            self.done["repost"] += 1
            return True
        try:
            acc = self.session(rec)
            rp = acc.repost(pid)
        except ctn.RateLimited:
            self.say("write budget exhausted (429): no more reposts this run")
            return False
        except ctn.APIError as e:
            self.say(f"repost #{pid} by {username}: {e.status} {e.message}")
            if e.status in (403, 404, 410):
                self.state["dead_posts"].append(pid)
            self.mark_error(rec, e)
            return True
        self.state["last_repost"] = time.time()
        self.record({"act": "repost", "post_id": rp.get("post_id"), "target_post": pid, "target_author": author,
                     "username": username, "account_id": rec.get("account_id")})
        rl = acc.rate_limit
        return rl is None or rl.remaining >= config.SWARM_WRITE_RESERVE

    def run_once(self, register=True):
        if config.SWARM_OFF_FILE.exists():
            self.say("SWARM_OFF present: paused")
            return {}
        if register:
            self.maybe_register()
        found = scan(self.social, self.say)
        likes, reposts = self.plan_likes(found), self.plan_reposts(found)
        self.say(f"{'LIVE' if self.live else 'DRY RUN'}: {len(found)} Vote No posts, {len(self.active())} swarm "
                 f"accounts, {len(likes)} likes and {len(reposts)} reposts planned")
        author = {pid: c["post"].get("author_id") for pid, c in found.items()}
        half = len(likes) // 2
        repost_q = list(reposts)
        liking = True
        for i, (pid, username) in enumerate(likes):
            if not liking:
                break
            if i == half and repost_q:               # first repost mid-run, the second at the end
                pid_r, user_r = repost_q.pop(0)
                if not self.repost(pid_r, user_r, author[pid_r]):
                    repost_q = []
            liking = self.like(pid, username, author[pid])
            if self.live:
                self.sleep(random.uniform(*config.SWARM_LIKE_GAP_S))
        for pid_r, user_r in repost_q:
            if not self.repost(pid_r, user_r, author[pid_r]):
                break
        self.save()
        summary = {"act": "swarm_scan", "found": len(found), "likes": self.done["like"], "reposts": self.done["repost"],
                   "accounts": len(self.active())}
        if self.live:
            log({**summary, "owner": self.owner})
        self.say(f"done: {summary['likes']} likes, {summary['reposts']} reposts")
        return summary
