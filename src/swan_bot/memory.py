"""What each voice has said, and what we have said to each citizen (todo/50 fixes 1 and 2).

The prompt critique (docs/06-strategy/prompt-critique-2026-10-28.md): one hot voice sent 1,542 replies in 32 h and told
"Jacqui starts high school" in 763 of them, because the gate compares a draft with the team's latest texts, never with
the voice's own, and the prompt shows the voice's people and fortnight event every time. And the reply prompt never
said what we had already told the citizen, though 37% of writes go to citizens we wrote to 8+ times.

State, in bot.py's state dict (saved with it), recorded on every send whatever the arm, so a fixes block starts with
a day of history:
    voice_texts   {username: [clean text, ...]}               the voice's last config.VOICE_MEMORY_N texts
    voice_items   {username: {item key: [ts, ...]}}           when its prompts carried each profile item (last 24 h)
    citizen_sent  {author id: [[ts, username, clean text]...]} our last few texts to a citizen, any voice
    citizen_n     {author id: n}                              how many times we have written to them in all

arm() says whether this write is in a "fixes" block (config.STYLE_FIXES, switchback arm_style).
"""
import random
import re
import time

from . import config, experiment

ITEM_WINDOW_S = 24 * 3600
HISTORY_CHARS = 160         # what a citizen's history keeps of each text (the prompt quotes 140): the state is saved on every send
_WORD = re.compile(r"[a-z']+|\d+")
# words that don't make a run worth remembering: "the question doesn't" is a template (the phrase budgets have those);
# "jacqui starts high" is a story
_STOP = set("""a an the and or but so to of in on at for from by with as is are was were be been it its it's this that
these those there their they them you your you're i i'm i'd i've me my we our us he she his her him not no yes do does
doesn't don't did didn't would wouldn't could can can't will won't just only even still then than if when what which who
how why where all any one some every more most much very really about into over after before up out off get got say says
said""".split())
# the argument's own words (facts, frame angles and gists, levers, rebuttals, the question): a run made only of these is
# our shared case ("adds no nurse", "40 empty nursing"), which the team-wide phrase budgets police. A run with a word from
# outside it is a voice's story ("jacqui starts high", "my sister karen"): that is what one voice must not tell everyone.
_CASE_EXTRA = set("""question questions itself gives ballot list places doors door gate gates papers pass passes certificate
end ends ending finish stops stop never says nurse nurses nursing posts empty bed beds""".split())
_VOCAB = None


def reset_vocab():
    """Forget the argument vocabulary (facts.ON_RELOAD calls this, so a fact the desk adds counts as our case)."""
    global _VOCAB
    _VOCAB = None


def argument_vocab():
    global _VOCAB
    if _VOCAB is None:
        from . import content, facts            # here, not at import: content imports this module
        text = " ".join([f"{f['text']} {f['note']}" for f in facts.TABLE.values()] +
                        [f"{f['angle']} {f['gist']}" for f in content.FRAMES.values()] + list(content.LEVERS.values()) +
                        [line for _, line, _ in content.REBUTTALS] + [content.QUESTION])
        _VOCAB = set(_WORD.findall(text.lower())) | _CASE_EXTRA
    return _VOCAB


def arm(t=None):
    """'fixes' or 'base' for a write now: base while config.STYLE_FIXES is off; else arm_style's block (frozen at
    ARMS_FREEZE to FREEZE_PIN["arm_style"]), 'fixes' everywhere if arm_style is not on the switchback."""
    if not getattr(config, "STYLE_FIXES", False):
        return "base"
    return experiment.block("arm_style", t)[1] or "fixes"


def item_key(text):
    """A profile item's key: its first 40 characters, lowercased (the item texts are fixed per card and variant)."""
    return re.sub(r"\s+", " ", (text or "").lower()).strip()[:40]


def record(state, username, author_id, text, items=(), t=None):
    """Remember one sent text: the voice's own texts, the profile items its prompt carried, and (author_id given) the
    citizen's history. Prunes as it goes."""
    t = time.time() if t is None else t
    if username and text:
        vt = state.setdefault("voice_texts", {})
        vt[username] = (vt.get(username, []) + [text])[-config.VOICE_MEMORY_N:]
    if username and items:
        vi = state.setdefault("voice_items", {}).setdefault(username, {})
        for k in items:
            vi[k] = [x for x in vi.get(k, []) if t - x < ITEM_WINDOW_S] + [t]
        for k in [k for k, ts in vi.items() if not any(t - x < ITEM_WINDOW_S for x in ts)]:
            del vi[k]
    if author_id is not None and text:
        a = str(author_id)
        cs, cn = state.setdefault("citizen_sent", {}), state.setdefault("citizen_n", {})
        cs[a] = (cs.get(a, []) + [[round(t), username, text[:HISTORY_CHARS]]])[-config.CITIZEN_HISTORY_N:]
        cn[a] = cn.get(a, 0) + 1
        if len(cs) > config.CITIZEN_HISTORY_MAX:
            for k in sorted(cs, key=lambda k: cs[k][-1][0])[:len(cs) - config.CITIZEN_HISTORY_MAX]:
                cs.pop(k, None)
                cn.pop(k, None)


def voice_texts(state, username):
    return list((state.get("voice_texts") or {}).get(username) or [])


def spent_items(state, username, t=None):
    """The item keys this voice's prompts carried ITEM_MAX_PER_DAY times in the last 24 h: left out of its next prompts."""
    t = time.time() if t is None else t
    vi = (state.get("voice_items") or {}).get(username) or {}
    return {k for k, ts in vi.items() if sum(t - x < ITEM_WINDOW_S for x in ts) >= config.ITEM_MAX_PER_DAY}


def colour(rng=random):
    """True for the share of fixes-block replies whose prompt carries the voice's profile colour."""
    return rng.random() < config.PROFILE_SHARE


def history(state, author_id):
    """(n, [(username, text), ...]): how often we wrote to this citizen, and our latest texts to them, oldest first."""
    a = str(author_id)
    n = (state.get("citizen_n") or {}).get(a, 0)
    return n, [(u, x) for _, u, x in (state.get("citizen_sent") or {}).get(a, [])]


def _runs(text, n):
    words = _WORD.findall((text or "").lower().replace("’", "'"))
    out = set()
    for i in range(len(words) - n + 1):
        run = words[i:i + n]
        if sum(len(w) >= 4 and w not in _STOP for w in run) >= 2:
            out.add(" ".join(run))
    return out


def voice_repeat(text, texts, target_text="", n=None, most=None):
    """The first run of n words (2+ content words, one of them outside the argument's vocabulary: a story, not our
    case) of text that is already in `most` of the voice's texts, and not in the citizen's own post (their words are an
    echo, not our script), or None. Replayed on 5,226 replies (26-28 Oct): 11% of the drafts as written would go,
    mostly one story ("jacqui starts high" 179, "jacqui turns 12" 125); counting the case's own words too, 18-30%."""
    n, most = n or config.VOICE_RUN_WORDS, most or config.VOICE_RUN_MAX
    if not texts:
        return None
    vocab = argument_vocab()
    theirs = _runs(target_text, n)
    seen = [_runs(old, n) for old in texts]
    words = _WORD.findall((text or "").lower().replace("’", "'"))
    for i in range(len(words) - n + 1):
        run = " ".join(words[i:i + n])
        if run in theirs or sum(len(w) >= 4 and w not in _STOP for w in words[i:i + n]) < 2:
            continue
        if not any(len(w) >= 4 and w not in _STOP and w not in vocab for w in words[i:i + n]):
            continue
        if sum(run in s for s in seen) >= most:
            return run
    return None
