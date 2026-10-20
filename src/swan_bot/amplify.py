"""Own-team amplification into Trending, built to look organic (todo/04-reach-amplification.md). Off unless --amplify.

Why: Trending ranks by recent likes, replies and reposts (a fit on 20 Oct: a repost weighs ~6-8 likes, a reply ~1,
the score drops ~2/h), and the top 35 needs ~50 like-equivalents in the first ~15 min. Our accounts can give that.

Roles: boosters only view and like (no posts, so nothing of theirs can be hidden or suspended under the published
rules); voices write. For each amplified voice post this schedules:
  - likes from a random subset of the other accounts awake at that time, on a front-loaded lognormal curve (median
    ~8 min, never in the first 45 s, tail to 2 h), each preceded by a view;
  - own-thread replies from other voices (one-liners, questions, a detail of their own, sometimes a pushback that the
    author answers) and reposts. These are writes: the bot's main loop sends them at its normal pace;
  - filler likes on other No and neutral posts, so ≥50% of every account's likes go to posts that aren't ours (the
    lockstep tell CopyCatch / like-farm studies look for);
  - measurement at +1 h and +6 h (views, citizen likes and replies), and follow-backs to citizens who liked it.
A bandit picks the level per post (heavy / light / none) from the measured reward.

Detectors this is built against (Blue teams and the moderator): Beutel et al. 2013 (CopyCatch: same users, same
targets, same time window), De Cristofaro et al. 2014 (like farms: all likes within ~2 h, likers that like nothing
else), Pacheco et al. 2021 / QUT coordination-network-toolkit (co-actions within 60 s), Chavoshi et al. 2016 (DeBot:
lag-correlated activity), and the ring tells we see on Legit Social (consecutive-id repliers, one reply a minute).
Nothing here hides anything from the organisers: every action is logged with account, role and owner.
Single-threaded: the bot calls tick() while it waits. tick() never raises.
"""
import collections
import datetime as dt
import math
import random
import re
import secrets
import time
from zoneinfo import ZoneInfo

import capturethenarrative as ctn

from . import config, content
from .targeting import FIRM_NO, FIRM_YES, REFERENDUM

NO_TAGS = re.compile(r"#(voteno|keepkingstoniaopen|choicenotcoercion|nomandate|protectchoice)\b", re.I)
YES_TAGS = re.compile(r"#(voteyes|protectkingstonia|yes2h2|yesforkingstonia)\b", re.I)
THREAD_MIX = ["one_liner", "question", "detail", "own_angle", "one_liner", "detail"]   # pushback is added separately

# ---- booster identities: plausible islanders, varied handle styles (no template family) ----
FIRST = ["Mele", "Tevita", "Losana", "Sefo", "Ana", "Malakai", "Kalo", "Vika", "Joeli", "Salote", "Noa", "Leilani",
         "Tama", "Hina", "Rosa", "Kim", "Aroha", "Wiremu", "Lose", "Pita", "Grace", "Liam", "Chloe", "Ethan", "Mia",
         "Sam", "Jess", "Toby", "Nadia", "Raj", "Mei", "Hugo", "Ella", "Kai", "Zara", "Owen", "Lucy", "Ari", "Niko",
         "Tess", "Fiona", "Marco", "Ivy", "Felix", "Sina", "Rua", "Paea", "Elena", "Jonah", "Tui"]
LAST = ["Taufa", "Vainikolo", "Fonua", "Havili", "Kupu", "Moala", "Latu", "Tonga", "Faleafa", "Pulu", "Ngata",
        "Walker", "Bennett", "Chen", "Nguyen", "Patel", "Murray", "Reid", "Hughes", "Fraser", "Lim", "Silva",
        "Tuilagi", "Afamasaga", "Kaufusi", "Morgan", "Brooks", "Kaur", "Ito", "Rossi", "Mataele", "Sopoaga",
        "Leota", "Harris", "Doyle", "Parker", "Vake", "Finau", "Tupou", "Kioa"]
HOBBY = ["sails", "reef", "bakes", "tides", "garden", "runs", "reads", "surf", "fishes", "ukulele", "netball",
         "kayak", "market", "lagoon", "coconut", "harbour"]


