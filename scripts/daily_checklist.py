# daily_checklist.py - Enhanced with VIX and sector heat
import json, sys, argparse, os, time
from datetime import datetime, time as dt_time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cache_util import get_cached

try:
    HAS_SIGNALS = True
except ImportError:
    HAS_SIGNALS = False

try:
    from market_sentiment import get_vix, get_market_overview
    HAS_MARKET = True
except ImportError:
    HAS_MARKET = False

WATCHLIST_PATH = os.path.expanduser("~/.us_stock_watchlist.json")

def check_stock(symbol):
    """Check a single stock for signals"""
    result = {"symbol": symbol, "timestamp": datetime.now().isoformat()}
    try:
        data = tech_analyze(symbol, timeframe="1d", output_json=True)
        result["rating"] = data.get("rating", "")
        result["score"] = data.get("score", 0)
        result["trade_plan"] = data.get("trade_plan", {})
        result["signals"] = data.get("summary", {}).get("signals", [])
        result["resonance"] = data.get("resonance", {}).get("alignment", "")
        result["price"] = data.get("last_close", 0)
        result["status"] = "ok"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    return result

def get_vix_level():
    """Get VIX level for market context."""
    if not HAS_MARKET:
        return None
    try:
        vix_data = get_vix()
        return vix_data.get("level", "unknown"), vix_data.get("value", 0)
    except Exception:
        return None, 0

def get_sector_heat():
    """Get sector heat ranking for market context."""
    if not HAS_MARKET:
        return []
    try:
        from scan_stocks import run_sector
        result = run_sector(top=5)
        if result.get("status") == "ok":
            return result.get("data", [])
    except Exception:
        pass
    return []

def pre_market_check():
    """Run pre-market checklist for watchlist"""
    if not os.path.exists(WATCHLIST_PATH):
        return {"status": "empty", "message": "No watchlist found"}
    with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
        wl = json.load(f)
    
    results = []
    buy_signals = []
    sell_signals = []
    
    for item in wl.get("watchlist", []):
        symbol = item["symbol"]
        check = check_stock(symbol)
        results.append(check)
        
        rating = check.get("rating", "")
        score = check.get("score", 0)
        tp = check.get("trade_plan", {})
        
        if rating in ("Overweight", "Buy", "Strong Buy") and score >= 60:
            rr = tp.get("risk_reward", 0)
            if rr >= 2.0:
                buy_signals.append({
                    "symbol": symbol, "rating": rating, "score": score,
                    "entry": tp.get("entry_zone", 0), "stop": tp.get("stop_loss", 0),
                    "rr": rr, "note": item.get("note", "")
                })
        elif rating in ("Underweight", "Sell", "Strong Sell"):
            sell_signals.append({
                "symbol": symbol, "rating": rating, "score": score,
                "note": item.get("note", "")
            })
    
    # Add market context
    market_context = {}
    vix_level, vix_value = get_vix_level()
    if vix_level:
        market_context["vix"] = {"level": vix_level, "value": vix_value}
    sector_heat = get_sector_heat()
    if sector_heat:
        market_context["sector_heat"] = sector_heat
    
    return {
        "generated_at": datetime.now().isoformat(),
        "total_checked": len(results),
        "buy_candidates": buy_signals,
        "sell_candidates": sell_signals,
        "market_context": market_context,
        "all_results": results
    }

def main():
    parser = argparse.ArgumentParser(description="Daily Pre-Market Checklist")
    parser.add_argument("--symbols", nargs="*", help="Override watchlist with specific symbols")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    
    if args.symbols:
        results = []
        for sym in args.symbols:
            results.append(check_stock(sym))
        output = {"generated_at": datetime.now().isoformat(), "symbols_checked": len(results), "results": results}
    else:
        output = pre_market_check()
    
    print(json.dumps(output, ensure_ascii=False, indent=2))
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json.dumps(output, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
