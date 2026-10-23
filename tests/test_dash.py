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


def test_second_llm_is_not_degraded_but_the_sixth_is(tmp_path):
    def chain(n):          # the first n-1 models parked, the nth ready
        return {"llm": [{"model": f"m{i}", "parked_until": 3600, "why": "daily quota"} for i in range(n - 1)]
                + [{"model": f"m{n}", "parked_until": None, "why": None}]}
    ctx, _ = page(make_root(tmp_path / "a", [write(3)], chain(2)))
    assert ctx["banner"]["level"] == "green" and ctx["llm"]["rank"] == "2nd" and not ctx["llm"]["degraded"]
    ctx, _ = page(make_root(tmp_path / "b", [write(3)], chain(6)))
    assert ctx["banner"]["level"] == "amber" and "m6" in ctx["banner"]["text"] and ctx["llm"]["degraded"]


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
    assert len(ctx["activity"]) == build.ACTIVITY_TOP and ctx["older"] == []      # plain writes are not critical
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
    assert kinds == [("hidden", "post hidden"), ("group", "ops ×5"), ("write", "1st reply"), ("group", "LLM parked ×2")]
    assert ctx["activity"][1]["text"] == ("2 deploys (latest def5678 two) · "
                                          "gemini-c, gemini-b, gemini-a: daily quota until 17:00")
    assert html.count("<details class=\"x\" id=\"g-") == 2


def test_older_activity_keeps_only_critical_events(tmp_path):
    acts = [{"ts": iso(500), "act": "suspended", "username": "lani_42"},
            {"ts": iso(499), "act": "register", "username": "new_1", "persona": "lani"}]
    acts += [write(m) for m in range(40, 0, -1)]
    root = make_root(tmp_path, acts)
    (root / "logs" / "alerts.log").write_text(
        f"{iso(450)[:19]}Z [swan-ec2] deployed abc1234 Marc: one\n"
        f"{iso(440)[:19]}Z [swan-ec2] @lani: post #9 hidden by the moderator (1 hidden)\n")
    ctx, _ = page(root)
    assert len(ctx["activity"]) == build.ACTIVITY_TOP
    assert [r["what"] for r in ctx["older"]] == ["post hidden", "deploy", "new account", "SUSPENDED"]


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
    assert "Recently added (0)" in html and 'id="facts-recent"' not in html


# ---- Reach (2026-10-23): three lights, speed / volume / conversion, each against its own bar ----
def refresh(minutes_ago, funnel, candidates=3):
    return {"ts": iso(minutes_ago), "act": "refresh", "candidates": candidates, "funnel": funnel}


def rowof(ctx, start):
    return next(r for r in ctx["reach"]["rows"] if r["name"].startswith(start))


def light(ctx, key):
    return next(i for i in ctx["reach"]["lights"] if i["key"] == key)["light"]


def test_reach_is_three_lights_and_zero_posting_is_red_not_green(tmp_path):
    f = {"2026-10-22T05": {"seen": 3, "answered": 3, "skipped": {}, "lost": {}, "pending": {}}}
    ctx, html = page(make_root(tmp_path, [refresh(1, f), write(90)]))       # everything we saw was answered, then silence
    assert [i["key"] for i in ctx["reach"]["lights"]] == ["speed", "volume", "conversion", "stealth"]
    assert light(ctx, "volume") == "red" and "last post 1 h" in rowof(ctx, "Posting")["now"]
    assert ctx["worst"] == "red" and html.count('class="light ') == 4 and "Citizens answered" not in html
    assert light(ctx, "speed") == "grey"                                     # nothing timed: never green by default


def test_reach_volume_green_at_budget_and_amber_between(tmp_path):
    full = [write(0.3 * i + 0.1) for i in range(100)]                       # 100 writes in 30 min = 3.3/min
    ctx, _ = page(make_root(tmp_path, full))
    assert light(ctx, "volume") == "green" and rowof(ctx, "Posting")["now"].startswith("3.3/min of 3")
    ctx, _ = page(make_root(tmp_path / "b", [write(0.5 * i + 0.1) for i in range(40)]))   # 1.3/min = 44%
    assert light(ctx, "volume") == "amber"


