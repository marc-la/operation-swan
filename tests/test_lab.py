"""todo/25's NPC lab: the classifier's parsing and letter shuffle, the libraries, the queue and the report. No network."""
import pathlib
import sys
import tomllib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from swan_bot import config  # noqa: E402
from swan_lab import cards, library, npc, report, trials  # noqa: E402


def test_letters_are_shuffled_per_trial_and_cover_every_verdict():
    orders = {tuple(npc.letters(seed, "c1").values()) for seed in range(12)}
    assert len(orders) > 1 and all(set(o) == set(npc.VERDICTS) for o in orders)
    assert npc.letters(3, "c1") == npc.letters(3, "c1")


def test_parse_verdict_reads_the_form_and_a_bare_letter():
    order = {"A": "toward_yes", "B": "toward_no", "C": "same"}
    assert npc.parse_verdict("VIEW: B\nVACCINE: P", order) == ("toward_no", "positive")
    assert npc.parse_verdict("view - c\nvaccine: m", order) == ("same", "mixed")
    assert npc.parse_verdict("A", order) == ("toward_yes", None)
    assert npc.parse_verdict("I think it is unclear", order) == (None, None)


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
                    lab_model="competitor")
    strats = [dict(name="control", version="v"), dict(name="base", version="v"), dict(name="news_link", version="v")]
    rows = ([row("control", "same")] * 9 + [row("control", "toward_yes")] + [row("base", "same")] * 10 +
            [row("news_link", "toward_no")] * 3 + [row("news_link", "same")] * 7)
    md = report.markdown(rows, strats)
    lines = [l for l in md.splitlines() if l.startswith("| news_link")]
    assert lines and "+30" in lines[0] and "+40" in lines[0]                   # net +30, +40 against Control's −10
    assert "| yes_but |" in md and "news_link" in md.split("Movability")[1]
