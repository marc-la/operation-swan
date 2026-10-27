"""todo/49 (27 Oct): the value pick. swan_bot/value.py (expected points at landing), its place in Targeter.next_target behind
config.VALUE_PICK and the arm_pick switchback, the class on lost funnel records, and scripts/value_table.py's fit and replay.
No network."""
import datetime as dt
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from swan_bot import bot, config, experiment, targeting, value  # noqa: E402

spec = importlib.util.spec_from_file_location("value_table", ROOT / "scripts" / "value_table.py")
vt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vt)

NOW = 1_800_000_000.0
BLOCK = config.PICK_BLOCK_S


def cand(minutes, cls="conditions", now=NOW):
    made = dt.datetime.fromtimestamp(now - 60 * minutes, dt.timezone.utc).isoformat()
    return {"post": {"post_id": 1, "author_id": 100, "created_at": made}, "target_class": cls}


# ---- the table ----
def test_the_shipped_table_is_valid_and_never_rises_with_age():
    assert value.valid(value.DEFAULT)
    for g in value.NEEDED:
        pts = [value.curve(value.DEFAULT["curves"][g], m) for m in (0, 0.5, 1, 2, 3, 5, 8, 15, 40, 200, 2000)]
        assert all(b <= a + 1e-9 for a, b in zip(pts, pts[1:])), g


def test_the_curve_is_flat_outside_its_knots_and_between_them_in_between():
    knots = [[1.0, 3.0], [3.0, 1.0], [10.0, 0.5]]
    assert value.curve(knots, 0) == 3.0 and value.curve(knots, 500) == 0.5
    mid = value.curve(knots, 2.0)
    assert 1.0 < mid < 3.0
    assert value.curve(knots, 3.0) == 1.0


def test_classes_map_to_groups_and_unknown_reads_weak():
    assert value.group_of("conditions_flat") == value.group_of("yes_reason") == "strong"
    assert value.group_of("unsure") == value.group_of("firm_yes") == value.group_of(None) == "weak"
    assert value.group_of("lean_no") == "lean_no"


def test_expected_points_follow_age_at_landing_and_class():
    ev = lambda m, cls="conditions", lag=30: value.expected_points(cand(m, cls), NOW, lag_s=lag)   # noqa: E731
    assert ev(0.5) > ev(2) > ev(6) > ev(60)
    assert ev(3) > ev(3, "unclear")                         # past the first minute a weak post is worth about a third
    assert ev(6) > ev(3, "unclear")                         # ...so a 6-min Yes-but beats a 3-min unclear post
    assert ev(0.1, "unclear") > ev(1.5)                     # in its first minute a weak post is worth a strong one
    assert ev(1, lag=120) <= ev(1, lag=0)                   # a longer send lag lands it older
    missing = value.expected_points({"post": {}, "target_class": "conditions"}, NOW)
    assert missing == value.expected_points(cand(24 * 60), NOW)   # no readable time: a day old, last among the fresh


def test_steps_make_near_values_equal():
    assert config.VALUE_STEP == 0.25
    old = {g: value.curve(value.DEFAULT["curves"][g], 900) for g in value.NEEDED}
    assert len({value.step(v) for v in old.values()}) == 1          # old tails: one value, today's order decides
    assert value.step(2.8) > value.step(2.2)


def test_a_valid_table_file_replaces_the_default_and_a_bad_one_does_not(tmp_path, monkeypatch):
    path = tmp_path / "value_table.json"
    monkeypatch.setattr(config, "VALUE_TABLE_FILE", path)
    value.reset()
    assert value.table(now=NOW) is value.DEFAULT                     # no file
    good = json.loads(json.dumps(value.DEFAULT))
    good["curves"]["strong"] = [[1, 5.0], [10, 1.0]]
    path.write_text(json.dumps(good))
    assert value.table(now=NOW) is value.DEFAULT                     # cached for TABLE_CHECK_S
    assert value.table(now=NOW + value.TABLE_CHECK_S + 1)["curves"]["strong"] == [[1, 5.0], [10, 1.0]]
    bad = json.loads(json.dumps(good))
    bad["curves"]["weak"] = [[1, 1.0], [10, 2.0]]                    # rises with age
    path.write_text(json.dumps(bad))
    import os
    os.utime(path, (NOW + 999, NOW + 999))
    assert value.table(now=NOW + 3 * value.TABLE_CHECK_S) is value.DEFAULT
    path.write_text("{not json")
    os.utime(path, (NOW + 1999, NOW + 1999))
    assert value.table(now=NOW + 5 * value.TABLE_CHECK_S) is value.DEFAULT
    assert not value.valid({"curves": {"strong": [[1, 1]]}})        # a group missing


