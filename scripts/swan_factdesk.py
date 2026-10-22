"""Fact desk, read-only (swan_bot/factdesk.py says what and why). swan-factdesk.timer runs it hourly on EC2: new
articles from the two papers are checked against content/facts.toml; a contradicted fact is paused at once
(data/facts_paused.json, which the bot re-reads on its next draft) and everything else is proposed. With
config.FACTDESK_AUTO (todo/29, on since 22 Oct) the desk then decides its open proposals itself
(factdesk.auto_decide): changes go to the overlay data/facts_auto.toml, each logged in data/facts_auto.jsonl
(by "factdesk-auto") and alerted with its undo command, with no daily cap (config.FACTDESK_AUTO_PER_DAY), and the bot is
restarted once to read them. Pauses, proposals and decisions go to logs/alerts.log (the dashboard shows it) and the
team Mongo; scripts/facts_review.py still decides by hand whatever the desk leaves.

    python scripts/swan_factdesk.py                      # what the timer runs
    python scripts/swan_factdesk.py --dry                # print only: no state, pause, proposal, decision, alert, log or Mongo
    python scripts/swan_factdesk.py --no-auto            # propose only, as before autopilot (this run)
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
            if kind == "decision":                  # autopilot (todo/29): the proposal's status, and the record
                db.fact_proposals.update_one({"id": doc["id"]}, {"$set": dict(
                    status=doc["status"], decided_by=doc["by"], decided_at=doc["decided_at"])})
                db.fact_decisions.update_one({"_id": f"{doc['id']}|{doc['status']}|{doc['decided_at']}"},
                                             {"$setOnInsert": doc}, upsert=True)
                return True
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
    ap.add_argument("--no-auto", action="store_true", help="propose only (config.FACTDESK_AUTO off for this run)")
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
    auto = None
    if config.FACTDESK_AUTO and not args.no_auto:
        auto = factdesk.auto_decide(dry=args.dry, alert=alert, mirror=mirror, log=log, test=factdesk.run_facts_tests)
        print(json.dumps({k: [r["id"] for r in v] if isinstance(v, list) else v for k, v in auto.items()}))
    if not args.dry:
        state["last_run"] = dt.datetime.now(dt.timezone.utc).isoformat()    # the dashboard's "desk stalled" check
        factdesk.write_json(factdesk.STATE_FILE, state)      # after the decisions: a failed mirror waits in it
        if auto and auto["applied"]:
            restart_bot()


def restart_bot():
    """The bot reads its facts at start (facts.load, overlay included): restart it, as a deploy does (update.sh)."""
    try:
        subprocess.run(["sudo", "-n", "systemctl", "try-restart", "swan-bot"], check=False, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"restart: {type(e).__name__}; the overlay goes live on the next deploy or restart")


if __name__ == "__main__":
    main()
