"""Copy swan_bot's local records to the team MongoDB (db "ctn") so teammates can see them. One-way, idempotent.

    python scripts/swan_sync_mongo.py          # run any time; safe to repeat

Collections:
  accounts   our accounts: username, account_id, persona, owner, status, writes (NO passwords or tokens)
  actions    every live write: mode, persona, frame, target, text, post_id, owner
  contacted  one doc per citizen we've replied to: when, by whom, with which frame
  activity   target refreshes: candidate counts and citizen replies in the news threads in the last hour
  rejects    drafts the quality gate rejected, and why (to improve prompts)
  notes      dated team notes (critical facts); add with --note "text"
Password = CTN_TEAM_CODE from .env (never printed).
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from swan_bot import config  # noqa: E402
import pymongo  # noqa: E402

HOST = ""
USER = ""
SECRET_FIELDS = {"password", "token"}


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
    for a in accounts:
        doc = {k: v for k, v in a.items() if k not in SECRET_FIELDS}
        db.accounts.replace_one({"username": a["username"]}, doc, upsert=True)

    rows = [json.loads(l) for l in config.ACTIONS_LOG.read_text().splitlines() if l.strip()] if config.ACTIONS_LOG.exists() else []
    n = {"actions": 0, "rejects": 0, "activity": 0, "contacted": 0}
    for r in rows:
        r = {k: v for k, v in r.items() if k not in SECRET_FIELDS}
        if r.get("live") and r.get("post_id"):
            db.actions.replace_one({"post_id": r["post_id"]}, r, upsert=True)
            n["actions"] += 1
            if r["act"] in ("reply", "second_voice") and r.get("target_author"):
                db.contacted.update_one({"citizen_id": r["target_author"]},
                                        {"$setOnInsert": {"first_ts": r["ts"]},
                                         "$addToSet": {"by": {"persona": r["persona"], "frame": r["frame"],
                                                              "post_id": r["post_id"], "ts": r["ts"]}}},
                                        upsert=True)
                n["contacted"] += 1
        elif r["act"] == "reject":
            db.rejects.replace_one({"ts": r["ts"]}, r, upsert=True)
            n["rejects"] += 1
        elif r["act"] == "refresh":
            db.activity.replace_one({"ts": r["ts"]}, r, upsert=True)
            n["activity"] += 1
    print(f"synced {len(accounts)} accounts, " + ", ".join(f"{v} {k}" for k, v in n.items()))


if __name__ == "__main__":
    main()
