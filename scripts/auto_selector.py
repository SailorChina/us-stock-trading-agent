#!/usr/bin/env python3
"""Auto Selector - One-Click Stock Selection + Full Analysis.

Usage:
  python scripts/auto_selector.py              # default: top 5, score>=15
  python scripts/auto_selector.py --top 10 --min 20
  python scripts/auto_selector.py --json
  python scripts/auto_selector.py --verbose
"""
import argparse, json, os, sys, time, threading
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from smart_money_screener import scan_smart_money
from tech_engine import get_hot_list_futu, generate_signal


def _futu_available(timeout=2):
    import socket
    try:
        socket.create_connection(("127.0.0.1", 11111), timeout=timeout)
        return True
    except Exception:
        return False


def scan_smart(top_n=30, min_score=15):
    try:
        results = scan_smart_money(top_n=top_n, min_score=min_score)
        return {"status": "ok", "count": len(results), "data": results}
    except Exception as e:
        return {"status": "error", "error": str(e), "count": 0, "data": []}


def scan_hot(top_n=30):
    try:
        stocks = get_hot_list_futu(top=top_n)
        return {"status": "ok" if stocks else "empty", "count": len(stocks), "data": stocks}
    except Exception as e:
        return {"status": "error", "error": str(e), "count": 0, "data": []}


def merge_and_rank(smart_result, hot_result, top_n=10):
    smart_map = {r["symbol"]: r for r in smart_result.get("data", [])}
    hot_map = {s["code"]: s for s in hot_result.get("data", [])}
    all_symbols = set(smart_map.keys()) | set(hot_map.keys())
    candidates = []
    for sym in all_symbols:
        sm = smart_map.get(sym, {})
        ht = hot_map.get(sym, {})
        smart_score = sm.get("total_score", 0)
        hot_score = ht.get("hot_score", 0)
        hot_norm = min(hot_score / 100.0 * 30, 30) if hot_score > 0 else 0
        composite = smart_score + hot_norm
        price_data = sm.get("price") or {}
        price = price_data.get("latest_price", 0)
        chg = price_data.get("change_pct", 0)
        sources = []
        if smart_score > 0: sources.append("smart")
        if hot_score > 0: sources.append("hot")
        candidates.append({
            "symbol": sym, "smart_score": smart_score,
            "hot_score_raw": hot_score, "hot_score_norm": round(hot_norm, 1),
            "composite": round(composite, 1), "price": price,
            "change_pct": chg, "sources": sources,
        })
    for c in candidates:
        try:
            t = generate_signal(c["symbol"], num_bars=60)
            if t.get("status") == "ok":
                d = t["data"]
                c["tech_rating"] = d.get("rating", "")
                c["tech_score"] = d.get("score", 0)
                c["tech_signal"] = d.get("signal", "")
                c["composite"] = round(c["composite"] + d.get("score",0)*25/100, 1)
            else:
                c["tech_rating"] = ""; c["tech_score"] = 0; c["tech_signal"] = ""
        except Exception:
            c["tech_rating"] = ""; c["tech_score"] = 0; c["tech_signal"] = ""
    candidates.sort(key=lambda x: x["composite"], reverse=True)
    return candidates[:top_n]