def test_reach_few_voices_and_lost_citizens_turn_volume_down(tmp_path):
    busy = [write(0.3 * i + 0.1) for i in range(100)]
    ctx, _ = page(make_root(tmp_path, busy, status={"accounts": {"voices": 4}}))
    assert rowof(ctx, "Voices")["light"] == "amber" and light(ctx, "volume") == "amber"
    f = {"2026-10-22T04": {"seen": 5, "answered": 3, "skipped": {}, "lost": {"gate:near_duplicate": 2}, "pending": {}},
         "2026-10-22T05": {"seen": 0, "answered": 0, "skipped": {}, "lost": {}, "pending": {}}}
    ctx, html = page(make_root(tmp_path / "b", [refresh(1, f)] + busy))
    row = rowof(ctx, "Citizens lost")
    assert row["light"] == "red" and light(ctx, "volume") == "red" and "2 gate:near_duplicate" in row["fix"]
    assert "→ Citizens lost" in html


def test_reach_speed_from_reply_times(tmp_path):
    # our posts 100 and 200 were written 30 and 20 min ago (ids rise with time), so citizen post 150 dates to 25 min ago
    acts = [dict(write(30), post_id=100), dict(write(20), post_id=200),
            dict(write(1), act="reply", source="latest", target_post=150, post_id=300)]
    ctx, _ = page(make_root(tmp_path, acts))
    r = rowof(ctx, "Reply time, new")
    assert r["now"] == "24.0 min" and r["light"] == "red" and light(ctx, "speed") == "red"
    acts[2] = dict(acts[2], ts=iso(18), target_post=190)                   # post 190 dates to 21 min ago: answered in 3
    ctx, _ = page(make_root(tmp_path / "b", acts))
    assert rowof(ctx, "Reply time, new")["now"] == "3.0 min" and light(ctx, "speed") == "green"


def test_reach_does_not_date_a_post_across_a_long_gap():
    clock = [(100, 1000.0), (200, 1000.0 + 3 * 3600)]                      # no post of ours for 3 h: the guess is useless
    assert build._written_at(150, clock) is None


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


