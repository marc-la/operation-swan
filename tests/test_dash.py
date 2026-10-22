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
    score = [{"ts": "2026-10-21T12:30:00+00:00", "score": 6500, "rank": 20, "teams": 145, "by": "marc"},
             {"ts": iso(60), "score": 7140, "rank": 14, "teams": 145, "by": "kim"}]
    ctx, html = page(make_root(tmp_path, [write(3)], score=score))
    assert ctx["score"]["delta"] == 640 and ctx["day_start"] == "9pm"
    assert ctx["milestone"]["name"] == "Poll 2" and ctx["milestone"]["reached"]     # 7,000 since 20 Oct
    assert "7,140" in html and "+640" in html


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
    root = make_root(tmp_path, [write(m) for m in range(40, 0, -1)], fallback, score=score)
    (root / "data" / "llm_usage.json").write_text(json.dumps({"2026-10-21": {"flash-lite": 500, "gpt-oss": 12},
                                                              "2026-10-20": {"gpt-oss": 999}}))  # 21 Oct Pacific
    ctx, html = page(root)
    assert ctx["score"]["per_hour"] == round(640 / 17)            # 13:00 UTC roll-over to 06:00 UTC = 17 h
    assert [h["change"] for h in ctx["history"]] == [280, 360, None]
    assert [m["state"] for m in ctx["llm"]["chain"]] == ["daily quota until 15:00", "ready"]
    assert [m["calls"] for m in ctx["llm"]["chain"]] == [500, 12]
    assert "flash-lite (500 calls today)" in html
    assert len(ctx["activity"]) == build.ACTIVITY_TOP and len(ctx["older"]) == 40 - build.ACTIVITY_TOP
    assert '<details id="bot">' in html and "#14" in html


def test_main_writes_page_robots_and_script(tmp_path, monkeypatch):
    (tmp_path / "r").mkdir()
    root, out = make_root(tmp_path / "r", [write(3)]), tmp_path / "out"
    monkeypatch.setattr(sys, "argv", ["build", "--root", str(root), "--out", str(out)])
    monkeypatch.setattr(build, "service_state", lambda: "active")
    build.main()
    assert {p.name for p in out.iterdir()} == {"index.html", "lab.html", "robots.txt", "app.js"}
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
    assert 'class="down"><b>Paused: polls</b>' in html                   # red, at the top of Facts (Marc, 22 Oct)
    assert "--accept" not in html and "<script>alert(1)" not in html      # no review queue on the page any more
    assert "4 still open" in html


# ---- Reach (2026-10-22): did we answer every citizen we could, fast, and did it convert? ----
def refresh(minutes_ago, funnel, candidates=3):
    return {"ts": iso(minutes_ago), "act": "refresh", "candidates": candidates, "funnel": funnel}


def rowof(ctx, start):
    return next(r for r in ctx["reach"]["rows"] if r["name"].startswith(start))


def test_reach_green_when_every_citizen_answered_and_collapsed(tmp_path):
    f = {"2026-10-22T04": {"seen": 10, "answered": 8, "skipped": {"off_topic": 2}, "lost": {}, "pending": {}},
         "2026-10-22T05": {"seen": 2, "answered": 1, "skipped": {}, "lost": {}, "pending": {"queued": 1}}}
    ctx, html = page(make_root(tmp_path, [refresh(1, f)]))
    r = ctx["reach"]
    assert r["verdict"] == "keeping up" and not r["open"] and not r["fixes"]
    assert r["tile"]["answered"] == 8 and r["tile"]["answerable"] == 8 and "8/8 answered" in r["summary"]
    assert "Citizens answered" in html and "Reach: keeping up" in html and "2 off topic" in r["extra"][0]


def test_reach_losing_citizens_is_red_open_with_the_reason(tmp_path):
    f = {"2026-10-22T04": {"seen": 5, "answered": 3, "skipped": {}, "lost": {"gate:near_duplicate": 2}, "pending": {}},
         "2026-10-22T05": {"seen": 0, "answered": 0, "skipped": {}, "lost": {}, "pending": {}}}
    ctx, html = page(make_root(tmp_path, [refresh(1, f)]))
    row = rowof(ctx, "Citizens answered")
    assert ctx["reach"]["verdict"] == "losing citizens" and ctx["reach"]["open"] and row["light"] == "red"
    assert "2 lost" in row["now"] and "2 gate:near_duplicate" in row["fix"] and "→ Citizens answered" in html


