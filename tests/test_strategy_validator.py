"""Offline tests: strategy_validator (v3.4.0).

The single most important property here is the absence of look-ahead: a bar
must be scored using only what was knowable at that bar. Everything else —
IC, buckets, simulation — is checked against constructed data with a known
answer.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import numpy as np
import pandas as pd
import pytest

import strategy_validator as sv


def _df(n=200, seed=11):
    rng = np.random.default_rng(seed)
    close = np.maximum(100 + np.cumsum(rng.normal(0, 1, n)), 1.0)
    high = close * (1 + np.abs(rng.normal(0, 0.01, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.01, n)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    volume = rng.integers(1_000_000, 5_000_000, n).astype(float)
    return pd.DataFrame({
        "time_key": pd.date_range("2024-01-01", periods=n, freq="D"),
        "open": open_, "high": high, "low": low,
        "close": close, "volume": volume,
    })


def _rows(scores, rets):
    return [{"date": f"d{i}", "score": s, "fwd_ret": r}
            for i, (s, r) in enumerate(zip(scores, rets))]


# --------------------------------------------------------------------------
# the property that matters
# --------------------------------------------------------------------------

def test_score_history_has_no_look_ahead():
    """Mutating FUTURE bars must not change earlier bars' scores."""
    df = _df(200)
    before = sv.score_history("US.TEST", df, horizon=5, window_bars=120)
    assert len(before) > 50

    changed = df.copy()
    changed.loc[150:, "close"] *= 1.7      # rewrite the future
    changed.loc[150:, "high"] *= 1.7
    changed.loc[150:, "low"] *= 0.6
    after = sv.score_history("US.TEST", changed, horizon=5, window_bars=120)

    # rows[i] corresponds to bar t = 60 + i; bars before 150 are unaffected
    untouched = 150 - 60
    for i in range(min(untouched, len(before), len(after))):
        assert before[i]["score"] == after[i]["score"], \
            f"bar {60 + i} score moved when the future changed — look-ahead"

    # sanity: the mutation really did reach later bars
    assert any(b["score"] != a["score"]
               for b, a in zip(before[untouched:], after[untouched:]))


def test_score_history_attaches_forward_return():
    rows = sv.score_history("US.TEST", _df(200), horizon=5, window_bars=120)
    assert rows, "expected scored bars"
    for r in rows:
        assert set(("score", "fwd_ret")) <= set(r)
        assert 0.0 <= r["score"] <= 100.0


# --------------------------------------------------------------------------
# statistics against known answers
# --------------------------------------------------------------------------

def test_ic_is_perfect_on_planted_signal():
    scores = list(np.linspace(10, 90, 100))
    rets = [s / 1000.0 for s in scores]          # perfectly monotone
    info = sv.information_coefficient(_rows(scores, rets))
    assert info["ic"] == pytest.approx(1.0, abs=0.001)
    assert info["significant"] is True


def test_ic_is_negative_on_inverted_signal():
    scores = list(np.linspace(10, 90, 100))
    rets = [-s / 1000.0 for s in scores]
    info = sv.information_coefficient(_rows(scores, rets))
    assert info["ic"] == pytest.approx(-1.0, abs=0.001)
    assert info["significant"] is True


def test_ic_is_not_significant_on_uncorrelated_noise():
    """Scores trend, returns alternate — the IC must land inside the noise band."""
    n = 100
    scores = [float(i) for i in range(n)]
    rets = [0.01 if i % 2 == 0 else -0.01 for i in range(n)]
    info = sv.information_coefficient(_rows(scores, rets))
    assert info["significant"] is False
    assert info["ci95"][0] < 0 < info["ci95"][1]


def test_verdict_predictive_on_planted_signal():
    scores = list(np.linspace(10, 90, 100))
    rows = _rows(scores, [s / 1000.0 for s in scores])
    info = sv.information_coefficient(rows)
    buckets = sv.bucket_returns(rows)
    verdict = sv._verdict(info, buckets, sv.simulate(rows))
    assert verdict["verdict"] == "predictive"
    assert verdict["top_minus_bottom_pct"] > 0


