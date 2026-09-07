"""Test: earnings_analyzer - Yahoo Finance data fetching and scoring."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from earnings_analyzer import get_earnings_summary, get_analyst_targets, earnings_score


def test_earnings_summary_returns_dict():
    result = get_earnings_summary("US.NVDA")
    assert isinstance(result, dict)
    assert "symbol" in result
    assert "generated_at" in result


def test_earnings_summary_status():
    result = get_earnings_summary("US.NVDA")
    assert "status" in result
    assert result["status"] in ("ok", "error")


def test_analyst_targets_returns_dict():
    result = get_analyst_targets("US.NVDA")
    assert isinstance(result, dict)
    assert "symbol" in result


def test_earnings_score_no_data():
    result = earnings_score({"status": "error"}, "US.NVDA")
    assert result["score"] == 50
    assert result["signal"] == "unknown"


def test_earnings_score_empty_data():
    result = earnings_score({}, "US.NVDA")
    assert result["score"] == 50


def test_earnings_score_with_good_financials():
    data = {
        "status": "ok",
        "financials": {
            "pe_ratio": 30,
            "forward_pe": 25,
            "eps_trailing": 3.0,
            "eps_forward": 4.0,
            "profit_margin": 0.25,
            "revenue_growth": 0.15,
            "recommendation": "buy",
        },
        "upside": 10,
    }
    result = earnings_score(data, "US.NVDA")
    assert isinstance(result, dict)
    assert "score" in result
    assert "signal" in result
