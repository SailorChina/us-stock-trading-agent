"""Test: market_regime.py - regime classification and detection."""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from market_regime import classify_regime, get_confidence, get_regime


def test_classify_regime_bull():
    assert classify_regime(vix=12.0, spx_chg=1.5) == "bull"
    assert classify_regime(vix=10.0, spx_chg=3.0) == "bull"


def test_classify_regime_bear():
    # VIX > 30 returns volatile, not bear
    assert classify_regime(vix=35.0, spx_chg=-3.0) == "volatile"
    # SPX drop > 2% with moderate VIX triggers bear
    assert classify_regime(vix=20.0, spx_chg=-3.0) == "bear"
    assert classify_regime(vix=22.0, spx_chg=-2.5) == "bear"


@pytest.mark.network
@pytest.mark.timeout(30)
def test_classify_regime_volatile():
    assert classify_regime(vix=32.0, spx_chg=-0.5) == "volatile"
    assert classify_regime(vix=40.0, spx_chg=1.0) == "volatile"


@pytest.mark.network
@pytest.mark.timeout(30)
def test_classify_regime_neutral():
    assert classify_regime(vix=18.0, spx_chg=0.5) == "neutral"
    assert classify_regime(vix=22.0, spx_chg=-0.5) == "neutral"
    assert classify_regime(vix=15.0, spx_chg=-0.5) == "neutral"


def test_get_confidence_clear():
    assert get_confidence(vix=10.0, spx_chg=0.0) == 85
    assert get_confidence(vix=45.0, spx_chg=0.0) == 85
    assert get_confidence(vix=20.0, spx_chg=3.0) == 75


def test_get_confidence_mixed():
    conf = get_confidence(vix=20.0, spx_chg=0.5)
    assert 40 <= conf <= 60


@pytest.mark.network
@pytest.mark.timeout(30)
def test_get_regime_returns_dict():
    result = get_regime()
    assert isinstance(result, dict)
    assert "generated_at" in result
    if result.get("status") == "ok":
        assert "regime" in result
        assert "confidence" in result


def test_get_regime_reports_unavailable_instead_of_faking_neutral(monkeypatch):
    """Both inputs are unobtainable, and that must be REPORTED, not smoothed over.

    This function reads US.VIX and US.SPX; futu recognises neither ("unknown
    symbol"), so both lookups fail. That used to be silent: vix and spx_chg
    stayed 0 and classify_regime(0, 0) hit its `vix < 20 and spx_chg > -1`
    branch, returning a confident "neutral" every day. daily_pick's
    "no new longs in a bear market" gate was built on exactly that reading --
    which is why the gate could never fire.
    """
    import futu_pool
    import market_regime as mr

    class _FakeCtx:
        def get_stock_quote(self, codes):       # noqa: ARG002
            return (1, None)                    # ret != RET_OK -> unknown symbol

    monkeypatch.setattr(mr, "FUTU_OK", True)
    monkeypatch.setattr(futu_pool, "get_futu_context", lambda *a, **k: _FakeCtx())

    r = mr.get_regime()
    assert r["regime"] == "unknown", "a failed read must not become a market call"
    assert r["status"] == "unavailable"
    assert "VIX" in r["error"]