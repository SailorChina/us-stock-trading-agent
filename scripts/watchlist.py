#!/usr/bin/env python3
"""Watchlist management - persistent stock watchlist with notes"""
import json, sys, argparse, os
from datetime import datetime

WATCHLIST_PATH = os.path.expanduser("~/.us_stock_watchlist.json")

def load_watchlist():
    if os.path.exists(WATCHLIST_PATH):
        with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"watchlist": [], "notes": {}, "created_at": datetime.now().isoformat()}

def save_watchlist(wl):
    with open(WATCHLIST_PATH, "w", encoding="utf-8") as f:
        json.dump(wl, f, ensure_ascii=False, indent=2)

def add_stock(symbol, note="", sector="", priority="medium"):
    wl = load_watchlist()
    # Check if already exists
    for s in wl["watchlist"]:
        if s["symbol"] == symbol:
            s["note"] = note or s.get("note", "")
            s["sector"] = sector or s.get("sector", "")
            s["priority"] = priority or s.get("priority", "medium")
            s["updated_at"] = datetime.now().isoformat()
            save_watchlist(wl)
            return {"status": "updated", "symbol": symbol}
    wl["watchlist"].append({
        "symbol": symbol, "note": note, "sector": sector,
        "priority": priority, "added_at": datetime.now().isoformat()
    })
    save_watchlist(wl)
    return {"status": "added", "symbol": symbol}

def remove_stock(symbol):
    wl = load_watchlist()
    wl["watchlist"] = [s for s in wl["watchlist"] if s["symbol"] != symbol]
    save_watchlist(wl)
    return {"status": "removed", "symbol": symbol}

def list_stocks():
    wl = load_watchlist()
    return wl

def main():
    parser = argparse.ArgumentParser(description="Watchlist Manager")
    parser.add_argument("--action", default="list", choices=["list", "add", "remove", "analyze"])
    parser.add_argument("--symbol")
    parser.add_argument("--note")
    parser.add_argument("--sector")
    parser.add_argument("--priority", default="medium")
    args = parser.parse_args()
    
    if args.action == "list":
        print(json.dumps(load_watchlist(), ensure_ascii=False, indent=2))
    elif args.action == "add":
        if not args.symbol:
            print("需要 --symbol", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(add_stock(args.symbol, args.note, args.sector, args.priority), ensure_ascii=False, indent=2))
    elif args.action == "remove":
        if not args.symbol:
            print("需要 --symbol", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(remove_stock(args.symbol), ensure_ascii=False, indent=2))
    elif args.action == "analyze":
        wl = load_watchlist()
        results = {}
        for item in wl["watchlist"]:
            sym = item["symbol"]
            results[sym] = {"note": item.get("note", ""), "sector": item.get("sector", ""), "priority": item.get("priority", "")}
        print(json.dumps({"watchlist_count": len(wl["watchlist"]), "stocks": results}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
