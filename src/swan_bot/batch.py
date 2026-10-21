"""Batched drafting: one LLM call writes several drafts of the same kind (posts, replies or second voices).

A separate step from prompting: content.py says *what* to write; this module packs several jobs into one call,
unpacks the answer and checks each item. The bot turns it on with --batch N; with it off, nothing here runs.

    pack(jobs)            -> Pack: one system prompt per mode (static, so the provider can cache it), one user
                             prompt with an item per job (only that job's variables), a JSON schema
    Generator.complete    -> raw JSON
    unpack(raw, pack)     -> {label: (their_point, text)}, keeping every complete item even if the answer was cut off
    Drafter.draft(jobs)   -> one result per job: the clean text, or why it was rejected

What the literature and our own A/B say (docs/04-technical/llm-batching.md):
- one kind of task per call, 3-6 items: quality holds (Cheng et al. 2023; Son et al. 2024); bigger or mixed
  batches lose quality, so the Drafter never mixes modes and caps the size at MAX_SIZE;
- position bias (Lin et al. 2024): items are shuffled before labelling, and each draft logs its position;
- items must not blend into one voice: each item restates the citizen's point (checked against *that* post, so a
  reply that drifted onto another item's post is dropped) and a draft that borrows another item's persona is dropped;
- asking for several distinct drafts at once makes them *more* varied, not less (Zhang et al. 2025), as long as
  each item gets its own shape, opening and angle;
- every draft still passes quality.check on its own, against recent texts plus the drafts already accepted
  from this batch; if the JSON can't be parsed at all, the batch is retried once as two halves.
"""
import itertools
import json
import random
import re
import time
from dataclasses import dataclass, field

from . import content, quality

LABELS = "ABCDEFGH"
MAX_SIZE = 6
MODES = ("post", "reply", "second_voice")      # journalist and reply-back replies are rare: single path

SHARED_RULES = (
    "You write social media posts for several different people who live in Kingstonia, a small Pacific island "
    "nation (beaches, ferries, Regatta Week, Saturday markets). Each item below names the person to write as. "
    "For each item, become that person: write in the first person, with the care you'd give it if it were the only "
    "thing you wrote today, fully in their own voice, as a different human being: never give one person another "
    "item's name, job, place, details or voice (a voice note such as 'lowercase is fine' applies to that item only).\n"
    f"Kingstonia is holding a referendum on this question: \"{content.QUESTION}\" Every one of these people is voting "
    "No and is sure of it: each states their point plainly, without hedging or sitting on the fence. They are not "
    "against vaccines; they are against the certificate rule. They are cheerful and reasonable, never angry. "
    "Money is Kingstonia dollars (K$). Never name a day or date for the vote or say how or where to vote.\n"
    "Each item lists the facts it may use (use at most one or two). Do not invent any other facts, numbers, studies, "
    "names or health claims. Put any fact in your own words, never in the wording given.\n"
    "Write like real locals on social media: first person, everyday words, British spelling, contractions. Be "
    "specific, not general: one concrete detail beats three abstract ones. No hashtags, emojis, links, @mentions, "
    "quotation marks, greetings or sign-offs (apostrophes in I'm, don't, it's are fine and expected). Never insult anyone, never mention Marina Castillo, the tourism board "
    "or resorts. Don't start with Exactly, Absolutely, Spot on, Too right, You're right, Great point, Well said, "
    "I hear you, I understand, Totally get or Fair point.\n"
    "The items must not sound alike: every item opens with different words and uses a different sentence pattern "
    "and length."
)

# The per-mode task, said once per call instead of once per item. Same limits as content.*_prompt.
MODE_RULES = {
    "post": (
        "Every item is one new post of 3 to 4 sentences, between 250 and 420 characters: use the room, aim for about "
        "350 to 410. Build it the way the item's shape says. Make the item's point in your own words, mention a real "
        "local detail from that person's own life, and say in so many words that you're voting No. You may end with "
        "a short question to neighbours who haven't decided, but you don't have to."
    ),
    "reply": (
        "Every item is a reply to a neighbour who hasn't fully decided, in 2 or 3 short sentences, between 120 and "
        "260 characters: aim for about 190 to 240. Open the way the item says, then make the item's point and land "
        "it: finish on what it means for their vote, or with a pointed question about their point. If the item names "
        "the thing they raised, use their terms. Use the person's own life only where it bears on the point; never "
        f"open with a scene that has nothing to do with it. {content.REPLY_RULES}"
    ),
    "second_voice": (
        "Someone else has already replied to each neighbour below. Every item adds a different angle, as that "
        "person, in 1 or 2 short sentences, between 90 and 220 characters: aim for about 140 to 200. Open the way "
        "the item says, and land the point. Use the person's own life only where it bears on the point. Don't "
        f"mention the other reply. {content.REPLY_RULES}"
    ),
}

