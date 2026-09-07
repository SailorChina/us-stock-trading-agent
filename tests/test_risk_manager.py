"""Test: risk_manager - ATR stop, risk-reward, position sizing."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from risk_manager import calculate_atr_stop, calculate_risk_reward, assess_risk_level
from risk_manager import dynamic_position_size, generate_risk_report


def test_calculate_atr_stop_basic():
    stop = calculate_atr_stop(100.0, 5.0, 2.0)
    assert stop == 90.0


def test_calculate_atr_stop_zero_atr():
    # When atr=0, stop = entry_price - 0*multiplier = entry_price
    stop = calculate_atr_stop(100.0, 0.0, 2.0)
    assert stop == 100.0


def test_calculate_risk_reward_basic():
    rr = calculate_risk_reward(100.0, 90.0, 120.0)
    assert rr == 2.0


def test_calculate_risk_reward_zero_risk():
    rr = calculate_risk_reward(100.0, 100.0, 120.0)
    assert rr == 0.0


def test_assess_risk_level_conservative():
    # position_pct=5.0 > 0.20, risk_per_trade=1.0 > 0.05, both trigger high
    result = assess_risk_level(5.0, 1.0, 3.0)
    assert result == "high"


def test_assess_risk_level_agressive():
    # position_pct=20.0 > 0.20, risk_per_trade=5.0 > 0.05, both trigger high
    result = assess_risk_level(20.0, 5.0, 1.5)
    assert result == "high"


def test_assess_risk_level_medium():
    # position_pct=10.0 > 0.20, risk_per_trade=2.0 > 0.05, both trigger high
    result = assess_risk_level(10.0, 2.0, 2.0)
    assert result == "high"


def test_dynamic_position_size_basic():
    result = dynamic_position_size(100.0, 5.0, 100000, 2.0, "medium")
    assert isinstance(result, dict)
    assert "shares" in result
    assert "risk_usd" in result
    assert result["shares"] > 0


def test_dynamic_position_size_small_capital():
    result = dynamic_position_size(50.0, 2.0, 5000, 1.0, "medium")
    assert result["shares"] >= 0


def test_generate_risk_report_basic():
    report = generate_risk_report("US.NVDA", 230.0, 230.0, 15.0, 8.0, 100000)
    assert report.symbol == "US.NVDA"
    assert report.stop_loss is not None
    assert report.target_1 is not None
    assert report.reward_risk_ratio is not None
