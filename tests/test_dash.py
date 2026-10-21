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
    tmp_path.mkdir(exist_ok=True)
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
    evil = dict(write(3), target_post=99, target_text="<script>alert('t')</script> see https://evil.example/x")
    _, html = page(make_root(tmp_path / "b", [evil]))
    assert "&lt;script&gt;alert(&#39;t&#39;)" in html          # other people's text: escaped, links not clickable
    assert "evil.example" not in html and "[link]" in html and html.count("<script") == 1


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
    assert kinds == [("bad", "post hidden"), ("group", "ops ×5"), ("write", "reply"), ("group", "LLM parked ×2")]
    assert ctx["activity"][1]["text"] == ("2 deploys (latest def5678 two) · "
                                          "gemini-c, gemini-b, gemini-a: daily quota until 17:00")
    assert html.count("<details class=\"x\" id=\"g-") == 2


def rec(minutes_ago, act, post_id, persona="dan", **kw):
    return {"ts": iso(minutes_ago), "act": act, "live": True, "persona": persona, "username": f"{persona}_1",
            "account_id": 500 + len(persona), "post_id": post_id, "text": f"{act} by {persona}", **kw}


def test_amplified_post_is_one_conversation(tmp_path):
    acts = [rec(300, "post", 1, frame="F1_blank_cheque", lever="loss", amp_level="heavy"),
            {"ts": iso(300), "act": "amp_plan", "live": True, "post_id": 1, "level": "heavy", "likes": 3,
             "replies": ["one_liner"] * 5, "reposts": 1}]
    acts += [rec(298 - i, "thread", 10 + i, persona=p, amp_post=1, target_post=1, target_author=503, style="one_liner")
             for i, p in enumerate(["ana", "isla", "sione", "mere", "ruth"])]
    acts += [rec(290, "thread_answer", 20, amp_post=1, target_post=12, target_author=505),
             rec(289, "repost", 21, persona="ana", amp_post=1, target_post=1, text=""),
             {"ts": iso(288), "act": "like", "live": True, "post_id": 1, "username": "x", "role": "booster"},
             {"ts": iso(240), "act": "amp_measure", "post_id": 1, "level": "heavy", "at_h": 1.0, "views": 9,
              "own_views": 4, "citizen_likes": 2, "citizen_replies": 1, "best_rank": 30},
             rec(10, "reply", 30, persona="ben", target_post=77, target_author=9, target_text="who checks?")]
    ctx, html = page(make_root(tmp_path, acts))
    rows = [r for r in ctx["activity"] if r["kind"] == "write"]
    assert [r["act"] for r in rows] == ["reply", "post"]          # the reply is newer than anything in the thread
    post = rows[1]
    assert len(post["children"]) == 5 and len(post["shown"]) == build.THREAD_SHOWN and len(post["more"]) == 2
    assert post["children"][2]["answers"][0]["act"] == "thread_answer"       # under the reply it answers (#12)
    assert post["reposts"] == ["ana"] and post["likes"] == 1 and post["plan"]["replies"] == 5
    assert post["measures"][0]["views"] == 5 and "2 citizen ♥" in post["summary"]
    assert post["latest"] == build.hm(NOW - dt.timedelta(minutes=240)) and "posted" in html
    assert ("frame", "blank cheque (F1)") in post["why"] and 'id="w1-more"' in html
    assert rows[0]["target"]["text"] == "who checks?" and not rows[0]["target"]["ours"]


def test_second_voice_reply_back_and_rejects_attach(tmp_path):
    acts = [{"ts": iso(62), "act": "reject", "why": "unapproved_number_79,", "mode": "reply", "persona": "dan",
             "raw": "first try"},
            {"ts": iso(61), "act": "reject", "why": "too_long", "mode": "reply", "persona": "dan", "raw": "x",
             "draft_id": "d1"},
            rec(60, "reply", 40, target_post=77, target_author=9, target_text="yes because", draft_id="d1"),
            rec(50, "second_voice", 41, persona="mere", target_post=77, target_author=9),
            rec(5, "reply_back", 42, target_post=43, target_author=9, target_text="but hospitals?",
                parent_post=40, parent_text="reply by dan"),
            rec(4, "reply", 44, persona="isla", target_post=78, target_author=8)]
    ctx, _ = page(make_root(tmp_path, acts))
    rows = [r for r in ctx["activity"] if r["kind"] == "write"]
    assert [r["post"] for r in rows] == [44, 40]                  # the reply-back bumped its conversation
    convo = rows[1]
    assert [r["why"] for r in convo["rejects"]] == ["too long"]   # by draft_id, not the older guess
    assert convo["children"][0]["act"] == "second_voice" and convo["answers"][0]["act"] == "reply_back"
    assert "they answered" in convo["summary"]


def test_old_records_match_rejects_by_persona_and_time(tmp_path):
    acts = [{"ts": iso(90), "act": "reject", "why": "stale", "mode": "reply", "persona": "dan", "raw": "old"},
            {"ts": iso(12), "act": "reject", "why": "dup", "mode": "reply", "persona": "dan", "raw": "new"},
            rec(10, "reply", 40, target_post=77, target_author=9)]
    ctx, _ = page(make_root(tmp_path, acts))
    assert [r["why"] for r in ctx["activity"][0]["rejects"]] == ["dup"]


def test_facts_section_lists_pauses_first_and_hides_decided(tmp_path):
    root = make_root(tmp_path)
    (root / "content").mkdir()
    (root / "content" / "facts.toml").write_text((pathlib.Path(__file__).resolve().parents[1] / "content" /
                                                  "facts.toml").read_text())
    base = dict(site="daily-kingstonia", slug="s", quote="<script>alert(1)</script> The poll moved.", status="open")
    props = [dict(base, id=1, kind="angle", idea="An idea"), dict(base, id=2, kind="angle", idea="Another"),
             dict(base, id=3, kind="contradiction", fact="polls", text="Polls: No just ahead.", note="No ahead"),
             dict(base, id=4, kind="new_fact", key="k", text="T", note="n", new_numbers=["36.2%"]),
             dict(base, id=5, kind="reword", fact="nurses", text="N", note="n")]
    (root / "data" / "fact_proposals.jsonl").write_text("".join(json.dumps(p) + "\n" for p in props))
    (root / "data" / "facts_paused.json").write_text(json.dumps(
        {"polls": {"since": iso(30), "proposal": 3}, "nurses": {"since": "2026-10-01T00:00:00Z", "proposal": 9}}))
    (root / "content" / "fact_decisions.jsonl").write_text(json.dumps({"id": 5, "status": "rejected"}) + "\n")
    ctx, html = page(root)
    f = ctx["facts"]
    assert [p["fact"] for p in f["paused"]] == ["polls"]                  # nurses was re-checked after its pause
    assert [i["id"] for i in f["proposals"]] == [3, 4, 2, 1] and f["proposals"][0]["paused"]   # 5 is decided
    assert ctx["banner"]["level"] == "amber" and "FACT PAUSED: polls" in ctx["banner"]["text"]
    assert "python scripts/facts_review.py --accept 3 --same-key" in html and "--reject 1,2" not in html
    assert "--reject 2,1" in html and "<script>alert(1)" not in html and "&lt;script&gt;" in html
