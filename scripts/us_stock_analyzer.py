#!/usr/bin/env python3
"""US Stock Analyzer - uses tech_engine for all analysis"""
import argparse, json, sys, os, time
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from tech_engine import (
    fetch_kline, get_price, get_tech_summary, generate_signal,
    format_tech_output, get_premarket_hot, get_hot_list,
    scan_premarket, scan_hot_list,
)

SYMBOL_MAP = {
    "nvda": "US.NVDA", "yingweida": "US.NVDA",
    "tsla": "US.TSLA", "tesila": "US.TSLA",
    "aapl": "US.AAPL", "pingguo": "US.AAPL", "apple": "US.AAPL",
    "msft": "US.MSFT", "weiruan": "US.MSFT", "microsoft": "US.MSFT",
    "goog": "US.GOOG", "guge": "US.GOOG", "google": "US.GOOG", "alphabet": "US.GOOG",
    "amzn": "US.AMZN", "yamaxun": "US.AMZN", "amazon": "US.AMZN",
    "meta": "US.META", "lianfu": "US.META", "facebook": "US.META",
    "nflx": "US.NFLX", "nifei": "US.NFLX", "netflix": "US.NFLX",
    "amd": "US.AMD", "chaowei": "US.AMD",
}

def normalize_symbol(raw):
    key = raw.strip().lower()
    if key in SYMBOL_MAP:
        return SYMBOL_MAP[key]
    if key.startswith("us."):
        return key.upper()
    if len(key) <= 5 and key.isalpha():
        return f"US.{key.upper()}"
    raise ValueError(f"cannot recognize symbol: {raw}")

def get_tech_analysis(symbol, timeframe="1d"):
    return generate_signal(symbol, timeframe=timeframe, num_bars=60)

def get_capital_anomaly(symbol, time_range=7):
    result = {"module": "capital", "status": "pending"}
    try:
        script = os.path.join(SCRIPT_DIR, "..", "..", ".codex", "skills", "futu-capital-anomaly", "scripts", "handle_capital_anomaly.py")
        if not os.path.exists(script):
            alt = os.path.join(SCRIPT_DIR, "futu-capital-anomaly", "scripts", "handle_capital_anomaly.py")
            if os.path.exists(alt):
                script = alt
        if os.path.exists(script):
            import subprocess
            cmd = [sys.executable, script, symbol, "--time-range", str(time_range), "--json"]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                result["status"] = "ok"
                try:
                    result["data"] = json.loads(r.stdout)
                except Exception:
                    result["data"] = {"text": r.stdout}
            else:
                result["status"] = "error"
                result["error"] = r.stderr[:200]
        else:
            result["status"] = "skipped"
            result["note"] = "futu-capital-anomaly skill not installed"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    return result

def get_news(symbol, size=10):
    result = {"module": "news", "status": "pending"}
    try:
        ticker = symbol.split(".")[-1] if "." in symbol else symbol
        import urllib.request, urllib.parse
        params = urllib.parse.urlencode({"keyword": ticker, "size": str(size), "sort_type": "2", "lang": "zh-CN"})
        req = urllib.request.Request(
            f"https://ai-news-search.futunn.com/news_search?{params}",
            headers={"User-Agent": "us-stock-agent/2.0"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result["status"] = "ok"
            result["data"] = json.loads(resp.read().decode())
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    return result

def main():
    parser = argparse.ArgumentParser(description="US Stock Analyst v2")
    parser.add_argument("symbol")
    parser.add_argument("--dimensions", default="all")
    parser.add_argument("--time-range", type=int, default=7)
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--output", default=None)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--json", action="store_true", help="Raw JSON output")
    args = parser.parse_args()

    try:
        symbol = normalize_symbol(args.symbol)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Analyzing {symbol}...", file=sys.stderr)
    t0 = time.time()

    dims = []
    if args.quick:
        dims = ["tech"]
    elif args.dimensions == "all":
        dims = ["price", "tech", "capital", "news"]
    else:
        dims = args.dimensions.split(",")

    report = {
        "symbol": symbol,
        "analyzed_at": datetime.now().isoformat(),
        "config": {"time_range": args.time_range, "timeframe": args.timeframe},
        "elapsed_sec": 0,
        "modules": {}
    }

    for dim in dims:
        if dim == "price":
            report["modules"]["price"] = get_price(symbol)
        elif dim == "tech":
            report["modules"]["tech"] = get_tech_analysis(symbol, args.timeframe)
        elif dim == "capital":
            report["modules"]["capital"] = get_capital_anomaly(symbol, args.time_range)
        elif dim == "news":
            report["modules"]["news"] = get_news(symbol)
        else:
            report["modules"][dim] = {"status": "skipped"}

    report["elapsed_sec"] = round(time.time() - t0, 1)

    if args.json:
        output = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    else:
        output = json.dumps(report, ensure_ascii=False, indent=2, default=str)
        tech = report["modules"].get("tech", {})
        if tech.get("status") == "ok" and tech.get("data"):
            display = format_tech_output(tech)
            output = output[:-1]
        escaped = display.replace(chr(10), chr(92)+chr(110)).replace(chr(34), chr(92)+chr(34))

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Saved: {args.output}", file=sys.stderr)
    else:
        print(output)

if __name__ == "__main__":
    main()
