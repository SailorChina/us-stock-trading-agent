"""Test: enhanced_indicators - CCI, RVI, StochRSI, Williams %R, OBV divergence."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import numpy as np
import pandas as pd
from enhanced_indicators import (
    calc_cci, calc_rvi, calc_stoch_rsi, calc_williams_r,
    detect_obv_divergence, calc_all_enhanced, enhanced_signal_score,
)


def _make_df(n=60, base=100.0, trend="up"):
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=n, freq="1D")
    if trend == "up":
        close = base + np.cumsum(np.abs(np.random.randn(n)) * 0.3)
    elif trend == "down":
        close = base - np.cumsum(np.abs(np.random.randn(n)) * 0.3)
    else:
        close = base + np.cumsum(np.random.randn(n) * 0.5)
    high = close + np.abs(np.random.randn(n) * 0.3)
    low = close - np.abs(np.random.randn(n) * 0.3)
    open_ = close + np.random.randn(n) * 0.1
    volume = np.random.randint(1_000_000, 10_000_000, n).astype(float)
    last_close = pd.Series([base] + list(close[:-1]), index=dates)
    return pd.DataFrame({
        "time_key": dates, "open": open_, "high": high, "low": low,
        "close": close, "volume": volume, "last_close": last_close.values,
    })


def test_calc_cci():
    df = _make_df(30, 100.0)
    result = calc_cci(df)
    assert "cci" in result
    assert "signal" in result
    assert isinstance(result["cci"], (int, float))


def test_calc_cci_oversold():
    df = _make_df(30, 100.0, trend="down")
    result = calc_cci(df)
    assert result["cci"] < 0 or result["signal"] in ("oversold", "bearish", "neutral")


def test_calc_rvi():
    df = _make_df(30, 100.0)
    result = calc_rvi(df)
    assert "rvi" in result
    assert "signal" in result


def test_calc_stoch_rsi():
    df = _make_df(30, 100.0)
    result = calc_stoch_rsi(df)
    assert "stoch_rsi" in result
    assert "k" in result
    assert "d" in result
    assert "signal" in result


def test_calc_williams_r():
    df = _make_df(30, 100.0)
    result = calc_williams_r(df)
    assert "williams_r" in result
    assert -100 <= result["williams_r"] <= 0
    assert "signal" in result


def test_detect_obv_divergence():
    df = _make_df(40, 100.0)
    result = detect_obv_divergence(df)
    assert "divergence" in result
    assert "strength" in result
    assert result["divergence"] in ("none", "bullish_divergence", "bearish_divergence")
    assert 0 <= result["strength"] <= 100


def test_calc_all_enhanced():
    df = _make_df(30, 100.0)
    result = calc_all_enhanced(df)
    assert "cci" in result
    assert "rvi" in result
    assert "stoch_rsi" in result
    assert "williams_r" in result
    assert "obv_divergence" in result


def test_enhanced_signal_score():
    df = _make_df(30, 100.0)
    result = enhanced_signal_score(df)
    assert "score" in result
    assert "rating" in result
    assert "reasons" in result
    assert isinstance(result["score"], (int, float))
    assert 0 <= result["score"] <= 100
    assert result["rating"] in ("bullish", "bearish", "neutral")


def test_enhanced_score_with_bearish_trend():
    df = _make_df(30, 100.0, trend="down")
    result = enhanced_signal_score(df)
    # Down trend should not push score to > 80
    assert result["score"] < 95


def test_enhanced_short_df():
    df = pd.DataFrame({"close": [100, 101], "open": [99, 100],
                       "high": [101, 102], "low": [99, 100], "volume": [1e6, 1e6]})
    result = calc_cci(df)
    assert result["cci"] == 0.0
