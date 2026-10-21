"""Hidden-post watch, hourly ring self-audit and hourly new-citizen watch (scripts/citizen_watch.py), read-only
(swan_bot/watch.py says what and why). swan-watch.timer runs it every 20 min on EC2. New hidden posts, a ring alarm
and a possible run of new citizens go to logs/swan_watch.jsonl and the alert channel.

    python scripts/swan_watch.py            # what the timer runs
    python scripts/swan_watch.py --dry      # print only: no state, log or alert
"""
import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import capturethenarrative as ctn  # noqa: E402

import citizen_watch  # noqa: E402
from ring_audit import audit_many, ring_score  # noqa: E402
from swan_bot import config, feeds, watch  # noqa: E402


def jsonl(path):
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    def record(rec):
        rec = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(), **rec}
        print(json.dumps(rec))
        if not args.dry:
            with open(watch.WATCH_LOG, "a") as f:
                f.write(json.dumps(rec) + "\n")

    def alert(msg):
        if not args.dry:
            subprocess.run([str(ROOT / "deploy" / "alert.sh"), msg], check=False)

    now = time.time()
    social = ctn.LegitSocial()
    state = watch.load()
    hidden = state.setdefault("hidden", {})
    records = json.loads(config.ACCOUNTS_FILE.read_text()) if config.ACCOUNTS_FILE.exists() else []   # ids only
    voices = [r for r in records if r.get("role", "voice") != "booster" and r.get("status", "active") == "active"]
    rows = jsonl(config.ACTIONS_LOG)

    # ---- hidden posts, every run ----
    for username, pid in watch.find_hidden(social, voices, watch.logged_posts(rows, now), hidden):
        hidden.setdefault(username, []).append(pid)
        n = len(hidden[username])
        actions = sum(1 for r in rows if r.get("live") and r.get("username") == username)
        step = ("stops writing" if n >= config.HIDDEN_STOP else
                "off amplified posts and threads" if n >= config.HIDDEN_OFF_AMP else "no change")
        record({"act": "hidden_post", "username": username, "post_id": pid, "hidden": n, "actions": actions,
                "bot": step})
        alert(f"@{username}: post #{pid} hidden by the moderator ({n} hidden, {actions} actions; 3 = suspended). "
              f"Bot: {step}. Decide whether this voice keeps writing.")
    state["checked"] = now

    # ---- ring self-audit, hourly ----
    if now - state.get("ring_ts", 0) >= watch.RING_EVERY_S:
        ours_ids = {r.get("account_id") for r in records}
        plans = [r["post_id"] for r in rows if r.get("act") == "amp_plan" and r.get("live") and r.get("post_id")]
        try:
            trend = [p["post_id"] for p in feeds.read(social, "feed_trending", "swan-watch", limit=watch.RING_TRENDING)
                     if p["author_id"] not in ours_ids]
        except ctn.APIError as e:
            print("feed_trending:", e.status, e.message)
            trend = []
        ours, leaders = audit_many(social, plans[-watch.RING_OURS:]), audit_many(social, trend)
        ours_med, leaders_med = watch.ring_medians(ours, leaders, ring_score)
        record({"act": "ring_audit", "ours": [(r["post_id"], ring_score(r)) for r in ours],
                "ours_median": ours_med, "leaders_median": leaders_med})
        state["ring_ts"], state["ring"] = now, {"ours_median": ours_med, "leaders_median": leaders_med}
        if watch.ring_alarm(ours_med, leaders_med) and now - state.get("ring_alert_ts", 0) >= watch.RING_ALERT_GAP_S:
            state["ring_alert_ts"] = now
            alert(f"ring self-audit: our amplified posts score {ours_med} (median RING), the Trending leaders "
                  f"{leaders_med}. We look as coordinated as the teams we'd report. "
                  f"Spread the likes and thread replies out (config.LIKE_DELAY / THREAD_DELAY).")
    # ---- new citizens mid-game (todo/21 G10), hourly: alert only, a person adds the range ----
    if now - state.get("citizens_ts", 0) >= watch.RING_EVERY_S:
        state["citizens_ts"] = now
        try:
            citizen_watch.scan(social, state, {r.get("account_id") for r in records}, record, alert)
        except ctn.APIError as e:
            print("citizen_watch:", e.status, e.message)
    if not args.dry:
        watch.save(state)


if __name__ == "__main__":
    main()