def test_reach_conversion_queue_and_notes(tmp_path):
    f = {"2026-10-22T05": {"seen": 1, "answered": 1, "skipped": {"off_topic": 2}, "lost": {}, "pending": {}}}
    rf = dict(refresh(1, f, candidates=30), groups={"sweep": {"queued": 20}, "older": {"queued": 0}})
    acc = [dict(write(5), llm_calls=2), dict(write(6), llm_calls=1)]
    root = make_root(tmp_path, [rf] + acc)
    (root / "data" / "reach_notes.json").write_text(json.dumps({"Drafts passing": "prompt fix live 15:20, recheck 16:30"}))
    ctx, html = page(root)
    r = ctx["reach"]
    assert rowof(ctx, "Changes of mind")["now"].startswith("net 0: 0 toward No") and light(ctx, "conversion") == "amber"
    assert rowof(ctx, "Citizens waiting")["now"] == "10" and "20 extra-group posts queued" in r["extra"]
    assert "2 off topic" in r["extra"][0] and "In hand: prompt fix live 15:20, recheck 16:30" in html


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
    assert 'class="kpis tiles"' in html and 'id="pts-' not in html and "+3,831 since 9pm" in html
    assert [t["kind"] for t in s["tiles"]] == ["persuasion", "engagement", "blue", "polls", "penalties"]
    # the score-over-time rows open to the portal's own notes behind each change
    (root / "data" / "score.json").write_text(json.dumps([
        {"ts": iso(200), "score": 1000, "rank": 9, "by": "portal"}, {"ts": iso(100), "score": 4026, "rank": 8, "by": "portal"},
        {"ts": iso(10), "score": 4831, "rank": 7, "by": "portal"}]))
    ctx, html = page(root)
    notes = [[n["points"] for n in h["notes"]] for h in ctx["history"]]
    assert notes == [[809, -4], [26, 3000], []] and html.count('<details class="note"') == 2


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
        ("run", "2 unclear, " + build.hm(NOW - dt.timedelta(minutes=70)) + "–"
                + build.hm(NOW - dt.timedelta(minutes=65))),
        ("row", "account 4")]
    assert [r["what"] for r in items[3]["rows"]] == ["#3", "#5"]                 # the run opens to the same rows
    out = {r["what"]: (r["out"], r["note"], r["css"]) for r in ctx["blue"]["rows"]}
    assert out["account 8"] == ("suspended", "+7.5", "up") and out["account 9"] == ("dismissed", "no points, no lock", "")
    assert out["account 4"] == ("ruled", "outcome not in the portal log yet", "")
    # pending 3 + 2 hidden + genuine + 1 suspended + 1 dismissed + 2 unclear (1 of 2 suspended) + account 4 unreported
    assert ctx["blue"]["counts"] == {"success": 4, "failed": 3, "pending": 4}
    assert out["#1"][2] == "warn" and out["#4"][2] == "down" and out["#3"][2] == "up"   # pending, genuine, hidden
    assert '<td class="out warn">pending</td><td class="det">#1 · group c100 · rules ' in html
    assert '<span class="out up">▸ 2 hidden</span>' in html
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
    assert ctx["blue_banner"]["level"] == "red" and "against our own accounts" in ctx["blue_banner"]["text"]
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
    assert "2 recently added" in html and "An idea" not in html and not f["auto"]["problems"]


def test_facts_loud_only_for_a_failed_test_or_a_stalled_desk(tmp_path):
    root = make_root(tmp_path)
    (root / "content").mkdir()
    (root / "content" / "facts.toml").write_text((pathlib.Path(__file__).resolve().parents[1] / "content" /
                                                  "facts.toml").read_text())
    (root / "data" / "factdesk_state.json").write_text(json.dumps({"seen": {}, "last_run": iso(30)}))
    ctx, _ = page(root)
    assert not ctx["facts"]["auto"]["problems"] and ctx["banner"]["level"] == "green"
    (root / "data" / "factdesk_state.json").write_text(json.dumps({"seen": {}, "last_run": iso(200)}))
    (root / "data" / "facts_auto.jsonl").write_text(json.dumps(dict(
        id=9, status="failed", by="factdesk-auto", decided_at=iso(40),
        summary="#9 left for a human: tests/test_facts.py failed with this run's changes (1 failed)")) + "\n")
    ctx, html = page(root)
    probs = ctx["facts"]["auto"]["problems"]
    assert len(probs) == 2 and "test_facts.py failed" in probs[0] and "hasn't run since" in probs[1]
    assert ctx["banner"]["level"] == "amber" and ctx["banner"]["text"].startswith("FACTS: tests/test_facts.py failed")
    assert "2 problems" in html


def test_trending_pulse_is_one_line_at_the_bottom(tmp_path):
    p = {"ts": iso(20), "act": "pulse", "id": 77, "hooks": [{"text": "ferry cuts"}, {"text": "nurses"}],
         "no_shapes": ["a"], "yes_lines": ["b", "c"], "avoid": []}
    _, html = page(make_root(tmp_path, [write(3), p]))
    assert '<details id="pulse"' not in html and html.index('id="pulse"') > html.index('id="facts"')
    assert "from Trending #77: 2 hooks, 1 for No, 2 Yes lines, 0 overused; first hook “ferry cuts”" in html


