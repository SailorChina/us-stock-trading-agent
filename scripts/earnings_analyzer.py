#!/usr/bin/env python3
"""Earnings & Analyst Data - Yahoo Finance fallback for US stocks"""
import json, sys, os, time, urllib.request
from datetime import datetime
from typing import Dict, Optional

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
from cache_util import retry_call

_YAHOO_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _yahoo_get(symbol: str, field: str, period: str = "max") -> Optional[dict]:
    """Fetch a single field from Yahoo Finance chart API."""
    ysym = symbol.replace("US.", "")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ysym}?interval=1d&period={period}"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": _YAHOO_UA, "Accept": "application/json"
        })
        data = json.loads(urllib.request.urlopen(req, timeout=8).read())
        result = data.get("chart", {}).get("result")
        if result:
            return result[0]
    except Exception:
        pass
    return None


def get_earnings_summary(symbol: str) -> Dict:
    """Get earnings-related data from Yahoo Finance."""
    ysym = symbol.replace("US.", "")
    result = {"symbol": symbol, "generated_at": datetime.now().isoformat()}
    
    # Fetch quote info
    url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ysym}?modules=defaultSequenceQueue,price,financialData"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": _YAHOO_UA, "Accept": "application/json"
        })
        data = json.loads(urllib.request.urlopen(req, timeout=8).read())
        queue = data.get("quoteSummary", {}).get("result", [{}])[0]
        
        price_info = queue.get("price", {})
        fin_data = queue.get("financialData", {})
        
        result["price"] = {
            "current": price_info.get("regularMarketPrice", {}).get("fmt"),
            "prev_close": price_info.get("regularMarketPreviousClose", {}).get("fmt"),
            "market_cap": price_info.get("marketCap", {}).get("fmt"),
        }
        
        result["financials"] = {
            "pe_ratio": fin_data.get("trailingPE", {}).get("raw"),
            "forward_pe": fin_data.get("forwardPE", {}).get("raw"),
            "pb_ratio": fin_data.get("priceToBook", {}).get("raw"),
            "eps_trailing": fin_data.get("trailingEps", {}).get("raw"),
            "eps_forward": fin_data.get("forwardEps", {}).get("raw"),
            "dividend_yield": fin_data.get("dividendYield", {}).get("raw"),
            "profit_margin": fin_data.get("profitMargins", {}).get("raw"),
            "revenue_growth": fin_data.get("revenueGrowth", {}).get("raw"),
            "analyst_target": fin_data.get("targetMeanPrice", {}).get("raw"),
            "analyst_rating": fin_data.get("recommendationKey", {}),
            "recommendation": fin_data.get("recommendationKey", {}).get("raw"),
        }
        
        # Earnings history
        earnings = fin_data.get("earningsTimestamp", {})
        result["earnings"] = {
            "next_earnings": datetime.fromtimestamp(earnings.get("raw", 0)).isoformat() if earnings.get("raw") else None,
            "last_earnings": datetime.fromtimestamp(earnings.get("fmt", 0)).isoformat() if earnings.get("fmt") else None,
        }
        
        result["source"] = "yahoo"
        result["status"] = "ok"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    
    return result


def get_analyst_targets(symbol: str) -> Dict:
    """Get analyst price targets and ratings."""
    result = {"symbol": symbol, "generated_at": datetime.now().isoformat()}
    
    ysym = symbol.replace("US.", "")
    url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ysym}?modules=defaultSequenceQueue,price,financialData"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": _YAHOO_UA, "Accept": "application/json"
        })
        data = json.loads(urllib.request.urlopen(req, timeout=8).read())
        queue = data.get("quoteSummary", {}).get("result", [{}])[0]
        fin_data = queue.get("financialData", {})
        
        result["targets"] = {
            "mean": fin_data.get("targetMeanPrice", {}).get("raw"),
            "high": fin_data.get("targetHighPrice", {}).get("raw"),
            "low": fin_data.get("targetLowPrice", {}).get("raw"),
            "median": fin_data.get("targetMedianPrice", {}).get("raw"),
            "num_analysts": fin_data.get("numberOfAnalystOpinions", {}).get("raw"),
        }
        result["rating"] = {
            "recommendation": fin_data.get("recommendationKey", {}).get("raw"),
            "rating_num": fin_data.get("recommendationMean", {}).get("raw"),
        }
        result["upside"] = None
        current = fin_data.get("regularMarketPrice", {}).get("raw")
        mean = fin_data.get("targetMeanPrice", {}).get("raw")
        if current and mean and current > 0:
            result["upside"] = round((mean - current) / current * 100, 1)
        
        result["source"] = "yahoo"
        result["status"] = "ok"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    
    return result