# ---- the switch and the arm ----
def test_it_ships_off_with_a_freeze_pin():
    assert config.VALUE_PICK is False
    assert config.PICK_ARMS == ["base", "value"] and config.PICK_BLOCK_S == 3 * 3600
    assert config.FREEZE_PIN["arm_pick"] == "base"
    assert value.pick_arm(NOW) == "base"


def test_pick_arm_runs_the_switchback_only_with_the_flag(monkeypatch):
    monkeypatch.setattr(config, "SWITCHBACK", [("arm_pick", config.PICK_ARMS, BLOCK)])
    assert {value.pick_arm(NOW + i * BLOCK) for i in range(4)} == {"base"}        # flag off: base, whatever the blocks
    monkeypatch.setattr(config, "VALUE_PICK", True)
    seen = [value.pick_arm(NOW + i * BLOCK) for i in range(8)]
    assert set(seen) == {"base", "value"} and value.pick_arm(NOW) == value.pick_arm(NOW + 1)
    monkeypatch.setattr(config, "SWITCHBACK", [])
    assert value.pick_arm(NOW) == "value"                                         # on, no test running: value everywhere


def test_the_pick_arm_freezes_to_base_on_1_nov(monkeypatch):
    monkeypatch.setattr(config, "VALUE_PICK", True)
    monkeypatch.setattr(config, "SWITCHBACK", [("arm_pick", config.PICK_ARMS, BLOCK)])
    monkeypatch.setattr(config, "ARMS_FREEZE", NOW)
    assert {value.pick_arm(NOW + h * 3600) for h in range(48)} == {"base"}
    assert experiment.block("arm_pick", NOW + 5)[0] == "arm_pick:frozen"


# ---- next_target ----
def _order(monkeypatch, arm, posts, scores=None, nets=None):
    """Post ids in the order next_target hands them out. posts: {pid: (minutes old, class)}; arm: "value", "base" or None
    (the flag off). The queue arm is shallow (newest-first with the todo/47 downrank), as live."""
    monkeypatch.setattr(config, "SWITCHBACK", [("arm_queue", ["shallow"], 3 * 3600)]
                        + ([("arm_pick", [arm], BLOCK)] if arm else []))
    monkeypatch.setattr(config, "VALUE_PICK", bool(arm))
    monkeypatch.setattr(config, "UNSURE_FIRST", False)
    monkeypatch.setattr(config, "TURNOUT_ARM", False)
    t = targeting.Targeter(None, log=lambda r: None)
    for pid, (minutes, cls) in posts.items():
        created = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes)).isoformat()
        t._queue(dict(post_id=pid, author_id=1000 + pid, body="the referendum", created_at=created), "latest", None, None, 0,
                 cls, net=(nets or {}).get(pid))
        t.candidates[pid]["score"] = (scores or {}).get(pid, 8.0)
    out = []
    while (c := t.next_target(set(), set(), {}, set())):
        out.append(c["post"]["post_id"])
        t.candidates.pop(c["post"]["post_id"], None)
    return out


def test_off_and_in_base_blocks_the_order_is_todays(monkeypatch):
    posts = {1: (1.5, "conditions"), 2: (0.2, "unclear"), 3: (6, "conditions"), 4: (3, "unsure")}
    today = [1, 2, 4, 3]                       # newest first, the weak ones 2.5 min older
    assert _order(monkeypatch, None, posts) == today
    assert _order(monkeypatch, "base", posts) == today


def test_value_blocks_take_what_the_table_says_is_worth_more(monkeypatch):
    # a weak post in its first minute beats a 1.5-min Yes-but; a 6-min Yes-but beats a 3-min unsure post
    posts = {1: (1.5, "conditions"), 2: (0.2, "unclear"), 3: (6, "conditions"), 4: (3, "unsure")}
    assert _order(monkeypatch, "value", posts) == [2, 1, 3, 4]


def test_in_the_old_tail_the_read_still_decides(monkeypatch):
    posts = {1: (300, "lean_no"), 2: (300, "conditions"), 3: (300, "unclear")}
    scores = {1: 3.0, 2: 9.0, 3: 6.0}
    assert _order(monkeypatch, "value", posts, scores) == _order(monkeypatch, "base", posts, scores) == [2, 3, 1]


