import pytest
"""Test: options_analysis - IV/PCR classification and structure."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from options_analysis import classify_iv, classify_pcr, get_unusual_options


def test_classify_iv_low():
    assert classify_iv(0.15) == "low"
    assert classify_iv(0.0) == "low"


def test_classify_iv_normal():
    assert classify_iv(0.25) == "normal"
    assert classify_iv(0.34) == "normal"


def test_classify_iv_high():
    assert classify_iv(0.40) == "high"
    assert classify_iv(0.49) == "high"


def test_classify_iv_extreme():
    assert classify_iv(0.55) == "extreme"
    assert classify_iv(1.0) == "extreme"


def test_classify_iv_none():
    assert classify_iv(None) == "unknown"


def test_classify_pcr_bullish():
    assert classify_pcr(0.5) == "bullish"
    assert classify_pcr(0.69) == "bullish"


def test_classify_pcr_neutral():
    assert classify_pcr(0.8) == "neutral"
    assert classify_pcr(0.99) == "neutral"


def test_classify_pcr_cautious():
    assert classify_pcr(1.1) == "cautious"
    assert classify_pcr(1.29) == "cautious"


def test_classify_pcr_bearish():
    assert classify_pcr(1.5) == "bearish"
    assert classify_pcr(2.0) == "bearish"


def test_classify_pcr_none():
    assert classify_pcr(None) == "unknown"


@pytest.mark.network
@pytest.mark.timeout(30)
def test_get_unusual_options():
    result = get_unusual_options("US.NVDA")
    assert isinstance(result, str)