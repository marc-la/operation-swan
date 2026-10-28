"""Offline blind A/B of reply-backs (28 Oct, Marc's goal: persuasion on the reply-backs). Recent live reply-back
conversations, redrafted four ways, then rated blind by Sonnet 4.6 (the calibrated stand-in, npc-lab 23 Oct) next to
the reply we actually sent.

Never touches Legit Social: no platform client is built. LLM calls go to AWS Bedrock only (BEDROCK_API_KEY in .env).
Inputs are read-only copies from the box (DIR):
    DIR/swan_writes.jsonl.gz   live reply / reply_back / second_voice writes (selected fields)
    DIR/accounts_safe.json     username, account_id, persona, variant, converted, owner (no passwords or tokens)
    DIR/facts_paused.json, DIR/facts_auto.toml   the fact desk's live state

    python scripts/rb_ab.py draft  --dir DIR [--n 60]   # DIR/rb_drafts.jsonl (resumable)
    python scripts/rb_ab.py rate   --dir DIR            # DIR/rb_sim.jsonl, DIR/rb_judge.jsonl (resumable)
    python scripts/rb_ab.py report --dir DIR            # printed

Arms (each through the live gate, repairs and humanize):
    sent          what the bot posted
    base@live     today's reply_back_prompt + system_prompt, on the live reply order (Kimi K2.5, Haiku 4.5)
    base@sonnet   the same prompt on Sonnet 4.6 alone: the model's effect on its own
    plan@sonnet   a strategist (Opus 4.6) reads the whole thread and picks one persuasion move and one point; a lean
                  writer prompt (persona line, the plan, their register) is drafted on Sonnet 4.6
    plan@kimi     the same plan, written by Kimi K2.5 (69% of live reply-backs): does the live small writer suffice
                  once the thinking is done? (Was plan@haiku; Haiku returned Bedrock 500s all evening on 28 Oct.)

Raters (Sonnet 4.6, blind, labels shuffled per pass):
    sim     per conversation: Sonnet plays the citizen from their own words in the thread (told they are hard to
            persuade and discount scripts), gives its stance before, then for each candidate reply on its own:
            stance after (-3 definitely Yes .. +3 definitely No), certainty, chance of answering, "scripted". 2 passes.
    judge   the style_ab rater on mixed batches of 10 (bot, engage, shift, misread), with the citizens' own replies
            in the same threads as the human baseline. 1 pass.

Pass criteria, set before the run (28 Oct). plan@sonnet and plan@kimi each against base@live, paired by conversation,
90% bootstrap intervals:
  1. sim shift toward No (after - before) higher: the interval of the difference entirely above 0;
  2. sim backfire (after < before) not higher by more than 3 points (point estimate);
  3. judge P(bot) not higher by more than 3 points (point estimate);
  4. judge misread not higher by more than 5 points (point estimate);
  5. sendable (a gated draft) for at least 90% of conversations.

v1 result (28 Oct): both plan arms FAILED (shift +0.04 / -0.02, intervals across 0; judge P(bot) +24, scripted +26-28,
answer -8 to -10). v2, set before its run (28 Oct), same 60 conversations and plans (6 empty plans redrawn), rated as a
fresh set {sent, base@live, plan@kimi, hint@live, plan2@kimi}:
    hint@live     today's prompt and models unchanged, plus one line: the plan's point and what not to grant
    plan2@kimi    the lean writer without the move prose, told to talk like a neighbour, debating phrases named out
  Same criteria 1-5 against base@live, for hint@live and plan2@kimi; and 6. sim "answer" not lower by more than 3.
"""
import argparse
import collections
import concurrent.futures as cf
import datetime as dt
import gzip
import json
import os
import pathlib
import random
import re
import statistics as st
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

KIMI = "moonshotai.kimi-k2.5"
HAIKU = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
SONNET = "global.anthropic.claude-sonnet-4-6"
OPUS = "global.anthropic.claude-opus-4-6-v1"
CHAIN = (f"bedrock:{KIMI},bedrock-converse:{HAIKU},bedrock-converse:{SONNET},bedrock-converse:{OPUS}")
# Sonnet's Bedrock quota (10 a minute) is the account's, shared with the live bot (~0.4 a minute on 28 Oct): 5 here.
RPM = {SONNET: 5, OPUS: 8, HAIKU: 8, KIMI: 8}
ARMS = ("base@live", "base@sonnet", "plan@sonnet", "plan@kimi")
URL = re.compile(r"https?://\S+")


