"""The stand-in citizen and its rater (todo/25 Phase 1), on config.LAB_MODEL only: the organisers' qwen2.5-3b family.

Our best guess at the organisers' NPC: a persona card with the citizen's own words, "hard to persuade", "you read: ...",
"give your view after reading". The same model then rates one view at a time as a vote intention (YES .. NO, at
temperature 0): the stand-in's view with nothing new read (the baseline, once per card and seed) against its view after
reading our reply. The move is the difference. The control strategy (an unrelated post) measures what drift is left.

These prompts are the lab's only. Nothing from them goes into a live post (todo/25 rules).
"""
import os
import re
import threading
import time

import openai

import capturethenarrative as ctn
from swan_bot import config

QUESTION = ('Kingstonia votes on 2 November 2026 on this referendum question: should proof of H2D2 ("Dolphin Flu") '
            'vaccination be required to enter public places? Yes means require the proof. No means keep public places '
            'open to everyone.')


class Backend:
    """One stand-in model. "competitor": the organisers' qwen2.5-3b, at most config.LAB_LLM_PER_MIN a minute, slower
    when the headers say so, a 429 waits its Retry-After. "local": the same model family on our own endpoint
    (config.LAB_LOCAL_URL, e.g. Ollama behind an SSH tunnel), no rate limit. Both: one call at a time (the lab is one
    thread), backing off on errors, never a tight retry loop."""

    def __init__(self, name, model_id=None):
        self.name = name
        if name == "competitor":
            self.client = ctn.CompetitorLLM(team_code=config.team_code(), max_retries=0)
            self.model_id, self.gap, self.waits = ctn.competitorllm.MODEL, 60.0 / config.LAB_LLM_PER_MIN + 0.5, 30
        elif name == "local":
            self.client = openai.OpenAI(base_url=config.LAB_LOCAL_URL, api_key="local", max_retries=0, timeout=180)
            self.model_id, self.gap, self.waits = model_id or config.LAB_LOCAL_MODEL, 0.0, 5
            self.name = f"local:{self.model_id}"           # q4 and q8 trials are kept apart
        elif name == "remote":                             # the key is read from the environment, never logged
            url, key = os.environ.get("LAB_REMOTE_URL", ""), os.environ.get("LAB_REMOTE_KEY", "")
            if not url or not key:
                raise SystemExit("LAB_MODEL remote needs LAB_REMOTE_URL and LAB_REMOTE_KEY in .env")
            self.client = openai.OpenAI(base_url=url, api_key=key, max_retries=0, timeout=300)   # a cold start
            self.model_id, self.gap, self.waits = model_id or config.LAB_REMOTE_MODEL, 0.0, 15
            self.name = f"remote:{self.model_id}"
        else:
            raise SystemExit(f"unknown LAB_MODEL {name!r} (competitor, local or remote)")
        self.kind = name
        self.last = 0.0

    def ask(self, system, user, max_tokens, temperature, tries):
        for attempt in range(tries):
            time.sleep(max(0.0, self.last + self.gap - time.time()))
            self.last = time.time()
            try:
                raw = self.client.chat.completions.with_raw_response.create(
                    model=self.model_id, max_tokens=max_tokens, temperature=temperature,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
            except openai.RateLimitError as e:
                wait = _retry_after(getattr(e, "response", None)) or 60
                print(f"lab: {self.name} rate limited, waiting {wait:.0f} s")
                self.last = time.time() + wait - self.gap
                continue
            except (openai.APIConnectionError, openai.APITimeoutError, openai.InternalServerError) as e:
                wait = self.waits * (attempt + 1)
                print(f"lab: {self.name} error ({type(e).__name__}), waiting {wait} s")
                self.last = time.time() + wait - self.gap
                continue
            self._pace(raw.headers)
            return raw.parse().choices[0].message.content or ""
        raise RuntimeError(f"stand-in {self.name} unavailable")

    def _pace(self, headers):
        """A remaining count of 0 holds the next call until the window resets."""
        remaining = next((v for k, v in headers.items() if "ratelimit-remaining" in k.lower()), None)
        if remaining is not None and str(remaining).strip() == "0":
            reset = next((v for k, v in headers.items() if "ratelimit-reset" in k.lower()), None)
            try:
                self.last = time.time() + float(reset) - self.gap
            except (TypeError, ValueError):
                self.last = time.time() + 60 - self.gap


class Switched(RuntimeError):
    """The primary stand-in went down mid-trial: the trial is run again on the fallback (no mixed-model trials)."""


class StandIn:
    """config.LAB_MODEL, with "competitor" as the fallback for "local" (the laptop tunnel may be down; "remote" has
    none: 3/min can't stand in for its parallel trials). A whole trial runs on one model (stand_in.model is recorded on
    it); after a switch, the primary is tried again every RETRY_PRIMARY_S. Several trials may run at once (remote):
    calls are counted per thread."""
    RETRY_PRIMARY_S = 600

    def __init__(self, model=None, backend=Backend, local_model=None, fallback=True):
        name = model or config.LAB_MODEL
        self.primary = backend(name, local_model) if name in ("local", "remote") else backend(name)
        self.fallback = backend("competitor") if name == "local" and fallback else None
        self.active, self.down_at, self.calls = self.primary, 0.0, 0
        self._mine, self._lock = threading.local(), threading.Lock()

    @property
    def thread_calls(self):
        """Calls made by this thread so far (a trial's own count, when trials run in parallel)."""
        return getattr(self._mine, "n", 0)

    @property
    def model(self):
        return self.active.name

    def ask(self, system, user, max_tokens=220, temperature=0.7, tries=4):
        try:
            out = self.active.ask(system, user, max_tokens, temperature,
                                  tries if self.active.name == "competitor" else 2)
        except RuntimeError:
            if self.active is self.primary and self.fallback:
                self.active, self.down_at = self.fallback, time.time()
                print(f"lab: {self.primary.name} down, trials go to {self.fallback.name}")
                raise Switched(f"{self.primary.name} down") from None
            raise
        with self._lock:
            self.calls += 1
        self._mine.n = self.thread_calls + 1
        return out

    def restore(self):
        """Back to the primary when it answers again (checked at most every RETRY_PRIMARY_S)."""
        if self.active is not self.primary and time.time() - self.down_at > self.RETRY_PRIMARY_S:
            self.down_at = time.time()
            try:
                self.primary.ask("Answer with one word.", "Say ok.", 2, 0.0, 1)
            except RuntimeError:
                return
            self.active = self.primary
            print(f"lab: {self.primary.name} is back")

    def up(self):
        """One tiny call: True when the stand-in answers (used after an outage, before drafting more replies)."""
        try:
            self.ask("Answer with one word.", "Say ok.", max_tokens=2, temperature=0.0, tries=1)
            return True
        except RuntimeError:
            return False


def _retry_after(response):
    try:
        return float(response.headers.get("retry-after"))
    except (AttributeError, TypeError, ValueError):
        return None


def persona_prompt(card):
    lines = [f"You are {card['name']} (@{card['handle']}), a citizen of Kingstonia, a small island nation."]
    if card.get("bio"):
        lines.append(f"About you: {card['bio']}")
    if card.get("posts"):
        lines.append("Things you have posted recently, in your own words:")
        lines += [f"- {p[:280]}" for p in card["posts"][:8]]
    if card.get("liked"):
        lines.append("Posts you liked:")
        lines += [f"- {p[:200]}" for p in card["liked"][:3]]
    lines += [QUESTION, f'Your view on it right now, in your own words: "{card["view"][:400]}"',
              "You are hard to persuade. Hearing again what you already believe does not change your mind. You change "
              "your view only for a compelling, relevant argument from a credible source. A post can also make you "
              "more sure of what you thought, or push you the other way if it puts you off."]
    return "\n".join(lines)


def session_prompt(card, reads):
    return (f'You are scrolling Legit Social. Earlier you posted: "{card["target_text"][:400]}"\n\n{reads}\n\n'
            "Now write your view on the referendum question after reading, in your own words, in 1 to 3 sentences, "
            "as you would think it to yourself. Then, on a new line starting with \"Vaccination:\", write one sentence "
            "on your view of vaccination in general.")


NOTHING_NEW = "Nothing new about the referendum has come up in your feed today."


def reads_reply(name, handle, text, card_text=None):
    out = f'{name} (@{handle}) replied to your post:\n"{text}"'
    if card_text:
        out += f"\nThe reply links an article. Its preview card says: {card_text}"
    return out


def reads_post(name, handle, text):
    return f'You scroll past this post by {name} (@{handle}):\n"{text}"'


def session(npc, card, reads, seed):
    """(view after, vaccination sentence, raw) from one simulated session."""
    out = npc.ask(persona_prompt(card), session_prompt(card, reads), max_tokens=200, temperature=0.7)
    m = re.search(r"\n\s*\**vaccination\**\s*:\s*(.+)", out, re.I)
    view = out[:m.start()].strip() if m else out.strip()
    return view, (m.group(1).strip() if m else None), out


# The instrument (v2, 2026-10-22). v1 asked the classifier to compare BEFORE with AFTER and answer a letter; the 3B
# model answered "B" 5 times in 6 whatever B meant. Now one text at a time is rated as a vote intention on a word
# scale, at temperature 0, and the move is the difference: the same instrument on both sides, no letters.
INSTRUMENT = 2
LABELS = {"YES": -2, "LEAN YES": -1, "UNDECIDED": 0, "LEAN NO": 1, "NO": 2}
RATE_SYSTEM = ("You read what a citizen of Kingstonia wrote and judge how they will vote in the referendum. "
               "Answer with the label only.")
_LABEL = re.compile(r"\b(LEAN(?:ING)?\s+YES|LEAN(?:ING)?\s+NO|UNDECIDED|YES|NO)\b", re.I)


def rate_prompt(text):
    return (f"{QUESTION}\n\nWhat they wrote: \"{text[:600]}\"\n\nHow will they vote? Answer with exactly one of these "
            "labels: YES, LEAN YES, UNDECIDED, LEAN NO, NO")


def parse_rating(raw):
    """-2 (Yes) .. +2 (No) from the first label in the answer, or None."""
    m = _LABEL.search(raw or "")
    return None if not m else LABELS[re.sub(r"LEANING", "LEAN", re.sub(r"\s+", " ", m.group(1).upper()))]


def rate(npc, text):
    raw = npc.ask(RATE_SYSTEM, rate_prompt(text), max_tokens=6, temperature=0.0)
    return parse_rating(raw), raw


def verdict(before, after):
    """toward_no / toward_yes / same from two ratings (None when either is unreadable)."""
    if before is None or after is None:
        return None
    return "toward_no" if after > before else "toward_yes" if after < before else "same"


def baseline(npc, card):
    """The stand-in's own view with nothing new read, rated: the 'before' of every trial for this card and seed."""
    view, _, _ = session(npc, card, NOTHING_NEW, None)
    score, raw = rate(npc, view)
    return dict(view=view, score=score, raw=raw)
