"""todo/40 item 5: what the hidden-post watch logs per hide (write, backend, arms, card, timing, portal), the 4 h tail after a
voice's last write, and that the old fields and readers are untouched (no network)."""
import importlib.util
import json
import pathlib
import sys
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import capturethenarrative as ctn  # noqa: E402

from swan_bot import config, watch  # noqa: E402
from swan_bot.bot import Accounts  # noqa: E402

NOW = 1_800_000_000.0


def iso(t):
    return watch._iso(t)


def row(t, post_id, username, act="reply", **kw):
    return dict(ts=iso(t), live=True, act=act, post_id=post_id, username=username, **kw)


def scan_of(*rows):
    s = watch.LogScan()
    for r in rows:
        s.add(r)
    return s


# ---- what the scan keeps of a write ----------------------------------------------------------------------------------
def test_scan_keeps_the_write_context_of_the_first_row():
    s = scan_of(row(NOW - 100, 5, "a", backend="kimi", draft_id="d5", sv_delay="slow", arm="firm_yes", length=210, text="x",
                    lever=None),
                row(NOW - 50, 5, "a", act="post", backend="other"),            # a later row for the same id does not replace it
                row(NOW - 40, 6, "a", act="like"),                              # a like is not a write
                dict(row(NOW - 30, 7, "a"), live=False))
    assert s.ctx[5] == dict(act="reply", ts=NOW - 100, backend="kimi", draft_id="d5", length=210,
                            arms={"sv_delay": "slow", "arm": "firm_yes"}), "only arms the row holds; no text"
    assert 6 not in s.ctx and 7 not in s.ctx
    assert s.last_write("a") == NOW - 100, "the latest write, by the time its first row was logged"
    assert s.last_write("nobody") is None


# ---- who is watched -------------------------------------------------------------------------------------------------
def test_a_suspended_voice_is_watched_for_four_hours_after_its_last_write():
    recs = [dict(username="act", status="active"), dict(username="booster", role="booster", status="active"),
            dict(username="gone_recent", status="suspended"), dict(username="gone_old", status="suspended"),
            dict(username="gone_silent", status="suspended")]
    s = scan_of(row(NOW - 3.9 * 3600, 1, "gone_recent"), row(NOW - 4.1 * 3600, 2, "gone_old"))
    assert [r["username"] for r in watch.watched(recs, s, NOW)] == ["act", "gone_recent"]
    assert [r["username"] for r in watch.watched(recs, s, NOW, tail_s=0)] == ["act"], "off"
    assert config.WATCH_TAIL_S == 4 * 3600 and "WATCH_TAIL_S" in config.STEALTH_ENV


class Social:
    def __init__(self, listed, hidden=()):
        self.listed, self.hidden = listed, set(hidden)

    def iterate(self, method, *args, max_items=None):
        return iter(method(*args))

    def account_posts(self, account_id, **kw):
        return [{"post_id": p} for p in self.listed.get(account_id, [])]

    def get_post(self, pid):
        if pid in self.hidden:
            raise ctn.APIError("GET", f"/posts/{pid}", 404, '{"error": "post not found"}')
        return {"post_id": pid}


def test_a_suspended_voice_with_an_empty_post_list_is_not_read_as_all_hidden():
    gone = dict(username="gone", account_id=7, status="suspended")
    logged = {"gone": {1, 2, 3}}
    assert watch.find_hidden(Social({7: []}, hidden={1, 2, 3}), [gone], logged, {}) == []
    assert watch.find_hidden(Social({7: [1]}, hidden={2}), [gone], logged, {}) == [("gone", 2)]
    live = dict(gone, status="active")
    assert watch.find_hidden(Social({7: []}, hidden={1, 2, 3}), [live], logged, {}) == [("gone", 1), ("gone", 2), ("gone", 3)]


# ---- the fields -----------------------------------------------------------------------------------------------------
def voice(**kw):
    return dict(username="ana_fifita_rn27", account_id=4603, persona="ana", role="voice", status="active",
                password="SECRET-PW", token="SECRET-TOKEN", created=iso(NOW - 80 * 3600), **kw)


