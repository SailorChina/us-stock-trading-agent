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


def _try_import(module_name, func_name):
    """Safely try to import a function, return None on failure."""
    try:
        mod = __import__(module_name, fromlist=[func_name])
        return getattr(mod, func_name, None)
    except Exception:
        return None


def compute_decision(symbol: str, timeframe: str = "1d", skip_smart_money: bool = False, smart_money_data: list = None, precomputed: dict = None) -> Dict:
    """Compute a comprehensive trading decision from all available signals."""
    t0 = time.time()
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

    # 1. Technical Analysis (weight: 30%)
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
        result["factors"]["technical"] = {
            "score": tech_data.get("score", 50),
            "rating": tech_data.get("rating", "Hold"),
            "weight": 30,
            "weighted_score": tech_data.get("score", 50) * 0.30,
        }
    except Exception as e:
        result["factors"]["technical"] = {"error": str(e), "weight": 30, "weighted_score": 0}

    # 2. Enhanced Indicators (weight: 20%)
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
            else:
                enh = {"score": 50, "rating": "neutral", "reasons": []}
        result["factors"]["enhanced"] = {
            "score": enh.get("score", 50),
            "rating": enh.get("rating", "neutral"),
            "reasons": enh.get("reasons", []),
            "weight": 20,
            "weighted_score": enh.get("score", 50) * 0.20,
        }
    except Exception as e:
        result["factors"]["enhanced"] = {"error": str(e), "weight": 20, "weighted_score": 0}

    # 3. Candlestick Patterns (weight: 15%)
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
            patterns = get_latest_patterns(df, 5) or [] if df is not None else []
        pscore = pattern_score(patterns) if patterns else {"score": 50, "signal": "neutral"}
        result["factors"]["candlestick"] = {
            "score": pscore.get("score", 50),
            "signal": pscore.get("signal", "neutral"),
            "patterns": [p.get("type", "?") for p in patterns],
            "weight": 15,
            "weighted_score": pscore.get("score", 50) * 0.15,
        }
    except Exception as e:
        result["factors"]["candlestick"] = {"error": str(e), "weight": 15, "weighted_score": 0}
    
    # 4. Earnings/Analyst (weight: 15%)
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
        if earnings.get("status") == "ok":
            escore = earnings_score(earnings, symbol)
            result["factors"]["earnings"] = {
                "score": escore["score"],
                "signal": escore["signal"],
                "reasons": escore["reasons"],
                "pe_ratio": earnings.get("financials", {}).get("pe_ratio"),
                "analyst_target": earnings.get("financials", {}).get("target_mean_price"),
                "weight": 15,
                "weighted_score": escore["score"] * 0.15,
            }
    except Exception as e:
        result["factors"]["earnings"] = {"error": str(e), "weight": 15, "weighted_score": 0}
    
    # 5. Market Regime (weight: 10%)
    try:
        regime = None
        _pc_reg = pc.get("regime")
        if isinstance(_pc_reg, dict) and "regime" in _pc_reg:
            regime = _pc_reg
        else:
            regime = get_regime()
        regime_score = {"bull": 70, "neutral": 50, "volatile": 40, "bear": 25}.get(
            regime.get("regime", "neutral"), 50
        )
        result["factors"]["regime"] = {
            "regime": regime.get("regime", "unknown"),
            "score": regime_score,
            "vix": regime.get("vix", 0),
            "confidence": regime.get("confidence", 0),
            "weight": 10,
            "weighted_score": regime_score * 0.10,
        }
    except Exception as e:
        result["factors"]["regime"] = {"error": str(e), "weight": 10, "weighted_score": 0}
    
    # 6. Smart Money (weight: 10%)
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
                "weight": 10,
                "weighted_score": sm_score * 0.10,
            }
        except Exception as e:
            result["factors"]["smart_money"] = {"error": str(e), "weight": 10, "weighted_score": 0}
    
    # Compute composite score
    total_weighted = sum(f.get("weighted_score", 0) for f in result["factors"].values() 
                        if isinstance(f, dict) and "weighted_score" in f)
    total_weight = sum(f.get("weight", 0) for f in result["factors"].values()
                       if isinstance(f, dict) and "weight" in f)
    
    composite = total_weighted if total_weight > 0 else 50
    composite = max(0, min(100, composite))
    
    # Decision logic
    if composite >= 70:
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
        price = get_price(symbol)
    current_price = price.get("latest_price", 0) if price else 0
    change_pct = price.get("change_pct", 0) if price else 0
    
    # Trade plan from tech analysis (reuse tech_data when available)
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
            entry = round(current_price * 0.985, 2)
            atr = tp.get("atr", 0)
            if atr > 0:
                stop = round(entry - atr * 2.0, 2)
            else:
                stop = round(entry * 0.95, 2)
            risk = entry - stop
            tp1 = round(entry + risk * 2.0, 2)
            tp2 = round(entry + risk * 2.5, 2)
            trade_plan = {
                "entry_zone": entry,
                "stop_loss": stop,
                "target_1": tp1,
                "target_2": tp2,
                "risk_reward": round((tp1 - entry) / risk, 2) if risk > 0 else 0,
                "atr": atr,
                "current_price": current_price,
            }
    except Exception:
        pass
    
    result["decision"] = {
        "composite_score": round(composite, 1),
        "decision": decision,
        "action": action,
        "current_price": current_price,
        "change_pct": change_pct,
        "trade_plan": trade_plan,
        "confidence": min(95, int(composite * 0.9 + 5)) if composite >= 55 else max(10, int(composite * 0.5)),
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
