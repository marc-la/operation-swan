"""Text generation through a chain of external models, tried in order (OpenAI-compatible endpoints, plus Bedrock's
Converse API for the models Bedrock serves only there).

The chain (best first) comes from LLM_CHAIN in .env if set, else deploy/llm_chain.txt (committed: edit and push to
re-rank), else Gemini, Groq, OpenRouter defaults. Lines whose provider has no key in .env are skipped.
One account per provider, each used on its own terms.
Free tiers cap requests per model per day, so a 429 that says the daily quota is spent parks that model until the
retry time, a per-minute 429 parks it for a minute, and the next model in the chain is tried. Every model's calls
are counted per day in data/llm_usage.json so we learn the real quotas.
Paid models (config.LLM_PRICES) are charged per call from the tokens the API reports, into data/llm_spend.json by
Sydney day. When today's allowance (llm.allowance: the budget shared out by the Red multiplier, unspent days carried
forward) is spent, they are parked until Sydney midnight and the free models carry on.
The provided qwen 3B model is only used with allow_qwen=True (off in production: too weak, too slow).
"""
import datetime as dt
import json
import os
import re
import threading
import time
import types
import urllib.parse
from zoneinfo import ZoneInfo

import httpx2 as httpx           # openai's own HTTP library (the box has no plain httpx or requests)
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
    # Model Studio, international (Singapore) endpoint: the only region our key works on. New accounts get ~1M free
    # tokens per model for 90 days, then pay-as-you-go unless "stop when free quota is used up" is on (2026-10-21)
    "alibaba": dict(key="ALIBABA_API_KEY", url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
                    models="ALIBABA_MODEL", default=""),
    # Bedrock (Sydney), billed to the AWS free-plan credits on the EC2 account. Claude is us-east-1 only and refuses
    # /chat/completions, so it isn't reachable here (2026-10-21)
    "bedrock": dict(key="BEDROCK_API_KEY", url="https://bedrock-mantle.ap-southeast-2.api.aws/v1",
                    models="BEDROCK_MODEL", default=""),
    # Bedrock's own Converse API (same key, Bearer auth) for the models bedrock-mantle doesn't serve: Kimi K3, and
    # Claude once AWS lifts our daily token limit (2026-10-22). Model ids take the inference-profile prefix
    # (global. / au.), e.g. bedrock-converse:global.moonshotai.kimi-k3 in deploy/llm_chain.txt
    "bedrock-converse": dict(key="BEDROCK_API_KEY", url="https://bedrock-runtime.ap-southeast-2.amazonaws.com",
                             models="BEDROCK_CONVERSE_MODEL", default="", converse=True),
}
CONVERSE_MIN_TOKENS = 16     # Kimi K3 refuses a smaller maxTokens
CHAIN_FILE = config.ROOT / "deploy" / "llm_chain.txt"
USAGE_FILE = config.DATA / "llm_usage.json"
QUOTA_DAY = ZoneInfo("America/Los_Angeles")      # Gemini and Groq daily quotas reset at midnight Pacific
SPEND_FILE = config.DATA / "llm_spend.json"
BUDGET_DAY = ZoneInfo(config.LOCAL_TZ)           # competition days roll over at midnight Sydney


def budget_days():
    """[(ISO day, weight)] from config.LLM_BUDGET_DAYS."""
    out = []
    for start, end, weight in config.LLM_BUDGET_DAYS:
        d, last = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
        while d <= last:
            out.append((d.isoformat(), weight))
            d += dt.timedelta(days=1)
    return out


def allowance(day, spent):
    """USD the priced models may still spend on Sydney day `day`: the budget's share up to and including that day,
    minus everything spent so far ({day: usd}, today included). Unspent days carry forward; never past the budget."""
    days = budget_days()
    total = sum(w for _, w in days) or 1
    share = config.LLM_BUDGET_USD * sum(w for d, w in days if d <= day) / total
    return max(0.0, min(share, config.LLM_BUDGET_USD) - sum(v for d, v in spent.items() if d <= day))


