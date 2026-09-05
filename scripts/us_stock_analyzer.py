#!/usr/bin/env python3
"""US Stock Analyzer - direct imports, no subprocess"""
import argparse, json, sys, os, time
from cache_util import retry_call
from datetime import datetime

# Add paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

HAS_SIGNALS = False

# Symbol normalization
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

def get_price(symbol):
    result = {"module": "price", "status": "pending"}
    try:
        df = fetch_kline(symbol, ktype="1d", num=5)
        if df is not None and len(df) > 1:
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            result["status"] = "ok"
            result["data"] = {
                "symbol": symbol,
                "latest_price": float(latest["close"]),
                "latest_time": str(latest["time"])[:10],
                "prev_close": float(prev["close"]),
                "change_pct": round((float(latest["close"]) - float(prev["close"])) / float(prev["close"]) * 100, 2),
                "volume": float(latest["volume"]),
            }
        else:
            result["status"] = "error"
            result["error"] = "K-line data insufficient"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    return result

def get_tech_analysis(symbol, timeframe="1d"):
    result = {"module": "tech", "status": "pending"}
    if not HAS_SIGNALS:
        result["status"] = "skipped"
        result["error"] = "library unavailable"
        return result
    try:
        import io
        _old_stdout = sys.stdout
        sys.stdout = _fake_stdout = io.StringIO()
        try:
            tech_analyze = None
            data = tech_analyze(symbol, timeframe=timeframe, output_json=True)
        finally:
            sys.stdout = _old_stdout
        # Fix last_time: override with actual kline date
        try:
            df = fetch_kline(symbol, ktype="1d", num=5)
            if df is not None and len(df) > 0:
                actual_date = str(df.iloc[-1]["time"])[:10]
                if "technical_analysis" in data and "last_time" in data["technical_analysis"]:
                    data["technical_analysis"]["last_time"] = actual_date
                data["last_time"] = actual_date
                # Also fix timestamp field
                data["timestamp"] = actual_date + " 00:00:00"
        except Exception:
            pass
        result["status"] = "ok"
        result["data"] = data
        # Also keep raw text for display
        result["raw"] = _format_tech_output(data)
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    return result

def _format_tech_output(data):
    """Format tech analysis data into readable text"""
    lines = []
    lines.append("=" * 60)
    lines.append(f"  {data.get('code', '')}  Technical Analysis")
    lines.append(f"  Rating: {data.get('rating', '')} (Score: {data.get('score', '')}/100)")
    lines.append(f"  Confidence: {data.get('confidence', '')}")
    lines.append("")
    
    # Dimensions
    dims = data.get("dimensions", {})
    lines.append("  Dimension Scores:")
    for dim, info in dims.items():
        score = info.get("score", 0)
        reason = info.get("reason", "")
        bar_len = int(score / 10)
        bar = "#" * bar_len + "-" * (10 - bar_len)
        lines.append(f"    {dim.capitalize():10s}: [{bar}] {score}  ({info.get('weight', 0)*100:.0f}%)")
        lines.append(f"              {reason[:60]}")
    lines.append("")
    
    # Signals
    signals = data.get("summary", {}).get("signals", [])
    if signals:
        lines.append("  Signals:")
        for s in signals:
            lines.append(f"    - {s}")
    lines.append("")
    
    # Resonance
    res = data.get("resonance", {})
    if res:
        lines.append("  Multi-Timeframe Resonance:")
        lines.append(f"    Daily: {res.get('daily_rating', '')} ({res.get('daily_score', '')})")
        lines.append(f"    Weekly: {res.get('weekly_rating', '')} ({res.get('weekly_score', '')})")
        lines.append(f"    Monthly: {res.get('monthly_rating', '')} ({res.get('monthly_score', '')})")
        lines.append(f"    Alignment: {res.get('alignment', '')} (+{res.get('confidence_boost', 0)} confidence)")
    lines.append("")
    
    # Support/Resistance
    sr = data.get("support_resistance", {})
    if sr:
        lines.append("  Support/Resistance:")
        lines.append(f"    R1: {sr.get('resistance_1', '')}  R2: {sr.get('resistance_2', '')}")
        lines.append(f"    S1: {sr.get('support_1', '')}  S2: {sr.get('support_2', '')}")
        lines.append(f"    VWAP: {sr.get('vwap', '')}")
    lines.append("")
    
    # Trade Plan
    tp = data.get("trade_plan", {})
    if tp:
        lines.append("  Trade Plan:")
        lines.append(f"    Entry: {tp.get('entry_zone', '')}")
        lines.append(f"    Stop:  {tp.get('stop_loss', '')}")
        lines.append(f"    Target1: {tp.get('target_1', '')}  Target2: {tp.get('target_2', '')}")
        lines.append(f"    R:R = {tp.get('risk_reward', '')}:1  Position: {tp.get('position_size_pct', '')}%")
    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)

def get_capital_anomaly(symbol, time_range=7):
    result = {"module": "capital", "status": "pending"}
    try:
        script = os.path.join(SCRIPT_DIR, "..", "..", ".codex", "skills", "futu-capital-anomaly", "scripts", "handle_capital_anomaly.py")
        if not os.path.exists(script):
            # Try alternative path
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
    
    # Output
    if args.json:
        output = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    else:
        # Pretty format
        output = json.dumps(report, ensure_ascii=False, indent=2, default=str)
        # Try to add tech raw output if available
        tech = report["modules"].get("tech", {})
        if tech.get("status") == "ok" and tech.get("raw"):
            output = output[:-1]  # Remove trailing }
            output += ',\n  "display": ' + json.dumps(tech["raw"], ensure_ascii=False) + "\n}"
    
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Saved: {args.output}", file=sys.stderr)
    else:
        print(output)

if __name__ == "__main__":
    main()
