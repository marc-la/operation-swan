"""Copy swan_bot's local records to the team MongoDB (db "ctn") so teammates can see them. One-way, idempotent.

    python scripts/swan_sync_mongo.py          # run any time; safe to repeat. Copies only the log lines added since the last run
    python scripts/swan_sync_mongo.py --full   # from every log's first line (after a Mongo wipe or a hand edit there)

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
import hashlib
import json
import os
import pathlib
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from swan_bot import bot, config, jsonl  # noqa: E402
from swan_bot.bot import ARMS  # noqa: E402
from swan_lab import library as lab_library  # noqa: E402
import pymongo  # noqa: E402
from pymongo import ReplaceOne, UpdateOne  # noqa: E402

HOST = ""
USER = ""
SECRET_FIELDS = {"password", "token"}
CHUNK = 1000                                         # bulk ops per round trip (and the most a crash can replay)
SCHEMA = 1                                           # bump when a handler below changes what it writes: logs resync from 0
CURSOR_FILE = config.DATA / "swan_sync_cursors.json"    # per log: byte offset, inode, head hash (swan_bot/jsonl.py)
EXPERIMENT_FIELDS = ("ts", "act", "post_id", "username", "account_id", "owner", "persona", "frame", "source",
                     "target_post", "target_author", "shape", "voice", "opener", "tag", "catchphrase", "theme", "identity",
                     "messenger_match", "amp_level", "style", "exp", "git_sha", "target_stance", "target_class",
                     "soft_yes", "yes_reason") + ARMS


def connect():
    config.load_env()
    pw = urllib.parse.quote_plus(config.team_code())
    return pymongo.MongoClient(f"mongodb+srv://{USER}:{pw}@{HOST}/", serverSelectionTimeoutMS=15000)["ctn"]


class Sink:
    """Bulk ops per collection: one round trip per CHUNK ops, not one per row, and not the whole log in memory."""

    def __init__(self, db):
        self.db, self.ops, self.n = db, collections.defaultdict(list), {}

    def add(self, name, op):
        self.n.setdefault(name, 0)
        batch = self.ops[name]
        batch.append(op)
        if len(batch) >= CHUNK:
            self.flush(name)

    def flush(self, name=None):
        for name in [name] if name else list(self.ops):
            batch = self.ops[name]
            if batch:
                self.db[name].bulk_write(batch, ordered=False)
                self.n[name] += len(batch)
                self.ops[name] = []


def action(sink, r):
    r = {k: v for k, v in r.items() if k not in SECRET_FIELDS}
    if r.get("live") and r.get("post_id"):
        sink.add("actions", ReplaceOne({"post_id": r["post_id"]}, r, upsert=True))
        if r["act"] != "repost":
            doc = {k: r.get(k) for k in EXPERIMENT_FIELDS}
            doc["mode"] = doc.pop("act")
            sink.add("experiments", ReplaceOne({"post_id": r["post_id"]}, doc, upsert=True))
        if r["act"] in ("reply", "second_voice") and r.get("target_author"):
            sink.add("contacted", UpdateOne({"citizen_id": r["target_author"]},
                                            {"$setOnInsert": {"first_ts": r["ts"]},
                                             "$addToSet": {"by": {"persona": r["persona"], "frame": r["frame"],
                                                                  "post_id": r["post_id"], "ts": r["ts"]}}},
                                            upsert=True))
    elif r.get("act") == "reject":
        sink.add("rejects", ReplaceOne({"ts": r["ts"]}, r, upsert=True))
    elif r.get("act") == "refresh":
        sink.add("activity", ReplaceOne({"ts": r["ts"]}, r, upsert=True))
    elif r.get("act") == "amp_measure":
        sink.add("post_outcomes", ReplaceOne({"ts": r["ts"], "act": "amp_measure"}, r, upsert=True))


def outcome(sink, r):
    sink.add("post_outcomes", ReplaceOne({"ts": r["ts"], "act": r["act"], "post_id": r.get("post_id"),
                                          "account_id": r.get("account_id")}, r, upsert=True))


def followup(sink, r):
    sink.add("followups", ReplaceOne({"post_id": r["post_id"], "check": r["check"]}, r, upsert=True))


def blue(sink, r):                                  # swan_blue: reports, rulings, locks, mode changes
    sink.add("blue", ReplaceOne({"ts": r["ts"], "act": r["act"], "key": r.get("key")}, r, upsert=True))


def lab_trial(sink, r):                             # the NPC lab (todo/25)
    sink.add("lab_trials", ReplaceOne({"ts": r["ts"], "strategy": r["strategy"], "persona": r["persona"],
                                       "seed": r["seed"]}, r, upsert=True))


def sources():
    """(cursor name, jsonl path, handler) for every append-only log."""
    return [("actions", config.ACTIONS_LOG, action), ("outcomes", config.OUTCOMES_LOG, outcome),
            ("followups", config.FOLLOWUPS_LOG, followup), ("blue", config.LOGS / "blue_reports.jsonl", blue),
            ("lab_trials", config.LAB_DIR / "trials.jsonl", lab_trial)]


def fingerprint():
    """Changes with what the handlers copy (the fields, the secrets stripped, SCHEMA): a changed mapping resyncs
    the logs from 0, as the old full re-read did on every run."""
    return hashlib.sha1(json.dumps([SCHEMA, sorted(SECRET_FIELDS), EXPERIMENT_FIELDS]).encode()).hexdigest()[:12]


def sync(db, full=False, cursor_file=None):
    """Copy what the logs gained since the last run. Each log's cursor (jsonl.Reader.cursor, in cursor_file) is saved
    only after that log's writes all went through: a crash replays at most a chunk, and every op is an upsert."""
    cursor_file = cursor_file or CURSOR_FILE
    saved = bot.load_json(cursor_file, {})
    files = {} if full or saved.get("fingerprint") != fingerprint() else dict(saved.get("files", {}))
    sink = Sink(db)
    for name, path, handler in sources():
        reader = jsonl.Reader(path, resume=files.get(name))
        for r in reader:
            handler(sink, r)
        sink.flush()
        files[name] = reader.cursor
        bot.save_json(cursor_file, {"fingerprint": fingerprint(), "files": files})
    return sink


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--note", help="add a dated team note")
    ap.add_argument("--full", action="store_true", help="resync every log from its first line (default: only new lines)")
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

    sink = sync(db, full=args.full)
    for card in lab_library.personas():              # small: replaced whole every run
        sink.add("lab_personas", ReplaceOne({"id": card["id"]}, card, upsert=True))
    sink.flush()
    print(f"synced {len(accounts)} accounts, " + (", ".join(f"{v} {k}" for k, v in sink.n.items()) or "no new rows"))


if __name__ == "__main__":
    main()
