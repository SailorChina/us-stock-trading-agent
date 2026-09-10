"""Tests for backtest_engine: the portfolio-level evaluation layer.

These are pure-math tests on synthetic price paths so they run offline and
fast. The point is to lock in the *definitions* (annualisation, drawdown
sign, cost drag direction, turnover accounting) because a silent error there
would flip a strategy verdict without any test failing elsewhere.
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import backtest_engine as be


def _df_from_closes(closes, start="2020-01-01"):
    idx = pd.date_range(start, periods=len(closes), freq="B")
    return pd.DataFrame({
        "time_key": [d.strftime("%Y-%m-%d %H:%M:%S") for d in idx],
        "open": closes, "high": np.array(closes) * 1.01,
        "low": np.array(closes) * 0.99, "close": closes,
        "volume": [1_000_000] * len(closes), "last_close": closes,
    })


class TestStatsFromSeries:
    def test_flat_series_has_zero_return_and_zero_drawdown(self):
        s = be._stats_from_series([0.0] * 20, horizon=21)
        assert s["total_return_pct"] == pytest.approx(0.0, abs=1e-9)
        assert s["max_drawdown_pct"] == pytest.approx(0.0, abs=1e-9)
        assert s["hit_rate"] == 0.0

    def test_all_positive_series_has_no_drawdown(self):
        s = be._stats_from_series([0.01] * 24, horizon=21)
        assert s["max_drawdown_pct"] == pytest.approx(0.0, abs=1e-9)
        assert s["hit_rate"] == 1.0
        assert s["total_return_pct"] > 0

    def test_drawdown_is_reported_negative(self):
        s = be._stats_from_series([0.05, -0.20, 0.05, -0.10], horizon=21)
        assert s["max_drawdown_pct"] < 0

    def test_empty_input_returns_empty_dict(self):
        assert be._stats_from_series([], horizon=21) == {}

    def test_annualisation_scales_with_horizon(self):
        """Same per-period return, longer horizon -> lower annualised vol."""
        rets = [0.01, -0.01, 0.02, -0.02] * 8
        s_short = be._stats_from_series(rets, horizon=5)
        s_long = be._stats_from_series(rets, horizon=21)
        assert s_short["ann_vol_pct"] > s_long["ann_vol_pct"]


class TestCostDirection:
    def test_higher_cost_lowers_net_return(self):
        gross = [0.02, 0.01, -0.01, 0.03, 0.0, 0.02]
        turn = [1.0] * 6
        net0 = be._stats_from_series(
            [g - t * (0.0 / 10000) * 2 for g, t in zip(gross, turn)], 21)
        net8 = be._stats_from_series(
            [g - t * (8.0 / 10000) * 2 for g, t in zip(gross, turn)], 21)
        assert net8["total_return_pct"] < net0["total_return_pct"]

    def test_zero_turnover_means_no_cost(self):
        gross = [0.02, -0.01, 0.03]
        net = be._stats_from_series([g - 0.0 for g in gross], 21)
        assert net["total_return_pct"] == pytest.approx(
            be._stats_from_series(gross, 21)["total_return_pct"])


class TestBlockBootstrap:
    def test_identical_series_gives_p_near_one(self):
        """If the strategy IS the benchmark, the excess is ~0 and almost every
        resample is >= it -- so p should be large (no evidence of edge)."""
        s = [0.01, -0.02, 0.03, 0.0, -0.01] * 6
        p = be._block_bootstrap_p(s, s, n_iter=200)
        assert p is not None and p > 0.5

    def test_varying_consistent_excess_gives_small_p(self):
        """A strategy that beats the benchmark in every period by a varying
        amount: centered resampling almost never reproduces the observed mean,
        so the null is rejected."""
        port = [0.10, 0.12, 0.08, 0.11, 0.09, 0.13, 0.07, 0.10] * 4
        bench = [0.0] * 32
        p = be._block_bootstrap_p(port, bench, n_iter=500)
        assert p is not None and p < 0.05

    def test_constant_excess_gives_small_p(self):
        """Even a perfectly constant edge is detectable once the series is
        centered, because the centered null has zero variance while the
        observed mean does not."""
        p = be._block_bootstrap_p([0.10] * 30, [0.0] * 30, n_iter=300)
        assert p is not None and p < 0.05

    def test_no_edge_gives_large_p(self):
        """Zero excess -> p should be large; this is the case that catches the
        uncentered-bootstrap bug, where every series returned ~0.5 regardless."""
        import random
        rng = random.Random(0)
        port = [rng.gauss(0, 0.03) for _ in range(60)]
        p = be._block_bootstrap_p(port, [0.0] * 60, n_iter=500)
        assert p is not None and p > 0.20

    def test_returns_none_when_too_few_periods(self):
        assert be._block_bootstrap_p([0.1, 0.2], [0.0, 0.0]) is None

    def test_mismatched_lengths_return_none(self):
        assert be._block_bootstrap_p([0.1] * 10, [0.0] * 5) is None


class TestCachedFetcher:
    def test_serves_from_cache_without_network(self):
        closes = list(np.linspace(100, 200, 400))
        cache = {"US.TEST": _df_from_closes(closes)}
        f = be.cached_fetcher(cache)
        df = f("US.TEST", "1d", 300)
        assert df is not None and len(df) == 300
        assert df["close"].iloc[-1] == pytest.approx(closes[-1])

    def test_unknown_symbol_returns_none(self):
        f = be.cached_fetcher({})
        assert f("US.NOPE", "1d", 100) is None

    def test_num_larger_than_cache_returns_available_rows(self):
        closes = list(np.linspace(100, 110, 350))
        cache = {"US.TEST": _df_from_closes(closes)}
        f = be.cached_fetcher(cache)
        df = f("US.TEST", "1d", 9999)
        assert len(df) == 350


class TestBacktestStyleGuards:
    def test_unknown_style_is_rejected(self):
        cache = {"US.A": _df_from_closes(list(np.linspace(100, 120, 400)))}
        r = be.backtest_style("definitely_not_a_style", cache)
        assert r["status"] == "unknown_style"

    def test_tiny_universe_reports_insufficient_periods(self):
        cache = {"US.A": _df_from_closes(list(np.linspace(100, 120, 400)))}
        r = be.backtest_style("mom_12_1_raw", cache, min_names=30)
        assert r["status"] in ("insufficient_periods", "insufficient_universe", "ok")
        # with 1 symbol it can never reach min_names=30 names
        assert r["status"] == "insufficient_periods"


class TestLoadCache:
    def test_loads_real_cache_if_present(self):
        """Smoke test against the real cached history when this checkout has
        it; skip silently in a clean clone so CI does not depend on data."""
        if not os.path.isdir(be.CACHE_DIR):
            pytest.skip("no local history cache")
        cache = be.load_cache()
        if not cache:
            pytest.skip("cache empty")
        assert len(cache) > 100
        for sym, df in list(cache.items())[:5]:
            assert sym.startswith("US.")
            assert len(df) >= 300
            assert list(df.columns[:3]) == ["time_key", "open", "high"]
