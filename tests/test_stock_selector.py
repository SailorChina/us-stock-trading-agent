"""Offline tests: stock_selector factor engine (v3.4.0).

The critical properties: scores are pure functions of a DataFrame (no network,
no look-ahead), each style is directionally sane on constructed data, and a
falling knife is never offered by the reversal ranker.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import numpy as np
import pandas as pd
import pytest

import stock_selector as sel


def _df(close_path, n=320, base=100.0, seed=3):
    rng = np.random.default_rng(seed)
    close = close_path(base, n, rng)
    close = np.maximum(close, 1.0)
    high = close * (1 + np.abs(rng.normal(0, 0.006, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.006, n)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    volume = rng.integers(2_000_000, 20_000_000, n).astype(float)
    return pd.DataFrame({
        "time_key": pd.date_range("2023-01-01", periods=n, freq="D"),
        "open": open_, "high": high, "low": low, "close": close, "volume": volume,
    })


def _uptrend(base, n, rng):
    return base * np.cumprod(1 + rng.normal(0.0035, 0.012, n))


def _pullback_in_uptrend(base, n, rng, last_bar=1.012):
    """Uptrend with a compounding pullback that ENDS on an up day (stabilising)."""
    c = base * np.cumprod(1 + rng.normal(0.004, 0.01, n))
    peak = c[-7]
    for j in range(6, 1, -1):                  # declining bars
        c[-j] = peak * (0.965 ** (7 - j))
    c[-1] = c[-2] * last_bar                   # stabilising day
    return c


def _downtrend(base, n, rng):
    return base * np.cumprod(1 + rng.normal(-0.004, 0.012, n))


def _steep(base, n, rng):
    """Strong 12-1 momentum (~+60%) so the display score saturates at 100."""
    c = base * np.cumprod(1 + rng.normal(0.0018, 0.008, n))
    c[-21:] = c[-22]                            # flat last month (skip window)
    return c


def _steeper(base, n, rng):
    """Even stronger 12-1 momentum (~+130%), also saturating at 100."""
    c = base * np.cumprod(1 + rng.normal(0.0042, 0.008, n))
    c[-21:] = c[-22]
    return c


def _flat(base, n, rng):
    return np.full(n, base)


def _chaotic(base, n, rng):
    return base * np.cumprod(1 + rng.choice([-0.05, 0.0, 0.05], size=n))


# --- shape / purity ---------------------------------------------------------

def test_scores_are_pure_dicts():
    for style in ("momentum", "reversal", "quality"):
        r = sel.score_style(style, _df(_uptrend))
        assert isinstance(r, dict) and "score" in r and "reasons" in r
        assert 0.0 <= r["score"] <= 100.0


def test_unknown_style_is_handled():
    r = sel.score_style("not_a_style", _df(_uptrend))
    assert r["score"] == 0.0


def test_short_history_is_rejected_not_crash():
    short = _df(_uptrend, n=30)
    for style in ("momentum", "reversal", "quality"):
        r = sel.score_style(style, short)
        assert r["score"] == 0.0


# --- momentum ---------------------------------------------------------------

def test_momentum_favours_a_trending_name():
    trend = sel.momentum_score(_df(_uptrend))
    flat = sel.momentum_score(_df(_flat))
    assert trend["score"] > flat["score"]


def test_momentum_penalises_downtrend():
    up = sel.momentum_score(_df(_uptrend))
    down = sel.momentum_score(_df(_downtrend))
    assert up["score"] > 50
    assert down["score"] < 35


# --- reversal ---------------------------------------------------------------

def test_reversal_catches_pullback_inside_uptrend():
    r = sel.reversal_score(_df(_pullback_in_uptrend))
    assert r["score"] > 30, f"pullback in uptrend not flagged: {r}"


def test_reversal_rejects_falling_knife():
    """No prior uptrend -> the pullback is a knife, score must be 0."""
    r = sel.reversal_score(_df(_downtrend))
    assert r["score"] == 0.0
    assert any("falling knife" in reason or "uptrend" in reason
               for reason in r["reasons"])


def test_reversal_waits_for_stabilisation():
    """A pullback that is STILL FALLING must not be a candidate."""
    still = _df(lambda b, n, r: _pullback_in_uptrend(b, n, r, last_bar=0.975))
    r = sel.reversal_score(still)
    assert r["score"] == 0.0
    assert any("still falling" in reason for reason in r["reasons"])


def test_reversal_rewards_reclaiming_ma5():
    """The confirmation branch must distinguish a MA5 reclaim from a weak up day.

    Note: a violent bounce scores LOWER overall on purpose — it has already
    eaten into the pullback discount and the oversold reading, so the entry is
    worse. What must differ is the confirmation branch itself.
    """
    weak = _df(lambda b, n, r: _pullback_in_uptrend(b, n, r, last_bar=1.005))
    strong = _df(lambda b, n, r: _pullback_in_uptrend(b, n, r, last_bar=1.08))
    rw, rs = sel.reversal_score(weak), sel.reversal_score(strong)
    assert any("reclaimed MA5" in reason for reason in rs["reasons"])
    assert any("still below MA5" in reason for reason in rw["reasons"])
    assert rs["score"] > 0 and rw["score"] > 0


def test_reversal_ignores_a_quiet_uptrend():
    """No pullback (making highs) -> no reversal setup."""
    r = sel.reversal_score(_df(_uptrend))
    assert r["score"] == 0.0
    assert any("pullback" in reason for reason in r["reasons"])


# --- quality ----------------------------------------------------------------

def test_quality_prefers_calm_over_chaotic():
    calm = sel.quality_score(_df(lambda b, n, r: b * np.cumprod(1 + r.normal(0.001, 0.008, n))))
    wild = sel.quality_score(_df(_chaotic))
    assert calm["score"] > wild["score"]


def test_quality_rejects_penny_stock():
    penny = sel.quality_score(_df(_uptrend, base=0.5), min_price=3.0)
    assert penny["score"] == 0.0
    assert any("price" in reason for reason in penny["reasons"])


# --- entry context ----------------------------------------------------------

def test_context_for_entry_basic():
    ctx = sel.context_for_entry(_df(_uptrend))
    assert ctx["close"] > 0
    assert ctx["atr"] > 0
    assert isinstance(ctx["returns"], list) and len(ctx["returns"]) > 0


# --- sector buckets (signal clusters by sector) -----------------------------

def test_sector_of_maps_known_names():
    assert sel.sector_of("US.NVDA") == "semis"
    assert sel.sector_of("US.AMD") == "semis"
    assert sel.sector_of("US.JPM") == "financials"


def test_sector_of_groups_semis_together():
    """The cluster that blew up in the event study must share one bucket."""
    names = ["US.NVDA", "US.AMD", "US.INTC", "US.MU", "US.AMAT", "US.MRVL"]
    assert len({sel.sector_of(n) for n in names}) == 1


def test_sector_of_defaults_to_other():
    assert sel.sector_of("US.NOTREAL") == "other"


# --- evidence-backed family (12-1 momentum / short-term reversal / low vol) --

def _last_month_change(base, n, rng, factor):
    """Uptrend whose final 21 bars move to `factor` x the level 21 bars ago."""
    c = base * np.cumprod(1 + rng.normal(0.002, 0.008, n))
    c[-21:] = c[-22] * np.linspace(1.0, factor, 21)
    return c


def test_momentum_12_1_ranks_trends():
    up = sel.momentum_12_1_score(_df(_uptrend))
    down = sel.momentum_12_1_score(_df(_downtrend))
    assert up["score"] > 60
    assert down["score"] < 40
    assert "mom_12_1_pct" in up["stats"]


def test_momentum_12_1_needs_full_year():
    """12-1 cannot be computed from half a year - must say so, not guess."""
    r = sel.momentum_12_1_score(_df(_uptrend, n=150))
    assert r["score"] == 0.0
    assert any("insufficient" in x for x in r["reasons"])


def test_mom_12_1_raw_keeps_ordering_above_the_display_clamp():
    """Regression: the first version clamped the RANKING variable at 100, so
    every name with 12-1 momentum above +50% tied at exactly 100 and the
    ordering collapsed precisely where the signal is strongest. `raw` must
    stay strictly ordered; `score` may saturate."""
    strong = sel.momentum_12_1_raw_score(_df(_steep))
    stronger = sel.momentum_12_1_raw_score(_df(_steeper))
    assert strong["score"] == 100.0 and stronger["score"] == 100.0   # both clamp
    assert stronger["raw"] > strong["raw"]                            # but raw orders
    assert "raw" in strong


def test_mom_12_1_raw_needs_full_year():
    r = sel.momentum_12_1_raw_score(_df(_uptrend, n=150))
    assert r["score"] == 0.0
    assert any("insufficient" in x for x in r["reasons"])


def test_mom_12_1_raw_differs_from_vol_scaled_variant():
    """The validated ranker must NOT divide by volatility - that scaling is
    what dropped the same signal from t=3.58 to t=1.03. Guard the distinction
    so a future 'cleanup' cannot silently merge the two."""
    raw = sel.momentum_12_1_raw_score(_df(_steep))
    scaled = sel.momentum_12_1_score(_df(_steep))
    assert raw["score"] != scaled["score"]
    assert "raw" in raw                            # raw exposes the unclamped rank
    assert "raw" not in scaled                     # the scaled variant does not
    assert "ann_vol_pct" not in raw["stats"]       # raw never estimates vol
    assert raw["stats"]["mom_12_1_pct"] == scaled["stats"]["mom_12_1_pct"]


def test_short_term_reversal_prefers_losers():
    """Last month's loser should outscore last month's winner (opposite of momentum)."""
    loser = sel.short_term_reversal_score(
        _df(lambda b, n, r: _last_month_change(b, n, r, 0.80)))
    winner = sel.short_term_reversal_score(
        _df(lambda b, n, r: _last_month_change(b, n, r, 1.25)))
    assert loser["score"] > winner["score"]
    assert loser["score"] >= 90
    assert winner["score"] <= 20


def test_low_vol_prefers_calm_names():
    calm = sel.low_vol_score(_df(lambda b, n, r: b * np.cumprod(1 + r.normal(0.001, 0.007, n))))
    wild = sel.low_vol_score(_df(_chaotic))
    assert calm["score"] > wild["score"]
    assert calm["score"] > 50


def test_new_styles_are_registered():
    for name in ("mom_12_1", "st_reversal", "low_vol"):
        assert name in sel.STYLES
        r = sel.score_style(name, _df(_uptrend))
        assert 0.0 <= r["score"] <= 100.0
