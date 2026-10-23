"""scripts/rival_snapshot.py: which accounts a census snapshot re-reads (pure helpers; no network)."""
import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import rival_snapshot as rs  # noqa: E402

NOW = dt.datetime(2026, 10, 24, 12, 0, tzinfo=dt.timezone.utc)


def row(i, hours_old, err=None):
    posts = [] if hours_old is None else [{"id": i, "t": (NOW - dt.timedelta(hours=hours_old)).isoformat().replace("+00:00", "Z")}]
    return json.dumps({"account_id": i, "err": err, "posts": posts})


def test_live_ids_take_the_latest_appearance_and_skip_ours_and_errors(tmp_path):
    a, b = tmp_path / "rest.jsonl", tmp_path / "snap-1.jsonl"
    a.write_text("\n".join([row(5000, 2), row(5001, 30), row(5002, 1), row(5003, None), row(5004, 1, err="403")]) + "\n")
    b.write_text(row(5001, 3) + "\n" + row(5000, 40) + "\n")      # 5001 woke up, 5000 is stale in the later file
    assert rs.live_ids([a, b], ours={5002}, now=NOW, live_h=12) == [5001]
    assert rs.live_ids([a], ours=set(), now=NOW, live_h=12) == [5000, 5002]


def test_new_ids_are_readable_team_accounts_not_seen_before():
    rows = [{"account_id": 2000}, {"account_id": 6000}, {"account_id": 6001, "private": True}, {"account_id": 6002}]
    assert rs.new_ids({6000}, rows) == [6002]
