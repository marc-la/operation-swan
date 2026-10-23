"""scripts/aws_cost.py: the maths behind the credit projection (figures from Cost Explorer on 23 Oct 2026)."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import aws_cost  # noqa: E402

TOKENS = {  # usage type: cost, thousands of tokens (23 Oct)
    "APS2-moonshotai.kimi-k2.5-mantle-input-tokens-standard": {"UnblendedCost": 4.278, "UsageQuantity": 6899.6},
    "APS2-moonshotai.kimi-k2.5-mantle-output-tokens-standard": {"UnblendedCost": 1.143, "UsageQuantity": 369.9},
    "APS2-deepseek.v3.2-mantle-input-tokens-standard": {"UnblendedCost": 0.196, "UsageQuantity": 306.1},
    "APS2-BoxUsage:t3.micro": {"UnblendedCost": 0.75, "UsageQuantity": 56},
}


def test_real_prices_are_per_million_tokens_and_skip_non_token_lines():
    prices = aws_cost.real_prices(TOKENS)
    assert set(prices) == {"moonshotai.kimi-k2.5", "deepseek.v3.2"}
    assert round(prices["moonshotai.kimi-k2.5"]["in"], 2) == 0.62
    assert round(prices["moonshotai.kimi-k2.5"]["out"], 2) == 3.09


def test_padding_factor_counts_only_models_priced_in_config():
    # billed Kimi 0.62/3.09 and DeepSeek 0.64/1.91 against the padded config prices (0.75/3.75, 0.80/2.40)
    assert 0.80 < aws_cost.padding_factor(aws_cost.real_prices(TOKENS)) < 0.85


def test_projection_pace_and_budget_scenarios():
    ledger = {"2026-10-21": 0.13, "2026-10-22": 6.0, "2026-10-23": 3.0}
    kw = dict(billed=9.0, ledger=ledger, today="2026-10-23", instance_type="t3.medium", factor=0.8, unpriced_day=0.1,
              surplus=0.0)
    p = aws_cost.project(**kw)
    assert p["days_left"] == 10 and p["ledger_rate_per_day"] == 6.0       # 21 Oct is not trusted
    fixed = (0.0528 * 24 + 0.12 + 0.027 + 0.1) * 11
    assert abs(p["fixed_ec2_etc"] - fixed) < 1e-6
    assert abs(p["pace"]["total"] - (9.0 + 0.8 * 3.0 + fixed + 0.8 * (3.0 + 60.0))) < 1e-6
    assert p["pace"]["headroom"] == aws_cost.CREDIT_USD - p["pace"]["total"]
    cfg_left = aws_cost.config.LLM_BUDGET_USD - sum(ledger.values())
    assert abs(p["budget"]["total"] - (9.0 + 0.8 * 3.0 + fixed + 0.8 * cfg_left)) < 1e-6


def test_status_bands():
    assert aws_cost.status({"budget": {"total": 150}}) == "ok"
    assert aws_cost.status({"budget": {"total": 190}}) == "watch"
    assert aws_cost.status({"budget": {"total": 210}}) == "over"