def test_reach_no_funnel_yet_is_amber_and_page_renders(tmp_path):
    ctx, html = page(make_root(tmp_path, [write(5)]))
    assert ctx["reach"]["tile"] is None and rowof(ctx, "Citizens answered")["light"] == "amber"
    assert "posts last hour" in html


def test_reach_throughput_last_full_hour_against_budget_and_pace(tmp_path):
    f = {"2026-10-22T05": {"seen": 9, "answered": 1, "skipped": {}, "lost": {}, "pending": {"queued": 8}}}
    calm = {"2026-10-22T05": {"seen": 1, "answered": 1, "skipped": {}, "lost": {}, "pending": {}}}
    # NOW is 06:00 UTC: the last full hour is 05:00-06:00; 96 writes there = 1.6/min, one more at 06:00 is not in it
    acts = [dict(write(1 + i * 0.6), post_id=1000 + i) for i in range(96)] + [dict(write(0), post_id=9)]
    ctx, html = page(make_root(tmp_path, [refresh(1, f, candidates=40)] + acts,
                               status={"write_budget": {"limit": 3, "remaining": 2}, "queue": {"candidates": 40}}))
    t = rowof(ctx, "Throughput")
    assert t["now"] == "1.6/min of 3.0 (53%) · pace 2.5" and t["light"] == "amber"          # under 0.9 × 2.5, 40 waiting
    assert ctx["reach"]["verdict"] == "falling behind" and "1.6/min of 3" in ctx["reach"]["summary"]
    assert not any(r["name"].startswith("Longest wait") for r in ctx["reach"]["rows"])
    ctx, _ = page(make_root(tmp_path / "b", [refresh(1, calm)] + acts, status={"queue": {"candidates": 40}}))
    assert rowof(ctx, "Throughput")["light"] == "green"         # every citizen of that hour answered: a quiet hour
    acts = [dict(write(1 + i * 0.4), post_id=1000 + i) for i in range(150)]
    ctx, _ = page(make_root(tmp_path / "c", [refresh(1, f)] + acts))      # at pace, citizens waiting: green
    assert rowof(ctx, "Throughput")["light"] == "green" and rowof(ctx, "Throughput")["now"].startswith("2.5/min")


def test_reach_answered_is_a_share_too(tmp_path):
    f = {"2026-10-22T04": {"seen": 220, "answered": 125, "skipped": {"off_topic": 12}, "lost": {},
                           "pending": {"queued": 83}},
         "2026-10-22T05": {"seen": 2, "answered": 1, "skipped": {}, "lost": {}, "pending": {}}}
    ctx, html = page(make_root(tmp_path, [refresh(1, f)]))
    assert rowof(ctx, "Citizens answered")["now"] == "125 of 208 (60%) · 83 waiting · 0 lost"
    assert "125/208 answered (60%)" in ctx["reach"]["summary"] and "60% · 0 lost" in html


def test_reach_dates_citizen_posts_from_our_post_ids():
    clock = [(100, 1000.0), (200, 2000.0)]
    assert build._written_at(150, clock) == 1500.0
    assert build._written_at(50, clock) is None and build._written_at("x", clock) is None


def test_reach_counts_changes_of_mind_from_portal_messages():
    since = NOW - dt.timedelta(hours=5)
    pts = [{"_t": NOW - dt.timedelta(hours=1), "message": "NPC engagement: 3 likes, 2 contributions to changes of mind "
            "towards your side and 1 contribution to a change of mind away from your side"},
           {"_t": NOW - dt.timedelta(hours=2), "message": "NPC engagement: 1 change of mind on vaccination towards your side, "
            "4 contributions to changes of mind on vaccination towards neither side"},
           {"_t": NOW - dt.timedelta(hours=9), "message": "NPC engagement: 9 contributions to changes of mind towards your side"}]
    m = build._minds(pts, since)
    assert m == {"toward": 3, "away": 1, "neither": 4, "primary_toward": 1}


