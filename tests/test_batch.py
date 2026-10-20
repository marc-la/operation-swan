"""Offline tests for batched drafting (src/swan_bot/batch.py): no network, a fake model answers.

    python -m pytest tests/test_batch.py -q
"""
import json
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from swan_bot import batch, content  # noqa: E402

P = {p["key"]: p for p in content.PERSONAS}
REPLY_A = ("I'd want an end date too. A Yes is binding and the ballot question has no finish date, so nobody can "
           "promise it stops. That's why I'm voting No.")
REPLY_B = ("The list of places isn't written yet; it comes by regulation after the vote, so a Yes signs off on "
           "venues none of us has seen.")


def reply_job(persona, body, frame="F14_no_yes_but"):
    return dict(mode="reply", rec={"persona": persona}, frame=frame, wants=[], context=None,
                target={"post_id": hash(body) % 10000, "author_id": 999, "body": body})


class FakeGen:
    """Answers each item by looking up its persona in `answers` (persona key -> (their_point, text))."""

    def __init__(self, answers, cut=None):
        self.answers, self.cut, self.calls = answers, cut, 0
        self.last_finish = "stop"

    def complete(self, system, user, json_mode=False, schema=None, models=None, reasoning=None, **kw):
        self.calls += 1
        items = []
        for block in user.split("=== Item ")[1:]:
            label = block[0]
            key = next(k for k, p in P.items() if f"Write as {p['name']}," in block)
            point, text = self.answers[key]
            items.append({"id": label, "their_point": point, "text": text})
        raw = json.dumps({"items": items})
        return (raw[:self.cut] if self.cut else raw), "fake"


def test_pack_one_mode_shuffled_and_rules_once():
    jobs = [reply_job("lani", "need an end date first"), reply_job("josh", "which places are on the list?"),
            reply_job("ana", "hospitals are stretched")]
    p = batch.pack(jobs, rng=random.Random(1))
    assert p.labels == ["A", "B", "C"]
    assert content.REPLY_RULES in p.system and content.REPLY_RULES not in p.user      # hoisted, said once
    assert p.user.count("=== Item") == 3
    assert {j["rec"]["persona"] for j in p.jobs} == {"lani", "josh", "ana"}
    assert p.schema["properties"]["items"]["items"]["properties"]["id"]["enum"] == ["A", "B", "C"]
    orders = {tuple(j["rec"]["persona"] for j in batch.pack(jobs, rng=random.Random(s)).jobs) for s in range(20)}
    assert len(orders) > 1                                                             # shuffled


def test_pack_refuses_mixed_modes():
    post = dict(mode="post", rec={"persona": "ben"}, frame="F5_not_here_yet")
    try:
        batch.pack([post, reply_job("lani", "x")])
    except ValueError:
        return
    raise AssertionError("mixed modes must be refused")


def test_unpack_salvages_cut_off_answer():
    raw = json.dumps({"items": [{"id": "A", "their_point": "x", "text": "first"},
                                {"id": "B", "their_point": "y", "text": "second"}]})
    assert batch.unpack(raw, ["A", "B"]) == {"A": ("x", "first"), "B": ("y", "second")}
    assert batch.unpack(raw[:-30], ["A", "B"]) == {"A": ("x", "first")}
    assert batch.unpack("```json\n" + raw + "\n```", ["A", "B"])["B"] == ("y", "second")
    assert batch.unpack('{"items": [{"id": "Z", "their_point": "", "text": "t"}]}', ["A"]) == {}


def test_points_at_catches_mixup():
    mine, other = "We need a sunset clause and an end date", "Which venues are on the list?"
    assert batch.points_at("wants an end date", mine, [other])
    assert not batch.points_at("which venues on the list", mine, [other])


def test_bleeds():
    assert batch.bleeds("Ben's tuna sold out at the market", "lani", ["lani", "ben"])
    assert batch.bleeds("up before dawn on the boat with the tuna", "lani", ["lani", "ben"])
    assert not batch.bleeds("flat whites by the wharf", "lani", ["lani", "ben"])
    assert not batch.bleeds("that's the plain truth", "ana", ["ana", "ruth"])


def test_drafter_checks_each_item_and_drops_mixups():
    jobs = [reply_job("lani", "I'd vote yes but only with an end date"),
            reply_job("josh", "Which places would be on the list? Nobody has said")]
    gen = FakeGen({"lani": ("wants an end date", REPLY_A),
                   "josh": ("wants an end date", REPLY_B)})       # josh's point drifted onto lani's post
    res = {r["job"]["rec"]["persona"]: r for r in batch.Drafter(gen, size=4).draft(jobs)}
    assert res["lani"]["text"] and res["lani"]["batch_size"] == 2
    assert res["josh"]["text"] is None and res["josh"]["why"] == "mixup"
    assert gen.calls == 1


def test_drafter_splits_unparseable_batch_once():
    jobs = [reply_job("lani", "end date first"), reply_job("josh", "which places on the list")]

    class Broken(FakeGen):
        def complete(self, *a, **kw):
            if self.calls == 0:
                self.calls += 1
                return "sorry, no", "fake"
            return super().complete(*a, **kw)

    gen = Broken({"lani": ("end date", REPLY_A), "josh": ("places list", REPLY_B)})
    res = batch.Drafter(gen, size=4).draft(jobs)
    assert gen.calls == 3 and [r["batch_size"] for r in res] == [1, 1]


def test_desk_pool_ttl_and_ready():
    jobs = [reply_job("lani", "end date first")]
    gen = FakeGen({"lani": ("end date", REPLY_A)})
    ready = {"ok": False}
    desk = batch.Desk(batch.Drafter(gen, size=4), ready=lambda rec, t: ready["ok"])
    assert desk.fill(jobs, []) == []
    assert desk.take("reply", 0) is None and len(desk.pool) == 1              # account not free yet: kept
    ready["ok"] = True
    t0 = desk.pool[0]["drafted_at"]
    assert desk.take("reply", t0 + 21 * 60) is None and desk.pool == []      # 21 min old: dropped
    desk.fill(jobs, [])
    assert desk.take("reply", desk.pool[0]["drafted_at"] + 60)["text"] == REPLY_A
