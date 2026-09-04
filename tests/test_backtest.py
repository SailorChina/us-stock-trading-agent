"""Test: backtest MA strategy."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from backtest import simple_ma_strategy
import pandas as pd
from datetime import datetime, timedelta

def _make_df(days=100):
    dates = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(days)]
    prices = [100 + i * 0.5 + (5 if i % 30 == 0 else 0) for i in range(days)]
    df = pd.DataFrame({"time": dates, "open": prices, "high": prices,
                       "low": [p-1 for p in prices], "close": prices, "volume": [1000]*days})
    return df

def test_ma_strategy_returns_result():
    df = _make_df(100)
    result = simple_ma_strategy(df, ma_fast=5, ma_slow=20)
    assert "trades" in result
    assert "total_trades" in result
    assert result["total_trades"] >= 0

def test_ma_strategy_insufficient_data():
    df = pd.DataFrame({"time": [], "open": [], "high": [], "low": [], "close": [], "volume": []})
    result = simple_ma_strategy(df, ma_fast=5, ma_slow=20)
    assert "error" in result
