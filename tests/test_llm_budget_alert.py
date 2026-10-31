"""todo/61 (31 Oct, Marc): the LLM budget projection and its alert (watch.llm_budget_report / llm_budget_run)."""
import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from swan_bot import config, watch  # noqa: E402

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 31, 0, 0, tzinfo=UTC).timestamp()          # 11:00 Sydney, 31 Oct
END = "2026-11-03T00:00:00+11:00"
SPEND = {"2026-10-29": 24.86, "2026-10-30": 18.89, "2026-10-31": 8.62, "2026-10-28": 88.78}    # 141.15: the box, 31 Oct 00:00 UTC


def test_the_projection_uses_today_s_rate_and_the_conservative_end():
    rep = watch.llm_budget_report(NOW, SPEND, {}, budget_usd=195.0, end=END)
    assert rep["left"] == round(195.0 - 141.15, 2)
    assert abs(rep["rate"] - 8.62 / 11) < 1e-3                          # 11 h into the Sydney day
    assert rep["hours"] == 61.0
    assert abs(rep["end_left"] - (53.85 - 8.62 / 11 * 61)) < 0.02 and rep["end_left"] > watch.LLM_ALERT_MIN_LEFT
    assert rep["alerts"] == {}                                          # about $6 left at midnight Sydney, 2 Nov


def test_a_short_projection_and_a_budget_park_alert():
    rich = dict(SPEND, **{"2026-10-28": 140.0})                         # $2.63 left
    status = {"llm": [{"model": config.HAIKU, "parked_until": "x", "why": "daily budget"},
                      {"model": "gemini-3.5-flash-lite", "parked_until": "x", "why": "daily budget"},   # free: not counted
                      {"model": "moonshotai.kimi-k2.5", "parked_until": "x", "why": "error"}]}
    rep = watch.llm_budget_report(NOW, rich, status, budget_usd=195.0, end=END)
    assert "LLM BUDGET:" in rep["alerts"]["short"] and "SWAN_LEAD_HAIKU_SHARE" in rep["alerts"]["short"]
    assert rep["parked"] == [config.HAIKU] and "parked" in rep["alerts"]


def test_early_in_the_day_the_rate_is_yesterday_s_average():
    early = dt.datetime(2026, 10, 30, 14, 0, tzinfo=UTC).timestamp()   # 01:00 Sydney, 31 Oct
    rep = watch.llm_budget_report(early, SPEND, {}, budget_usd=195.0, end=END)
    assert abs(rep["rate"] - 18.89 / 24) < 1e-3


def test_each_alert_goes_once_per_gap(monkeypatch, tmp_path):
    monkeypatch.setattr(watch, "LLM_ALERT_FILE", tmp_path / "state.json")
    monkeypatch.setattr(watch, "LLM_SPEND_FILE", tmp_path / "spend.json")
    monkeypatch.setattr(watch, "LLM_STATUS_FILE", tmp_path / "status.json")
    monkeypatch.setattr(config, "LLM_BUDGET_USD", 195.0)
    (tmp_path / "spend.json").write_text(json.dumps(dict(SPEND, **{"2026-10-28": 140.0})))
    sent, rows = [], []
    watch.llm_budget_run(NOW, alert=sent.append, record=rows.append)
    watch.llm_budget_run(NOW + 1200, alert=sent.append, record=rows.append)          # 20 min later: not again
    watch.llm_budget_run(NOW + watch.LLM_ALERT_GAP_S + 1, alert=sent.append, record=rows.append)
    assert len(sent) == 2 and all(s.startswith("LLM BUDGET:") for s in sent)
    assert [r["act"] for r in rows] == ["llm_budget"] * 3 and rows[1]["sending"] == []
    watch.llm_budget_run(NOW, alert=sent.append, record=rows.append, dry=True)           # dry: prints, sends nothing
    assert len(sent) == 2


def test_missing_files_are_no_alert(monkeypatch, tmp_path):
    monkeypatch.setattr(watch, "LLM_ALERT_FILE", tmp_path / "state.json")
    monkeypatch.setattr(watch, "LLM_SPEND_FILE", tmp_path / "none.json")
    monkeypatch.setattr(watch, "LLM_STATUS_FILE", tmp_path / "none2.json")
    sent = []
    rep = watch.llm_budget_run(NOW, alert=sent.append, record=lambda r: None)
    assert rep["left"] == config.LLM_BUDGET_USD and not sent
