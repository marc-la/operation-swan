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
    post = dict(mode="post", rec=dict(persona="lani"), frame="F1_blank_cheque")    # the broadcast arm's posts too
    bot.build_prompt(post, targeter)
    assert post["meta"]["arm_conv"] == "no_leaners"
    journalist = dict(mode="journalist", rec=dict(persona="lani"), frame="F1_blank_cheque",
                      target=dict(post_id=9, author_id=3, body="The referendum explained"))
    bot.build_prompt(journalist, targeter)
    assert "arm_conv" not in journalist["meta"]
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


def test_replies_no_longer_state_our_vote_and_keep_off_worn_phrases():
    from swan_bot import content
    body = "Only if there's a sunset clause. Otherwise I can't vote Yes."
    prompts = [content.reply_prompt(body, "F14_no_yes_but", [], persona=content.PERSONAS[0], style=s, read=True)
               for s in ("current", "mirror_concede")]
    prompts += [content.second_voice_prompt(body, "F6_islands", [], persona=content.PERSONAS[1]),
                content.reply_back_prompt("ours", body), content.reply_back_prompt("ours", body, style="mirror_concede")]
    for p in prompts:
        assert content.NO_VERDICT_RULE in p and "say plainly that you're voting No" not in p.lower()
        assert "'end date'" in p and "'sunset'" not in p                    # the citizen said sunset first
    assert "plain statement of your No" not in "".join(prompts)
    assert content.worn_line(" ".join(content.WORN_PHRASES)) == ""


def test_fresh_facts_arm_offers_news_that_fits_the_citizen(tmp_path, monkeypatch):
    import datetime as dt
    from swan_bot import content
    from swan_bot import facts as fact_store
    now = dt.datetime.now(dt.timezone.utc)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    old = (now - dt.timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    overlay = tmp_path / "facts_auto.toml"
    overlay.write_text(
        f'[ferry_queue_checks]\ntext = "The ferry company says it has no staff to check passes at the wharf gate."\n'
        f'note = "ferry company has no staff to check passes"\nstatus = "active"\n'
        f'source = "kingstonia-herald/ferry-pass-checks"\nchecked = {stamp}\nadded = {stamp}\nnumbers = []\n'
        f'says = []\nframes = []\n'
        f'[stale_news]\ntext = "An old story about the ferry."\nnote = "old ferry story"\nstatus = "active"\n'
        f'source = "daily-kingstonia/old"\nchecked = {old}\nadded = {old}\nnumbers = []\nsays = []\nframes = []\n')
    monkeypatch.setattr(fact_store, "AUTO_FILE", overlay)
    try:
        picked = content.fresh_facts("Worried about the ferry queue if they check passes at the wharf")
        assert [k for k, _, _ in picked] == ["ferry_queue_checks"]                 # 48 h only, the fitting one
        assert picked[0][2] == "Kingstonia Herald"
        monkeypatch.setattr(config, "SWITCHBACK", [("arm_conv", ["fresh_facts"], 7200)])
        job = job_for(None, body="Worried about the ferry queue if they check passes at the wharf")
        _, _, user = bot.build_prompt(job, types.SimpleNamespace(headline=None))
        assert "New this week in the papers: ferry company has no staff to check passes (Kingstonia Herald)" in user
        assert job["meta"]["fresh"] == ["ferry_queue_checks"] and "fresh" in bot.ARMS
        assert user.index("New this week") < user.index("First read them")         # before the JSON instructions
    finally:
        monkeypatch.undo()
        fact_store.refresh(force=True)


def test_target_order_arm_puts_the_movable_classes_first(monkeypatch):
    import datetime as dt
    from swan_bot import targeting

    def post(pid):
        return dict(post_id=pid, author_id=1000 + pid, body="the referendum",
                    created_at=(dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=30)).isoformat())

    def order(arm):
        monkeypatch.setattr(config, "SWITCHBACK", [("arm_conv", [arm], 7200)])
        monkeypatch.setattr(config, "TURNOUT_ARM", False)
        t = targeting.Targeter(None, log=lambda r: None)
        for pid, cls in ((1, "yes_reason"), (2, "lean_no"), (3, "conditions"), (4, "unsure"), (5, "firm_yes")):
            t._queue(post(pid), "latest", None, None, 0, cls)
        out = []
        while (c := t.next_target(set(), set(), {})) is not None:
            out.append(c["target_class"])
        return out
    assert order("target_order")[:4] == ["unsure", "lean_no", "conditions", "yes_reason"]
    base = order("base")
    assert base.index("lean_no") > base.index("conditions") and base.index("lean_no") > base.index("unsure")
