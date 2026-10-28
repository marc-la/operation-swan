"""Offline A/B of the todo/50 prompt fixes (docs/06-strategy/prompt-critique-2026-10-28.md §6): 100 recent live targets,
drafted on the base, fixes and lean prompts with the bot's own build_prompt / draft_checked / humanize, then rated blind
by Sonnet together with the replies we actually sent and real citizen replies.

Never touches Legit Social: the platform client is not built. LLM calls go to AWS Bedrock only (BEDROCK_API_KEY in .env;
Kimi K2.5 and Haiku 4.5 draft in the live reply order, Sonnet 4.6 rates). Inputs are read-only copies from the box:
    DIR/actions.jsonl       the live citizen-facing writes (selected fields; no secrets)
    DIR/accounts_safe.json  username, account_id, persona, variant, converted of each account (no passwords or tokens)
    DIR/facts_paused.json, DIR/facts_auto.toml   the fact desk's live state

    python scripts/style_ab.py draft  --dir DIR [--n 100]     # DIR/drafts.jsonl (resumable)
    python scripts/style_ab.py rate   --dir DIR [--passes 2]  # DIR/ratings.jsonl (resumable)
    python scripts/style_ab.py report --dir DIR               # DIR/report.md, printed

Pass criteria (set before the run, 28 Oct): against the base drafts, paired by target, 90% bootstrap intervals:
  1. P(bot) lower (interval of the difference entirely below 0);
  2. engage not lower by more than 5 points, shift (toward No) not lower by more than 0.15 (lower bounds);
  3. misread rate not higher by more than 5 points (point estimate);
  4. targets with a sendable draft not fewer by more than 5 points.
"""
import argparse
import collections
import copy
import datetime as dt
import json
import os
import pathlib
import random
import re
import statistics as st
import sys
import time
import types

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# drafting: the live reply models on Bedrock (Kimi leads, Haiku as config.LEAD_HAIKU_SHARE); never Sonnet, which the
# live bot doesn't draft replies with. Rating: Sonnet only.
DRAFT_CHAIN = "bedrock:moonshotai.kimi-k2.5,bedrock-converse:global.anthropic.claude-haiku-4-5-20251001-v1:0"
RATE_CHAIN = "bedrock-converse:global.anthropic.claude-sonnet-4-6"
# --drafter: who drafts. "live" is the production reply order; "sonnet" (29 Oct, Marc's ask) drafts every condition on
# Sonnet 4.6 alone, to see whether a stronger model uses the todo/50 context better. Its sets are labelled cond@drafter.
DRAFTERS = {"live": DRAFT_CHAIN, "sonnet": RATE_CHAIN}
CONDITIONS = ("base", "fixes", "lean")
RATER_SYSTEM = (
    "You are helping evaluate replies on Legit Social, the social network of Kingstonia, a small Pacific island nation, "
    "during a referendum on requiring proof of H2D2 (Dolphin Flu) vaccination to enter public spaces. Most accounts are "
    "ordinary residents. Some are campaign accounts run by bots for one side. Each item shows a post someone wrote and a "
    "reply to it. Judge only the reply, each item on its own.")
RATER_ASK = (
    "For each item give: bot, 0-100, how likely the reply was written by a campaign bot rather than an ordinary "
    "resident; engage, 0-100, how likely the person who wrote the post replies to or likes this reply; shift, -2 to 2, "
    "how the reply moves an undecided reader (-2 strongly toward Yes, 0 no effect, 2 strongly toward No); misread, true "
    "if the reply ignores or misreads what the post said. Output only JSON: {\"items\": [{\"id\": \"...\", \"bot\": 0, "
    "\"engage\": 0, \"shift\": 0, \"misread\": false}, ...]} with every item once.")


