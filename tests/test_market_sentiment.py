"""Test: market_sentiment - VIX classification and Yahoo fallback."""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from market_sentiment import classify_vix, _calc_change, get_vix, get_market_overview


def test_classify_vix_low():
    assert classify_vix(12.0) == "very_low"
    assert classify_vix(18.0) == "low"


def test_classify_vix_medium():
    assert classify_vix(22.0) == "medium"
    assert classify_vix(29.0) == "medium"


def test_classify_vix_high():
    assert classify_vix(32.0) == "high"
    assert classify_vix(39.0) == "high"


def test_classify_vix_extreme():
    assert classify_vix(45.0) == "extreme"
    assert classify_vix(50.0) == "extreme"


def test_classify_vix_zero():
    assert classify_vix(0) == "very_low"


def test_calc_change_basic():
    q = {"close": 105.0, "prev_close": 100.0}
    assert _calc_change(q) == 5.0


def test_calc_change_negative():
    q = {"close": 95.0, "prev_close": 100.0}
    assert _calc_change(q) == -5.0


def test_calc_change_no_prev():
    q = {"close": 100.0, "prev_close": 0}
    assert _calc_change(q) == 0.0


def test_calc_change_none():
    assert _calc_change(None) == 0.0


@pytest.mark.network
@pytest.mark.timeout(30)
def test_get_vix_returns_dict():
    result = get_vix()
    assert isinstance(result, dict)


@pytest.mark.network
@pytest.mark.timeout(30)
def test_get_market_overview_returns_dict():
    result = get_market_overview()
    assert isinstance(result, dict)