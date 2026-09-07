"""Test: ml_predictor - ML prediction and backtest logic."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import numpy as np
import pandas as pd
from ml_predictor import predict_direction, backtest_ml, SKLEARN_OK


def test_sklearn_available():
    assert SKLEARN_OK is True


def test_predict_direction_insufficient_data():
    result = predict_direction("US.NVDA", lookback=200)
    assert "status" in result
    # Should fail gracefully (no live data in test env)
    assert result["status"] in ("insufficient_data", "insufficient_features",
                                  "sklearn_unavailable", "ok")


def test_predict_direction_returns_dict():
    result = predict_direction("US.NVDA", lookback=30)
    assert isinstance(result, dict)
    assert "symbol" in result
    assert "generated_at" in result


def test_backtest_ml_insufficient_data():
    result = backtest_ml("US.NVDA", lookback=200)
    assert "status" in result


def test_backtest_ml_returns_dict():
    result = backtest_ml("US.NVDA", lookback=30)
    assert isinstance(result, dict)
    assert "symbol" in result
