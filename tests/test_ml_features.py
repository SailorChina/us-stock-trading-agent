"""Test: ml_features - feature extraction and matrix building."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import numpy as np
import pandas as pd
from ml_features import extract_features, get_feature_columns, build_feature_matrix


def _make_df(n=100, base=100.0):
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


def test_get_feature_columns():
    cols = get_feature_columns()
    assert isinstance(cols, list)
    assert "close" in cols
    assert "rsi" in cols
    assert "target" not in cols


def test_extract_features_returns_dataframe():
    df = _make_df(100, 100.0)
    result = extract_features(df, lookback=30)
    assert isinstance(result, pd.DataFrame)
    assert "target" in result.columns
    assert len(result) > 0


def test_extract_features_has_target():
    df = _make_df(100, 100.0)
    result = extract_features(df, lookback=30)
    assert set(result.columns) == set(get_feature_columns()) | {"target"}


def test_extract_features_target_binary():
    """Targets are 0/1, except the trailing bars that have no 5-bar outcome."""
    df = _make_df(100, 100.0)
    result = extract_features(df, lookback=30)
    targets = result["target"].values.astype(float)
    assert set(targets[:-5]).issubset({0.0, 1.0})
    # the last 5 bars cannot know their own 5-bar-ahead outcome
    assert np.isnan(targets[-5:]).all()


def test_extract_features_insufficient_data():
    df = _make_df(20, 100.0)
    result = extract_features(df, lookback=30)
    assert result is None


def test_build_feature_matrix():
    df = _make_df(100, 100.0)
    feat_df = extract_features(df, lookback=30)
    matrix = build_feature_matrix(feat_df)
    assert matrix is not None
    assert isinstance(matrix, pd.DataFrame)
    assert "target" not in matrix.columns
    assert matrix.isnull().sum().sum() == 0


def test_build_feature_matrix_none():
    result = build_feature_matrix(None)
    assert result is None


def test_extract_features_columns_match():
    df = _make_df(100, 100.0)
    result = extract_features(df, lookback=30)
    expected_cols = set(get_feature_columns())
    actual_cols = set(result.columns) - {"target"}
    assert expected_cols == actual_cols


def test_extract_features_ret_features():
    df = _make_df(100, 100.0)
    result = extract_features(df, lookback=30)
    # Returns should be in reasonable range
    assert result["ret_1d"].min() > -1.0
    assert result["ret_1d"].max() < 1.0


def test_extract_features_rsi_range():
    df = _make_df(100, 100.0)
    result = extract_features(df, lookback=30)
    assert result["rsi"].min() >= 0
    assert result["rsi"].max() <= 100
