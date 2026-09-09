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


# --------------------------------------------------------------------------
# cross-sectional validation
# --------------------------------------------------------------------------

def test_newey_west_inflates_se_when_autocorrelated():
    """An autocorrelated IC series must get a WIDER standard error."""
    rng = np.random.default_rng(0)
    x, cur = [], 0.0
    for _ in range(300):
        cur = 0.8 * cur + rng.normal(0, 1)
        x.append(cur)
    nw = sv.newey_west_se(x)
    naive = float(np.std(x, ddof=1)) / np.sqrt(len(x))
    assert nw > naive * 1.5, "HAC should widen the SE under autocorrelation"


def test_newey_west_close_to_naive_for_iid():
    rng = np.random.default_rng(1)
    x = list(rng.normal(0, 1, 300))
    nw = sv.newey_west_se(x)
    naive = float(np.std(x, ddof=1)) / np.sqrt(len(x))
    assert 0.6 < nw / naive < 1.6


def test_ic_stats_significant_on_stable_ic():
    ics = [0.15 + ((i % 3) - 1) * 0.001 for i in range(40)]
    st = sv.ic_stats(ics)
    assert st["mean_ic"] == pytest.approx(0.15, abs=0.01)
    assert st["significant"] is True
    assert st["t_stat_newey_west"] > 1.96


def test_ic_stats_not_significant_on_zero_mean_noise():
    ics = [0.01 if i % 2 == 0 else -0.01 for i in range(40)]
    st = sv.ic_stats(ics)
    assert st["significant"] is False


def test_ic_stats_reports_both_t_stats():
    st = sv.ic_stats([0.12] * 10 + [0.08] * 10)
    assert st["t_stat_naive"] is not None
    assert st["t_stat_newey_west"] is not None


def test_cross_section_detects_planted_signal(monkeypatch):
    """When high scores genuinely earn more, cross-sectional IC must show it."""
    syms = [f"US.S{i:02d}" for i in range(20)]
    scores = {s: 20 + i * 3 for i, s in enumerate(syms)}

    def fake_history(symbol, df, horizon=5, window_bars=120, min_bars=60, step=1, scorer=None):
        n = len(df)
        base = scores[symbol]
        out = []
        for t in range(60, n - horizon, step):
            sc = base + (t % 3) * 0.1
            out.append({"bar": t, "date": f"d{t}", "score": sc,
                        "fwd_ret": (sc - 50) / 1000.0})
        return out

    monkeypatch.setattr(sv, "score_history", fake_history)
    rep = sv.validate_cross_section(syms, horizon=5, bars=200, quantile=0.2,
                                    fetcher=lambda s, tf, b: _df(200, seed=abs(hash(s)) % 1000))

    assert rep["status"] == "ok", rep.get("fetch_failures") or rep
    assert rep["periods"] >= 12
    assert rep["information_coefficient"]["mean_ic"] > 0.9
    assert rep["information_coefficient"]["significant"] is True
    assert rep["verdict"] == "predictive"
    assert rep["portfolio"]["excess_pct"] > 0


def test_cross_section_uses_non_overlapping_windows(monkeypatch):
    """step must equal horizon, or forward windows overlap and n is inflated."""
    seen = {}

    def fake_history(symbol, df, horizon=5, window_bars=120, min_bars=60, step=1, scorer=None):
        seen["horizon"], seen["step"] = horizon, step
        return [{"bar": 60 + i * 5, "date": f"d{i}", "score": 50.0 + i,
                 "fwd_ret": 0.01} for i in range(20)]

    syms = [f"US.S{i:02d}" for i in range(12)]
    monkeypatch.setattr(sv, "score_history", fake_history)
    sv.validate_cross_section(syms, horizon=7, bars=200,
                              fetcher=lambda s, tf, b: _df(200))
    assert seen["horizon"] == 7
    assert seen["step"] == 7


def test_cross_section_insufficient_universe():
    rep = sv.validate_cross_section(["US.A", "US.B"], horizon=5, bars=200,
                                    fetcher=lambda s, tf, b: None)
    assert rep["status"] == "insufficient_universe"


def test_cross_section_insufficient_periods_verdict(monkeypatch):
    """Very few rebalance dates must NOT be reported as a finding."""
    def fake_history(symbol, df, horizon=5, window_bars=120, min_bars=60, step=1, scorer=None):
        return [{"bar": 60, "date": "d1", "score": 60.0, "fwd_ret": 0.02},
                {"bar": 65, "date": "d2", "score": 40.0, "fwd_ret": -0.02}]

    syms = [f"US.S{i:02d}" for i in range(12)]
    monkeypatch.setattr(sv, "score_history", fake_history)
    rep = sv.validate_cross_section(syms, horizon=5, bars=200,
                                    fetcher=lambda s, tf, b: _df(200))
    assert rep["verdict"] == "insufficient_periods"


# --- style scorer plumbing (daily_pick styles share the validator) ---------

def test_score_history_accepts_custom_scorer():
    """The same pure scorer used live must be usable for validation."""
    df = _df(200)
    rows = sv.score_history("US.X", df, horizon=5, window_bars=120, step=5,
                            scorer=lambda w: {"score": 61.0})
    assert rows
    assert all(r["score"] == 61.0 for r in rows)


