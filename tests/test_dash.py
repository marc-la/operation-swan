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


def test_amber_when_every_llm_parked_briefly(tmp_path):
    brief = {"llm": [{"model": "flash-lite", "parked_until": 60, "why": "per-minute limit"},
                     {"model": "gpt-oss", "parked_until": 90, "why": "daily quota"}]}
    ctx, _ = page(make_root(tmp_path, [write(3)], brief))
    assert ctx["banner"]["level"] == "amber" and ctx["banner"]["text"].startswith("LLMS BUSY")


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
    assert html.count("<script") == 1 and '<script src="app.js" defer></script>' in html    # no inline script
    assert "<img" not in html and "&lt;script&gt;" in html
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


def test_score_rate_history_and_llm_chain(tmp_path):
    score = [{"ts": "2026-10-21T12:00:00+00:00", "score": 2500, "rank": 20, "teams": 145, "by": "marc"},
             {"ts": "2026-10-22T01:00:00+00:00", "score": 2860, "rank": 16, "teams": 145, "by": "kim"},
             {"ts": iso(0), "score": 3140, "rank": 14, "teams": 145, "by": "kim"}]
    fallback = {"llm": [{"model": "flash-lite", "parked_until": 3600, "why": "daily quota"},
                        {"model": "gpt-oss", "parked_until": None, "why": None}]}
    ctx, html = page(make_root(tmp_path, [write(m) for m in range(40, 0, -1)], fallback, score=score))
    assert ctx["score"]["per_hour"] == round(640 / 17)            # 13:00 UTC roll-over to 06:00 UTC = 17 h
    assert [h["change"] for h in ctx["history"]] == [280, 360, None]
    assert [m["state"] for m in ctx["llm"]["chain"]] == ["daily quota until 15:00", "in use"]
    assert len(ctx["activity"]) == build.ACTIVITY_TOP and len(ctx["older"]) == 40 - build.ACTIVITY_TOP
    assert '<details id="bot">' in html and "#14" in html


def test_main_writes_page_robots_and_script(tmp_path, monkeypatch):
    (tmp_path / "r").mkdir()
    root, out = make_root(tmp_path / "r", [write(3)]), tmp_path / "out"
    monkeypatch.setattr(sys, "argv", ["build", "--root", str(root), "--out", str(out)])
    monkeypatch.setattr(build, "service_state", lambda: "active")
    build.main()
    assert {p.name for p in out.iterdir()} == {"index.html", "robots.txt", "app.js"}
    assert "location.reload" in (out / "app.js").read_text()


def test_back_to_back_parks_and_deploys_are_bundled(tmp_path):
    def park(minutes_ago, model, hours=3):
        return {"ts": iso(minutes_ago), "act": "llm_park", "model": model, "why": "daily quota",
                "until": (NOW + dt.timedelta(hours=hours)).isoformat()}
    acts = [park(30, "gemini-a"), park(29, "gemini-b"), write(20), park(10, "gemini-a"), park(9, "gemini-b"),
            park(8, "gemini-c")]
    root = make_root(tmp_path, acts)
    (root / "logs" / "alerts.log").write_text(
        f"{iso(5)[:19]}Z [swan-ec2] deployed abc1234 Marc: one\n{iso(4)[:19]}Z [swan-ec2] deployed def5678 Marc: two\n"
        f"{iso(3)[:19]}Z [swan-ec2] @lani: post #9 hidden by the moderator (1 hidden)\n")
    ctx, html = page(root)
    kinds = [(r["kind"], r["what"]) for r in ctx["activity"]]
    assert kinds == [("bad", "post hidden"), ("group", "deploys ×2"), ("group", "LLM parked ×3"),
                     ("write", "reply"), ("group", "LLM parked ×2")]
    assert ctx["activity"][2]["text"] == "gemini-c, gemini-b, gemini-a: daily quota until 17:00"
    assert ctx["activity"][1]["text"] == "latest: def5678 Marc: two"
    assert html.count("<details class=\"x\"") == 3
