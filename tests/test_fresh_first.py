"""A fresh citizen post jumps the queue (FRESH_BONUS, 23 Oct): the reply-time goal is under 5 min, and with ~2,000
queued the median wait was ~3 h."""
import datetime as dt

from swan_bot import config, targeting


def _post(pid, minutes):
    return dict(post_id=pid, author_id=1000 + pid, body="the referendum",
                created_at=(dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes)).isoformat())


def test_a_fresh_ordinary_post_goes_before_older_posts_with_a_stronger_read(monkeypatch):
    monkeypatch.setattr(config, "SWITCHBACK", [])
    monkeypatch.setattr(config, "UNSURE_FIRST", False)          # the order without the unsure split
    monkeypatch.setattr(config, "TURNOUT_ARM", False)
    t = targeting.Targeter(None, log=lambda r: None)
    for pid, cls, minutes in ((1, "unsure", 30), (2, "conditions", 90), (3, "lean_no", 2), (4, "unclear", 20)):
        t._queue(_post(pid, minutes), "latest", None, None, 0, cls)
    for pid in (1, 2, 4):
        t.candidates[pid]["score"] = 9.0                  # strong reads, an hour or so old
    first = t.next_target(set(), set(), {}, set())
    assert first["post"]["post_id"] == 3, "the 2-minute-old lean-No post, ahead of the 'unsure' ones"


def test_unsure_half_goes_first_and_each_half_keeps_the_old_order(monkeypatch):
    """UNSURE_FIRST (Marc, 24 Oct): two halves, unsure first; inside each, score plus FRESH_BONUS as before."""
    monkeypatch.setattr(config, "SWITCHBACK", [])
    monkeypatch.setattr(config, "TURNOUT_ARM", False)

    def order(unsure_first):
        monkeypatch.setattr(config, "UNSURE_FIRST", unsure_first)
        t = targeting.Targeter(None, log=lambda r: None)
        for pid, cls, minutes in ((1, "conditions", 90), (2, "unsure", 120), (3, "unsure", 600), (4, "lean_no", 2)):
            t._queue(_post(pid, minutes), "latest", None, None, 0, cls)
        for pid, score in ((1, 9.0), (2, 2.0), (3, 1.5)):
            t.candidates[pid]["score"] = score
        out = []
        while (c := t.next_target(set(), set(), {}, set())):
            out.append(c["post"]["post_id"])
            t.candidates.pop(c["post"]["post_id"], None)
        return out

    assert order(True) == [2, 3, 4, 1]                  # the unsure by score, then the rest (the fresh lean-No leads that half)
    assert order(False) == [4, 1, 2, 3]                 # as before: by score


def test_among_fresh_posts_the_unsure_one_still_goes_first(monkeypatch):
    monkeypatch.setattr(config, "SWITCHBACK", [])
    monkeypatch.setattr(config, "TURNOUT_ARM", False)
    monkeypatch.setattr(config, "UNSURE_FIRST", True)
    t = targeting.Targeter(None, log=lambda r: None)
    for pid, cls, minutes in ((1, "lean_no", 1), (2, "unsure", 6), (3, "conditions", 2)):
        t._queue(_post(pid, minutes), "latest", None, None, 0, cls)
    for pid, score in ((1, 9.0), (2, 2.0), (3, 8.0)):
        t.candidates[pid]["score"] = score
    assert t.next_target(set(), set(), {}, set())["post"]["post_id"] == 2     # all under FRESH_MIN: the unsure one first
