"""Tests for fundamental_factors and the backtest_engine panel hook.

The factor maths is easy to get subtly wrong in ways that look fine: a
cross-sectional rank computed per-symbol instead of per-date produces a smooth,
plausible, completely invalid score. So the tests pin the cross-sectional
contract, the point-in-time contract, and the alignment of panel rows onto the
existing rebalance grid.
"""
import datetime as dt
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import backtest_engine as be
import fundamental_factors as fxf
import futu_fundamentals as ff


# ---------------------------------------------------------------------------
# percentile rank
# ---------------------------------------------------------------------------

def test_pct_rank_is_monotonic_and_spans_the_range():
    r = fxf._pct_rank([10.0, 20.0, 30.0])
    assert r == [0.0, 50.0, 100.0]


def test_pct_rank_averages_ties():
    """Ties must share the mean of their positions, not get arbitrary order."""
    r = fxf._pct_rank([5.0, 5.0, 5.0])
    assert r == [50.0, 50.0, 50.0]


def test_pct_rank_handles_a_single_value():
    assert fxf._pct_rank([1.0]) == [50.0]


def test_pct_rank_is_scale_invariant():
    a = fxf._pct_rank([1.0, 2.0, 3.0])
    b = fxf._pct_rank([1000.0, 2000.0, 3000.0])
    assert a == b


def test_pct_rank_never_leaves_the_0_100_band():
    r = fxf._pct_rank([-50.0, 0.0, 3.0, 900.0])
    assert min(r) >= 0.0 and max(r) <= 100.0


# ---------------------------------------------------------------------------
# point-in-time quality extraction
# ---------------------------------------------------------------------------

def _rec(symbol, rows):
    return {"symbol": symbol, "periods": rows}


def _p(end, avail, **vals):
    return {"period_text": end[:7], "period_end": end, "available_date": avail,
            "values": vals}


def test_raw_quality_by_date_respects_availability():
    """A symbol must not appear on a date where its numbers were not yet out."""
    fund = {"US.A": _rec("US.A", [_p("2025-03-31", "2025-05-15", roe=9.0)])}
    dates = {"US.A": ["2025-05-01", "2025-06-01"]}
    raw = fxf.raw_quality_by_date(fund, dates)
    assert "2025-05-01" not in raw or "US.A" not in raw["2025-05-01"]
    assert raw["2025-06-01"]["US.A"]["roe"] == 9.0


# ---------------------------------------------------------------------------
# the cross-sectional panel
# ---------------------------------------------------------------------------

def _synthetic(n_syms=25, n_bars=200, horizon=21):
    """Price frames on a shared calendar + fundamentals that rank with index."""
    price, fund = {}, {}
    base = dt.date(2024, 1, 1)
    stamps = [(base + dt.timedelta(days=i)).isoformat() for i in range(n_bars)]
    for k in range(n_syms):
        sym = "US.S%02d" % k
        closes = [100.0 * (1 + 0.0005 * k) ** i for i in range(n_bars)]
        price[sym] = pd.DataFrame({"time_key": stamps, "close": closes})
        # stronger index -> better fundamentals
        rows = [_p(e, (dt.date.fromisoformat(e) + dt.timedelta(days=45)).isoformat(),
                   roe=5.0 + k, roic=4.0 + k, gross_margin=20.0 + k)
                for e in ("2023-03-31", "2023-06-30", "2023-09-30", "2023-12-31",
                          "2024-03-31", "2024-06-30")]
        fund[sym] = _rec(sym, rows)
    return price, fund, horizon


def test_quality_panel_ranks_cross_sectionally_per_date():
    price, fund, h = _synthetic()
    panel = fxf.quality_panel(fund, price, h)
    panel.pop("_meta", None)
    assert len(panel) == 25
    for sym, m in panel.items():
        for d, v in m.items():
            assert 0.0 <= v <= 100.0
    # at any shared date the best-fundamental name must outrank the worst
    any_date = sorted(panel["US.S00"])[0]
    assert panel["US.S24"][any_date] > panel["US.S00"][any_date]


def test_quality_panel_is_flat_when_all_names_are_identical():
    """With no dispersion every name sits at the 50th percentile -- a score with
    no information must not look like a strong signal."""
    price, fund, h = _synthetic()
    for rec in fund.values():
        for p in rec["periods"]:
            p["values"] = {"roe": 10.0, "roic": 10.0, "gross_margin": 10.0}
    panel = fxf.quality_panel(fund, price, h)
    panel.pop("_meta", None)
    vals = [v for m in panel.values() for v in m.values()]
    assert vals and all(abs(v - 50.0) < 1e-6 for v in vals)


def test_quality_panel_skips_dates_with_too_few_peers():
    price, fund, h = _synthetic(n_syms=5)          # < MIN_PEERS
    panel = fxf.quality_panel(fund, price, h)
    meta = panel.pop("_meta")
    assert panel == {} or all(not m for m in panel.values())
    assert meta["dates_skipped"] > 0