def test_activity_alert_colours_repost_text_and_portal_accounts(tmp_path):
    acts = [{"ts": iso(9), "act": "reply", "live": True, "post_id": 70, "username": "dan_1", "text": "x",
             "target_post": 60, "target_author": 9, "target_text": "Keep the ferries running, all of them, please."},
            {"ts": iso(8), "act": "repost", "live": True, "post_id": 71, "target_post": 60, "target_author": 9,
             "username": "alim10", "role": "swarm"},
            {"ts": iso(7), "act": "repost", "live": True, "post_id": 72, "target_post": 61, "target_author": 8,
             "username": "alim10", "role": "swarm"},
            {"ts": iso(6), "act": "suspended", "username": "lani_42"}]
    root = make_root(tmp_path, acts)
    (root / "logs" / "alerts.log").write_text(
        f"{iso(5)[:19]}Z [swan-ec2] DEPLOY FAILED, rolled back to abc1234. Bad commit: x\n"
        f"{iso(4)[:19]}Z [swan-ec2] BLUE: #2 ruled genuine (reply ring)\n"
        f"{iso(3)[:19]}Z [swan-ec2] @lani: post #9 hidden by the moderator (1 hidden)\n")
    (root / "data" / "portal.json").write_text(json.dumps({"ts": iso(1), "accounts": {
        "registered": 61, "banned": 13, "max_total": 200, "max_active": 50}}))
    ctx, html = page(root)
    kinds = {r["what"]: r["kind"] for r in ctx["activity"] + ctx["older"]}
    assert kinds["deploy failed"] == "deployfail" and kinds["Blue"] == "blue" and kinds["post hidden"] == "hidden"
    assert kinds["SUSPENDED"] == "susp"
    texts = [r["text"] for r in ctx["activity"] if r.get("act") == "repost"]
    assert texts == ["reposted #61 by account 8 (text not in our logs)",
                     "reposted #60 by account 9: “Keep the ferries running, all of them, please.”"]
    assert "61 registered · 13 banned · 50 active max" in html and 'id="bot-own-accounts"' not in html


def test_combined_portal_lines_split_blue_by_its_counts():
    """Marc, 22 Oct: 'NPC engagement and moderation' lines are mostly engagement. Blue takes its counts' worth (first
    report 25, later 5, upheld account 15, times the line's ×rate), the rest goes to engagement and persuasion."""
    t = NOW - dt.timedelta(hours=1)
    lines = [(550, "NPC engagement and moderation: 21 likes, 1 repost, 19 replies, 3 contributions to changes of mind "
                   "on vaccination towards neither side and 6 first inauthentic reports"),
             (684, "NPC engagement and moderation: 29 likes, 1 repost, 32 replies, 1 follow, 2 contributions to changes "
                   "of mind on vaccination towards neither side, 1 contribution to a change of mind towards your side, "
                   "1 inauthentic report and 1 upheld account report"),
             (24, "Moderation (×0.1 points): 8 first inauthentic reports"),
             (169, "Moderation (×0.5 points): 13 first inauthentic reports"),
             (265, "NPC engagement: 10 likes, 3 reposts, 11 replies and 1 follow")]
    pts = [dict(_t=t, points=p, message=m) for p, m in lines]
    kinds = {r["kind"]: r for r in build.score_lines(pts, NOW - dt.timedelta(hours=2))["rows"]}
    assert kinds["blue"]["points"] == 150 + 20 + 24 + 169 and kinds["blue"]["mixed"]
    assert kinds["engagement"]["points"] + kinds["persuasion"]["points"] == 550 - 150 + 684 - 20 + 265


def test_stealth_light_counts_new_bans_today(tmp_path):
    root = make_root(tmp_path, [write(3)])
    log = {"counts": [{"ts": iso(1500), "registered": 50, "banned": 2}, {"ts": iso(30), "registered": 52, "banned": 5}],
           "suspended": [{"ts": iso(30), "username": "a_b", "id": 7, "why": "3 posts hidden"}]}
    (root / "data" / "portal.json").write_text(json.dumps({"ts": iso(1), "account_log": log}))
    ctx, html = page(root)
    st = next(i for i in ctx["reach"]["lights"] if i["key"] == "stealth")
    assert st["head"] == "3 bans" and st["light"] == "green" and "3 posts hidden ×1" in rowof(ctx, "New bans")["now"]
    assert "@a_b" in html


