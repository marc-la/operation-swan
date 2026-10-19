"""Text generation. Gemini (OpenAI-compatible endpoint, GEMINI_API_KEY) is the writer; models are tried in order.

Free-tier quotas are small and per model (gemini-3.8-flash: 20 requests/day on 2026-10-20), so a 429 that says
the daily quota is spent parks that model until the retry time, and a per-minute 429 parks it for a minute.
The provided qwen model is only used with allow_qwen=True: weak drafts cost account lives, so by default the bot
waits instead of posting worse text.
"""
import os
import re
import time

import openai
import capturethenarrative as ctn

from . import config

QWEN_GAP_S = 21          # 3 requests/min team-wide, one at a time
DEFAULT_MODELS = "gemini-3.5-flash,gemini-3.5-flash-lite"


def _retry_seconds(err):
    """Parse 'retry in 13h30m17.9s' / 'retryDelay': '41s' from a Gemini 429."""
    s = str(err)
    m = re.search(r"retry in (?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", s)
    if m and any(m.groups()):
        h, mi, se = (float(x) if x else 0.0 for x in m.groups())
        return h * 3600 + mi * 60 + se
    m = re.search(r"retryDelay['\"]?\s*:\s*['\"]?(\d+)s", s)
    return float(m.group(1)) if m else 60.0


class Generator:
    def __init__(self, team_code, allow_qwen=False):
        self.allow_qwen = allow_qwen
        self.qwen = ctn.CompetitorLLM(team_code=team_code, max_retries=2) if allow_qwen else None
        self.qwen_last = 0.0
        key = os.environ.get("GEMINI_API_KEY", "")
        self.gemini = openai.OpenAI(api_key=key, base_url=config.GEMINI_URL, max_retries=0, timeout=60) if key else None
        self.models = [m.strip() for m in os.environ.get("GEMINI_MODEL", DEFAULT_MODELS).split(",") if m.strip()]
        self.parked = {}                      # model -> time it may be tried again
        self.calls = {}                       # model -> successful calls this run (to learn the quotas)

    def describe(self):
        return "+".join(self.models) + ("+qwen" if self.allow_qwen else "") if self.gemini else ("qwen" if self.allow_qwen else "none")

    def complete(self, system, user, max_tokens=220):
        """Return (text, backend) or (None, None) when no model is available right now."""
        if self.gemini:
            for model in self.models:
                if time.time() < self.parked.get(model, 0):
                    continue
                try:
                    r = self.gemini.chat.completions.create(
                        model=model, max_tokens=4096, temperature=0.9,
                        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
                    self.calls[model] = self.calls.get(model, 0) + 1
                    return (r.choices[0].message.content or "").strip(), model
                except openai.RateLimitError as e:
                    wait = _retry_seconds(e)
                    daily = "per_day" in str(e).lower() or "free_tier_requests" in str(e) or wait > 600
                    self.parked[model] = time.time() + (wait if daily else max(wait, 60))
                    print(f"gemini {model}: {'daily quota spent' if daily else 'per-minute limit'}, "
                          f"parked {wait / 60:.0f} min (calls this run: {self.calls.get(model, 0)})")
                except openai.NotFoundError:
                    self.parked[model] = time.time() + 24 * 3600
                    print(f"gemini {model}: not available, skipped")
                except (openai.InternalServerError, openai.APITimeoutError, openai.APIConnectionError):
                    self.parked[model] = time.time() + 120
                except openai.APIError as e:
                    print("gemini error:", type(e).__name__, str(e)[:120])
                    self.parked[model] = time.time() + 300
        if not self.allow_qwen:
            return None, None
        wait = self.qwen_last + QWEN_GAP_S - time.time()
        if wait > 0:
            time.sleep(wait)
        self.qwen_last = time.time()
        r = self.qwen.chat.completions.create(
            model=ctn.competitorllm.MODEL, max_tokens=max_tokens, temperature=0.9,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        return (r.choices[0].message.content or "").strip(), "qwen"

    def next_available_in(self):
        """Seconds until some Gemini model may be tried again."""
        if not self.gemini or not self.models:
            return 3600
        return max(0.0, min(self.parked.get(m, 0) for m in self.models) - time.time())