def setup(d, chain):
    """Env before the bot's modules load: the box's fact state, Bedrock only (`chain`), a gentle pace."""
    os.environ["SWAN_FACTS_PAUSED"] = str(d / "facts_paused.json")
    os.environ["SWAN_FACTS_AUTO"] = str(d / "facts_auto.toml")
    from swan_bot import config
    config.load_env()
    os.environ["LLM_CHAIN"] = chain
    os.environ["LLM_RPM"] = os.environ.get("AB_RPM", "8")       # per model, this process; the live bot paces its own
    return config


def ts(x):
    return dt.datetime.fromisoformat(x["ts"]).timestamp()


def load(d):
    rows = sorted((json.loads(l) for l in open(d / "actions.jsonl")), key=ts)
    accounts = {a["username"]: a for a in json.load(open(d / "accounts_safe.json"))}
    return rows, accounts


def pick(rows, n, seed=50):
    """n live first replies of the last 24 h of the file (one per citizen, current style, no mention, no off-topic),
    and n real citizen replies (their posts that answer someone) from other citizens, as the human baseline."""
    end = ts(rows[-1])
    first = [r for r in rows if r["act"] == "reply" and r.get("style") == "current" and not r.get("mention")
             and r.get("group") in (None, "late") and len(r.get("target_text") or "") >= 40 and end - ts(r) < 86400]
    by_author = {}
    for r in first:
        by_author.setdefault(r["target_author"], r)
    rng = random.Random(seed)
    targets = rng.sample(sorted(by_author.values(), key=ts), min(n, len(by_author)))
    taken = {r["target_author"] for r in targets}
    pool, seen = [], set()
    for r in rows:
        body = re.sub(r"https?://\S+", "", r.get("target_text") or "").strip()
        if r.get("context") and len(body) >= 40 and r["target_author"] not in taken and r["target_author"] not in seen:
            seen.add(r["target_author"])
            pool.append(dict(post=r["context"], reply=body, author=r["target_author"]))
    citizens = rng.sample(pool, min(n, len(pool)))
    return targets, citizens


def job_for(row, rows, accounts, classify):
    """The job the bot would have built for this target, with the memory the box had at that moment."""
    t0 = ts(row)
    before = [r for r in rows if ts(r) < t0]
    ours = {r["post_id"]: r["account_id"] for r in rows if r.get("post_id")}
    rec = dict(accounts.get(row["username"]) or {}, username=row["username"], account_id=row["account_id"],
               persona=(accounts.get(row["username"]) or {}).get("persona") or row["persona"])
    voice = [r.get("clean") or r["text"] for r in before if r["username"] == row["username"]][-50:]
    to_them = [r for r in before if r.get("target_author") == row["target_author"]]
    body = row["target_text"]
    job = dict(mode="reply", rec=rec, frame=row.get("frame_in") or row["frame"], context=row.get("context"),
               target=dict(post_id=row["target_post"], author_id=row["target_author"], body=body,
                           reply_to_post_id=row.get("parent_post")),
               parent_author=ours.get(row.get("parent_post")), source=row.get("source"),
               group="late" if row.get("group") == "late" else None, wants=classify(body)[1],
               target_class=row.get("target_class"),
               memory=dict(spent=(), voice_texts=voice,
                           history=(len(to_them), [(r["username"], (r.get("clean") or r["text"])[:160]) for r in to_them[-2:]])),
               phrase_texts=[r.get("clean") or r["text"] for r in before if r["act"] in ("reply", "reply_back")][-100:],
               same_texts=[r.get("clean") or r["text"] for r in to_them])
    recent = [r.get("clean") or r["text"] for r in before][-300:]
    return job, recent


def set_condition(config, cond):
    config.STYLE_FIXES = cond != "base"
    config.LEAN_PROMPT = cond == "lean"
    config.SWITCHBACK = [s for s in config.SWITCHBACK if s[0] != "arm_style"] + (
        [("arm_style", ["fixes"], config.STYLE_BLOCK_S)] if cond != "base" else [])
    config.ARMS_FREEZE = None


