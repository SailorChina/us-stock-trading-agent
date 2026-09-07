"""Test: candlestick_patterns - pattern detection and scoring."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import numpy as np
import pandas as pd
from candlestick_patterns import calc_candlestick, get_latest_patterns, pattern_score


def _make_df(n=60, base=100.0):
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=n, freq="1D")
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


def test_calc_candlestick_returns_list():
    df = _make_df(60, 100.0)
    patterns = calc_candlestick(df)
    assert isinstance(patterns, list)


def test_get_latest_patterns_returns_list():
    df = _make_df(60, 100.0)
    patterns = get_latest_patterns(df, 5)
    assert isinstance(patterns, list)
    assert len(patterns) <= 5


def test_pattern_score_neutral():
    score = pattern_score([])
    assert score["score"] == 50
    assert score["signal"] == "neutral"
    assert score["count"] == 0


def test_pattern_score_bullish():
    patterns = [{"direction": "bullish", "type": "hammer"},
                {"direction": "bullish", "type": "morning_star"}]
    score = pattern_score(patterns)
    assert score["score"] > 50
    assert score["bullish"] == 2


def test_pattern_score_bearish():
    patterns = [{"direction": "bearish", "type": "shooting_star"}]
    score = pattern_score(patterns)
    assert score["score"] < 50
    assert score["bearish"] == 1


def test_pattern_score_with_mixed():
    patterns = [
        {"direction": "bullish", "type": "hammer"},
        {"direction": "bearish", "type": "shooting_star"},
        {"direction": "bullish", "type": "bullish_engulfing"},
    ]
    score = pattern_score(patterns)
    assert isinstance(score["score"], (int, float))
    assert 0 <= score["score"] <= 100
