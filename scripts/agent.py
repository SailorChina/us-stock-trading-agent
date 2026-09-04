#!/usr/bin/env python3
"""US Stock Trading Agent - Main Entry Point"""
import argparse, json, sys, os, time
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

try:
    from us_stock_analyzer import normalize_symbol, get_price, get_tech_analysis, get_news
    from market_sentiment import get_market_overview, get_vix, get_magnificent_seven
    from news_sentiment import fetch_news, analyze_news, get_sentiment_summary
    from options_analysis import get_futu_iv, get_options_pcr, get_unusual_options
    from watchlist import load_watchlist, add_stock, remove_stock
    from daily_checklist import pre_market_check, check_stock
    from trade_journal import add_trade, list_trades
    from risk_manager import generate_risk_report, dynamic_position_size
    from backtest import simple_ma_strategy
    from cache_util import get_cached
    MOD_OK = True
except ImportError as e:
    MOD_OK = False
    print(f"Warning: some modules unavailable: {e}", file=sys.stderr)


def _adjust_trade_plan(tp, current_price, atr):
    """Adjust entry_zone to be near current price with pullback margin.
    
    stock_signals returns VWAP-based entry_zone which can be days old.
    This recalculates entry relative to the latest close price.
    """
    if not tp or not current_price or current_price <= 0:
        return tp
    # Pull back 1.5% from current price as entry (wait for dip)
    entry = round(current_price * 0.985, 2)
    if atr and atr > 0:
        stop = round(entry - atr * 2.0, 2)
    else:
        stop = round(entry * 0.95, 2)
    risk = entry - stop
    tp1 = round(entry + risk * 2.0, 2)
    tp2 = round(entry + risk * 2.5, 2)
    rr = round((tp1 - entry) / risk, 2) if risk > 0 else 0
    return {
        **tp,
        "entry_zone": entry,
        "stop_loss": stop,
        "target_1": tp1,
        "target_2": tp2,
        "risk_reward": rr,
        "risk_usd": round(risk * tp.get("position_size_pct", 3) * current_price / 100, 2),
        "reward_usd": round((tp1 - entry) * tp.get("position_size_pct", 3) * current_price / 100, 2),
        "current_price": current_price,
        "atr": atr,
        "entry_note": f"Adjusted from VWAP {tp.get('entry_zone')} to pullback entry near current price",
    }


def run_full_analysis(symbol, timeframe="1d"):
    """Run complete analysis for a stock"""
    print(f"Running full analysis for {symbol}...", file=sys.stderr)
    t0 = time.time()
    report = {
        "symbol": symbol,
        "generated_at": datetime.now().isoformat(),
        "modules": {}
    }
    report["modules"]["price"] = get_price(symbol)
    report["modules"]["tech"] = get_tech_analysis(symbol, timeframe)
    report["modules"]["news"] = get_news(symbol)
    try:
        news_data = report["modules"]["news"].get("data", {}).get("data", [])
        if news_data:
            analysis, sentiments = analyze_news(news_data)
            report["modules"]["news_sentiment"] = {"summary": get_sentiment_summary(sentiments), "news": analysis}
    except Exception:
        pass
    report["modules"]["options"] = {
        "iv": {"value": get_futu_iv(symbol), "status": "ok" if get_futu_iv(symbol) else "unavailable"},
        "pcr": {"value": get_options_pcr(symbol), "status": "ok" if get_options_pcr(symbol) else "unavailable"},
        "unusual": get_unusual_options(symbol)
    }
    report["elapsed_sec"] = round(time.time() - t0, 1)
    return report