def booster_identity(taken=()):
    """(username, display_name) that reads like a real person and differs from the username."""
    for _ in range(50):
        f, l = random.choice(FIRST), random.choice(LAST)
        fl, ll = f.lower(), l.lower()
        n = random.randint(1, 99)
        style = random.randrange(7)
        user = [f"{fl}{ll}", f"{fl}_{ll[0]}{n}", f"{fl}.{ll}", f"{fl}{random.randint(68, 99) if n % 2 else n}",
                f"{ll}_{fl[0]}", f"{fl}_{random.choice(HOBBY)}", f"{fl[0]}{ll}{n}"][style]
        user = re.sub(r"[^a-z0-9_.]", "", user)[:30]
        name = random.choice([f"{f} {l}", f"{f} {l}", f"{f} {l[0]}.", f, f"{f} {l}"])
        if user not in taken and user != name.lower():
            return user, name
    return f"{fl}{ll}{random.randint(100, 999)}", f"{f} {l}"


def delay_s(spec):
    median_min, sigma, lo, hi = spec
    return 60 * min(hi, max(lo, random.lognormvariate(math.log(median_min), sigma)))


def side_of(text):
    """'yes' | 'no' | 'neutral' | 'off' (not about the referendum) from keywords and tags."""
    t = text or ""
    if YES_TAGS.search(t) or FIRM_YES.search(t):
        return "yes"
    if NO_TAGS.search(t) or FIRM_NO.search(t):
        return "no"
    return "neutral" if REFERENDUM.search(t) else "off"


def is_citizen_id(account_id):
    return config.OFFICIAL_MAX_ID < (account_id or 0) <= config.CITIZEN_MAX_ID


