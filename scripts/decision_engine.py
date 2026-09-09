#!/usr/bin/env python3
"""Decision Engine - Multi-factor signal fusion for trading decisions."""
import json, sys, os, time
from datetime import datetime
from typing import Dict, List, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from tech_engine import get_price, generate_signal, fetch_kline
from enhanced_indicators import enhanced_signal_score, calc_all_enhanced
from candlestick_patterns import get_latest_patterns, pattern_score
from earnings_analyzer import get_earnings_summary, earnings_score
from market_regime import get_regime
from smart_money_screener import scan_smart_money

# Factor weights, deliberately NOT equal and deliberately NOT six.
#
# The old 30/20/15 split pretended technical / enhanced / candlestick were
# three independent dimensions. They are not: CCI, RVI, StochRSI and Williams
# %R are the same momentum signal in different algebra, so weighting them
# separately counted one opinion three times and manufactured false
# confirmation. Candlestick patterns also carry the weakest replicated
# evidence of anything here. Money was moved to the two factors that actually
# carry independent information (fundamentals and flow).
FACTOR_WEIGHTS = {
    "technical": 35,
    "enhanced": 10,      # same momentum signal as technical - confirmation only
    "candlestick": 5,    # weakest evidence; kept at a token weight
    "earnings": 25,      # genuinely independent information set
    "smart_money": 15,   # flow, not price
    "regime": 0,         # a GATE, not a score - see apply_regime_gate
}

# Regimes in which new long exposure is refused outright.
REGIME_GATE = {"bear", "volatile"}


def _try_import(module_name, func_name):
    """Safely try to import a function, return None on failure."""
    try:
        mod = __import__(module_name, fromlist=[func_name])
        return getattr(mod, func_name, None)
    except Exception:
        return None


def _absent(weight: int, err: str = None) -> Dict:
    """A factor whose data could not be obtained.

    It contributes NOTHING — critically, its `weighted_score` must not be a
    bearish 0 that is divided by a still-counted weight. `available=False`
    removes the weight from the denominator instead.
    """
    f = {"weight": weight, "weighted_score": 0.0, "available": False}
    if err:
        f["error"] = err
    return f


def apply_regime_gate(decision: Dict, regime: Dict) -> Dict:
    """Refuse new longs when the market regime is hostile.

    Regime used to be just another 10% score component, so a bear market cost
    roughly 5 points of composite — nowhere near enough to keep you out. For
    an equity long book, WHETHER you are exposed dominates WHICH name you
    pick, so regime belongs on the gate rather than in the sum.

    Shorts are left alone: falling markets are what they are for.
    """
    state = (regime or {}).get("regime", "unknown")
    gated = state in REGIME_GATE and decision.get("action") == "BUY"
    original = decision.get("decision")
    if gated:
        decision["decision"] = "HOLD"
        decision["action"] = "HOLD"
        decision["regime_gate_note"] = (
            f"long suppressed by regime gate ({state}) — no new long entries")
    decision["regime_gate"] = {
        "regime": state,
        "applied": gated,
        "blocked_decision": original if gated else None,
    }
    return decision