def run_full_analysis(symbol, timeframe="1d", smart_money_data=None, price_map=None, tech_cache=None):
    from us_stock_analyzer import get_price, get_tech_analysis, get_news
    # Override price module with cached data from smart money scan
    cached_price = (price_map or {}).get(symbol)
    # Override tech module with cached data from smart money scan
    cached_tech = (tech_cache or {}).get(symbol)
    from news_sentiment import fetch_news, analyze_news, get_sentiment_summary
    from options_analysis import get_futu_iv, get_options_pcr, get_unusual_options
    from candlestick_patterns import get_latest_patterns
    from enhanced_indicators import enhanced_signal_score
    from earnings_analyzer import get_earnings_summary
    from decision_engine import compute_decision_fast
    from market_regime import get_regime
    from tech_engine import fetch_kline

    print(f"  Running FULL analysis for {symbol}...", file=sys.stderr)
    t0 = time.time()
    report = {"symbol": symbol, "generated_at": datetime.now().isoformat(), "modules": {}, "summary": {}}
    results = {}
    errors = {}

    def _run(name, fn):
        try: results[name] = fn()
        except Exception as e: errors[name] = str(e)

    def _news_fn(sym):
        n = get_news(sym)
        nd = n.get("data", {}).get("data", [])
        if nd:
            a, s = analyze_news(nd)
            return {"raw": n, "sentiment": {"signals": get_sentiment_summary(s), "news": a}}
        return {"raw": n}

    def _options_fn(sym):
        iv = get_futu_iv(sym)
        pcr = get_options_pcr(sym)
        return {"iv": {"value": iv, "status": "ok" if iv else "unavailable"},
                "pcr": {"value": pcr, "status": "ok" if pcr else "unavailable"},
                "unusual": get_unusual_options(sym)}

    def _candlestick_fn(sym):
        df = (cached_tech.get("data", {}).get("_kline") if cached_tech else None)
        if df is None:
            df = fetch_kline(sym, ktype="1d", num=60)
        return {"patterns": get_latest_patterns(df, n_patterns=10)}

    def _enhanced_fn(sym):
        df = (cached_tech.get("data", {}).get("_kline") if cached_tech else None)
        if df is None:
            df = fetch_kline(sym, ktype="1d", num=60)
        return {"result": enhanced_signal_score(df)}

    def _earnings_fn(sym):
        return {"result": get_earnings_summary(sym)}

    def _decision_fn(sym):
        """Reuse everything already computed above — no extra futu API calls."""
        return {"result": compute_decision_fast(
            sym,
            smart_money_data=smart_money_data,
            tech_data=results.get("tech"),
            enhanced_data=results.get("enhanced"),
            candle_data=results.get("candlestick"),
            earnings_data=results.get("earnings"),
            regime_data=results.get("regime"),
            price_data=results.get("price") if results.get("price") else cached_price,
            timeframe=timeframe,
        )}

    tasks = [
        ("price", lambda: cached_price if cached_price else get_price(symbol)),
        ("tech", lambda: cached_tech if cached_tech else get_tech_analysis(symbol, timeframe)),
        ("news", lambda: _news_fn(symbol)),
        ("options", lambda: _options_fn(symbol)),
        ("candlestick", lambda: _candlestick_fn(symbol)),
        ("enhanced", lambda: _enhanced_fn(symbol)),
        ("earnings", lambda: _earnings_fn(symbol)),
        # regime must run BEFORE decision so it can be reused
        ("regime", get_regime),
        ("decision", lambda: _decision_fn(symbol)),
    ]
    # Sequential execution to avoid shared futu context thread-safety issues
    for name, fn in tasks:
        _run(name, fn)
    for k, v in results.items(): report["modules"][k] = v
    for k, v in errors.items(): report["modules"][k] = {"status": "error", "error": v}

    parts = []
    if "tech" in results:
        d = results["tech"].get("data", {})
        parts.append("tech:" + d.get("rating","?") + "(" + str(d.get("score",0)) + ")")
    if "enhanced" in results:
        r = results["enhanced"].get("result", {})
        parts.append("enh:" + r.get("rating","?") + "(" + str(r.get("score",0)) + ")")
    if "candlestick" in results:
        p = results["candlestick"].get("patterns", [])
        bull = sum(1 for x in p if x.get("direction") == "bullish")
        bear = sum(1 for x in p if x.get("direction") == "bearish")
        parts.append("candle:" + str(bull) + "B/" + str(bear) + "S")
    if "decision" in results:
        d = results["decision"].get("result", {}).get("decision", {})
        parts.append("dec:" + d.get("action","?") + "(s=" + str(d.get("composite_score",0)) + ")")
    if "earnings" in results:
        parts.append("earn:" + results["earnings"].get("result",{}).get("status","?"))
    if "regime" in results:
        parts.append("regime:" + results["regime"].get("regime","?"))

    report["summary"] = {"parts": parts, "raw": " | ".join(parts)}
    report["elapsed_sec"] = round(time.time() - t0, 1)
    report["errors"] = errors if errors else None
    return report


