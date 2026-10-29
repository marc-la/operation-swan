"""scripts/flip_audit.py (todo/52 WS8): the sample of flip replies, the judge's page, the tally by fear, proof and turn."""
import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import flip_audit  # noqa: E402

NOW = dt.datetime(2026, 10, 29, 13, 0, tzinfo=dt.timezone.utc)


def row(i, flip="hospitals/surge_drill/no_staff", live=True, act="reply", hours_ago=2):
    return dict(ts=(NOW - dt.timedelta(hours=hours_ago)).isoformat(), act=act, live=live, flip=flip, flip_fear=1,
                read_stance="yes_but", target_text=f"post {i}", text=f"reply {i}")


def test_sample_takes_live_flip_replies_of_the_window(tmp_path):
    log = tmp_path / "a.jsonl"
    rows = [row(i) for i in range(5)] + [row(9, live=False), row(10, act="reply_back"), row(11, hours_ago=30),
                                         dict(row(12), flip=None)]
    log.write_text("".join(json.dumps(r) + "\n" for r in rows))
    items = flip_audit.sample(log, n=10, now=NOW, seed=1)
    assert sorted(it["post"] for it in items) == [f"post {i}" for i in range(5)]
    assert len(flip_audit.sample(log, n=3, now=NOW, seed=1)) == 3


def test_the_page_carries_the_rubric_and_the_answer_format():
    page = flip_audit.render([dict(i=0, flip="a/b/c", stance="yes_but", post="their words", reply="our words")])
    assert all(f"**{k}**" in page for k in flip_audit.RUBRIC) and '"i": N' in page
    assert "Their post: their words" in page and "Our reply: our words" in page


def test_tally_by_fear_proof_and_turn():
    items = [dict(i=0, flip="hospitals/surge_drill/islands"), dict(i=1, flip="hospitals/contained_case/no_end"),
             dict(i=2, flip="conditional_yes/wastewater_caught/no_end")]
    ok = {k: True for k in flip_audit.RUBRIC}
    verdicts = [dict(ok, i=0, specific=False, note="islands turn for a hospital post"), dict(ok, i=1),
                dict(ok, i=2, tasteful=False, no_invention=False, note="you'd lose the early warning"), dict(ok, i=7)]
    r = flip_audit.tally(items, verdicts)
    assert r["n"] == 3 and r["fails"] == {"specific": 1, "tasteful": 1, "no_invention": 1}
    assert r["by"]["turn"]["islands"]["specific"] == 1 and r["by"]["fear"]["hospitals"]["n"] == 2
    assert len(r["notes"]) == 2


def test_main_round_trip(tmp_path, capsys):
    log, items, verdicts = tmp_path / "a.jsonl", tmp_path / "items.jsonl", tmp_path / "v.jsonl"
    log.write_text("".join(json.dumps(row(i)) + "\n" for i in range(3)))
    flip_audit.main(["sample", "--log", str(log), "--out", str(items), "--seed", "2"], now=NOW)
    assert "# Flip audit" in capsys.readouterr().out
    verdicts.write_text("".join(json.dumps(dict({k: True for k in flip_audit.RUBRIC}, i=it["i"])) + "\n"
                                for it in flip_audit.read_jsonl(items)))
    flip_audit.main(["tally", str(items), str(verdicts)])
    assert capsys.readouterr().out.startswith("3 judged; failed: none")
