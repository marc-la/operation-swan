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


@pytest.fixture(autouse=True)
def _no_live_switch_files(monkeypatch, tmp_path):
    """The box's live switch and account files (AMPLIFY_OFF, secrets/*_accounts.json) must not change what the tests
    see: since 2026-10-22 check.sh runs the suite on the box before every deploy, and AMPLIFY_OFF there failed
    test_amplify for everyone. Tests that need one of these files set their own after this."""
    from swan_bot import config
    monkeypatch.setattr(config, "AMP_OFF_FILE", tmp_path / "AMPLIFY_OFF")
    monkeypatch.setattr(config, "ACCOUNTS_FILE", tmp_path / "swan_accounts.json")
    monkeypatch.setattr(config, "SWARM_ACCOUNTS_FILE", tmp_path / "swarm_accounts.json")
    # the live switchback (todo/25 arm_conv) follows the clock: in a target_order block next_target ranks lean_no
    # first and test_targeting failed for 2 h at a time (23 Oct). Tests that need an arm set SWITCHBACK themselves.
    monkeypatch.setattr(config, "SWITCHBACK", [])