def earnings_score(earnings_data: Dict, symbol: str = "") -> Dict:
    """Score a stock based on earnings data."""
    if earnings_data.get("status") != "ok":
        return {"score": 50, "signal": "unknown", "note": "no earnings data"}
    
    fin = earnings_data.get("financials", {})
    score = 50
    reasons = []
    
    # PE ratio
    pe = fin.get("pe_ratio")
    if pe:
        if pe < 15:
            score += 8; reasons.append(f"PE {pe:.1f} cheap")
        elif pe < 25:
            score += 3; reasons.append(f"PE {pe:.1f} reasonable")
        elif pe > 50:
            score -= 8; reasons.append(f"PE {pe:.1f} expensive")
    
    # Forward PE vs Trailing PE
    fpe = fin.get("forward_pe")
    tpe = fin.get("pe_ratio")
    if fpe and tpe and tpe > 0:
        if fpe < tpe * 0.8:
            score += 10; reasons.append("Forward PE << Trailing (growth expected)")
        elif fpe > tpe:
            score -= 5; reasons.append("Forward PE > Trailing (growth slowing)")
    
    # EPS growth
    eps_trail = fin.get("eps_trailing")
    eps_fwd = fin.get("eps_forward")
    if eps_trail and eps_fwd and eps_trail > 0:
        growth = (eps_fwd - eps_trail) / eps_trail * 100
        if growth > 20:
            score += 10; reasons.append(f"EPS growth +{growth:.0f}%")
        elif growth < -10:
            score -= 8; reasons.append(f"EPS decline {growth:.0f}%")
    
    # Profit margin
    pm = fin.get("profit_margin")
    if pm:
        if pm > 0.20:
            score += 5; reasons.append(f"Profit margin {pm*100:.0f}%")
        elif pm < 0:
            score -= 10; reasons.append(f"Negative margin {pm*100:.0f}%")
    
    # Revenue growth
    rg = fin.get("revenue_growth")
    if rg:
        if rg > 0.15:
            score += 8; reasons.append(f"Rev growth +{rg*100:.0f}%")
        elif rg < -0.05:
            score -= 5; reasons.append(f"Rev decline {rg*100:.0f}%")
    
    # Analyst recommendation
    rec = fin.get("recommendation")
    if rec:
        if rec in ("strong_buy", "buy"):
            score += 10; reasons.append(f"Analyst: {rec}")
        elif rec in ("sell", "strong_sell"):
            score -= 10; reasons.append(f"Analyst: {rec}")
    
    # Upside to target
    upside = None
    try:
        ups = earnings_data.get("upside")
        if ups is not None:
            if ups > 15:
                score += 8; reasons.append(f"Upside {ups:+.1f}%")
            elif ups < -10:
                score -= 8; reasons.append(f"Downside {ups:+.1f}%")
    except Exception:
        pass
    
    score = max(0, min(100, score))
    if score >= 65:
        signal = "bullish"
    elif score <= 35:
        signal = "bearish"
    else:
        signal = "neutral"
    
    return {"score": score, "signal": signal, "reasons": reasons, "financials": fin}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--mode", default="all", choices=["earnings", "analysts", "score"])
    args = parser.parse_args()
    
    if args.mode in ("earnings", "all"):
        earnings = get_earnings_summary(args.symbol)
    else:
        earnings = {"status": "skipped"}
    
    if args.mode in ("analysts", "all"):
        analysts = get_analyst_targets(args.symbol)
    else:
        analysts = {"status": "skipped"}
    
    if args.mode in ("score", "all"):
        score = earnings_score(earnings if args.mode == "score" else earnings, args.symbol)
    else:
        score = {"status": "skipped"}
    
    result = {
        "symbol": args.symbol,
        "generated_at": datetime.now().isoformat(),
        "earnings": earnings,
        "analysts": analysts,
        "score": score,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
