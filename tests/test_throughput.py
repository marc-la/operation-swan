"""todo/24: throughput to ~3/min and no wasted drafts (no network)."""
import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from swan_bot import bot, config, targeting  # noqa: E402


def ago(minutes):
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes)).isoformat()


def job(mode, persona, author, post_id=1):
    return dict(mode=mode, rec=dict(persona=persona), target=dict(post_id=post_id, author_id=author))


# ---- 4. no draft for a capped citizen ------------------------------------------------------------------------------
def test_held_drafts_count_as_sent():
    contacted = {}
    targeting.contact(contacted, 914, "grace")
    held = [job("reply", "kai", 914), job("post", "dan", None), job("reply", "ben", 700)]
    held[1]["target"] = None
    now = bot.contacted_now(contacted, held)
    assert now["914"] == {"grace", "kai"} and now["700"] == {"ben"}
    assert len(now) == 2, "a post has no citizen"
    assert bot.contacted_now(contacted) == targeting.sessions(contacted), "nothing held: as before"


def test_drafter_skips_a_citizen_a_held_draft_will_cap():
    """The night of 21 Oct: grace answered citizen 914, kai's draft to them waited for the writer, and josh was
    drafted too (the cap counted grace only); josh's draft was thrown away at send. Now josh isn't drafted."""
    t = targeting.Targeter(None, log=lambda r: None)
    t.is_citizen = lambda aid: True
    contacted = {}
    targeting.contact(contacted, 914, "grace")
    t._consider(dict(post_id=168865, author_id=914, created_at=ago(1), body="still not sure about this referendum"),
                "latest")
    assert 168865 in t.candidates
    held = [job("reply", "kai", 914, post_id=168807)]
    assert t.next_target(set(), set(), bot.contacted_now(contacted, held)) is None
    assert t.items[168865]["why"] == "session_cap", "it waits for the next session; it isn't dropped"
    assert t.next_target(set(), set(), bot.contacted_now(contacted, []))["post"]["post_id"] == 168865
    j = job("reply", "josh", 914, post_id=168865)
    targeting.contact(contacted, 914, "kai")
    assert bot.gone_at_send(j, dict(replied_posts=[], contacted=contacted)) == "session_cap", "the send check agrees"
    assert config.SESSION_VOICES == 2