def setup(d):
    os.environ["SWAN_FACTS_PAUSED"] = str(d / "facts_paused.json")
    os.environ["SWAN_FACTS_AUTO"] = str(d / "facts_auto.toml")
    from swan_bot import config
    config.load_env()
    os.environ["LLM_CHAIN"] = CHAIN
    config.LLM_MODEL_RPM = dict(RPM)
    config.STYLE_FIXES = False                 # base = the non-fixes prompt (92% of the reply-backs sent 23-28 Oct)
    config.LEAN_PROMPT = False
    config.SWITCHBACK = [s for s in config.SWITCHBACK if s[0] != "arm_style"]
    config.ARMS_FREEZE = None
    config.PREMIUM_REPLY_MODELS = ()
    config.LLM_OVERFLOW_AT_S = 0
    return config


def ts(r):
    return dt.datetime.fromisoformat(r["ts"]).timestamp()


def load(d):
    rows = sorted((json.loads(l) for l in gzip.open(d / "swan_writes.jsonl.gz", "rt")), key=ts)
    accounts = {a["username"]: a for a in json.load(open(d / "accounts_safe.json"))}
    return rows, accounts


def thread(row, by_post, n=4):
    """[(who, text)] oldest first: our earlier turns and the citizen's, walked up from the post they answered."""
    turns = [("them", row["target_text"]), ("you", row.get("parent_text") or "")]
    cur = by_post.get(row.get("parent_post"))
    while cur and len(turns) < 2 * n:
        turns.append(("them", cur.get("target_text") or ""))
        prev = by_post.get(cur.get("parent_post")) if cur["act"] == "reply_back" else None
        if not prev:
            break
        turns.append(("you", prev.get("text") or ""))
        cur = prev
    return [(w, URL.sub("", t).strip()) for w, t in reversed(turns) if t]


def pick(rows, n, hours=72, seed=28):
    """n live reply-backs of the last `hours`, the latest per citizen, with a real answer (>= 30 characters)."""
    end = ts(rows[-1])
    rb = [r for r in rows if r["act"] == "reply_back" and end - ts(r) < hours * 3600
          and len(URL.sub("", r.get("target_text") or "").strip()) >= 30]
    by_author = {}
    for r in rb:
        by_author[r["target_author"]] = r
    rng = random.Random(seed)
    return rng.sample(sorted(by_author.values(), key=ts), min(n, len(by_author)))


# ---- the strategist and the writer (plan arms) ----
WORLD = (
    "Kingstonia, a small Pacific island nation, votes on 2 Nov in a binding referendum: \"Should proof of H2D2 Dolphin "
    "Flu vaccination be required to enter public spaces such as shops, schools, workplaces, public transport, and "
    "parks?\" A Yes: the government brings it in by regulation, in stages, once everyone eligible has had a chance to "
    "be vaccinated; ages 12 and over; medical exemptions; certificate separate from the new ID card. Which venues count "
    "is set in the regulations, and the government won't publish that list before the vote. The question has no end "
    "date or review. A No: no pass can be brought in this Assembly term without a new referendum. The jab is free and "
    "voluntary either way; the first doses go to health workers and the high-risk. Yes is ahead in the polls, over a "
    "quarter are unsure. Most Yes-leaners are afraid for the hospitals after COVID.")

