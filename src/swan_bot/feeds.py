"""Feed reads (todo/21 G1). feed_latest and feed_trending share 10 reads a minute (the server answers each with that
route's budget; account_posts, replies and get_post have 300 each, checked 2026-10-21). On 21 Oct the bot found the
budget at <= 3 when it paged Latest, so:
  - every feed call goes through read(), which appends the process, the route, the budget the answer reported and any
    error status to logs/feed_reads.jsonl (one file for the whole box; swan-blue writes the same format);
  - the bot is the one Latest reader. It writes what it read to data/latest_snapshot.json (atomically), and swan-blue
    reads that instead of the feeds:
        {"read_at": ISO UTC, "posts": [Latest posts as feed_latest returns them, last SNAPSHOT_KEEP_S, newest first],
         "trending": {"read_at": ISO UTC, "posts": [the last Trending read, in rank order]}}
  - dry runs read a saved snapshot through FixtureFeeds, not the live feeds.
"""
import datetime as dt
import json
import os
import time

import capturethenarrative as ctn

from . import config

FEED_LOG = config.LOGS / "feed_reads.jsonl"
SNAPSHOT_FILE = config.DATA / "latest_snapshot.json"
SNAPSHOT_KEEP_S = 15 * 60           # Latest posts this new stay in the snapshot (swan-blue reads it every minute)


def now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read(social, route, proc, **kw):
    """social.<route>(**kw), logged with the feed budget its answer reported. Errors are logged and re-raised."""
    t, status = time.time(), None
    try:
        return getattr(social, route)(**kw)
    except ctn.APIError as e:
        status = e.status
        raise
    finally:
        rl = getattr(social, "rate_limit", None)
        try:
            config.LOGS.mkdir(exist_ok=True)
            with open(FEED_LOG, "a") as f:
                f.write(json.dumps({"ts": now_iso(), "proc": proc, "route": route, "paged": bool(kw.get("cursor")),
                                    "remaining": rl.remaining if rl else None, "limit": rl.limit if rl else None,
                                    "reset": rl.reset if rl else None, "ms": round((time.time() - t) * 1000),
                                    **({"error": status} if status else {})}) + "\n")
        except (OSError, AttributeError):
            pass                                     # the log must never stop a read


def created_ts(post):
    return dt.datetime.fromisoformat(post["created_at"].replace("Z", "+00:00")).timestamp()


def write_snapshot(latest, trending=None, trending_at=None, path=None):
    """Atomically replace the snapshot. latest: Latest posts (newest first); trending: the last Trending read."""
    path = path or SNAPSHOT_FILE
    path.parent.mkdir(exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"read_at": now_iso(), "posts": latest,
                               "trending": {"read_at": trending_at, "posts": trending or []}}))
    os.replace(tmp, path)


def read_snapshot(path=None, max_age_s=None):
    """The snapshot as a dict, or None when it is missing, unreadable or older than max_age_s."""
    try:
        snap = json.loads((path or SNAPSHOT_FILE).read_text())
    except (OSError, ValueError):
        return None
    if max_age_s is not None:
        age = time.time() - dt.datetime.fromisoformat(snap["read_at"]).timestamp()
        if age > max_age_s:
            return None
    return snap


class FixtureFeeds:
    """Dry runs: Latest and Trending from a saved snapshot, never the live feeds (the 10/min budget is the live
    bot's). Every other read goes to the real client. Each feed answers once; later reads find nothing new."""

    def __init__(self, social, snapshot):
        self.social, self.snapshot = social, snapshot
        self.rate_limit = None

    def __getattr__(self, name):
        return getattr(self.social, name)

    def feed_latest(self, limit=100, cursor=None):
        posts = [] if cursor else self.snapshot.get("posts", [])[:limit]
        return ctn.Page(posts, None)

    def feed_trending(self, limit=50, cursor=None):
        return ctn.Page([] if cursor else (self.snapshot.get("trending") or {}).get("posts", [])[:limit], None)


FIXTURE_FILE = config.DATA / "feed_fixture.json"


def fixture(social, path=None):
    """The snapshot a dry run reads its feeds from: the file at path (a copy of the box's latest_snapshot.json, say),
    else data/feed_fixture.json, made once from one live Latest and one Trending read and reused after that."""
    path = path or FIXTURE_FILE
    snap = read_snapshot(path)
    if snap is None:
        latest = list(read(social, "feed_latest", "dry-run", limit=100))
        trending = list(read(social, "feed_trending", "dry-run", limit=50))
        write_snapshot(latest, trending, now_iso(), path=path)
        snap = read_snapshot(path)
    return snap
