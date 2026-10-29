"""The room (todo/52 WS1, 29 Oct): content/room.toml, observe and its windows, rising drivers and phrases, the flip lift,
room.json and the saved counts. No network."""
import json
import pathlib
import sys
import types

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from swan_bot import bot, config, flip, room, targeting  # noqa: E402

HOUR = 3600
NOW = 1_800_000_000 - 1_800_000_000 % HOUR + 1800          # half past an hour
SUNSET = "I'm voting Yes, but only with a hard sunset clause and the venue list published."
HOSPITAL = "I'm voting Yes because our hospital wards can't take a surge."
NO_POST = "I'm voting No, keep it voluntary."


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setattr(config, "ROOM_ON", True)
    monkeypatch.setattr(config, "ROOM_LIFT_ON", True)
    monkeypatch.setattr(config, "FLIP_ON", True)
    room.reset()
    flip.reset()
    yield
    room.reset()
    flip.reset()


def fill(n, text, cheap="yes_but", start=0, at=NOW, step=10):
    """n posts written at `at` (unix s), ids from start, seen as they were written."""
    for i in range(n):
        room.observe(start + i, f"{text} #{i}", cheap=cheap, made=at, t=at + step)


# ---- the file -------------------------------------------------------------------------------------------------------
def test_the_file_parses_and_every_lift_names_a_flip_item():
    ds = room.drivers()
    assert len(ds) >= 20 and {d["family"] for d in ds.values()} == set(room.FAMILIES)
    items = {f"{part}.{k}" for part in ("evidence", "pivot") for k in flip.data()[part]}
    for key, d in ds.items():
        missing = [x for x in d["lifts"] if x not in items]
        assert not missing, f"driver.{key} lifts what content/flip.toml doesn't have: {missing}"
        assert d["family"] != "no" or not d["lifts"], f"driver.{key}: the No case is never flipped"


def test_the_drivers_are_the_room_read_s_families():
    assert room.voiced(SUNSET)[:2] == ["b1_places", "b2_end"]
    assert "y1_hospitals" in room.voiced(HOSPITAL)
    assert room.voiced("Who's going to the cup final?") == []


def test_a_bad_file_keeps_the_last_good_drivers(tmp_path):
    good = tmp_path / "room.toml"
    good.write_text('[driver.x]\nfamily = "but"\nlabel = "x"\nkeywords = ["sunset"]\n')
    assert list(room.drivers(good)) == ["x"]
    good.write_text('[driver.x]\nfamily = "nope"\n')
    import os
    os.utime(good, (NOW, NOW))                                  # a new mtime: re-read
    assert list(room.drivers(good)) == ["x"]
    with pytest.raises(ValueError):
        room.parse('[driver.x]\nfamily = "nope"\nlabel = "x"\nkeywords = ["a"]\n')


# ---- observe ----------------------------------------------------------------------------------------------------------
def test_observe_is_idempotent_and_off_the_vote_is_not_the_room():
    for _ in range(3):
        room.observe(1, SUNSET, cheap="yes_but", made=NOW, t=NOW + 5)
    room.observe(2, "Who's going to the cup final?", cheap=None, made=NOW, t=NOW + 5)
    s = room.summary(NOW + 60)
    assert s["posts"]["recent"] == 1
    end = next(d for d in s["drivers"] if d["key"] == "b2_end")
    assert end["n"] == 1 and end["share"] == 1.0


def test_a_read_is_counted_once_beside_the_first_sight():
    room.observe(1, SUNSET, cheap="unsure", made=NOW, t=NOW + 5)
    for _ in range(2):
        room.observe(1, SUNSET, stance="yes_but", t=NOW + 60)
    s = room.summary(NOW + 120)
    assert s["stance"]["recent"] == {"unsure": 1.0}                 # the keyword stance, every post
    assert s["reads"]["recent"] == {"n": 1, "mix": {"yes_but": 1.0}}  # the light read, posts we answered


def test_a_post_seen_hours_after_it_was_written_is_not_counted_at_first_sight():
    room.observe(1, SUNSET, cheap="yes_but", made=NOW - 3 * HOUR, t=NOW)
    room.observe(1, SUNSET, stance="yes_but", t=NOW)                 # its read still counts: we answered it
    s = room.summary(NOW + 60)
    assert s["posts"]["recent"] == 0 and s["reads"]["recent"]["n"] == 1


