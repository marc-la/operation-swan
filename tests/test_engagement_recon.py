"""scripts/engagement_recon.py (todo/46): the delay buckets, the placed share and the portal counts on hand-built input."""
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
spec = importlib.util.spec_from_file_location("engagement_recon", ROOT / "scripts" / "engagement_recon.py")
er = importlib.util.module_from_spec(spec)
spec.loader.exec_module(er)


def test_delay_buckets_cover_every_hour_and_keep_their_order():
    assert [er.bucket(h) for h in (0, 0.99, 1, 5.9, 6, 23.9, 24, 70)] == ["0-1 h", "0-1 h", "1-6 h", "1-6 h", "6-24 h", "6-24 h", "over 24 h", "over 24 h"]
    t = er.delay_table([0.1, 0.2, 7, 30, 31, 100])
    assert list(t.items()) == [("0-1 h", 2), ("1-6 h", 0), ("6-24 h", 1), ("over 24 h", 3)]
    assert list(er.delay_table([]).values()) == [0, 0, 0, 0]


def test_placed_share_is_reads_over_portal_and_none_without_a_portal_count():
    assert er.placed(100, 25) == (0.25, 100, 25)
    assert er.placed(0, 5)[0] is None


def test_portal_counts_sum_the_window_only(tmp_path):
    ev = [{"ts": "2026-10-24T10:19:00+00:00", "points": 1, "message": "NPC engagement: 5 views, 3 likes and 2 replies"},
          {"ts": "2026-10-24T11:19:00+00:00", "points": 1, "message": "NPC engagement (×2 points): 4 likes, 1 repost and 1 follow"},
          {"ts": "2026-10-24T11:19:00+00:00", "points": 1, "message": "Moderation (×0.5 points): 3 first inauthentic reports"},
          {"ts": "2026-10-24T13:19:00+00:00", "points": 1, "message": "NPC engagement: 99 likes"}]
    f = tmp_path / "portal.json"
    f.write_text(json.dumps({"events": ev}))
    lo = er.ts_of("2026-10-24T10:00:00+00:00")
    got = er.portal_counts(f, lo, lo + 3 * 3600)
    assert (got["likes"], got["replies"], got["reposts"], got["follows"]) == (7, 2, 1, 1)