def run_analysis_parallel(symbols, max_workers=5, smart_money_data=None, price_map=None, tech_cache=None):
    results = {}
    errors = {}
    def _worker(sym):
        try:
            results[sym] = run_full_analysis(sym, timeframe="1d",
                                             smart_money_data=smart_money_data,
                                             price_map=price_map, tech_cache=tech_cache)
        except Exception as e:
            errors[sym] = str(e)
    # Sequential execution for thread safety with shared futu context
    for sym in symbols:
        _worker(sym)
    return results, errors


def format_table(candidates, analysis_results, errors):
    lines = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines.append("")
    lines.append("=" * 90)
    lines.append("  ONE-CLICK AUTO SELECTOR  |  " + now)
    lines.append("  Smart Money + Hot List  |  " + str(len(candidates)) + " candidates  |  Analyzed top " + str(len(analysis_results)))
    lines.append("=" * 90)
    lines.append("")
    hdr = "  " + "{:>3}  {:<10}  {:>8}  {:>7}  {:>6}  {:>5}  {:>8}  {:>9}  {}".format(
        "#", "Symbol", "Price", "Chg%", "Smart", "Hot", "Tech", "Composite", "Action")
    lines.append(hdr)
    lines.append("  " + "-" * 80)

    for i, c in enumerate(candidates):
        sym = c["symbol"]
        price = c.get("price", 0)
        chg = c.get("change_pct", 0)
        smart = c.get("smart_score", 0)
        hot = c.get("hot_score_norm", 0)
        tech = c.get("tech_rating", "")
        composite = c.get("composite", 0)
        action = "-"
        if sym in analysis_results:
            res = analysis_results[sym]
            dec = res.get("modules", {}).get("decision", {}).get("result", {}).get("decision", {})
            action = dec.get("action", "-")
            if action == "-":
                tech_r = res.get("modules", {}).get("tech", {}).get("data", {}).get("rating", "")
                score = res.get("modules", {}).get("tech", {}).get("data", {}).get("score", 0)
                if tech_r in ("Overweight", "Buy", "Strong Buy") and score >= 60:
                    action = "BUY"
                elif tech_r in ("Underweight", "Sell", "Strong Sell"):
                    action = "SELL"
                else:
                    action = "HOLD"
        elif sym in errors:
            action = "ERR"
        price_str = "${:.2f}".format(price) if price > 0 else "-"
        chg_str = "{:+.2f}%".format(chg) if chg != 0 else "0.00%"
        line = "  " + "{:>3}  {:<10}  {:>8}  {:>7}  {:>6}  {:>5.0f}  {:>8}  {:>9.1f}  {}".format(
            i + 1, sym, price_str, chg_str, smart, hot, tech, composite, action)
        lines.append(line)

    lines.append("")
    if analysis_results:
        lines.append("-" * 90)
        lines.append("  DETAILED ANALYSIS (Top Picks)")
        lines.append("-" * 90)
        for i, c in enumerate(candidates[:len(analysis_results)]):
            sym = c["symbol"]
            if sym not in analysis_results: continue
            res = analysis_results[sym]
            summary = res.get("summary", {})
            raw = summary.get("raw", "")
            price_mod = res.get("modules", {}).get("price") or {}
            tech_mod = res.get("modules", {}).get("tech") or {}
            tp = tech_mod.get("data", {}).get("trade_plan", {})
            current_price = price_mod.get("latest_price", 0)
            # Fallback to decision module price if price module is null
            if current_price == 0:
                dec_mod = res.get("modules", {}).get("decision", {}).get("result", {}).get("decision", {})
                current_price = dec_mod.get("current_price", 0)
            entry = tp.get("entry_zone", 0)
            stop = tp.get("stop_loss", 0)
            target = tp.get("target_1", 0)
            rr = tp.get("risk_reward", 0)
            lines.append("  #{} {}  Price=${:.2f}".format(i + 1, sym, current_price))
            lines.append("      " + raw)
            if entry > 0:
                lines.append("      Entry=${:.2f}  Stop=${:.2f}  Target1=${:.2f}  RR={:.1f}:1".format(entry, stop, target, rr))
            lines.append("")
        lines.append("-" * 90)

    if errors:
        lines.append("")
        lines.append("  ERRORS:")
        for sym, err in errors.items():
            lines.append("    " + sym + ": " + err)

    lines.append("")
    lines.append("=" * 90)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Auto Selector - One-Click Stock Selection + Full Analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python auto_selector.py                    # top 5, min_score=15
  python auto_selector.py --top 10 --min 20
  python auto_selector.py --json
  python auto_selector.py --verbose --top 8