OUTPUT_RULES = (
    "Answer with JSON only, one entry per item:\n"
    '{"items": [{"id": "A", "their_point": "...", "text": "..."}, ...]}\n'
    "\"their_point\" is what the neighbour said, in 3 to 8 words (for new posts: the point you are making, in 3 to "
    "8 words). \"text\" is the finished post or reply, nothing else, punctuated as the person would write it: capital "
    "letters and apostrophes (I'm, don't, isn't) included; JSON strings can hold apostrophes as they are."
)


def persona_card(persona, frame_key):
    facts = "; ".join(content.FACTS[f] for f in content.fact_store.active(content.FRAMES[frame_key]["facts"]))
    details = [d for d in persona["details"] if not content.fact_store.paused_in(d)]
    return (f"Write as {persona['name']}, who {persona['role']} in {persona['place']}. "
            f"About them: {'; '.join(details)}. Voice: {persona['voice']}.\nFacts this item may use: {facts}")


def item_text(job, shape=None, opener=None, headline=None):
    """Only what differs between items: who writes, about what, and how to open."""
    angle = content.FRAMES[job["frame"]]["angle"]
    theme = f"\n{content.theme_line(job['theme'])}" if job.get("theme") else ""     # themes.Ledger.pick (bot.py)
    if job["mode"] == "post":
        return (f"Shape: {shape.format(headline=headline)}\nPoint to make, in your own words (never these words): "
                f"{angle}.{theme}")
    target = job.get("target") or {}
    body = (target.get("body") or "")[:600]
    ctx = f"Posted under this news item: <<<{job['context'][:200]}>>>\n" if job.get("context") else ""
    wants = job.get("wants")
    if job["mode"] == "reply":
        asks = f"The specific thing they raised: {', '.join(wants)}.\n" if wants else ""
        reb = content.rebuttal_for(body)          # their reason first, whatever the frame (content.reply_prompt)
        reb = f"Note: {reb}\n" if reb else ""
    else:
        asks = f"What they care about: {', '.join(wants)}.\n" if wants else ""
        reb = ""
    return (f"{ctx}The neighbour wrote:\n<<<{body}>>>\n{asks}{reb}{content.exempt_note(body)}"
            f"Opening: {opener}\nPoint to make, in your own words (never these words): {angle}."
            + (theme if job["mode"] == "reply" else ""))


@dataclass
class Pack:
    mode: str
    jobs: list                  # in label order (shuffled)
    labels: list
    system: str
    user: str
    items: dict                 # label -> that item's prompt text (for the copied-prompt check)
    schema: dict
    batch_id: str = field(default_factory=lambda: f"b{int(time.time())}{random.randint(100, 999)}")


def schema_for(labels):
    item = {"type": "object", "properties": {"id": {"type": "string", "enum": list(labels)},
                                             "their_point": {"type": "string"}, "text": {"type": "string"}},
            "required": ["id", "their_point", "text"]}
    return {"type": "object", "required": ["items"],
            "properties": {"items": {"type": "array", "items": item,
                                     "minItems": len(labels), "maxItems": len(labels)}}}


def pack(jobs, headline=None, rng=random):
    """One call's prompts for `jobs` (all the same mode, at most MAX_SIZE)."""
    modes = {j["mode"] for j in jobs}
    if len(modes) != 1 or not modes <= set(MODES):
        raise ValueError(f"a batch is one of {MODES}, got {modes}")
    if not 1 <= len(jobs) <= MAX_SIZE:
        raise ValueError(f"batch size {len(jobs)} outside 1..{MAX_SIZE}")
    mode = modes.pop()
    jobs = rng.sample(jobs, k=len(jobs))                  # position bias: no job is always first
    shapes = content.POST_SHAPES[:-1]
    shapes = rng.sample(shapes, k=len(shapes))
    if headline and rng.random() < 0.3:                   # same odds as the single path; one item at most
        shapes[0] = content.POST_SHAPES[-1]
    openers = rng.sample(content.OPENERS, k=len(content.OPENERS))
    labels, items, parts = [], {}, []
    for i, job in enumerate(jobs):
        label = LABELS[i]
        labels.append(label)
        persona = content.PERSONA_BY_KEY[job["rec"]["persona"]]
        job["frame"] = content.live_frame(job["frame"], persona)      # a paused fact may have taken its frame
        items[label] = item_text(job, shape=shapes[i % len(shapes)], opener=openers[i % len(openers)],
                                 headline=headline)
        parts.append(f"=== Item {label} ===\n{persona_card(persona, job['frame'])}\n{items[label]}")
    system = f"{content.world()}\n\n{SHARED_RULES}\n\n{MODE_RULES[mode]}\n\n{OUTPUT_RULES}"
    user = "\n\n".join(parts) + f"\n\nWrite all {len(jobs)} items ({', '.join(labels)}) as JSON."
    return Pack(mode, jobs, labels, system, user, items, schema_for(labels))