def test_reach_outcome_first_queue_split_and_notes(tmp_path):
    f = {"2026-10-22T05": {"seen": 1, "answered": 1, "skipped": {}, "lost": {}, "pending": {}}}
    rf = dict(refresh(1, f, candidates=30), groups={"sweep": {"queued": 20}, "older": {"queued": 0}})
    acc = [dict(write(5), llm_calls=2), dict(write(6), llm_calls=1)]
    root = make_root(tmp_path, [rf] + acc)
    (root / "data" / "reach_notes.json").write_text(json.dumps({"Drafts passing": "prompt fix live 15:20, recheck 16:30"}))
    ctx, html = page(root)
    r = ctx["reach"]
    assert r["rows"][0]["name"].startswith("Changes of mind") and r["summary"].startswith("today 0 toward No")
    assert "Queue now: 10 citizens waiting · 20 extra-group posts" in r["extra"]
    assert "In hand: prompt fix live 15:20, recheck 16:30" in html


def test_reach_other_view_change_is_not_counted_as_neither():
    pts = [{"_t": NOW, "message": "NPC engagement: 1 contribution to a change of mind, 2 contributions to changes of "
            "mind on vaccination towards neither side"}]
    assert build._minds(pts, NOW - dt.timedelta(hours=1))["neither"] == 2


# ---- Score & targets: the portal's points by kind, out of Activity (todo/29) ----
def test_points_by_kind_under_score_not_in_activity(tmp_path):
    ev = [{"ts": iso(30), "type": "SCORE_NARRATIVE", "points": 809, "message": "NPC engagement and moderation: 34 likes, "
           "4 reposts, 36 replies, 1 follow, 3 contributions to changes of mind on vaccination towards neither side, "
           "1 first inauthentic report and 2 inauthentic reports"},
          {"ts": iso(90), "type": "SCORE_NARRATIVE", "points": -4,
           "message": "NPC engagement: 2 contributions to changes of mind away from your side"},
          {"ts": iso(120), "type": "SCORE_NARRATIVE", "points": 26,
           "message": "Moderation (×0.5 points): 2 first inauthentic reports"},
          {"ts": iso(150), "type": "SCORE_NARRATIVE", "points": 3000,
           "message": "Narrative: the poll was too close to call (52–48), so both sides share it"},
          {"ts": "2026-10-21T10:00:00+00:00", "type": "SCORE_NARRATIVE", "points": 99, "message": "NPC engagement: 9 likes"}]
    root = make_root(tmp_path, [write(3)])
    (root / "data" / "portal.json").write_text(json.dumps({"ts": iso(1), "events": ev}))
    ctx, html = page(root)
    s = ctx["score_lines"]
    kinds = {r["kind"]: r for r in s["rows"]}
    assert s["total"] == 809 - 4 + 26 + 3000                  # since 9pm Perth only; the 21 Oct line is the day before
    assert sum(r["points"] for r in s["rows"]) == s["total"]  # the split adds up to the portal's totals
    assert kinds["polls"]["points"] == 3000 and kinds["penalties"]["points"] == -4 and not kinds["penalties"]["mixed"]
    assert kinds["blue"]["counts"] == [("first reporter", 3), ("later reporter", 2)] and kinds["blue"]["events"] == 2
    assert kinds["persuasion"]["mixed"] and ("neither side (contribution)", 3) in kinds["persuasion"]["counts"]
    assert kinds["engagement"]["lines"][0]["of"] == 809 and "34 likes" in kinds["engagement"]["lines"][0]["text"]
    assert not any("pts" in r["what"] for r in ctx["activity"] + ctx["older"])
    assert 'id="pts-blue"' in html and "+3,831 since 9pm" in html


