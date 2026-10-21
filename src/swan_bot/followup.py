"""Read-only measurement for the overnight experiments (todo/13): what happened after each of our live writes.

Two per-write signals, read on a schedule from the bot's own action log (never from the platform's write side):
  outcome    per post at +1 h and +6 h: views, likes, replies, reposts, and how many likes/replies were citizens';
             403/404/410 means hidden or gone
  followup   per citizen we replied to, at +2 h and +12 h: their posts since our reply, classified with
             targeting.stance, and a label: moved_no / moved_yes / no_change / unclear / silent / private
Plus, per run: our posts' ranks in Trending (one feed read), and every ~2 h each voice's citizen followers (H9).
scripts/swan_followup.py runs it (systemd timer, every 30 min on EC2). Writes logs/swan_outcomes.jsonl and
logs/swan_followups.jsonl; scripts/swan_sync_mongo.py copies them to Mongo.
"""
import datetime as dt
import json
import time

import capturethenarrative as ctn

from . import config
from .amplify import is_citizen_id
from .analysis import ts_of
from .targeting import stance

WRITES = {"post", "reply", "second_voice", "journalist", "reply_back", "thread"}
CONTACTS = {"reply", "second_voice", "reply_back"}
OWN_POSTS = WRITES | {"thread_answer"}      # rows whose post_id is a post we wrote (not a like, repost or plan)


def our_post_ids(rows):
    """The ids of the posts we wrote. Like rows carry live and post_id too (the post liked, mostly another team's),
    so counting them made replied_to_us true for replies to anyone we'd liked, and filled Trending with others'
    posts (todo/20, fixed 2026-10-22)."""
    return {r["post_id"] for r in rows if r.get("live") and r.get("post_id") and r.get("act") in OWN_POSTS}
FOLLOWERS_EVERY_S = 2 * 3600
READ_GAP_S = 0.5            # ~120 reads/min at most: the bot shares the 300/min per-endpoint budgets


def label(baseline, after):
    """Follow-up label from the stance of the post we replied to and the stances of their later referendum posts
    (oldest first; None entries = off topic). The latest clear stance decides."""
    on_topic = [s for s in after if s]
    if not on_topic:
        return "silent"
    clear = [s for s in on_topic if s != "unclear"]
    if not clear:
        return "unclear"
    last = clear[-1]
    if last == "no" and baseline != "no":
        return "moved_no"
    if last == "yes" and baseline != "yes":
        return "moved_yes"
    return "no_change"


def due(rows, state, now):
    """[(lateness_s, kind, i, row)] for every check that is due, least late first (fresh checks before backfill)."""
    out = []
    for r in rows:
        if not (r.get("live") and r.get("post_id") and r.get("act") in WRITES):
            continue
        age = now - ts_of(r["ts"])
        pid = str(r["post_id"])
        kinds = [("outcome", config.OUTCOME_AT_S)]
        if r["act"] in CONTACTS and r.get("target_author"):
            kinds.append(("followup", config.FOLLOWUP_AT_S))
        for kind, at in kinds:
            done = state[kind].get(pid, [])
            for i, a in enumerate(at):
                if i not in done and age >= a:
                    out.append((age - a, kind, i, r))
    return sorted(out, key=lambda x: x[0])


