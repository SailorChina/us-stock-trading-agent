"""Test: risk manager calculations."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import risk_manager

def test_atr_stop():
    stop = risk_manager.calculate_atr_stop(100.0, atr=3.0, multiplier=2.0)
    assert stop == 94.0

def test_risk_reward():
    # entry=100, stop=90 -> risk=10; target=120 -> reward=20; RR=20/10=2.0
    rr = risk_manager.calculate_risk_reward(entry=100, stop=90, target=120)
    assert rr == 2.0

def test_risk_reward_zero_risk():
    rr = risk_manager.calculate_risk_reward(entry=100, stop=110, target=120)
    assert rr == 0.0  # stop above entry = invalid

def test_risk_report():
    report = risk_manager.generate_risk_report(
        symbol="US.NVDA", entry_price=220, current_price=228,
        position_pct=0.10, atr=7.76, total_capital=100000
    )
    assert report.symbol == "US.NVDA"
    assert report.stop_loss is not None
    assert report.reward_risk_ratio > 0
    assert report.risk_level in ("low", "medium", "high")

def test_dynamic_position_size():
    result = risk_manager.dynamic_position_size(
        entry_price=220, atr=7.76, capital=100000, risk_pct=2
    )
    assert result["shares"] > 0
    assert result["position_pct"] > 0

def test_portfolio_check():
    positions = [
        {"shares": 10, "current_price": 220, "sector": "Tech", "position_pct": 0.15},
        {"shares": 5,  "current_price": 500, "sector": "Tech", "position_pct": 0.10},
    ]
    checks = risk_manager.portfolio_check(positions, total_capital=100000)
    assert checks["total_position_pct"] == 25.0
    assert checks["cash_ratio"] == 75.0