# ---- Blue: pending summarised by group, reports by outcome, account outcomes, own-account check (todo/29) ----
def blue_root(tmp_path, own_ids=None, reports=()):
    root = make_root(tmp_path, [write(3)])
    at = lambda m: iso(m)
    ledger = [dict(key="p1", target=1, kind="post", team="c100", status="pending", at=at(-30)),
              dict(key="p2", target=2, kind="post", team="c100", status="pending", at=at(-10)),
              dict(key="a7", target=7, kind="account", team="c200", status="pending", at=at(-50)),
              dict(key="p3", target=3, kind="post", team="c100", status="hidden", at=at(100)),
              dict(key="p5", target=5, kind="post", team="c300", status="hidden", at=at(95)),
              dict(key="p4", target=4, kind="post", team="c200", status="genuine", at=at(90)),
              dict(key="a8", target=8, kind="account", team="c200", status="ruled", at=at(200)),     # run at 180: upheld
              dict(key="a9", target=9, kind="account", team="c300", status="ruled", at=at(130)),     # run at 120: none
              dict(key="a5", target=5, kind="account", team="c300", status="ruled", at=at(70)),      # run at 60: 1 of 2
              dict(key="a6", target=6, kind="account", team="c300", status="ruled", at=at(65)),
              dict(key="a4", target=4, kind="account", team="c300", status="ruled", at=at(20))]      # no run since
    st = dict(ts=iso(1), mode="auto", why="x", pending=3, cap=30, today={"filed": 9}, waiting=[], rings=[], ledger=ledger)
    if own_ids is not None:
        st["own_ids"] = own_ids
    (root / "data" / "blue_status.json").write_text(json.dumps(st))
    (root / "logs" / "blue_reports.jsonl").write_text("".join(json.dumps(r) + "\n" for r in reports))
    ev = [{"ts": iso(180), "points": 7, "message": "Moderation (×0.5 points): 1 upheld account report"},
          {"ts": iso(120), "points": 50, "message": "NPC engagement: 10 likes"},
          {"ts": iso(60), "points": 15, "message": "NPC engagement and moderation: 1 upheld account report"}]
    (root / "data" / "portal.json").write_text(json.dumps({"ts": iso(1), "events": ev}))
    return root


def test_blue_timeline_collapses_runs_in_place_and_account_outcomes(tmp_path):
    ctx, html = page(blue_root(tmp_path))
    items = ctx["blue"]["timeline"]
    assert [(i["kind"], i.get("what") or i["label"]) for i in items] == [
        ("row", "#1"), ("row", "#2"), ("row", "account 7"),                    # pending: never collapsed
        ("run", "2 hidden, " + build.hm(NOW - dt.timedelta(minutes=100)) + "–" + build.hm(NOW - dt.timedelta(minutes=95))),
        ("row", "#4"),                                                           # genuine: never collapsed
        ("row", "account 8"), ("row", "account 9"),
        ("run", "2 accounts suspended or dismissed: 1 of these 2 suspended, "
                + build.hm(NOW - dt.timedelta(minutes=70)) + "–" + build.hm(NOW - dt.timedelta(minutes=65))),
        ("row", "account 4")]
    assert [r["what"] for r in items[3]["rows"]] == ["#3", "#5"]                 # the run opens to the same rows
    words = {r["what"]: r["word"] for r in ctx["blue"]["rows"]}
    assert words["account 8"] == "suspended · +7.5" and words["account 9"] == "dismissed (no points, no lock)"
    assert words["account 4"] == "ruled · outcome not in the portal log yet"
    assert html.count('<details class="run"') == 2 and "team 1" not in html and "group c300" in html
    assert "Own accounts reported: not checked" in html                         # no ids published by swan-blue yet
    assert '<details id="blue">' in html and '<details class="reach" id="reach">' in html   # collapsed by default
    assert 'id="blue-risk"' not in html and "Since 9pm:" not in html            # Marc: less on the page


