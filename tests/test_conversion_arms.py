"""todo/25: the conversion arms (base, old_models, no_leaners) in 2 h switchback blocks, logged as arm_conv."""
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from swan_bot import bot, config, experiment  # noqa: E402

READ_LEAN_NO = ('{"stance": "lean_no", "doubt": "permanence", "frame": "F1_blank_cheque", "reply": '
                '"Which places count is the whole question, and nobody will say until after the vote. I\'m voting No."}')
READ_UNSURE = READ_LEAN_NO.replace("lean_no", "unsure")


class Gen:
    """Answers each call from a list of drafts and records which models it was allowed."""
    chain = [("bedrock", "moonshotai.kimi-k2.5"), ("gemini", "gemini-3.5-flash-lite"), ("groq", "openai/gpt-oss-120b"),
             ("groq", "qwen/qwen3.8-27b")]

    def __init__(self, drafts, parked=None):
        self.drafts, self.calls, self.parked = list(drafts), [], dict(parked or {})

    def complete(self, system, user, models=None, **kw):
        self.calls.append((models, user))
        allowed = [m for _, m in self.chain if not models or m in models]
        return self.drafts.pop(0), allowed[0]


def job_for(arm_conv, body="Not sure how I'll vote on the referendum yet."):
    return dict(mode="reply", rec=dict(persona="lani"), frame=None, arm=None, wants=[], context=None, read=True,
                meta={"arm_conv": arm_conv}, target=dict(post_id=5, author_id=500, body=body))


def test_the_block_sets_arm_conv_on_citizen_facing_writes_only(monkeypatch):
    monkeypatch.setattr(config, "SWITCHBACK", [("arm_conv", ["no_leaners"], 7200)])
    targeter = types.SimpleNamespace(headline=None)
    job = job_for(None)
    bot.build_prompt(job, targeter)
    assert job["meta"]["arm_conv"] == "no_leaners" and job["meta"]["block_id"].startswith("arm_conv:7200:")
    post = dict(mode="post", rec=dict(persona="lani"), frame="F1_blank_cheque")
    bot.build_prompt(post, targeter)
    assert "arm_conv" not in post["meta"]
    assert "arm_conv" in bot.ARMS                                   # logged on every write


def test_no_switchback_means_base(monkeypatch):
    monkeypatch.setattr(config, "SWITCHBACK", [])
    job = job_for(None)
    bot.build_prompt(job, types.SimpleNamespace(headline=None))
    assert job["meta"]["arm_conv"] == "base" and "block_id" not in job["meta"]


def test_blocks_rotate_through_every_arm():
    seen = {experiment.block("arm_conv", t=h * 3600)[1] for h in range(0, 24, 2)}
    assert seen == set(config.CONV_ARMS)


def test_old_models_arm_drafts_on_the_old_chain():
    gen = Gen([READ_UNSURE])
    text, backend, _ = bot.draft_checked(gen, job_for("old_models"), "sys", "user", [])
    assert text and backend == "gemini-3.5-flash-lite"
    gen = Gen([READ_UNSURE])
    _, backend, _ = bot.draft_checked(gen, job_for("base"), "sys", "user", [])
    assert backend == config.REPLY_MODELS[0]
    order = bot.conv_models(gen, ["moonshotai.kimi-k2.5", "gemini-3.5-flash-lite"])
    assert order == list(config.CONV_OLD_MODELS) + ["moonshotai.kimi-k2.5"]       # the usual order is the fallback


def test_old_models_arm_falls_back_when_all_are_parked():
    gen = Gen([READ_UNSURE], parked={m: 9e12 for m in config.CONV_OLD_MODELS})
    _, backend, _ = bot.draft_checked(gen, job_for("old_models"), "sys", "user", [])
    assert backend == config.REPLY_MODELS[0]


def test_no_leaners_arm_skips_a_lean_no_read():
    gen = Gen([READ_LEAN_NO])
    job = job_for("no_leaners")
    assert bot.draft_checked(gen, job, "sys", "user", [])[0] is None
    assert job["read_skip"] == "arm_conv:lean_no" and job["meta"]["read_stance"] == "lean_no"
    for arm in ("base", "old_models"):                              # the other arms answer them
        job = job_for(arm)
        assert bot.draft_checked(Gen([READ_LEAN_NO]), job, "sys", "user", [])[0]
    job = job_for("no_leaners")                                     # and no_leaners answers everyone else
    assert bot.draft_checked(Gen([READ_UNSURE]), job, "sys", "user", [])[0]
