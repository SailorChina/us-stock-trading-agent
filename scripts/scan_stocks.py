#!/usr/bin/env python3
"""US Stock Scanner - with timeout protection, cache, and Yahoo Finance fallback"""
import argparse, json, sys, time, urllib.request, os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cache_util import get_cached

from tech_engine import scan_premarket, scan_hot_list, get_price

DEFAULT_TIMEOUT_SCAN = 300
DEFAULT_TIMEOUT_SECTOR = 120
DEFAULT_TIMEOUT_MEME = 60
DEFAULT_TIMEOUT_PREMARKET = 30

_YAHOO_SECTOR = {
    "IBB": "Biotechnology", "XOP": "Oil and Gas E and P", "XBI": "Biotech SPDR",
    "ARKK": "Innovation", "XLE": "Energy", "XLK": "Technology", "VGT": "Technology",
    "SMH": "Semiconductors", "SOXX": "Semiconductors", "XLF": "Financial",
    "VHT": "Healthcare", "XLV": "Healthcare", "XME": "Materials",
    "XLY": "Consumer Discretionary", "XLP": "Consumer Staples",
    "XLU": "Utilities", "XLI": "Industrial",
}

def _yahoo_get(symbol, period="5d"):
    url = "https://query1.finance.yahoo.com/v8/finance/chart/" + symbol + "?interval=1d&period=" + period
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        data = retry_call(lambda: (lambda: json.loads(urllib.request.urlopen(req, timeout=8)).read()))()
        r = data.get("chart", {}).get("result")
        if r and r[0]["indicators"]["quote"][0]["close"]:
            closes = r[0]["indicators"]["quote"][0]["close"]
            vc = [c for c in closes if c is not None]
            if vc:
                return {"close": vc[-1], "prev_close": vc[-2] if len(vc) > 1 else vc[-1]}
    except Exception:
        pass
    return None

def yahoo_sector_ranking(top=10):
    """Fast Yahoo Finance fallback for sector ETF ranking."""
    tickers = list(_YAHOO_SECTOR.keys())
    results = {}
    for sym in tickers:
        q = _yahoo_get(sym, period="10d")
        if q and q["prev_close"] and q["prev_close"] != 0:
            chg_1d = (q["close"] - q["prev_close"]) / q["prev_close"] * 100
            results[sym] = {
                "ticker": sym,
                "en_name": _YAHOO_SECTOR.get(sym, sym),
                "price": round(q["close"], 2),
                "chg_1d": round(chg_1d, 2),
                "chg_5d": 0.0, "chg_20d": 0.0, "chg_60d": 0.0,
                "heat_score": round(chg_1d + 5, 1),
            }
        time.sleep(0.3)
    sorted_items = sorted(results.values(), key=lambda x: x["chg_1d"], reverse=True)
    top_results = sorted_items[:top]
    if not top_results and results:
        return [{"ticker": k, "price": v["price"], "chg_1d": v["chg_1d"],
                 "chg_5d": 0.0, "note": "weekend_data"} for k,v in list(results.items())[:top]]
    return top_results

def _fetch_sector_sina():
    ranks = get_sector_ranking()
    items = []
    for r in ranks:
        items.append({
            "ticker": getattr(r, "ticker", ""),
            "en_name": getattr(r, "en_name", ""),
            "cn_name": getattr(r, "cn_name", ""),
            "price": float(getattr(r, "price", 0) or 0),
            "chg_1d": float(getattr(r, "chg_1d", 0) or 0),
            "chg_5d": float(getattr(r, "chg_5d", 0) or 0),
            "chg_20d": float(getattr(r, "chg_20d", 0) or 0),
            "chg_60d": float(getattr(r, "chg_60d", 0) or 0),
            "heat_score": float(getattr(r, "heat_score", 0) or 0),
        })
    return items