class Amplifier:
    def __init__(self, social, accounts, state, live, log, targeter=None, code=None, owner=None, boosters=0,
                 save=lambda: None):
        self.social, self.accounts, self.state, self.live = social, accounts, state, live
        self.log, self.targeter, self.code, self.owner = log, targeter, code, owner
        self.boosters_target = max(0, min(boosters, config.MAX_BOOSTERS))
        self.save = save
        self.scale = 1.0 if live else 1 / 30                  # dry runs play the schedule 30x faster
        self.tz = ZoneInfo(config.LOCAL_TZ)
        self.like_times = collections.deque()
        self.like_hold_until = 0.0
        self.next_filler = 0.0
        self.next_save = 0.0
        self.fake_id = -1
        for key, default in (("amp_actions", []), ("amp_threads", []), ("amp_posts", {}), ("amp_liked", {}),
                             ("amp_stats", {}), ("amp_next_post", 0.0), ("amp_filler_debt", 0.0)):
            state.setdefault(key, default)
        created = [dt.datetime.fromisoformat(r["created"]).timestamp() for r in accounts.boosters() if r.get("created")]
        self.next_register = (max(created) + random.uniform(*config.BOOSTER_REGISTER_GAP_S)) if created and live else 0.0

    # ---- switches ----------------------------------------------------------------------------
    def paused(self):
        return config.AMP_OFF_FILE.exists()

    def asleep(self, rec, at=None):
        start = rec.get("sleep_start")
        if start is None or not config.SLEEP_H:
            return False
        local = dt.datetime.fromtimestamp(at or time.time(), self.tz)
        return (local.hour + local.minute / 60 - start) % 24 < config.SLEEP_H

    # ---- boosters ----------------------------------------------------------------------------
    def maybe_register_booster(self):
        acc = self.accounts
        if (len(acc.boosters()) >= self.boosters_target or len(acc.active()) >= config.MAX_ACTIVE
                or len([r for r in acc.records if r.get("role") == "booster"]) >= config.MAX_BOOSTERS
                or time.time() < self.next_register):
            return
        taken = {r["username"] for r in acc.records}
        username, name = booster_identity(taken)
        self.next_register = time.time() + random.uniform(*config.BOOSTER_REGISTER_GAP_S)
        rec = dict(role="booster", persona=None, username=username, display_name=name, owner=self.owner,
                   created=dt.datetime.now(dt.timezone.utc).isoformat(), status="active",
                   sleep_start=round(random.uniform(0, 24), 2), last_write=0, writes=0, followed=[])
        if not self.live:
            rec.update(username=f"(dry){username}", account_id=None)
            acc.records.append(rec)
            return
        password = secrets.token_urlsafe(18)
        try:
            a = self.social.register(username, password, self.code, display_name=name)
        except ctn.APIError as e:
            print("register booster:", e.status, e.message)
            self.next_register = time.time() + 120
            return
        rec.update(password=password, token=a.token, account_id=a.account_id)
        acc.records.append(rec)
        acc.open[username] = a
        acc.save()
        self.log({"act": "register", "role": "booster", "username": username, "account_id": a.account_id,
                  "owner": self.owner})
        print(f"registered booster {username} (id {a.account_id}) for {self.owner}")

    # ---- level choice (bandit) -------------------------------------------------------------------
    def choose_level(self):
        stats = self.state["amp_stats"]
        if any(stats.get(lv, [0, 0])[0] < 4 for lv in config.AMP_LEVELS) or random.random() < config.AMP_EXPLORE:
            levels = list(config.AMP_PRIOR)
            return random.choices(levels, weights=[config.AMP_PRIOR[lv] for lv in levels])[0]
        return max(config.AMP_LEVELS, key=lambda lv: stats[lv][1] / stats[lv][0])

    def amp_post_due(self):
        return not self.paused() and time.time() >= self.state["amp_next_post"]

    # ---- after a voice post goes out ---------------------------------------------------------------
    def on_post(self, post_id, rec, text, frame, level):
        """Schedule likes, views, thread replies and reposts for one of our new posts."""
        t = time.time()
        self.state["amp_next_post"] = t + random.uniform(*config.AMP_POST_GAP_S) * self.scale
        if post_id is None:                                  # dry run: a fake id so the schedule can be printed
            post_id, self.fake_id = self.fake_id, self.fake_id - 1
        spec = config.AMP_LEVELS[level]
        self.state["amp_posts"][str(post_id)] = dict(t=t, level=level, author=rec["username"],
                                                     persona=rec.get("persona"), frame=frame, own_views=0,
                                                     measured=[], best_rank=None, likes=0, text=text[:600])
        likes = self.plan_likes(post_id, rec, random.randint(*spec["likes"]), t)
        voices = [r for r in self.accounts.voices() if r["persona"] != rec["persona"]]
        n_rep = min(random.randint(*spec["replies"]), len(voices))
        styles = random.sample(THREAD_MIX, k=min(n_rep, len(THREAD_MIX)))
        if n_rep and random.random() < config.PUSHBACK_SHARE:
            styles[-1] = "pushback"
        threads = [dict(kind="thread", post_id=post_id, due=t + delay_s(config.THREAD_DELAY) * self.scale, style=s,
                        author=rec["persona"], frame=frame) for s in styles]
        threads += [dict(kind="repost", post_id=post_id, due=t + delay_s(config.REPOST_DELAY) * self.scale,
                         author=rec["persona"])
                    for _ in range(min(random.randint(*spec["reposts"]), len(voices)))]
        self.state["amp_threads"] += threads
        self.log({"act": "amp_plan", "live": self.live, "post_id": post_id, "level": level,
                  "username": rec["username"], "likes": len(likes),
                  "replies": [s for s in styles], "reposts": sum(th["kind"] == "repost" for th in threads)})
        print(f"  amplify #{post_id} [{level}]: {len(likes)} likes over "
              f"{(max([a['due'] for a in likes], default=t) - t) / 60:.0f} min, "
              f"{n_rep} thread replies {styles}, {sum(th['kind'] == 'repost' for th in threads)} reposts")
        return likes

    def plan_likes(self, post_id, author_rec, n, t):
        pool = [r for r in self.accounts.active() if r["username"] != author_rec["username"]]
        random.shuffle(pool)
        plan = []
        for r in pool:
            if len(plan) >= n:
                break
            due = t + delay_s(config.LIKE_DELAY) * self.scale
            if self.asleep(r, due):
                continue
            plan.append(dict(kind="like", post_id=post_id, username=r["username"], due=due, own=True))
        self.state["amp_actions"] += plan
        return plan

    # ---- writes the main loop sends (thread replies, author answers, reposts) ----------------------
    def next_write_job(self):
        """A due thread job for the main loop to draft/send, or None. Drops jobs >60 min overdue."""
        if self.paused():
            return None
        t = time.time()
        threads = self.state["amp_threads"]
        threads[:] = [th for th in threads if t - th["due"] < 3600]
        for th in sorted((th for th in threads if th["due"] <= t), key=lambda th: th["due"]):
            done = self.state["amp_posts"].get(str(th["post_id"]), {}).setdefault("touched", [])
            if th["kind"] == "answer":
                rec = self.accounts.by_persona(th["author"])
                if not rec or rec.get("last_write", 0) + config.REPOST_MIN_GAP_S > t:
                    continue
            else:
                gap = config.REPOST_MIN_GAP_S if th["kind"] == "repost" else None
                frame = None if th["kind"] == "repost" else random.choice(
                    [f for f in content.FRAMES if f != th.get("frame")])
                rec = self.accounts.eligible(frame, exclude={th["author"], *done}, gap=gap)
                if not rec:
                    continue
                th["frame_for"] = frame
            threads.remove(th)
            meta = self.state["amp_posts"].get(str(th["post_id"]), {})
            if th["post_id"] < 0 or (th["kind"] == "answer" and th.get("parent") is None):    # dry run: nothing to fetch
                body = th.get("pushback") if th["kind"] == "answer" else meta.get("text")
                target = dict(post_id=th.get("parent") or th["post_id"], author_id=None, body=body or "(our post)")
            else:
                try:
                    target = self.social.get_post(th["parent"] if th["kind"] == "answer" else th["post_id"])
                except ctn.APIError as e:
                    if e.status in (403, 404, 410):                   # hidden or deleted: stop amplifying it
                        self.drop_post(th["post_id"], f"get_post {e.status}")
                    continue
            if th["kind"] != "answer":
                done.append(rec["persona"])
            job = dict(mode={"thread": "thread", "answer": "thread_answer", "repost": "repost"}[th["kind"]],
                       rec=rec, target=target, frame=th.get("frame_for") or th.get("frame") or
                       content.PERSONA_BY_KEY[rec["persona"]]["frames"][0], style=th.get("style"),
                       amp_post=th["post_id"], our_text=meta.get("text") or "")
            return job
        return None

    def on_thread_sent(self, job, reply_id, text):
        """After a thread reply: a pushback gets the author's answer a few minutes later."""
        if job["mode"] == "thread" and job.get("style") == "pushback":
            meta = self.state["amp_posts"].get(str(job["amp_post"]), {})
            self.state["amp_threads"].append(dict(
                kind="answer", post_id=job["amp_post"], parent=reply_id,
                due=time.time() + random.uniform(180, 720) * self.scale,
                author=meta.get("persona"), pushback=text))

    def drop_post(self, post_id, why):
        pid = post_id
        self.state["amp_actions"] = [a for a in self.state["amp_actions"] if a.get("post_id") != pid]
        self.state["amp_threads"] = [th for th in self.state["amp_threads"] if th["post_id"] != pid]
        self.log({"act": "amp_drop", "post_id": pid, "why": why})

    # ---- the tick: likes, views, filler, registration, measurement ---------------------------------
    def tick(self):
        try:
            self._tick()
        except Exception as e:                              # never take the writer down
            print("amplify tick:", type(e).__name__, str(e)[:160])
        if self.live and time.time() >= self.next_save:
            self.next_save = time.time() + 60
            self.save()

    def _tick(self):
        if self.paused():
            return
        if self.boosters_target:
            self.maybe_register_booster()
        t = time.time()
        while self.like_times and t - self.like_times[0] > 60:
            self.like_times.popleft()
        self.track_ranks()
        due = sorted((a for a in self.state["amp_actions"] if a["due"] <= t), key=lambda a: a["due"])
        for a in due:
            if not self.like_budget():
                break
            self.state["amp_actions"].remove(a)
            self.do_like(a)
        if self.state["amp_filler_debt"] >= 1 and t >= self.next_filler and self.like_budget():
            if self.do_filler():
                self.state["amp_filler_debt"] -= 1
            self.next_filler = t + random.uniform(8, 60)
        self.measure_due()

    def like_budget(self):
        return len(self.like_times) < config.LIKES_PER_MIN and time.time() >= self.like_hold_until

    def liked(self, username):
        return self.state["amp_liked"].setdefault(username, [])

    def do_like(self, a, filler=False):
        """View then like (the view first, as a reader would). Returns True if the like went through."""
        rec = next((r for r in self.accounts.active() if r["username"] == a["username"]), None)
        pid = a["post_id"]
        if not rec or pid in self.liked(rec["username"]):
            return False
        self.like_times.append(time.time())
        if not self.live or pid is None or pid < 0:
            self.liked(rec["username"]).append(pid)
            if not filler:
                self.state["amp_filler_debt"] += config.FILLER_RATIO
            self.log({"act": "like", "live": False, "post_id": pid, "username": rec["username"],
                      "role": rec.get("role", "voice"), "own": not filler})
            return True
        acc = self.accounts.session(rec)
        try:
            try:
                acc.view(pid)
                meta = self.state["amp_posts"].get(str(pid))
                if meta:
                    meta["own_views"] = meta.get("own_views", 0) + 1
                acc.like(pid)
            except ctn.APIError as e:
                if e.status != 401:
                    raise
                acc = self.accounts.relogin(rec)
                acc.like(pid)
        except ctn.RateLimited as e:
            self.like_hold_until = time.time() + (e.retry_after or 30)
            self.state["amp_actions"].append({**a, "due": self.like_hold_until + random.uniform(1, 20)})
            return False
        except ctn.APIError as e:
            print(f"like #{pid} by {rec['username']}: {e.status} {e.message}")
            self.liked(rec["username"]).append(pid)            # never retry a failed like (failed-request budget)
            if e.status in (403, 404, 410) and not filler:
                if "suspend" in (e.message or "").lower():
                    rec["status"] = "suspended"
                    self.accounts.save()
                    self.log({"act": "suspended", "username": rec["username"]})
                else:
                    self.drop_post(pid, f"like {e.status}")
            return False
        rl = acc.rate_limit
        if rl and rl.remaining <= 1:
            self.like_hold_until = time.time() + rl.reset / max(rl.limit, 1) + 1
        liked = self.liked(rec["username"])
        liked.append(pid)
        del liked[:-2000]
        if not filler:
            self.state["amp_filler_debt"] += config.FILLER_RATIO
            meta = self.state["amp_posts"].get(str(pid))
            if meta:
                meta["likes"] = meta.get("likes", 0) + 1
        self.log({"act": "like", "live": True, "post_id": pid, "username": rec["username"],
                  "account_id": rec.get("account_id"), "role": rec.get("role", "voice"), "owner": rec.get("owner"),
                  "own": not filler})
        return True

    def filler_pool(self):
        """Other people's recent No / neutral / off-topic top-level posts (never Yes, never ours)."""
        if not self.targeter:
            return []
        ours = {r.get("account_id") for r in self.accounts.records}
        return [p for p in getattr(self.targeter, "feed_posts", [])
                if p["author_id"] not in ours and not p.get("reply_to_post_id") and p.get("kind") != "repost"
                and side_of(p.get("body")) != "yes"]

    def do_filler(self):
        pool = self.filler_pool()
        likers = [r for r in self.accounts.active() if not self.asleep(r)]
        random.shuffle(likers)
        for r in likers[:5]:
            fresh = [p for p in pool if p["post_id"] not in self.liked(r["username"])]
            if fresh:
                # No-side posts first (helps No in Trending), then anything neutral
                no = [p for p in fresh if side_of(p.get("body")) == "no"]
                p = random.choice(no if no and random.random() < 0.6 else fresh)
                return self.do_like(dict(post_id=p["post_id"], username=r["username"]), filler=True)
        return False

    def track_ranks(self):
        trending = getattr(self.targeter, "trending_ids", None) if self.targeter else None
        if not trending:
            return
        for rank, pid in enumerate(trending, 1):
            meta = self.state["amp_posts"].get(str(pid))
            if meta and (meta.get("best_rank") is None or rank < meta["best_rank"]):
                meta["best_rank"] = rank

    # ---- measurement, bandit reward, follow-backs ----------------------------------------------
    def measure_due(self):
        t = time.time()
        for pid, meta in list(self.state["amp_posts"].items()):
            done = len(meta.get("measured", []))
            if done >= len(config.MEASURE_AT_S):
                if t - meta["t"] > 2 * 86400:
                    del self.state["amp_posts"][pid]
                continue
            if t - meta["t"] < config.MEASURE_AT_S[done]:
                continue
            meta.setdefault("measured", []).append(t)
            if int(pid) < 0 or not self.live:
                continue
            self.measure(int(pid), meta, first=done == 0)
            return                                            # one measurement per tick

    def measure(self, pid, meta, first):
        try:
            c = self.social.counters(pid)
            likers = list(self.social.likers(pid, limit=100))
            replies = list(self.social.replies(pid, limit=100))
        except ctn.APIError as e:
            if e.status in (403, 404, 410):
                self.drop_post(pid, f"measure {e.status}")
                self.log({"act": "amp_measure", "post_id": pid, "hidden_or_gone": e.status, **meta})
            return
        cit_likers = [x["account_id"] for x in likers if is_citizen_id(x.get("account_id"))]
        cit_replies = [r for r in replies if is_citizen_id(r.get("author_id"))]
        views = max(0, (c.get("view_count") or 0) - meta.get("own_views", 0))
        reward = 5 * len(cit_likers) + 15 * len(cit_replies) + views
        self.log({"act": "amp_measure", "post_id": pid, "level": meta["level"], "author": meta["author"],
                  "frame": meta.get("frame"), "at_h": round((time.time() - meta["t"]) / 3600, 1),
                  "likes": c.get("like_count"), "replies": c.get("reply_count"), "reposts": c.get("repost_count"),
                  "views": c.get("view_count"), "own_likes": meta.get("likes", 0), "own_views": meta.get("own_views", 0),
                  "citizen_likes": len(cit_likers), "citizen_replies": len(cit_replies), "best_rank": meta.get("best_rank"),
                  "reward": reward})
        if first:
            s = self.state["amp_stats"].setdefault(meta["level"], [0, 0.0])
            s[0] += 1
            s[1] += reward
        # the author follows citizens who liked it (+20 each if they follow back) and likes citizen replies
        rec = next((r for r in self.accounts.voices() if r["username"] == meta["author"]), None)
        if not rec:
            return
        acc = self.accounts.session(rec)
        followed = rec.setdefault("followed", [])
        for aid in [a for a in cit_likers if a not in followed][:config.FOLLOW_BACK_MAX]:
            try:
                acc.follow(aid)
                followed.append(aid)
                self.log({"act": "follow", "username": rec["username"], "account_id": aid, "why": "liked_our_post"})
            except ctn.APIError as e:
                print("follow-back:", e.status, e.message)
                break
        for r in cit_replies[:3]:
            if r["post_id"] in self.liked(rec["username"]):
                continue
            self.do_like(dict(post_id=r["post_id"], username=rec["username"]), filler=True)
        self.accounts.save()


