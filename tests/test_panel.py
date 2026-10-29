"""The panel (todo/52 WS2): per-citizen light reads, the moves between them, the join to our last write, the windows."""
import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import panel  # noqa: E402

NOW = dt.datetime(2026, 10, 29, 12, 0, tzinfo=dt.timezone.utc)


def at(hours_ago):
    return (NOW - dt.timedelta(hours=hours_ago)).isoformat()


def reply(author, their_post, our_post, stance, hours_ago, flip=None, news=None, flip_fear=None, live=True, text="",
          cls=None):
    return dict(ts=at(hours_ago), act="reply", live=live, target_author=author, target_post=their_post, post_id=our_post,
                read_stance=stance, flip=flip, news=news, flip_fear=flip_fear, target_text=text, target_class=cls)


ROWS = [
    reply(501, 100, 150, "yes_but", 30, flip="hospitals/surge_drill/no_end", flip_fear=1,
          text="Yes, but our hospital wards need a sunset on this", cls="yes_reason"),
    reply(501, 200, 250, "lean_no", 10),                                       # to No, after the hospitals flip
    reply(502, 300, 350, "lean_no", 20, news="poll_narrows"),
    reply(502, 400, 450, "firm_no", 5),                                        # lean to firm
    reply(503, 500, 550, "firm_no", 15),
    reply(503, 600, 650, "yes_but", 3, flip="conditional_yes/contained_case/no_list"),   # to Yes
    reply(504, 700, 750, "yes_but", 4),                                        # one read: not on the panel
    reply(505, 800, 850, "yes_but", 9),
    reply(505, 900, 950, "unclear", 8),                                        # no position: skipped
    reply(505, 1000, 1050, "yes_but", 2),                                      # no move
    reply(506, 1100, 1150, "yes_but", 6, live=False),                          # a dry run: not ours to count
    reply(506, 1200, 1250, "firm_no", 1, live=False),
    dict(ts=at(1), act="like", live=True, target_author=501, post_id=None),
]


def files(tmp_path, rows=ROWS):
    log = tmp_path / "actions.jsonl"
    log.write_text("".join(json.dumps(r) + "\n" for r in rows))
    deploys = tmp_path / "deploys.jsonl"
    deploys.write_text(json.dumps(dict(ts=at(12).replace("+00:00", "Z"), old="a" * 40, new="b" * 40, result="ok")) + "\n")
    portal = tmp_path / "portal.json"
    portal.write_text(json.dumps(dict(events=[
        dict(ts=at(2), points=50, message="NPC engagement: 9 views, 2 likes and 1 contribution to a change of mind towards your side"),
        dict(ts=at(3), points=-10, message="NPC engagement: 3 contributions to a change of mind away from your side")])))
    return log, deploys, portal


def test_moves_are_counted_per_citizen_and_joined_to_our_last_write(tmp_path):
    log, _, _ = files(tmp_path)
    reads, touches = panel.load(log, NOW - dt.timedelta(days=3))
    assert set(reads) == {"501", "502", "503", "504", "505"}                  # dry runs and unclear reads left out
    pairs = panel.moves(reads, touches)
    kinds = {(p["author"], p["kind"]) for p in pairs}
    assert kinds == {("501", "to_no"), ("502", "lean_firm"), ("503", "to_yes"), ("505", None)}
    move = next(p for p in pairs if p["author"] == "501")
    assert move["flip"] == "hospitals/surge_drill/no_end" and move["flip_fear"] == 1    # our reply to post 100 (id 150 < 200)


def test_windows_count_citizens_per_100_re_read(tmp_path):
    log, _, _ = files(tmp_path)
    pairs = panel.moves(*panel.load(log, NOW - dt.timedelta(days=3)))
    w = panel.window(pairs, NOW - dt.timedelta(hours=24), NOW + dt.timedelta(minutes=1))
    assert w["reread"] == 4 and w["to_no"] == 1 and w["per100_to_no"] == 25.0 and w["per100_lean_firm"] == 25.0
    assert w["to_yes"] == 1 and w["firm_lean"] == 0 and w["net"] == 0 and w["per100_net"] == 0.0
    assert panel.window(pairs, NOW - dt.timedelta(hours=48), NOW - dt.timedelta(hours=24))["per100_to_no"] is None


def test_kinds():
    assert panel.kind("yes_but", "firm_no") == panel.kind("unsure", "lean_no") == "to_no"
    assert panel.kind("lean_no", "firm_no") == "lean_firm" and panel.kind("firm_no", "lean_no") == "firm_lean"
    assert panel.kind("lean_no", "yes_but") == "to_yes"
    assert panel.kind("yes_but", "firm_yes") is None and panel.kind("yes_but", "yes_but") is None


def test_build_writes_the_dashboard_s_json_with_deploys_and_the_portal(tmp_path):
    log, deploys, portal = files(tmp_path)
    out = panel.build(log, deploys, portal, NOW, days=2)
    json.dumps(out, default=str)
    assert out["last24"]["to_no"] == 1 and out["panel"] == {"citizens": 5, "on_panel": 4}
    d = out["deploys"][0]
    assert d["sha"] == "bbbbbbb" and d["before"]["to_no"] == 0 and d["after"]["to_no"] == 1   # 501 moved 10 h ago, after it
    today = next(r for r in out["days"] if r["day"] == "2026-10-29")
    assert today["portal"]["toward"] == 1 and today["portal"]["away"] == 3
    touch = {v: (n, tn, ty) for v, n, tn, ty in out["by_touch"]["fear"]}
    assert touch == {"hospitals": (1, 1, 0), "none": (3, 1, 1)}           # (pairs, toward No, toward Yes)


def test_main_writes_json_quietly(tmp_path, capsys):
    log, deploys, portal = files(tmp_path)
    out = tmp_path / "panel.json"
    panel.main(["--log", str(log), "--deploy-log", str(deploys), "--portal", str(portal), "--json", str(out), "--quiet"], now=NOW)
    assert json.loads(out.read_text())["last24"]["reread"] == 4 and capsys.readouterr().out == ""
    panel.main(["--log", str(log), "--deploy-log", str(deploys), "--portal", str(portal), "--touch", "--deploys"], now=NOW)
    printed = capsys.readouterr().out
    assert "re-read 4: net +0" in printed and "around the last 10 deploys" in printed


def test_who_moves_by_what_they_voiced(tmp_path):
    log, _, _ = files(tmp_path)
    pairs = panel.moves(*panel.load(log, NOW - dt.timedelta(days=3)))
    k = panel.by_kind(pairs)
    assert ("fear+but", 1, 1, 0, 100.0) in k["voiced"] and ("yes_reason", 1, 1, 0, 100.0) in k["class"]
    assert sum(n for _, n, _, _, _ in k["voiced"]) == 4                       # every pair: 501, 502, 503, 505
    assert panel.voices("Yes, but publish the venue list") == "but" and panel.voices("hello there") == "other"
