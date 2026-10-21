"""LLM spend cap, model tiering, reply-backs in amplified threads, Trending-thread targets (no network)."""
import datetime as dt
import json
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from swan_bot import bot, config, llm  # noqa: E402

KIMI = "moonshotai.kimi-k2.5"


def test_allowance_follows_the_multiplier_and_carries_forward():
    days = llm.budget_days()
    assert days[0] == ("2026-10-21", 1) and days[-1] == ("2026-11-02", 4) and len(days) == 13
    unit = config.LLM_BUDGET_USD / sum(w for _, w in days)
    assert abs(llm.allowance("2026-10-21", {}) - unit) < 1e-9
    spent = {d: unit for d, _ in days if d <= "2026-10-25"}           # every x1 day spent its share
    assert abs(llm.allowance("2026-10-26", spent) - 2 * unit) < 1e-9
    assert abs(llm.allowance("2026-10-26", {}) - 7 * unit) < 1e-9, "unspent days carry forward"
    assert abs(llm.allowance("2026-11-02", {}) - config.LLM_BUDGET_USD) < 1e-9
    assert llm.allowance("2026-10-22", {"2026-10-21": 50.0}) == 0.0, "an overspend comes out of later days"
    assert llm.allowance("2026-10-20", {}) == 0.0


def make_gen(tmp_path, monkeypatch, spent=None):
    monkeypatch.setattr(llm, "SPEND_FILE", tmp_path / "spend.json")
    monkeypatch.setattr(llm, "USAGE_FILE", tmp_path / "usage.json")
    if spent is not None:
        (tmp_path / "spend.json").write_text(json.dumps(spent))
    gen = llm.Generator("unused")
    gen.chain = [("bedrock", KIMI), ("groq", "free-model")]

    def fake_call(prov, model, system, user, *a, **kw):
        gen._charge(model, types.SimpleNamespace(prompt_tokens=1_000_000, completion_tokens=0), system, user, "x")
        return f"from {model}"
    gen._call = fake_call
    return gen


def today():
    return dt.datetime.now(llm.BUDGET_DAY).date().isoformat()


def test_charge_and_park_when_today_is_spent(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LLM_BUDGET_DAYS", [(today(), today(), 1)])
    monkeypatch.setattr(config, "LLM_BUDGET_USD", 0.5)          # one 1M-token call ($0.75) spends it
    gen = make_gen(tmp_path, monkeypatch)
    assert gen.complete("s", "u") == (f"from {KIMI}", KIMI)
    assert abs(gen.spent()[today()] - config.LLM_PRICES[KIMI][0]) < 1e-9, "1M input tokens at the input price"
    assert gen.budget_left() == 0.0
    assert gen.complete("s", "u") == ("from free-model", "free-model"), "the paid model is parked, the free one runs"
    assert gen.park_why[KIMI] == "daily budget"
    gen.parked.clear()
    assert gen.complete("s", "u")[1] == "free-model"


def test_charge_without_usage_estimates(tmp_path, monkeypatch):
    gen = make_gen(tmp_path, monkeypatch)
    gen._charge(KIMI, None, "s" * 4000, "", "a" * 400)
    p_in, p_out = config.LLM_PRICES[KIMI]
    assert abs(gen.spent()[today()] - (1000 * p_in + 1100 * p_out) / 1e6) < 1e-9
    gen._charge("free-model", None, "s", "u", "t")
    assert len(gen.spent()) == 1


class StubGen:
    chain = [("gemini", "gemini-3.5-flash-lite"), ("bedrock", KIMI), ("groq", "openai/gpt-oss-120b")]

    def __init__(self):
        self.models = []

    def complete(self, system, user, models=None, **kw):
        self.models.append(models)
        return "draft", "m"


def models_for(job, monkeypatch):
    monkeypatch.setattr(bot.quality, "check", lambda raw, *a, **kw: (raw, None))
    gen = StubGen()
    bot.draft_checked(gen, dict(job, meta={}), "sys", "user", [])
    return gen.models[0]


def test_tiering(monkeypatch):
    assert models_for(dict(mode="post", amp=True), monkeypatch) == config.AMP_MODELS
    assert models_for(dict(mode="reply"), monkeypatch) == config.AMP_MODELS
    assert models_for(dict(mode="reply_back"), monkeypatch) == config.AMP_MODELS
    assert models_for(dict(mode="thread"), monkeypatch) == ["gemini-3.5-flash-lite", "openai/gpt-oss-120b"]
    assert models_for(dict(mode="post"), monkeypatch) is None


def test_reply_backs_only_in_amplified_threads():
    posts = {1: dict(post_id=1, author_id=500, reply_to_post_id=900, root_post_id=900, body="theirs, in our thread"),
             2: dict(post_id=2, author_id=501, reply_to_post_id=950, root_post_id=950, body="theirs, elsewhere"),
             900: dict(post_id=900, body="our amplified post"), 950: dict(post_id=950, body="our plain reply")}
    resolved = []

    class Acc:
        def notifications(self, unresolved, limit):
            return [dict(kind="reply", post=dict(post_id=1), notification_id=11),
                    dict(kind="reply", post=dict(post_id=2), notification_id=12)]

        def resolve_notification(self, nid):
            resolved.append(nid)

    accounts = types.SimpleNamespace(voices=lambda: [dict(username="v0")], session=lambda rec: Acc())
    social = types.SimpleNamespace(get_post=lambda pid: posts[pid])
    targeter = types.SimpleNamespace(is_citizen=lambda aid: True)
    jobs = bot.reply_back_jobs(social, accounts, targeter, roots={900})
    assert [j["target"]["post_id"] for j in jobs] == [1]
    assert resolved == [11, 12], "skipped notifications are resolved too"
    assert len(bot.reply_back_jobs(social, accounts, targeter, roots=None)) == 2


def test_trending_thread_targets_rank_above_news():
    from swan_bot import targeting
    t = targeting.Targeter(None, log=lambda r: None)
    t.is_citizen = lambda aid: True
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    body = "leaning yes on the referendum but only if there's an end date"
    t._consider(dict(post_id=1, author_id=100, body=body, created_at=now), "news")
    t._consider(dict(post_id=2, author_id=101, body=body, created_at=now), "thread")
    if t.candidates:                                   # the body has to classify into a frame for either to count
        assert t.candidates[2]["score"] > t.candidates[1]["score"]


def test_reserve_keeps_the_paid_models_for_amplified_posts(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LLM_BUDGET_DAYS", [(today(), today(), 1)])
    monkeypatch.setattr(config, "LLM_BUDGET_USD", 4.0)
    monkeypatch.setattr(config, "LLM_AMP_RESERVE_SHARE", 0.25)               # $1 kept for amplified posts
    gen = make_gen(tmp_path, monkeypatch, spent={today(): 3.2})
    assert gen.complete("s", "u")[1] == "free-model", "an ordinary draft drops to the free model"
    assert KIMI not in gen.parked, "...without parking the paid one"
    assert gen.complete("s", "u", priority=True)[1] == KIMI


def test_priority_window_holds_other_writes():
    import time
    from swan_bot import amplify
    from test_amplify import make_accounts
    amp = amplify.Amplifier(None, make_accounts(), {}, live=False, log=lambda r: None)
    assert not amp.priority_window()
    amp.on_post(None, amp.accounts.records[0], "our post", "F1_blank_cheque", "heavy")
    assert amp.priority_window()
    for m in amp.state["amp_posts"].values():
        m["t"] = time.time() - config.AMP_PRIORITY_S - 1
    assert not amp.priority_window(), "after the window, other writes go again"
