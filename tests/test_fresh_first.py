"""A fresh citizen post jumps the queue (FRESH_BONUS, 23 Oct): the reply-time goal is under 5 min, and with ~2,000
queued the median wait was ~3 h."""
import datetime as dt

from swan_bot import config, targeting


def _post(pid, minutes):
    return dict(post_id=pid, author_id=1000 + pid, body="the referendum",
                created_at=(dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes)).isoformat())


def test_a_fresh_ordinary_post_goes_before_older_posts_with_a_stronger_read(monkeypatch):
    monkeypatch.setattr(config, "SWITCHBACK", [])
    monkeypatch.setattr(config, "TURNOUT_ARM", False)
    t = targeting.Targeter(None, log=lambda r: None)
    for pid, cls, minutes in ((1, "unsure", 30), (2, "conditions", 90), (3, "lean_no", 2), (4, "unclear", 20)):
        t._queue(_post(pid, minutes), "latest", None, None, 0, cls)
    for pid in (1, 2, 4):
        t.candidates[pid]["score"] = 9.0                  # strong reads, an hour or so old
    first = t.next_target(set(), set(), {}, set())
    assert first["post"]["post_id"] == 3, "the 2-minute-old lean-No post, ahead of the 'unsure' ones"
