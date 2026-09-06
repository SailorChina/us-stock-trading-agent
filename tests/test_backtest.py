"""Test: backtest - MA strategy with synthetic data."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import pandas as pd
from backtest import simple_ma_strategy


def _make_trend_df(n=100, start=100.0):
    import numpy as np
    np.random.seed(99)
    dates = pd.date_range("2023-01-01", periods=n, freq="1D")
    close = start + np.cumsum(np.random.randn(n) * 0.3) + np.linspace(0, 10, n)
    return pd.DataFrame({
        "time_key": dates, "open": close, "high": close + 0.5,
        "low": close - 0.5, "close": close, "volume": 1_000_000.0,
    })


def test_ma_strategy_golden_cross():
    df = _make_trend_df(100, 100.0)
    result = simple_ma_strategy(df, ma_fast=5, ma_slow=20)
    assert "trades" in result
    assert "total_return_pct" in result
    assert isinstance(result["trades"], list)


def test_ma_strategy_insufficient_data():
    df = pd.DataFrame({"close": [100.0, 101.0]})
    result = simple_ma_strategy(df, ma_fast=5, ma_slow=20)
    assert "error" in result


def test_ma_strategy_no_cross():
    df = pd.DataFrame({
        "time_key": pd.date_range("2023-01-01", periods=50),
        "open": [100.0] * 50, "high": [100.5] * 50,
        "low": [99.5] * 50, "close": [100.0] * 50,
        "volume": [1_000_000.0] * 50,
    })
    result = simple_ma_strategy(df, ma_fast=5, ma_slow=10)
    assert "trades" in result