"""swan_bot/jsonl.py (streaming reader with a resumable cursor), the incremental Mongo sync (scripts/swan_sync_mongo.py,
against a fake db: no Mongo) and followup.load_rows streaming (todo/34: the whole-log reads that were OOM-killed)."""
import importlib.util
import json
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from swan_bot import analysis, config, followup, jsonl, watch  # noqa: E402

spec = importlib.util.spec_from_file_location("swan_sync_mongo", ROOT / "scripts" / "swan_sync_mongo.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def line(**rec):
    return json.dumps(rec) + "\n"


def write(path, *lines, mode="a"):
    with open(path, mode) as f:
        f.write("".join(lines))


# ---- the reader ------------------------------------------------------------------------------------------

def test_reads_records_and_counts_only_complete_lines(tmp_path):
    p = tmp_path / "a.jsonl"
    write(p, line(n=1), line(n=2), '{"n": 3')                       # the last line is half written
    r = jsonl.Reader(p)
    assert [x["n"] for x in r] == [1, 2]
    assert r.offset == len(line(n=1)) + len(line(n=2)), "the offset stops before the partial line"
    write(p, ', "x": 1}\n')                                         # ...and now it is finished
    r2 = jsonl.Reader(p, resume=r.cursor)
    assert list(r2) == [{"n": 3, "x": 1}]
    assert r2.offset == p.stat().st_size and not r2.reset


def test_skips_blank_bad_and_non_object_lines_but_consumes_them(tmp_path):
    p = tmp_path / "a.jsonl"
    p.write_bytes(line(n=1).encode() + b"\n" + b"{broken\n" + b"[1, 2]\n" + b"\xff\xfe\n" + b"7\n" + line(n=2).encode())
    r = jsonl.Reader(p)
    assert [x["n"] for x in r] == [1, 2]
    assert r.offset == p.stat().st_size


def test_contains_prefilter_parses_only_matching_lines(tmp_path):
    p = tmp_path / "a.jsonl"
    write(p, line(act="lost"), line(act="like", live=True), "not json but has \"live\" in it\n", line(act="wait"))
    r = jsonl.Reader(p, contains='"live"')
    assert [x["act"] for x in r] == ["like"]
    assert r.offset == p.stat().st_size, "lines the filter skipped are consumed too"


def test_missing_and_empty_files(tmp_path):
    r = jsonl.Reader(tmp_path / "none.jsonl")
    assert list(r) == [] and r.offset == 0 and not r.reset
    p = tmp_path / "e.jsonl"
    p.write_text("")
    r = jsonl.Reader(p)
    assert list(r) == [] and r.offset == 0
    gone = jsonl.Reader(tmp_path / "none.jsonl", resume={"offset": 50, "inode": 1, "head": "x"})
    assert list(gone) == [] and gone.reset and gone.offset == 0


def test_resume_reads_only_the_new_lines(tmp_path):
    p = tmp_path / "a.jsonl"
    write(p, line(n=1), line(n=2))
    r = jsonl.Reader(p)
    list(r)
    saved = json.loads(json.dumps(r.cursor))                        # it survives a round trip through the state file
    assert list(jsonl.Reader(p, resume=saved)) == []
    write(p, line(n=3))
    r2 = jsonl.Reader(p, resume=saved)
    assert [x["n"] for x in r2] == [3] and not r2.reset


def test_truncated_file_starts_again(tmp_path):
    p = tmp_path / "a.jsonl"
    write(p, line(n=1), line(n=2), line(n=3))
    r = jsonl.Reader(p)
    list(r)
    write(p, line(n=9), mode="w")                                   # copytruncate: same inode, smaller
    r2 = jsonl.Reader(p, resume=r.cursor)
    assert [x["n"] for x in r2] == [9] and r2.reset


def test_new_inode_starts_again(tmp_path):
    p = tmp_path / "a.jsonl"
    write(p, line(n=1), line(n=2))
    r = jsonl.Reader(p)
    list(r)
    p.rename(tmp_path / "a.jsonl.1")
    write(p, line(n=7), line(n=8), line(n=9))                       # bigger than the old offset, another file
    r2 = jsonl.Reader(p, resume=r.cursor)
    assert [x["n"] for x in r2] == [7, 8, 9] and r2.reset


def test_rewritten_file_with_the_same_inode_and_more_bytes_starts_again(tmp_path):
    p = tmp_path / "a.jsonl"
    write(p, line(n=1, pad="x" * 300), line(n=2, pad="x" * 300))
    r = jsonl.Reader(p)
    list(r)
    ino = os.stat(p).st_ino
    write(p, *[line(n=100 + i, pad="y" * 300) for i in range(5)], mode="r+")     # in place: inode kept, longer
    assert os.stat(p).st_ino == ino
    r2 = jsonl.Reader(p, resume=r.cursor)
    assert [x["n"] for x in r2] == [100, 101, 102, 103, 104] and r2.reset


def test_stopping_early_keeps_the_offset_of_what_was_consumed(tmp_path):
    p = tmp_path / "a.jsonl"
    write(p, line(n=1), line(n=2), line(n=3))
    r = jsonl.Reader(p)
    for rec in r:
        if rec["n"] == 2:
            break
    assert r.offset == len(line(n=1)) + len(line(n=2))


# ---- the incremental sync --------------------------------------------------------------------------------

class FakeDb:
    """db[name].bulk_write(ops, ordered=False) recorded as (collection, op class, filter, doc/update); fail_on raises."""

    def __init__(self, fail_on=None):
        self.writes, self.fail_on = [], fail_on

    def __getitem__(self, name):
        db = self

        class Coll:
            def bulk_write(self, ops, ordered=True):
                assert ordered is False
                if db.fail_on == name:
                    raise RuntimeError("Atlas is down")
                for op in ops:
                    db.writes.append((name, type(op).__name__, op._filter, op._doc))
        return Coll()


@pytest.fixture
def logs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOGS", tmp_path / "logs")
    monkeypatch.setattr(config, "ACTIONS_LOG", tmp_path / "logs" / "swan_actions.jsonl")
    monkeypatch.setattr(config, "OUTCOMES_LOG", tmp_path / "logs" / "swan_outcomes.jsonl")
    monkeypatch.setattr(config, "FOLLOWUPS_LOG", tmp_path / "logs" / "swan_followups.jsonl")
    monkeypatch.setattr(config, "LAB_DIR", tmp_path / "lab")
    (tmp_path / "logs").mkdir()
    (tmp_path / "lab").mkdir()
    return tmp_path


def live(ts, act="reply", post_id=1, **kw):
    return {**dict(ts=ts, act=act, live=True, post_id=post_id, username="u", persona="p", frame="F", target_author=7,
                   password="hunter2"), **kw}


def seed(logs):
    write(config.ACTIONS_LOG, line(**live("t1", post_id=1)), line(**live("t2", act="repost", post_id=2)),
          line(ts="t3", act="reject", why="x"), line(ts="t4", act="refresh", candidates=3),
          line(ts="t5", act="lost", why="gone"), line(ts="t6", act="amp_measure", post_id=5))
    write(config.OUTCOMES_LOG, line(ts="o1", act="outcome", post_id=1, account_id=3, views=4))
    write(config.FOLLOWUPS_LOG, line(ts="f1", act="followup", post_id=1, check=0, label="silent"))
    write(logs / "logs" / "blue_reports.jsonl", line(ts="b1", act="report", key="k"))
    write(config.LAB_DIR / "trials.jsonl", line(ts="l1", strategy="s", persona="p", seed=0))


def run(logs, db, full=False):
    return sync.sync(db, full=full, cursor_file=logs / "cursors.json")


def test_first_run_copies_everything_with_the_same_keys_and_no_secrets(logs):
    seed(logs)
    db = FakeDb()
    sink = run(logs, db)
    by = {}
    for name, op, filt, doc in db.writes:
        by.setdefault(name, []).append((op, filt))
    assert by["actions"] == [("ReplaceOne", {"post_id": 1}), ("ReplaceOne", {"post_id": 2})]
    assert by["experiments"] == [("ReplaceOne", {"post_id": 1})], "reposts have no experiment doc"
    assert by["contacted"] == [("UpdateOne", {"citizen_id": 7})]
    assert by["rejects"] == [("ReplaceOne", {"ts": "t3"})] and by["activity"] == [("ReplaceOne", {"ts": "t4"})]
    assert ("ReplaceOne", {"ts": "t6", "act": "amp_measure"}) in by["post_outcomes"]
    assert ("ReplaceOne", {"ts": "o1", "act": "outcome", "post_id": 1, "account_id": 3}) in by["post_outcomes"]
    assert by["followups"] == [("ReplaceOne", {"post_id": 1, "check": 0})]
    assert by["blue"] == [("ReplaceOne", {"ts": "b1", "act": "report", "key": "k"})]
    assert by["lab_trials"] == [("ReplaceOne", {"ts": "l1", "strategy": "s", "persona": "p", "seed": 0})]
    assert not any("password" in str(w[3]) or "hunter2" in str(w[3]) for w in db.writes)
    assert sink.n["actions"] == 2 and sink.n["post_outcomes"] == 2


def test_second_run_sends_nothing_and_new_rows_are_sent(logs):
    seed(logs)
    run(logs, FakeDb())
    db = FakeDb()
    assert run(logs, db).n == {} and db.writes == []
    write(config.ACTIONS_LOG, line(**live("t9", post_id=9)), line(ts="t10", act="skip"))
    write(config.OUTCOMES_LOG, line(ts="o2", act="outcome", post_id=9, account_id=3))
    sink = run(logs, db)
    assert [(w[0], w[2]) for w in db.writes] == [("actions", {"post_id": 9}), ("experiments", {"post_id": 9}),
                                                  ("contacted", {"citizen_id": 7}),
                                                  ("post_outcomes", {"ts": "o2", "act": "outcome", "post_id": 9,
                                                                    "account_id": 3})]
    assert sink.n == {"actions": 1, "experiments": 1, "contacted": 1, "post_outcomes": 1}


def test_a_later_line_for_the_same_key_still_wins(logs):
    """Likes carry the liked post's id: two rows, one key. The newer replaces the older, as in a full re-read."""
    write(config.ACTIONS_LOG, line(**live("t1", act="like", post_id=4, username="a")))
    run(logs, FakeDb())
    write(config.ACTIONS_LOG, line(**live("t2", act="like", post_id=4, username="b")))
    db = FakeDb()
    run(logs, db)
    assert [(w[0], w[2], w[3]["username"]) for w in db.writes if w[0] == "actions"] == [("actions", {"post_id": 4}, "b")]


def test_cursor_is_not_saved_when_a_bulk_write_raises(logs):
    seed(logs)
    with pytest.raises(RuntimeError):
        run(logs, FakeDb(fail_on="followups"))
    state = json.loads((logs / "cursors.json").read_text())["files"]
    assert set(state) == {"actions", "outcomes"}, "logs before the failing one are done; it and the rest are not"
    db = FakeDb()
    run(logs, db)
    assert {w[0] for w in db.writes} == {"followups", "blue", "lab_trials"}, "the retry sends only what was not saved"


def test_chunks_are_flushed_and_a_failed_chunk_replays_whole(logs, monkeypatch):
    monkeypatch.setattr(sync, "CHUNK", 3)
    write(config.ACTIONS_LOG, *[line(**live(f"t{i}", act="like", post_id=i)) for i in range(1, 8)])
    db = FakeDb()
    sink = run(logs, db)
    assert sink.n["actions"] == 7 and sink.n["experiments"] == 7
    assert sum(1 for w in db.writes if w[0] == "actions") == 7
    assert all(len(v) < 3 for v in sink.ops.values()), "nothing is left buffered"


def test_truncated_log_is_read_from_the_start(logs):
    seed(logs)
    run(logs, FakeDb())
    write(config.ACTIONS_LOG, line(**live("t20", post_id=20)), mode="w")        # rotated: smaller than the cursor
    db = FakeDb()
    run(logs, db)
    assert [(w[0], w[2]) for w in db.writes if w[0] == "actions"] == [("actions", {"post_id": 20})]


def test_full_resends_everything(logs):
    seed(logs)
    run(logs, FakeDb())
    db = FakeDb()
    run(logs, db, full=True)
    assert {w[0] for w in db.writes} >= {"actions", "rejects", "followups", "blue", "lab_trials", "post_outcomes"}
    assert sum(1 for w in db.writes if w[0] == "actions") == 2


def test_a_changed_mapping_resyncs_from_the_start(logs, monkeypatch):
    seed(logs)
    run(logs, FakeDb())
    monkeypatch.setattr(sync, "SCHEMA", sync.SCHEMA + 1)
    db = FakeDb()
    run(logs, db)
    assert sum(1 for w in db.writes if w[0] == "actions") == 2


def test_a_half_written_last_line_waits_for_the_rest(logs):
    write(config.ACTIONS_LOG, line(**live("t1", post_id=1)), json.dumps(live("t2", post_id=2))[:40])
    db = FakeDb()
    run(logs, db)
    assert [w[2] for w in db.writes if w[0] == "actions"] == [{"post_id": 1}]
    write(config.ACTIONS_LOG, json.dumps(live("t2", post_id=2))[40:] + "\n")
    db = FakeDb()
    run(logs, db)
    assert [w[2] for w in db.writes if w[0] == "actions"] == [{"post_id": 2}]


# ---- followup.load_rows ----------------------------------------------------------------------------------

def old_load_rows(path):
    rows = []
    for ln in path.read_text().splitlines():
        try:
            rows.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return rows


def test_followup_rows_stream_and_match_the_old_read(logs):
    write(config.ACTIONS_LOG,
          line(ts="2026-10-23T01:00:00+00:00", act="refresh", candidates=3),
          line(**live("2026-10-23T01:01:00+00:00", act="reply", post_id=11, target_text="a 'live' word", text="long")),
          line(ts="2026-10-23T01:02:00+00:00", act="like", live=False, post_id=12),
          "{broken\n",
          line(ts="2026-10-23T01:03:00+00:00", act="like", live=True, post_id=13, account_id=5, persona="kai"),
          line(ts="2026-10-23T01:04:00+00:00", act="lost", why="gone", text="live"),
          line(**live("2026-10-23T01:05:00+00:00", act="post", post_id=14, account_id=6)),
          json.dumps(live("2026-10-23T01:06:00+00:00", post_id=15))[:30])
    old = old_load_rows(config.ACTIONS_LOG)
    new = followup.load_rows()
    assert new == [{k: r[k] for k in followup.ROW_FIELDS if k in r} for r in old if r.get("live")]
    assert all("context" not in r and "text" not in r for r in new), "cut to the fields run() reads"
    now = analysis.ts_of("2026-10-24T00:00:00+00:00")
    state = {"outcome": {}, "followup": {}}
    assert followup.our_post_ids(new) == followup.our_post_ids(old) == {11, 14}
    got = followup.due(new, state, now)
    assert got and got == [(late, kind, i, {k: r[k] for k in followup.ROW_FIELDS if k in r})
                           for late, kind, i, r in followup.due(old, state, now)]


def test_followup_rows_of_a_missing_log(logs):
    assert followup.load_rows() == []


# ---- scripts/swan_watch.py: one streamed pass instead of the whole log in a list ---------------------------

def test_watch_scan_matches_the_old_whole_file_computation(logs):
    base = analysis.ts_of("2026-10-23T01:00:00+00:00")
    iso = lambda dt_s: analysis.dt.datetime.fromtimestamp(base + dt_s, analysis.dt.timezone.utc).isoformat()
    write(config.ACTIONS_LOG,
          line(**live(iso(0), post_id=1, username="a")),
          line(**live(iso(10), act="like", post_id=1, username="a")),                  # a like: counted, not a write
          line(**live(iso(20), act="reply", post_id=1, username="a")),                 # post 1 again, later
          line(**live(iso(30), act="post", post_id=2, username="b")),
          line(**live(iso(5000), act="post", post_id=3, username="b")),               # too new to be listed
          line(ts=iso(40), act="lost", why="the word \"live\" appears only in the text", text="live", username="a"),
          line(ts=iso(41), act="reply", live=False, post_id=9, username="a", text="\"live\": true"),
          line(**live("not a time", post_id=4, username="a")),                        # bad ts: counted, not logged
          line(**live(iso(50), act="amp_plan", post_id=100)),
          line(**live(iso(51), act="amp_plan", post_id=101)),
          line(ts=iso(52), act="amp_plan", live=False, post_id=102),
          "{broken\n",
          *[line(**live(iso(60 + i), act="amp_plan", post_id=200 + i)) for i in range(10)],
          line(**live(iso(80), act="repost", post_id=5, username="c")),
          json.dumps(live(iso(90), post_id=6, username="a"))[:40])                     # half written
    now = base + 1000

    rows = old_load_rows(config.ACTIONS_LOG)                                            # the old computation
    old_logged = watch.logged_posts(rows, now)
    old_actions = lambda u: sum(1 for r in rows if r.get("live") and r.get("username") == u)
    old_plans = [r["post_id"] for r in rows if r.get("act") == "amp_plan" and r.get("live") and r.get("post_id")]

    scan = watch.LogScan()
    for r in jsonl.Reader(config.ACTIONS_LOG, contains='"live"'):
        scan.add(r)
    assert scan.logged_posts(now) == old_logged == {"a": {1}, "b": {2}, "c": {5}}
    assert [scan.actions[u] for u in ("a", "b", "c", "nobody")] == [old_actions(u) for u in ("a", "b", "c", "nobody")]
    assert scan.actions["a"] == 4
    assert list(scan.plans) == old_plans[-watch.RING_OURS:]


def test_experiment_report_local_load_matches_the_old_one(logs):
    rep_spec = importlib.util.spec_from_file_location("experiment_report", ROOT / "scripts" / "experiment_report.py")
    rep = importlib.util.module_from_spec(rep_spec)
    rep_spec.loader.exec_module(rep)

    def old_load_local(since, dry_runs):                          # as it was before 23 Oct: the whole log in a list
        rows = rep.jsonl(config.ACTIONS_LOG)
        if dry_runs:
            writes = [dict(r, mode=r["act"], post_id=f"dry{i}") for i, r in enumerate(rows)
                      if r["act"] in ("post", "reply", "second_voice", "journalist", "reply_back") and not r.get("live")]
        else:
            writes = [dict(r, mode=r["act"]) for r in rows if r.get("live") and r.get("post_id") and r["act"] != "repost"]
        outcomes = rep.jsonl(config.OUTCOMES_LOG) + [r for r in rows if r["act"] == "amp_measure"]
        return ([w for w in writes if rep.ts_of(w["ts"]) >= since], rep.jsonl(config.FOLLOWUPS_LOG), outcomes, [])

    write(config.ACTIONS_LOG,
          line(ts="2026-10-23T01:00:00+00:00", act="refresh"),
          line(ts="2026-10-23T01:01:00+00:00", act="reply", live=False, post_id=None, text="dry"),
          "{broken\n",
          line(**live("2026-10-23T01:02:00+00:00", post_id=1)),
          line(**live("2026-10-23T01:03:00+00:00", act="repost", post_id=2)),
          line(ts="2026-10-23T01:04:00+00:00", act="amp_measure", post_id=5, views=3),
          line(ts="2026-10-22T01:05:00+00:00", act="post", live=False, post_id=None),
          line(**live("2026-10-22T01:06:00+00:00", post_id=3)),
          line(ts="2026-10-23T01:07:00+00:00", act="journalist", live=False, post_id=None))
    write(config.OUTCOMES_LOG, line(ts="o1", act="outcome", post_id=1))
    write(config.FOLLOWUPS_LOG, line(ts="f1", act="followup", post_id=1, check=0))
    since = analysis.ts_of("2026-10-23T00:00:00+00:00")
    for dry in (False, True):
        got = rep.load_local(since, dry)
        assert got == old_load_local(since, dry) and got[0], dry