def run_sector(top=10, timeout=DEFAULT_TIMEOUT_SECTOR):
    t0 = time.time()
    try:
        items, cached = get_cached("sectors_us", _fetch_sector_sina, ttl_minutes=30)
        elapsed = time.time() - t0
        if items:
            return {"status": "ok", "source": "sina" + ("_cache" if cached else ""),
                    "elapsed_sec": round(elapsed, 1), "data": items[:top]}
    except Exception:
        pass
    try:
        items = yahoo_sector_ranking(top)
        elapsed = time.time() - t0
        return {"status": "ok", "source": "yahoo", "elapsed_sec": round(elapsed, 1), "data": items}
    except Exception as e:
        elapsed = time.time() - t0
        return {"status": "error", "elapsed_sec": round(elapsed, 1), "error": str(e)}

def run_scan(min_score=55, max_picks=10, timeout=DEFAULT_TIMEOUT_SCAN):
    t0 = time.time()
    config = ScanConfig(min_score=float(min_score), max_per_market=max_picks)
    try:
        result = scan_parallel(config=config, output_json=True)
        elapsed = time.time() - t0
        status = "timeout" if elapsed > timeout else "ok"
        return {"status": status, "elapsed_sec": round(elapsed, 1), "data": result}
    except Exception as e:
        elapsed = time.time() - t0
        return {"status": "error", "elapsed_sec": round(elapsed, 1), "error": str(e)}

def run_meme_scan(timeout=DEFAULT_TIMEOUT_MEME):
    t0 = time.time()
    try:
        stocks = get_meme_stocks()
        if not stocks:
            return {"status": "ok", "elapsed_sec": 0, "data": [], "note": "meme watchlist is empty"}
        ranks = get_sector_ranking()
        results = []
        for s in stocks:
            try:
                df = fetch_kline(s.code, "1d", 300)
                if df is None or df.empty or len(df) < 60:
                    results.append({"code": s.code, "status": "data_insufficient"})
                    continue
                rating = compute_rating(df)
                sector_bonus = get_sector_bonus(s.code, ranks)
                meme_bonus = get_meme_bonus(s.code)
                final_score = rating["score"] * sector_bonus * meme_bonus
                results.append({
                    "code": s.code, "rating": rating["rating"],
                    "score": round(final_score, 1),
                    "meme_bonus": round(meme_bonus, 2), "sector_bonus": round(sector_bonus, 2),
                })
            except Exception as e:
                results.append({"code": getattr(s, "code", str(s)), "error": str(e)})
        elapsed = time.time() - t0
        status = "timeout" if elapsed > timeout else "ok"
        return {"status": status, "elapsed_sec": round(elapsed, 1), "data": results}
    except Exception as e:
        elapsed = time.time() - t0
        return {"status": "error", "elapsed_sec": round(elapsed, 1), "error": str(e)}

def main():
    p = argparse.ArgumentParser(description="US Stock Scanner")
    p.add_argument("--mode", default="scan", choices=["scan", "sector", "meme-scan", "premarket"])
    p.add_argument("--min-score", type=int, default=55)
    p.add_argument("--max-picks", type=int, default=10)
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--timeout", type=int, default=None)
    p.add_argument("--output", default=None)
    a = p.parse_args()
    timeout = a.timeout or (DEFAULT_TIMEOUT_SCAN if a.mode=="scan" else DEFAULT_TIMEOUT_SECTOR if a.mode=="sector" else DEFAULT_TIMEOUT_PREMARKET if a.mode=="premarket" else DEFAULT_TIMEOUT_MEME)
    r = {"generated_at": datetime.now().isoformat(), "mode": a.mode, "timeout_sec": timeout}
    t_start = time.time()
    if a.mode == "scan":
        r["scan"] = run_scan(a.min_score, a.max_picks, timeout)
    elif a.mode == "sector":
        r["sector"] = run_sector(a.top, timeout)
    elif a.mode == "meme-scan":
        r["meme"] = run_meme_scan(timeout) if LIB_OK else {"status": "error", "error": "library unavailable"}
    elif a.mode == "premarket":
        r["premarket"] = scan_premarket(top=a.top)
    r["total_elapsed_sec"] = round(time.time() - t_start, 1)
    out = json.dumps(r, ensure_ascii=False, indent=2, default=str)
    if a.output:
        with open(a.output, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"Saved: {a.output}", file=sys.stderr)
    else:
        print(out)

if __name__ == "__main__":
    main()