def test_first_and_second_replies_are_split_not_lumped(tmp_path):
    score = [{"ts": iso(60), "score": 100, "rank": 9, "teams": 50, "by": "kim"},
             {"ts": iso(0), "score": 140, "rank": 8, "teams": 50, "by": "kim"}]
    acts = [write(50), write(40), write(30, act="reply_back"), write(20, act="second_voice"), write(10, act="reply_back"),
            write(90, act="reply_back")]                                    # the last one is before the window
    ctx, html = page(make_root(tmp_path, acts, score=score))
    assert build.WRITES["reply"] == "1st reply" and build.WRITES["reply_back"] == "2nd reply"
    assert ctx["history"][0]["replies"] == (2, 2) and ctx["history"][1]["replies"] is None
    assert "2 1st reply · 2 2nd reply" in rowof(ctx, "Writes, last hour")["now"]
    assert "1st / 2nd replies" not in html


def test_tab_title_is_a_status_word_not_a_colour(tmp_path):
    assert build.STATUS_WORD == {"green": "RUNNING", "amber": "ALERT", "red": "DOWN"}
    ctx, html = page(make_root(tmp_path, [write(3)]), service="inactive")
    assert ctx["worst"] == "red" and "<title>Swan · DOWN</title>" in html
    for worst, word in (("green", "RUNNING"), ("amber", "ALERT"), ("red", "DOWN")):
        assert f"<title>Swan · {word}</title>" in build.render(dict(ctx, worst=worst, status_word=build.STATUS_WORD[worst]))


def test_reply_time_stages_are_split_for_first_and_second_replies(tmp_path):
    base = NOW.timestamp()

    def timed(minutes_ago, act, made, pick, drafted, sent, **kw):
        a = write(minutes_ago, act=act)
        a.update(source="latest", t_made=base - made * 60, t_pick=base - pick * 60, t_drafted=base - drafted * 60,
                 t_sent=base - sent * 60, **kw)
        return a
    acts = [timed(10, "reply", 14, 12, 11, 10), timed(8, "reply", 12, 10, 9, 8),          # wait 2 / draft 1 / hold 1
            timed(6, "reply_back", 9, 8, 7, 6),                                           # wait 1 / draft 1 / hold 1
            write(5, act="reply_back"),                                                   # an old row: no stamps, not timed
            timed(4, "reply", 8, 6, 5, 6)]                                                # out of order: not timed
    ctx, html = page(make_root(tmp_path, acts))
    assert rowof(ctx, "Where the time goes, 1st replies")["now"] == "wait 2.0 · draft 1.0 · hold 1.0 = 4.0 min (n 2)"
    assert rowof(ctx, "Where the time goes, 2nd replies")["now"] == "wait 1.0 · draft 1.0 · hold 1.0 = 3.0 min (n 1)"
    ctx, _ = page(make_root(tmp_path / "x", [write(5)]))
    assert rowof(ctx, "Where the time goes, 1st replies")["now"] == "no timed writes yet"


def test_stage_times_logged_on_a_write():
    from swan_bot import bot
    got = bot.stage_times(dict(t_pick=100.04, t_drafted=102.0, drafted_ahead=True),
                          dict(created_at="2026-10-23T00:00:00Z"))
    assert got["t_made"] == 1792713600.0 and got["t_pick"] == 100.0 and got["t_drafted"] == 102.0
    assert got["t_sent"] > 1.7e9 and got["drafted_ahead"] is True
    none = bot.stage_times({}, None)
    assert none["t_made"] is None and none["t_pick"] is None and none["drafted_ahead"] is None


