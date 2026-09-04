#!/usr/bin/env python3
import json, sys, os, time, urllib.request
from cache_util import retry_call
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_WATCHLIST = [
    "US.NVDA", "US.AAPL", "US.MSFT", "US.AMZN", "US.META", "US.GOOG", "US.TSLA",
    "US.SPY", "US.QQQ", "US.IWM",
]

def _yahoo_get_change(symbol, period="1d"):
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/" + symbol + "?" + "interval=1d" + chr(38) + "period=" + period
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = retry_call(lambda: (lambda: json.loads(urllib.request.urlopen(req, timeout=8)).read()))()
        result = data.get("chart", {}).get("result")
        if result and result[0]["indicators"]["quote"][0]["close"]:
            closes = result[0]["indicators"]["quote"][0]["close"]
            valid = [x for x in closes if x is not None]
            if len(valid) >= 2:
                return {"price": round(valid[-1], 2), "prev": round(valid[-2], 2), "change_pct": round((valid[-1] - valid[-2]) / valid[-2] * 100, 2)}
    except Exception:
        pass
    return None

def run_premarket_scan(top=10, threshold=1.0):
    t0 = time.time()
    results = []
    for sym in _WATCHLIST:
        q = _yahoo_get_change(sym, period="5d")
        if q:
            results.append({"symbol": sym, "price": q["price"], "change_pct": q["change_pct"],
                "type": "mover" if abs(q["change_pct"]) >= threshold else "normal"})
    results.sort(key=lambda x: abs(x["change_pct"]), reverse=True)
    elapsed = time.time() - t0
    return {"status": "ok", "generated_at": datetime.now().isoformat(),
            "elapsed_sec": round(elapsed, 1), "threshold": threshold,
            "top_movers": results[:top], "total_scanned": len(results)}

def run_afterhours_scan(top=10):
    return run_premarket_scan(top=top, threshold=0.5)

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Pre-market / After-hours Movers Scanner")
    parser.add_argument("--mode", default="premarket", choices=["premarket", "afterhours"])
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--threshold", type=float, default=1.0)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    if args.mode == "premarket": data = run_premarket_scan(args.top, args.threshold)
    else: data = run_afterhours_scan(args.top)
    out = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f: f.write(out)
        print(f"Saved: {args.output}", file=sys.stderr)
    else: print(out)

if __name__ == "__main__": main()
