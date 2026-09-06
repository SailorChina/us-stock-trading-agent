"""Test: smart_money_screener - pure functions and structure."""
import pytest
import sys, os, json
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


def test_smart_universe():
    from smart_money_screener import SMART_UNIVERSE
    assert isinstance(SMART_UNIVERSE, list)
    assert len(SMART_UNIVERSE) >= 20
    for s in SMART_UNIVERSE:
        assert s.startswith("US.")
    assert "US.NVDA" in SMART_UNIVERSE
    assert "US.AAPL" in SMART_UNIVERSE


def test_format_report():
    from smart_money_screener import format_report
    results = [
        {
            "symbol": "US.NVDA", "total_score": 75,
            "flow_score": 25, "squeeze_score": 10, "tech_score": 25, "mom_score": 15,
            "signals": ["Smart70%", "3d buying"],
            "price": {"latest_price": 230.0, "change_pct": 2.5},
            "tech": {"status": "ok", "data": {
                "rating": "Overweight", "score": 72,
                "trade_plan": {"entry_zone": 226.5, "stop_loss": 215.0, "risk_reward": 2.0},
            }},
        },
        {
            "symbol": "US.TSLA", "total_score": 60,
            "flow_score": 15, "squeeze_score": 5, "tech_score": 25, "mom_score": 15,
            "signals": ["Short8%"],
            "price": {"latest_price": 250.0, "change_pct": 1.0},
            "tech": {"status": "ok", "data": {
                "rating": "Hold", "score": 50,
                "trade_plan": {"entry_zone": 246.0, "stop_loss": 235.0, "risk_reward": 1.5},
            }},
        },
    ]
    output = format_report(results)
    assert "SMART MONEY" in output
    assert "NVDA" in output
    assert "TSLA" in output
    assert "75" in output
    assert "60" in output
    assert "candidates" in output


def test_format_report_empty():
    from smart_money_screener import format_report
    output = format_report([])
    assert "0 candidates" in output


@pytest.mark.network
@pytest.mark.network
def test_scan_smart_money_returns_list():
    from smart_money_screener import scan_smart_money
    result = scan_smart_money(top_n=5, min_score=20)
    assert isinstance(result, list)
    if len(result) > 0:
        r = result[0]
        assert "symbol" in r
        assert "total_score" in r