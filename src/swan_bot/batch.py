"""Batched drafting: one LLM call writes several drafts (posts, replies, second voices, journalist replies).

Why: the free Gemini tier caps requests per day, not words, so one request that returns 4-5 drafts stretches the
same key 3-5x further than one draft per request, without falling back to the weak qwen model.

How (standard batch-prompting practice):
- the shared rules (world, voice, limits) go once at the top; each item is self-contained and labelled A, B, C...
  (persona card, the facts that item may use, and the same task text the single-draft path uses);
- the model answers with JSON keyed by label; replies also restate the citizen's point in a few words, which we
  check against *that* citizen's post, so a reply that drifted onto another item's post is dropped;
- each item in a batch gets a different post shape / opening, and asking for several distinct drafts at once
  lets the model see what it already wrote, so they don't come out alike;
- every draft still passes quality.check on its own, plus a near-duplicate check against its batch-mates;
- if the JSON can't be parsed, the caller retries with a smaller batch.
"""
import json
import random
import re

from . import content

LABELS = "ABCDEFGH"

SHARED_RULES = (
    "You write social media posts for several different people who live in Kingstonia, a small Pacific island "
    "nation (beaches, ferries, Regatta Week, Saturday markets). Each item below names the person to write as and "
    "the task. Write every item fully in that person's own voice, as a different human being.\n"
    f"Kingstonia is holding a referendum on this question: \"{content.QUESTION}\" Every one of these people is voting "
    "No. They are not against vaccines; they are against the certificate rule. They are cheerful and reasonable, "
    "never angry. Money is Kingstonia dollars (K$). Never name a day or date for the vote or say how or where to vote.\n"
    "Each item lists the facts it may use (use at most one or two). Do not invent any other facts, numbers, studies, "
    "names or health claims. Put any fact in your own words, never in the wording given.\n"
    "Write like real locals on social media: first person, everyday words, British spelling, contractions. Be "
    "specific, not general: one concrete detail beats three abstract ones. No hashtags, emojis, links, @mentions, "
    "quotation marks, greetings or sign-offs. Never insult anyone, never mention Marina Castillo, the tourism board "
    "or resorts. Don't start with Exactly, Absolutely, Spot on, Too right, You're right, Great point, Well said, "
    "I hear you, I understand, Totally get or Fair point.\n"
    "The items must not sound alike: every item opens with different words and uses a different sentence pattern "
    "and length."
)

OUTPUT_RULES = (
    "Answer with JSON only, in exactly this form, one entry per item, in the same order:\n"
    '{"items": [{"id": "A", "their_point": "...", "text": "..."}, ...]}\n'
    "\"text\" is the finished post or reply, nothing else. For items that answer someone, \"their_point\" is what that "
    "person said, in 3 to 8 words; for new posts leave it empty."
)


def persona_card(persona, frame_key):
    facts = "; ".join(content.FACTS[f] for f in content.FRAMES[frame_key]["facts"])
    return (f"Write as {persona['name']}, who {persona['role']} in {persona['place']}. "
            f"About them: {'; '.join(persona['details'])}. Voice: {persona['voice']}. Facts this item may use: {facts}")


def task_text(job, headline=None, shape=None, opener=None):
    """The same task wording the single-draft path uses (content.*_prompt), with a fixed shape/opening."""
    target = job.get("target") or {}
    body = target.get("body") or ""
    mode = job["mode"]
    if mode == "post":
        return content.post_prompt(job["frame"], headline, shape=shape)
    if mode == "reply":
        return content.reply_prompt(body, job["frame"], job.get("wants"), job.get("context"), opener=opener)
    if mode == "second_voice":
        return content.second_voice_prompt(body, job["frame"], job.get("wants"), job.get("context"), opener=opener)
    if mode == "journalist":
        return content.journalist_prompt(target["author_id"], body)
    raise ValueError(f"mode {mode} is not batched")


def build_prompt(jobs, headline=None):
    """(system, user, labels) for one call covering `jobs` (each with mode, rec, frame, target...)."""
    shapes = random.sample(content.POST_SHAPES if headline else content.POST_SHAPES[:-1],
                           k=min(len(jobs), len(content.POST_SHAPES) - (0 if headline else 1)))
    openers = random.sample(content.OPENERS, k=min(len(jobs), len(content.OPENERS)))
    parts, labels = [], []
    for i, job in enumerate(jobs):
        label = LABELS[i]
        labels.append(label)
        persona = content.PERSONA_BY_KEY[job["rec"]["persona"]]
        task = task_text(job, headline, shape=shapes[i % len(shapes)], opener=openers[i % len(openers)])
        parts.append(f"=== Item {label} ({job['mode'].replace('_', ' ')}) ===\n{persona_card(persona, job['frame'])}\n"
                     f"Task: {task}")
    user = "\n\n".join(parts) + "\n\n" + OUTPUT_RULES
    return SHARED_RULES, user, labels


def parse_items(raw):
    """{label: (their_point, text)} from the model's answer; tolerant of code fences and stray prose. {} if unusable."""
    if not raw:
        return {}
    s = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    data = None
    for candidate in (s, s[s.find("{"):s.rfind("}") + 1], s[s.find("["):s.rfind("]") + 1]):
        try:
            data = json.loads(candidate)
            break
        except (json.JSONDecodeError, ValueError):
            continue
    if isinstance(data, dict):
        data = data.get("items")
    if not isinstance(data, list):
        return {}
    out = {}
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            out[str(item.get("id", "")).strip().upper()[:1]] = (str(item.get("their_point") or ""), item["text"])
    return out


_STOP = set("the a an and or but if so to of in on at for with is are was were be been it its this that these those "
            "they them their there we our you your i me my he she his her not no yes do does did have has had just "
            "about what when where which who how why would could should will can than then also very more most".split())


def _words(text):
    """Content-word stems (first 6 letters), so 'responsible' matches 'responsibility'."""
    return {w[:6] for w in re.findall(r"[a-z']+", (text or "").lower()) if len(w) > 3 and w not in _STOP}


def points_at(their_point, own_text, other_texts):
    """Mix-up guard: False only when the restated point clearly matches another item's post better than its own."""
    pw = _words(their_point)
    own = len(pw & _words(own_text))
    return all(len(pw & _words(o)) <= own for o in other_texts)