"""
    )
    parser.add_argument("--top", type=int, default=5, help="Number of candidates to analyze (default: 5)")
    parser.add_argument("--scan-top", type=int, default=30, help="How many to scan from each source (default: 30)")
    parser.add_argument("--min", type=int, default=15, dest="min_score", help="Min smart money score (default: 15)")
    parser.add_argument("--json", action="store_true", help="Raw JSON output")
    parser.add_argument("--verbose", action="store_true", help="Show detailed output")
    args = parser.parse_args()

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    print("Auto Selector v1.0  |  " + now_str, file=sys.stderr)

    if not _futu_available():
        print("ERROR: Futu OpenD not available on port 11111", file=sys.stderr)
        sys.exit(1)

    print("Phase 1: Scanning smart money + hot list...", file=sys.stderr)
    t0 = time.time()
    smart_result = {"status": "error", "count": 0, "data": []}
    hot_result = {"status": "error", "count": 0, "data": []}

    def _scan_smart():
        smart_result.update(scan_smart(top_n=args.scan_top, min_score=args.min_score))

    def _scan_hot():
        hot_result.update(scan_hot(top_n=args.scan_top))

    t1 = threading.Thread(target=_scan_smart)
    t2 = threading.Thread(target=_scan_hot)
    t1.start()
    t2.start()
    t1.join(timeout=60)
    t2.join(timeout=60)
    scan_time = round(time.time() - t0, 1)
    print("  Scan done in {}s  (smart={}  hot={})".format(scan_time, smart_result["count"], hot_result["count"]), file=sys.stderr)

    # Brief pause after heavy scan to let futu context stabilize
    time.sleep(5)
    print("Phase 2: Merging and ranking candidates...", file=sys.stderr)
    candidates = merge_and_rank(smart_result, hot_result, top_n=args.top)
    print("  {} candidates ranked".format(len(candidates)), file=sys.stderr)
    if not candidates:
        print("No candidates found. Try lowering --min score.", file=sys.stderr)
        sys.exit(0)

    print("Phase 3: Running full analysis on top {} picks...".format(len(candidates)), file=sys.stderr)
    t0 = time.time()
    all_smart = smart_result.get("data", [])
    # Build price map and tech cache from smart money data to avoid futu API degeneration after scan
    price_map = {}
    tech_cache = {}
    for item in all_smart:
        sym = item.get("symbol", "")
        pr = item.get("price") or {}
        if pr:
            price_map[sym] = pr
        tc = item.get("tech") or {}
        if tc and tc.get("status") == "ok":
            tech_cache[sym] = tc
    analysis_results, errors = run_analysis_parallel(
        [c["symbol"] for c in candidates],
        max_workers=min(len(candidates), 5),
        smart_money_data=all_smart,
        price_map=price_map,
        tech_cache=tech_cache
    )
    analyze_time = round(time.time() - t0, 1)
    print("  Analysis done in {}s  ({} ok, {} errors)".format(analyze_time, len(analysis_results), len(errors)), file=sys.stderr)

    if args.json:
        output = {
            "generated_at": datetime.now().isoformat(),
            "scan_time_sec": scan_time,
            "analysis_time_sec": analyze_time,
            "total_time_sec": round(scan_time + analyze_time, 1),
            "candidates": candidates,
            "analysis": analysis_results,
            "errors": errors,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    else:
        table = format_table(candidates, analysis_results, errors)
        print(table)

    buy_count = 0
    sell_count = 0
    for c in candidates:
        sym = c["symbol"]
        if sym in analysis_results:
            dec = analysis_results[sym].get("modules", {}).get("decision", {}).get("result", {}).get("decision", {})
            a = dec.get("action", "")
            if a == "BUY": buy_count += 1
            elif a == "SELL": sell_count += 1
    total = round(scan_time + analyze_time, 1)
    hold = len(candidates) - buy_count - sell_count
    print("")
    print("  Summary: {} BUY  |  {} SELL  |  {} HOLD/NEUTRAL  |  Total time: {}s".format(
        buy_count, sell_count, hold, total), file=sys.stderr)


if __name__ == "__main__":
    main()