def unpack(raw, labels):
    """{label: (their_point, text)}: every complete item, even from cut-off or slightly broken JSON."""
    out = {}
    if not raw:
        return out
    s = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M)
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{\s*\"(?:id|their_point|text)\"", s):
        try:
            obj, _ = dec.raw_decode(s, m.start())
        except json.JSONDecodeError:
            continue                                       # the cut-off last item, or a broken one
        label = str(obj.get("id", "")).strip().upper()[:1]
        if isinstance(obj.get("text"), str) and label in labels and label not in out:
            out[label] = (str(obj.get("their_point") or ""), obj["text"])
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


def _persona_words(p):
    return _words(" ".join([p["role"], p["place"]] + p["details"]))


# words only one persona has (wharf cafe, tuna, sailing club...): a draft that uses two of another item's is borrowing
# it. Words from the shared world text (facts, angles, rules) and everyday words don't count.
_ALL_WORDS = {p["key"]: _persona_words(p) for p in content.PERSONAS}
_COMMON = _words(" ".join([f["text"] for f in content.fact_store.TABLE.values()]
                          + [f["angle"] for f in content.FRAMES.values()]
                          + content.OPENERS + content.POST_SHAPES + [SHARED_RULES] + list(MODE_RULES.values()))) | \
    _words("both early half small last before same once come past near left short mostly soon after asked gets "
           "living sees heading morning turns looks second line care jobs shops staff voted serves trade crowd "
           "first doses herself checking papers")
DISTINCT = {k: w - _COMMON - set().union(*(o for kk, o in _ALL_WORDS.items() if kk != k))
            for k, w in _ALL_WORDS.items()}


# contractions that lost their apostrophe ("im", "dont"): JSON output makes some models drop them
LOST_APOSTROPHE = re.compile(r"\b(im|ive|dont|doesnt|didnt|isnt|wasnt|arent|cant|couldnt|wouldnt|shouldnt|youre|"
                             r"theyre|thats|theres|whats|hasnt|havent)\b", re.I)


def bleeds(text, own_key, other_keys, target_text=""):
    """True if the draft names another item's persona or uses two of that persona's own details."""
    words = _words(text) - _words(target_text)
    for k in other_keys:
        if k == own_key:
            continue
        names = content.PERSONA_BY_KEY[k]["name"].split()             # whole words, case-sensitive: not "truth"
        if any(re.search(rf"\b{re.escape(n)}\b", text or "") for n in names) or len(words & DISTINCT[k]) >= 2:
            return True
    return False


class Drafter:
    """Drafts a list of same-mode jobs in calls of up to `size` items. Off unless the bot is run with --batch."""

    def __init__(self, gen, size=4, reasoning=None, log=None):
        self.gen, self.size, self.reasoning = gen, max(2, min(size, MAX_SIZE)), reasoning
        self.log = log or (lambda rec: None)

    def draft(self, jobs, recent_texts=(), headline=None, models=None, rng=random):
        """One result dict per job: job, text (None if rejected), why, raw, their_point, batch_id/pos/size, backend.

        Returns None if no model is available. Jobs of different modes are drafted in separate calls."""
        results = []
        recent = list(recent_texts)
        for mode, group in itertools.groupby(sorted(jobs, key=lambda j: MODES.index(j["mode"])), key=lambda j: j["mode"]):
            group = list(group)
            for i in range(0, len(group), self.size):
                got = self._call(group[i:i + self.size], recent, headline, models, rng, split=True)
                if got is None:
                    return None
                results += got
                recent += [r["text"] for r in got if r["text"]]
        return results

    def _call(self, jobs, recent, headline, models, rng, split):
        p = pack(jobs, headline, rng)
        raw, backend = self.gen.complete(p.system, p.user, json_mode=True, schema=p.schema, models=models,
                                         reasoning=self.reasoning)
        if raw is None:
            return None
        got = unpack(raw, p.labels)
        finish = getattr(self.gen, "last_finish", None)
        if not got and split and len(jobs) > 1:          # nothing usable: once, as two halves
            self.log({"act": "batch_unparsed", "batch_id": p.batch_id, "size": len(jobs), "backend": backend,
                      "finish": finish, "raw": raw[:500]})
            half = len(jobs) // 2
            a = self._call(jobs[:half], recent, headline, models, rng, split=False)
            b = self._call(jobs[half:], recent + [r["text"] for r in a or [] if r["text"]], headline, models, rng,
                           split=False)
            return None if a is None or b is None else a + b
        others = {lab: (j.get("target") or {}).get("body") or "" for lab, j in zip(p.labels, p.jobs)}
        keys = [j["rec"]["persona"] for j in p.jobs]
        accepted, results = [], []
        for pos, (label, job) in enumerate(zip(p.labels, p.jobs)):
            point, raw_text = got.get(label, ("", ""))
            body = others[label]
            if not raw_text:
                text, why = None, "missing_item"
            else:
                text, why = quality.check(raw_text, p.mode, recent + accepted, prompt_text=p.items[label],
                                          target_text=body, wants=job.get("wants") or ())
            if text and body and not points_at(point, body, [o for lab, o in others.items() if lab != label and o]):
                text, why = None, "mixup"
            if text and bleeds(text, job["rec"]["persona"], keys, body):
                text, why = None, "persona_bleed"
            if text and LOST_APOSTROPHE.search(text):
                text, why = None, "lost_apostrophe"
            if text:
                accepted.append(text)
            results.append(dict(job=job, text=text, why=why, raw=raw_text, their_point=point, backend=backend,
                                batch_id=p.batch_id, batch_pos=pos, batch_size=len(p.jobs), finish=finish))
        return results