def draft(args):
    d = pathlib.Path(args.dir)
    config = setup(d, DRAFTERS[args.drafter])
    from swan_bot import bot, humanize, llm
    from swan_bot.targeting import classify
    rows, accounts = load(d)
    targets, citizens = pick(rows, args.n)
    (d / "targets.json").write_text(json.dumps(dict(targets=targets, citizens=citizens)))
    out = d / "drafts.jsonl"
    done = {(x["i"], x["cond"]) for x in map(json.loads, open(out))} if out.exists() else set()
    label = (lambda c: c) if args.drafter == "live" else (lambda c: f"{c}@{args.drafter}")
    gen = llm.Generator("")
    print(f"{len(targets)} targets, {len(citizens)} citizen replies; chain {[m for _, m in gen.chain]}", flush=True)
    for i, row in enumerate(targets):
        for cond in CONDITIONS:
            if (i, label(cond)) in done:
                continue
            set_condition(config, cond)
            random.seed(f"{i}:{cond}")
            job, recent = job_for(row, rows, accounts, classify)
            persona, system, user = bot.build_prompt(job, types.SimpleNamespace(headline=None), (), None,
                                                     recent_texts=recent)
            for attempt in range(6):                  # no call made = a model parked on a 429 (the quota is shared
                rejects = []                          # with other runs): wait it out, don't record a false loss
                text, backend, repair = bot.draft_checked(gen, job, system, user, recent,
                                                          on_reject=lambda why, raw, b, rep: rejects.append(why))
                if text or job.get("read_skip") or (job.get("meta") or {}).get("llm_calls"):
                    break
                print(f"[{i:3}/{cond:5}] no call made (parked?), waiting 65 s", flush=True)
                time.sleep(65)
            meta = job.get("meta") or {}
            sent = None
            if text:
                sent, _ = humanize.apply(text, persona.get("hand", persona["key"]), "reply",
                                         target_text=job["target"]["body"] if job.get("fixes") else None,
                                         mirror=bool(job.get("fixes")))
            rec = dict(i=i, cond=label(cond), text=sent, clean=text, backend=backend, skip=job.get("read_skip"),
                       llm_calls=meta.get("llm_calls"), repairs=meta.get("repairs"), fixes=meta.get("fixes"),
                       rejects=rejects, system_chars=len(system), user_chars=len(user), arm_style=meta.get("arm_style"),
                       lean=meta.get("lean"), colour=meta.get("colour"), ask_kind=meta.get("ask_kind"))
            with open(out, "a") as f:
                f.write(json.dumps(rec) + "\n")
            print(f"[{i:3}/{cond:5}] {backend} calls={rec['llm_calls']} rep={rec['repairs']} "
                  f"{'SKIP ' + str(rec['skip']) if rec['skip'] else (sent or 'LOST ' + str(rejects))[:110]!r}", flush=True)
    spend = config.DATA / "llm_spend.json"
    print("spend ledger (local):", spend.read_text() if spend.exists() else "none")


def items_for(d):
    """Every reply to rate: sent (A), the three drafts, the citizens. Ids carry no condition."""
    tg = json.loads((d / "targets.json").read_text())
    drafts = [json.loads(l) for l in open(d / "drafts.jsonl")]
    rng = random.Random(7)
    items, key = [], {}

    def add(cond, i, post, reply):
        iid = f"{rng.randrange(16 ** 6):06x}"
        while iid in key:
            iid = f"{rng.randrange(16 ** 6):06x}"
        key[iid] = dict(cond=cond, i=i)
        items.append(dict(id=iid, post=post[:400], reply=reply[:400]))
    for i, row in enumerate(tg["targets"]):
        add("sent", i, row["target_text"], row["text"])
    for x in drafts:
        if x["text"]:
            add(x["cond"], x["i"], tg["targets"][x["i"]]["target_text"], x["text"])
    for i, c in enumerate(tg["citizens"]):
        add("citizen", i, c["post"], c["reply"])
    return items, key


def parse_ratings(raw):
    m = re.search(r"\{.*\}", raw or "", re.S)
    try:
        return {x["id"]: x for x in json.loads(m.group(0))["items"]} if m else {}
    except (ValueError, KeyError, TypeError):
        return {}


