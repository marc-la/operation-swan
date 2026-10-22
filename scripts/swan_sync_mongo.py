"""Copy swan_bot's local records to the team MongoDB (db "ctn") so teammates can see them. One-way, idempotent.

    python scripts/swan_sync_mongo.py          # run any time; safe to repeat

Collections:
  accounts   our accounts (bot + swarm): username, account_id, role, persona, owner, status (NO passwords or tokens)
  actions    every live write: mode, persona, frame, target, text, post_id, owner
  contacted  one doc per citizen we've replied to: when, by whom, with which frame
  activity   target refreshes: candidate counts and citizen replies in the news threads in the last hour
  rejects    drafts the quality gate rejected, and why (to improve prompts)
  notes      dated team notes (critical facts); add with --note "text"
  experiments    one doc per live write: post id, mode, persona, frame, every arm, target class, git sha (todo/13)
  followups      a citizen's posts and stance label 2 h / 12 h after we replied (scripts/swan_followup.py)
  post_outcomes  per post at +1 h / +6 h: views, likes, replies, citizen likes and replies, Trending rank, hidden;
                 plus the amplifier's amp_measure records, trending snapshots and voices' follower counts
  lab_trials     the NPC lab's trials (todo/25, data/lab/trials.jsonl): strategy, persona, reply, stand-in verdict
  lab_personas   the lab's persona cards (content/lab/personas): citizens' own words, stance class, segment
  (portal_activity is filled by scripts/import_activity.py)
Password = CTN_TEAM_CODE from .env (never printed).
"""
import argparse
import collections
import datetime as dt
import json
import os
import pathlib
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from swan_bot import config  # noqa: E402
from swan_bot.bot import ARMS  # noqa: E402
from swan_lab import library as lab_library  # noqa: E402
import pymongo  # noqa: E402
from pymongo import ReplaceOne, UpdateOne  # noqa: E402

HOST = ""
USER = ""
SECRET_FIELDS = {"password", "token"}
EXPERIMENT_FIELDS = ("ts", "act", "post_id", "username", "account_id", "owner", "persona", "frame", "source",
                     "target_post", "target_author", "shape", "voice", "opener", "tag", "catchphrase", "theme", "identity",
                     "messenger_match", "amp_level", "style", "exp", "git_sha", "target_stance", "target_class",
                     "soft_yes", "yes_reason") + ARMS


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


def connect():
    config.load_env()
    pw = urllib.parse.quote_plus(config.team_code())
    return pymongo.MongoClient(f"mongodb+srv://{USER}:{pw}@{HOST}/", serverSelectionTimeoutMS=15000)["ctn"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--note", help="add a dated team note")
    args = ap.parse_args()
    db = connect()
    if args.note:
        db.notes.insert_one({"ts": dt.datetime.now(dt.timezone.utc).isoformat(), "by": config.operator(), "text": args.note})
        print("note added")

    accounts = json.loads(config.ACCOUNTS_FILE.read_text()) if config.ACCOUNTS_FILE.exists() else []
    if config.SWARM_ACCOUNTS_FILE.exists():          # swarm accounts (role "swarm", owner minhnguyenhoang)
        accounts += json.loads(config.SWARM_ACCOUNTS_FILE.read_text())
    for a in accounts:
        doc = {k: v for k, v in a.items() if k not in SECRET_FIELDS}
        db.accounts.replace_one({"username": a["username"]}, doc, upsert=True)

    rows = jsonl(config.ACTIONS_LOG)
    ops = collections.defaultdict(list)          # collection -> bulk ops: one round trip each, not one per row
    for r in rows:
        r = {k: v for k, v in r.items() if k not in SECRET_FIELDS}
        if r.get("live") and r.get("post_id"):
            ops["actions"].append(ReplaceOne({"post_id": r["post_id"]}, r, upsert=True))
            if r["act"] != "repost":
                doc = {k: r.get(k) for k in EXPERIMENT_FIELDS}
                doc["mode"] = doc.pop("act")
                ops["experiments"].append(ReplaceOne({"post_id": r["post_id"]}, doc, upsert=True))
            if r["act"] in ("reply", "second_voice") and r.get("target_author"):
                ops["contacted"].append(UpdateOne({"citizen_id": r["target_author"]},
                                                  {"$setOnInsert": {"first_ts": r["ts"]},
                                                   "$addToSet": {"by": {"persona": r["persona"], "frame": r["frame"],
                                                                        "post_id": r["post_id"], "ts": r["ts"]}}},
                                                  upsert=True))
        elif r["act"] == "reject":
            ops["rejects"].append(ReplaceOne({"ts": r["ts"]}, r, upsert=True))
        elif r["act"] == "refresh":
            ops["activity"].append(ReplaceOne({"ts": r["ts"]}, r, upsert=True))
        elif r["act"] == "amp_measure":
            ops["post_outcomes"].append(ReplaceOne({"ts": r["ts"], "act": "amp_measure"}, r, upsert=True))
    for r in jsonl(config.OUTCOMES_LOG):
        ops["post_outcomes"].append(ReplaceOne({"ts": r["ts"], "act": r["act"], "post_id": r.get("post_id"),
                                                "account_id": r.get("account_id")}, r, upsert=True))
    for r in jsonl(config.FOLLOWUPS_LOG):
        ops["followups"].append(ReplaceOne({"post_id": r["post_id"], "check": r["check"]}, r, upsert=True))
    for r in jsonl(config.LOGS / "blue_reports.jsonl"):       # swan_blue: reports, rulings, locks, mode changes
        ops["blue"].append(ReplaceOne({"ts": r["ts"], "act": r["act"], "key": r.get("key")}, r, upsert=True))
    for r in jsonl(config.LAB_DIR / "trials.jsonl"):           # the NPC lab (todo/25)
        ops["lab_trials"].append(ReplaceOne({"ts": r["ts"], "strategy": r["strategy"], "persona": r["persona"],
                                             "seed": r["seed"]}, r, upsert=True))
    for card in lab_library.personas():
        ops["lab_personas"].append(ReplaceOne({"id": card["id"]}, card, upsert=True))
    n = {}
    for name, batch in ops.items():
        db[name].bulk_write(batch, ordered=False)
        n[name] = len(batch)
    print(f"synced {len(accounts)} accounts, " + ", ".join(f"{v} {k}" for k, v in n.items()))


if __name__ == "__main__":
    main()
