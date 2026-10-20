"""Text generation through a chain of external models, tried in order (all OpenAI-compatible endpoints).

The chain (best first) comes from LLM_CHAIN in .env if set, else deploy/llm_chain.txt (committed: edit and push to
re-rank), else Gemini, Groq, OpenRouter defaults. Lines whose provider has no key in .env are skipped.
One account per provider, each used on its own terms.
Free tiers cap requests per model per day, so a 429 that says the daily quota is spent parks that model until the
retry time, a per-minute 429 parks it for a minute, and the next model in the chain is tried. Every model's calls
are counted per day in data/llm_usage.json so we learn the real quotas.
The provided qwen 3B model is only used with allow_qwen=True (off in production: too weak, too slow).
"""
import datetime as dt
import json
import os
import re
import threading
import time
from zoneinfo import ZoneInfo

import openai
import capturethenarrative as ctn

from . import config

QWEN_GAP_S = 21          # 3 requests/min team-wide, one at a time
DEFAULT_RPM = 10         # our own per-model cap (LLM_RPM in .env overrides); Gemini's free tier allows 15/min
PROVIDERS = {
    "gemini": dict(key="GEMINI_API_KEY", url=config.GEMINI_URL, models="GEMINI_MODEL",
                   default="gemini-3.5-flash,gemini-3.5-flash-lite"),
    "groq": dict(key="GROQ_API_KEY", url="https://api.groq.com/openai/v1", models="GROQ_MODEL",
                 default="openai/gpt-oss-120b,qwen/qwen3.8-27b"),
    # free tier with no credit: ~50 requests/day across all :free models (1,000/day once $10 of credit is bought)
    "openrouter": dict(key="OPENROUTER_API_KEY", url="https://openrouter.ai/api/v1", models="OPENROUTER_MODEL",
                       default="google/gemma-4-31b-it:free"),
    # more OpenAI-compatible providers: add the key to .env and a line to deploy/llm_chain.txt
    "openai": dict(key="OPENAI_API_KEY", url="https://api.openai.com/v1", models="OPENAI_MODEL", default=""),
    "anthropic": dict(key="ANTHROPIC_API_KEY", url="https://api.anthropic.com/v1/", models="ANTHROPIC_MODEL", default=""),
    "xai": dict(key="XAI_API_KEY", url="https://api.x.ai/v1", models="XAI_MODEL", default=""),
    "deepseek": dict(key="DEEPSEEK_API_KEY", url="https://api.deepseek.com/v1", models="DEEPSEEK_MODEL", default=""),
    "mistral": dict(key="MISTRAL_API_KEY", url="https://api.mistral.ai/v1", models="MISTRAL_MODEL", default=""),
    "cerebras": dict(key="CEREBRAS_API_KEY", url="https://api.cerebras.ai/v1", models="CEREBRAS_MODEL", default=""),
}
CHAIN_FILE = config.ROOT / "deploy" / "llm_chain.txt"
USAGE_FILE = config.DATA / "llm_usage.json"
QUOTA_DAY = ZoneInfo("America/Los_Angeles")      # Gemini and Groq daily quotas reset at midnight Pacific


def _retry_seconds(err):
    """Parse 'retry in 13h30m17.9s' (Gemini) / 'try again in 1m26.4s' (Groq) / 'retryDelay': '41s'."""
    s = str(err)
    m = re.search(r"(?:retry|try again) in (?:(\d+)h)?(?:(\d+)m(?!s))?(?:([\d.]+)s)?", s)
    if m and any(m.groups()):
        h, mi, se = (float(x) if x else 0.0 for x in m.groups())
        return h * 3600 + mi * 60 + se
    m = re.search(r"retryDelay['\"]?\s*:\s*['\"]?(\d+)s", s)
    return float(m.group(1)) if m else 60.0


def _is_daily(err, wait):
    s = str(err).lower()
    return wait > 600 or any(k in s for k in ("per_day", "per day", "perday", "free_tier_requests", "(rpd)", "(tpd)"))


def chain_from_env():
    """[(provider, model)] in the order to try them. Providers without a key are skipped."""
    spec = os.environ.get("LLM_CHAIN", "").strip()
    if not spec and CHAIN_FILE.exists():
        spec = ",".join(l.split("#")[0].strip() for l in CHAIN_FILE.read_text().splitlines() if l.split("#")[0].strip())
    if spec:
        pairs = [tuple(x.strip().split(":", 1)) for x in spec.split(",") if ":" in x]
    else:
        pairs = [(name, m.strip()) for name, p in PROVIDERS.items()
                 for m in os.environ.get(p["models"], p["default"]).split(",") if m.strip()]
    return [(prov, model) for prov, model in pairs if prov in PROVIDERS and os.environ.get(PROVIDERS[prov]["key"])]


