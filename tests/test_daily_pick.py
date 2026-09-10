"""Offline tests: daily_pick after-close scanner (v3.4.0).

Everything network is injected, so the scan logic itself is tested without
touching futu: universe loading, per-style ranking, regime gating, and the
report shape.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import numpy as np
import pandas as pd
import pytest

import daily_pick as dp


def _df(n=320, base=100.0, seed=5):
    rng = np.random.default_rng(seed)
    close = np.maximum(base * np.cumprod(1 + rng.normal(0.003, 0.012, n)), 1.0)
    return _frame(close, seed)


def _pullback_df(n=320, base=100.0, seed=6):
    """Uptrend pullback that ends on an UP day (reversal needs stabilisation)."""
    rng = np.random.default_rng(seed)
    close = base * np.cumprod(1 + rng.normal(0.004, 0.01, n))
    peak = close[-7]
    for j in range(6, 1, -1):
        close[-j] = peak * (0.965 ** (7 - j))
    close[-1] = close[-2] * 1.012
    return _frame(close, seed)


def _frame(close, seed):
    rng = np.random.default_rng(seed)
    n = len(close)
    close = np.maximum(close, 1.0)
    high = close * (1 + np.abs(rng.normal(0, 0.006, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.006, n)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    volume = rng.integers(5_000_000, 20_000_000, n).astype(float)
    return pd.DataFrame({
        "time_key": pd.date_range("2023-01-01", periods=n, freq="D"),
        "open": open_, "high": high, "low": low, "close": close, "volume": volume,
    })


@pytest.fixture
def fake_data(monkeypatch, tmp_path):
    import market_regime
    monkeypatch.setattr(market_regime, "get_regime",
                        lambda: {"regime": "bull", "vix": 14.0, "status": "ok"})
    uni = tmp_path / "universe.json"
    uni.write_text(json.dumps({"symbols": ["US.A", "US.B", "US.C", "US.D"]}),
                   encoding="utf-8")
    return str(uni)


def _run(fake_data, fetcher, **kw):
    return dp.run_pick(universe_path=fake_data, include_hot=False,
                       fetcher=fetcher, **kw)


def test_scan_returns_candidates_for_every_style(fake_data):
    def fetcher(sym, bars):
        return _pullback_df(seed=8) if sym == "US.A" else _df(seed=abs(hash(sym)) % 1000)
    rep = _run(fake_data, fetcher, top=2)
    assert rep["gate"]["block_new_longs"] is False
    assert rep["conclusion"] == "scan complete - see candidates"
    assert set(rep["candidates"]) == set(dp.DEFAULT_STYLES)
    for style, rows in rep["candidates"].items():
        assert rows, f"{style} produced no candidates"
        row = rows[0]
        assert {"symbol", "score", "close", "stop_loss", "position_pct"} <= set(row)
        assert row["score"] > 0
        assert row["stop_loss"] < row["close"]


def test_scores_are_ranked_descending(fake_data):
    rep = _run(fake_data, lambda sym, bars: _df(seed=abs(hash(sym)) % 997), top=8)
    for rows in rep["candidates"].values():
        scores = [r["score"] for r in rows]
        assert scores == sorted(scores, reverse=True)


def test_bear_regime_gates_all_longs(fake_data, monkeypatch):
    import market_regime
    monkeypatch.setattr(market_regime, "get_regime",
                        lambda: {"regime": "bear", "vix": 32.0, "status": "ok"})
    rep = _run(fake_data, lambda sym, bars: _df(seed=abs(hash(sym)) % 997))
    assert rep["gate"]["block_new_longs"] is True
    assert rep["conclusion"] == "NO_NEW_LONGS"


def test_low_liquidity_symbols_are_filtered_out(fake_data):
    good = _df(seed=1)
    bad = _df(seed=2)
    bad["close"] = 0.5                        # penny stock

    def fetcher(sym, bars):
        return good if sym == "US.A" else bad

    rep = _run(fake_data, fetcher)
    seen = {r["symbol"] for rows in rep["candidates"].values() for r in rows}
    assert "US.A" in seen
    assert seen <= {"US.A"}, f"low-liquidity symbols leaked through: {seen}"


# --- sector diversification -------------------------------------------------

def test_sector_cap_limits_concentration():
    """Top-N must not be one leveraged bet wearing five tickers."""
    rows = [{"symbol": s, "score": 90 - i} for i, s in enumerate(
        ["US.NVDA", "US.AMD", "US.INTC", "US.MU", "US.AMAT", "US.JPM"])]
    capped = dp._sector_cap(rows, max_per_sector=1)
    assert [r["symbol"] for r in capped] == ["US.NVDA", "US.JPM"]
    capped2 = dp._sector_cap(rows, max_per_sector=2)
    assert [r["symbol"] for r in capped2] == ["US.NVDA", "US.AMD", "US.JPM"]
    assert dp._sector_cap(rows, max_per_sector=0) == rows      # 0 disables


def test_run_pick_applies_sector_cap(monkeypatch, tmp_path):
    import market_regime
    monkeypatch.setattr(market_regime, "get_regime",
                        lambda: {"regime": "bull", "vix": 14.0, "status": "ok"})
    uni = tmp_path / "semis.json"
    uni.write_text(json.dumps({"symbols": ["US.NVDA", "US.AMD", "US.INTC", "US.MU"]}),
                   encoding="utf-8")

    def fetcher(sym, bars):
        return _pullback_df(seed=abs(hash(sym)) % 500)         # reversal setups

    rep = dp.run_pick(universe_path=str(uni), include_hot=False, top=4,
                      styles=["reversal"], max_per_sector=1, fetcher=fetcher)
    assert len(rep["candidates"]["reversal"]) <= 1, \
        "all-semis universe must not fill the list"


def test_hot_list_symbols_are_added(fake_data, monkeypatch):
    import tech_engine
    monkeypatch.setattr(tech_engine, "get_hot_list",
                        lambda market, top: {"status": "ok",
                                             "data": [{"code": "US.HOT1"},
                                                      {"code": "US.HOT2"}]})
    seen_symbols = []

    def fetcher(sym, bars):
        seen_symbols.append(sym)
        return _df(seed=abs(hash(sym)) % 900)

    dp.run_pick(universe_path=fake_data, include_hot=True, fetcher=fetcher, top=1)
    assert "US.HOT1" in seen_symbols
    assert "US.HOT2" in seen_symbols


def test_scan_survives_bad_fetches(fake_data):
    def fetcher(sym, bars):
        return None if sym == "US.B" else _df(seed=abs(hash(sym)) % 900)

    rep = _run(fake_data, fetcher, top=2)
    assert rep["scan"]["symbols_scanned"] == 4
    assert rep["scan"]["symbols_passed_filters"] == 3
    assert any(rows for rows in rep["candidates"].values())
