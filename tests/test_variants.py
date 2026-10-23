"""Variants of persona cards (variants.py, todo/38): 200 variants over all 32 cards (20 live + 12 staged) obey the
content rules, spread their handle shapes, never collide, differ in hand, are deterministic given a seed, leave the base
cards alone and reach prompts only through bot.persona_of.

    python -m pytest tests/test_variants.py -q
"""
import copy
import json
import pathlib
import random
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from swan_bot import bot, content, humanize, variants as V  # noqa: E402
from swan_bot.playbook import characters  # noqa: E402
from test_characters import ALLOWED_NUMBERS, BANNED, HAWTHORNE_OK  # noqa: E402

N = 200
WINDOW = 45                  # accounts alive at once in the simulation (the real cap is 49 with swarm and Blue besides)
CARDS = V.default_cards()
KEYS = sorted(CARDS)


AGE_WORDS = re.compile(r"\b(" + "|".join(sorted((V.age_words(a) for a in range(16, 91) if a not in V._TENS),
                                               key=len, reverse=True)) + r")\b")


def simulate(n=N, seed=2610, keys=None, window=WINDOW):
    """Register n variants one after another over the cards (round robin): the records as the pool would hold them.
    Once `window` are alive the oldest is suspended by the platform, so a name or a hand is shared only by voices that
    lived at the same time."""
    rng, records = random.Random(seed), []
    keys = keys or KEYS
    for i in range(n):
        key = keys[i % len(keys)]
        v = V.make_variant(key, records, rng, cards=CARDS)
        taken = {r["username"] for r in records}
        user = V.username_for(v["handle"], rng, taken)
        records.append(dict(persona=key, username=user, display_name=v["name"], status="active", role="voice",
                            created=f"2026-10-23T{i // 60:02d}:{i % 60:02d}:00", variant=v))
        alive = [r for r in records if r["status"] == "active"]
        if len(alive) > window:
            alive[0]["status"] = "suspended"
    return records


@pytest.fixture(scope="module")
def pool():
    return simulate()


def overlaid(rec):
    return V.persona(rec, cards=CARDS)


def test_thirty_two_cards_live_and_staged():
    assert len(CARDS) == 32 and set(CARDS) >= set(content.PERSONA_BY_KEY)
    assert all(c.get("hand") and c.get("people") and c.get("age") for c in CARDS.values())


def test_two_hundred_variants_pass_every_check(pool):
    assert len(pool) == N
    bad = [(r["username"], r["variant"]["checks"]) for r in pool if r["variant"]["checks"]]
    assert not bad, bad[:5]
    for r in pool:
        if r["status"] == "active":
            ok, why = V.distinct(r["variant"], pool, cards=CARDS)
            assert ok, (r["username"], why)
    assert sum(r["status"] == "active" for r in pool) == WINDOW


def test_forty_nine_alive_at_once_is_clean():
    records = simulate(49, seed=3, window=49)
    assert not [r["username"] for r in records if r["variant"]["checks"]]

def test_schema(pool):
    for r in pool:
        v = r["variant"]
        assert v["v"] == V.VERSION and v["base"] == r["persona"] and v["shape"] in V.SHAPES
        assert isinstance(v["age"], int) and 16 <= v["age"] <= 90
        assert set(v["hand"]) == set(humanize.HANDS["lani"]) and v["hand"]["device"] in ("phone", "tablet", "laptop")
        assert set(v["use"]) == {"details", "people", "lines", "now"}
        assert all(isinstance(i, int) for idx in v["use"].values() for i in idx)
        assert all(isinstance(k, str) and isinstance(x, str) for k, x in v["swap"].items())
        assert v["name"].startswith(v["first"]) and v["style_of"] in (None, *CARDS)
        json.dumps(v)                                       # a plain record field


