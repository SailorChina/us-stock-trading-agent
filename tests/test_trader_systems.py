"""Offline tests: quantified famous-trader systems (trader_systems.py).

These lock in each system's CONTRACT and its REJECTION logic. The rejections
matter more than the scores: a system that never rejects anything is not
implementing the rule it claims to implement. Every test runs on synthetic
price paths, so the suite is pure and fast.
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import trader_systems as ts


def _df(path_fn, n=320, seed=7):
    rng = np.random.default_rng(seed)
    close = np.maximum(path_fn(n, rng), 1.0)
    return pd.DataFrame({
        "time_key": pd.date_range("2022-01-03", periods=n, freq="B"),
        "open": np.concatenate([[close[0]], close[:-1]]),
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": rng.integers(2_000_000, 20_000_000, n).astype(float),
    })


def _smooth_uptrend(n, rng):
    """A clean, low-noise advance - should pass trend filters and fit well."""
    return 100 * np.cumprod(1 + rng.normal(0.0025, 0.004, n))


def _trend_with_noise(noise):
    """Same drift, different noise level. Isolates the R^2 term in Clenow:
    with an identical mean return the only difference is how well the log
    price fits a straight line."""
    def _f(n, rng):
        return 100 * np.cumprod(1 + rng.normal(0.003, noise, n))
    return _f


def _downtrend(n, rng):
    return 100 * np.cumprod(1 + rng.normal(-0.003, 0.012, n))


def _steep_uptrend(n, rng):
    """~1%/day. Price runs well ABOVE its 20-EMA, which is an extension and
    must not be mistaken for a pullback into the EMA."""
    return 100 * np.cumprod(1 + rng.normal(0.010, 0.003, n))


def _spiky(n, rng):
    """Steady advance punctuated by one +25% day - Clenow must reject this."""
    c = 100 * np.cumprod(1 + rng.normal(0.002, 0.006, n))
    tail_len = 39
    c[-40] = c[-41] * 1.25                              # the spike itself
    c[-tail_len:] = c[-40] * np.cumprod(1 + rng.normal(0.002, 0.006, tail_len))
    return c


def _runup_then_tight_flag(n, rng):
    """The HTF shape: a long violent run-up, then a short tight flag.

    The flag must be SHORTER than the flag-window the scorer looks back over
    (tight_bars=15, runup_bars=60), otherwise the measured "run-up" lands
    entirely inside the flag and reads as ~0%.
    """
    tight = 20
    c = 100 * np.cumprod(1 + rng.normal(0.009, 0.010, n - tight))
    tail = c[-1] * np.cumprod(1 + rng.normal(0.0, 0.002, tight))
    return np.concatenate([c, tail])


def _vcp_shape(n, rng):
    """Successive contractions of 25% -> 12% -> 5% across the final 120 bars.

    Each contraction is preceded by an up-leg, and the up-legs are sized so the
    series ENDS above where the consolidation began. That matters: a real VCP
    sits at the top of a prior advance (Minervini requires price above the
    200-day MA), so a fixture that drifts net-lower would be rejected by the
    MA200 gate before the contraction logic is ever exercised.
    """
    base = 100 * np.cumprod(1 + rng.normal(0.002, 0.004, n - 120))
    seg = 40
    out = list(base)
    px = base[-1]
    for depth, up in ((0.25, 0.30), (0.12, 0.20), (0.05, 0.12)):
        peak = px * (1 + up)
        out.extend(list(np.linspace(px, peak, seg // 2)))
        out.extend(list(np.linspace(peak, peak * (1 - depth), seg - seg // 2)))
        px = peak * (1 - depth)
    return np.array(out[:n])


# ---------------------------------------------------------------------------
# contract
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(ts.SYSTEMS))
def test_every_system_returns_the_standard_contract(name):
    r = ts.SYSTEMS[name](_df(_smooth_uptrend))
    assert set(("score", "raw", "reasons", "stats")).issubset(r)
    assert 0.0 <= r["score"] <= 100.0
    assert isinstance(r["raw"], (int, float))
    assert isinstance(r["reasons"], list) and r["reasons"]


@pytest.mark.parametrize("name", sorted(ts.SYSTEMS))
def test_short_history_is_rejected_not_guessed(name):
    """50 bars is below every system's minimum (the shortest, Turtle, needs
    60), so each must refuse rather than score on partial data."""
    r = ts.SYSTEMS[name](_df(_smooth_uptrend, n=50))
    assert r["score"] == 0.0
    assert r["raw"] == 0.0


@pytest.mark.parametrize("name", sorted(ts.SYSTEMS))
def test_systems_are_pure_and_never_touch_the_network(name):
    df = _df(_smooth_uptrend)
    a = ts.SYSTEMS[name](df)
    b = ts.SYSTEMS[name](df.copy())
    assert a["score"] == b["score"] and a["raw"] == b["raw"]


@pytest.mark.parametrize("name", sorted(ts.SYSTEMS))
def test_scoring_does_not_mutate_the_input(name):
    df = _df(_smooth_uptrend)
    before = df["close"].tolist()
    ts.SYSTEMS[name](df)
    assert df["close"].tolist() == before


# ---------------------------------------------------------------------------
# Clenow
# ---------------------------------------------------------------------------

def test_clenow_rejects_below_the_100_day_ma():
    """Clenow disqualifies any stock under its 100-day MA. Guard the rule."""
    r = ts.clenow_score(_df(_downtrend))
    assert r["score"] == 0.0
    assert any("MA" in x for x in r["reasons"])


def test_clenow_rejects_a_single_day_spike():
    """A +25% single day violates his 15% spike limit and must be excluded."""
    r = ts.clenow_score(_df(_spiky))
    assert r["score"] == 0.0
    assert any("spike" in x.lower() for x in r["reasons"])


def test_clenow_rewards_a_smooth_trend_over_a_choppy_one():
    """The R^2 multiplier exists to prefer a clean advance. Same drift, only
    the noise differs - so the smoother series must show a better fit and a
    higher rank score."""
    smooth = ts.clenow_score(_df(_trend_with_noise(0.003), seed=99))
    choppy = ts.clenow_score(_df(_trend_with_noise(0.030), seed=99))
    assert smooth["score"] > 0 and choppy["score"] > 0      # both pass the gates
    assert smooth["stats"]["r2"] > choppy["stats"]["r2"]
    assert smooth["raw"] > choppy["raw"]


def test_clenow_stats_report_slope_and_r2():
    r = ts.clenow_score(_df(_smooth_uptrend))
    assert "ann_slope_pct" in r["stats"] and "r2" in r["stats"]
    assert 0.0 <= r["stats"]["r2"] <= 1.0


# ---------------------------------------------------------------------------
# Minervini trend template
# ---------------------------------------------------------------------------

def test_minervini_passes_a_clean_uptrend_with_all_seven_checks():
    r = ts.minervini_score(_df(_smooth_uptrend))
    assert r["stats"]["checks_passed"] == 7
    assert r["score"] > 0


def test_minervini_rejects_a_downtrend():
    r = ts.minervini_score(_df(_downtrend))
    assert r["score"] == 0.0
    assert r["stats"]["checks_passed"] < 7


def test_minervini_reports_proximity_to_the_52_week_high():
    r = ts.minervini_score(_df(_smooth_uptrend))
    assert "pct_of_52w_high" in r["stats"]
    assert r["stats"]["pct_of_52w_high"] > 0


# ---------------------------------------------------------------------------
# High Tight Flag
# ---------------------------------------------------------------------------

def test_htf_requires_a_run_up():
    """No prior advance means no flag to trade - must reject, not score."""
    r = ts.high_tight_flag_score(_df(_downtrend))
    assert r["score"] == 0.0
    assert any("run-up" in x for x in r["reasons"])


def test_htf_accepts_a_runup_followed_by_a_tight_flag():
    r = ts.high_tight_flag_score(_df(_runup_then_tight_flag))
    assert r["score"] > 0
    assert r["stats"]["flag_range_pct"] < 15.0
    assert r["stats"]["runup_pct"] > 30.0


def test_htf_rejects_a_loose_flag():
    """A violent run-up followed by an equally violent pullback is not an HTF."""
    def wild_tail(n, rng):
        c = _runup_then_tight_flag(n, rng)
        c[-15:] = c[-16] * np.cumprod(1 + rng.normal(-0.01, 0.05, 15))
        return c
    r = ts.high_tight_flag_score(_df(wild_tail))
    assert r["score"] == 0.0


# ---------------------------------------------------------------------------
# Pullback to the 20-EMA
# ---------------------------------------------------------------------------

def test_pullback_rejects_a_broken_uptrend():
    r = ts.pullback_ema_score(_df(_downtrend))
    assert r["score"] == 0.0
    assert any("uptrend" in x for x in r["reasons"])


def test_pullback_requires_the_price_to_actually_touch_the_ema():
    """A stock running ~10% above its 20-EMA is extended, not pulling back."""
    r = ts.pullback_ema_score(_df(_steep_uptrend))
    assert r["score"] == 0.0
    assert any("EMA" in x for x in r["reasons"])


def test_pullback_fires_when_price_returns_to_the_ema_in_an_uptrend():
    """Drive price back onto a rising 20-EMA with an up-close and it should
    score, which is the whole point of the setup."""
    def touch_then_confirm(n, rng):
        c = 100 * np.cumprod(1 + rng.normal(0.004, 0.005, n))
        ema = c[-20]                                  # park the recent bars flat
        c[-12:] = ema * np.linspace(1.0, 1.001, 12)
        c[-1] = c[-2] * 1.004                         # stabilising up day
        return c
    r = ts.pullback_ema_score(_df(touch_then_confirm))
    assert r["score"] > 0
    assert abs(r["stats"]["dist_ema_pct"]) <= 4.0


# ---------------------------------------------------------------------------
# VCP
# ---------------------------------------------------------------------------

def test_vcp_rejects_a_stock_below_its_200_day_ma():
    r = ts.vcp_score(_df(_downtrend))
    assert r["score"] == 0.0


def test_vcp_accepts_progressively_shallower_contractions():
    r = ts.vcp_score(_df(_vcp_shape))
    assert r["score"] > 0
    depths = r["stats"]["depths_pct"]
    assert depths[-1] < depths[0]           # tightening, as designed
    assert r["stats"]["tightening"] > 1.0


# ---------------------------------------------------------------------------
# Turtle channel breakout
# ---------------------------------------------------------------------------

def test_turtle_scores_a_breakout_above_a_rangebound_stock():
    r = ts.turtle_breakout_score(_df(_smooth_uptrend))
    assert r["score"] > 0
    assert "channel_pos" in r["stats"]


def test_turtle_rejects_insufficient_history():
    r = ts.turtle_breakout_score(_df(_smooth_uptrend, n=40))
    assert r["score"] == 0.0


# ---------------------------------------------------------------------------
# registry / wiring
# ---------------------------------------------------------------------------

def test_systems_registry_exposes_six_named_systems():
    assert set(ts.SYSTEMS) == {"clenow", "minervini", "htf", "pullback_ema", "vcp", "turtle55"}


def test_systems_are_registered_into_stock_selector_styles():
    """The picker and validator must reach these through the same dispatch as
    our own factors, otherwise they cannot be measured end to end."""
    import stock_selector as sel
    for name in ts.SYSTEMS:
        assert name in sel.STYLES
        assert callable(sel.STYLES[name])


def test_registration_did_not_displace_our_own_styles():
    import stock_selector as sel
    for name in ("mom_12_1_raw", "mom_12_1", "momentum", "reversal", "quality",
                 "st_reversal", "low_vol"):
        assert name in sel.STYLES


def test_daily_pick_default_is_still_only_the_validated_factor():
    """A famous name must never silently become the default buy list."""
    import daily_pick
    assert daily_pick.DEFAULT_STYLES == ["mom_12_1_raw"]
