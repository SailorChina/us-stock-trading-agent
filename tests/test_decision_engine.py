"""Test: decision_engine - composite scoring logic."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from decision_engine import compute_decision_fast


def test_compute_decision_returns_dict():
    result = compute_decision_fast("US.NVDA")
    assert isinstance(result, dict)
    assert "decision" in result
    assert "factors" in result
    assert "symbol" in result
    assert result["symbol"] == "US.NVDA"


def test_decision_has_required_keys():
    result = compute_decision_fast("US.NVDA")
    dec = result["decision"]
    assert "composite_score" in dec
    assert "decision" in dec
    assert "action" in dec
    assert dec["decision"] in ("STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL")
    assert dec["action"] in ("BUY", "HOLD", "SELL")


def test_decision_score_range():
    result = compute_decision_fast("US.NVDA")
    score = result["decision"]["composite_score"]
    assert 0 <= score <= 100


def test_decision_has_trade_plan():
    result = compute_decision_fast("US.NVDA")
    tp = result["decision"].get("trade_plan", {})
    if tp:
        assert "entry_zone" in tp
        assert "stop_loss" in tp
        assert "target_1" in tp
