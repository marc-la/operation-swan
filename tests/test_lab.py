"""todo/25's NPC lab: the classifier's parsing and letter shuffle, the libraries, the queue and the report. No network."""
import pathlib
import sys
import tomllib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from swan_bot import config  # noqa: E402
from swan_lab import cards, library, npc, report, trials  # noqa: E402


def test_ratings_parse_words_not_letters():
    assert npc.parse_rating("LEAN NO") == 1 and npc.parse_rating("Lean yes.") == -1
    assert npc.parse_rating("NO") == 2 and npc.parse_rating("YES") == -2 and npc.parse_rating("Undecided") == 0
    assert npc.parse_rating("Leaning No") == 1 and npc.parse_rating("I can't tell") is None
    assert npc.verdict(0, 1) == "toward_no" and npc.verdict(1, -1) == "toward_yes" and npc.verdict(2, 2) == "same"
    assert npc.verdict(None, 1) is None


def test_session_splits_the_vaccination_line():
    class Fake:
        model, calls = "competitor", 0

        def ask(self, *a, **kw):
            return "I still want a sunset first.\nVaccination: I'm fine with vaccines."
    card = dict(id="c1", name="T", handle="t", view="Yes if there's a sunset", target_text="sunset please", posts=[])
    view, vax, _ = npc.session(Fake(), card, "a reply", 0)
    assert view == "I still want a sunset first." and vax == "I'm fine with vaccines."


def test_persona_prompt_has_their_words_and_no_live_text():
    card = dict(name="Tessa", handle="tessa", bio="", view="Privacy isn't negotiable.", posts=["Keep data separate."],
                liked=["A liked post"], target_text="x")
    p = npc.persona_prompt(card)
    assert "Privacy isn't negotiable." in p and "Keep data separate." in p and "hard to persuade" in p


def test_toml_cards_round_trip(tmp_path):
    card = dict(id="c9", author_id=9, name='Ana "A" Lee', concerns=["sunset", "kids"], posts=["line\nbreak", "ok"],
                view="It's — fine", built="2026")
    library.save_persona(card, tmp_path)
    back = tomllib.loads((tmp_path / "c9.toml").read_text())
    assert back == card


def test_strategy_versions_and_the_seed_major_queue(tmp_path):
    (tmp_path / "a.toml").write_text('name = "a"\npriority = 2\ninstruction = "x"\ntargets = ["yes_but"]\n')
    (tmp_path / "b.toml").write_text('name = "b"\npriority = 1\ninstruction = "y"\nseeds = 1\n')
    strats = library.strategies(tmp_path)
    assert [s["name"] for s in strats] == ["b", "a"] and strats[0]["gate"] and strats[0]["style"] == "current"
    cs = [dict(id="c1", stance_class="yes_but"), dict(id="c2", stance_class="firm_no")]
    q = [(s["name"], c["id"], seed) for s, c, seed in library.queue(strats, cs, set())]
    assert q[:3] == [("b", "c1", 0), ("b", "c2", 0), ("a", "c1", 0)] and ("a", "c2", 0) not in q
    assert len(q) == 2 + config.LAB_SEEDS
    done = {("b", strats[0]["version"], "c1", 0)}
    assert ("b", "c1", 0) not in [(s["name"], c["id"], seed) for s, c, seed in library.queue(strats, cs, done)]
    edited = dict(strats[0], instruction="changed")
    assert library.version(edited) != strats[0]["version"]                   # an edit re-queues its trials


def test_every_shipped_strategy_loads():
    strats = library.strategies()
    names = {s["name"] for s in strats}
    assert {"control", "base", "news_link", "at_address", "confident", "overclaim"} <= names
    assert next(s for s in strats if s["name"] == "overclaim")["gate"] is False


def test_segment_and_class():
    assert cards.segment(["I'm definitely voting Yes, no question."])[0] == "firm"
    assert cards.segment(["Not sure, leaning Yes unless they publish a sunset."]) == ("hedged", ["sunset"])
    assert cards.class_of("unclear", "hi") == "unsure" and cards.class_of("bogus", "hi") is None


def test_safety_blocks_logistics_and_other_links():
    assert trials.safety("Vote No. Also see http://example.com") == "forbidden_content"
    assert trials.safety("The question has no end date. I'm voting No.") is None


def test_report_ranks_against_control():
    def row(s, v, cls="yes_but"):
        return dict(strategy=s, version="v", verdict=v, stance_class=cls, certainty="plain", concerns=["sunset"],
                    lab_model="competitor", instrument=npc.INSTRUMENT)
    strats = [dict(name="control", version="v"), dict(name="base", version="v"), dict(name="news_link", version="v")]
    rows = ([row("control", "same")] * 9 + [row("control", "toward_yes")] + [row("base", "same")] * 10 +
            [row("news_link", "toward_no")] * 3 + [row("news_link", "same")] * 7)
    md = report.markdown(rows, strats)
    lines = [l for l in md.splitlines() if l.startswith("| news_link")]
    assert lines and "+30" in lines[0] and "+40" in lines[0]                   # net +30, +40 against Control's −10
    assert "| yes_but |" in md and "news_link" in md.split("Movability")[1]


