"""Dashboard builder (todo/09): banner rules, score maths, and that no secret or script can reach the page."""
import datetime as dt
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from swan_dash import build  # noqa: E402

NOW = dt.datetime(2026, 10, 22, 6, 0, tzinfo=dt.timezone.utc)        # 2pm Perth, 22 Oct
CANARY = "CANARY-team-code-7f3a"


def iso(minutes_ago):
    return (NOW - dt.timedelta(minutes=minutes_ago)).isoformat()


def make_root(tmp_path, actions=(), status=None, score=None, health=""):
    (tmp_path / "logs").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "secrets").mkdir()
    (tmp_path / ".env").write_text(f"CTN_TEAM_CODE={CANARY}\n")
    (tmp_path / "secrets" / "swan_accounts.json").write_text(json.dumps([{"username": "a", "password": CANARY}]))
    (tmp_path / "logs" / "swan_actions.jsonl").write_text("".join(json.dumps(a) + "\n" for a in actions))
    t = NOW.timestamp()
    st = {"ts": iso(1), "per_min": 2.5, "rate_limited_last_hour": 0,
          "llm": [{"model": "flash-lite", "parked_until": None, "why": None},
                  {"model": "gpt-oss", "parked_until": None, "why": None}],
          "accounts": {"live": 46, "voices": 12, "boosters": 34, "used": 46, "suspended": 0}}
    st.update(status or {})
    st["llm"] = [{**m, "parked_until": m["parked_until"] and t + m["parked_until"]} for m in st["llm"]]
    (tmp_path / "data" / "status.json").write_text(json.dumps(st))
    if score is not None:
        (tmp_path / "data" / "score.json").write_text(json.dumps(score))
    (tmp_path / "data" / "health_state").write_text(health)
    return tmp_path


def write(minutes_ago, text="hello", act="reply"):
    return {"ts": iso(minutes_ago), "act": act, "live": True, "persona": "lani", "username": "lani_42",
            "post_id": 123, "text": text, "target_text": "<script>alert('target')</script>"}


def page(root, service="active"):
    ctx = build.gather(root, NOW, service)
    return ctx, build.render(ctx)


def test_green_when_running(tmp_path):
    ctx, html = page(make_root(tmp_path, [write(3), write(70)]))
    assert ctx["banner"]["level"] == "green" and "3 min ago" in ctx["banner"]["text"]
    assert ctx["writes"]["hour"] == 1 and ctx["writes"]["planned"] == 150


def test_red_when_service_down_or_health_problem(tmp_path):
    root = make_root(tmp_path, [write(3)])
    assert page(root, service="inactive")[0]["banner"]["level"] == "red"
    (root / "data" / "health_state").write_text("BOT NOT WRITING: no live write for 95 min")
    ctx, _ = page(root)
    assert ctx["banner"] == {"level": "red", "text": "BOT NOT WRITING: no live write for 95 min"}


def test_red_when_every_llm_parked_amber_on_fallback(tmp_path):
    parked = {"llm": [{"model": "flash-lite", "parked_until": 3600, "why": "daily quota"},
                      {"model": "gpt-oss", "parked_until": 600, "why": "per-minute limit"}]}
    assert page(make_root(tmp_path, [write(3)], parked))[0]["banner"]["level"] == "red"


def test_amber_on_fallback_llm(tmp_path):
    fallback = {"llm": [{"model": "flash-lite", "parked_until": 3600, "why": "daily quota"},
                        {"model": "gpt-oss", "parked_until": None, "why": None}]}
    ctx, _ = page(make_root(tmp_path, [write(3)], fallback))
    assert ctx["banner"]["level"] == "amber" and "gpt-oss" in ctx["banner"]["text"]
    assert ctx["llm"]["rank"] == "2nd"


def test_amber_when_status_stale(tmp_path):
    ctx, _ = page(make_root(tmp_path, [write(3)], {"ts": iso(12)}))
    assert ctx["banner"]["level"] == "amber" and "12 min" in ctx["banner"]["text"]


def test_score_delta_since_day_rollover(tmp_path):
    # the day rolled over at 13:00 UTC on 21 Oct (midnight Sydney, 9pm Perth)
    score = [{"ts": "2026-10-21T12:30:00+00:00", "score": 2500, "rank": 20, "teams": 145, "by": "marc"},
             {"ts": iso(60), "score": 3140, "rank": 14, "teams": 145, "by": "kim"}]
    ctx, html = page(make_root(tmp_path, [write(3)], score=score))
    assert ctx["score"]["delta"] == 640 and ctx["day_start"] == "9pm"
    assert ctx["milestone"]["name"] == "Poll 2" and ctx["milestone"]["reached"]
    assert "3,140" in html and "+640" in html


def test_no_secret_and_no_script_reaches_the_page(tmp_path, monkeypatch):
    monkeypatch.setenv("CTN_TEAM_CODE", CANARY)
    evil = write(3, text="<script>alert(1)</script><img src=x onerror=alert(2)>")
    _, html = page(make_root(tmp_path, [evil]))
    assert CANARY not in html
    assert "<script" not in html and "<img" not in html and "&lt;script&gt;" in html
    assert "alert('target')" not in html                 # other people's text is never rendered


def test_long_parks_only_in_activity(tmp_path):
    parks = [{"ts": iso(5), "act": "llm_park", "model": "m1", "why": "per-minute limit",
              "until": (NOW - dt.timedelta(minutes=4)).isoformat()},
             {"ts": iso(6), "act": "llm_park", "model": "m2", "why": "daily quota",
              "until": (NOW + dt.timedelta(hours=9)).isoformat()}]
    ctx, _ = page(make_root(tmp_path, parks + [write(3)]))
    texts = [r["text"] for r in ctx["activity"]]
    assert any("m2" in t for t in texts) and not any("m1" in t for t in texts)


def test_tail_skips_cut_first_line(tmp_path):
    p = tmp_path / "a.jsonl"
    p.write_text("".join(json.dumps({"i": i, "pad": "x" * 50}) + "\n" for i in range(100)))
    recs = build.tail_jsonl(p, nbytes=1000)
    assert recs and recs[-1]["i"] == 99 and all("pad" in r for r in recs)