def test_card_info_names_the_card_not_the_secrets():
    ana = voice()
    twin = dict(voice(), username="other27", status="suspended")
    info = watch.card_info(ana, [ana, twin, dict(username="x", persona="josh")])
    assert info["persona"] == "ana" and info["role"].startswith("ward nurse") and info["place"] == "Kingstonia City"
    assert info["origin"] == "original" and info["handle"] == "a_a_a9" and info["card_reuse"] == 1
    assert info["card_reuse_suspended"] == 1 and info["card_of"] is None
    assert "SECRET" not in json.dumps(info)
    conv = voice(converted=dict(at=iso(NOW), card_of="old_holder"), variant=dict(age=44, shape="firstname_job"))
    info = watch.card_info(conv, [conv])
    assert (info["origin"], info["card_of"], info["age"], info["shape"]) == ("converted", "old_holder", 44, "firstname_job")
    assert watch.card_info(voice(pool=dict(act="activate", at=iso(NOW))), [])["origin"] == "activated"


def test_hide_fields_say_what_wrote_the_hide_and_when():
    rec = voice(converted=dict(at=iso(NOW - 30 * 3600), card_of="old_holder"))
    s = scan_of(row(NOW - 5 * 3600, 11, rec["username"], backend="kimi", draft_id="abcd", sv_delay="slow", arm_conv="base"))
    portal = dict(ts=iso(NOW - 600), why="3 posts hidden")
    f = watch.hide_fields(rec, [rec], 11, s, [NOW - 7200], portal, NOW)
    assert (f["write_id"], f["write_act"], f["backend"]) == ("abcd", "reply", "kimi")
    assert f["write_ts"] == iso(NOW - 5 * 3600) and f["write_age_h"] == 5.0
    assert f["arms"] == {"sv_delay": "slow", "arm_conv": "base"}
    assert f["voice_age_h"] == 25.0, "age of the voice at the write: converted 30 h before, written 5 h before"
    assert f["since_prev_hide_h"] == 2.0 and f["hides_before"] == 1 and f["after_suspension"] is False
    assert f["portal"] == dict(ts=iso(NOW - 600), why="3 posts hidden") and f["card"]["origin"] == "converted"
    json.dumps(f)
    first = watch.hide_fields(rec, [rec], 11, s, [], None, NOW)
    assert first["since_prev_hide_h"] is None and first["hides_before"] == 0 and first["portal"] is None
    unknown = watch.hide_fields(rec, [rec], 999, s, [], None, NOW)              # a write the scan has no row for
    assert unknown["write_id"] is None and unknown["arms"] == {} and unknown["write_age_h"] is None
    assert watch.hide_fields(dict(rec, status="suspended"), [rec], 11, s, [], None, NOW)["after_suspension"] is True


def test_suspension_fields_tie_the_portal_time_to_the_hides_and_the_last_write():
    rec = voice()
    s = scan_of(row(NOW - 9000, 1, rec["username"]))
    f = watch.suspension_fields(rec, [rec], dict(ts=iso(NOW - 600), why="reported as a bot"),
                                [NOW - 4 * 3600, NOW - 3600], 2, s)
    assert (f["why"], f["portal_ts"], f["hidden"]) == ("reported as a bot", iso(NOW - 600), 2)
    assert f["since_first_hide_h"] == pytest.approx(3.83, abs=0.01) and f["since_last_hide_h"] == pytest.approx(0.83, abs=0.01)
    assert f["last_write_to_suspension_h"] == pytest.approx(2.33, abs=0.01) and f["voice_age_h"] == pytest.approx(79.83, abs=0.01)
    assert "SECRET" not in json.dumps(f)
    bare = watch.suspension_fields(rec, [rec], dict(ts=iso(NOW), why=""), [], 0, watch.LogScan())
    assert bare["since_first_hide_h"] is None and bare["last_write_ts"] is None


