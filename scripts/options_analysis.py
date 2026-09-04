#!/usr/bin/env python3
"""US Stock Options & Derivatives Analysis - with retry logic"""
import json, sys, argparse, time
from datetime import datetime

_futu_ctx = None

def _get_futu_ctx():
    """Get or create a shared Futu quote context."""
    global _futu_ctx
    if _futu_ctx is None:
        from futu import OpenQuoteContext
        _futu_ctx = OpenQuoteContext()
        _futu_ctx.open()
    return _futu_ctx

def _futu_call(func_name, *args, **kwargs):
    """Make a Futu API call with retry (3 attempts, 1s delay)."""
    for attempt in range(3):
        try:
            ctx = _get_futu_ctx()
            func = getattr(ctx, func_name)
            ret, data = func(*args, **kwargs)
            if ret == RET_OK:
                return data
            return None
        except Exception as e:
            if attempt < 2:
                time.sleep(1)
            else:
                return None
    return None

def _close_futu_ctx():
    """Close shared Futu context."""
    global _futu_ctx
    if _futu_ctx is not None:
        try:
            _futu_ctx.close()
        except Exception:
            pass
        _futu_ctx = None

def get_futu_iv(symbol):
    data = _futu_call("get_quote_snapshot", [symbol])
    if data is not None and len(data) > 0:
        row = data.iloc[0]
        iv = row.get("opt_iv", 0) if "opt_iv" in row else 0
        return float(iv) if iv else None
    return None

def get_options_pcr(symbol):
    data = _futu_call("get_stock_quote", [symbol])
    if data is not None and len(data) > 0:
        row = data.iloc[0]
        pcr = row.get("opt_pcr", 0) if "opt_pcr" in row else 0
        return float(pcr) if pcr else None
    return None

def get_unusual_options(symbol):
    data = _futu_call("get_financial_unusual", code=symbol, time_range=7, analysis_dimensions=[], language_id=0)
    if data:
        content = data.get("data", {}).get("content", "")
        return content if content else "No unusual activity"
    return "No unusual activity"

def classify_iv(iv):
    if iv is None: return "unknown"
    if iv < 0.20: return "low"
    elif iv < 0.35: return "normal"
    elif iv < 0.50: return "high"
    else: return "extreme"

def classify_pcr(pcr):
    if pcr is None: return "unknown"
    if pcr < 0.7: return "bullish"
    elif pcr < 1.0: return "neutral"
    elif pcr < 1.3: return "cautious"
    else: return "bearish"

def main():
    parser = argparse.ArgumentParser(description="US Stock Options Analysis")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--mode", default="quick", choices=["quick", "full", "iv", "pcr", "unusual"])
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    
    result = {"symbol": args.symbol, "generated_at": datetime.now().isoformat(), "mode": args.mode}
    
    if args.mode in ("quick", "full", "iv"):
        iv = get_futu_iv(args.symbol)
        result["iv"] = {"value": round(iv, 4), "level": classify_iv(iv)} if iv else {"status": "unavailable", "note": "Futu Basic tier - upgrade needed for IV data"}
    
    if args.mode in ("quick", "full", "pcr"):
        pcr = get_options_pcr(args.symbol)
        result["pcr"] = {"value": round(pcr, 4), "sentiment": classify_pcr(pcr)} if pcr else {"status": "unavailable", "note": "Futu Basic tier - upgrade needed for PCR data"}
    
    if args.mode in ("quick", "full", "unusual"):
        result["unusual"] = get_unusual_options(args.symbol)
    
    if args.mode == "full":
        result["options_chain"] = "Use Futu OpenAPI get_option_list() for detailed chain"
    
    print(json.dumps(result, ensure_ascii=False, indent=2))
    _close_futu_ctx()

if __name__ == "__main__":
    main()
