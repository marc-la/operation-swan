"""Hidden-post watch (swan_bot/watch.py) and what the bot does with it (no network)."""
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import capturethenarrative as ctn  # noqa: E402

from swan_bot import amplify, bot, config, watch  # noqa: E402
from test_amplify import make_accounts  # noqa: E402

OLD = "2026-10-20T10:00:00+00:00"


def not_found(pid):
    return ctn.APIError("GET", f"/posts/{pid}", 404, '{"error": "post not found"}')


class Social:
    """account 1 lists posts 10 and 11; post 12 is hidden (404); post 13 is listed late (get_post finds it)."""
    def __init__(self):
        self.gets = []

    def account_posts(self, account_id, **kw):
        return [{"post_id": 10}, {"post_id": 11}] if account_id == 1 else []

    def iterate(self, method, *args, max_items=None):
        return iter(method(*args))

    def get_post(self, pid):
        self.gets.append(pid)
        if pid == 12:
            raise not_found(pid)
        return {"post_id": pid}


def test_logged_posts_keeps_settled_live_writes():
    now = time.time()
    rows = [dict(ts=OLD, act="reply", live=True, post_id=10, username="a"),
            dict(ts=OLD, act="like", live=True, post_id=99, username="a"),          # a like is not our post
            dict(ts=OLD, act="post", live=False, post_id=98, username="a"),         # dry run
            dict(ts=time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(now)), act="thread", live=True,
                 post_id=97, username="a")]                                         # too new to be listed
    assert watch.logged_posts(rows, now) == {"a": {10}}


def test_find_hidden_confirms_404_only():
    social = Social()
    voices = [dict(username="a", account_id=1)]
    new = watch.find_hidden(social, voices, {"a": {10, 11, 12, 13}}, known={})
    assert new == [("a", 12)]
    assert social.gets == [12, 13], "only unlisted posts are confirmed"
    assert watch.find_hidden(Social(), voices, {"a": {10, 11, 12}}, known={"a": [12]}) == []


def test_ring_alarm():
    score = lambda r: r["s"]
    assert watch.ring_medians([{"s": 40}, {"s": 60}], [{"s": 30}], score) == (50, 30)
    assert watch.ring_alarm(50, 30) and not watch.ring_alarm(20, 30)
    assert not watch.ring_alarm(None, 30) and not watch.ring_alarm(50, None)


def write_hidden(tmp_path, monkeypatch, hidden):
    path = tmp_path / "swan_watch.json"
    path.write_text(json.dumps({"hidden": hidden}))
    monkeypatch.setattr(watch, "WATCH_FILE", path)


def test_two_hidden_posts_stop_a_voice_writing(tmp_path, monkeypatch):
    acc = make_accounts(n_voices=3, n_boosters=0)
    write_hidden(tmp_path, monkeypatch, {"v0": [1, 2], "v1": [3]})
    v0, v1, v2 = acc.voices()
    assert acc.parked(v0) and not acc.ready(v0)
    assert not acc.parked(v1) and acc.ready(v1), "one hidden post: still writes replies"
    for _ in range(20):
        assert acc.eligible()["username"] != "v0"
        assert acc.assignable()["username"] != "v0"
    assert len(acc.voices()) == 3, "a parked voice still counts, so no replacement is registered"


def test_one_hidden_post_keeps_a_voice_off_amplification(tmp_path, monkeypatch):
    acc = make_accounts()
    write_hidden(tmp_path, monkeypatch, {"v1": [5]})
    monkeypatch.setattr(config, "AMP_AUTHOR_EXPLORE", 1.0)        # random author: v1 must still never come up
    amp = amplify.Amplifier(None, acc, {}, live=False, log=lambda r: None)
    amp.scale = 1.0
    assert all(amp.pick_author()["username"] != "v1" for _ in range(100))
    amp.on_post(None, acc.records[0], "our post", "F1_blank_cheque", "heavy")
    for th in amp.state["amp_threads"]:
        th["due"] = time.time() - 1
    while (job := amp.next_write_job()):
        assert job["rec"]["username"] != "v1"
        job["rec"]["last_write"] = 0


def test_a_parked_voice_answers_nobody(tmp_path, monkeypatch):
    """23 Oct audit: 6 of 7 voices kept writing (reply-backs, pooled drafts) after reaching the limit."""
    acc = make_accounts(n_voices=2, n_boosters=0)
    write_hidden(tmp_path, monkeypatch, {"v0": [1, 2]})
    asked = []

    class NoNotes:
        def notifications(self, **kw):
            return []

    def session(rec):
        asked.append(rec["username"])
        return NoNotes()

    bot.reply_back_jobs(None, acc, None, session=session)
    assert asked == ["v1"], "the parked voice's notifications are never read"