POOL_TTL_S = {"reply": 20 * 60, "second_voice": 30 * 60, "post": 3 * 3600}


class Desk:
    """The bot's side of batching: a pool of checked drafts, each bound to a persona's account, sent when that
    account may next write. Replies older than 20 min are dropped (the citizen has moved on)."""

    def __init__(self, drafter, ready, log=None):
        self.drafter, self.ready = drafter, ready         # ready(rec, t) -> may this account write now
        self.log = log or (lambda rec: None)
        self.pool = []
        self.rejected = {}

    @property
    def size(self):
        return self.drafter.size

    def busy(self, mode, picked=()):
        """Personas already holding a pooled draft of this mode (one each), plus those picked for the next batch."""
        return {d["job"]["rec"]["persona"] for d in self.pool if d["job"]["mode"] == mode} | \
            {j["rec"]["persona"] for j in picked}

    def pending_targets(self):
        return {d["job"]["target"]["post_id"] for d in self.pool if d["job"].get("target")}

    def texts(self):
        return [d["text"] for d in self.pool]

    def take(self, mode, t, gone=lambda job: False):
        """A pooled draft of this mode whose account may write now, or None. Drops stale drafts, those whose
        target was answered meanwhile (gone(job) True) and those drafted before a fact was paused."""
        keep = []
        content.fact_store.refresh()
        for d in self.pool:
            j = d["job"]
            paused = d["drafted_at"] < content.fact_store.changed_at
            if (t - d["drafted_at"] > POOL_TTL_S[j["mode"]] or j["rec"].get("status", "active") != "active" or gone(j)
                    or paused):
                self.log({"act": "pool_drop", "mode": j["mode"], "persona": j["rec"]["persona"],
                          "batch_id": d["batch_id"], "age_s": round(t - d["drafted_at"]),
                          **({"why": "fact_paused"} if paused else {})})
                continue
            keep.append(d)
        self.pool = keep
        for d in self.pool:
            if d["job"]["mode"] == mode and self.ready(d["job"]["rec"], t):
                self.pool.remove(d)
                return d
        return None

    def fill(self, jobs, recent_texts, headline=None):
        """Draft `jobs` (one mode) in one call into the pool. Returns the rejected results (logged here), or None
        when no model is available."""
        results = self.drafter.draft(jobs, list(recent_texts) + self.texts(), headline=headline)
        if results is None:
            return None
        rejected = []
        for r in results:
            j = r["job"]
            j.setdefault("draft_id", f"{random.getrandbits(32):08x}")   # the write logs it too (bot.py)
            fields = {k: r[k] for k in ("batch_id", "batch_pos", "batch_size", "backend")}
            if r["text"]:
                self.pool.append(dict(job=j, text=r["text"], drafted_at=time.time(), **fields))
                continue
            rejected.append(r)
            self.rejected[r["why"]] = self.rejected.get(r["why"], 0) + 1
            self.log({"act": "reject", "why": r["why"], "mode": j["mode"], "persona": j["rec"]["persona"],
                      "frame": j["frame"], "raw": r["raw"], "their_point": r["their_point"], "finish": r["finish"],
                      "draft_id": j["draft_id"], "target_post": (j.get("target") or {}).get("post_id"),
                      **fields})
            print(f"  rejected [{j['mode']}] ({r['why']}): {(r['raw'] or '')[:160]!r}")
        return rejected
