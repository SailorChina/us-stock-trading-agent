#!/usr/bin/env python3
"""Auto Analyzer - periodic watchlist analysis with scheduling."""
import argparse, json, os, sys, time, glob
from datetime import datetime, timedelta
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

WATCHLIST_PATH = os.path.expanduser("~/.us_stock_watchlist.json")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "..", "data")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def run_single_analysis(symbol, timeframe="1d"):
    """Run full analysis on a single stock."""
    result = {"symbol": symbol, "analyzed_at": datetime.now().isoformat()}
    try:
        from us_stock_analyzer import get_price, get_tech_analysis, get_news
        from news_sentiment import fetch_news, analyze_news, get_sentiment_summary
        from market_sentiment import get_vix

        price = get_price(symbol)
        tech = get_tech_analysis(symbol, timeframe)
        news = get_news(symbol)

        # News sentiment
        news_list = news.get("data", {}).get("data", []) if news.get("data") else []
        sentiment = None
        if news_list:
            try:
                analysis, sentiments = analyze_news(news_list)
                sentiment = get_sentiment_summary(sentiments)
            except Exception:
                pass

        # Determine signal
        rating = tech.get("data", {}).get("rating", "")
        score = tech.get("data", {}).get("score", 0)
        tp = tech.get("data", {}).get("trade_plan", {})
        rr = tp.get("risk_reward", 0)

        action = "HOLD"
        if rating in ("Overweight", "Buy", "Strong Buy") and score >= 60 and rr >= 2.0:
            action = "BUY"
        elif rating in ("Underweight", "Sell", "Strong Sell"):
            action = "SELL"

        result.update({
            "price": price.get("data", {}),
            "tech_rating": rating,
            "tech_score": score,
            "trade_plan": tp,
            "action": action,
            "news_sentiment": sentiment,
            "signals": tech.get("data", {}).get("summary", {}).get("signals", []),
            "resonance": tech.get("data", {}).get("resonance", {}).get("alignment", ""),
        })
    except Exception as e:
        result["error"] = str(e)
    return result


def load_watchlist():
    """Load watchlist from file."""
    if not os.path.exists(WATCHLIST_PATH):
        return []
    with open(WATCHLIST_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("watchlist", [])


def save_report(results, output_path=None):
    """Save analysis report to JSON file."""
    if output_path is None:
        date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(OUTPUT_DIR, f"auto_analysis_{date_str}.json")
    report = {
        "generated_at": datetime.now().isoformat(),
        "total_stocks": len(results),
        "results": results,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    return output_path


def print_summary(results):
    """Print summary of analysis results."""
    buys = [r for r in results if r.get("action") == "BUY"]
    sells = [r for r in results if r.get("action") == "SELL"]
    holds = [r for r in results if r.get("action") == "HOLD"]

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"Auto Analysis Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"Total: {len(results)} stocks | BUY: {len(buys)} | SELL: {len(sells)} | HOLD: {len(holds)}", file=sys.stderr)

    if buys:
        print(f"\n[BUY CANDIDATES]", file=sys.stderr)
        for r in buys:
            tp = r.get("trade_plan", {})
            print(f"  {r['symbol']}: {r['tech_rating']} ({r['tech_score']}) "
                  f"Entry={tp.get('entry_zone','?')} Stop={tp.get('stop_loss','?')} RR={tp.get('risk_reward','?')}:1",
                  file=sys.stderr)

    if sells:
        print(f"\n[SELL CANDIDATES]", file=sys.stderr)
        for r in sells:
            print(f"  {r['symbol']}: {r['tech_rating']} ({r['tech_score']})", file=sys.stderr)

    if not buys and not sells:
        print("\n[NO SIGNALS] All watchlist stocks in HOLD mode", file=sys.stderr)


def run_once(output_path=None):
    """Run one analysis cycle."""
    watchlist = load_watchlist()
    if not watchlist:
        print("Watchlist is empty. Add stocks with: python scripts/watchlist.py --action add SYMBOL",
              file=sys.stderr)
        return []

    results = []
    for item in watchlist:
        symbol = item.get("symbol", "")
        if symbol:
            print(f"Analyzing {symbol}...", file=sys.stderr)
            result = run_single_analysis(symbol)
            results.append(result)

    saved_path = save_report(results, output_path)
    print_summary(results)
    print(f"\nReport saved: {saved_path}", file=sys.stderr)
    return results


def run_daemon(interval_hours=1):
    """Run analysis in a loop with specified interval."""
    print(f"Auto Analyzer daemon started. Interval: {interval_hours}h. Press Ctrl+C to stop.",
          file=sys.stderr)
    while True:
        try:
            run_once()
        except KeyboardInterrupt:
            print("\nStopping auto analyzer.", file=sys.stderr)
            break
        except Exception as e:
            print(f"Error in analysis cycle: {e}", file=sys.stderr)
        time.sleep(interval_hours * 3600)


def main():
    parser = argparse.ArgumentParser(description="Auto Analyzer - Periodic Watchlist Analysis")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--daemon", action="store_true", help="Run continuously")
    parser.add_argument("--interval", type=float, default=1.0, help="Hours between runs (daemon mode)")
    parser.add_argument("--output", default=None, help="Output JSON path")
    parser.add_argument("--symbols", nargs="*", help="Override watchlist with specific symbols")
    args = parser.parse_args()

    if args.symbols:
        # Quick analysis for specific symbols
        results = []
        for sym in args.symbols:
            print(f"Analyzing {sym}...", file=sys.stderr)
            results.append(run_single_analysis(sym))
        saved = save_report(results, args.output)
        print_summary(results)
        print(f"Report saved: {saved}", file=sys.stderr)
    elif args.daemon:
        run_daemon(args.interval)
    else:
        run_once(args.output)


if __name__ == "__main__":
    main()