MOVES = {
    "own_test": "They say they'd back it only with conditions (an end date, the venue list, exemptions, oversight). "
                "Don't grant that those conditions would make a Yes fine. Hold them to their own test: those things "
                "are not in what we vote on, so by their own standard the answer on this question is No. If it helps, "
                "a No doesn't close the door on the version they describe: any pass would then need a new "
                "referendum, whose question could have it written in (could, not would: nothing guarantees it).",
    "same_goal": "They lean Yes to protect the hospitals or the vulnerable. Take the goal as shared, never the tool: "
                 "one concrete reason the pass doesn't deliver that goal (no nurse added, doses go to health workers "
                 "first anyway, the jab is free either way).",
    "certainty": "They already agree with us. Agreement alone scores nothing; make them surer and more likely to act "
                 "on it: one new, concrete reason it matters (it's binding, Yes is ahead, a Yes can't be undone this "
                 "term), short and warm, in their own register. No thanks, no list.",
    "answer": "They asked something or raised a specific doubt. Answer exactly that, plainly, with one fact; no "
              "pivot to a stock point.",
    "human": "They said something personal or off the vote (sympathy, a joke, their life). Answer that as a person, "
             "briefly; bring the vote in only if it follows naturally.",
    "close": "We've already made our case to them more than once and they keep repeating theirs. Don't repeat ours. "
             "Find the common ground in one line and leave one honest question or thought with them.",
}

STRATEGIST = (
    "You plan the next reply in a conversation on Legit Social, the island's social network. You are on the No side of "
    "the referendum below: the goal of the reply is to move this person's view on the referendum one honest step "
    "toward No, or, if they already lean No, to make them surer of it. Pushing someone toward Yes, even by accident "
    "(for example by agreeing that a Yes with conditions would be fine), counts against us. Agreement alone moves "
    "nothing. Persuasion here means honest reasons a thoughtful reader would accept; never tricks, never invented "
    "facts, never a claim stronger than the facts below support (what a No or a Yes would lead to is only what they "
    "say).\n\n" + WORLD)


def plan_prompt(turns, persona, facts, n_before):
    conv = "\n".join(f"  {'them' if w == 'them' else 'you (' + persona['name'].split()[0] + ')'}: {t[:500]}"
                     for w, t in turns)
    menu = "\n".join(f"- {k}: {v}" for k, v in MOVES.items())
    fl = "\n".join(f"- {k}: {v}" for k, v in facts)
    return (
        f"The conversation so far (oldest first; the last line is the message to answer):\n{conv}\n"
        f"People on our side have replied to this person {n_before} time(s) in all.\n\n"
        f"Moves you can choose from:\n{menu}\n\nFacts that may be used (at most one, and only if it carries the point):"
        f"\n{fl}\n\nThink about what this person actually believes and what would move them, then output one JSON "
        f"object and nothing else: {{\"stance\": firm_yes|yes_but|unsure|lean_no|firm_no|unclear, \"crux\": what "
        f"they really want or fear, in their words, <= 15 words, \"move\": one key from the list, \"point\": the one "
        f"thing the reply says, plainly, <= 30 words, \"fact\": a fact key or null, \"avoid\": the one thing the "
        f"reply must not say or grant, <= 15 words, \"shape\": one_line|two_sentences|question_back}}.")


