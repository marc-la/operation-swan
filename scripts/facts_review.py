r"""Review the fact desk's proposals and pauses (todo/16), then commit the result. Run it on a laptop with a checkout
of main: the EC2 box can't push, and the commit author is the approver (attribution for the code handover).

    python scripts/facts_review.py                     # one by one: accept, edit, reject or skip
    python scripts/facts_review.py --list              # open proposals and the pauses that hold now
    python scripts/facts_review.py --accept 7 --text "..." --note "..."    # contradicted: retired, new key added
    python scripts/facts_review.py --accept 31 --same-key --note "..."     # only the wording changed: in place
    python scripts/facts_review.py --accept 7 --text "..." --says '\blimited spread\b' --says '\blocal cases\b'
    python scripts/facts_review.py --accept 9 --key polls_latest --frames F1_blank_cheque
    python scripts/facts_review.py --reject 8          # a contradiction: re-affirms the fact (lifts its pause)
    python scripts/facts_review.py --accept 9,12 --reject 2,4,5   # a day's decisions, one test run, one commit
    python scripts/facts_review.py --recheck no_spread # re-affirm a fact without a proposal (lifts its pause)

Proposals and pauses come from the team Mongo (the desk mirrors them there); --local reads data/ instead (on the
box, or in tests). The dashboard's Facts section lists the same items with the command for each. Every decision
is also appended to content/fact_decisions.jsonl, which goes in the same commit: that is how the dashboard (and
git history) know what was decided, and by whom. Accepting changes content/facts.toml (facts) or docs/06-strategy/frames-and-messengers.md
(angles). Every change to a fact stamps its `checked`, which is what ends a pause once the commit is deployed. The
tests run before anything is recorded; if they fail, every edit is undone. Then it prints the commit to run: the
push is the approval, live on EC2 in ~2 minutes. When: daily around the 9 pm Perth rollover, and within the hour
of a pause alert.
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from swan_bot import config, content, factdesk  # noqa: E402
from swan_bot import facts as fact_store  # noqa: E402

FACTS = fact_store.FILE
ANGLES = ROOT / "docs" / "06-strategy" / "frames-and-messengers.md"
ANGLES_HEADING = "## Angle ideas from the fact desk"
DECISIONS = ROOT / "content" / "fact_decisions.jsonl"


def decided_ids():
    """Proposal ids with a committed decision (content/fact_decisions.jsonl)."""
    return {r.get("id") for r in _jsonl(DECISIONS)}


def _jsonl(path):
    out = []
    try:
        for line in pathlib.Path(path).read_text().splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    except FileNotFoundError:
        pass
    return out


class LocalStore:
    """data/fact_proposals.jsonl and data/facts_paused.json (the desk's own files)."""

    def __init__(self, proposals=factdesk.PROPOSALS_FILE, paused=None):
        self.proposals_file, self.paused_file = proposals, paused or fact_store.PAUSED_FILE

    def proposals(self):
        return factdesk.read_proposals(self.proposals_file)

    def pauses(self):
        try:
            return fact_store.read_pauses(self.paused_file)
        except ValueError as e:
            print(f"{self.paused_file}: {e}")
            return {}

    def decided(self, pid, status, extra):
        factdesk.append_jsonl(self.proposals_file, [dict(id=pid, status=status, **extra)])


class MongoStore:
    """The team Mongo: fact_proposals (status set here) and fact_pauses (as the desk raised them)."""

    def __init__(self):
        from swan_sync_mongo import connect
        self.db = connect()

    def proposals(self):
        return {d["id"]: d for d in self.db.fact_proposals.find({}, {"_id": 0})}

    def pauses(self):
        out = {}
        for d in self.db.fact_pauses.find({}, {"_id": 0}).sort("since", 1):
            out[d["fact"]] = d                          # the latest pause per fact
        return out

    def decided(self, pid, status, extra):
        self.db.fact_proposals.update_one({"id": pid}, {"$set": dict(status=status, **extra)})


def holding(store):
    """{fact: pause} for the pauses this checkout's facts.toml hasn't re-checked yet."""
    return {k: v for k, v in store.pauses().items() if fact_store.holds(k, v)}


def show(p):
    head = f"#{p['id']} {p['kind']}"
    if p["kind"] in ("contradiction", "reword"):
        now = fact_store.TABLE.get(p["fact"], {})
        held = content.requiring(p["fact"]) if p["kind"] == "contradiction" else []
        print(f"{head}  {p['fact']}{'  [paused]' if p.get('paused') else ''}"
              + (f"  (stated in: {', '.join(held)})" if held else ""))
        print(f"   now:      {now.get('text')}\n             note: {now.get('note')}")
        if p.get("text"):
            print(f"   suggests: {p['text']}\n             note: {p['note']}")
        if p.get("failed_checks"):
            print(f"   (its suggestion failed {p['failed_checks']}: {p.get('failed_text')} / {p.get('failed_note')})")
        print(f"   why:      {p.get('why')}")
    elif p["kind"] == "new_fact":
        print(f"{head}  {p['key']}  frames: {', '.join(p.get('frames') or []) or '-'}")
        print(f"   text:     {p['text']}\n   note:     {p['note']}")
        if p.get("new_numbers"):
            print(f"   new figures (allowed once accepted): {', '.join(p['new_numbers'])}")
    else:
        print(f"{head}{'  (opinion column)' if p.get('opinion') else ''}\n   idea:     {p['idea']}")
    print(f"   quote:    «{p['quote']}»\n             {p['site']}/{p['slug']} ({p.get('published_at')})")
    for a in p.get("also") or []:
        print(f"   also:     «{a['quote']}» {a['site']}/{a['slug']}")


def list_all(store):
    pauses, props = holding(store), store.proposals()
    print(f"Paused now ({len(pauses)}), until facts.toml re-checks them:")
    for k, v in pauses.items():
        print(f"  {k}: since {v.get('since')}, {v.get('site')}/{v.get('slug')} (proposal {v.get('proposal')})")
    done = decided_ids()
    opened = sorted((p for p in props.values() if p.get("status") == "open" and p["id"] not in done),
                    key=lambda p: p["id"])
    print(f"\nOpen proposals ({len(opened)}):")
    for p in opened:
        show(p)
        print()
    return opened


def approver():
    try:
        name = subprocess.run(["git", "config", "user.name"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    except OSError:
        name = ""
    return name or os.environ.get("CTN_OPERATOR") or "unknown"


def add_angle(text, line):
    if ANGLES_HEADING not in text:
        text = text.rstrip("\n") + (f"\n\n{ANGLES_HEADING}\n\nArgument ideas the fact desk found in the papers, "
                                    "accepted by a human. Turn one into a frame in src/swan_bot/content.py (FRAMES) "
                                    "by hand; nothing here reaches a prompt on its own.\n")
    return text.rstrip("\n") + "\n" + line + "\n"


def run_tests():
    py = ROOT / ".venv" / "bin" / "python"
    r = subprocess.run([str(py if py.exists() else sys.executable), "-m", "pytest", "-q", "tests"], cwd=ROOT,
                       capture_output=True, text=True)
    return r.returncode == 0, (r.stdout + r.stderr).strip().splitlines()[-15:]


def apply(store, decisions, yes=False):
    """decisions: [(proposal, accept, overrides)]. Edits the files, runs the tests, records the decisions."""
    facts_before, angles_before = FACTS.read_text(), ANGLES.read_text()
    facts_text, angles_text, done = facts_before, angles_before, []
    for p, accept, kw in decisions:
        if p["kind"] == "contradiction" and not accept and not yes:
            if input(f"Reject #{p['id']}: {p['fact']} stays as it is and its pause lifts. Sure? [y/N] ").lower() != "y":
                continue
        try:
            facts_text, angle, summary = factdesk.decide(p, accept, facts_text, **kw)
        except (ValueError, KeyError) as e:
            print(f"#{p['id']} not applied: {e}")
            continue
        if angle:
            angles_text = add_angle(angles_text, angle)
        done.append((p, accept, kw, summary))
    if not done:
        return False
    changed = facts_text != facts_before or angles_text != angles_before
    if changed:
        FACTS.write_text(facts_text)
        ANGLES.write_text(angles_text)
        ok, tail = run_tests()
        if not ok:
            FACTS.write_text(facts_before)
            ANGLES.write_text(angles_before)
            print("The tests failed, so nothing was changed or recorded:\n  " + "\n  ".join(tail))
            return False
    who, when = approver(), factdesk._iso(dt.datetime.now().timestamp())
    records = []
    for p, accept, kw, summary in done:
        extra = dict(decided_by=who, decided_at=when, summary=summary,
                     **{k: v for k, v in kw.items() if v not in (None, False)})
        status = "accepted" if accept else "rejected"
        try:
            store.decided(p["id"], status, extra)
        except Exception as e:                       # noqa: BLE001 (Mongo down: the committed file still has it)
            print(f"  (store: {type(e).__name__}; the decision is still in {DECISIONS.name})")
        records.append(dict(id=p["id"], kind=p["kind"], status=status, **extra))
        print(f"  {summary}")
    factdesk.append_jsonl(DECISIONS, records)
    msg = ("Facts: " if changed else "Fact desk decisions: ") + "; ".join(s for *_, s in done)
    print(("\nTests pass. " if changed else "\n") + "Commit and push (the push is the approval; live in ~2 min):\n"
          f"  git commit -m {msg[:300]!r} -- content/facts.toml content/fact_decisions.jsonl "
          "docs/06-strategy/frames-and-messengers.md\n  git push")
    return True


def interactive(store):
    opened = list_all(store)
    decisions = []
    for p in opened:
        show(p)
        choices = "[a]ccept [e]dit [r]eject [s]kip [q]uit" + (" [t] retire" if p["kind"] in ("contradiction", "reword")
                                                             else "") + (" [k] same key" if p["kind"] == "contradiction"
                                                                         else "")
        c = input(f"{choices}? ").strip().lower()[:1]
        if c == "q":
            break
        if c == "a":
            decisions.append((p, True, {}))
        elif c == "r":
            decisions.append((p, False, {}))
        elif c == "t" and p["kind"] in ("contradiction", "reword"):
            decisions.append((p, True, {"retire": True}))
        elif c == "k" and p["kind"] == "contradiction":
            decisions.append((p, True, {"same_key": True, "note": input("note (Enter keeps it): ").strip() or None}))
        elif c == "e":
            kw = {}
            if p["kind"] == "angle":
                kw["text"] = input("idea: ").strip() or None
            else:
                if p["kind"] == "new_fact":
                    kw["key"] = input(f"key [{p['key']}]: ").strip() or None
                kw["text"] = input("text: ").strip() or None
                kw["note"] = input("note: ").strip() or None
                says = input("says patterns, separated by ' | ' (Enter keeps them): ").strip()
                if says:
                    kw["says"] = [x.strip() for x in says.split(" | ") if x.strip()]
            decisions.append((p, True, kw))
        print()
    if decisions:
        apply(store, decisions)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--accept", metavar="IDS", help="proposal ids, comma-separated")
    ap.add_argument("--reject", metavar="IDS", help="proposal ids, comma-separated")
    ap.add_argument("--recheck", metavar="FACT", help="re-affirm a fact as it stands (lifts its pause)")
    ap.add_argument("--text")
    ap.add_argument("--note")
    ap.add_argument("--key", help="a new fact's key")
    ap.add_argument("--frames", help="a new fact's frames, comma-separated")
    ap.add_argument("--says", action="append", help="replace the fact's `says` patterns (repeat; '' for none)")
    ap.add_argument("--retire", action="store_true", help="accept a contradiction by pausing the fact for good")
    ap.add_argument("--same-key", action="store_true",
                    help="accept a contradiction in place: the code that requires the fact still holds")
    ap.add_argument("--yes", action="store_true", help="don't ask before rejecting a contradiction")
    ap.add_argument("--local", action="store_true", help="read data/ instead of Mongo")
    args = ap.parse_args()
    config.load_env()
    store = LocalStore() if args.local else MongoStore()
    if args.list:
        list_all(store)
    elif args.accept or args.reject:
        ids = lambda s: [int(x) for x in (s or "").replace(" ", "").split(",") if x]
        accept, reject = ids(args.accept), ids(args.reject)
        kw = dict(text=args.text, note=args.note, key=args.key, retire=args.retire, same_key=args.same_key,
                  frames=args.frames.split(",") if args.frames else None,
                  says=[x for x in args.says if x] if args.says is not None else None)
        kw = {k: v for k, v in kw.items() if v not in (None, False)}
        if kw and len(accept) != 1:
            raise SystemExit("--text, --note, --key, --frames, --says, --retire and --same-key go with one --accept")
        props, done = store.proposals(), decided_ids()
        todo = []
        for pid, ok in [(i, True) for i in accept] + [(i, False) for i in reject]:
            p = props.get(pid)
            if not p or p.get("status") != "open" or pid in done:
                raise SystemExit(f"no open proposal #{pid}")
            todo.append((p, ok, kw if ok else {}))
        apply(store, todo, yes=args.yes)
    elif args.recheck:
        if args.recheck not in fact_store.TABLE:
            raise SystemExit(f"no fact {args.recheck!r}")
        before = FACTS.read_text()
        FACTS.write_text(factdesk.toml_set(before, args.recheck, checked=factdesk.stamp()))
        ok, tail = run_tests()
        if not ok:
            FACTS.write_text(before)
            raise SystemExit("The tests failed; nothing changed:\n  " + "\n  ".join(tail))
        print(f"Tests pass. git commit -m 'Facts: {args.recheck} re-checked' -- content/facts.toml && git push")
    else:
        interactive(store)


if __name__ == "__main__":
    main()
