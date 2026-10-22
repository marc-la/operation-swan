"""The stand-in citizen and its classifier (todo/25 Phase 1), on config.LAB_MODEL only: the organisers' qwen2.5-3b.

Our best guess at the organisers' NPC: a persona card with the citizen's own words, "hard to persuade", "you read: ...",
"give your view after reading". The classifier then compares the card's view (their own words) with the view after
reading: toward Yes / toward No / the same. Its three answers get letters in a per-trial shuffled order, so a small
model's letter bias averages out; the control strategy (an unrelated post) measures what drift is left.

These prompts are the lab's only. Nothing from them goes into a live post (todo/25 rules).
"""
import random
import re
import time

import openai

import capturethenarrative as ctn
from swan_bot import config

QUESTION = ('Kingstonia votes on 2 November 2026 on this referendum question: should proof of H2D2 ("Dolphin Flu") '
            'vaccination be required to enter public places? Yes means require the proof. No means keep public places '
            'open to everyone.')
VERDICTS = {"toward_yes": "closer to YES: more for requiring the proof, or less against it",
            "toward_no": "closer to NO: more against requiring the proof, or less for it",
            "same": "the same position, maybe in other words"}


class Backend:
    """One stand-in model. "competitor": the organisers' qwen2.5-3b, at most config.LAB_LLM_PER_MIN a minute, slower
    when the headers say so, a 429 waits its Retry-After. "local": the same model family on our own endpoint
    (config.LAB_LOCAL_URL, e.g. Ollama behind an SSH tunnel), no rate limit. Both: one call at a time (the lab is one
    thread), backing off on errors, never a tight retry loop."""

    def __init__(self, name):
        self.name = name
        if name == "competitor":
            self.client = ctn.CompetitorLLM(team_code=config.team_code(), max_retries=0)
            self.model_id, self.gap, self.waits = ctn.competitorllm.MODEL, 60.0 / config.LAB_LLM_PER_MIN + 0.5, 30
        elif name == "local":
            self.client = openai.OpenAI(base_url=config.LAB_LOCAL_URL, api_key="local", max_retries=0, timeout=180)
            self.model_id, self.gap, self.waits = config.LAB_LOCAL_MODEL, 0.0, 5
        else:
            raise SystemExit(f"unknown LAB_MODEL {name!r} (competitor or local)")
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
    """config.LAB_MODEL, with "competitor" as the fallback for "local" (the tunnel may be down). A whole trial runs on
    one model (stand_in.model is recorded on it); after a switch, the primary is tried again every RETRY_PRIMARY_S."""
    RETRY_PRIMARY_S = 600

    def __init__(self, model=None, backend=Backend):
        name = model or config.LAB_MODEL
        self.primary = backend(name)
        self.fallback = backend("competitor") if name != "competitor" else None
        self.active, self.down_at, self.calls = self.primary, 0.0, 0

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
        self.calls += 1
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


def reads_reply(name, handle, text, card_text=None):
    out = f'{name} (@{handle}) replied to your post:\n"{text}"'
    if card_text:
        out += f"\nThe reply links an article. Its preview card says: {card_text}"
    return out


def reads_post(name, handle, text):
    return f'You scroll past this post by {name} (@{handle}):\n"{text}"'


def session(npc, card, reads, seed):
    """(view after, vaccination sentence) from one simulated session."""
    out = npc.ask(persona_prompt(card), session_prompt(card, reads), max_tokens=200, temperature=0.7)
    m = re.search(r"\n\s*\**vaccination\**\s*:\s*(.+)", out, re.I)
    view = out[:m.start()].strip() if m else out.strip()
    return view, (m.group(1).strip() if m else None), out


def letters(seed, card_id):
    """{letter: verdict} in a per-trial shuffled order."""
    keys = list(VERDICTS)
    random.Random(f"{card_id}:{seed}:letters").shuffle(keys)
    return dict(zip("ABC", keys))


def classify_prompt(before, after, order):
    opts = "\n".join(f"{k} = {VERDICTS[v]}" for k, v in order.items())
    return (f"{QUESTION}\n\nA citizen's view BEFORE: \"{before[:500]}\"\nThe same citizen's view AFTER: \"{after[:500]}\"\n\n"
            f"Compared with BEFORE, the AFTER view is:\n{opts}\n\n"
            "Then say how the AFTER view treats vaccination itself: P = positive about vaccines, N = negative, "
            "M = mixed or not stated.\nAnswer in exactly this form and nothing else:\nVIEW: <A, B or C>\nVACCINE: <P, N or M>")


def parse_verdict(raw, order):
    """(verdict, vaccine) from the classifier's answer; None where it can't be read."""
    v = re.search(r"VIEW\W*([ABC])\b", raw or "", re.I) or re.match(r"\W*([ABC])\b", raw or "")
    x = re.search(r"VACCINE\W*([PNM])\b", raw or "", re.I)
    return (order.get(v.group(1).upper()) if v else None,
            {"P": "positive", "N": "negative", "M": "mixed"}.get(x.group(1).upper()) if x else None)


def classify(npc, card, after, seed):
    order = letters(seed, card["id"])
    raw = npc.ask("You compare two statements carefully and answer in the exact form asked.",
                  classify_prompt(card["view"], after, order), max_tokens=20, temperature=0.0)
    verdict, vaccine = parse_verdict(raw, order)
    return verdict, vaccine, raw
