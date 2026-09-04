#!/usr/bin/env python3
"""Trade journal — persistent log of trades and analysis results"""
import json, sys, argparse, os
from datetime import datetime

JOURNAL_PATH = os.path.expanduser("~/.us_stock_trade_journal.jsonl")

def add_trade(action, symbol, shares, price, stop_loss=None, target_1=None, target_2=None, reason="", note=""):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action, "symbol": symbol, "shares": shares,
        "price": price, "stop_loss": stop_loss, "target_1": target_1, "target_2": target_2,
        "reason": reason, "note": note,
    }
    with open(JOURNAL_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry

def add_analysis(symbol, analysis_result):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": "analysis",
        "symbol": symbol,
        "result": analysis_result,
    }
    with open(JOURNAL_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry

def list_trades(limit=20, symbol=None):
    if not os.path.exists(JOURNAL_PATH):
        return {"trades": [], "count": 0}
    trades = []
    with open(JOURNAL_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if entry.get("type") == "analysis":
                continue
            if symbol and entry.get("symbol") != symbol:
                continue
            trades.append(entry)
    trades = trades[-limit:]
    return {"trades": trades, "count": len(trades)}

def list_analyses(limit=20, symbol=None):
    if not os.path.exists(JOURNAL_PATH):
        return {"analyses": [], "count": 0}
    analyses = []
    with open(JOURNAL_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if entry.get("type") != "analysis":
                continue
            if symbol and entry.get("symbol") != symbol:
                continue
            analyses.append(entry)
    analyses = analyses[-limit:]
    return {"analyses": analyses, "count": len(analyses)}

def main():
    p = argparse.ArgumentParser(description="Trade Journal")
    p.add_argument("--action", default="list", choices=["add", "analyze", "list", "history"])
    p.add_argument("--symbol")
    p.add_argument("--shares", type=int)
    p.add_argument("--price", type=float)
    p.add_argument("--stop-loss", type=float)
    p.add_argument("--target-1", type=float)
    p.add_argument("--target-2", type=float)
    p.add_argument("--reason")
    p.add_argument("--note")
    p.add_argument("--analysis-file")
    p.add_argument("--limit", type=int, default=20)
    a = p.parse_args()

    if a.action == "add":
        if not a.symbol or not a.shares or not a.price:
            print("需要 --symbol --shares --price", file=sys.stderr)
            sys.exit(1)
        entry = add_trade("BUY", a.symbol, a.shares, a.price, a.stop_loss, a.target_1, a.target_2, a.reason, a.note)
        print(json.dumps(entry, ensure_ascii=False, indent=2))
    elif a.action == "analyze":
        if not a.analysis_file:
            print("需要 --analysis-file", file=sys.stderr)
            sys.exit(1)
        with open(a.analysis_file, encoding="utf-8") as f:
            result = json.load(f)
        entry = add_analysis(a.symbol or result.get("symbol", ""), result)
        print(json.dumps({"status": "saved", "symbol": entry["symbol"], "timestamp": entry["timestamp"]}, ensure_ascii=False, indent=2))
    elif a.action == "list":
        trades = list_trades(a.limit, a.symbol)
        print(json.dumps(trades, ensure_ascii=False, indent=2))
    elif a.action == "history":
        analyses = list_analyses(a.limit, a.symbol)
        print(json.dumps(analyses, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