def test_tiers_stay_first_in_value_blocks(monkeypatch):
    posts = {1: (0.2, "conditions"), 2: (400, "unclear")}
    assert _order(monkeypatch, "value", posts, nets={2: "late"}) == [2, 1]      # a late reply goes before everything


def test_the_hand_out_carries_ev_and_the_arm_and_the_write_logs_them(monkeypatch):
    for arm in ("value", None):
        monkeypatch.setattr(config, "SWITCHBACK", [("arm_pick", ["value"], BLOCK)] if arm else [])
        monkeypatch.setattr(config, "VALUE_PICK", bool(arm))
        t = targeting.Targeter(None, log=lambda r: None)
        created = dt.datetime.now(dt.timezone.utc).isoformat()
        t._queue(dict(post_id=5, author_id=100, body="the referendum", created_at=created), "latest", None, None, 0, "conditions")
        c = t.next_target(set(), set(), {}, set())
        assert c["arm_pick"] == (arm or "base") and 2.0 < c["ev"] < 3.0
        assert {"ev", "arm_pick"} <= set(bot.reply_job(c, {"persona": "x"}))
    assert '("ev", "arm_pick")' in pathlib.Path(bot.__file__).read_text()


def test_a_lost_item_logs_its_class(monkeypatch):
    logged = []
    t = targeting.Targeter(None, log=logged.append)
    old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=config.OLDER_MAX_AGE_H + 1)).isoformat()
    post = dict(post_id=9, author_id=100, body="the referendum, i'd want a sunset", created_at=old)
    t._queue(post, "latest", None, None, 0, "conditions")
    t._expire()
    lost = [r for r in logged if r.get("act") == "lost"]
    assert lost and lost[0]["cls"] == "conditions" and lost[0]["why"] == "expired:queued"


# ---- scripts/value_table.py ----
def test_pava_is_the_closest_non_increasing_sequence():
    assert vt.pava([3, 1, 2, 0], [1, 1, 1, 1]) == [3, 1.5, 1.5, 0]
    assert vt.pava([1, 3], [3, 1]) == [1.5, 1.5]                        # weighted
    assert vt.pava([5, 4, 3], [1, 1, 1]) == [5, 4, 3]


def test_the_fit_takes_out_the_hour_and_pools_thin_cells():
    rows = []
    # one hour busy (points 1 at any age), one quiet (points 4 at any age); old posts are only answered in the quiet hour
    # in the raw data, so a raw mean would make them look better than fresh ones. Within an hour, fresh beats old by 1.
    for i in range(60):
        rows.append(dict(group="strong", minutes=0.5, hour=1, points=2.0))
        rows.append(dict(group="strong", minutes=0.5, hour=2, points=5.0))
        rows.append(dict(group="strong", minutes=500, hour=2, points=4.0))
        rows.append(dict(group="strong", minutes=500, hour=2, points=4.0))
    for i in range(10):                                                     # thin: 10 < MIN_N
        rows.append(dict(group="strong", minutes=30, hour=1, points=9.0))
    for g in ("weak", "lean_no"):
        rows += [dict(group=g, minutes=1.5, hour=1, points=1.0) for _ in range(50)]
    tab = vt.fit(rows)
    pts = [p for _, p in tab["curves"]["strong"]]
    assert pts[0] > pts[-1]                                                 # fresh beats old once the hour is out
    assert all(b <= a for a, b in zip(pts, pts[1:])) and value.valid(tab)
    assert tab["n"]["strong"] == [120, 10, 120]


def test_the_replay_hands_slots_by_policy():
    tab = value.DEFAULT
    t0 = NOW
    pool = [dict(pid=1, author=1, cls="conditions", made=t0 - 90, found=t0 - 80, score=8, picked=None, lag=None),
            dict(pid=2, author=2, cls="unclear", made=t0 - 10, found=t0 - 5, score=8, picked=None, lag=None),
            dict(pid=3, author=3, cls="conditions", made=t0 - 360, found=t0 - 350, score=8, picked=None, lag=None),
            dict(pid=4, author=4, cls="unsure", made=t0 - 180, found=t0 - 170, score=8, picked=None, lag=None)]
    slots = [(t0 + i, 30, None) for i in range(4)]
    base = [p["pid"] for p in vt.simulate(pool, slots, "base", tab)]
    val = [p["pid"] for p in vt.simulate(pool, slots, "value", tab)]
    assert base == [1, 2, 4, 3] and val == [2, 1, 3, 4]
    assert vt.band(1.9) == "<2m" and vt.band(300) == ">4h"