def test_windows_prune():
    fill(5, SUNSET, at=NOW - 30 * HOUR)
    fill(5, SUNSET, start=100, at=NOW)
    s = room.summary(NOW + 60)
    assert s["posts"]["recent"] == 5 and s["posts"]["base"] == 0
    assert all(h > NOW // HOUR - room.RECENT_H - room.BASE_H for h in room._buckets)


def test_an_hour_out_of_the_window_keeps_only_phrases_of_two_posts():
    room.observe(1, "a hard sunset clause please", cheap="yes_but", made=NOW, t=NOW + 5)
    room.observe(2, "a hard sunset clause or nothing", cheap="yes_but", made=NOW, t=NOW + 5)
    room.observe(3, "the wastewater signal worries me", cheap="yes_but", made=NOW, t=NOW + 5)
    room.summary(NOW + room.RECENT_H * HOUR + 60)
    grams = room._buckets[NOW // HOUR]["grams"]
    assert grams.get("hard sunset clause") == 2 and "wastewater signal" not in grams


def test_phrases():
    p = room.phrases("Publish the venues, @kai, and a hard sunset! https://x.io/y #VoteNo")
    assert {"publish the venues", "hard sunset"} <= p
    assert not any(w in g for g in p for w in ("kai", "http", "voteno"))
    assert "the venues" not in p and "and a hard" not in p


# ---- rising -----------------------------------------------------------------------------------------------------------
def base_day(n_per_h=20, text="Yes, but only with an end date on it.", stance="yes_but"):
    """A day of posts in the 24 h before the window."""
    i = 10_000
    for h in range(room.RECENT_H, room.RECENT_H + room.BASE_H):
        fill(n_per_h, text, cheap=stance, start=i, at=NOW - h * HOUR)
        i += n_per_h


def test_a_driver_at_twice_its_day_share_rises_and_lifts_its_flip_items():
    base_day()                                                      # 480 posts, no hospital in any
    fill(30, "Yes, but only with an end date on it.", start=1)
    fill(10, HOSPITAL, start=100)                                   # 10 of 40 in the window, 0 of 480 before
    s = room.summary(NOW + 60)
    hosp = next(d for d in s["drivers"] if d["key"] == "y1_hospitals")
    end = next(d for d in s["drivers"] if d["key"] == "b2_end")
    assert hosp["rising"] and hosp["x"] >= config.ROOM_RISE and not end["rising"]
    assert s["lifted"] == ["evidence.surge_drill"]
    assert room.lift("evidence", "surge_drill", t=NOW + 60) == config.ROOM_LIFT
    assert room.lift("pivot", "no_end", t=NOW + 60) == 1.0
    assert room.lift("evidence", "surge_drill", t=NOW + 60 + room.STALE_S + 1) == 1.0     # the room thread stopped


def test_nothing_rises_while_the_baseline_is_building():
    fill(20, HOSPITAL)
    s = room.summary(NOW + 60)
    assert s["building"] and not s["lifted"] and not s["phrases"]
    assert not any(d["rising"] for d in s["drivers"])


def test_rising_phrases_are_their_new_words():
    base_day()
    fill(12, "Yes, but the wastewater retest has me rattled.", start=1)
    fill(28, "Yes, but only with an end date on it.", start=100)
    s = room.summary(NOW + 60)
    top = [p["phrase"] for p in s["phrases"]]
    assert "wastewater retest" in " | ".join(top)
    assert not any(p in ("end date",) for p in top)                # every day's words are not rising
    assert len(top) == len(set(top))


def test_the_lift_switch(monkeypatch):
    base_day()
    fill(10, HOSPITAL, start=1)
    fill(30, "Yes, but only with an end date on it.", start=100)
    room.summary(NOW + 60)
    monkeypatch.setattr(config, "ROOM_LIFT_ON", False)
    assert room.lift("evidence", "surge_drill", t=NOW + 60) == 1.0


def test_the_flip_draws_a_lifted_item_more_often_and_logs_it(monkeypatch):
    monkeypatch.setattr(room, "lift", lambda part, key, t=None: 1.0)
    posts = [f"Our hospital wards are full, I'm voting Yes ({i})." for i in range(300)]
    before = sum(flip.choose(p)["evidence"]["key"] == "voluntary_doses" for p in posts)
    monkeypatch.setattr(room, "lift", lambda part, key, t=None: 1.5 if (part, key) == ("evidence", "voluntary_doses") else 1.0)
    choices = [flip.choose(p) for p in posts]
    after = sum(c["evidence"]["key"] == "voluntary_doses" for c in choices)
    assert after > before
    assert all(("evidence.voluntary_doses" in c["lifted"]) == (c["evidence"]["key"] == "voluntary_doses") for c in choices)


def test_the_write_logs_the_lift_and_the_dial(monkeypatch):
    monkeypatch.setattr(room, "lift", lambda part, key, t=None: 1.5 if part == "pivot" else 1.0)
    j = dict(mode="reply", rec=dict(persona="lani"), frame=None, arm=None, wants=[], context=None, read=False, meta={},
             target=dict(post_id=5, author_id=500, body="I'm voting Yes to protect our hospitals, but only with a sunset."))
    bot.build_prompt(j, types.SimpleNamespace(headline=None))
    assert j["meta"]["flip_fear"] == config.FLIP_FEAR and j["meta"]["flip_lift"].startswith("pivot.")
    assert {"flip_fear", "flip_lift"} <= set(bot.ARMS)


# ---- the cheap stance -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text,stance", [
    (SUNSET, "yes_but"),
    ("Not sure yet, the hospitals worry me with this referendum.", "unsure"),
    ("I'm leaning yes on the referendum to protect the hospitals.", "yes_but"),
    (HOSPITAL, "firm_yes"),                                          # a Yes stated with its reason and no hedge
    ("I'm voting no. #VoteNo", "firm_no"),
    ("Leaning No on the referendum, the list isn't out.", "lean_no"),
    ("Voting yes. #VoteYes", "firm_yes"),
    ("Who's going to the cup final?", None),
])
def test_the_cheap_stance(text, stance):
    assert targeting.room_stance(text, targeting.target_class(text)) == stance


