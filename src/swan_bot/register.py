"""How a citizen writes, who they are talking to, and whether they said something personal (todo/50 fixes 2 and 4).

The prompt critique (docs/06-strategy/prompt-critique-2026-10-28.md): citizens write all lowercase 24% of the time and
end without a full stop 16% (us 7% and 0.1%); 9.5% open by addressing someone by name ("Rex, you're right about...");
we answered a condolence ("so sorry to hear about your dad") with a story about a market stall. read() is the measure;
content turns it into prompt lines and humanize mirrors the case and the full stop.
"""
import re

_LETTERS = re.compile(r"[A-Za-z]")
_URL = re.compile(r"https?://\S+")
_CASUAL = re.compile(r"\b(u|ur|pls|gonna|kinda|wanna|gotta|lol|haha|tbh|imo|idk|dont|cant|wont|im|ive|theyre|thats|"
                     r"isnt|doesnt|didnt|youre|yeah|yep|nah)\b", re.I)
# a name or handle they open on: "Rex, ...", "@kai_n, ...", "Fair point, Jordy.", "Kai's point lands", "Old Frank, ..."
_ADDRESS = re.compile(r"^\s*(?:@(?P<handle>\w+)|(?:(?i:fair point|good point|thanks|cheers|ta|sorry|hi|hey|oh|yes|no|"
                      r"true|exactly|agreed|honestly)[,!]?\s+)?(?:(?i:old)\s+)?(?P<name>[A-Z][a-z]{1,15}))(?:[’']s point\b|\s*[,!:.—-])")
_NOT_NAMES = {"Yes", "No", "The", "This", "That", "If", "But", "And", "So", "Honestly", "Exactly", "Agreed", "True", "Thanks",
              "Cheers", "Sorry", "Hi", "Hey", "Oh", "Well", "Look", "Okay", "Ok", "Right", "Sure", "Fair", "Good", "Great",
              "I", "We", "You", "They", "My", "Our", "Kingstonia", "Central", "Covid", "Proof", "Rules", "Same", "Totally"}
# something said to a person, not about the vote: thanks, sympathy, a joke, a direct question to them
PERSONAL = re.compile(r"\bsorry (to hear|for your|about your)\b|\bmy condolences\b|\bthinking of you\b|\bhugs?\b|"
                      r"\bthank(s| you)\b|\bcheers\b|\bappreciate (it|you|that)\b|\bhaha+\b|\blol\b|😂|"
                      r"\bhow (are|is) (you|your)\b|\bhope (you|your)\b|\bthat'?s (so )?(sad|awful|hard|tough|lovely)\b", re.I)


def read(text):
    """{lower, no_stop, casual, words, addressed}: all lowercase (30+ letters), no closing punctuation, casual marks,
    word count (links left out), and the name or @handle they open on (None)."""
    t = _URL.sub("", text or "").strip()
    letters = _LETTERS.findall(t)
    m = _ADDRESS.match(t)
    name = m and (m.group("handle") or m.group("name"))
    if name and name in _NOT_NAMES:
        name = None
    return dict(lower=len(letters) >= 30 and t == t.lower(), no_stop=bool(t) and t[-1].isalnum(),
                casual=bool(_CASUAL.search(t)), words=len(t.split()), addressed=name or None)


def personal(text):
    """The personal remark in text (thanks, sympathy, a joke, a question about them), or None."""
    m = PERSONAL.search(_URL.sub("", text or ""))
    return m.group(0) if m else None


def is_me(name, persona):
    """True when an addressed name or handle is this voice: its first name, its handle or its username."""
    if not name or not persona:
        return False
    n = name.lower()
    first = (persona.get("name") or "").split()[:1]
    return n in {(first[0].lower() if first else ""), (persona.get("handle") or "").lower(),
                 (persona.get("username") or "").lower()} - {""}


def line(reg):
    """The register line for a reply prompt: answer the way they write. "" when they write like everyone."""
    if not reg:
        return ""
    how = []
    if reg["lower"]:
        how.append("all lowercase")
    if reg["casual"]:
        how.append("casually")
    if reg["no_stop"] and not reg["lower"]:
        how.append("without a full stop at the end")
    size = ("in a line or two" if reg["words"] <= 25 else f"in about {min(reg['words'], 60)} words")
    lead = f"They write {', '.join(how)} {size}" if how else f"They write {size}"
    return f"{lead}: answer in the same register and no longer than they did. Plain sentences: no semicolons. "