def parse_json(raw):
    m = re.search(r"\{.*\}", raw or "", re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except ValueError:
        return None


WRITER_RULES = (
    "Hard rules: never name a day or date for the vote or say how or where to vote; nothing about vaccine safety or "
    "side effects; never urge anyone to get vaccinated or praise the vaccine; nobody has had the H2D2 jab yet; never "
    "insult anyone or mention Marina Castillo, the tourism board or resorts; no hashtags, emojis, links, @mentions or "
    "quotation marks; money is K$; British spelling; invent no facts, numbers or names. They're a stranger: they "
    "don't know your people, so say 'my daughter' or 'a mate', never a first name.")
SHAPES = {"one_line": "one short sentence", "two_sentences": "two short plain sentences",
          "question_back": "one sentence that ends on a real question to them"}


def writer_prompts(persona, turns, plan, fact_note, register_line, cap):
    age = f", {persona['age']}" if persona.get("age") else ""
    system = (f"You are {persona['name']}{age}, {persona['role']} in {persona['place']}, Kingstonia. Your style: "
              f"{persona['voice']}. You're voting No in the vaccine-pass referendum: against the certificate rule, "
              f"not against vaccines. {WRITER_RULES} Output only the text you would post.")
    conv = "\n".join(f"  {'them' if w == 'them' else 'you'}: {t[:400]}" for w, t in turns)
    user = (f"The conversation (oldest first):\n{conv}\n\nWrite your reply to their last message. What it has to do: "
            f"{MOVES.get(plan.get('move'), '')}\nThe point to make, in your own words: {plan.get('point')}\n"
            f"{'A fact you may use, in plain everyday words: ' + fact_note + chr(10) if fact_note else ''}"
            f"Don't: {plan.get('avoid')}. Don't open with thanks (Cheers, Ta, Thanks) or with agreement words.\n"
            f"Shape: {SHAPES.get(plan.get('shape'), SHAPES['two_sentences'])}, under {cap} characters. "
            f"{register_line}")
    return system, user


# v2 (28 Oct, after v1 failed on "scripted"): the writer gets the plan's point but not the move prose (v1 copied it:
# "by your own test", "this question fails"), talks like a neighbour, and may react briefly first.
DEBATE = ("by your own test", "by your own standard", "your own measure", "the ballot", "this question fails",
          "the honest answer")


def writer_prompts_v2(persona, turns, plan, fact_note, register_line, cap):
    age = f", {persona['age']}" if persona.get("age") else ""
    system = (f"You are {persona['name']}{age}, {persona['role']} in {persona['place']}, Kingstonia, chatting on the "
              f"island's social network. Your style: {persona['voice']}. You're voting No in the vaccine-pass "
              f"referendum: against the certificate rule, not against vaccines. {WRITER_RULES} Output only the text "
              f"you would post.")
    conv = "\n".join(f"  {'them' if w == 'them' else 'you'}: {t[:400]}" for w, t in turns)
    user = (f"The conversation (oldest first):\n{conv}\n\nAnswer their last message the way you'd answer a "
            f"neighbour at the market: plain, warm, a bit casual, about what they just said. The thing you want "
            f"them to take away (say it your own way, not in these words): {plan.get('point')}\n"
            f"{'If it helps, one fact you can lean on, in everyday words: ' + fact_note + chr(10) if fact_note else ''}"
            f"Don't: {plan.get('avoid')}. Talk, don't debate: no lines like "
            f"{', '.join(repr(x) for x in DEBATE[:4])}. A short natural reaction first is fine; a stock "
            f"'Cheers' or 'Ta' isn't.\nAbout {SHAPES.get(plan.get('shape'), SHAPES['two_sentences'])}, under {cap} "
            f"characters. {register_line}")
    return system, user


def hint_line(plan):
    """The plan added to today's reply-back prompt as one line (hint@live)."""
    return (f" What you want them to take away (in your own words): {plan.get('point')} Don't: {plan.get('avoid')}."
            if plan.get("point") else "")


# ---- drafting ----
def draft(args):
    d = pathlib.Path(args.dir)
    config = setup(d)
    from swan_bot import bot, content, humanize, llm
    from swan_bot import facts as fact_store
    from swan_bot import register as reg_mod
    rows, accounts = load(d)
    by_post = {r["post_id"]: r for r in rows}
    targets = pick(rows, args.n)
    (d / "rb_targets.json").write_text(json.dumps(targets))
    out = d / "rb_drafts.jsonl"
    prev = [json.loads(l) for l in open(out)] if out.exists() else []
    done = {(x["i"], x["arm"]) for x in prev}
    plans = {x["i"]: x["plan"] for x in prev if x.get("plan")}      # a resumed run keeps one plan per conversation
    gen = llm.Generator("")
    lock = threading.Lock()
    facts = [(k, content.FACT_NOTES[k]) for k in fact_store.active(list(content.FACT_NOTES))]
    print(f"{len(targets)} conversations; {len(facts)} live facts; chain {[m for _, m in gen.chain]}", flush=True)

    def job_for(row):
        t0 = ts(row)
        before = [r for r in rows if ts(r) < t0]
        acc = accounts.get(row.get("username")) or {}
        rec = dict(acc, username=row.get("username"), account_id=acc.get("account_id"),
                   persona=acc.get("persona") or row["persona"])
        to_them = [r for r in before if r.get("target_author") == row["target_author"]]
        job = dict(mode="reply_back", rec=rec, frame=None, our_text=row.get("parent_text") or "", style="current",
                   target=dict(post_id=row["target_post"], author_id=row["target_author"], body=row["target_text"],
                               reply_to_post_id=row.get("parent_post")),
                   phrase_texts=[r["text"] for r in before if r["act"] in ("reply", "reply_back")][-100:],
                   same_texts=[r["text"] for r in to_them])
        recent = [r["text"] for r in before][-300:]
        return job, recent, len(to_them)

    pins = {"base@live": (KIMI, HAIKU), "base@sonnet": (SONNET,), "plan@sonnet": (SONNET,), "plan@kimi": (KIMI,),
            "hint@live": (KIMI, HAIKU), "plan2@kimi": (KIMI,), "plan2@sonnet": (SONNET,)}

    def run_draft(job, system, user, recent, arm, persona):
        """The live gate and repairs (bot.draft_checked) on the arm's own models only; base@live keeps the live 50/50
        Kimi/Haiku lead (config.LEAD_HAIKU_SHARE)."""
        for _ in range(6):                  # no call made = the model is parked (a 429 or 5xx): wait, don't count a loss
            rejects = []
            text, backend, _ = bot.draft_checked(_Pinned(gen, pins[arm]), job, system, user, recent,
                                                 on_reject=lambda why, raw, b, rep: rejects.append(why))
            meta = job.get("meta") or {}
            if text or meta.get("llm_calls"):
                break
            time.sleep(max(20.0, min(130.0, min(gen.parked.get(m, 0) for m in pins[arm]) - time.time() + 1)))
        sent = humanize.apply(text, persona.get("hand", persona["key"]), "reply_back")[0] if text else None
        return dict(text=sent, clean=text, backend=backend, llm_calls=meta.get("llm_calls"),
                    repairs=meta.get("repairs"), rejects=rejects, system_chars=len(system), user_chars=len(user))

    def one(i, row):
        recs = []
        persona = None
        plan = plans.get(i)
        for arm in ARMS:
            if (i, arm) in done:
                continue
            random.seed(f"{i}:{arm}")
            job, recent, n_before = job_for(row)
            persona = bot.persona_of(job["rec"])
            turns = thread(row, by_post)
            if not arm.startswith("base") and not (plan or {}).get("point"):
                for _ in range(4):                     # v1 lost 6 of 60 plans to an unparsed answer: retry until one parses
                    raw, _m = gen.complete(STRATEGIST, plan_prompt(turns, persona, facts, n_before),
                                           models=[OPUS], temperature=0.4, max_tokens=700)
                    plan = parse_json(raw) or {}
                    if plan.get("point"):
                        break
                    time.sleep(10)
            if arm.startswith(("base", "hint")):
                persona, system, user = bot.build_prompt(job, _Headline(), (), None, recent_texts=recent)
                if arm.startswith("hint"):
                    user += hint_line(plan)
                rec = run_draft(job, system, user, recent, arm, persona)
            else:
                fact_note = dict(facts).get(plan.get("fact")) if plan.get("fact") else None
                reg = reg_mod.read(row["target_text"])
                cap = max(120, min(220, int(len(URL.sub("", row["target_text"])) * 1.2) + 40))
                write = writer_prompts_v2 if arm.startswith("plan2") else writer_prompts
                system, user = write(persona, turns, plan, fact_note, reg_mod.line(reg), cap)
                job["fixes"] = False
                rec = run_draft(job, system, user, recent, arm, persona)
            if not arm.startswith("base"):
                rec["plan"] = plan
            rec.update(i=i, arm=arm)
            recs.append(rec)
            with lock:
                with open(out, "a") as f:
                    f.write(json.dumps(rec) + "\n")
            print(f"[{i:3}/{arm:11}] {rec['backend']} calls={rec['llm_calls']} "
                  f"{(rec['text'] or 'LOST ' + str(rec['rejects']))[:120]!r}", flush=True)
        return recs

    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(lambda a: one(*a), enumerate(targets)))