def test_overlay_obeys_the_character_rules(pool):
    persona_names = {c["name"].split()[0].lower() for c in CARDS.values()} | {"dan"}
    base_owner = {}
    for key, c in CARDS.items():                            # the cards' own people, so no variant shares one
        for person in c["people"]:
            base_owner.setdefault(person.split(",")[0].strip(), key)
    for i, r in enumerate(pool):
        p = overlaid(r)
        owner = {person.split(",")[0].strip(): pool[j]["username"] for j in range(max(0, i - WINDOW), i)
                 for person in overlaid(pool[j])["people"]}
        profile = [p["problem"], p["covid"], p.get("arc") or ""] + p["people"] + p["lines"] + p["now"]
        for t in profile + [p["role"]] + p["details"]:
            hit = BANNED.search(HAWTHORNE_OK.sub("", t))
            assert not hit, (r["username"], hit.group(0), t)
        for t in profile:                                   # test_characters' number rule is on the profile text
            for num in re.findall(r"\d[\d,.]*\d|\d", t.replace("Year 8", "")):
                assert num in ALLOWED_NUMBERS, (r["username"], num, t)
        assert all(len(s.split()) <= 25 for s in p["lines"]), r["username"]
        assert len(p["lines"]) >= 3 and len(p["people"]) >= 2 and len(p["now"]) >= 4 and len(p["details"]) >= 2
        for person in p["people"]:
            name = person.split(",")[0].strip()
            assert name and name[0].isupper(), (r["username"], person)
            assert not ({w.lower() for w in name.split()} & persona_names), (r["username"], name)
            assert name not in owner and name not in base_owner, (name, r["username"])


def test_people_names_never_shared_between_voices(pool):
    skip = {"Mr", "Mrs", "Dr", "Old", "Uncle", "Aunty", "Nana", "Nurse", "Coach", "Captain", "Miss", "Ms", "The"}
    toks = [{t for person in overlaid(r)["people"] for t in re.findall(r"\b[A-Z][\w'-]+", person.split(",")[0])} - skip
            for r in pool]
    for i, mine in enumerate(toks):
        for j in range(max(0, i - WINDOW), i):
            assert not mine & toks[j], (mine & toks[j], pool[i]["username"], pool[j]["username"])


def test_old_people_and_own_name_are_gone(pool):
    for r in pool[:80]:
        base, p = CARDS[r["persona"]], overlaid(r)
        blob = " ".join([p["problem"] or "", p["covid"] or "", p.get("arc") or ""] + p["people"] + p["lines"] + p["now"] + p["details"])
        assert not re.search(rf"\b{re.escape(base['name'].split()[0])}\b", blob), (r["persona"], base["name"])
        for person in base["people"]:
            p0 = V.parse_person(person)
            for old in (p0["first"], p0["last"] if p0["last"] and " " not in p0["last"] else None):
                if old:
                    assert not re.search(rf"(?<![\w']){re.escape(old)}(?!\w)", blob), (r["persona"], old)


def test_handle_shapes_cover_eight_and_never_repeat_in_a_row(pool):
    shapes = [V.shape_of(r) for r in pool]
    assert len(set(shapes)) >= 8 and set(shapes) <= set(V.SHAPES)
    assert all(a != b for a, b in zip(shapes, shapes[1:]))
    alive = [V.shape_of(r) for r in pool if r["status"] == "active"]
    hist = {s: alive.count(s) for s in V.SHAPES}
    assert max(hist.values()) - min(hist.values()) <= 3, hist       # the pool's histogram stays flat


def test_shape_differs_from_the_suspended_account_being_replaced():
    records = simulate(40)
    for key in KEYS[:12]:
        last = [r for r in records if r["persona"] == key][-1]
        last["status"] = "suspended"
        rng = random.Random(7)
        for _ in range(5):
            v = V.make_variant(key, records, rng, cards=CARDS)
            assert v["shape"] != V.shape_of(last), (key, v["shape"])


def test_usernames_unique_valid_and_never_a_seen_one(pool):
    users = [r["username"] for r in pool]
    assert len(set(users)) == len(users)
    handles = {c["handle"] for c in CARDS.values()}
    for u in users:
        assert re.fullmatch(r"[a-z][a-z0-9_]{2,31}", u), u
        assert u not in handles
    assert all(r["variant"]["handle"].lower().rstrip("0123456789") != "" for r in pool)


def test_username_for_appends_two_digits_caps_and_avoids_taken():
    rng = random.Random(1)
    u = V.username_for("tess_aumua", rng)
    assert re.fullmatch(r"tess_aumua\d\d", u)
    assert V.username_for("kauri88", rng) == "kauri88"                      # word_digits: the handle is the username
    assert len(V.username_for("a" * 40, rng)) <= 32
    taken = {f"tess_aumua{n}" for n in range(10, 100)}
    u = V.username_for("tess_aumua", rng, taken)
    assert u not in taken and len(u) <= 32 and u.startswith("tess_aumua")
    assert V.username_for("kauri88", rng, {"kauri88"}) != "kauri88"
    assert V.username_for("tess", random.Random(3)) == V.username_for("tess", random.Random(3))


