"""swan_bot/pattern_audit.py and scripts/pattern_audit.py (todo/38): metric maths on hand-built logs, the grades of the two
simulated pools (the old rota is red, a mixed pool is green), the CLI output and absent data."""
import datetime as dt
import importlib.util
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from swan_bot import pattern_audit as pa  # noqa: E402

NOW = dt.datetime(2026, 10, 23, 10, 0, tzinfo=dt.timezone.utc).timestamp()
CANARY = "CANARY-password-5d1e"


def iso(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat()


def row(t, user, act="reply", **kw):
    return dict(ts=iso(t), act=act, live=True, username=user, persona=user[:2], **kw)


def voice_rows(user, gaps_s, start=NOW - 20 * 3600):
    t, out = start, []
    for g in gaps_s:
        out.append(row(t, user))
        t += g
    out.append(row(t, user))
    return out


# ---- metric maths on small hand-built inputs ----
def test_gap_stats_metronome_vs_spread():
    cv, ent, modal = pa.gap_stats([240.0] * 20)
    assert cv == 0 and ent == 0 and modal == 1.0
    spread = [60, 90, 150, 240, 400, 700, 1100, 1900, 2500, 130, 310, 520]            # seconds, all over the place
    cv, ent, modal = pa.gap_stats(spread)
    assert cv > 0.9 and ent > 3 and modal <= 0.25
    assert pa.gap_stats([240.0] * 3) == (None, None, None)                             # too few gaps: no figure


def test_modal_share_counts_gaps_within_ten_percent_of_the_mode():
    gaps = [240] * 5 + [255, 225, 100, 500, 900, 1200, 60]                              # 7 of 12 within +-10% of 240
    assert pa.gap_stats(gaps)[2] == pytest.approx(7 / 12)


def test_awake_stretch_ends_at_a_long_pause():
    times = [0, 600, 1200, 1800, 1800 + 3 * 3600, 1800 + 3 * 3600 + 600]
    assert pa.awake_stretch_s(times) == 1800


def test_voice_stats_hours_and_sleep_window():
    start = NOW - 24 * 3600
    times = [start + h * 3600 + 600 for h in range(24) if h < 8 or h >= 16]             # silent for 8 h in the middle
    st = pa.voice_stats(times, start, NOW)
    assert st["hours_active"] == 16 and 7 <= st["awake_h"] <= 8.5
    assert len(st["sleep"]) in (8, 9)                                          # the 9 h between the last write at 07:10 and the next at 16:10
    every = pa.voice_stats([start + h * 3600 + 5 for h in range(24)], start, NOW)
    assert every["hours_active"] == 24 and every["sleep"] == set()


def test_pair_corr_is_one_for_lockstep_and_near_zero_for_strangers():
    a = set(range(0, 1440, 10))
    assert pa.pair_corr({"a": a, "b": set(a)}, 1440) == [pytest.approx(1.0)]
    b = set(range(5, 1440, 10))
    assert pa.pair_corr({"a": a, "b": b}, 1440)[0] < 0                                  # a rota never overlaps: slightly negative


def test_near_write_share_and_chance():
    ev = [(0, "a", "x", 1), (10, "b", "x", 2), (500, "a", "x", 3), (2000, "b", "x", 4)]
    share, exp = pa.near_write(ev)
    assert share == 0.5 and 0 < exp < 0.1                                                # one pair within 30 s of four writes


def test_multi_voice_needs_two_voices_inside_ten_minutes():
    ev = []
    for c in range(30):
        ev.append((c * 5000.0, "a", "x", c))
    ev += [(5 * 5000.0 + 300, "b", "x", 5), (7 * 5000.0 + 3000, "b", "x", 7), (9 * 5000.0 + 60, "a", "x", 9)]
    share, n, hits = pa.multi_voice(sorted(ev))
    assert (n, hits) == (30, 1) and share == pytest.approx(1 / 30)                       # 5 yes; 7 too late; 9 is the same voice
    assert pa.multi_voice(ev[:10])[0] is None                                            # under 20 citizens: no figure


def test_handle_shapes_and_derivability():
    assert pa.handle_shape("marcotaufa") == "a" and pa.handle_shape("lucy.pulu") == "a.a"
    assert pa.handle_shape("vika_i92") == "a_aN2" and pa.handle_shape("kai_nakamura_dev76") == "a_a_aN2"
    assert pa.name_derived("owen_bakes", "Owen Faleafa") is True and pa.name_derived("kai72", "Owen Faleafa") is False
    assert pa.name_derived("x", None) is None
    ident = pa.identity_stats(["sam_t18", "liam_f70", "rua90", "ella.latu"], {})
    assert ident["two_digit_share"] == 0.75 and ident["top_shape_share"] == 0.5 and ident["suffix_digits"] == {"0": 1, "2": 3}


def test_registration_spacing_clusters_and_instant_first_writes():
    created = {f"u{i}": NOW - 3600 * (50 - 10 * i) for i in range(5)}                   # every 10 h, nothing clustered
    first = {u: c + 6 * 3600 for u, c in created.items()}
    reg = pa.registration_stats(created, [], first, NOW)
    assert reg["reg_cluster"] == 0 and reg["reg_gap_cv"] == pytest.approx(0, abs=1e-9)
    assert reg["instant_write"] == 0 and reg["median_first_write_min"] == pytest.approx(360)
    batch = {f"b{i}": NOW - 3600 + i * 60 for i in range(6)}
    reg = pa.registration_stats(batch, [], {u: c + 30 for u, c in batch.items()}, NOW)
    assert reg["reg_cluster"] == 1.0 and reg["instant_write"] == 1.0
    assert pa.registration_stats({"a": NOW - 100}, [], {}, NOW)["reg_gap_cv"] is None   # too few


def test_grade_and_score_follow_the_one_table():
    gap = pa.SPEC["gap_cv"]                                                               # higher is better: green 0.5, red 0.25
    assert [pa.grade_of(gap, v) for v in (1.0, 0.5, 0.4, 0.25, 0.1, None)] == ["green", "green", "amber", "amber", "red", "grey"]
    assert pa.score_of(gap, 0.9) == 100 and pa.score_of(gap, 0.5) == pytest.approx(70) and pa.score_of(gap, 0.25) == pytest.approx(35)
    assert pa.score_of(gap, 0.0) == 0
    modal = pa.SPEC["modal_gap"]                                                          # lower is better
    assert [pa.grade_of(modal, v) for v in (0.1, 0.25, 0.3, 0.45, 0.46)] == ["green", "green", "amber", "amber", "red"]
    assert pa.score_of(modal, 0.25) == pytest.approx(70)
    for s in pa.SPECS:                                                                    # every row's four numbers run the right way
        xs = [pa._x(s, v) for v in (s.ideal, s.green, s.red, s.worst)]
        assert xs == sorted(xs) and s.weight > 0, s.key


def test_composite_is_a_weighted_mean_and_a_red_stops_green():
    ok = {s.key: s.ideal for s in pa.SPECS}
    assert pa.composite(ok) == (100, "green")
    one_red = dict(ok, gap_cv=0.01)
    score, grade = pa.composite(one_red)
    assert score > 70 and grade == "amber"                                                 # a high mean cannot hide a red metric
    assert pa.composite({"gap_cv": 0.5}) == (None, "grey")                                 # too little data


def test_hand_built_log_metronome_voices_grade_red_on_timing():
    rows = []
    for i, u in enumerate(("amy", "bo", "cat", "dee")):
        rows += voice_rows(u, [240 + i] * 350, start=NOW - 23.5 * 3600)        # 4 min +-, awake all day, every voice
    rep = pa.audit(rows, [], NOW)
    m = rep["metrics"]
    assert m["gap_cv"]["grade"] == "red" and m["modal_gap"]["grade"] == "red" and m["modal_gap"]["value"] == 1.0
    assert m["sleep_overlap"]["grade"] == "grey"                                           # nobody sleeps: nothing to compare
    assert [o["voice"] for o in rep["worst_voices"]] and len(rep["worst_voices"]) == 3
    assert set(rep["voices"]) == {"amy", "bo", "cat", "dee"}


def test_dry_and_failed_rows_are_not_writes():
    rows = [row(NOW - 100, "(dry)amy"), dict(row(NOW - 90, "amy"), live=False), row(NOW - 80, "amy", act="like"), row(NOW - 70, "amy")]
    assert [e[1] for e in pa.write_events(rows)] == ["amy"]


# ---- the two simulated pools ----
def test_simulation_is_deterministic():
    a = pa.simulate_pool(10, 6, seed=3, scheduler="mixed")
    assert a == pa.simulate_pool(10, 6, seed=3, scheduler="mixed") and a != pa.simulate_pool(10, 6, seed=4, scheduler="mixed")
    with pytest.raises(ValueError):
        pa.simulate_pool(5, 1, 1, "nope")


@pytest.mark.parametrize("n,seed", [(14, 1), (30, 2)])
def test_old_rota_grades_red(n, seed):
    rows, accounts, now = pa.simulate_pool(n, 48, seed, "old")
    rep = pa.audit(rows, accounts, now)
    m = rep["metrics"]
    assert rep["grade"] == "red" and rep["stealth_score"] < 35
    assert m["gap_cv"]["value"] < 0.05 and m["modal_gap"]["value"] > 0.9 and m["hours_active"]["value"] == 24
    assert m["pair_corr"]["grade"] == "red" and m["instant_write"]["grade"] == "red" and m["handle_shape"]["grade"] == "red"
    assert abs(rep["per_min"] - 2.9) < 0.1                                                  # it does hit the volume target
    assert len(rep["worst_voices"]) == 3 and rep["worst_voices"][0]["score"] <= 5
    assert rep["worst_metrics"] and all(rep["metrics"][k]["grade"] != "green" for k in rep["worst_metrics"])


@pytest.mark.parametrize("n,seed", [(30, 1), (30, 2), (24, 3)])
def test_mixed_pool_grades_green(n, seed):
    rows, accounts, now = pa.simulate_pool(n, 48, seed, "mixed")
    rep = pa.audit(rows, accounts, now)
    m = rep["metrics"]
    assert rep["grade"] == "green" and rep["stealth_score"] >= 80
    assert m["modal_gap"]["grade"] == "green" and m["gap_cv"]["grade"] == "green"
    assert m["pair_corr"]["grade"] == "green" and m["instant_write"]["grade"] == "green" and m["multi_voice"]["grade"] == "green"
    assert not any(v["grade"] == "red" for v in m.values())
    assert rep["per_min"] >= 0.8 * 2.9                                                     # honest volume too
    assert len(rep["hourly"]) == 24 and sum(h["writes"] for h in rep["hourly"]) == rep["writes"]


def test_the_two_pools_are_far_apart():
    old = pa.audit(*pa.simulate_pool(30, 48, 5, "old")[:2], pa.simulate_pool(30, 48, 5, "old")[2])
    mixed = pa.audit(*pa.simulate_pool(30, 48, 5, "mixed")[:2], pa.simulate_pool(30, 48, 5, "mixed")[2])
    assert mixed["stealth_score"] - old["stealth_score"] > 50


# ---- absent data ----
def test_empty_inputs_give_a_grey_report_not_an_error():
    rep = pa.audit([], [], NOW)
    assert rep["grade"] == "grey" and rep["stealth_score"] is None and rep["writes"] == 0
    assert rep["worst_voices"] == [] and rep["worst_metrics"] == [] and all(m["grade"] == "grey" for m in rep["metrics"].values())
    json.dumps(rep)
    pa.table(rep)


def test_few_voices_are_not_graded_on_pool_figures():
    rep = pa.audit(voice_rows("amy", [240] * 40) + voice_rows("bo", [250] * 40), [], NOW)
    assert rep["metrics"]["gap_cv"]["grade"] == "grey" and rep["voices_graded"] == 2         # two voices: a pool figure needs three


# ---- the CLI ----
def load_cli():
    spec = importlib.util.spec_from_file_location("pattern_audit_cli", ROOT / "scripts" / "pattern_audit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cli_writes_valid_json_and_never_a_secret(tmp_path, capsys):
    cli = load_cli()
    rows, accounts, now = pa.simulate_pool(12, 30, 7, "mixed")
    log = tmp_path / "swan_actions.jsonl"
    extra = [dict(ts=iso(now - 50), act="lost", why="no_model", text="x" * 50), dict(ts=iso(now - 40), act="like", username="amy")]
    log.write_text("".join(json.dumps(r) + "\n" for r in rows + extra))
    recs = tmp_path / "swan_accounts.json"
    recs.write_text(json.dumps([dict(a, password=CANARY, token=CANARY + "-t", followed=[1, 2], day_writes=[1.0]) for a in accounts]))
    out = tmp_path / "data" / "pattern_audit.json"
    assert cli.main(["--actions", str(log), "--accounts", str(recs), "--now", iso(now), "--out", str(out)]) == 0
    text = out.read_text()
    assert CANARY not in text and "password" not in text and "token" not in text and "followed" not in text
    assert CANARY not in capsys.readouterr().out
    rep = json.loads(text)
    assert rep["grade"] in ("green", "amber", "red") and 0 <= rep["stealth_score"] <= 100
    assert set(rep["metrics"]) == {s.key for s in pa.SPECS} and not list(out.parent.glob("*.tmp*"))   # atomic: no temp file left


def test_cli_with_nothing_to_read_still_writes_a_grey_report(tmp_path):
    cli = load_cli()
    out = tmp_path / "audit.json"
    assert cli.main(["--actions", str(tmp_path / "none.jsonl"), "--accounts", str(tmp_path / "none.json"), "--out", str(out)]) == 0
    assert json.loads(out.read_text())["grade"] == "grey"
    assert cli.main(["--actions", str(tmp_path / "none.jsonl"), "--accounts", str(tmp_path / "none.json"), "--out", str(tmp_path / "x.json"), "--no-write"]) == 0
    assert not (tmp_path / "x.json").exists()