def preview(n_boosters=34, n_voices=12, level="heavy"):
    """Print one post's schedule (no network). python -m swan_bot.amplify"""
    class _Acc:
        def __init__(self):
            self.records = [dict(username=f"v{i}", persona=content.PERSONAS[i]["key"], status="active")
                            for i in range(n_voices)]
            self.records += [dict(username=f"b{i}", role="booster", status="active",
                                  sleep_start=random.uniform(0, 24)) for i in range(n_boosters)]

        def active(self):
            return self.records

        def voices(self):
            return [r for r in self.records if r.get("role") != "booster"]

        def boosters(self):
            return [r for r in self.records if r.get("role") == "booster"]

    amp = Amplifier(None, _Acc(), {}, live=False, log=lambda r: None)
    amp.scale = 1.0
    likes = amp.on_post(None, amp.accounts.records[0], "", "F1_blank_cheque", level)
    mins = sorted((a["due"] - time.time()) / 60 for a in likes)
    buckets = [(0, 5), (5, 15), (15, 30), (30, 60), (60, 121)]
    print("likes by minute after posting:",
          {f"{a}-{b}": sum(a <= m < b for m in mins) for a, b in buckets})
    for th in sorted(amp.state["amp_threads"], key=lambda th: th["due"]):
        print(f"  +{(th['due'] - time.time()) / 60:4.1f} min  {th['kind']} {th.get('style') or ''}")


if __name__ == "__main__":
    preview()