def test_stealth_bars_0_to_5_green_6_to_10_amber_11_up_red(tmp_path):
    for new, want in ((0, "green"), (5, "green"), (6, "amber"), (10, "amber"), (11, "red")):
        root = make_root(tmp_path / f"s{new}", [write(3)])
        log = {"counts": [{"ts": iso(1500), "registered": 50, "banned": 2}, {"ts": iso(30), "registered": 50, "banned": 2 + new}]}
        (root / "data" / "portal.json").write_text(json.dumps({"ts": iso(1), "account_log": log}))
        ctx, _ = page(root)
        assert rowof(ctx, "New bans")["light"] == want, new


# ---- drafting starved: no_model drops and the priced-model budget (23 Oct) ----
def lost(minutes_ago, why="no_model", act="lost"):
    return {"ts": iso(minutes_ago), "act": act, "why": why, "mode": "reply"}


def with_budget(root, left):
    """data/llm_spend.json so that `left` USD of today's allowance (22 Oct Sydney) remains."""
    from swan_bot import llm
    day = NOW.astimezone(llm.BUDGET_DAY).date().isoformat()
    (root / "data" / "llm_spend.json").write_text(json.dumps({day: llm.allowance(day, {}) - left}))
    return llm.day_share(day) * build.bot_config.LLM_AMP_RESERVE_SHARE      # the reserve


def drafting(tmp_path, actions, left=None):
    root = make_root(tmp_path, actions)
    reserve = with_budget(root, left) if left is not None else None
    ctx, html = page(root)
    return ctx, html, reserve


def test_drafting_green_and_quiet(tmp_path):
    ctx, html, reserve = drafting(tmp_path, [write(3), lost(45)], left=20)
    assert ctx["draft_banner"]["level"] == "green" and "Drafting" not in html


def test_drafting_amber_on_any_drops_in_30_min(tmp_path):
    ctx, html, _ = drafting(tmp_path, [write(1), write(2), write(3), lost(25), lost(20, "expired:no_model", "requeue")], left=20)
    b = ctx["draft_banner"]
    assert b["level"] == "amber" and "0 drops in 10 min, 2 in 30" in b["text"] and "0.3 writes/min" in b["text"] and "$20.00 left" in b["text"]
    assert "<b>Drafting</b> · Replies slowed: no model free" in html and "Free models are parked" in html
    assert "not the cause" in "".join(b["detail"])


def test_drafting_amber_when_paid_models_held_back_or_budget_low(tmp_path):
    reserve = with_budget(make_root(tmp_path / "r"), 0)
    ctx, _, _ = drafting(tmp_path / "a", [write(3)], left=0.5 * reserve)
    assert ctx["draft_banner"]["level"] == "amber" and "held back" in ctx["draft_banner"]["text"]
    ctx, _, _ = drafting(tmp_path / "b", [write(3)], left=1.5 * reserve)             # between 1x and 2x the reserve
    assert ctx["draft_banner"]["level"] == "amber" and "BUDGET LOW" in ctx["draft_banner"]["text"] and "held back" not in ctx["draft_banner"]["text"]


def test_drafting_red_on_drops_and_no_writes(tmp_path):
    ctx, html, _ = drafting(tmp_path, [lost(2)] * 400 + [lost(20)] + [write(15)], left=20)
    b = ctx["draft_banner"]
    assert b["level"] == "red" and "400 drops in 10 min, 401 in 30" in b["text"] and "0.0 writes/min" in b["text"]
    assert ctx["worst"] == "red" and ctx["status_word"] == "DOWN"


def test_drafting_drops_with_healthy_writes_stay_amber(tmp_path):
    ctx, _, _ = drafting(tmp_path, [lost(2)] + [write(m / 3) for m in range(1, 31)], left=20)
    assert ctx["draft_banner"]["level"] == "amber"


