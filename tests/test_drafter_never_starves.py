"""23 Oct: replies stopped for hours when the day's allowance was down to the amplified-post reserve and every free model
was parked. A draft that no model answers is now retried once with the reserve (todo/34 item 5). No network."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from swan_bot import bot, config, llm  # noqa: E402

KIMI = "moonshotai.kimi-k2.5"


class ReserveGen:
    """Answers only a call that may spend the reserve (priority), like Generator.complete with the day's allowance spent
    down to the reserve and the free models parked."""
    chain = [("bedrock", KIMI), ("groq", "openai/gpt-oss-120b")]

    def __init__(self, answers=True):
        self.priorities, self.answers = [], answers

    def complete(self, system, user, models=None, priority=False, **kw):
        self.priorities.append(priority)
        return ("a draft", KIMI) if priority and self.answers else (None, None)


def draft(gen, job, monkeypatch):
    monkeypatch.setattr(bot.quality, "check", lambda raw, *a, **kw: (raw, None))
    return bot.draft_checked(gen, dict(job, meta={}), "sys", "user", [])


def test_a_reply_nobody_answers_is_retried_with_the_reserve(monkeypatch):
    gen = ReserveGen()
    text, backend, _ = draft(gen, dict(mode="reply"), monkeypatch)
    assert (text, backend) == ("a draft", KIMI)
    assert gen.priorities[0] is False and gen.priorities[-1] is True, "first the normal order, then the reserve"


def test_a_plain_post_too_and_an_amplified_post_needs_no_retry(monkeypatch):
    gen = ReserveGen()
    assert draft(gen, dict(mode="post"), monkeypatch)[0] == "a draft"
    gen = ReserveGen()
    assert draft(gen, dict(mode="post", amp=True), monkeypatch)[0] == "a draft"
    assert gen.priorities == [True], "amplified posts may spend the reserve from the start"


def test_nothing_answers_even_the_reserve_loses_the_draft_after_one_reserve_pass(monkeypatch):
    gen = ReserveGen(answers=False)
    text, backend, _ = draft(gen, dict(mode="reply"), monkeypatch)
    assert text is None and backend is None
    assert gen.priorities.count(True) == gen.priorities.count(False) >= 1, "one reserve pass, no more"


def test_qwen_plus_character_is_out_of_the_chain_and_the_amp_models():
    """Alibaba's free quota is spent (403 'free quota has been exhausted' on 23 Oct); Marc: leave it out."""
    live = [line.split("#")[0].strip() for line in llm.CHAIN_FILE.read_text().splitlines()]
    assert not any("qwen-plus-character" in line for line in live)
    assert "qwen-plus-character" not in config.AMP_MODELS
