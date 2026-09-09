"""Offline tests: ml_predictor correctness (v3.4.0).

Guards the bugs that made ML output confidently wrong:
  * one shared model file reused for every ticker;
  * StandardScaler fitted before the train/test split (leakage);
  * model chosen on the test set, then that same test score reported;
  * "forecast_7d" that actually looked backwards at past bars;
  * trailing bars labelled against close[-1] (fabricated labels).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import numpy as np
import pandas as pd
import pytest

import ml_predictor as mlp


def _synthetic(n=220, seed=7):
    """Deterministic random walk with OHLCV columns."""
    rng = np.random.default_rng(seed)
    close = np.maximum(100 + np.cumsum(rng.normal(0, 1, n)), 1.0)
    high = close * (1 + np.abs(rng.normal(0, 0.01, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.01, n)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    volume = rng.integers(1_000_000, 5_000_000, n).astype(float)
    return pd.DataFrame({"open": open_, "high": high, "low": low,
                         "close": close, "volume": volume})


@pytest.fixture
def fake_data(monkeypatch):
    """Serve synthetic bars instead of hitting the network."""
    import tech_engine
    monkeypatch.setattr(tech_engine, "fetch_kline", lambda *a, **k: _synthetic())


def test_model_path_is_per_symbol(tmp_path):
    a = mlp.model_path_for("US.NVDA")
    b = mlp.model_path_for("US.AAPL")
    assert a != b, "one shared model path leaks a ticker's model into another"
    assert "NVDA" in os.path.basename(a)
    assert "AAPL" in os.path.basename(b)
    explicit = str(tmp_path / "x.joblib")
    assert mlp.model_path_for("US.NVDA", explicit) == explicit


def test_majority_baseline():
    assert mlp._majority_baseline(np.array([1, 1, 1, 0])) == pytest.approx(0.75)
    assert mlp._majority_baseline(np.array([1, 0])) == pytest.approx(0.5)
    assert mlp._majority_baseline(np.array([])) == 0.0


def test_predict_reports_out_of_sample_accuracy_with_baseline(fake_data):
    r = mlp.predict_direction("US.NVDA", lookback=60)
    assert r["status"] == "ok", r.get("error") or r
    assert r["metrics_out_of_sample"] is True
    assert 0.0 <= r["accuracy"] <= 1.0
    assert 0.0 <= r["baseline_accuracy"] <= 1.0
    assert r["edge_over_baseline"] == pytest.approx(
        r["accuracy"] - r["baseline_accuracy"], abs=0.01)
    assert isinstance(r["beats_baseline"], bool)
    # a validation split must exist — selection happens there, not on test
    assert r["val_samples"] >= 10 and r["test_samples"] >= 10
    assert r["train_samples"] > 0


def test_scaler_is_fit_on_train_only(fake_data, tmp_path):
    """The scaler must never see validation/test rows."""
    p = str(tmp_path / "nvda.joblib")
    r = mlp.predict_direction("US.NVDA", lookback=60, model_path=p)
    assert r["status"] == "ok", r.get("error") or r

    import joblib
    from ml_features import extract_features
    scaler = joblib.load(p)["scaler"]

    fd = extract_features(_synthetic(), lookback=60)
    cols = [c for c in fd.columns if c != "target"]
    y = fd["target"].values.astype(float)
    X = fd[cols].values[~np.isnan(y)]
    train_end = int(len(X) * 0.6)

    assert scaler.mean_ == pytest.approx(X[:train_end].mean(axis=0), rel=1e-6)
    assert scaler.mean_ != pytest.approx(X.mean(axis=0), rel=1e-6), \
        "scaler saw the full dataset - that is leakage"


def test_foreign_model_is_rejected(fake_data, tmp_path):
    """Regression: a bundle trained on another symbol must NOT be reused."""
    p = str(tmp_path / "nvda.joblib")
    first = mlp.predict_direction("US.NVDA", lookback=60, model_path=p)
    assert first["status"] == "ok"

    # Ask for AAPL while pointing at NVDA's model file.
    second = mlp.predict_direction("US.AAPL", lookback=60, model_path=p)
    assert second["status"] == "ok"
    assert second["model_source"] == "trained_fresh", \
        "silently reused another symbol's model"
    assert second["metrics_out_of_sample"] is True


def test_saved_bundles_are_symbol_scoped(fake_data, tmp_path):
    p1, p2 = str(tmp_path / "nvda.joblib"), str(tmp_path / "aapl.joblib")
    assert mlp.predict_direction("US.NVDA", lookback=60, model_path=p1)["status"] == "ok"
    assert mlp.predict_direction("US.AAPL", lookback=60, model_path=p2)["status"] == "ok"

    import joblib
    b1, b2 = joblib.load(p1), joblib.load(p2)
    assert b1["symbol"] == "US.NVDA"
    assert b2["symbol"] == "US.AAPL"
    assert b1["model"] is not b2["model"]


def test_forecast_replaced_by_honest_recent_signals(fake_data):
    r = mlp.predict_direction("US.NVDA", lookback=60)
    assert r["status"] == "ok"
    assert "forecast_7d" not in r, "old key relabelled past bars as a forecast"
    assert "recent_bar_signals" in r
    assert r["recent_bar_signals"][0]["bars_ago"] == 1


def test_unlabelled_trailing_bars_are_excluded_from_training(fake_data, tmp_path):
    """Trailing bars have no real 5-bar outcome and must not be trained on."""
    from ml_features import extract_features
    fd = extract_features(_synthetic(), lookback=60)
    targets = fd["target"].values.astype(float)
    assert np.isnan(targets[-1]), "last bar cannot have a known 5-bar outcome"
    assert np.isnan(targets).sum() == 5
    assert not np.isnan(targets[:-5]).any()

    p = str(tmp_path / "nvda.joblib")
    r = mlp.predict_direction("US.NVDA", lookback=60, model_path=p)
    assert r["status"] == "ok"
    assert r["train_samples"] + r["val_samples"] + r["test_samples"] == len(targets) - 5
