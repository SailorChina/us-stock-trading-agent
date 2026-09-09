"""Offline tests: decision_engine precomputed fast-path + auto_selector wiring.

Guards against the regression where factor assignment was nested inside the
`else` branch, so precomputed data was silently dropped and the technical /
enhanced / candlestick factors never made it into the composite score.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import pytest

import decision_engine as de

TECH = {
    "status": "ok", "symbol": "US.NVDA",
    "data": {
        "rating": "Overweight", "score": 72,
        "trade_plan": {"atr": 5.5, "entry_zone": 226.5, "stop_loss": 215.0,
                       "target_1": 249.5, "risk_reward": 2.0},
    },
}
ENHANCED = {"result": {"score": 65, "rating": "bullish", "reasons": ["CCI>100"]}}
CANDLE = {"patterns": [{"type": "Hammer", "direction": "bullish"},
                       {"type": "Doji", "direction": "neutral"}]}
EARNINGS = {"result": {"status": "ok",
                       "financials": {"pe_ratio": 55.2, "target_mean_price": 250.0}}}
REGIME = {"regime": "bull", "vix": 15.3, "confidence": 0.8}
PRICE = {"symbol": "US.NVDA", "latest_price": 230.0, "change_pct": 2.5}
SMART = [{"symbol": "US.NVDA", "total_score": 71}]

ALL_FACTORS = ["technical", "enhanced", "candlestick", "earnings", "regime", "smart_money"]


@pytest.fixture
def no_network(monkeypatch):
    """Any API call on the precomputed path is a bug — make it loud."""
    def boom(*a, **k):
        raise AssertionError("unexpected API call on precomputed path")
    for name in ("generate_signal", "fetch_kline", "get_price",
                 "get_earnings_summary", "get_regime", "scan_smart_money"):
        monkeypatch.setattr(de, name, boom)
    return boom


def _fast(**kw):
    return de.compute_decision_fast("US.NVDA", smart_money_data=SMART, **kw)


def test_precomputed_path_populates_all_factors(no_network):
    r = _fast(tech_data=TECH, enhanced_data=ENHANCED, candle_data=CANDLE,
              earnings_data=EARNINGS, regime_data=REGIME, price_data=PRICE)
    for k in ALL_FACTORS:
        assert k in r["factors"], f"factor {k} missing — precomputed data dropped"
    assert not any("error" in v for v in r["factors"].values())


def test_precomputed_values_are_reused(no_network):
    r = _fast(tech_data=TECH, enhanced_data=ENHANCED, candle_data=CANDLE,
              earnings_data=EARNINGS, regime_data=REGIME, price_data=PRICE)
    f = r["factors"]
    assert f["technical"]["score"] == 72
    assert f["enhanced"]["score"] == 65
    assert f["candlestick"]["patterns"] == ["Hammer", "Doji"]
    assert f["regime"]["regime"] == "bull"
    # smart money reads total_score (not the old smart_score key)
    assert f["smart_money"]["score"] == 71
    assert r["decision"]["current_price"] == 230.0


def test_precomputed_trade_plan_reuses_tech(no_network):
    r = _fast(tech_data=TECH, enhanced_data=ENHANCED, candle_data=CANDLE,
              earnings_data=EARNINGS, regime_data=REGIME, price_data=PRICE)
    tp = r["decision"]["trade_plan"]
    assert tp, "trade plan should be built from precomputed tech_data"
    assert tp["atr"] == 5.5
    assert tp["current_price"] == 230.0
    assert tp["stop_loss"] < tp["entry_zone"] < tp["target_1"]


def test_smart_money_skipped_when_no_data(monkeypatch):
    monkeypatch.setattr(de, "scan_smart_money",
                        lambda *a, **k: pytest.fail("must not scan when data is None"))
    for name in ("generate_signal", "fetch_kline", "get_price",
                 "get_earnings_summary", "get_regime"):
        monkeypatch.setattr(de, name, lambda *a, **k: None)
    r = de.compute_decision_fast("US.NVDA", tech_data=TECH)
    assert "smart_money" not in r["factors"]


def test_fallback_fetches_when_precomputed_missing(monkeypatch):
    """With no precomputed tech, the engine must fall back to generate_signal."""
    calls = []
    monkeypatch.setattr(de, "generate_signal",
                        lambda *a, **k: calls.append(a) or TECH)
    monkeypatch.setattr(de, "fetch_kline", lambda *a, **k: None)
    monkeypatch.setattr(de, "get_price", lambda *a, **k: PRICE)
    monkeypatch.setattr(de, "get_earnings_summary", lambda *a, **k: None)
    monkeypatch.setattr(de, "get_regime", lambda *a, **k: REGIME)
    r = de.compute_decision_fast("US.NVDA", smart_money_data=SMART)
    assert calls, "expected generate_signal fallback"
    assert r["factors"]["technical"]["score"] == 72
    assert r["decision"]["current_price"] == 230.0


def test_empty_patterns_do_not_crash(no_network):
    r = _fast(tech_data=TECH, enhanced_data=ENHANCED, candle_data={"patterns": []},
              earnings_data=EARNINGS, regime_data=REGIME, price_data=PRICE)
    assert r["factors"]["candlestick"]["score"] == 50


@pytest.mark.parametrize("score,expected", [
    (90, "STRONG_BUY"),
    (50, "BUY"),
    (35, "HOLD"),
    (25, "SELL"),
    (15, "STRONG_SELL"),
])
def test_decision_threshold_bands(monkeypatch, score, expected):
    """Composite -> decision mapping uses the 70/45/35/25 bands."""
    monkeypatch.setattr(de, "get_price", lambda *a, **k: PRICE)
    # pin the two derived factors so the composite is exactly predictable
    monkeypatch.setattr(de, "pattern_score",
                        lambda p: {"score": score, "signal": "neutral"})
    monkeypatch.setattr(de, "earnings_score",
                        lambda e, s: {"score": score, "signal": "neutral", "reasons": []})
    r = de.compute_decision("US.NVDA", skip_smart_money=True, precomputed={
        "tech": {"status": "ok", "data": {"score": score, "rating": "Hold"}},
        "enhanced": {"result": {"score": score, "rating": "neutral", "reasons": []}},
        "candlestick": {"patterns": [{"type": "Hammer", "direction": "bullish"}]},
        "earnings": {"result": {"status": "ok", "financials": {}}},
        "regime": {"regime": "bull"},
        "price": PRICE,
    })
    # Composite is a weight-normalised average over AVAILABLE weight. With
    # smart money skipped the weights are 35+10+5+25+0 = 75, and every scored
    # factor shares the same value, so the composite reduces to that value.
    # Regime carries weight 0 — it is a gate, not a score component.
    assert r["decision"]["composite_score"] == pytest.approx(score, 0.1)
    assert r["decision"]["decision"] == expected


# --------------------------------------------------------------------------
# auto_selector wiring
# --------------------------------------------------------------------------

def test_run_analysis_parallel_forwards_smart_money(monkeypatch):
    """Regression: smart_money_data was dropped before reaching run_full_analysis."""
    import auto_selector as asel
    seen = {}

    def fake_run_full(sym, timeframe="1d", smart_money_data=None,
                      price_map=None, tech_cache=None):
        seen[sym] = smart_money_data
        return {"symbol": sym, "modules": {}}

    monkeypatch.setattr(asel, "run_full_analysis", fake_run_full)
    sm = [{"symbol": "US.AAPL", "total_score": 40}]
    results, errors = asel.run_analysis_parallel(["US.AAPL"], smart_money_data=sm)
    assert seen.get("US.AAPL") is sm, "smart_money_data not forwarded"
    assert errors == {}
    assert "US.AAPL" in results


def test_regime_runs_before_decision(monkeypatch):
    """Decision can only reuse regime if regime is computed first."""
    import auto_selector as asel
    import us_stock_analyzer, news_sentiment, options_analysis
    import candlestick_patterns, enhanced_indicators, earnings_analyzer
    import market_regime, tech_engine

    order = []

    monkeypatch.setattr(us_stock_analyzer, "get_price", lambda s: PRICE)
    monkeypatch.setattr(us_stock_analyzer, "get_tech_analysis", lambda s, tf: TECH)
    monkeypatch.setattr(us_stock_analyzer, "get_news", lambda s: {"data": {"data": []}})
    monkeypatch.setattr(news_sentiment, "fetch_news", lambda *a, **k: [])
    monkeypatch.setattr(options_analysis, "get_futu_iv", lambda s: 40.0)
    monkeypatch.setattr(options_analysis, "get_options_pcr", lambda s: 0.9)
    monkeypatch.setattr(options_analysis, "get_unusual_options", lambda s: [])
    monkeypatch.setattr(tech_engine, "fetch_kline", lambda *a, **k: None)
    monkeypatch.setattr(candlestick_patterns, "get_latest_patterns",
                        lambda df, *a, **k: CANDLE["patterns"])
    monkeypatch.setattr(enhanced_indicators, "enhanced_signal_score",
                        lambda df: ENHANCED["result"])
    monkeypatch.setattr(earnings_analyzer, "get_earnings_summary",
                        lambda s: EARNINGS["result"])
    monkeypatch.setattr(market_regime, "get_regime",
                        lambda: order.append("regime") or REGIME)

    seen = {}

    def fake_decision(sym, **kw):
        # same shape as the real compute_decision_fast return value
        order.append("decision")
        seen.update(kw)
        return {"symbol": sym, "factors": {},
                "decision": {"action": "BUY", "composite_score": 64.0}}

    import decision_engine
    monkeypatch.setattr(decision_engine, "compute_decision_fast", fake_decision)

    report = asel.run_full_analysis("US.NVDA", smart_money_data=SMART,
                                    price_map={"US.NVDA": PRICE},
                                    tech_cache={"US.NVDA": TECH})
    assert order == ["regime", "decision"], f"bad task order: {order}"
    # all cached data must be handed to the decision engine
    assert seen["tech_data"] is TECH
    assert seen["enhanced_data"]["result"] == ENHANCED["result"]
    assert seen["candle_data"]["patterns"] == CANDLE["patterns"]
    assert seen["regime_data"] == REGIME
    assert seen["smart_money_data"] is SMART
    assert report["modules"]["decision"]["result"]["decision"]["action"] == "BUY"


# --------------------------------------------------------------------------
# v3.4.0 — scoring correctness: missing data, normalisation, two-sided plans
# --------------------------------------------------------------------------

def _boom(*a, **k):
    raise RuntimeError("api down")


def test_failed_factor_is_absent_not_bearish(monkeypatch):
    """A factor that could not be computed must NOT be scored as a bearish 0.

    Old behaviour wrote weighted_score=0 while leaving its weight in the sum,
    so a data outage silently became a sell signal.
    """
    monkeypatch.setattr(de, "generate_signal", _boom)
    monkeypatch.setattr(de, "pattern_score", lambda p: {"score": 90, "signal": "bullish"})
    monkeypatch.setattr(de, "earnings_score",
                        lambda e, s: {"score": 90, "signal": "bullish", "reasons": []})
    r = de.compute_decision("US.NVDA", skip_smart_money=True, precomputed={
        "enhanced": {"result": {"score": 90, "rating": "bullish", "reasons": []}},
        "candlestick": {"patterns": [{"type": "Hammer", "direction": "bullish"}]},
        "earnings": {"result": {"status": "ok", "financials": {}}},
        "regime": {"regime": "bull"},
        "price": PRICE,
    })
    d = r["decision"]
    assert "technical" in r["data_quality"]["missing_factors"]
    # remaining weight 10 + 5 + 25 + 0(regime) = 40
    assert d["composite_score"] == pytest.approx(
        (90 * 10 + 90 * 5 + 90 * 25) / 40, 0.1)
    assert d["composite_score"] > 80, "an outage must not read as bearish"
    assert d["action"] == "BUY"


def test_composite_is_weight_normalised(monkeypatch):
    """composite = weighted average over AVAILABLE weight (0-100 scale).

    Skipping smart money used to shrink the denominator-free sum, making
    --fast runs systematically ~10% lower and incomparable with full runs.
    """
    monkeypatch.setattr(de, "pattern_score", lambda p: {"score": 50, "signal": "neutral"})
    monkeypatch.setattr(de, "earnings_score",
                        lambda e, s: {"score": 80, "signal": "bullish", "reasons": []})
    base = dict(
        tech_data={"status": "ok", "data": {"score": 72, "rating": "Overweight"}},
        enhanced_data={"result": {"score": 65, "rating": "bullish", "reasons": []}},
        candle_data={"patterns": [{"type": "Hammer", "direction": "bullish"}]},
        earnings_data={"result": {"status": "ok", "financials": {}}},
        regime_data={"regime": "bull"},
        price_data=PRICE,
    )
    r_full = _fast(**base)                      # smart money present -> weight 90
    assert r_full["decision"]["composite_score"] == pytest.approx(
        (72 * 35 + 65 * 10 + 50 * 5 + 80 * 25 + 71 * 15) / 90, 0.1)

    r_skip = de.compute_decision_fast("US.NVDA", smart_money_data=None, **base)
    assert r_skip["decision"]["composite_score"] == pytest.approx(
        (72 * 35 + 65 * 10 + 50 * 5 + 80 * 25) / 75, 0.1)
    assert r_skip["data_quality"]["available_weight"] == 75


def test_sell_decision_gets_short_trade_plan(monkeypatch):
    """A SELL must produce a SHORT plan — stop above entry, targets below."""
    monkeypatch.setattr(de, "pattern_score", lambda p: {"score": 10, "signal": "bearish"})
    monkeypatch.setattr(de, "earnings_score",
                        lambda e, s: {"score": 10, "signal": "bearish", "reasons": []})
    r = de.compute_decision("US.NVDA", skip_smart_money=True, precomputed={
        "tech": {"status": "ok", "data": {"score": 10, "rating": "Sell",
                                          "trade_plan": {"atr": 5.5}}},
        "enhanced": {"result": {"score": 10, "rating": "bearish", "reasons": []}},
        "candlestick": {"patterns": [{"type": "EveningStar", "direction": "bearish"}]},
        "earnings": {"result": {"status": "ok", "financials": {}}},
        "regime": {"regime": "bear"},
        "price": PRICE,
    })
    assert r["decision"]["action"] == "SELL"
    tp = r["decision"]["trade_plan"]
    assert tp["side"] == "short"
    assert tp["stop_loss"] > tp["entry_zone"] > tp["target_1"]


def test_confidence_reflects_factor_agreement(monkeypatch):
    """Similar composite + different dispersion must yield different confidence.

    Confidence used to be `composite*0.9+5`, i.e. pure decoration.
    """
    state = {"candle": 70, "earn": 70}
    monkeypatch.setattr(de, "pattern_score",
                        lambda p: {"score": state["candle"], "signal": "neutral"})
    monkeypatch.setattr(de, "earnings_score",
                        lambda e, s: {"score": state["earn"], "signal": "neutral",
                                      "reasons": []})

    def run(tech_score, enh_score):
        return de.compute_decision("US.NVDA", skip_smart_money=True, precomputed={
            "tech": {"status": "ok", "data": {"score": tech_score, "rating": "Hold"}},
            "enhanced": {"result": {"score": enh_score, "rating": "neutral",
                                    "reasons": []}},
            "candlestick": {"patterns": [{"type": "Doji", "direction": "neutral"}]},
            "earnings": {"result": {"status": "ok", "financials": {}}},
            "regime": {"regime": "bull"},
            "price": PRICE,
        })

    unanimous = run(70, 70)
    state.update(candle=90, earn=40)
    disputed = run(90, 50)

    assert abs(unanimous["decision"]["composite_score"]
               - disputed["decision"]["composite_score"]) < 3
    assert disputed["decision"]["confidence"] < unanimous["decision"]["confidence"]
    assert disputed["decision"]["conflict"] is True
    assert unanimous["decision"]["conflict"] is False


def test_no_usable_data_holds_instead_of_guessing(monkeypatch):
    """When every factor fails, return HOLD — do not invent a direction."""
    for name in ("generate_signal", "fetch_kline", "get_price",
                 "get_earnings_summary", "get_regime"):
        monkeypatch.setattr(de, name, _boom)
    r = de.compute_decision("US.NVDA", skip_smart_money=True)
    d = r["decision"]
    assert d["insufficient_data"] is True
    assert d["action"] == "HOLD"
    assert d["composite_score"] == pytest.approx(50.0, 0.1)
    assert d["confidence"] <= 20
    assert len(r["data_quality"]["missing_factors"]) == 5


# --------------------------------------------------------------------------
# v3.4.0 — regime gate: whether you are exposed beats which name you pick
# --------------------------------------------------------------------------

def _pin(monkeypatch, score):
    """Pin the two derived factors so the composite is exactly `score`."""
    monkeypatch.setattr(de, "pattern_score",
                        lambda p: {"score": score, "signal": "neutral"})
    monkeypatch.setattr(de, "earnings_score",
                        lambda e, s: {"score": score, "signal": "neutral",
                                      "reasons": []})


def _precomputed(score, regime="bull"):
    """Every factor pinned to `score`, with a trade plan present."""
    return {
        "tech": {"status": "ok", "data": {"score": score, "rating": "Hold",
                                          "trade_plan": {"atr": 5.5}}},
        "enhanced": {"result": {"score": score, "rating": "neutral", "reasons": []}},
        "candlestick": {"patterns": [{"type": "Hammer", "direction": "bullish"}]},
        "earnings": {"result": {"status": "ok", "financials": {}}},
        "regime": {"regime": regime},
        "price": PRICE,
    }


def test_regime_gate_blocks_longs_in_bear(monkeypatch):
    """A bear regime must suppress long entries, not merely shave points off."""
    _pin(monkeypatch, 80)
    r = de.compute_decision("US.NVDA", skip_smart_money=True,
                            precomputed=_precomputed(80, "bear"))
    d = r["decision"]
    assert d["regime_gate"]["applied"] is True
    assert d["regime_gate"]["blocked_decision"] == "STRONG_BUY"
    assert d["action"] == "HOLD"
    assert d["trade_plan"].get("note", "").startswith("suppressed")


def test_regime_gate_blocks_longs_in_volatile(monkeypatch):
    _pin(monkeypatch, 80)
    r = de.compute_decision("US.NVDA", skip_smart_money=True,
                            precomputed=_precomputed(80, "volatile"))
    assert r["decision"]["regime_gate"]["applied"] is True
    assert r["decision"]["action"] == "HOLD"


def test_regime_gate_allows_longs_in_bull(monkeypatch):
    _pin(monkeypatch, 80)
    r = de.compute_decision("US.NVDA", skip_smart_money=True,
                            precomputed=_precomputed(80, "bull"))
    d = r["decision"]
    assert d["regime_gate"]["applied"] is False
    assert d["action"] == "BUY"


def test_regime_gate_does_not_block_shorts(monkeypatch):
    """Falling markets are what shorts are for — the gate must not touch them."""
    _pin(monkeypatch, 10)
    r = de.compute_decision("US.NVDA", skip_smart_money=True,
                            precomputed=_precomputed(10, "bear"))
    d = r["decision"]
    assert d["action"] == "SELL"
    assert d["regime_gate"]["applied"] is False
    assert d["trade_plan"]["side"] == "short"


def test_apply_regime_gate_unit():
    """Direct check of the gate's own logic."""
    d = {"decision": "BUY", "action": "BUY"}
    de.apply_regime_gate(d, {"regime": "neutral"})
    assert d["action"] == "BUY" and d["regime_gate"]["applied"] is False

    d = {"decision": "SELL", "action": "SELL"}
    de.apply_regime_gate(d, {"regime": "bear"})
    assert d["action"] == "SELL", "shorts must survive the gate"

    d = {"decision": "BUY", "action": "BUY"}
    de.apply_regime_gate(d, {})
    assert d["action"] == "BUY", "unknown regime must not silently block"
