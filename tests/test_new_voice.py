"""todo/40 item 1: a converted or newly activated voice writes replies only for its first NEW_VOICE_NO_POST_H hours: no
persona post, amplified post or thread reply (no network)."""
import datetime as dt
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from swan_bot import config, stealth  # noqa: E402
from test_amplify import make_accounts, make_amp  # noqa: E402

H = 3600


def iso(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat()


def aged(rec, hours, now, how="converted"):
    """rec, begun `hours` ago by the given route."""
    at = now - hours * H
    if how == "converted":
        rec["converted"] = dict(at=iso(at), by="pool", from_role="booster")
    elif how == "activated":
        rec["pool"] = dict(by="pool", act="activate", at=iso(at))
    elif how == "ramp":
        rec["ramp"] = {"from": at, "until": at + 12 * H, "start": 0.25}
    else:
        rec["created"] = iso(at)
    return rec


def test_voice_since_picks_the_right_clock():
    now = 1_800_000_000.0
    assert stealth.voice_since({}) is None, "no dates: counts as old"
    assert stealth.voice_since({"created": iso(now - 5 * H)}) == pytest.approx(now - 5 * H)
    # a converted booster is old as an account but new as a voice: converted.at wins over created
    rec = aged({"created": iso(now - 200 * H)}, 2, now)
    assert stealth.voice_since(rec) == pytest.approx(now - 2 * H)
    # a warmed account the pool activated: the activation, not its registration
    rec = aged({"created": iso(now - 60 * H)}, 3, now, "activated")
    assert stealth.voice_since(rec) == pytest.approx(now - 3 * H)
    rec = aged({"created": iso(now - 60 * H), "pool": dict(act="register", at=iso(now - 60 * H))}, 4, now, "ramp")
    assert stealth.voice_since(rec) == pytest.approx(now - 4 * H), "a register note is not an activation"
    assert stealth.voice_since({"converted": {"at": "not a date"}, "created": iso(now - H)}) == pytest.approx(now - H)


@pytest.mark.parametrize("how", ["converted", "activated", "ramp", "created"])
def test_gate_at_23_and_25_hours(how):
    now = time.time()
    young, old = aged({}, 23, now, how), aged({}, 25, now, how)
    assert stealth.new_voice(young, now) and not stealth.new_voice(old, now)
    assert not stealth.new_voice({}, now) and not stealth.new_voice({"created": "junk"}, now)


def test_flag_off_and_default():
    now = time.time()
    assert config.NEW_VOICE_NO_POST_H == 24 and "NEW_VOICE_NO_POST_H" in config.STEALTH_ENV
    rec = aged({}, 1, now)
    assert stealth.new_voice(rec, now)
    config.stealth_from_env({"SWAN_NEW_VOICE_NO_POST_H": "0"})
    try:
        assert not stealth.new_voice(rec, now)
    finally:
        config.NEW_VOICE_NO_POST_H = 24


def two_voices(young_h, old_h):
    now = time.time()
    acc = make_accounts(n_voices=2, n_boosters=12)
    aged(acc.records[0], young_h, now)
    aged(acc.records[1], old_h, now)
    return acc, acc.records[0], acc.records[1], now


def test_young_voice_gets_no_persona_post():
    acc, new, old, now = two_voices(23, 25)
    assert acc.young(now) == {new["persona"]}
    for _ in range(30):
        assert acc.eligible(exclude=acc.young(now))["username"] == old["username"]
        assert acc.assignable(exclude=acc.young(now))["username"] == old["username"]
    assert acc.young(now + 3 * H) == set()
    acc, new, old, now = two_voices(25, 30)
    assert acc.young(now) == set()


def test_young_voice_is_never_an_amplified_author(monkeypatch):
    monkeypatch.setattr(config, "AMP_AUTHOR_EXPLORE", 1.0)
    acc, new, old, now = two_voices(23, 25)
    amp = make_amp(acc)
    assert {amp.pick_author()["username"] for _ in range(60)} == {old["username"]}
    aged(new, 25, now)
    assert {amp.pick_author()["username"] for _ in range(200)} == {new["username"], old["username"]}


def test_young_voice_writes_no_thread_reply_but_old_ones_do():
    acc = make_accounts(n_voices=6, n_boosters=12)
    now = time.time()
    young = aged(acc.records[2], 23, now)
    amp = make_amp(acc)
    amp.on_post(None, acc.records[0], "our post", "F1_blank_cheque", "heavy")
    for th in amp.state["amp_threads"]:
        th["due"] = now - 1
    seen = set()
    while (job := amp.next_write_job()):
        if job["mode"] == "thread":                 # a repost is not text and is not held back
            seen.add(job["rec"]["username"])
        job["rec"]["last_write"] = 0
    assert seen and young["username"] not in seen
    # the same plan once it has turned 24 h: it may reply in the thread
    aged(young, 25, now)
    amp = make_amp(acc)
    for _ in range(12):
        amp.on_post(None, acc.records[0], "our post", "F1_blank_cheque", "heavy")
    for th in amp.state["amp_threads"]:
        th["due"] = now - 1
    seen = set()
    while (job := amp.next_write_job()):
        if job["mode"] == "thread":
            seen.add(job["rec"]["username"])
        job["rec"]["last_write"] = 0
    assert young["username"] in seen


def test_replies_stay_open_to_a_young_voice():
    acc, new, old, now = two_voices(1, 25)
    acc.records[1]["last_write"] = now           # the old voice just wrote: only the young one is free
    assert acc.eligible(citizen=True)["username"] == new["username"]
