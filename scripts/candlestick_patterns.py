#!/usr/bin/env python3
"""Candlestick Pattern Recognition - 9 common patterns"""
import numpy as np
import pandas as pd
from datetime import datetime
from typing import List, Dict, Optional


def calc_candlestick(df: pd.DataFrame) -> List[Dict]:
    """Detect candlestick patterns from OHLC dataframe.
    
    Returns list of detected patterns with type, confidence, and bar index.
    """
    if df is None or len(df) < 3:
        return []
    
    close = df["close"].values
    open_ = df["open"].values
    high = df["high"].values
    low = df["low"].values
    body = close - open_
    body_abs = np.abs(body)
    upper_wick = high - np.maximum(close, open_)
    lower_wick = np.minimum(close, open_) - low
    range_ = high - low
    range_safe = np.where(range_ > 0, range_, 1)
    
    patterns = []
    n = len(close)
    
    for i in range(2, n):
        # Doji: small body relative to range
        if body_abs[i] / range_safe[i] < 0.1:
            patterns.append({
                "bar": i, "time": str(df.iloc[i].get("time_key", ""))[:10],
                "type": "doji", "direction": "neutral", "confidence": 70,
                "body_pct": round(body_abs[i] / range_safe[i] * 100, 1),
            })
        
        # Hammer: small body, long lower wick (>= 2x body), small upper wick
        if lower_wick[i] / max(body_abs[i], 0.001) >= 2.0 and upper_wick[i] / max(body_abs[i], 0.001) <= 0.5:
            patterns.append({
                "bar": i, "time": str(df.iloc[i].get("time_key", ""))[:10],
                "type": "hammer", "direction": "bullish", "confidence": 75,
                "lower_wick_pct": round(lower_wick[i] / range_safe[i] * 100, 1),
            })
        
        # Inverted Hammer: small body, long upper wick
        if upper_wick[i] / max(body_abs[i], 0.001) >= 2.0 and lower_wick[i] / max(body_abs[i], 0.001) <= 0.5:
            patterns.append({
                "bar": i, "time": str(df.iloc[i].get("time_key", ""))[:10],
                "type": "inverted_hammer", "direction": "bullish", "confidence": 65,
                "upper_wick_pct": round(upper_wick[i] / range_safe[i] * 100, 1),
            })
        
        # Shooting Star: opposite of hammer at top
        if i >= 3 and close[i-1] > open_[i-1] and upper_wick[i] / max(body_abs[i], 0.001) >= 2.0:
            patterns.append({
                "bar": i, "time": str(df.iloc[i].get("time_key", ""))[:10],
                "type": "shooting_star", "direction": "bearish", "confidence": 70,
            })
        
        # Bullish Engulfing
        if i >= 1:
            prev_body = body[i-1]
            curr_body = body[i]
            if prev_body < 0 and curr_body > 0:
                if curr_body >= abs(prev_body) * 1.5:
                    patterns.append({
                        "bar": i, "time": str(df.iloc[i].get("time_key", ""))[:10],
                        "type": "bullish_engulfing", "direction": "bullish", "confidence": 80,
                    })
            
            # Bearish Engulfing
            if prev_body > 0 and curr_body < 0:
                if abs(curr_body) >= abs(prev_body) * 1.5:
                    patterns.append({
                        "bar": i, "time": str(df.iloc[i].get("time_key", ""))[:10],
                        "type": "bearish_engulfing", "direction": "bearish", "confidence": 80,
                    })
        
        # Morning Star (3-bar bullish reversal)
        if i >= 3:
            if body[i-2] < -abs(body[i-2]) * 0.9 and abs(body[i-1]) / range_safe[i-1] < 0.1 and body[i] > 0:
                patterns.append({
                    "bar": i, "time": str(df.iloc[i].get("time_key", ""))[:10],
                    "type": "morning_star", "direction": "bullish", "confidence": 85,
                })
        
        # Evening Star (3-bar bearish reversal)
        if i >= 3:
            if body[i-2] > abs(body[i-2]) * 0.9 and abs(body[i-1]) / range_safe[i-1] < 0.1 and body[i] < 0:
                patterns.append({
                    "bar": i, "time": str(df.iloc[i].get("time_key", ""))[:10],
                    "type": "evening_star", "direction": "bearish", "confidence": 85,
                })
        
        # Three White Soldiers
        if i >= 4 and body[i] > 0 and body[i-1] > 0 and body[i-2] > 0:
            if close[i] > close[i-1] > close[i-2]:
                patterns.append({
                    "bar": i, "time": str(df.iloc[i].get("time_key", ""))[:10],
                    "type": "three_white_soldiers", "direction": "bullish", "confidence": 82,
                })
        
        # Three Black Crows
        if i >= 4 and body[i] < 0 and body[i-1] < 0 and body[i-2] < 0:
            if close[i] < close[i-1] < close[i-2]:
                patterns.append({
                    "bar": i, "time": str(df.iloc[i].get("time_key", ""))[:10],
                    "type": "three_black_crows", "direction": "bearish", "confidence": 82,
                })
    
    return patterns


def get_latest_patterns(df: pd.DataFrame, n_patterns=5) -> List[Dict]:
    """Get the most recent N patterns."""
    all_patterns = calc_candlestick(df)
    if not all_patterns:
        return []
    # Sort by bar descending, take last n
    sorted_patterns = sorted(all_patterns, key=lambda x: x["bar"], reverse=True)
    return sorted_patterns[:n_patterns]


def pattern_score(patterns: List[Dict]) -> Dict:
    """Score based on recent patterns."""
    if not patterns:
        return {"score": 50, "signal": "neutral", "count": 0}
    
    bullish = sum(1 for p in patterns if p["direction"] == "bullish")
    bearish = sum(1 for p in patterns if p["direction"] == "bearish")
    total = len(patterns)
    
    score = 50 + (bullish - bearish) * 10
    score = max(0, min(100, score))
    
    if score >= 65:
        signal = "bullish"
    elif score <= 35:
        signal = "bearish"
    else:
        signal = "neutral"
    
    return {"score": score, "signal": signal, "count": total,
            "bullish": bullish, "bearish": bearish}


def main():
    import argparse, json, sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from tech_engine import fetch_kline
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--bars", type=int, default=60)
    parser.add_argument("--top", type=int, default=5)
    args = parser.parse_args()
    
    df = fetch_kline(args.symbol, "1d", args.bars)
    if df is None:
        print(json.dumps({"error": "No data"}, indent=2))
        sys.exit(1)
    
    patterns = get_latest_patterns(df, args.top)
    pscore = pattern_score(patterns)
    
    result = {
        "symbol": args.symbol,
        "generated_at": datetime.now().isoformat(),
        "pattern_score": pscore,
        "patterns": patterns,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
