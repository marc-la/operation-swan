"""Shared test setup. The fact desk's runtime pauses (data/facts_paused.json) live on the box that runs the bot, and
deploy/check.sh runs these tests there: point the fact store at a file that doesn't exist, so a live pause can't
change what the tests see (tests that need a pause write their own, see tests/test_facts.py)."""
import os

os.environ["SWAN_FACTS_PAUSED"] = "/nonexistent/swan-tests/facts_paused.json"
# the desk's overlay (todo/29): the same, except when the desk itself runs tests/test_facts.py on a candidate overlay
# (factdesk.run_facts_tests sets SWAN_FACTS_AUTO_CHECK)
os.environ["SWAN_FACTS_AUTO"] = os.environ.get("SWAN_FACTS_AUTO_CHECK") or "/nonexistent/swan-tests/facts_auto.toml"
