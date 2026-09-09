"""Offline tests: volatility-targeted position sizing (v3.4.0).

The property that matters: two positions should contribute comparable RISK,
not comparable dollar amounts. A fixed percentage fails that; a volatility
target is what makes it hold.
"""
import sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import pytest

from risk_manager import annualized_vol, vol_target_position


def _returns(daily_amp, n=60):
    """Deterministic alternating series with sample stdev ~= daily_amp."""
    return [daily_amp if i % 2 == 0 else -daily_amp for i in range(n)]


def test_annualized_vol_needs_five_observations():
    assert annualized_vol([]) is None
    assert annualized_vol([0.01, 0.02]) is None
    assert annualized_vol([0.01] * 4) is None


def test_annualized_vol_scales_by_sqrt_time():
    r = _returns(0.01, 60)
    daily = 0.01
    assert annualized_vol(r) == pytest.approx(daily * math.sqrt(252), rel=0.05)


def test_vol_target_reduces_size_for_volatile_names():
    """A high-vol name must get a SMALLER position than a calm one."""
    calm = vol_target_position(100.0, returns=_returns(0.01), capital=100000.0)
    wild = vol_target_position(100.0, returns=_returns(0.06), capital=100000.0)

    assert wild["annualized_vol_pct"] > calm["annualized_vol_pct"]
    assert wild["position_pct"] < calm["position_pct"], \
        "volatile names must not get the same size as calm ones"
    assert wild["capped_by"] == "volatility_target"


def test_calm_name_hits_the_position_cap():
    """An unusually calm name is limited by the hard cap, not by vol target."""
    calm = vol_target_position(100.0, returns=_returns(0.005), capital=100000.0)
    assert calm["capped_by"] == "max_position"
    assert calm["position_pct"] == pytest.approx(25.0, abs=0.01)


def test_risk_cap_can_bind_and_is_reported():
    """A wide ATR stop must shrink the position, and say so."""
    r = vol_target_position(100.0, returns=_returns(0.01), atr=10.0,
                            capital=100000.0, max_risk_pct=1.0)
    assert r["capped_by"] == "risk_cap"
    # 1% of 100k risked over a 20-point stop -> 50 shares -> 5k -> 5%
    assert r["position_pct"] == pytest.approx(5.0, abs=0.1)
    assert r["risk_usd"] <= 100000.0 * 0.01 + 1e-6


def test_position_never_exceeds_max_position_pct():
    for amp in (0.001, 0.01, 0.05, 0.2):
        r = vol_target_position(100.0, returns=_returns(amp), capital=100000.0,
                                max_position_pct=25.0)
        assert r["position_pct"] <= 25.0 + 1e-9


def test_zero_vol_name_is_not_leveraged_to_infinity():
    r = vol_target_position(100.0, returns=[0.0] * 60, capital=100000.0)
    assert "error" in r


def test_invalid_inputs_are_rejected():
    assert "error" in vol_target_position(0, returns=_returns(0.01))
    assert "error" in vol_target_position(-5, returns=_returns(0.01))
    assert "error" in vol_target_position(100.0, returns=None)


def test_shares_are_whole_and_consistent():
    r = vol_target_position(100.0, returns=_returns(0.02), capital=100000.0)
    assert isinstance(r["shares"], int)
    assert r["shares"] >= 0
    assert r["position_value"] == pytest.approx(r["shares"] * 100.0, abs=0.01)