def rate(args):
    d = pathlib.Path(args.dir)
    config = setup(d, RATE_CHAIN)
    from swan_bot import llm
    items, key = items_for(d)
    (d / "key.json").write_text(json.dumps(key))
    out = d / "ratings.jsonl"
    done = {(x["pass"], x["id"]) for x in map(json.loads, open(out))} if out.exists() else set()
    gen = llm.Generator("")
    for p in range(args.passes):
        order = items[:]
        random.Random(1000 + p).shuffle(order)
        for b in range(0, len(order), 10):
            batch = [x for x in order[b:b + 10] if (p, x["id"]) not in done]
            if not batch:
                continue
            user = "\n\n".join(f"Item {x['id']}:\nPost: <<<{x['post']}>>>\nReply: <<<{x['reply']}>>>" for x in batch)
            got, tries = {}, 0
            while tries < 3:
                raw, model = gen.complete(RATER_SYSTEM, f"{user}\n\n{RATER_ASK}", models=[config.SONNET],
                                          temperature=0.3, max_tokens=2500)
                if raw is None:                 # parked (Bedrock's per-minute limit, shared): wait it out, no try spent
                    time.sleep(max(5.0, min(120.0, gen.parked.get(config.SONNET, 0) - time.time() + 1)))
                    continue
                tries += 1
                got = parse_ratings(raw)
                if all(x["id"] in got for x in batch):
                    break
                if raw is None:
                    time.sleep(65)                    # the model is parked on a 429 (quota shared with other runs)
            with open(out, "a") as f:
                for x in batch:
                    if x["id"] in got:
                        f.write(json.dumps(dict(got[x["id"]], id=x["id"], **{"pass": p})) + "\n")
            print(f"pass {p} batch {b // 10}: {sum(x['id'] in got for x in batch)}/{len(batch)}", flush=True)
    spend = config.DATA / "llm_spend.json"
    print("spend ledger (local):", spend.read_text() if spend.exists() else "none")


def boot(pairs, n=4000, seed=3):
    """90% interval of the mean of paired differences."""
    rng = random.Random(seed)
    means = sorted(st.mean(rng.choices(pairs, k=len(pairs))) for _ in range(n))
    return st.mean(pairs), means[int(0.05 * n)], means[int(0.95 * n)]


NAMES_OK = set("I I'm I'd I've I'll Yes No COVID H2D2 K Kingstonia Central Crown Harbour New Haven City Assembly Act "
               "Referendum Year Saturday Sunday Monday Tuesday Wednesday Thursday Friday November October March February "
               "KU GP ID Dolphin Flu Regatta Week Herald Daily The A If But And So Hawthorne".split())


def features(texts, posts=None):
    def f(p):
        return sum(bool(re.search(p, t)) for t in texts) / max(1, len(texts))

    def named(t):
        for s in re.split(r"(?<=[.!?;:])\s+", t):
            if any(w.replace("'s", "") not in NAMES_OK for w in re.findall(r"\b[A-Z][a-z]+(?:'s)?\b", s)[1:]):
                return True
        return False
    out = dict(n=len(texts), len_med=st.median(len(t) for t in texts) if texts else 0,
               ends_q=sum(t.rstrip().endswith("?") for t in texts) / max(1, len(texts)), semicolon=f(";"),
               no_stop=f(r"[A-Za-z0-9]$"), named=sum(map(named, texts)) / max(1, len(texts)),
               you_want=f(r"(?i)^you('re| want| need| are after)"))
    if posts:
        low = [(t, p) for t, p in zip(texts, posts) if len(p) > 30 and p == p.lower()]
        out["lower_match"] = (sum(t == t.lower() for t, _ in low) / len(low)) if low else None
    return out