class Generator:
    def __init__(self, team_code, allow_qwen=False):
        self.allow_qwen = allow_qwen
        self.qwen = ctn.CompetitorLLM(team_code=team_code, max_retries=2) if allow_qwen else None
        self.qwen_last = 0.0
        self.chain = chain_from_env()
        self.clients = {prov: openai.OpenAI(api_key=os.environ[PROVIDERS[prov]["key"]], base_url=PROVIDERS[prov]["url"],
                                            max_retries=0, timeout=90)
                        for prov in {p for p, _ in self.chain}}
        self.parked = {}                      # model -> time it may be tried again
        self.no_json_mode = set()             # models that refused response_format
        self.no_schema = set()                # models that refused a JSON schema (json_object still works)
        self.no_reasoning = set()             # models that refused reasoning_effort
        self.calls = {}                       # model -> successful calls this run
        self._lock = threading.Lock()         # scripts may call from several threads
        self._local = threading.local()
        self.min_gap = 60.0 / max(0.1, float(os.environ.get("LLM_RPM") or DEFAULT_RPM))
        self.last_call = {}                   # model -> time of the last request sent (pacing, not just 429s)

    def describe(self):
        names = [m for _, m in self.chain] + (["qwen"] if self.allow_qwen else [])
        return "+".join(names) or "none"

    def _count(self, model):
        with self._lock:
            self._count_locked(model)

    def _count_locked(self, model):
        self.calls[model] = self.calls.get(model, 0) + 1
        day = dt.datetime.now(QUOTA_DAY).date().isoformat()
        try:
            usage = json.loads(USAGE_FILE.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            usage = {}
        usage.setdefault(day, {})[model] = usage.get(day, {}).get(model, 0) + 1
        usage = {d: v for d, v in usage.items() if d >= (dt.date.fromisoformat(day) - dt.timedelta(days=14)).isoformat()}
        try:
            config.DATA.mkdir(exist_ok=True)
            USAGE_FILE.write_text(json.dumps(usage, indent=1))
        except OSError:
            pass

    def complete(self, system, user, max_tokens=220, json_mode=False, models=None, schema=None, reasoning=None):
        """Return (text, model) or (None, None) when no model is available right now.

        json_mode asks for a JSON object (batches), schema for that exact shape where the model supports it;
        reasoning sets reasoning_effort (e.g. "low"); models restricts the chain (for comparisons)."""
        for prov, model in self.chain:
            if models and model not in models:
                continue
            if time.time() < self.parked.get(model, 0):
                continue
            try:
                return self._call(prov, model, system, user, json_mode, schema, reasoning), model
            except openai.RateLimitError as e:
                wait = _retry_seconds(e)
                daily = _is_daily(e, wait)
                self.parked[model] = time.time() + (wait if daily else max(wait, 60))
                print(f"{prov} {model}: {'daily quota spent' if daily else 'per-minute limit'}, "
                      f"parked {wait / 60:.0f} min (calls this run: {self.calls.get(model, 0)})")
            except openai.BadRequestError as e:
                print(f"{prov} {model}: bad request:", str(e)[:160])
                self.parked[model] = time.time() + 300
            except openai.AuthenticationError:
                self.parked[model] = time.time() + 3600
                print(f"{prov} {model}: API key not valid (check {PROVIDERS[prov]['key']} in .env); parked 1 h")
            except openai.NotFoundError:
                self.parked[model] = time.time() + 24 * 3600
                print(f"{prov} {model}: not available, skipped")
            except (openai.InternalServerError, openai.APITimeoutError, openai.APIConnectionError):
                self.parked[model] = time.time() + 120
            except openai.APIError as e:
                print(f"{prov} {model} error:", type(e).__name__, str(e)[:120])
                self.parked[model] = time.time() + 300
        if not self.allow_qwen or models:
            return None, None
        wait = self.qwen_last + QWEN_GAP_S - time.time()
        if wait > 0:
            time.sleep(wait)
        self.qwen_last = time.time()
        r = self.qwen.chat.completions.create(
            model=ctn.competitorllm.MODEL, max_tokens=max_tokens, temperature=0.9,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        return (r.choices[0].message.content or "").strip(), "qwen"

    def _pace(self, model):
        """Space requests to one model at least min_gap apart (a dry run would otherwise burst past the cap)."""
        with self._lock:
            wait = self.last_call.get(model, 0) + self.min_gap - time.time()
            self.last_call[model] = time.time() + max(0.0, wait)
        if wait > 0:
            time.sleep(wait)

    def _call(self, prov, model, system, user, json_mode, schema=None, reasoning=None):
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        kw = dict(model=model, max_tokens=8192 if json_mode else 4096, temperature=0.9, messages=msgs)
        if reasoning and model not in self.no_reasoning:
            kw["reasoning_effort"] = reasoning
        formats = []
        if json_mode and schema and model not in self.no_schema:
            formats.append({"type": "json_schema", "json_schema": {"name": "drafts", "schema": schema}})
        if json_mode and model not in self.no_json_mode:
            formats.append({"type": "json_object"})
        for fmt in formats + [None]:
            self._pace(model)
            try:
                r = self.clients[prov].chat.completions.create(**({"response_format": fmt} if fmt else {}), **kw)
            except openai.BadRequestError as e:
                msg = str(e).lower()
                if "reasoning" in msg and "reasoning_effort" in kw:
                    self.no_reasoning.add(model)
                    kw.pop("reasoning_effort")
                    print(f"{prov} {model}: no reasoning_effort {reasoning!r}; using its default")
                    return self._call(prov, model, system, user, json_mode, schema, None)
                if fmt is None or ("json" not in msg and "schema" not in msg and "response_format" not in msg):
                    raise
                if fmt["type"] == "json_schema":          # cache the refusal, as with JSON mode
                    self.no_schema.add(model)
                    print(f"{prov} {model}: no JSON schema; using JSON mode")
                else:
                    self.no_json_mode.add(model)          # this model refuses JSON mode: ask again in plain text
                    print(f"{prov} {model}: no JSON mode; parsing plain text")
                continue
            self._count(model)
            self._local.finish = r.choices[0].finish_reason
            return (r.choices[0].message.content or "").strip()

    @property
    def last_finish(self):
        """finish_reason of this thread's last answer ("length" = cut off)."""
        return getattr(self._local, "finish", None)

    def next_available_in(self):
        """Seconds until some model in the chain may be tried again."""
        if not self.chain:
            return 3600
        return max(0.0, min(self.parked.get(m, 0) for _, m in self.chain) - time.time())