# ---- the script end to end: old fields and readers intact, new ones added -----------------------------------------------
def load_script():
    spec = importlib.util.spec_from_file_location("swan_watch_script", ROOT / "scripts" / "swan_watch.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_watch_script_logs_the_new_fields_and_keeps_the_old_ones(tmp_path, monkeypatch):
    mod = load_script()
    t = time.time()
    monkeypatch.setattr(mod.config, "load_env", lambda: None)                    # never read the box's .env in a test
    monkeypatch.setattr(sys, "argv", ["swan_watch.py"])
    monkeypatch.setattr(config, "ACTIONS_LOG", tmp_path / "actions.jsonl")
    monkeypatch.setattr(watch, "WATCH_FILE", tmp_path / "swan_watch.json")
    monkeypatch.setattr(watch, "WATCH_LOG", tmp_path / "swan_watch.jsonl")
    for name in ("LLM_SPEND_FILE", "LLM_STATUS_FILE", "LLM_ALERT_FILE"):        # todo/61: never the box's own LLM files
        monkeypatch.setattr(watch, name, tmp_path / f"{name.lower()}.json")
    alerts = []
    monkeypatch.setattr(mod.subprocess, "run", lambda cmd, **kw: alerts.append(cmd[-1]))
    records = [dict(username="ana_fifita_rn27", account_id=4603, persona="ana", role="voice", status="active",
                    created=iso(t - 90 * 3600), password="SECRET-PW", token="SECRET-TOKEN"),
               dict(username="josh_k_sparky36", account_id=4567, persona="josh", role="voice", status="suspended",
                    created=iso(t - 90 * 3600), password="SECRET-PW2", token="SECRET-TOKEN2")]
    config.ACCOUNTS_FILE.write_text(json.dumps(records))
    rows = [row(t - 5 * 3600, 10, "ana_fifita_rn27", backend="kimi", draft_id="d10"),
            row(t - 4 * 3600, 11, "ana_fifita_rn27", backend="kimi", draft_id="d11", sv_delay="slow"),
            row(t - 2 * 3600, 20, "josh_k_sparky36", backend="flash", draft_id="d20"),
            row(t - 1 * 3600, 21, "josh_k_sparky36", backend="flash", draft_id="d21", sv_delay="fast")]
    config.ACTIONS_LOG.write_text("".join(json.dumps(r) + "\n" for r in rows))
    config.PORTAL_FILE.write_text(json.dumps(dict(ts=iso(t - 300), account_log=dict(suspended=[
        dict(ts=iso(t - 1800), username="josh_k_sparky36", id=4567, why="3 posts hidden"),
        dict(ts=iso(t - 1800), username="josh_k_sparky36", id=9999, why="a different account"),
        dict(ts=iso(t - 1800), username="ana_fifita_rn27", id=1, why="not ours either")]))))
    watch.save(dict(ring_ts=t + 60, citizens_ts=t + 60))
    monkeypatch.setattr(mod.ctn, "LegitSocial", lambda *a, **k: Social({4603: [10], 4567: [20]}, hidden={11, 21}))

    mod.main()
    out = [json.loads(line) for line in watch.WATCH_LOG.read_text().splitlines()]
    hides = {r["post_id"]: r for r in out if r["act"] == "hidden_post"}
    assert set(hides) == {11, 21}
    a = hides[11]
    for old in ("ts", "act", "username", "post_id", "hidden", "actions", "bot"):
        assert old in a, old
    assert (a["hidden"], a["actions"], a["bot"]) == (1, 2, "off amplified posts and threads")
    assert a["write_id"] == "d11" and a["backend"] == "kimi" and a["arms"] == {"sv_delay": "slow"}
    assert a["after_suspension"] is False and a["card"]["role"].startswith("ward nurse") and a["since_prev_hide_h"] is None
    assert a["write_age_h"] == pytest.approx(4.0, abs=0.01) and a["portal"] is None
    j = hides[21]
    assert j["after_suspension"] is True and j["arms"] == {"sv_delay": "fast"} and j["portal"]["why"] == "3 posts hidden"
    assert len(alerts) == 1 and "@ana_fifita_rn27" in alerts[0], "a suspended voice's tail hide is logged, not alerted"
    susp = [r for r in out if r["act"] == "suspension"]
    assert [(r["username"], r["why"], r["hidden"]) for r in susp] == [("josh_k_sparky36", "3 posts hidden", 1)]
    assert susp[0]["account_id"] == 4567 and susp[0]["last_write_to_suspension_h"] is not None
    assert "SECRET" not in watch.WATCH_LOG.read_text() + watch.WATCH_FILE.read_text()

    state = json.loads(watch.WATCH_FILE.read_text())
    assert state["hidden"] == {"ana_fifita_rn27": [11], "josh_k_sparky36": [21]}, "the bot's reader is unchanged"
    assert set(state["hidden_at"]) == {"ana_fifita_rn27", "josh_k_sparky36"} and set(state["suspended_seen"]) == {"josh_k_sparky36"}
    acc = Accounts(None, live=False)
    assert acc.hidden() == {"ana_fifita_rn27": 1, "josh_k_sparky36": 1}

    mod.main()                                                                   # a second run finds nothing new
    again = [json.loads(l) for l in watch.WATCH_LOG.read_text().splitlines()]
    # the account-budget job (todo/39) and the LLM budget (todo/61) log one row a run each; everything else must be unchanged
    each_run = ("budget", "llm_budget")
    assert [r for r in again if r["act"] not in each_run] == [r for r in out if r["act"] not in each_run] and len(alerts) == 1
