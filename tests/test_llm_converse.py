"""Bedrock Converse provider (mocked HTTP, no network)."""
import json
import pathlib
import sys
import time

import httpx2 as httpx  # openai's HTTP library

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from swan_bot import llm  # noqa: E402

KEY = "test-secret-bedrock-key-123"
K3 = "global.moonshotai.kimi-k3"


def make_gen(tmp_path, monkeypatch, handler, chain=(("bedrock-converse", K3), ("groq", "free-model"))):
    monkeypatch.setenv("BEDROCK_API_KEY", KEY)
    monkeypatch.setenv("GROQ_API_KEY", "unused")
    monkeypatch.setenv("LLM_CHAIN", ",".join(f"{p}:{m}" for p, m in chain))
    monkeypatch.setenv("LLM_RPM", "6000")
    monkeypatch.setattr(llm, "USAGE_FILE", tmp_path / "usage.json")
    monkeypatch.setattr(llm, "SPEND_FILE", tmp_path / "spend.json")
    gen = llm.Generator("unused")
    gen.http = httpx.Client(transport=httpx.MockTransport(handler))
    return gen


def ok(content, stop="end_turn", usage=(120, 40)):
    return httpx.Response(200, json={"output": {"message": {"role": "assistant", "content": content}},
                                     "stopReason": stop,
                                     "usage": {"inputTokens": usage[0], "outputTokens": usage[1]}})


def test_chain_syntax_and_no_openai_client(tmp_path, monkeypatch):
    gen = make_gen(tmp_path, monkeypatch, lambda req: ok([{"text": "x"}]))
    assert gen.chain[0] == ("bedrock-converse", K3)
    assert "bedrock-converse" not in gen.clients and "groq" in gen.clients


def test_success_sends_converse_request(tmp_path, monkeypatch):
    seen = []

    def handler(req):
        seen.append(req)
        return ok([{"text": "  a draft  "}])
    gen = make_gen(tmp_path, monkeypatch, handler)
    assert gen.complete("sys", "usr", max_tokens=5, temperature=0.4) == ("a draft", K3)
    req = seen[0]
    assert req.method == "POST"
    assert str(req.url) == f"https://bedrock-runtime.ap-southeast-2.amazonaws.com/model/{K3}/converse"
    assert req.headers["authorization"] == f"Bearer {KEY}"
    body = json.loads(req.content)
    assert body["system"] == [{"text": "sys"}]
    assert body["messages"] == [{"role": "user", "content": [{"text": "usr"}]}]
    assert body["inferenceConfig"] == {"maxTokens": llm.CONVERSE_MIN_TOKENS, "temperature": 0.4}, "K3 needs >= 16"
    assert gen.last_finish == "stop" and gen.calls == {K3: 1}
    assert list(json.loads((tmp_path / "usage.json").read_text()).values()) == [{K3: 1}]


def test_reasoning_block_before_the_text(tmp_path, monkeypatch):
    content = [{"reasoningContent": {"reasoningText": {"text": "let me think...", "signature": "abc"}}},
               {"text": '{"A": "the answer"}'}]
    gen = make_gen(tmp_path, monkeypatch, lambda req: ok(content))
    assert gen.complete("s", "u", json_mode=True) == ('{"A": "the answer"}', K3)


def test_usage_is_charged_for_a_priced_model(tmp_path, monkeypatch):
    monkeypatch.setitem(llm.config.LLM_PRICES, K3, (1.0, 2.0))
    monkeypatch.setattr(llm.config, "LLM_BUDGET_DAYS", [("2000-01-01", "2100-01-01", 1)])
    gen = make_gen(tmp_path, monkeypatch, lambda req: ok([{"text": "x"}], usage=(1_000_000, 500_000)))
    assert gen.complete("s", "u", priority=True) == ("x", K3)
    assert abs(sum(gen.spent().values()) - 2.0) < 1e-9


