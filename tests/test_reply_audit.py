import datetime as dt

from swan_bot import content, reply_audit as ra

T0 = dt.datetime(2026, 10, 24, 11, 0, tzinfo=dt.timezone.utc)


def row(text, who="a", target="", minutes=0, **kw):
    ts = (T0 + dt.timedelta(minutes=minutes)).isoformat()
    return dict(act="reply", ts=ts, username=who, text=text, target_text=target, **kw)


def test_closer_ignores_names_numbers_and_today():
    a = ra.closer("Fetu's off the counter. What's wrong with keeping things as they are today?")
    b = ra.closer("Whats wrong with keeping things as they are?")
    assert a == b and a.startswith("whats wrong")
    assert ra.closer("A pass adds no nurse.") is None


def test_off_point_needs_one_shared_content_word():
    assert ra.off_point("My parents' wedding photo hangs above the till.", "I want the ward ready with a staffing plan") is True
    assert ra.off_point("A pass adds no nurse to the ward.", "we need more nurses on the ward") is False
    assert ra.off_point("", "anything") is None


def test_audit_counts_shared_closers_runs_and_allies():
    ask = "What's wrong with keeping things as they are today?"
    recs = [
        row("A pass at the bakery door won't add a single nurse. " + ask, "a", "staffing plan please", 0),
        row("Pass at the bakery door won't add a single nurse either. " + ask, "b", "gating isn't the fix", 1, rebuttal=True),
        row("Totally different words here about venues.", "c", "venues list", 2),
        dict(act="like", ts=T0.isoformat(), text="ignored"),
    ]
    out = ra.audit(recs, content.opposes_pass, known_names={"Central"})
    assert out["replies"] == 3
    assert out["top_closers"][0][1] == 2 and out["shared_closers"][0][1] == 2
    assert any("bakery door" in k for k, _ in out["shared_runs"])
    assert out["ally_argued"] == 1 and out["ally_n"] == 3
    assert "replies read: 3" in ra.render(out)


def test_since_drops_older_rows_and_names_are_judged_against_the_comment():
    old = row("Hello there.", minutes=-600)
    new = row("Ask Marlow about it.", target="Marlow said so", minutes=0)
    out = ra.audit([old, new], content.opposes_pass, since=T0.timestamp() - 60)
    assert out["replies"] == 1 and out["unknown_names"] == []