class Reader:
    def __init__(self, social, max_reads=None, gap=READ_GAP_S, log=print):
        self.social, self.gap, self.log = social, gap, log
        self.max_reads = config.FOLLOWUP_MAX_READS if max_reads is None else max_reads
        self.reads = 0

    def read(self, fn, *a, **kw):
        if self.reads >= self.max_reads:
            raise StopIteration("read budget for this run used")
        self.reads += 1
        time.sleep(self.gap)
        return fn(*a, **kw)

    def outcome(self, r, i, now, trending):
        pid = r["post_id"]
        rec = {"act": "outcome", "post_id": pid, "mode": r["act"], "check": i,
               "at_h": round((now - ts_of(r["ts"])) / 3600, 2), "trending_rank": trending.get(pid)}
        try:
            c = self.read(self.social.counters, pid)
        except ctn.RateLimited:
            raise
        except ctn.APIError as e:
            if e.status in (403, 404, 410):
                return {**rec, "hidden_or_gone": e.status}
            raise
        likers = self.read(self.social.likers, pid, limit=100) if c.get("like_count") else []
        replies = self.read(self.social.replies, pid, limit=100) if c.get("reply_count") else []
        cit_replies = [x for x in replies if is_citizen_id(x.get("author_id"))]
        return {**rec, "views": c.get("view_count"), "likes": c.get("like_count"), "replies": c.get("reply_count"),
                "reposts": c.get("repost_count"),
                "citizen_likes": sum(is_citizen_id(x.get("account_id")) for x in likers),
                "citizen_replies": len(cit_replies), "citizen_repliers": sorted({x["author_id"] for x in cit_replies})}

    def followup(self, r, i, now, our_ids):
        citizen, t0 = r["target_author"], ts_of(r["ts"])
        rec = {"act": "followup", "post_id": r["post_id"], "citizen_id": citizen, "mode": r["act"], "check": i,
               "at_h": round((now - t0) / 3600, 2), "baseline": stance(r.get("target_text"))}
        try:
            posts = self.read(self.social.account_posts, citizen, limit=30)
        except ctn.RateLimited:
            raise
        except ctn.APIError as e:
            if e.status == 403:
                return {**rec, "label": "private"}
            raise
        after = sorted((p for p in posts if p.get("kind") != "repost" and ts_of(p["created_at"]) > t0),
                       key=lambda p: p["created_at"])
        stances = [stance(p.get("body")) for p in after]
        return {**rec, "label": label(rec["baseline"], stances), "posts_after": len(after),
                "stances": [s for s in stances if s],
                "replied_to_us": any(p.get("reply_to_post_id") in our_ids for p in after),
                "replied_to_this": any(p.get("reply_to_post_id") == r["post_id"] for p in after),
                "texts": [(p.get("body") or "")[:280] for p, s in zip(after, stances) if s][-3:]}

    def trending(self, our_ids):
        """{post_id: rank} for our posts in Trending right now (one feed read; feeds are 10/min team-wide)."""
        try:
            posts = self.read(self.social.feed_trending, limit=50)
        except ctn.APIError:
            return {}
        return {p["post_id"]: rank for rank, p in enumerate(posts, 1) if p["post_id"] in our_ids}

    def followers(self, voices):
        """Each voice's followers, citizen vs other (H9: Home weights followed accounts). One page per 50."""
        out = []
        for v in voices:
            ids, cursor = [], None
            try:
                while True:
                    page = self.read(self.social.followers, v["account_id"], limit=50, cursor=cursor)
                    ids += [a.get("account_id") for a in page]
                    cursor = page.next_cursor
                    if not cursor or len(ids) >= 1000:
                        break
            except ctn.RateLimited:
                raise
            except ctn.APIError as e:
                out.append({**v, "error": e.status})
                continue
            out.append({**v, "followers": len(ids), "citizen_followers": sum(map(is_citizen_id, ids))})
        return out


def load_rows():
    if not config.ACTIONS_LOG.exists():
        return []
    rows = []
    for line in config.ACTIONS_LOG.read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue                                 # a line cut short by a crash
    return rows


def append(path, rec):
    path.parent.mkdir(exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps({"ts": dt.datetime.now(dt.timezone.utc).isoformat(), **rec}) + "\n")


def run(social, state, now=None, max_reads=None, dry=False, log=print):
    """One pass: every due check, least late first, until the read budget is used. Returns counts."""
    now = time.time() if now is None else now
    for k in ("outcome", "followup"):
        state.setdefault(k, {})
    rows = load_rows()
    todo = due(rows, state, now)
    n = {"due": len(todo), "outcome": 0, "followup": 0, "reads": 0}
    if dry:
        for late, kind, i, r in todo[:30]:
            log(f"due {kind}#{i} {r['act']} #{r['post_id']} (late {late / 3600:.1f} h)")
        return n
    reader = Reader(social, max_reads=max_reads)
    our_ids = our_post_ids(rows)
    try:
        trending = reader.trending(our_ids) if todo else {}
        if trending:
            append(config.OUTCOMES_LOG, {"act": "trending", "ranks": {str(k): v for k, v in trending.items()}})
        for late, kind, i, r in todo:
            key = f"{kind}:{r['post_id']}:{i}"
            try:
                rec = reader.outcome(r, i, now, trending) if kind == "outcome" else reader.followup(r, i, now, our_ids)
            except ctn.RateLimited:
                raise
            except ctn.APIError as e:                # a server error: try again next run, twice at most
                errors = state.setdefault("errors", {})
                errors[key] = errors.get(key, 0) + 1
                log(f"{key}: {e.status} {e.message}")
                if errors[key] < 3:
                    continue
                rec = {"act": kind, "post_id": r["post_id"], "check": i, "error": e.status}
            state.get("errors", {}).pop(key, None)
            append(config.OUTCOMES_LOG if kind == "outcome" else config.FOLLOWUPS_LOG, rec)
            state[kind].setdefault(str(r["post_id"]), []).append(i)
            n[kind] += 1
        if now - state.get("followers_at", 0) >= FOLLOWERS_EVERY_S:
            voices = {}
            for r in rows:
                if r.get("live") and r.get("account_id") and r.get("persona"):
                    voices[r["account_id"]] = dict(account_id=r["account_id"], username=r.get("username"),
                                                   persona=r["persona"])
            for rec in reader.followers(list(voices.values())):
                append(config.OUTCOMES_LOG, {"act": "followers", **rec})
            state["followers_at"] = now
    except StopIteration as e:
        log(str(e))
    except ctn.RateLimited as e:
        log(f"rate limited ({e.status}); stopping this run")
    n["reads"] = reader.reads
    return n
