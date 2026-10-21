"""Hidden-post watch and ring self-audit (read-only); scripts/swan_watch.py runs it every 20 min on EC2.

A moderator-hidden post answers 404 "post not found" and drops out of its author's post list (checked 2026-10-21 on
@lani_wharfcafe23, suspended the day before with one hidden post; we never delete posts). One hidden post plus
≥100 actions means the next inauthentic-account report suspends the voice; three hidden posts suspend it outright
(scoring guide §3). So:
  hidden   every run: each voice's logged posts vs its post list; a missing one that answers 404 is hidden. The
           counts go to data/swan_watch.json, which the bot reads (Accounts.hidden): config.HIDDEN_OFF_AMP hidden
           posts take a voice off amplified posts and threads, config.HIDDEN_STOP stop it writing.
  ring     hourly: scripts/ring_audit.py's score on our last amplified posts and on Trending (others' posts only).
           Alert when our median reaches the leaders' median: that's when Blue reporters rank us next to them.
"""
import json
import os
import statistics

import capturethenarrative as ctn

from . import config
from .analysis import ts_of

WATCH_FILE = config.DATA / "swan_watch.json"
WATCH_LOG = config.LOGS / "swan_watch.jsonl"
WRITES = {"post", "reply", "second_voice", "reply_back", "thread", "thread_answer", "journalist", "repost"}
SETTLE_S = 120              # a post this new may not be listed yet
MAX_CONFIRM = 60            # get_post confirmations per run (read budget: 300/min per endpoint, shared with the bot)
RING_EVERY_S = 3600
RING_OURS, RING_TRENDING = 8, 20
RING_ALERT_GAP_S = 6 * 3600


def load(path=None):
    try:
        return json.loads((path or WATCH_FILE).read_text())
    except (OSError, ValueError):
        return {}


def save(state, path=None):
    path = path or WATCH_FILE
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1))
    os.replace(tmp, path)                     # the bot reads this file: never let it see half a write


def logged_posts(rows, now):
    """{username: {post_id, ...}} of our live writes old enough to be listed."""
    out = {}
    for r in rows:
        if r.get("live") and r.get("post_id") and r.get("act") in WRITES and r.get("username"):
            try:
                ts = ts_of(r["ts"])
            except (KeyError, ValueError):
                continue
            if now - ts >= SETTLE_S:
                out.setdefault(r["username"], set()).add(r["post_id"])
    return out


def find_hidden(social, voices, logged, known):
    """New hidden posts as [(username, post_id)]: logged, not listed, and get_post answers 404."""
    new, budget = [], MAX_CONFIRM
    for rec in voices:
        mine = logged.get(rec["username"], set()) - set(known.get(rec["username"], []))
        if not mine or not rec.get("account_id"):
            continue
        try:
            listed = {p["post_id"] for p in social.iterate(social.account_posts, rec["account_id"], max_items=3000)}
        except ctn.APIError as e:
            print(f"{rec['username']}: account_posts {e.status} {e.message}")
            continue
        for pid in sorted(mine - listed):
            if budget <= 0:
                return new
            budget -= 1
            try:
                social.get_post(pid)                 # listed late, not hidden
            except ctn.APIError as e:
                if e.status == 404:
                    new.append((rec["username"], pid))
    return new


def ring_medians(ours, trending, score):
    """(our median, the leaders' median) of the ring score, None where a side has no rows."""
    med = lambda rows: statistics.median(score(r) for r in rows) if rows else None
    return med(ours), med(trending)


def ring_alarm(ours_med, leaders_med):
    return ours_med is not None and leaders_med is not None and ours_med >= leaders_med