def test_hands_differ_pairwise_and_from_their_base(pool):
    hands = [(r["username"], r["variant"]["hand"]) for r in pool]
    for i, (a, ha) in enumerate(hands):
        assert V.hand_distance(ha, CARDS[pool[i]["persona"]]["hand"]) >= V.EPS_HAND, a
        for b, hb in hands[max(0, i - WINDOW):i]:
            assert V.hand_distance(ha, hb) >= V.EPS_HAND, (a, b)
    for r in pool:                                          # a sane band: probabilities in range, device in family
        h, base = r["variant"]["hand"], CARDS[r["persona"]]["hand"]
        assert all(0.0 <= h[k] <= 1.0 for k in V.PROB_KEYS)
        assert h["careful"] >= 0.1 and h["slip"] <= 0.3
        assert h["device"] in V._FAMILY[base["device"]] or r["variant"]["style_of"]


def test_age_is_the_cards_plus_or_minus_six_never_equal(pool):
    for r in pool:
        base = CARDS[r["persona"]]["age"]
        age = r["variant"]["age"]
        assert age != base and abs(age - base) <= V.AGE_BAND and 16 <= age <= 90, (r["persona"], base, age)
    wally = next(r for r in pool if r["persona"] == "wally")                 # "seventy-four" in the role follows the age
    p = overlaid(wally)
    assert V.age_words(wally["variant"]["age"]) in p["role"] and "seventy-four" not in p["role"]


def test_use_differs_from_the_card_in_at_least_two_ways(pool):
    for r in pool:
        assert V.use_diff(r["variant"]["use"], CARDS[r["persona"]]) >= 2, r["persona"]


def test_seeded_determinism():
    records = simulate(12)
    a = V.make_variant("vika", records, random.Random(99), cards=CARDS)
    b = V.make_variant("vika", records, random.Random(99), cards=CARDS)
    c = V.make_variant("vika", records, random.Random(100), cards=CARDS)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True) != json.dumps(c, sort_keys=True)
    assert json.dumps(simulate(10, seed=5), sort_keys=True) == json.dumps(simulate(10, seed=5), sort_keys=True)
    assert V.make_variant("vika", records, 99, cards=CARDS) == V.make_variant("vika", records, 99, cards=CARDS)


def test_base_card_frames_role_place_unchanged_and_nothing_shared_is_mutated(pool):
    before = (copy.deepcopy(content.PERSONA_BY_KEY), copy.deepcopy(characters.CHARACTERS), copy.deepcopy(humanize.HANDS),
              copy.deepcopy(CARDS))
    for r in pool:
        base, p = CARDS[r["persona"]], overlaid(r)
        assert p["frames"] == base["frames"] and p["place"] == base["place"] and p["register"] == base["register"]
        assert p["key"] == base["key"] and p["handle"] == base["handle"]
        age_free = lambda s: AGE_WORDS.sub("#", s)
        assert age_free(p["role"]) == age_free(base["role"]), r["persona"]
        for f in ("problem", "covid"):                        # the argument is the card's (names aside)
            assert len((p[f] or "")) > 0 or not base[f]
        assert p["name"] == r["variant"]["name"] and p["name"] != base["name"]
        assert p["hand"] == r["variant"]["hand"] and p["hand"] is not r["variant"]["hand"]
    assert before == (content.PERSONA_BY_KEY, characters.CHARACTERS, humanize.HANDS, CARDS)


def test_style_of_takes_the_voice_line_and_keeps_the_register(pool):
    styled = [r for r in pool if r["variant"]["style_of"]]
    assert styled
    for r in styled:
        s, base = CARDS[r["variant"]["style_of"]], CARDS[r["persona"]]
        assert s["register"] == base["register"] and s["key"] != base["key"]
        assert overlaid(r)["voice"] == s["voice"]
    assert all(overlaid(r)["voice"] == CARDS[r["persona"]]["voice"] for r in pool if not r["variant"]["style_of"])


def test_retries_are_bounded(monkeypatch):
    calls = []
    real = V._check
    monkeypatch.setattr(V, "_check", lambda v, ctx: (calls.append(1), (False, ["forced"]))[1])
    v = V.make_variant("vika", [], random.Random(1), cards=CARDS)
    assert v["checks"] == ["forced"] and len(calls) <= V.MAX_TRIES * 8
    monkeypatch.setattr(V, "_check", real)
    monkeypatch.setattr(V, "MAX_TRIES", 3)
    # a pool that cannot be satisfied: every hand within epsilon (a huge epsilon), the call still returns
    monkeypatch.setattr(V, "EPS_HAND", 99.0)
    v = V.make_variant("vika", [], random.Random(1), cards=CARDS)
    assert v["checks"] and v["handle"] and v["name"]


