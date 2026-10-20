"""Import the portal's activity log (exported by hand: automation is open question 6) into Mongo `portal_activity`.

    python scripts/import_activity.py ~/Downloads/activity.csv --dry       # parse and print, write nothing
    python scripts/import_activity.py ~/Downloads/activity.csv             # upsert into Mongo (idempotent)
    python scripts/import_activity.py activity.csv --tz Australia/Perth    # if the export's times are Perth time

Each row becomes {ts (UTC ISO), hour, category, multiplier, points, text, views, likes, ..., towards, away, neither}
(swan_bot/analysis.parse_activity). The columns are found by name: a time column (time/date/when/timestamp),
the description (the cell that reads like "NPC engagement (×2 points): ...") and points if present. Naive times are
read in --tz (default Australia/Sydney, the portal's competition clock).
"""
import argparse
import collections
import csv
import datetime as dt
import hashlib
import json
import pathlib
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from swan_bot.analysis import parse_activity  # noqa: E402

FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y, %H:%M:%S",
           "%d/%m/%Y, %I:%M:%S %p", "%d/%m/%Y %I:%M %p", "%b %d, %Y, %I:%M:%S %p", "%d %b %Y %H:%M")


def parse_time(text, tz):
    text = (text or "").strip()
    try:
        t = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        for f in FORMATS:
            try:
                t = dt.datetime.strptime(text, f)
                break
            except ValueError:
                continue
        else:
            return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=tz)
    return t.astimezone(dt.timezone.utc)


def columns(header, sample):
    """(time column, text column, points column or None), by header name, else by what the cells look like."""
    low = [h.lower() for h in header]
    when = next((i for i, h in enumerate(low) if any(w in h for w in ("time", "date", "when"))), None)
    text = next((i for i, v in enumerate(sample) if ":" in v and any(w in v for w in
                 ("engagement", "Moderation", "Narrative", "view", "change of mind"))), None)
    if text is None:
        text = next((i for i, h in enumerate(low) if any(w in h for w in ("activity", "description", "detail",
                                                                            "event", "message"))), None)
    points = next((i for i, h in enumerate(low) if "point" in h or "score" in h), None)
    return when, text, points


def read(path, tz):
    with open(path, newline="") as f:
        rows = list(csv.reader(f))
    if len(rows) < 2:
        raise SystemExit("no rows")
    header, body = rows[0], [r for r in rows[1:] if any(c.strip() for c in r)]
    when, text, points = columns(header, body[0])
    if when is None or text is None:
        raise SystemExit(f"can't find the time and description columns in {header}; pass a CSV with headers")
    out, bad = [], 0
    for r in body:
        t = parse_time(r[when], tz)
        if t is None:
            bad += 1
            continue
        doc = {"ts": t.isoformat(), "hour": t.replace(minute=0, second=0, microsecond=0).isoformat(),
               "text": r[text], **parse_activity(r[text])}
        if points is not None:
            try:
                doc["points"] = float(r[points].replace(",", ""))
            except ValueError:
                doc["points"] = None
        doc["_id"] = hashlib.sha1(json.dumps([r[when], r[text], doc.get("points")]).encode()).hexdigest()[:20]
        out.append(doc)
    if bad:
        print(f"skipped {bad} rows with an unreadable time")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--tz", default="Australia/Sydney", help="time zone of naive times in the export")
    ap.add_argument("--dry", action="store_true", help="parse and print; write nothing")
    args = ap.parse_args()
    docs = read(args.csv, ZoneInfo(args.tz))
    hours = collections.defaultdict(collections.Counter)
    for d in docs:
        hours[d["hour"]].update({k: d[k] for k in ("towards", "neither", "away", "views", "likes") if d.get(k)})
    print(f"{len(docs)} rows, {len(hours)} hours. hour (UTC) | towards | neither | away | views | likes")
    for h in sorted(hours):
        c = hours[h]
        print(f"  {h[:16]} | {c['towards']:3} | {c['neither']:3} | {c['away']:3} | {c['views']:4} | {c['likes']:3}")
    unknown = collections.Counter(k for d in docs for k in d if k.startswith("other:"))
    if unknown:
        print("unrecognised items (check the parser):", dict(unknown))
    if args.dry:
        return
    from swan_sync_mongo import connect           # same credentials as the sync
    from pymongo import ReplaceOne
    db = connect()
    db.portal_activity.bulk_write([ReplaceOne({"_id": d["_id"]}, d, upsert=True) for d in docs], ordered=False)
    print(f"upserted {len(docs)} rows into portal_activity")


if __name__ == "__main__":
    main()