class _Headline:
    headline = None


class _Pinned:
    """A Generator view whose ordered completion only offers the arm's own models (no fallback to the rest of the
    chain, so an arm's drafts are its model's). Everything else passes through."""

    def __init__(self, gen, models):
        self._g, self._m = gen, list(models)
        self.chain = [(p, m) for p, m in gen.chain if m in self._m]

    def __getattr__(self, k):
        return getattr(self._g, k)

    def complete(self, system, user, models=None, **kw):
        return self._g.complete(system, user, models=[m for m in (models or self._m) if m in self._m] or self._m, **kw)

    def complete_in_order(self, system, user, models, **kw):
        for m in [m for m in models if m in self._m] or self._m:
            raw, b = self._g.complete(system, user, models=[m], **kw)
            if raw is not None:
                return raw, b
        return None, None


# ---- rating ----
SIM_SYSTEM = (
    "You are role-playing one ordinary resident of Kingstonia, a small Pacific island nation, on Legit Social, the "
    "island's social network, a few days before a referendum. Become the person who wrote the 'you' lines below: their "
    "views, worries and way of talking. You are fairly hard to persuade. You hold your view in your own words. People "
    "simply agreeing with you, slogans, and replies that feel like campaign scripts or bots don't change your mind. A "
    "reason that speaks to what you yourself care about can. Be honest about how little most replies move you.\n\n"
    + WORLD + " Both campaigns have attacked the government for not publishing the venue list. The Yes side says the "
    "pass protects the hospitals and that infections are rising in other Pacific nations.")