def test_verdict_inverse_when_high_scores_lose():
    scores = list(np.linspace(10, 90, 100))
    rows = _rows(scores, [-s / 1000.0 for s in scores])
    info = sv.information_coefficient(rows)
    verdict = sv._verdict(info, sv.bucket_returns(rows), sv.simulate(rows))
    assert verdict["verdict"] == "inverse"


def test_verdict_no_evidence_on_noise():
    n = 100
    rows = _rows([float(i) for i in range(n)],
                 [0.01 if i % 2 == 0 else -0.01 for i in range(n)])
    info = sv.information_coefficient(rows)
    verdict = sv._verdict(info, sv.bucket_returns(rows), sv.simulate(rows))
    assert verdict["verdict"] == "no_evidence"


def test_verdict_insufficient_samples():
    rows = _rows([1.0, 2.0, 3.0], [0.1, 0.2, 0.3])
    verdict = sv._verdict(sv.information_coefficient(rows), [], sv.simulate(rows))
    assert verdict["verdict"] == "insufficient_samples"


def test_buckets_rise_monotonically_for_a_real_signal():
    scores = list(np.linspace(10, 90, 100))
    rows = _rows(scores, [s / 1000.0 for s in scores])
    buckets = sv.bucket_returns(rows, buckets=5)
    assert len(buckets) == 5
    means = [b["mean_fwd_ret_pct"] for b in buckets]
    assert means == sorted(means), f"buckets not monotonic: {means}"
    assert means[-1] > means[0]


# --------------------------------------------------------------------------
# simulation
# --------------------------------------------------------------------------

def test_simulation_does_not_overlap_trades():
    """A 5-bar horizon must not count the same move five times."""
    rows = _rows([80.0] * 20, [0.01] * 20)
    sim = sv.simulate(rows, threshold=60.0, horizon=5)
    assert sim["trades"] == 4, "trades must be non-overlapping (20 bars / 5)"


def test_simulation_no_trades_below_threshold():
    rows = _rows([10.0] * 20, [0.01] * 20)
    sim = sv.simulate(rows, threshold=60.0, horizon=5)
    assert sim["trades"] == 0
    assert sim["strategy_return_pct"] == 0.0


def test_max_drawdown_is_negative():
    assert sv._max_drawdown([1.0, 1.2, 0.9, 1.1]) < 0


# --------------------------------------------------------------------------
# end to end, offline
# --------------------------------------------------------------------------

def test_validate_symbol_offline(monkeypatch):
    import tech_engine
    monkeypatch.setattr(tech_engine, "fetch_kline", lambda *a, **k: _df(300))
    rep = sv.validate_symbol("US.TEST", horizon=5, bars=300)
    assert rep["status"] == "ok", rep.get("error") or rep
    assert rep["scored_bars"] > 30
    assert "information_coefficient" in rep
    assert "buckets" in rep and len(rep["buckets"]) == 5
    assert "simulation" in rep
    assert "verdict" in rep


def test_validate_symbol_insufficient_data(monkeypatch):
    import tech_engine
    monkeypatch.setattr(tech_engine, "fetch_kline", lambda *a, **k: _df(30))
    rep = sv.validate_symbol("US.TEST", horizon=5, bars=30)
    assert rep["status"] == "insufficient_data"


def test_benchmark_comes_from_price_series_not_overlap(monkeypatch):
    """Regression: buy-and-hold must be the span return, not the product of
    every bar's overlapping forward return (which inflated it to ~180%)."""
    import tech_engine
    df = _df(300)
    monkeypatch.setattr(tech_engine, "fetch_kline", lambda *a, **k: df)

    rep = sv.validate_symbol("US.TEST", horizon=5, bars=300)
    rows = sv.score_history("US.TEST", df, horizon=5, window_bars=120)
    expected = (df["close"].iloc[-1] / df["close"].iloc[rows[0]["bar"]] - 1) * 100

    assert rep["benchmark_buy_hold_pct"] == pytest.approx(expected, abs=0.01)
    assert rep["simulation"]["buy_hold_return_pct"] == pytest.approx(expected, abs=0.01)


def test_bucket_monotonic_flag(monkeypatch):
    scores = list(np.linspace(10, 90, 100))
    rows = _rows(scores, [s / 1000.0 for s in scores])
    assert sv.bucket_returns(rows) is not None
    means = [b["mean_fwd_ret_pct"] for b in sv.bucket_returns(rows)]
    assert means == sorted(means)
