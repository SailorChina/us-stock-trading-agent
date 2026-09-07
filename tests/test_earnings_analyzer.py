"""Test: earnings_analyzer - scoring logic (no network required)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from earnings_analyzer import earnings_score


def test_earnings_score_no_data():
    result = earnings_score({"status": "error", "error": "timeout"}, "US.NVDA")
    assert result["score"] == 50
    assert result["signal"] == "unknown"


def test_earnings_score_good():
    data = {
        "status": "ok",
        "financials": {
            "pe_ratio": 20,
            "forward_pe": 18,
            "eps_trailing": 2.0,
            "eps_forward": 2.5,
            "profit_margin": 0.25,
            "revenue_growth": 0.20,
            "recommendation": "buy",
        },
        "upside": 15,
    }
    result = earnings_score(data, "US.NVDA")
    assert result["score"] > 50
    assert result["signal"] in ("bullish", "neutral")
    assert len(result["reasons"]) > 0


def test_earnings_score_bad():
    data = {
        "status": "ok",
        "financials": {
            "pe_ratio": 80,
            "forward_pe": 90,
            "eps_trailing": 5.0,
            "eps_forward": 4.0,
            "profit_margin": -0.05,
            "revenue_growth": -0.10,
            "recommendation": "sell",
        },
        "upside": -20,
    }
    result = earnings_score(data, "US.NVDA")
    assert result["score"] < 50
    assert result["signal"] == "bearish"