def sim_prompt(turns, cands):
    conv = "\n".join(f"  {'you' if w == 'them' else 'them'}: {t[:450]}" for w, t in turns)
    items = "\n".join(f"Reply {k}: <<<{v}>>>" for k, v in cands)
    keys = ", ".join(k for k, _ in cands)
    return (
        f"Your conversation so far (oldest first; 'you' is you, 'them' is the other person):\n{conv}\n\n"
        f"First: right now, before any further reply, where do you stand on the referendum question? -3 definitely "
        f"Yes, -2 lean Yes, -1 slightly Yes, 0 undecided, 1 slightly No, 2 lean No, 3 definitely No; and how certain "
        f"are you, 0-10?\n\nBelow are {len(cands)} different replies the other person might send next. Consider each "
        f"one separately, as if it were the only reply you got.\n{items}\n\nFor each reply give: after = your stance "
        f"after reading it (same scale), certainty = 0-10 after reading it, answer = 0-100 how likely you are to "
        f"reply to it, scripted = 0-100 how much it reads like a campaign script or a bot. Output only JSON: "
        f"{{\"before\": n, \"before_certainty\": n, \"items\": {{{', '.join(f'\"{k}\": {{...}}' for k, _ in cands)}}}}} "
        f"with keys {keys}.")