def compute_decision(symbol: str, timeframe: str = "1d", skip_smart_money: bool = False, smart_money_data: list = None, precomputed: dict = None) -> Dict:
    """Compute a comprehensive trading decision from all available signals."""
    t0 = time.time()
    W = FACTOR_WEIGHTS
    result = {
        "symbol": symbol,
        "generated_at": datetime.now().isoformat(),
        "decision": {},
        "factors": {},
        "weight_summary": {},
    }

    pc = precomputed or {}
    tech_data = {}        # kept for downstream trade-plan reuse
    tech_precomputed = False
    regime_state: Dict = {}

    # 1. Technical Analysis
    try:
        _pc_tech = pc.get("tech")
        if isinstance(_pc_tech, dict) and isinstance(_pc_tech.get("data"), dict) \
                and _pc_tech.get("status", "ok") == "ok":
            tech_data = _pc_tech["data"]
            tech_precomputed = True
        else:
            tech = generate_signal(symbol, timeframe, 60)
            if tech.get("status") == "ok":
                tech_data = tech.get("data", {}) or {}
        if tech_data:
            result["factors"]["technical"] = {
                "score": tech_data.get("score", 50),
                "rating": tech_data.get("rating", "Hold"),
                "weight": W["technical"],
                "weighted_score": tech_data.get("score", 50) * W["technical"] / 100.0,
                "available": True,
            }
        else:
            result["factors"]["technical"] = _absent(W["technical"])
    except Exception as e:
        result["factors"]["technical"] = _absent(W["technical"], str(e))

    # 2. Enhanced Indicators (largely redundant with technical — confirmation only)
    try:
        enh = None
        _pc_enh = pc.get("enhanced")
        if isinstance(_pc_enh, dict):
            if isinstance(_pc_enh.get("result"), dict):
                enh = _pc_enh["result"]
            elif "score" in _pc_enh:
                enh = _pc_enh
        if enh is None:
            df = fetch_kline(symbol, timeframe, 60)
            if df is not None and len(df) >= 20:
                enh = enhanced_signal_score(df)
        if enh is None:
            # No K-line -> factor absent. Do NOT fabricate a neutral 50:
            # that would silently pull the composite towards "hold".
            result["factors"]["enhanced"] = _absent(W["enhanced"])
        else:
            result["factors"]["enhanced"] = {
                "score": enh.get("score", 50),
                "rating": enh.get("rating", "neutral"),
                "reasons": enh.get("reasons", []),
                "weight": W["enhanced"],
                "weighted_score": enh.get("score", 50) * W["enhanced"] / 100.0,
                "available": True,
            }
    except Exception as e:
        result["factors"]["enhanced"] = _absent(W["enhanced"], str(e))

    # 3. Candlestick Patterns (token weight — weakest replicated evidence)
    try:
        patterns = None
        _pc_candle = pc.get("candlestick")
        if isinstance(_pc_candle, dict):
            if isinstance(_pc_candle.get("patterns"), list):
                patterns = _pc_candle["patterns"]
            elif isinstance(_pc_candle.get("result"), dict) \
                    and isinstance(_pc_candle["result"].get("patterns"), list):
                patterns = _pc_candle["result"]["patterns"]
        # An explicitly-provided empty list means "no patterns found" — respect it
        # instead of re-fetching the K-line.
        if patterns is None:
            df = fetch_kline(symbol, timeframe, 60)
            if df is not None:
                patterns = get_latest_patterns(df, 5) or []
        if patterns is None:
            result["factors"]["candlestick"] = _absent(W["candlestick"])
        else:
            pscore = pattern_score(patterns) if patterns else {"score": 50, "signal": "neutral"}
            result["factors"]["candlestick"] = {
                "score": pscore.get("score", 50),
                "signal": pscore.get("signal", "neutral"),
                "patterns": [p.get("type", "?") for p in patterns],
                "weight": W["candlestick"],
                "weighted_score": pscore.get("score", 50) * W["candlestick"] / 100.0,
                "available": True,
            }
    except Exception as e:
        result["factors"]["candlestick"] = _absent(W["candlestick"], str(e))

    # 4. Earnings/Analyst
    try:
        earnings = None
        _pc_earn = pc.get("earnings")
        if isinstance(_pc_earn, dict):
            if isinstance(_pc_earn.get("result"), dict):
                earnings = _pc_earn["result"]
            elif "financials" in _pc_earn or "status" in _pc_earn:
                earnings = _pc_earn
        if earnings is None:
            earnings = get_earnings_summary(symbol)
        if isinstance(earnings, dict) and earnings.get("status") == "ok":
            escore = earnings_score(earnings, symbol)
            result["factors"]["earnings"] = {
                "score": escore["score"],
                "signal": escore["signal"],
                "reasons": escore["reasons"],
                "pe_ratio": earnings.get("financials", {}).get("pe_ratio"),
                "analyst_target": earnings.get("financials", {}).get("target_mean_price"),
                "weight": W["earnings"],
                "weighted_score": escore["score"] * W["earnings"] / 100.0,
                "available": True,
            }
        else:
            result["factors"]["earnings"] = _absent(W["earnings"])
    except Exception as e:
        result["factors"]["earnings"] = _absent(W["earnings"], str(e))

    # 5. Market Regime — recorded for the gate, carries no score weight
    try:
        regime = None
        _pc_reg = pc.get("regime")
        if isinstance(_pc_reg, dict) and "regime" in _pc_reg:
            regime = _pc_reg
        else:
            regime = get_regime()
        if isinstance(regime, dict) and regime.get("regime"):
            regime_state = regime
            regime_score = {"bull": 70, "neutral": 50, "volatile": 40, "bear": 25}.get(
                regime.get("regime", "neutral"), 50
            )
            result["factors"]["regime"] = {
                "regime": regime.get("regime", "unknown"),
                "score": regime_score,
                "vix": regime.get("vix", 0),
                "confidence": regime.get("confidence", 0),
                "weight": W["regime"],
                "weighted_score": 0.0,
                "available": True,
            }
        else:
            result["factors"]["regime"] = _absent(W["regime"])
    except Exception as e:
        result["factors"]["regime"] = _absent(W["regime"], str(e))

    # 6. Smart Money
    if not skip_smart_money:
        try:
            if smart_money_data is not None:
                sm = smart_money_data
            else:
                sm = scan_smart_money(top_n=50, min_score=10)
            sm_score = 50
            for item in sm[:10] if isinstance(sm, list) else []:
                if item.get("code") == symbol or item.get("symbol") == symbol:
                    sm_score = item.get("total_score", 50)
                    break
            result["factors"]["smart_money"] = {
                "score": sm_score,
                "weight": W["smart_money"],
                "weighted_score": sm_score * W["smart_money"] / 100.0,
                "available": True,
            }
        except Exception as e:
            result["factors"]["smart_money"] = _absent(W["smart_money"], str(e))

    # ---- composite: availability-aware and weight-normalised --------------
    # Only factors that actually produced data go into the score. A failed
    # lookup is *missing information*, not a bearish opinion, so its weight
    # leaves the denominator instead of contributing a punishing zero.
    factors = {k: v for k, v in result["factors"].items() if isinstance(v, dict)}
    usable = {k: v for k, v in factors.items() if v.get("available", True)}
    total_weighted = sum(v.get("weighted_score", 0) for v in usable.values())
    total_weight = sum(v.get("weight", 0) for v in usable.values())
    attempted_weight = sum(v.get("weight", 0) for v in factors.values())
    missing = sorted(k for k, v in factors.items() if not v.get("available", True))

    if total_weight > 0:
        composite = 100.0 * total_weighted / total_weight
    else:
        composite = 50.0
    composite = max(0.0, min(100.0, composite))

    # ---- honest confidence ------------------------------------------------
    # Was previously a deterministic transform of the composite score, i.e.
    # decoration. Real confidence = do the factors agree, is the data
    # complete, and is the score actually away from neutral?
    # Zero-weight factors (the regime gate) carry no vote, so they must not
    # inflate the agreement measure either.
    scores = [v.get("score", 50) for v in usable.values()
              if v.get("score") is not None and v.get("weight", 0) > 0]
    if len(scores) >= 2:
        spread = max(scores) - min(scores)
        mean_s = sum(scores) / len(scores)
        std = (sum((s - mean_s) ** 2 for s in scores) / len(scores)) ** 0.5
        agreement = max(0.0, min(1.0, 1.0 - std / 35.0))
    else:
        spread, std = 0.0, 0.0
        # One (or zero) readings cannot corroborate anything — "no dispersion"
        # here means "no evidence", not "unanimous".
        agreement = 0.0
    completeness = (total_weight / attempted_weight) if attempted_weight > 0 else 0.0
    conviction = max(0.0, min(1.0, abs(composite - 50.0) / 30.0))
    confidence = 100.0 * (0.35 * agreement + 0.30 * completeness + 0.35 * conviction)
    confidence = int(max(5, min(95, round(confidence))))
    conflict = bool(len(scores) >= 2 and spread >= 40)

    # Decision logic
    insufficient = not usable
    if insufficient:
        # Nothing could be measured — do not manufacture a directional call.
        decision = "HOLD"
        action = "HOLD"
    elif composite >= 70:
        decision = "STRONG_BUY"
        action = "BUY"
    elif composite >= 45:
        decision = "BUY"
        action = "BUY"
    elif composite >= 35:
        decision = "HOLD"
        action = "HOLD"
    elif composite >= 25:
        decision = "SELL"
        action = "SELL"
    else:
        decision = "STRONG_SELL"
        action = "SELL"

    # Get price info (reuse cached price when available)
    price = None
    _pc_price = pc.get("price")
    if isinstance(_pc_price, dict) and _pc_price.get("latest_price"):
        price = _pc_price
    else:
        try:
            price = get_price(symbol)
        except Exception:
            price = None
    current_price = price.get("latest_price", 0) if isinstance(price, dict) else 0
    change_pct = price.get("change_pct", 0) if isinstance(price, dict) else 0

    result["decision"] = {
        "composite_score": round(composite, 1),
        "decision": decision,
        "action": action,
        "current_price": current_price,
        "change_pct": change_pct,
    }

    # The regime gate runs BEFORE the trade plan is built, so a suppressed
    # long can never hand you a long entry/target to act on.
    apply_regime_gate(result["decision"], regime_state)
    action = result["decision"]["action"]
    gated = bool(result["decision"].get("regime_gate", {}).get("applied"))

    # Trade plan from tech analysis (reuse tech_data when available)
    # NOTE: direction must match the decision — a SELL gets a SHORT plan
    # (stop above entry, targets below), not a recycled long plan.
    trade_plan = {}
    try:
        tp = (tech_data or {}).get("trade_plan", {}) if isinstance(tech_data, dict) else {}
        # Only fall back to a fresh generate_signal when tech was NOT precomputed —
        # otherwise the "precomputed path makes zero API calls" guarantee breaks.
        if not tp and not tech_precomputed:
            tech2 = generate_signal(symbol, timeframe, 60)
            if tech2.get("status") == "ok":
                tp = tech2.get("data", {}).get("trade_plan", {})
        if tp and current_price > 0:
            atr = tp.get("atr", 0)
            short = action == "SELL"
            if short:
                entry = round(current_price * 1.015, 2)
                stop = round(entry + atr * 2.0, 2) if atr > 0 else round(entry * 1.05, 2)
                risk = stop - entry
                tp1 = round(entry - risk * 2.0, 2)
                tp2 = round(entry - risk * 2.5, 2)
            else:
                entry = round(current_price * 0.985, 2)
                stop = round(entry - atr * 2.0, 2) if atr > 0 else round(entry * 0.95, 2)
                risk = entry - stop
                tp1 = round(entry + risk * 2.0, 2)
                tp2 = round(entry + risk * 2.5, 2)
            trade_plan = {
                "side": "short" if short else "long",
                "entry_zone": entry,
                "stop_loss": stop,
                "target_1": tp1,
                "target_2": tp2,
                "risk_reward": round(abs(tp1 - entry) / risk, 2) if risk > 0 else 0,
                "atr": atr,
                "current_price": current_price,
            }
            if gated:
                trade_plan["note"] = "suppressed by regime gate - not an entry"
            elif action == "HOLD":
                trade_plan["note"] = "reference only - action is HOLD"
    except Exception:
        pass

    result["decision"]["trade_plan"] = trade_plan
    result["decision"]["confidence"] = confidence
    result["decision"]["confidence_components"] = {
        "agreement": round(agreement, 3),
        "completeness": round(completeness, 3),
        "conviction": round(conviction, 3),
    }
    result["decision"]["factor_spread"] = round(spread, 1)
    result["decision"]["conflict"] = conflict
    result["decision"]["insufficient_data"] = insufficient

    result["data_quality"] = {
        "available_weight": total_weight,
        "attempted_weight": attempted_weight,
        "missing_factors": missing,
    }
    result["weight_summary"] = {k: v.get("weight", 0) for k, v in result["factors"].items() if isinstance(v, dict)}
    result["elapsed_sec"] = round(time.time() - t0, 1)

    return result


def compute_decision_fast(symbol: str, smart_money_data: list = None,
                          tech_data: dict = None, enhanced_data: dict = None,
                          candle_data: dict = None, earnings_data: dict = None,
                          regime_data: dict = None, price_data: dict = None,
                          timeframe: str = "1d") -> Dict:
    """Fast decision — use provided data to avoid re-running heavy modules.

    Any of the *_data args may be None; missing ones are fetched on demand.
    smart_money_data=None means "skip smart money" (no heavy scan).
    """
    skip = smart_money_data is None
    return compute_decision(symbol, timeframe=timeframe, skip_smart_money=skip,
                            smart_money_data=smart_money_data,
                            precomputed={
                                "tech": tech_data,
                                "enhanced": enhanced_data,
                                "candlestick": candle_data,
                                "earnings": earnings_data,
                                "regime": regime_data,
                                "price": price_data,
                            })


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Decision Engine")
    parser.add_argument("--symbol", required=True, help="Stock symbol (e.g., US.NVDA)")
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--fast", action="store_true", help="Skip smart money scan")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    if args.fast:
        result = compute_decision_fast(args.symbol, timeframe=args.timeframe)
    else:
        result = compute_decision(args.symbol, timeframe=args.timeframe)

    output = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Saved: {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