def test_logs_a_warning_when_no_candidate_is_clean(monkeypatch, caplog):
    monkeypatch.setattr(V, "EPS_HAND", 99.0)
    monkeypatch.setattr(V, "MAX_TRIES", 2)
    with caplog.at_level("WARNING", logger="swan.variants"):
        V.make_variant("tess", [], random.Random(2), cards=CARDS)
    assert "no clean candidate" in caplog.text


def test_distinct_catches_what_it_should():
    records = simulate(6)
    v = copy.deepcopy(records[0]["variant"])
    other = copy.deepcopy(records[1]["variant"])
    ok, why = V.distinct(other, [records[0]], cards=CARDS)
    assert ok, why
    probe = copy.deepcopy(other)
    probe.update(age=CARDS[probe["base"]]["age"])
    assert any(w == "age" for w in V.distinct(probe, records[:1], cards=CARDS)[1])
    probe = copy.deepcopy(other)
    probe["hand"] = dict(CARDS[probe["base"]]["hand"])
    assert "hand_close_to_base" in V.distinct(probe, [], cards=CARDS)[1]
    probe = copy.deepcopy(other)
    probe["hand"] = dict(v["hand"])
    assert any(w.startswith("hand_close:") for w in V.distinct(probe, records[:1], cards=CARDS)[1])
    probe = copy.deepcopy(other)
    probe["name"], probe["first"] = v["name"], v["first"]
    why = V.distinct(probe, records[:1], cards=CARDS)[1]
    assert "name_near" in why and "first_name_taken" in why
    probe = copy.deepcopy(other)
    probe["swap"] = dict(v["swap"])
    assert any(w.startswith("people_shared:") for w in V.distinct(probe, records[:1], cards=CARDS)[1])
    probe = copy.deepcopy(other)
    probe["handle"] = records[0]["variant"]["handle"] + "x"
    assert any(w.startswith("handle_near") for w in V.distinct(probe, records[:1], cards=CARDS)[1])
    probe = copy.deepcopy(other)
    probe["use"] = {f: sorted(range(len(CARDS[probe["base"]][f]))) for f in ("details", "people", "lines", "now")}
    assert "use_same" in V.distinct(probe, [], cards=CARDS)[1]


def test_never_reuses_a_suspended_username_or_a_near_one():
    records = simulate(30)
    for r in records:
        r["status"] = "suspended"
    seen = {r["username"] for r in records}
    rng = random.Random(8)
    for key in KEYS:
        v = V.make_variant(key, records, rng, cards=CARDS)
        u = V.username_for(v["handle"], rng, seen)
        assert u not in seen and not v["checks"]
        records.append(dict(persona=key, username=u, display_name=v["name"], status="suspended", variant=v))
        seen.add(u)


def test_name_pools_are_big_fictional_and_clean():
    firsts, lasts = V.FIRST_F + V.FIRST_M + V.FIRST_U, V.LAST
    assert len(set(firsts)) * len(set(lasts)) >= 200 * 10
    assert all(re.fullmatch(r"[A-Za-z]+", n) for n in firsts + lasts)
    low = {n.lower() for n in firsts + lasts}
    assert not low & V.DENY_TOKENS
    blocked = V._blocked_tokens(CARDS, [])
    free_f = [n for n in firsts if n.lower() not in blocked]
    free_l = [n for n in lasts if n.lower() not in blocked]
    assert len(free_f) * len(free_l) >= 200 and len(free_f) >= 60
    assert not {(a.lower(), b.lower()) for a in firsts for b in lasts} & V.DENY_FULL


def test_pure_module_has_no_network_or_llm():
    src = pathlib.Path(V.__file__).read_text()
    assert not re.search(r"^\s*(from|import)\s+(openai|requests|urllib|http|socket|capturethenarrative|ctn)\b", src, re.M)
    assert not re.search(r"\bllm\b|\.post\(|\.get\(\"http", src.replace("Never raises", ""))