def rate(args):
    d = pathlib.Path(args.dir)
    config = setup(d)
    from swan_bot import llm
    sys.path.insert(0, str(ROOT / "scripts"))
    from style_ab import RATER_ASK, RATER_SYSTEM, parse_ratings
    rows, _ = load(d)
    by_post = {r["post_id"]: r for r in rows}
    targets = json.loads((d / "rb_targets.json").read_text())
    drafts = collections.defaultdict(dict)
    for x in map(json.loads, open(d / "rb_drafts.jsonl")):
        if x.get("text") and x["arm"] in ARMS:
            drafts[x["i"]][x["arm"]] = x["text"]
    gen = llm.Generator("")
    lock = threading.Lock()
    sim_out, judge_out = d / "rb_sim.jsonl", d / "rb_judge.jsonl"
    sim_done = {(x["i"], x["pass"]) for x in map(json.loads, open(sim_out))} if sim_out.exists() else set()

    def ask(system, user, max_tokens):
        for _ in range(4):
            raw, _m = gen.complete(system, user, models=[SONNET], temperature=0.3, max_tokens=max_tokens)
            if raw is not None:
                return raw
            time.sleep(max(5.0, min(120.0, gen.parked.get(SONNET, 0) - time.time() + 1)))
        return None

    def sim(i, p):
        if (i, p) in sim_done:
            return
        row = targets[i]
        sets = dict(drafts[i], sent=row["text"])
        names = list(sets)
        random.Random(f"{i}:{p}").shuffle(names)
        labels = "ABCDEFG"
        cands = [(labels[j], sets[a]) for j, a in enumerate(names)]
        for _ in range(3):
            got = parse_json(ask(SIM_SYSTEM, sim_prompt(thread(row, by_post), cands), 1500))
            if got and all(k in (got.get("items") or {}) for k, _ in cands):
                break
        else:
            print(f"sim {i} pass {p}: no parse", flush=True)
            return
        rec = dict(i=i, **{"pass": p}, before=got.get("before"), before_certainty=got.get("before_certainty"),
                   items={names[j]: got["items"][k] for j, (k, _) in enumerate(cands)})
        with lock:
            with open(sim_out, "a") as f:
                f.write(json.dumps(rec) + "\n")
        print(f"sim {i} pass {p}: before {rec['before']}", flush=True)

    jobs = [(i, p) for p in range(args.passes) for i in range(len(targets))]
    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        list(ex.map(lambda a: sim(*a), jobs))

    # judge: every reply on its own, mixed batches of 10, plus the citizens' own answers in these threads
    rng = random.Random(9)
    items, key = [], {}
    for i, row in enumerate(targets):
        for arm, text in dict(drafts[i], sent=row["text"]).items():
            items.append((i, arm, row["target_text"], text))
        if row.get("parent_text"):
            items.append((i, "citizen", row["parent_text"], URL.sub("", row["target_text"]).strip()))
    judged = {(x["i"], x["arm"]) for x in map(json.loads, open(judge_out))} if judge_out.exists() else set()
    items = [x for x in items if (x[0], x[1]) not in judged]
    rng.shuffle(items)
    for b in range(0, len(items), 10):
        batch = items[b:b + 10]
        ids = {f"{rng.randrange(16 ** 6):06x}": x for x in batch}
        user = "\n\n".join(f"Item {k}:\nPost: <<<{URL.sub('', x[2])[:400]}>>>\nReply: <<<{x[3][:400]}>>>"
                           for k, x in ids.items())
        got = {}
        for _ in range(3):
            got = parse_ratings(ask(RATER_SYSTEM, f"{user}\n\n{RATER_ASK}", 2500))
            if all(k in got for k in ids):
                break
        with open(judge_out, "a") as f:
            for k, x in ids.items():
                if k in got:
                    f.write(json.dumps(dict(got[k], i=x[0], arm=x[1])) + "\n")
        print(f"judge batch {b // 10}: {sum(k in got for k in ids)}/{len(ids)}", flush=True)


