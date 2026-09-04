#!/usr/bin/env python3
import json, sys, os, time, urllib.request
from cache_util import retry_call
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_YAHOO_INDICATORS = {"VIX": "^VIX", "DXY": "DX-Y.NYB", "10Y": "^TNX", "2Y": "^IRX"}

def _yahoo_get_indicator(symbol, period="10d"):
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/" + symbol + "?" + "interval=1d" + chr(38) + "period=" + period
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = retry_call(lambda: (lambda: json.loads(urllib.request.urlopen(req, timeout=10)).read()))()
        result = data.get("chart", {}).get("result")
        if result and result[0]["indicators"]["quote"][0]["close"]:
            closes = result[0]["indicators"]["quote"][0]["close"]
            valid = [x for x in closes if x is not None]
            if valid:
                return {"price": round(valid[-1], 4), "prev": round(valid[-2], 4) if len(valid) > 1 else valid[-1]}
    except Exception:
        pass
    return None

def get_macro_snapshot():
    result = {"generated_at": datetime.now().isoformat(), "indicators": {}, "market_regime": ""}
    try:
        from market_sentiment import get_vix
        vix_data = get_vix()
        result["indicators"]["VIX"] = {"value": vix_data.get("value", 0), "level": vix_data.get("level", "unknown")}
    except Exception:
        pass
    for code, yahoo_sym in _YAHOO_INDICATORS.items():
        q = _yahoo_get_indicator(yahoo_sym)
        if q:
            chg = round((q["price"] - q["prev"]) / q["prev"] * 100, 4) if q["prev"] else 0
            result["indicators"][code] = {"price": q["price"], "change_pct": chg, "source": "yahoo"}
    vix_val = result["indicators"].get("VIX", {}).get("value", 20)
    if vix_val < 15: result["market_regime"] = "calm"
    elif vix_val < 20: result["market_regime"] = "normal"
    elif vix_val < 30: result["market_regime"] = "elevated"
    else: result["market_regime"] = "fear"
    return result

def list_macro_events():
    return [
        {"code": "CPI", "name": "Consumer Price Index", "freq": "monthly", "importance": "high"},
        {"code": "FOMC", "name": "Fed Rate Decision", "freq": "8x/year", "importance": "critical"},
        {"code": "NFP", "name": "Non-Farm Payrolls", "freq": "monthly", "importance": "high"},
        {"code": "VIX", "name": "CBOE Volatility Index", "freq": "daily", "importance": "medium"},
        {"code": "10Y", "name": "10-Year Treasury Yield", "freq": "daily", "importance": "medium"},
    ]

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Macro Economic Calendar")
    parser.add_argument("--mode", default="snapshot", choices=["snapshot", "events"])
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    if args.mode == "snapshot": data = get_macro_snapshot()
    else: data = {"events": list_macro_events()}
    out = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f: f.write(out)
        print(f"Saved: {args.output}", file=sys.stderr)
    else: print(out)

if __name__ == "__main__": main()
