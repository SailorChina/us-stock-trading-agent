"""Test: tech_engine new indicators - Aroon, ADX, VWAP, signal_strength."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import pandas as pd
import numpy as np
from tech_engine import calc_aroon, calc_adx, calc_vwap, calc_signal_strength, format_tech_output


def _make_df(n=60):
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=n, freq="1D")
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    return pd.DataFrame({
        "time_key": dates, "open": close, "high": close + 0.5,
        "low": close - 0.5, "close": close, "volume": 1_000_000.0,
    })


def test_calc_aroon():
    df = _make_df()
    ar = calc_aroon(df)
    assert "aroon_up" in ar and "aroon_down" in ar and "aroon_diff" in ar
    assert 0 <= ar["aroon_up"] <= 100
    assert 0 <= ar["aroon_down"] <= 100


def test_calc_adx():
    df = _make_df()
    ad = calc_adx(df)
    assert "adx" in ad and "plus_di" in ad and "minus_di" in ad
    assert ad["adx"] >= 0


def test_calc_vwap():
    df = _make_df()
    vwap = calc_vwap(df)
    assert isinstance(vwap, (int, float))
    assert vwap > 0


def test_calc_signal_strength():
    df = _make_df()
    strength = calc_signal_strength(df, atr=3.0, latest=105.0, ma20=102.0)
    assert 0 <= strength <= 100
    assert isinstance(strength, int)


def test_format_tech_output_with_new_indicators(sample_tech_result):
    output = format_tech_output(sample_tech_result)
    assert "Aroon" in output
    assert "ADX" in output
    assert "VWAP" in output
    assert "Strength" in output