# ---- through bot.persona_of
OLD_CONVERTED_PERSONA_OF = '''
def old(rec):
    card = content.PERSONA_BY_KEY[rec["persona"]]
    conv = rec.get("converted")
    if not conv:
        return card
    style = content.PERSONA_BY_KEY.get(conv.get("style_of")) or card
    names = {w for x in card.get("people") or [] for w in re.findall(r"\\b[A-Z][\\w'-]+", x.split(",")[0])} - bot._TITLES
    named = re.compile(r"\\b(" + "|".join(map(re.escape, sorted(names))) + r")\\b") if names else None
    clean = lambda t: t if t and not (named and named.search(t)) else None
    return dict(card, name=rec.get("display_name") or card["name"], voice=style["voice"],
                register=style.get("register", card.get("register")), hand=style["key"],
                people=[], lines=[], now=[], arc=None, details=[d for d in card["details"] if clean(d)],
                covid=clean(card.get("covid")), problem=clean(card.get("problem")))
'''


def test_persona_of_without_a_variant_is_what_it_was():
    ns = dict(content=content, re=re, bot=bot)
    exec(OLD_CONVERTED_PERSONA_OF, ns)
    old = ns["old"]
    keys = [p["key"] for p in content.PERSONAS]
    assert len(keys) == 20
    for k in keys:
        rec = dict(persona=k, username=f"u_{k}", status="active")
        assert bot.persona_of(rec) is content.PERSONA_BY_KEY[k]                       # the card itself, as before
        assert json.dumps(bot.persona_of(rec), sort_keys=True) == json.dumps(old(rec), sort_keys=True)
        rec = dict(rec, display_name="Some Name", converted=dict(by="marc", style_of=keys[(keys.index(k) + 1) % 20]))
        assert json.dumps(bot.persona_of(rec), sort_keys=True) == json.dumps(old(rec), sort_keys=True)
        assert "variant" not in bot.persona_of(rec)


def test_persona_of_with_a_variant_is_the_overlay_and_leaves_the_card_alone(pool):
    live = [r for r in pool if r["persona"] in content.PERSONA_BY_KEY][:25]
    snap = copy.deepcopy(content.PERSONA_BY_KEY)
    for r in live:
        p = bot.persona_of(r)
        assert p["name"] == r["variant"]["name"] and p["hand"] == r["variant"]["hand"]
        assert p is not content.PERSONA_BY_KEY[r["persona"]]
    assert snap == content.PERSONA_BY_KEY


def test_staged_card_variant_works_through_persona_of(pool):
    staged = [r for r in pool if r["persona"] not in content.PERSONA_BY_KEY]
    assert staged
    p = bot.persona_of(staged[0])
    assert p["key"] == staged[0]["persona"] and p["name"] == staged[0]["variant"]["name"]


def test_the_variants_hand_reaches_humanize_the_way_the_bot_passes_it(pool):
    r = next(r for r in pool if r["persona"] == "isla")
    p = bot.persona_of(r)
    arg = p.get("hand", p["key"])                              # bot.py's expression
    assert isinstance(arg, dict)
    text = "I don't think we can say that it is fine, but I can't see why. We shouldn't need papers to buy bread."
    outs = {humanize.apply(text, arg, "post", random.Random(s))[0] for s in range(40)}
    assert all(isinstance(o, str) and o for o in outs)
    # a dict equal to a card's own hand types exactly as the key does
    for s in range(20):
        assert humanize.apply(text, dict(humanize.HANDS["isla"]), "post", random.Random(s)) == \
               humanize.apply(text, "isla", "post", random.Random(s))


@pytest.mark.parametrize("key", ["lani", "josh", "wally", "ruth", "vika", "tess", "bernie", "dev"])
def test_prompts_carry_the_variants_name_not_the_bases(key):
    records = simulate(8, seed=11, keys=[key])
    rec = records[-1]
    base = CARDS[key]
    p = bot.persona_of(rec)
    first = base["name"].split()[0]
    old_people = {w for person in base["people"] for w in re.findall(r"\b[A-Z][a-z][\w'-]+", person.split(",")[0])} \
        - {"Mr", "Mrs", "Old", "Uncle", "Aunty", "Nana", "Dr", "Nurse", "Captain", "Coach"}
    random.seed(4)
    for frame in list(content.FRAMES)[:6]:
        for _ in range(12):
            s = content.system_prompt(p, frame)
            assert f"You are {rec['variant']['name']}" in s
            assert not re.search(rf"\b{re.escape(first)}\b", s), (key, first)
            assert base["name"] not in s
            assert not any(re.search(rf"\b{re.escape(w)}\b", s) for w in old_people if w not in content.world()), (key, old_people)
            assert f", {rec['variant']['age']} (" in s