def test_drafting_red_when_budget_spent(tmp_path):
    ctx, _, _ = drafting(tmp_path, [write(3)], left=0)
    assert ctx["draft_banner"]["level"] == "red" and ctx["draft_banner"]["text"].startswith("BUDGET SPENT") and "budget spent" in ctx["draft_banner"]["text"]


def test_drafting_missing_files_degrade_quietly(tmp_path):
    root = make_root(tmp_path, [lost(2)])                           # no llm_spend.json
    ctx, _ = page(root)
    assert ctx["draft_banner"]["level"] == "red" and "left today" not in ctx["draft_banner"]["text"]
    (root / "logs" / "swan_actions.jsonl").unlink()
    ctx, _ = page(root)
    assert ctx["draft_banner"]["level"] == "green"


def test_each_light_tile_says_on_hover_what_its_colours_mean(tmp_path):
    ctx, html = page(make_root(tmp_path, [write(3)]))
    for i in ctx["reach"]["lights"]:
        assert i["tip"] and ("Needs a look:" in i["tip"] or "Nothing amber or red." in i["tip"]) and "title=" in html, i["key"]
    assert "Green: 0-5 · amber: 6-10 · red: 11 or more." in html


def test_speed_leaves_out_catch_up_from_a_stall(tmp_path):
    """Posts made while we barely posted, answered late, are a backlog (23 Oct). Busy minutes keep counting."""
    busy = [write(m, act="post") for m in range(200, 119, -1) for _ in range(2)]            # 2 a minute: not starved
    stall = [write(m, act="post") for m in range(119, 70, -10)]                              # one per 10 min: starved
    def timed(ago, wait_min, **kw):
        sent = NOW.timestamp() - ago * 60
        return dict(write(ago), act="reply", source="latest", t_made=sent - wait_min * 60, t_pick=sent - 30,
                    t_drafted=sent - 20, t_sent=sent, **kw)
    acts = busy + stall + [timed(30, 2), timed(25, 75), timed(20, 2)]                       # 75 min wait: made ~100 min ago, in the stall
    ctx, _ = page(make_root(tmp_path, acts))
    r = rowof(ctx, "Reply time, new")
    assert "1 catch-up left out" in r["now"] and r["now"].startswith("2.") and r["light"] == "green", r
    acts[-2] = timed(25, 140)                                                              # 140 min wait, made in a busy bucket: counts
    ctx, _ = page(make_root(tmp_path / "b", acts))
    assert "catch-up" not in rowof(ctx, "Reply time, new")["now"]


def test_new_post_reply_time_bars_3_green_5_amber_over_red(tmp_path):
    for wait, want in ((2.0, "green"), (3.0, "green"), (4.5, "amber"), (5.0, "amber"), (5.5, "red")):
        sent = NOW.timestamp() - 600
        a = dict(write(10), act="reply", source="latest", t_made=sent - wait * 60, t_pick=sent - 30,
                 t_drafted=sent - 10, t_sent=sent)
        ctx, _ = page(make_root(tmp_path / f"w{wait}", [a]))
        assert rowof(ctx, "Reply time, new")["light"] == want, wait


def test_hidden_posts_are_shown_but_never_colour_stealth(tmp_path):
    root = make_root(tmp_path, [write(3), dict(write(2), act="alert")])
    ctx, _ = page(root)
    assert rowof(ctx, "Posts hidden")["light"] == "green"
    st = next(i for i in ctx["reach"]["lights"] if i["key"] == "stealth")
    assert st["light"] == "green" and "Nothing amber or red." in st["tip"]


def test_hover_lists_the_amber_and_red_rows_with_their_note(tmp_path):
    root = make_root(tmp_path, [write(3)])
    (root / "data" / "reach_notes.json").write_text(json.dumps({"Posting": "bot restarted 15:20"}))
    ctx, _ = page(root)
    tip = next(i for i in ctx["reach"]["lights"] if i["key"] == "volume")["tip"]
    assert "Needs a look:" in tip and "Posting, last 30 min" in tip and "(in hand: bot restarted 15:20)" in tip
