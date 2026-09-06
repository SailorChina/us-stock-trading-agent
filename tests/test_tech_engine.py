"""Test: tech_engine - indicator calculations (pure functions) and structure."""
import pytest
import sys, os, json
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from tech_engine import (
    calc_ma, calc_ema, calc_macd, calc_rsi, calc_kdj, calc_boll, calc_obv, calc_atr,
    format_tech_output, get_tech_summary,
)


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


def test_calc_ma():
    df = _make_df(60, 100.0)
    ma = calc_ma(df, periods=(5, 10, 20, 60))
    assert "MA5" in ma and "MA10" in ma and "MA20" in ma
    assert ma["MA5"] > 0
    assert ma["MA20"] > 0


def test_calc_ema():
    df = _make_df(60, 100.0)
    ema = calc_ema(df, periods=(12, 26, 9))
    assert "EMA12" in ema and "EMA26" in ema and "EMA9" in ema
    assert ema["EMA12"] > 0


def test_calc_macd():
    df = _make_df(60, 100.0)
    macd = calc_macd(df)
    assert "dif" in macd and "dea" in macd and "hist" in macd
    assert isinstance(macd["dif"], (int, float))
    assert isinstance(macd["hist"], (int, float))


def test_calc_rsi():
    df = _make_df(60, 100.0)
    rsi = calc_rsi(df, period=14)
    assert 0 <= rsi <= 100
    assert isinstance(rsi, (int, float))


def test_calc_rsi_uptrend():
    df = _make_df(60, 100.0)
    df["close"] = df["close"] + np.linspace(0, 20, 60)
    rsi = calc_rsi(df, period=14)
    assert rsi > 50


def test_calc_kdj():
    df = _make_df(60, 100.0)
    kdj = calc_kdj(df)
    assert "k" in kdj and "d" in kdj and "j" in kdj
    assert 0 <= kdj["k"] <= 100
    assert 0 <= kdj["d"] <= 100


def test_calc_boll():
    df = _make_df(60, 100.0)
    boll = calc_boll(df)
    assert "upper" in boll and "mid" in boll and "lower" in boll
    assert boll["upper"] > boll["mid"] > boll["lower"]
    assert 0 <= boll["position_pct"] <= 100


def test_calc_obv():
    df = _make_df(60, 100.0)
    obv = calc_obv(df)
    assert isinstance(obv, (int, float))
    assert obv != 0


def test_calc_atr():
    df = _make_df(60, 100.0)
    atr = calc_atr(df, period=14)
    assert atr > 0
    assert isinstance(atr, (int, float))


def test_format_tech_output_basic():
    data = {
        "status": "ok", "symbol": "US.NVDA",
        "data": {
            "rating": "Overweight", "score": 72,
            "price": {"latest_price": 230.0, "change_pct": 2.5},
            "dimensions": {
                "trend": {"score": 15, "reason": "MA bullish"},
                "momentum": {"score": 12, "reason": "RSI OK"},
                "volatility": {"score": 8, "reason": "ATR normal"},
                "volume": {"score": 10, "reason": "OBV rising"},
            },
            "indicators": {
                "ma": {"MA5": 228, "MA10": 225, "MA20": 220, "MA60": 200},
                "ema": {"EMA12": 229, "EMA26": 224},
                "macd": {"dif": 1.5, "dea": 1.2, "hist": 0.3, "signal": "bullish"},
                "rsi": 58.0, "kdj": {"k": 60, "d": 55, "j": 70},
                "boll": {"upper": 240, "mid": 220, "lower": 200, "position_pct": 65},
                "atr": 5.5,
            },
            "signals": ["Price above MA20", "MACD golden cross"],
            "trade_plan": {
                "entry_zone": 226.5, "stop_loss": 215.0,
                "target_1": 249.5, "target_2": 261.0,
                "risk_reward": 2.0, "atr": 5.5,
                "position_size_pct": 50.0, "risk_usd": 11.5,
            },
            "last_time": "2024-06-01", "bar_count": 60,
        },
    }
    output = format_tech_output(data)
    assert "NVDA" in output
    assert "Overweight" in output
    assert "72" in output
    assert "MACD" in output
    assert "Entry:" in output
    assert "Stop:" in output


@pytest.mark.network
def test_format_tech_output_error():
    data = {"status": "error", "error": "Connection failed"}
    output = format_tech_output(data)
    assert "Connection failed" in output


@pytest.mark.network
def test_get_tech_summary_no_live():
    result = get_tech_summary("US.NVDA")
    assert isinstance(result, dict)


def test_smart_universe_constant():
    from smart_money_screener import SMART_UNIVERSE
    assert isinstance(SMART_UNIVERSE, list)
    assert len(SMART_UNIVERSE) > 0
    for s in SMART_UNIVERSE:
        assert s.startswith("US.")
    assert "US.NVDA" in SMART_UNIVERSE


def test_calc_ma_short_df():
    df = pd.DataFrame({
        "time_key": pd.date_range("2024-01-01", periods=10, freq="1D"),
        "open": [100.0] * 10, "high": [101.0] * 10,
        "low": [99.0] * 10, "close": [100.0 + i * 0.1 for i in range(10)],
        "volume": [1_000_000.0] * 10,
    })
    ma = calc_ma(df, periods=(5,))
    assert "MA5" in ma


def test_calc_rsi_short_df():
    df = pd.DataFrame({
        "time_key": pd.date_range("2024-01-01", periods=15, freq="1D"),
        "open": [100.0] * 15, "high": [101.0] * 15,
        "low": [99.0] * 15, "close": [100.0 + i * 0.5 for i in range(15)],
        "volume": [1_000_000.0] * 15,
        "last_close": [100.0] + [100.0 + (i-1) * 0.5 for i in range(1, 15)],
    })
    rsi = calc_rsi(df, period=14)
    assert isinstance(rsi, (int, float))