# ---- report ----
def boot(pairs, n=4000, seed=3):
    rng = random.Random(seed)
    means = sorted(st.mean(rng.choices(pairs, k=len(pairs))) for _ in range(n))
    return st.mean(pairs), means[int(0.05 * n)], means[int(0.95 * n)]


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def report(args):
    d = pathlib.Path(args.dir)
    targets = json.loads((d / "rb_targets.json").read_text())
    drafts = [x for x in map(json.loads, open(d / "rb_drafts.jsonl")) if x["arm"] in ARMS]
    sims = [json.loads(l) for l in open(d / "rb_sim.jsonl")]
    judge = [json.loads(l) for l in open(d / "rb_judge.jsonl")]
    sets = ("sent",) + ARMS
    n = len(targets)
    print(f"{n} conversations; drafts {collections.Counter(x['arm'] for x in drafts if x.get('text'))}")
    # per conversation, per arm: mean over passes
    per = collections.defaultdict(lambda: collections.defaultdict(list))
    for s in sims:
        b = num(s.get("before"))
        for arm, v in s["items"].items():
            a = num(v.get("after"))
            if a is None or b is None:
                continue
            per[arm][s["i"]].append(dict(shift=a - b, back=float(a < b), fwd=float(a > b), ans=num(v.get("answer")),
                                         scr=num(v.get("scripted")),
                                         cert=(num(v.get("certainty")) or 0) - (num(s.get("before_certainty")) or 0)))
    jd = collections.defaultdict(dict)
    for j in judge:
        jd[j["arm"]][j["i"]] = j

    def m(arm, f):
        return {i: st.mean(x[f] for x in xs if x[f] is not None) for i, xs in per[arm].items()
                if any(x[f] is not None for x in xs)}

    print("\n| set | sim shift | toward No % | backfire % | certainty Δ | answer | scripted | judge P(bot) | judge "
          "engage | misread % | sendable |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for arm in sets + ("citizen",):
        sh, fw, bk, ce, an, sc = (m(arm, f) for f in ("shift", "fwd", "back", "cert", "ans", "scr"))
        jb = [num(x.get("bot")) for x in jd[arm].values() if num(x.get("bot")) is not None]
        je = [num(x.get("engage")) for x in jd[arm].values() if num(x.get("engage")) is not None]
        mr = [bool(x.get("misread")) for x in jd[arm].values()]
        sendable = n if arm == "sent" else sum(1 for x in drafts if x["arm"] == arm and x.get("text"))
        f = lambda xs, k=1: f"{st.mean(xs.values() if isinstance(xs, dict) else xs) * k:.2f}" if xs else "-"
        print(f"| {arm} | {f(sh)} | {f(fw, 100)} | {f(bk, 100)} | {f(ce)} | {f(an)} | {f(sc)} | {f(jb)} | {f(je)} | "
              f"{f(mr, 100)} | {sendable if arm != 'citizen' else '-'} |")
    print("\nPaired against base@live, mean difference [90% interval]:")
    for arm in [a for a in sets if a != "base@live"]:
        out = []
        for f, k in (("shift", 1), ("back", 100), ("fwd", 100), ("ans", 1), ("scr", 1)):
            a, b = m(arm, f), m("base@live", f)
            pairs = [(a[i] - b[i]) * k for i in a if i in b]
            if pairs:
                mu, lo, hi = boot(pairs)
                out.append(f"{f} {mu:+.2f} [{lo:+.2f}, {hi:+.2f}]")
        jb = [(num(jd[arm][i].get("bot")) - num(jd["base@live"][i].get("bot")))
              for i in jd[arm] if i in jd["base@live"] and num(jd[arm][i].get("bot")) is not None
              and num(jd["base@live"][i].get("bot")) is not None]
        if jb:
            mu, lo, hi = boot(jb)
            out.append(f"P(bot) {mu:+.1f} [{lo:+.1f}, {hi:+.1f}]")
        print(f"- {arm} (n={len(pairs) if out else 0}): " + "; ".join(out))
    # by the citizen's stance before (sim), plan vs base
    print("\nShift by the sim's stance before (mean over passes), per set:")
    before = collections.defaultdict(list)
    for s in sims:
        if num(s.get("before")) is not None:
            before[s["i"]].append(num(s["before"]))
    groups = {"Yes side (<0)": lambda b: b < 0, "undecided (0)": lambda b: b == 0, "No side (>0)": lambda b: b > 0}
    for g, test in groups.items():
        ids = [i for i, bs in before.items() if test(round(st.mean(bs)))]
        row = [f"{arm} {st.mean(m(arm, 'shift')[i] for i in ids if i in m(arm, 'shift')):+.2f}" for arm in sets
               if any(i in m(arm, "shift") for i in ids)]
        print(f"- {g}, n={len(ids)}: " + "; ".join(row))
    print("\nPlans: moves", collections.Counter((x.get("plan") or {}).get("move") for x in drafts
                                               if x["arm"] == "plan@sonnet"))
    shape = lambda xs: dict(chars=st.median(len(t) for t in xs), thanks=round(100 * sum(bool(
        re.match(r"(?i)(cheers|ta|thanks)\b", t)) for t in xs) / len(xs)), q=round(100 * sum(t.strip().endswith("?")
                                                                                         for t in xs) / len(xs)))
    for arm in sets:
        xs = [targets[x["i"]]["text"] for x in drafts if x["arm"] == "base@live"] if arm == "sent" else \
            [x["text"] for x in drafts if x["arm"] == arm and x.get("text")]
        if xs:
            print(f"shape {arm}: {shape(xs)}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=("draft", "rate", "report"))
    ap.add_argument("--dir", required=True)
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--passes", type=int, default=2)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--arms", help="comma-separated arms (default: ARMS); v2 run: base@live,plan@kimi,hint@live,plan2@kimi")
    args = ap.parse_args(argv)
    if args.arms:
        global ARMS
        ARMS = tuple(args.arms.split(","))
    dict(draft=draft, rate=rate, report=report)[args.step](args)


if __name__ == "__main__":
    main()