def test_the_targeter_shows_the_room_every_post_it_judges(monkeypatch):
    seen = []
    monkeypatch.setattr(room, "observe", lambda pid, text, cheap=None, stance=None, made=None, t=None: seen.append((pid, cheap)))
    t = targeting.Targeter(types.SimpleNamespace(), log=lambda rec: None)
    now = targeting.dt.datetime.now(targeting.dt.timezone.utc).isoformat()
    for pid, body in ((1, SUNSET), (2, "LOUD ABUSE ABOUT THE VOTE FROM SOMEONE ANGRY ON THE REFERENDUM")):
        t._consider(dict(post_id=pid, author_id=500, body=body, created_at=now, kind="post"), "latest")
    assert seen == [(1, "yes_but"), (2, "unclear")]                 # a hard skip is still in the room


# ---- room.json and the saved counts -----------------------------------------------------------------------------------
def test_write_and_load_round_trip(tmp_path):
    base_day(n_per_h=15)
    fill(10, SUNSET, start=1)
    room.observe(1, SUNSET, stance="yes_but", t=NOW + 30)
    out, state = tmp_path / "room.json", tmp_path / "room_state.json"
    s = room.write(NOW + 60, out=out, state=state)
    assert json.loads(out.read_text())["posts"] == s["posts"] == {"recent": 10, "base": 360, "day": 10 + 15 * 21}
    room.reset()
    assert room.load(state, t=NOW + 60) == 1 + room.BASE_H         # the hours that had posts: the window's one, the day before
    assert room.summary(NOW + 60)["posts"] == s["posts"]


def test_load_survives_a_missing_or_broken_file(tmp_path):
    assert room.load(tmp_path / "nope.json") == 0
    (tmp_path / "bad.json").write_text("{not json")
    assert room.load(tmp_path / "bad.json") == 0
    (tmp_path / "list.json").write_text("[1, 2]")
    assert room.load(tmp_path / "list.json") == 0


def test_room_off_counts_nothing(monkeypatch):
    monkeypatch.setattr(config, "ROOM_ON", False)
    fill(5, SUNSET)
    assert room.summary(NOW + 60)["posts"]["recent"] == 0
    assert room.lift("pivot", "no_end") == 1.0


def test_a_first_start_seeds_the_day_from_the_log(tmp_path):
    log = tmp_path / "actions.jsonl"
    rows = [dict(ts=f"{targeting.dt.datetime.fromtimestamp(NOW - h * HOUR, targeting.dt.timezone.utc).isoformat()}",
                 act="reply", live=True, target_post=1000 + i, target_text=SUNSET if i % 2 else HOSPITAL,
                 read_stance="yes_but", t_made=NOW - h * HOUR - 60)
            for i, h in enumerate(range(1, 27))]
    rows += [dict(rows[0], live=False, target_post=5), dict(rows[0], act="reply_back", target_post=6),
             dict(rows[0], ts="2020-01-01T00:00:00+00:00", target_post=7)]           # a dry run, a reply-back, too old
    log.write_text("".join(json.dumps(r) + "\n" for r in rows))
    cheap = lambda text: targeting.room_stance(text, targeting.target_class(text))
    assert room.seed(log, cheap, t=NOW) == 26
    s = room.summary(NOW)
    assert s["posts"]["recent"] + s["posts"]["base"] == 26 and s["reads"]["day"]["n"] == 23     # reads 1-23 h back: the hours of the day
    assert room.seed(tmp_path / "nope.jsonl", cheap, t=NOW) == 0