def day_share(day):
    """The budget's share for one Sydney day before carry-over (the priority reserve is a part of it)."""
    days = budget_days()
    return config.LLM_BUDGET_USD * sum(w for d, w in days if d == day) / (sum(w for _, w in days) or 1)


def cost(model, prompt_tokens, completion_tokens):
    p_in, p_out = config.LLM_PRICES[model]
    return (prompt_tokens * p_in + completion_tokens * p_out) / 1e6


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


class Unavailable(Exception):
    """A model that can't answer now (Converse errors, which aren't openai exceptions): park it `seconds`."""

    def __init__(self, why, seconds, detail=""):
        super().__init__(f"{why}: {detail}" if detail else why)
        self.why, self.seconds, self.detail = why, seconds, detail


def _to_utc_midnight():
    now = dt.datetime.now(dt.timezone.utc)
    return ((now + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0) - now).total_seconds()


def _converse_error(status, message):
    """Unavailable for a Converse error ({"message": ...}). Bedrock's daily token quota resets at 00:00 UTC."""
    s = message.lower()
    if "per day" in s:                                  # "Too many tokens per day, please wait before trying again."
        return Unavailable("daily quota", _to_utc_midnight(), message)
    if "not available" in s or status == 404:           # "... is not available for this account": try again tomorrow
        return Unavailable("not available", _to_utc_midnight(), message)
    if status == 429 or "too many" in s:
        return Unavailable("per-minute limit", 60, message)
    if status in (401, 403):
        return Unavailable("key not valid", 3600, message)
    if status >= 500:
        return Unavailable("InternalServerError", 120, message)
    return Unavailable("bad request", 300, message)


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
                        for prov in {p for p, _ in self.chain} if not PROVIDERS[prov].get("converse")}
        self.http = None                      # httpx client for the Converse providers, made on first use
        self.parked = {}                      # model -> time it may be tried again
        self.park_why = {}                    # model -> why it is parked (shown on the dashboard)
        self.on_park = None                   # callback(model, until, why): the bot logs parks
        self.no_json_mode = set()             # models that refused response_format
        self.no_schema = set()                # models that refused a JSON schema (json_object still works)
        self.no_reasoning = set()             # models that refused reasoning_effort
        self.no_cap = set()                   # reasoning models that spend max_tokens on thinking (empty answers)
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

    def complete(self, system, user, max_tokens=None, json_mode=False, models=None, schema=None, reasoning=None,
                 temperature=0.9, priority=False):
        """Return (text, model) or (None, None) when no model is available right now.

        json_mode asks for a JSON object (batches), schema for that exact shape where the model supports it;
        reasoning sets reasoning_effort (e.g. "low"); models restricts the chain (for comparisons).
        max_tokens caps the answer (None: 4096, 8192 in JSON mode); a cut-off answer sets last_finish "length".
        priority (amplified posts) may spend the reserve, config.LLM_AMP_RESERVE_SHARE of today's share; other calls
        skip the paid models once only the reserve is left."""
        for prov, model in self.chain:
            if models and model not in models:
                continue
            if time.time() < self.parked.get(model, 0):
                continue
            if model in config.LLM_PRICES:
                left = self.budget_left()
                if left <= 0:
                    now = dt.datetime.now(BUDGET_DAY)
                    midnight = (now + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                    self._park(model, (midnight - now).total_seconds(), "daily budget")
                    print(f"{prov} {model}: today's LLM budget is spent; parked to Sydney midnight")
                    continue
                today = dt.datetime.now(BUDGET_DAY).date().isoformat()
                if not priority and left <= config.LLM_AMP_RESERVE_SHARE * day_share(today):
                    continue                                 # the rest of today is kept for amplified posts
            try:
                return self._call(prov, model, system, user, json_mode, schema, reasoning, max_tokens,
                                  temperature), model
            except Unavailable as e:
                self._park(model, e.seconds, e.why)
                print(f"{prov} {model}: {e.why}, parked {e.seconds / 60:.0f} min:", e.detail[:160])
            except openai.RateLimitError as e:
                wait = _retry_seconds(e)
                daily = _is_daily(e, wait)
                self._park(model, wait if daily else max(wait, 60), "daily quota" if daily else "per-minute limit")
                print(f"{prov} {model}: {'daily quota spent' if daily else 'per-minute limit'}, "
                      f"parked {wait / 60:.0f} min (calls this run: {self.calls.get(model, 0)})")
            except openai.BadRequestError as e:
                print(f"{prov} {model}: bad request:", str(e)[:160])
                self._park(model, 300, "bad request")
            except openai.AuthenticationError:
                self._park(model, 3600, "key not valid")
                print(f"{prov} {model}: API key not valid (check {PROVIDERS[prov]['key']} in .env); parked 1 h")
            except openai.NotFoundError:
                self._park(model, 24 * 3600, "not available")
                print(f"{prov} {model}: not available, skipped")
            except (openai.InternalServerError, openai.APITimeoutError, openai.APIConnectionError) as e:
                self._park(model, 120, type(e).__name__)    # printed: silent parks hid a night on the fallbacks
                print(f"{prov} {model}: {type(e).__name__}, parked 2 min (calls this run: {self.calls.get(model, 0)})")
            except openai.APIError as e:
                print(f"{prov} {model} error:", type(e).__name__, str(e)[:120])
                self._park(model, 300, type(e).__name__)
        if not self.allow_qwen or models:
            return None, None
        wait = self.qwen_last + QWEN_GAP_S - time.time()
        if wait > 0:
            time.sleep(wait)
        self.qwen_last = time.time()
        r = self.qwen.chat.completions.create(
            model=ctn.competitorllm.MODEL, max_tokens=max_tokens or 220, temperature=temperature,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        return (r.choices[0].message.content or "").strip(), "qwen"

    def spent(self):
        """{Sydney day: USD} charged to the priced models (data/llm_spend.json)."""
        try:
            return json.loads(SPEND_FILE.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def budget_left(self):
        return allowance(dt.datetime.now(BUDGET_DAY).date().isoformat(), self.spent())

    def _charge(self, model, usage, system, user, text):
        """Add one call's cost to today's spend. Without a usage block, ~4 characters a token (input + answer)."""
        if model not in config.LLM_PRICES:
            return
        p = getattr(usage, "prompt_tokens", None)
        c = getattr(usage, "completion_tokens", None)        # includes the thinking tokens of a reasoning model
        if p is None or c is None:
            p, c = (len(system) + len(user)) / 4, len(text) / 4 + 1000      # unknown thinking: assume 1,000
        day = dt.datetime.now(BUDGET_DAY).date().isoformat()
        with self._lock:
            spent = self.spent()
            spent[day] = round(spent.get(day, 0.0) + cost(model, p, c), 6)
            try:
                config.DATA.mkdir(exist_ok=True)
                SPEND_FILE.write_text(json.dumps(spent, indent=1))
            except OSError:
                pass

    def _park(self, model, seconds, why):
        self.parked[model] = time.time() + seconds
        self.park_why[model] = why
        if self.on_park:
            self.on_park(model, self.parked[model], why)

    def status(self):
        """The chain in order, with each model's park time and reason (for data/status.json; no keys)."""
        now = time.time()
        return [dict(model=m, parked_until=self.parked[m] if self.parked.get(m, 0) > now else None,
                     why=self.park_why.get(m) if self.parked.get(m, 0) > now else None) for _, m in self.chain]

    def _pace(self, model):
        """Space requests to one model at least min_gap apart (a dry run would otherwise burst past the cap)."""
        with self._lock:
            wait = self.last_call.get(model, 0) + self.min_gap - time.time()
            self.last_call[model] = time.time() + max(0.0, wait)
        if wait > 0:
            time.sleep(wait)

    def _call(self, prov, model, system, user, json_mode, schema=None, reasoning=None, max_tokens=None,
              temperature=0.9):
        if PROVIDERS[prov].get("converse"):
            return self._converse(prov, model, system, user, json_mode, max_tokens, temperature)
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        cap = max_tokens if model not in self.no_cap else None
        kw = dict(model=model, max_tokens=cap or (8192 if json_mode else 4096), temperature=temperature,
                  messages=msgs)
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
                    return self._call(prov, model, system, user, json_mode, schema, None, max_tokens, temperature)
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
            text = (r.choices[0].message.content or "").strip()
            self._charge(model, getattr(r, "usage", None), system, user, text)
            if cap and r.choices[0].finish_reason == "length":
                # a thinking model spends max_tokens on thinking: at 600, gpt-oss-120b answered "" 96 times on 20-21
                # Oct and gemini-3.6-flash stopped mid-sentence ("...if she'd need papers to get on")
                self.no_cap.add(model)
                print(f"{prov} {model}: cut off at max_tokens={cap} (thinking); asking again without the cap")
                return self._call(prov, model, system, user, json_mode, schema, reasoning, None, temperature)
            return text

    def _converse(self, prov, model, system, user, json_mode, max_tokens=None, temperature=0.9):
        """One Bedrock Converse call (no JSON mode or schema there: the prompts spell out the JSON and it's parsed
        as plain text, as for no_json_mode models). Errors raise Unavailable; the key never goes into a message."""
        key = os.environ[PROVIDERS[prov]["key"]]
        cap = max_tokens if model not in self.no_cap else None
        body = {"system": [{"text": system}], "messages": [{"role": "user", "content": [{"text": user}]}],
                "inferenceConfig": {"maxTokens": max(CONVERSE_MIN_TOKENS, cap or (8192 if json_mode else 4096)),
                                    "temperature": temperature}}
        url = f"{PROVIDERS[prov]['url']}/model/{urllib.parse.quote(model, safe='')}/converse"
        if getattr(self, "http", None) is None:
            self.http = httpx.Client(timeout=90)
        self._pace(model)
        try:
            r = self.http.post(url, json=body, headers={"Authorization": f"Bearer {key}"})
        except httpx.TimeoutException:
            raise Unavailable("APITimeoutError", 120) from None
        except httpx.HTTPError as e:
            raise Unavailable("APIConnectionError", 120, type(e).__name__) from None
        try:
            data = r.json()
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        if r.status_code != 200:
            msg = str(data.get("message") or data.get("Message") or f"HTTP {r.status_code}").replace(key, "***")
            raise _converse_error(r.status_code, msg)
        try:
            content = data["output"]["message"]["content"]
        except (KeyError, TypeError):
            raise Unavailable("bad response", 300, str(list(data))[:120]) from None
        # a reasoning model (Kimi K3) may put reasoningContent blocks before the answer: keep only the text blocks
        text = "".join(b["text"] for b in content if isinstance(b, dict) and isinstance(b.get("text"), str)).strip()
        self._count(model)
        stop = data.get("stopReason")
        self._local.finish = "length" if stop == "max_tokens" else "stop" if stop in ("end_turn", "stop_sequence") else stop
        u = data.get("usage") or {}
        self._charge(model, types.SimpleNamespace(prompt_tokens=u.get("inputTokens"),
                                                  completion_tokens=u.get("outputTokens")), system, user, text)
        if cap and stop == "max_tokens":
            self.no_cap.add(model)             # spent the cap thinking, as with the OpenAI-compatible models
            print(f"{prov} {model}: cut off at max_tokens={cap} (thinking); asking again without the cap")
            return self._converse(prov, model, system, user, json_mode, None, temperature)
        return text

    @property
    def last_finish(self):
        """finish_reason of this thread's last answer ("length" = cut off)."""
        return getattr(self._local, "finish", None)

    def next_available_in(self):
        """Seconds until some model in the chain may be tried again."""
        if not self.chain:
            return 3600
        return max(0.0, min(self.parked.get(m, 0) for _, m in self.chain) - time.time())