def test_cross_section_rejects_unknown_style():
    rep = sv.validate_cross_section(["US.A", "US.B"], style="not_real",
                                    fetcher=lambda s, tf, b: _df(200))
    assert rep["status"] == "unknown_style"
    assert "momentum" in rep["known_styles"]


def test_cross_section_validates_a_style(monkeypatch):
    """A planted style ranker must be measurable through the same path."""
    syms = [f"US.S{i:02d}" for i in range(14)]
    base = {s: 20 + i * 5 for i, s in enumerate(syms)}

    def fake_history(symbol, df, horizon=5, window_bars=120, min_bars=60,
                     step=1, scorer=None):
        n = len(df)
        out = []
        for t in range(60, n - horizon, step):
            sc = base[symbol] + (t % 2) * 0.2
            out.append({"bar": t, "date": f"d{t}", "score": sc,
                        "fwd_ret": (sc - 50) / 1000.0})
        return out

    monkeypatch.setattr(sv, "score_history", fake_history)
    rep = sv.validate_cross_section(syms, horizon=5, bars=200, style="momentum",
                                    fetcher=lambda s, tf, b: _df(200))
    assert rep["status"] == "ok"
    assert rep["style"] == "momentum"
    assert rep["information_coefficient"]["mean_ic"] > 0.9
    assert rep["verdict"] == "predictive"


# --- event study (rare-signal styles: reversal) ----------------------------

def _dip_recovery_df(n=240, base=100.0, seed=9, dip_every=24, dip_gap=60):
    """Steady uptrend punctuated by 3% dips that mean-revert quickly.

    Signal days (the dip bar) are followed by stronger-than-normal returns,
    so an honest event study must find a positive per-symbol excess.
    """
    rng = np.random.default_rng(seed)
    c = [float(base)]
    for i in range(1, n):
        prev = c[-1]
        if i >= dip_gap and (i - dip_gap) % dip_every == 0:
            c.append(prev * 0.97)                     # dip bar
        elif 1 <= (i - dip_gap) % dip_every <= 4:
            c.append(prev * 1.010)                    # recovery: strong days
        else:
            c.append(prev * (1.0 + rng.normal(0.002, 0.004)))
    close = np.asarray(c)
    high = close * 1.005
    low = close * 0.995
    open_ = np.concatenate([[close[0]], close[:-1]])
    volume = np.full(n, 5_000_000.0)
    return pd.DataFrame({
        "time_key": pd.date_range("2023-01-01", periods=n, freq="D"),
        "open": open_, "high": high, "low": low, "close": close, "volume": volume,
    })


def _dip_detector():
    """Detect the dip bar: close dropped ~3% vs the prior bar."""
    def _score(window):
        c = window["close"].values
        hit = (len(c) >= 2 and c[-1] < c[-2] * 0.98)
        return {"score": 100.0 if hit else 0.0}
    return _score


def test_event_study_finds_planted_signal(monkeypatch):
    syms = [f"US.D{i}" for i in range(6)]
    monkeypatch.setattr(sv, "score_history", lambda *a, **k: None)  # unused here
    rep = sv.validate_events(
        syms, style="reversal", threshold=50.0, horizon=10, bars=240,
        fetcher=lambda s, tf, b: _dip_recovery_df(seed=10 + abs(hash(s)) % 7),
        scorer=_dip_detector())
    assert rep["status"] == "ok"
    assert rep["symbols_active"] == len(syms)
    assert rep["signals"] >= len(syms)
    assert rep["mean_excess_pct"] > 0
    assert rep["t_stat"] is not None and rep["t_stat"] > 2.0, rep
    assert rep["verdict"] == "predictive"
    assert all(p["excess"] > 0 for p in rep["per_symbol"]), \
        "every symbol's signal days should beat its own normal days"


def test_event_study_signals_do_not_overlap():
    """Dense dips with a 10-bar horizon must not be counted more than once."""
    df = _dip_recovery_df(n=300, dip_every=12, dip_gap=60)   # a dip every 12 bars
    rep = sv.validate_events(["US.D0"], style="reversal", threshold=50.0,
                             horizon=10, bars=300, min_active=1,
                             fetcher=lambda s, tf, b: df, scorer=_dip_detector())
    max_non_overlap = (300 - 60) // 10 + 1
    assert rep["signals"] <= max_non_overlap, \
        f"overlapping signals counted: {rep['signals']} > {max_non_overlap}"


def test_event_study_insufficient_signals():
    rep = sv.validate_events(["US.A", "US.B"], style="reversal", threshold=50.0,
                             bars=200, fetcher=lambda s, tf, b: _df(200),
                             scorer=lambda w: {"score": 0.0})
    assert rep["verdict"] == "insufficient_signals"


def test_event_study_rejects_unknown_style():
    rep = sv.validate_events(["US.A"], style="nope", bars=200,
                             fetcher=lambda s, tf, b: _df(200))
    assert rep["status"] == "unknown_style"
    assert "reversal" in rep["known_styles"]