class FakeBackend:
    """A stand-in model that answers, or is down."""
    down = set()

    def __init__(self, name, model_id=None):
        self.name = name

    def ask(self, system, user, max_tokens, temperature, tries):
        if self.name in FakeBackend.down:
            raise RuntimeError(f"stand-in {self.name} unavailable")
        return f"{self.name} ok"


def test_local_falls_back_to_competitor_for_whole_trials_and_comes_back(monkeypatch):
    FakeBackend.down = {"local"}
    si = npc.StandIn("local", backend=FakeBackend)
    assert si.model == "local"
    try:
        si.ask("s", "u")
        raise AssertionError("expected a switch")
    except npc.Switched:
        pass
    assert si.model == "competitor" and si.ask("s", "u") == "competitor ok"
    si.restore()                                                   # too soon: stays on the fallback
    assert si.model == "competitor"
    FakeBackend.down = set()
    si.down_at -= si.RETRY_PRIMARY_S + 1
    si.restore()
    assert si.model == "local" and si.ask("s", "u") == "local ok"


def test_competitor_alone_has_no_fallback():
    FakeBackend.down = {"competitor"}
    si = npc.StandIn("competitor", backend=FakeBackend)
    assert si.fallback is None and not si.up()
    FakeBackend.down = set()


def test_trials_on_another_model_are_not_done_and_not_pooled():
    rows = [dict(strategy="base", version="v", persona="c1", seed=0, lab_model="competitor", verdict="same",
                 instrument=npc.INSTRUMENT)]
    assert library.done_keys(rows, "competitor") == {("base", "v", "c1", 0)}
    assert library.done_keys(rows, "local") == set()
    md = report.markdown(rows + [dict(rows[0], lab_model="local", verdict="toward_no")],
                         [dict(name="base", version="v")])
    assert md.count("# NPC lab results") == 2


def test_the_lab_page_renders_per_model_with_examples(tmp_path):
    import json
    from swan_dash import build
    from swan_dash.lab import gather_lab
    (tmp_path / "content" / "lab" / "strategies").mkdir(parents=True)
    (tmp_path / "content" / "lab" / "strategies" / "base.toml").write_text('name = "base"\ninstruction = ""\n')
    (tmp_path / "content" / "lab" / "strategies" / "control.toml").write_text('name = "control"\nnpc_reads = "control"\n')
    library.save_persona(dict(id="c1", author_id=1, stance_class="yes_but", target_text="Only with a sunset <b>."),
                         tmp_path / "content" / "lab" / "personas")
    strats = {s["name"]: s for s in library.strategies(tmp_path / "content" / "lab" / "strategies")}
    rows = [dict(strategy=n, version=strats[n]["version"], persona="c1", stance_class="yes_but", seed=0,
                 lab_model="competitor", verdict=v, reply="No end date. I'm voting No.", after="Still Yes", voice="lani",
                 instrument=npc.INSTRUMENT)
            for n, v in (("base", "toward_no"), ("control", "same"))]
    (tmp_path / "data" / "lab").mkdir(parents=True)
    (tmp_path / "data" / "lab" / "trials.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    ctx = gather_lab(tmp_path)
    assert [m["model"] for m in ctx["models"]] == ["competitor"]
    base = next(t for t in ctx["models"][0]["table"] if t["name"] == "base")
    assert base["net"] == 100 and base["vs"] == 100 and base["by_class"]["yes_but"] == 100
    html = build.render(dict(ctx, built="09:00"), "lab.html.j2")
    assert "Only with a sunset &lt;b&gt;." in html and "toward_no" in html     # their words, escaped


def test_a_trial_rates_baseline_and_after_with_one_instrument(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LAB_DIR", tmp_path)

    class Fake:
        model, calls = "local:q4", 0

        def ask(self, system, user, **kw):
            self.calls += 1
            if system == npc.RATE_SYSTEM:
                return "LEAN NO" if "convinced" in user else "UNDECIDED"
            return "I'm convinced now." if "replied" in user or "scroll past" in user else "Still thinking."
    card = dict(id="c1", name="T", handle="t", view="Yes if there's a sunset", target_text="sunset please", posts=[],
                stance_class="yes_but")
    strat = dict(name="control", version="v", npc_reads="control", control_text="Nice day.")
    rec = trials.run_trial(strat, card, 0, None, Fake(), None)
    assert (rec["before"], rec["after_score"], rec["verdict"], rec["instrument"]) == (0, 1, "toward_no", npc.INSTRUMENT)
    assert rec["npc_calls"] == 4 and len(library.baselines()) == 1          # baseline: a session and a rating
    rec = trials.run_trial(strat, card, 0, None, Fake(), None)
    assert rec["npc_calls"] == 2 and len(library.baselines()) == 1          # cached for this card, model and seed


def test_paired_shift_against_control_cancels_the_ceiling():
    def r(s, persona, seed, score):
        return dict(strategy=s, persona=persona, seed=seed, after_score=score)
    ctrl = [r("control", "c1", 0, 2), r("control", "c2", 0, 0)]
    rows = [r("base", "c1", 0, 2), r("base", "c2", 0, 1), r("base", "c3", 0, 2)]      # c3 has no control pair
    assert report.shift(rows, ctrl) == (0.5, 2)
    assert report.shift(rows, []) == (None, 0)
