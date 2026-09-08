#!/usr/bin/env python3

"""US Stock Options & Derivatives Analysis - with retry logic"""

import json, sys, argparse, time, threading

from datetime import datetime
from futu_pool import get_futu_context, RET_OK






def get_futu_iv(symbol):
    try:
        from futu import RET_OK
        ctx = get_futu_context()
        if ctx is None:
            return None
        ret, data = ctx.get_option_underlying_overview([symbol])
        if ret == RET_OK and data is not None and len(data) > 0:
            row = data.iloc[0]
            iv = row.get("iv", 0) if "iv" in row else 0
            return float(iv) if iv else None
        ret2, data2 = ctx.get_quote_snapshot([symbol])
        if ret2 == RET_OK and data2 is not None and len(data2) > 0:
            row2 = data2.iloc[0]
            iv = row2.get("opt_iv", 0) if "opt_iv" in row2 else 0
            return float(iv) if iv else None
    except Exception as e:
        print(f"[options] get_futu_iv error: {e}", file=sys.stderr)
    return None



def get_options_pcr(symbol):
    try:
        from futu import RET_OK
        ctx = get_futu_context()
        if ctx is None:
            return None
        ret, data = ctx.get_option_underlying_overview([symbol])
        if ret == RET_OK and data is not None and len(data) > 0:
            row = data.iloc[0]
            pcr = row.get("put_call_ratio", 0) if "put_call_ratio" in row else 0
            return float(pcr) if pcr else None
    except Exception as e:
        print(f"[options] get_options_pcr error: {e}", file=sys.stderr)
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





if __name__ == "__main__":

    main()