def test_blue_own_account_check(tmp_path):
    reps = [{"act": "report", "kind": "post", "target": 500, "author": 41},
            {"act": "report", "kind": "account", "target": 42, "author": 42},
            {"act": "ruling", "key": "p500"}]
    ctx, html = page(blue_root(tmp_path, own_ids=[1, 2, 3], reports=reps))
    assert ctx["blue"]["own"] == {"lines": 2, "hits": 0, "accounts": 3} and "Own accounts reported: <b>0</b>" in html
    ctx, html = page(blue_root(tmp_path / "b", own_ids=[41, 42], reports=reps))
    assert ctx["blue"]["own"]["hits"] == 2 and '<p class="down">Own accounts reported' in html
    assert ctx["banner"]["level"] == "amber" and "against our own accounts" in ctx["banner"]["text"]
    assert "OUR OWN ACCOUNTS REPORTED: 2" in ctx["blue"]["summary"]


def test_facts_section_is_the_autopilot_log_with_undo(tmp_path):
    root = make_root(tmp_path)
    (root / "content").mkdir()
    (root / "content" / "facts.toml").write_text((pathlib.Path(__file__).resolve().parents[1] / "content" /
                                                  "facts.toml").read_text())
    base = dict(site="daily-kingstonia", slug="s", quote="The poll moved.", status="open")
    props = [dict(base, id=1, kind="new_fact", key="k1", text="T"), dict(base, id=2, kind="angle", idea="An idea"),
             dict(base, id=3, kind="reword", fact="nurses", text="N"), dict(base, id=4, kind="new_fact", key="k4"),
             dict(base, id=5, kind="contradiction", fact="polls_1021", text="P")]
    (root / "data" / "fact_proposals.jsonl").write_text("".join(json.dumps(p) + "\n" for p in props))
    rec = lambda i, status, m, **kw: dict(id=i, status=status, by="factdesk-auto", decided_at=iso(m), site="daily-"
                                          "kingstonia", slug="s", quote="The poll moved.", summary=f"#{i} {status}", **kw)
    log = [rec(1, "accepted", 50, kind="new_fact", text="T"), rec(2, "logged", 50, kind="angle"),
           rec(3, "failed", 50, kind="reword"), rec(4, "accepted", 40, kind="new_fact"), rec(4, "undone", 30),
           rec(5, "retired", 20, kind="contradiction")]
    (root / "data" / "facts_auto.jsonl").write_text("".join(json.dumps(r) + "\n" for r in log))
    (root / "data" / "facts_auto.toml").write_text('[polls_1021]\ntext = "x"\nnote = "y"\nstatus = "paused"\nsource = '
                                                   f'"s"\nchecked = {iso(20)[:19]}Z\n')
    (root / "data" / "facts_paused.json").write_text(json.dumps({"polls_1021": {"since": iso(60), "proposal": 5}}))
    ctx, html = page(root)
    f = ctx["facts"]
    assert f["auto"]["on"] and f["auto"]["today"] == 3 and not f["paused"]          # the overlay settled the pause
    assert [(d["id"], d["status"], d["reverted"]) for d in f["auto"]["log"]] == [
        (5, "retired", False), (4, "accepted", True), (1, "accepted", False)]      # what went live, newest first
    assert f["auto"]["log"][2]["text"] == "T" and f["auto"]["log"][0]["text"].startswith("Retired: x")
    assert f["auto"]["log"][0]["paper"] == "Daily Kingstonia"
    assert "facts_review.py --undo 5" in html and "--undo 1" in html and "--undo 4" not in html   # #4 reverted
    assert [p["id"] for p in f["proposals"]] == [3, 4]                             # failed and undone: for a human
    assert "2 approved automatically" in html and "2 still open" in html and "An idea" not in html


def test_trending_pulse_is_one_line_at_the_bottom(tmp_path):
    p = {"ts": iso(20), "act": "pulse", "id": 77, "hooks": [{"text": "ferry cuts"}, {"text": "nurses"}],
         "no_shapes": ["a"], "yes_lines": ["b", "c"], "avoid": []}
    _, html = page(make_root(tmp_path, [write(3), p]))
    assert '<details id="pulse"' not in html and html.index('id="pulse"') > html.index('id="facts"')
    assert "from Trending #77: 2 hooks, 1 for No, 2 Yes lines, 0 overused; first hook “ferry cuts”" in html
