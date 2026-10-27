"""Shared test setup. The fact desk's runtime pauses (data/facts_paused.json) live on the box that runs the bot, and
deploy/check.sh runs these tests there: point the fact store at a file that doesn't exist, so a live pause can't
change what the tests see (tests that need a pause write their own, see tests/test_facts.py)."""
import os

os.environ["SWAN_FACTS_PAUSED"] = "/nonexistent/swan-tests/facts_paused.json"
# the desk's overlay (todo/29): the same, except when the desk itself runs tests/test_facts.py on a candidate overlay
# (factdesk.run_facts_tests sets SWAN_FACTS_AUTO_CHECK)
os.environ["SWAN_FACTS_AUTO"] = os.environ.get("SWAN_FACTS_AUTO_CHECK") or "/nonexistent/swan-tests/facts_auto.toml"

import pathlib  # noqa: E402
import sys  # noqa: E402

import pytest  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import _budget_stub  # noqa: E402,F401  swan_bot.budget (todo/39) until it is merged: the dashboard imports it


@pytest.fixture(autouse=True)
def _no_live_switch_files(monkeypatch, tmp_path):
    """The box's live switch and account files (AMPLIFY_OFF, secrets/*_accounts.json) must not change what the tests
    see: since 2026-10-22 check.sh runs the suite on the box before every deploy, and AMPLIFY_OFF there failed
    test_amplify for everyone. Tests that need one of these files set their own after this."""
    from swan_bot import config
    monkeypatch.setattr(config, "AMP_OFF_FILE", tmp_path / "AMPLIFY_OFF")
    monkeypatch.setattr(config, "LEAD_HAIKU_SHARE", 0)       # the random lead model: tests that want it set it
    monkeypatch.setattr(config, "ACCOUNTS_FILE", tmp_path / "swan_accounts.json")
    monkeypatch.setattr(config, "SWARM_ACCOUNTS_FILE", tmp_path / "swarm_accounts.json")
    monkeypatch.setattr(config, "PORTAL_FILE", tmp_path / "portal.json")      # todo/40: the box's own portal.json marks no test account
    # watch.py binds its own copies at import: the account-budget job read the laptop's real data/portal.json and alert state
    # (data/swan_budget.json, which every run then rewrote), so test_hide_log failed whenever the real budget alert was due
    # and passed on the rerun (25 Oct uptime check)
    from swan_bot import watch
    monkeypatch.setattr(watch, "PORTAL_FILE", tmp_path / "portal.json")
    monkeypatch.setattr(watch, "BUDGET_FILE", tmp_path / "swan_budget.json")
    # the live switchback (todo/25 arm_conv) follows the clock: in a target_order block next_target ranks lean_no
    # first and test_targeting failed for 2 h at a time (23 Oct). Tests that need an arm set SWITCHBACK themselves.
    monkeypatch.setattr(config, "SWITCHBACK", [])
    # 27 Oct: the arm freeze is a date (1 Nov Sydney); tests use clocks past it (NOW = 1.8e9). Its own test sets it.
    monkeypatch.setattr(config, "ARMS_FREEZE", None)
    # todo/48: the box's data/npc_scores.json must not make a test account a citizen; both switches stay off (a .env
    # override included). tests/test_npc.py writes its own file and turns them on.
    monkeypatch.setattr(config, "NPC_SCORES_FILE", tmp_path / "npc_scores.json")
    monkeypatch.setattr(config, "NPC_EXTRA_ARM", False)
    monkeypatch.setattr(config, "BLUE_NPC_GUARD", False)
    config._NPC.update(mtime=None, built=0.0, scores={})
    # todo/38: the pool scheduler is on in config, but the older tests are written for the longest-rest-first pick; the
    # scheduler's own tests (tests/test_pool_scheduler.py) switch it on. Its state is per process: start every test clean.
    from swan_bot import stealth
    monkeypatch.setattr(config, "POOL_SCHEDULER", False)
    stealth.reset()
    # todo/38: the pool orchestrator ships OFF and no test may switch it on by accident (a .env override included);
    # tests/test_pool.py turns it on against fakes, with sockets blocked.
    monkeypatch.setattr(config, "POOL_LIVE", False)
    for name in ("POOL_WRITERS", "POOL_PIPELINE"):             # hot_mode_apply sets the hot refill's target: never leaks to the next test
        monkeypatch.setattr(config, name, getattr(config, name))