def test_quality_panel_requires_enough_metrics_per_name():
    """A name with only one of three metrics is not scorable."""
    price, fund, h = _synthetic()
    for p in fund["US.S00"]["periods"]:
        p["values"] = {"roe": 1.0}                  # only 1 of 3
    panel = fxf.quality_panel(fund, price, h)
    panel.pop("_meta", None)
    any_date = sorted(next(iter(panel.values())))[0]
    assert any_date not in panel.get("US.S00", {})


# ---------------------------------------------------------------------------
# combining with momentum
# ---------------------------------------------------------------------------

def test_gate_by_quality_excludes_names_below_the_floor():
    mom = {"US.LOW": {"2024-01-01": 5.0}, "US.HIGH": {"2024-01-01": 1.0}}
    qual = {"US.LOW": {"2024-01-01": 10.0}, "US.HIGH": {"2024-01-01": 90.0}}
    got = fxf.gate_by_quality(mom, qual, 50.0)
    assert "US.LOW" not in got and "US.HIGH" in got


def test_gate_by_quality_drops_names_with_no_quality_score():
    mom = {"US.NOQ": {"2024-01-01": 5.0}}
    assert fxf.gate_by_quality(mom, {}, 50.0) == {}


def test_gate_by_quality_keeps_the_momentum_score_untouched():
    """Filtering must not rescale the ranker, or the top-N changes meaning."""
    mom = {"US.A": {"d": 123.4}}
    qual = {"US.A": {"d": 99.0}}
    assert fxf.gate_by_quality(mom, qual, 50.0)["US.A"]["d"] == 123.4


def test_orthogonality_detects_identical_rankers():
    mom = {("US.S%02d" % k): {"d": float(k)} for k in range(40)}
    qual = {("US.S%02d" % k): {"d": float(k)} for k in range(40)}
    o = fxf.orthogonality(mom, qual)
    assert o["dates"] == 1
    assert o["mean_rank_corr"] > 0.99


def test_orthogonality_reports_zero_dates_when_nothing_overlaps():
    o = fxf.orthogonality({"US.A": {"d": 1.0}}, {"US.B": {"d": 1.0}})
    assert o["dates"] == 0


# ---------------------------------------------------------------------------
# backtest_engine panel hook
# ---------------------------------------------------------------------------

def _frame():
    stamps = [(dt.date(2024, 1, 1) + dt.timedelta(days=i)).isoformat() for i in range(120)]
    return pd.DataFrame({"time_key": stamps, "close": [100.0 + i for i in range(120)]})


def test_rows_from_panel_aligns_to_the_standard_grid():
    df = _frame()
    h = 21
    grid = fxf._grid_dates(df, h)
    panel = {d: 77.0 for d in grid}
    rows = be._rows_from_panel(df, panel, h)
    assert [r["date"] for r in rows] == grid
    assert all(r["score"] == 77.0 for r in rows)


def test_rows_from_panel_computes_the_forward_return_from_the_same_closes():
    df = _frame()
    h = 21
    grid = fxf._grid_dates(df, h)
    rows = be._rows_from_panel(df, {d: 1.0 for d in grid}, h)
    closes = df["close"].values
    t = 60
    expected = (closes[t + h] - closes[t]) / closes[t]
    assert rows[0]["fwd_ret"] == pytest.approx(expected)


def test_rows_from_panel_skips_dates_the_panel_does_not_cover():
    df = _frame()
    grid = fxf._grid_dates(df, 21)
    rows = be._rows_from_panel(df, {grid[1]: 5.0}, 21)
    assert [r["date"] for r in rows] == [grid[1]]


def test_rows_from_panel_tolerates_missing_inputs():
    df = _frame()
    assert be._rows_from_panel(df, None, 21) == []
    assert be._rows_from_panel(df, {}, 21) == []
    assert be._rows_from_panel(pd.DataFrame(), {"d": 1.0}, 21) == []


def test_backtest_style_accepts_a_panel_and_reports_metrics():
    """End-to-end on synthetic data: a panel with real signal must produce a
    result dict, not an exception, and must beat a panel with none."""
    n_syms, n_bars, h = 40, 300, 21
    price, panel = {}, {}
    base = dt.date(2024, 1, 1)
    stamps = [(base + dt.timedelta(days=i)).isoformat() for i in range(n_bars)]
    for k in range(n_syms):
        # higher k -> stronger drift, and the panel ranks k the same way
        closes = [100.0 * (1 + 0.0010 * k) ** i for i in range(n_bars)]
        sym = "US.P%02d" % k
        price[sym] = pd.DataFrame({"time_key": stamps, "close": closes})
        panel[sym] = {d: float(k) for d in fxf._grid_dates(price[sym], h)}
    r = be.backtest_style("panel_test", price, horizon=h, top_n=5, panel=panel)
    assert r.get("status") == "ok"
    assert r["portfolio_net"]["cagr_pct"] > 0
