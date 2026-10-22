"""The lab's libraries: persona cards (content/lab/personas/*.toml), strategies (content/lab/strategies/*.toml) and the
trial log (data/lab/trials.jsonl). A teammate adds a strategy with one file and a push; the runner queues it.

A strategy file:

    name = "values_as_no"
    author = "marc"
    priority = 2                 # lower runs first
    instruction = "..."          # added to today's reply prompt ("" = today's reply, the Base)
    targets = ["yes_but", ...]   # stance classes it is tried on (default: all)
    style = "current"            # the live reply style: "current" or "mirror_concede"
    seeds = 2                    # optional, default config.LAB_SEEDS
    gate = true                  # the live quality gate and its repairs (false: one draft, safety checks only)
    insert = "mention" | "link"  # optional: code adds the citizen's @handle, or a verified article URL
    drafter = "deepseek.v3.2"    # optional: the one drafting model (config.LAB_DRAFTERS); default the live reply order
    npc_reads = "reply" | "control" | "two_voice"   # what the stand-in reads (default "reply")
    control_text = "..."         # for npc_reads = "control": the unrelated post it reads instead
"""
import hashlib
import json
import threading
import tomllib

from swan_bot import config


def _toml_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    return json.dumps("" if v is None else str(v), ensure_ascii=False)   # a JSON string is a TOML basic string


def dump_toml(d):
    """Flat TOML for a card (strings, numbers, booleans, lists of those)."""
    return "".join(f"{k} = {_toml_value(v)}\n" for k, v in d.items() if v is not None)


def load_dir(path):
    out = []
    for p in sorted(path.glob("*.toml")):
        try:
            d = tomllib.loads(p.read_text())
        except (tomllib.TOMLDecodeError, OSError) as e:
            print(f"lab: skipping {p.name}: {e}")
            continue
        d.setdefault("name", p.stem)
        out.append(d)
    return out


def personas(path=None):
    return load_dir(path or config.LAB_PERSONAS)


def save_persona(card, path=None):
    path = path or config.LAB_PERSONAS
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{card['id']}.toml").write_text(dump_toml(card))


def strategies(path=None):
    out = []
    for s in load_dir(path or config.LAB_STRATEGIES):
        s.setdefault("instruction", "")
        s.setdefault("priority", 5)
        s.setdefault("style", "current")
        s.setdefault("gate", True)
        s.setdefault("npc_reads", "reply")
        s["version"] = version(s)
        out.append(s)
    return sorted(out, key=lambda s: (s["priority"], s["name"]))


def version(s):
    """A strategy's version: editing what it does re-queues its trials; editing its notes doesn't."""
    keys = ("instruction", "style", "gate", "insert", "npc_reads", "control_text", "drafter")
    return hashlib.sha1(json.dumps({k: s.get(k) for k in keys}, sort_keys=True).encode()).hexdigest()[:8]


def trials(name="trials.jsonl"):
    p = config.LAB_DIR / name
    out = []
    if p.exists():
        for line in p.read_text().splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def baselines():
    return trials("baselines.jsonl")


_WRITE = threading.Lock()


def record(row, name="trials.jsonl"):
    config.LAB_DIR.mkdir(parents=True, exist_ok=True)
    with _WRITE, open(config.LAB_DIR / name, "a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def queue(strats, cards, done):
    """[(strategy, card, seed)] not yet run, seed-major (every cell gets seed 0 before any gets seed 1), then by the
    strategy's priority. done: {(strategy name, version, card id, seed)} of finished trials (errors excluded)."""
    out = []
    for s in strats:
        targets = set(s.get("targets") or ())
        for c in cards:
            if targets and c.get("stance_class") not in targets:
                continue
            for seed in range(int(s.get("seeds") or config.LAB_SEEDS)):
                if (s["name"], s["version"], c["id"], seed) not in done:
                    out.append((s, c, seed))
    return sorted(out, key=lambda x: (x[2], x[0]["priority"], x[0]["name"], x[1]["id"]))


def done_keys(rows, lab_model=None):
    """Finished trials on this stand-in model and the current instrument (a new stand-in or rater re-runs the queue
    rather than pooling unlike trials)."""
    from .npc import INSTRUMENT
    return {(t["strategy"], t["version"], t["persona"], t["seed"]) for t in rows
            if not t.get("error") and t.get("instrument") == INSTRUMENT
            and (lab_model is None or t.get("lab_model") == lab_model)}