def run_quick_signal(symbol):
    """Get quick buy/sell signal with price-adjusted trade plan"""
    try:
        data = get_tech_analysis(symbol)["data"]
        rating = data.get("rating", "")
        score = data.get("score", 0)
        tp = data.get("trade_plan", {})
        ta = data.get("technical_analysis", {})
        signals = data.get("summary", {}).get("signals", [])
        
        # Get current price and ATR
        price_data = get_price(symbol).get("data", {})
        current_price = price_data.get("latest_price", 0)
        atr = ta.get("atr_14")
        
        # Adjust trade plan entry to be near current price
        adjusted_tp = _adjust_trade_plan(tp, current_price, atr)
        rr = adjusted_tp.get("risk_reward", 0)
        
        signal = {
            "symbol": symbol,
            "current_price": current_price,
            "rating": rating,
            "score": score,
            "signals": signals,
            "resonance": data.get("resonance", {}).get("alignment", ""),
            "trade_plan": adjusted_tp,
            "action": None
        }
        
        if rating in ("Overweight", "Buy", "Strong Buy") and score >= 60 and rr >= 2.0:
            signal["action"] = "BUY"
            signal["reason"] = f"{rating} score={score} RR={rr}:1 entry={adjusted_tp.get('entry_zone')}"
        elif rating in ("Underweight", "Sell", "Strong Sell"):
            signal["action"] = "SELL"
            signal["reason"] = f"{rating}"
        else:
            signal["action"] = "HOLD"
            signal["reason"] = f"Score {score} below threshold or RR < 2"
        
        return signal
    except Exception as e:
        return {"symbol": symbol, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="US Stock Trading Agent v2",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog="""
Examples:
  python agent.py analyze NVDA               # Full analysis
  python agent.py signal AAPL                # Quick signal
  python agent.py watchlist                  # List watchlist
  python agent.py watchlist add MSFT \"均线\"  # Add to watchlist
  python agent.py checklist                  # Pre-market check
  python agent.py report NVDA                # Quick report
""")
    parser.add_argument("command", choices=["analyze", "signal", "watchlist", "checklist", "report"],
                       help="Command to run")
    parser.add_argument("symbol", nargs="?", help="Stock symbol (e.g., NVDA, US.NVDA)")
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--output", default=None)
    parser.add_argument("--json", action="store_true", help="Raw JSON output")
    parser.add_argument("--verbose", action="store_true", help="Show detailed output")
    args = parser.parse_args()
    
    if not MOD_OK:
        print("Error: required modules not available", file=sys.stderr)
        sys.exit(1)
    
    if args.command == "analyze":
        if not args.symbol:
            print("需要 --symbol", file=sys.stderr)
            sys.exit(1)
        symbol = normalize_symbol(args.symbol)
        result = run_full_analysis(symbol, args.timeframe)
        output = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    elif args.command == "signal":
        if not args.symbol:
            print("需要 --symbol", file=sys.stderr)
            sys.exit(1)
        symbol = normalize_symbol(args.symbol)
        result = run_quick_signal(symbol)
        if args.json:
            output = json.dumps(result, ensure_ascii=False, indent=2)
        elif args.verbose:
            tech = get_tech_analysis(symbol, args.timeframe)
            output = json.dumps({"signal": result, "tech": tech}, ensure_ascii=False, indent=2)
        else:
            output = json.dumps({k: v for k, v in result.items() if k in ("symbol", "current_price", "rating", "score", "action", "reason", "trade_plan")}, ensure_ascii=False, indent=2)
    elif args.command == "watchlist":
        result = load_watchlist()
        output = json.dumps(result, ensure_ascii=False, indent=2)
    elif args.command == "checklist":
        result = pre_market_check()
        output = json.dumps(result, ensure_ascii=False, indent=2)
    elif args.command == "report":
        if not args.symbol:
            print("需要 --symbol", file=sys.stderr)
            sys.exit(1)
        symbol = normalize_symbol(args.symbol)
        price = get_price(symbol)
        tech = get_tech_analysis(symbol)
        news = get_news(symbol)
        report = {
            "symbol": symbol,
            "generated_at": datetime.now().isoformat(),
            "tech_rating": tech.get("data", {}).get("rating", ""),
            "tech_score": tech.get("data", {}).get("score", 0),
            "trade_plan": tech.get("data", {}).get("trade_plan", {}),
            "news_count": len(news.get("data", {}).get("data", [])) if news.get("data") else 0,
        }
        if args.json or args.verbose:
            report["price"] = price.get("data", {})
        output = json.dumps(report, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Saved: {args.output}", file=sys.stderr)
    else:
        print(output)

if __name__ == "__main__":
    main()
