"""Test: decision_engine - compute_decision and compute_decision_fast."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from decision_engine import compute_decision, compute_decision_fast


def test_compute_decision_returns_dict():
    result = compute_decision("US.NVDA")
    assert isinstance(result, dict)
    assert "decision" in result
    assert "factors" in result
    assert "symbol" in result
    assert result["symbol"] == "US.NVDA"


def test_compute_decision_has_required_keys():
    result = compute_decision("US.NVDA")
    dec = result["decision"]
    assert "composite_score" in dec
    assert "decision" in dec
    assert "action" in dec
    assert dec["decision"] in ("STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL")
    assert dec["action"] in ("BUY", "HOLD", "SELL")


def test_compute_decision_score_range():
    result = compute_decision("US.NVDA")
    score = result["decision"]["composite_score"]
    assert 0 <= score <= 100


def test_compute_decision_fast_returns_dict():
    result = compute_decision_fast("US.NVDA")
    assert isinstance(result, dict)
    assert "decision" in result
    assert "factors" in result


def test_compute_decision_fast_keys():
    result = compute_decision_fast("US.NVDA")
    dec = result["decision"]
    assert "composite_score" in dec
    assert "decision" in dec
    assert "action" in dec