def test_cut_off_at_the_cap_is_asked_again_uncapped(tmp_path, monkeypatch):
    sent = []

    def handler(req):
        cap = json.loads(req.content)["inferenceConfig"]["maxTokens"]
        sent.append(cap)
        return ok([{"text": ""}], stop="max_tokens") if cap == 600 else ok([{"text": "full"}])
    gen = make_gen(tmp_path, monkeypatch, handler)
    assert gen.complete("s", "u", max_tokens=600) == ("full", K3)
    assert sent == [600, 4096] and K3 in gen.no_cap


def test_daily_quota_parks_until_utc_midnight(tmp_path, monkeypatch, capsys):
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(429, json={"message": "Too many tokens per day, please wait before trying again."})
    gen = make_gen(tmp_path, monkeypatch, handler, chain=(("bedrock-converse", K3),))
    assert gen.complete("s", "u") == (None, None)
    left = gen.parked[K3] - time.time()
    assert gen.park_why[K3] == "daily quota" and abs(left - llm._to_utc_midnight()) < 5
    assert gen.complete("s", "u") == (None, None) and len(calls) == 1, "parked: not asked again"
    assert "daily quota" in capsys.readouterr().out


def test_daily_quota_falls_through_to_the_next_model(tmp_path, monkeypatch):
    gen = make_gen(tmp_path, monkeypatch,
                   lambda req: httpx.Response(429, json={"message": "Too many tokens per day, please wait."}))
    real = gen._call
    gen._call = lambda prov, model, *a, **kw: "free" if prov == "groq" else real(prov, model, *a, **kw)
    assert gen.complete("s", "u") == ("free", "free-model")


def test_not_available_disables_it_for_the_day(tmp_path, monkeypatch):
    msg = "Invocation of model ID global.anthropic.claude-sonnet-4-6 is not available for this account."
    gen = make_gen(tmp_path, monkeypatch, lambda req: httpx.Response(400, json={"message": msg}),
                   chain=(("bedrock-converse", "global.anthropic.claude-sonnet-4-6"),))
    assert gen.complete("s", "u") == (None, None)
    m = "global.anthropic.claude-sonnet-4-6"
    assert gen.park_why[m] == "not available" and gen.parked[m] - time.time() > llm._to_utc_midnight() - 5


def test_per_minute_throttle_and_server_errors_park_briefly(tmp_path, monkeypatch):
    for status, message, why, secs in [(429, "Too many requests, please wait before trying again.", "per-minute limit", 60),
                                       (503, "Service unavailable", "InternalServerError", 120),
                                       (400, "maxTokens must be at least 16", "bad request", 300)]:
        gen = make_gen(tmp_path, monkeypatch, lambda req: httpx.Response(status, json={"message": message}),
                       chain=(("bedrock-converse", K3),))
        assert gen.complete("s", "u") == (None, None)
        assert gen.park_why[K3] == why and abs(gen.parked[K3] - time.time() - secs) < 5


def test_timeout_parks_and_never_leaks_the_key(tmp_path, monkeypatch, capsys):
    def handler(req):
        raise httpx.ReadTimeout("timed out", request=req)
    gen = make_gen(tmp_path, monkeypatch, handler, chain=(("bedrock-converse", K3),))
    assert gen.complete("s", "u") == (None, None) and gen.park_why[K3] == "APITimeoutError"
    assert KEY not in capsys.readouterr().out


def test_secrets_never_in_logs_or_exceptions(tmp_path, monkeypatch, capsys):
    """Even an error body that echoes the key (it shouldn't) is redacted in the exception and the printed line."""
    def handler(req):
        return httpx.Response(403, json={"message": f"The security token {KEY} included in the request is invalid."})
    gen = make_gen(tmp_path, monkeypatch, handler, chain=(("bedrock-converse", K3),))
    try:
        gen._converse("bedrock-converse", K3, "s", "u", False)
        raise AssertionError("should raise")
    except llm.Unavailable as e:
        assert KEY not in str(e) and KEY not in repr(e) and e.why == "key not valid"
        assert e.__cause__ is None and e.__context__ is None
    assert gen.complete("s", "u") == (None, None)
    out = capsys.readouterr()
    assert KEY not in out.out and KEY not in out.err and "***" in out.out
    assert KEY not in json.dumps(gen.status())
