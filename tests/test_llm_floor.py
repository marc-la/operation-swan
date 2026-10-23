"""The daily floor under the LLM allowance (23 Oct 2026): the weighted share of $6.80 a day left no margin over the bot's
~$6-7 a day, the allowance ran out at ~06:30 Sydney and 7 h of drafts found no model. The floor never lifts the total
past LLM_BUDGET_USD and leaves days outside the budget alone."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from swan_bot import config, llm  # noqa: E402


def test_floor_lifts_the_early_days_and_carries(monkeypatch):
    monkeypatch.setattr(config, "LLM_BUDGET_USD", 170.0)
    monkeypatch.setattr(config, "LLM_DAILY_FLOOR_USD", 12.0)
    assert llm.allowance("2026-10-21", {}) == 12.0                        # weighted share would be 6.80
    assert llm.allowance("2026-10-23", {}) == 36.0                        # 3 days at the floor
    assert llm.allowance("2026-10-23", {"2026-10-21": 0.13, "2026-10-22": 5.85, "2026-10-23": 4.3}) > 25.0
    assert llm.day_share("2026-10-23") == 12.0


def test_weighted_share_wins_once_it_passes_the_floor(monkeypatch):
    monkeypatch.setattr(config, "LLM_BUDGET_USD", 170.0)
    monkeypatch.setattr(config, "LLM_DAILY_FLOOR_USD", 12.0)
    assert llm.day_share("2026-11-01") == 27.2                            # 4 x 6.80
    assert llm.allowance("2026-11-02", {}) == 170.0                       # the weighted total; the floor is 13 x 12 = 156


def test_total_cap_and_days_outside_the_budget_are_untouched(monkeypatch):
    monkeypatch.setattr(config, "LLM_BUDGET_USD", 50.0)
    monkeypatch.setattr(config, "LLM_DAILY_FLOOR_USD", 12.0)
    assert llm.allowance("2026-10-25", {}) == 50.0                        # 5 x 12 = 60 would pass the cap
    assert llm.allowance("2026-10-20", {}) == 0.0 and llm.day_share("2026-10-20") == 0.0
    assert llm.allowance("2026-10-21", {"2026-10-21": 11.0}) == 1.0


def test_deepseek_and_mistral_are_priced_so_their_spend_counts():
    for m in ("deepseek.v3.2", "mistral.mistral-large-3-675b-instruct"):
        assert m in config.LLM_PRICES


def test_day_share_never_passes_the_total_budget(monkeypatch):
    monkeypatch.setattr(config, "LLM_BUDGET_USD", 4.0)
    monkeypatch.setattr(config, "LLM_DAILY_FLOOR_USD", 12.0)
    assert llm.day_share("2026-10-21") == 4.0                             # else the reserve (25% of it) would eat a small budget