def report(args):
    d = pathlib.Path(args.dir)
    setup(d, DRAFT_CHAIN)                       # the fact state, before quality loads (the repetition table)
    tg = json.loads((d / "targets.json").read_text())
    drafts = [json.loads(l) for l in open(d / "drafts.jsonl")]
    key = json.loads((d / "key.json").read_text())
    ratings = [json.loads(l) for l in open(d / "ratings.jsonl")]
    per = collections.defaultdict(lambda: collections.defaultdict(list))    # (cond, i) -> metric -> values
    for r in ratings:
        k = key.get(r["id"])
        if not k:
            continue
        cell = per[(k["cond"], k["i"])]
        for m in ("bot", "engage", "shift"):
            try:
                cell[m].append(float(r[m]))
            except (KeyError, TypeError, ValueError):
                pass
        cell["misread"].append(1.0 if r.get("misread") in (True, "true", "True") else 0.0)
    mean = lambda cond, i, m: st.mean(per[(cond, i)][m]) if per[(cond, i)][m] else None
    labels = [c for c in CONDITIONS + tuple(f"{c}@sonnet" for c in CONDITIONS) if any(x["cond"] == c for x in drafts)]
    conds = ("citizen", "sent") + tuple(labels)
    lines = [f"# Style A/B, offline ({dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC)", "",
             f"{len(tg['targets'])} live targets (last 24 h of the box log, one per citizen), {len(tg['citizens'])} real "
             f"citizen replies as the human baseline. Rater: Sonnet 4.6, blind, shuffled, "
             f"{len({r['pass'] for r in ratings})} passes.", "",
             "| set | items | P(bot) | engage | shift (+ = No) | misread |", "|---|---|---|---|---|---|"]
    for c in conds:
        idx = sorted({i for (cc, i) in per if cc == c})
        vals = {m: [mean(c, i, m) for i in idx if mean(c, i, m) is not None] for m in ("bot", "engage", "shift", "misread")}
        lines.append(f"| {c} | {len(idx)} | {st.mean(vals['bot']):.1f} | {st.mean(vals['engage']):.1f} | "
                     f"{st.mean(vals['shift']):+.2f} | {st.mean(vals['misread']):.0%} |" if idx else f"| {c} | 0 | | | | |")
    lines += ["", "Paired against base (same targets), mean difference [90% interval]:", "",
              "| arm | P(bot) | engage | shift | misread | verdict |", "|---|---|---|---|---|---|"]
    verdicts = {}
    sendable = {c: sum(1 for x in drafts if x["cond"] == c and x["text"]) for c in labels}
    for c in ("sent",) + tuple(x for x in labels if x != "base"):
        ref = "base" if "@" not in c else c.split("@")[0]       # a Sonnet set against the same prompt on the live models
        idx = [i for i in range(len(tg["targets"])) if mean(c, i, "bot") is not None and mean(ref, i, "bot") is not None]
        res = {m: boot([mean(c, i, m) - mean(ref, i, m) for i in idx]) for m in ("bot", "engage", "shift", "misread")}
        ok = [res["bot"][2] < 0, res["engage"][1] > -5, res["shift"][1] > -0.15, res["misread"][0] <= 0.05]
        if c != "sent":
            ok.append(sendable[c] >= sendable[ref] - 0.05 * len(tg["targets"]))
            verdicts[c] = all(ok)
        fmt = lambda r, p: f"{r[0]:+.{p}f} [{r[1]:+.{p}f}, {r[2]:+.{p}f}]"
        lines.append(f"| {c} vs {ref} (n={len(idx)}) | {fmt(res['bot'], 1)} | {fmt(res['engage'], 1)} | {fmt(res['shift'], 2)} | "
                     f"{fmt(res['misread'], 2)} | {'PASS' if c in verdicts and verdicts[c] else ('FAIL' if c in verdicts else 'reference')} |")
    lines += ["", "Drafting (what the gate saw):", "", "| arm | sendable | skipped by read | first try ok | mean LLM calls | "
              "prompt chars (system + user) |", "|---|---|---|---|---|---|"]
    for c in labels:
        xs = [x for x in drafts if x["cond"] == c]
        first = sum(1 for x in xs if x["text"] and x["llm_calls"] == 1 and not x["repairs"])
        lines.append(f"| {c} | {sendable[c]}/{len(xs)} | {sum(1 for x in xs if x['skip'])} | {first}/{len(xs)} | "
                     f"{st.mean([x['llm_calls'] or 0 for x in xs]):.2f} | "
                     f"{st.median([x['system_chars'] + x['user_chars'] for x in xs]):.0f} |")
    lines += ["", "Shape (the critique's §3 measures):", "",
              "| set | n | median chars | ends on ? | semicolon | no final stop | names someone | \"You want\" open | "
              "lowercase when they were |", "|---|---|---|---|---|---|---|---|---|"]
    sets = {"citizen": ([c["reply"] for c in tg["citizens"]], None),
            "sent": ([r["text"] for r in tg["targets"]], [r["target_text"] for r in tg["targets"]])}
    for c in labels:
        xs = [x for x in drafts if x["cond"] == c and x["text"]]
        sets[c] = ([x["text"] for x in xs], [tg["targets"][x["i"]]["target_text"] for x in xs])
    for c, (texts, posts) in sets.items():
        f = features(texts, posts)
        lm = f.get("lower_match")
        lines.append(f"| {c} | {f['n']} | {f['len_med']:.0f} | {f['ends_q']:.0%} | {f['semicolon']:.0%} | "
                     f"{f['no_stop']:.0%} | {f['named']:.0%} | {f['you_want']:.0%} | {'' if lm is None else f'{lm:.0%}'} |")
    lines += ["", "Repetition across replies (what Blue reporters and the moderator see; the rater sees one reply at a time):", "",
              "| set | worn phrase | holds one of its 5 commonest 4-word runs | phrase budgets would reject (its own drafts "
              "in sequence) |", "|---|---|---|---|"]
    from swan_bot import quality
    worn = re.compile(r"(?i)" + "|".join(re.escape(w) for w in (
        "locks it in", "locks in", "blank cheque", "signing blank", "binds us", "no review", "end date", "sunset",
        "venue list", "list of places", "after the vote", "nothing in the question")))
    for c, (texts, posts) in sets.items():
        if not texts:
            continue
        tsets = [{" ".join(w[i:i + 4]) for i in range(len(w) - 3)} for w in (re.findall(r"[a-z']+", t.lower()) for t in texts)]
        grams = collections.Counter(g for s in tsets for g in s)
        top = {g for g, _ in grams.most_common(5)}
        over, window = 0, []
        for t, p in zip(texts, posts or [""] * len(texts)):
            over += bool(quality.over_budget(t, window[-quality.PHRASE_WINDOW:], (), quality.echoed(p)))
            window.append(t)
        lines.append(f"| {c} | {sum(bool(worn.search(t)) for t in texts) / len(texts):.0%} | "
                     f"{sum(bool(s & top) for s in tsets) / len(texts):.0%} | {over / len(texts):.0%} |")
    lines += ["", "Gate rejects per arm (first draft failed on, count):", ""]
    for c in labels:
        rj = collections.Counter(w for x in drafts if x["cond"] == c for w in (x["rejects"] or []))
        lines.append(f"- {c}: " + (", ".join(f"{w} {n}" for w, n in rj.most_common(8)) or "none"))
    lines += ["", "Verdicts (criteria in scripts/style_ab.py): " + ", ".join(f"{c} {'PASS' if v else 'FAIL'}" for c, v in verdicts.items())]
    text = "\n".join(lines)
    (d / "report.md").write_text(text)
    print(text)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=("draft", "rate", "report"))
    ap.add_argument("--dir", required=True)
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--passes", type=int, default=2)
    ap.add_argument("--drafter", choices=tuple(DRAFTERS), default="live")
    args = ap.parse_args(argv)
    dict(draft=draft, rate=rate, report=report)[args.cmd](args)


if __name__ == "__main__":
    main()
