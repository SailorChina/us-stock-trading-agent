"""Test: tech_engine core indicator functions with mock data."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import numpy as np
import pandas as pd
from tech_engine import calc_ma, calc_ema, calc_macd, calc_rsi, calc_kdj, calc_boll
from tech_engine import calc_atr, calc_obv, calc_aroon, calc_adx, calc_vwap, calc_signal_strength


def _make_df(n=60, base=100.0):
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=n, freq="1D")
    close = base + np.cumsum(np.random.randn(n) * 0.5)
    high = close + np.abs(np.random.randn(n) * 0.3)
    low = close - np.abs(np.random.randn(n) * 0.3)
    open_ = close + np.random.randn(n) * 0.1
    volume = np.random.randint(1_000_000, 10_000_000, n).astype(float)
    last_close = pd.Series([base] + list(close[:-1]), index=dates)
    return pd.DataFrame({"time_key": dates, "open": open_, "high": high, "low": low,
                       "close": close, "volume": volume, "last_close": last_close.values})


def test_calc_ma():
    df = _make_df(60, 100.0)
    ma = calc_ma(df)
    assert "MA5" in ma and "MA10" in ma and "MA20" in ma and "MA60" in ma
    assert ma["MA5"] > 0


def test_calc_ema():
    df = _make_df(60, 100.0)
    ema = calc_ema(df)
    assert all(k in ema for k in ["EMA12", "EMA26", "EMA9"])


def test_calc_macd():
    df = _make_df(60, 100.0)
    macd = calc_macd(df)
    assert all(k in macd for k in ["dif", "dea", "hist", "signal"])


def test_calc_rsi():
    df = _make_df(60, 100.0)
    rsi = calc_rsi(df)
    assert 0 <= rsi <= 100


def test_calc_kdj():
    df = _make_df(60, 100.0)
    kdj = calc_kdj(df)
    assert all(k in kdj for k in ["k", "d", "j"])


def test_calc_boll():
    df = _make_df(60, 100.0)
    boll = calc_boll(df)
    assert boll["upper"] > boll["mid"] > boll["lower"]


def test_calc_atr():
    df = _make_df(60, 100.0)
    atr = calc_atr(df)
    assert atr > 0


def test_calc_obv():
    df = _make_df(60, 100.0)
    obv = calc_obv(df)
    assert isinstance(obv, float)


def test_calc_aroon():
    df = _make_df(60, 100.0)
    aroon = calc_aroon(df)
    assert 0 <= aroon["aroon_up"] <= 100
    assert 0 <= aroon["aroon_down"] <= 100


def test_calc_adx():
    df = _make_df(60, 100.0)
    adx = calc_adx(df)
    assert adx["adx"] >= 0


def test_calc_vwap():
    df = _make_df(60, 100.0)
    vwap = calc_vwap(df)
    assert vwap > 0


def test_calc_signal_strength():
    df = _make_df(60, 100.0)
    atr = calc_atr(df)
    latest = float(df["close"].iloc[-1])
    ma20 = float(df["close"].rolling(20).mean().iloc[-1])
    strength = calc_signal_strength(df, atr, latest, ma20)
    assert 0 <= strength <= 100
