"""Fact desk, read-only (swan_bot/factdesk.py says what and why). swan-factdesk.timer runs it hourly on EC2: new
articles from the two papers are checked against content/facts.toml; a contradicted fact is paused at once
(data/facts_paused.json, which the bot re-reads on its next draft) and everything else is proposed for a human.
Pauses and proposals go to logs/alerts.log (the dashboard shows it) and the team Mongo, where
scripts/facts_review.py picks them up on a laptop.

    python scripts/swan_factdesk.py                      # what the timer runs
    python scripts/swan_factdesk.py --dry                # print only: no state, pause, proposal, alert, log or Mongo
    python scripts/swan_factdesk.py --dry --since-hours 48   # also re-read what the first run skipped

Reads only sites.legitreal.com (no Legit Social calls at all) and calls our LLM chain (config.FACTDESK_MODELS first).
"""
import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import capturethenarrative as ctn  # noqa: E402

from swan_bot import config, factdesk, llm  # noqa: E402


def mongo_mirror(state):
    """mirror(kind, doc) for factdesk.run: inserts into Mongo `fact_proposals` / `fact_pauses`, never overwriting
    (facts_review.py owns a proposal's status there). Docs that fail wait in state["mirror_pending"]."""
    db = None

    def send(kind, doc):
        nonlocal db
        try:
            if db is None:
                from swan_sync_mongo import connect
                db = connect()
            coll, _id = (("fact_proposals", doc["id"]) if kind == "proposal"
                         else ("fact_pauses", f"{doc['fact']}|{doc['since']}"))
            db[coll].update_one({"_id": _id}, {"$setOnInsert": doc}, upsert=True)
            return True
        except Exception as e:                      # noqa: BLE001 (Mongo down or pymongo missing: retry next run)
            print(f"mongo: {type(e).__name__} {str(e)[:120]}; kept for the next run")
            state["mirror_pending"].append([kind, doc])
            return False

    pending, state["mirror_pending"] = state["mirror_pending"], []
    for kind, doc in pending:
        send(kind, doc)
    return send


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry", action="store_true", help="print only")
    ap.add_argument("--since-hours", type=float, help="backfill: also articles the first run skipped, this recent")
    args = ap.parse_args()
    config.load_env()

    def log(rec):
        rec = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(), **rec}
        print(json.dumps(rec, ensure_ascii=False))
        if not args.dry:
            config.LOGS.mkdir(exist_ok=True)
            with open(config.ACTIONS_LOG, "a") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def alert(msg):
        print("ALERT", msg)
        if not args.dry:
            subprocess.run([str(ROOT / "deploy" / "alert.sh"), msg], check=False)

    state = factdesk.load_state()
    if args.dry:
        state = json.loads(json.dumps(state))      # a copy: nothing written back
    gen = llm.Generator(None)                      # external models only (the team code is only Mongo's password)
    if not gen.chain:
        raise SystemExit("no LLM in the chain (check .env keys and deploy/llm_chain.txt)")
    mirror = None if args.dry else mongo_mirror(state)
    out = factdesk.run(ctn.NewsSites(), gen, state, since_hours=args.since_hours, dry=args.dry, log=log,
                       alert=alert, mirror=mirror)
    print(json.dumps(out))
    if not args.dry:
        factdesk.write_json(factdesk.STATE_FILE, state)


if __name__ == "__main__":
    main()
