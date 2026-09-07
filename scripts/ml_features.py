#!/usr/bin/env python3
"""Feature Engineering for ML prediction - extract features from kline data."""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional


def extract_features(df: pd.DataFrame, lookback: int = 60) -> pd.DataFrame:
    """Extract ML features from OHLCV dataframe.
    
    Returns DataFrame with engineered features, one row per bar.
    Last row is the prediction target row.
    """
    if df is None or len(df) < lookback + 10:
        return None
    
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    open_ = df["open"].values
    volume = df["volume"].values
    
    n = len(close)
    features = []
    
    for i in range(lookback, n):
        window = slice(i - lookback, i)
        fwd = slice(i, min(i + 5, n))  # predict next 5 bars direction
        
        row = {}
        
        # --- Price features ---
        row["close"] = close[i]
        row["open"] = open_[i]
        row["body"] = (close[i] - open_[i]) / max(open_[i], 1e-10)
        row["range"] = (high[i] - low[i]) / max(close[i], 1e-10)
        row["upper_wick"] = (high[i] - max(close[i], open_[i])) / max(close[i], 1e-10)
        row["lower_wick"] = (min(close[i], open_[i]) - low[i]) / max(close[i], 1e-10)
        row["ret_1d"] = (close[i] - close[i-1]) / max(close[i-1], 1e-10)
        row["ret_3d"] = (close[i] - close[i-3]) / max(close[i-3], 1e-10) if i >= 3 else 0.0
        row["ret_5d"] = (close[i] - close[i-5]) / max(close[i-5], 1e-10) if i >= 5 else 0.0
        
        # --- MA features ---
        for p in [5, 10, 20, 50]:
            if i >= p:
                row[f"ma{p}"] = np.mean(close[i-p:i]) / max(close[i], 1e-10)
                row[f"ma{p}_dist"] = (close[i] - row[f"ma{p}"]) / max(close[i], 1e-10)
            else:
                row[f"ma{p}"] = 1.0
                row[f"ma{p}_dist"] = 0.0
        
        # MA alignment
        row["ma_bullish"] = 1.0 if row["ma5"] > row["ma10"] > row["ma20"] else 0.0
        row["ma_trend"] = 1.0 if row["ma5"] > row["ma20"] else 0.0
        
        # --- RSI ---
        if i >= 14:
            delta = close[i-14:i] - close[i-15:i-1]
            gain = np.where(delta > 0, delta, 0).mean()
            loss = np.where(delta <= 0, -delta, 0).mean()
            rs = gain / max(loss, 1e-10)
            row["rsi"] = 100 - (100 / (1 + rs))
        else:
            row["rsi"] = 50.0
        
        # --- MACD ---
        if i >= 26:
            ema12 = pd.Series(close[i-26:i]).ewm(span=12, adjust=False).mean().iloc[-1]
            ema26 = pd.Series(close[i-26:i]).ewm(span=26, adjust=False).mean().iloc[-1]
            dif = ema12 - ema26
            row["macd_dif"] = dif / max(close[i], 1e-10)
            row["macd_hist"] = dif / max(close[i], 1e-10)  # simplified
        else:
            row["macd_dif"] = 0.0
            row["macd_hist"] = 0.0
        
        # --- Bollinger ---
        if i >= 20:
            ma20 = np.mean(close[i-20:i])
            std20 = np.std(close[i-20:i])
            row["boll_pos"] = (close[i] - ma20) / max(std20 * 2, 1e-10)
            row["boll_width"] = std20 * 2 / max(ma20, 1e-10)
        else:
            row["boll_pos"] = 0.0
            row["boll_width"] = 0.0
        
        # --- Volume ---
        if i >= 20:
            vol_avg = np.mean(volume[i-20:i])
            row["vol_ratio"] = volume[i] / max(vol_avg, 1e-10)
        else:
            row["vol_ratio"] = 1.0
        
        # --- ATR ---
        if i >= 14:
            trs = []
            for j in range(i-13, i+1):
                tr = high[j] - low[j]
                if j > 0:
                    tr = max(tr, abs(high[j] - close[j-1]), abs(low[j] - close[j-1]))
                trs.append(tr)
            row["atr"] = np.mean(trs) / max(close[i], 1e-10)
        else:
            row["atr"] = 0.0
        
        # --- Momentum ---
        row["momentum_10"] = (close[i] - close[max(0, i-10)]) / max(close[max(0, i-10)], 1e-10)
        row["momentum_20"] = (close[i] - close[max(0, i-20)]) / max(close[max(0, i-20)], 1e-10)
        
        # --- Volatility ---
        if i >= 10:
            row["volatility"] = np.std(close[i-10:i]) / max(np.mean(close[i-10:i]), 1e-10)
        else:
            row["volatility"] = 0.0
        
        features.append(row)
    
    result = pd.DataFrame(features)
    
    # Target: direction of next 5 bars (1=up, 0=down)
    targets = []
    for i in range(lookback, n):
        future_close = close[i+5] if i+5 < n else close[-1]
        targets.append(1.0 if future_close > close[i] else 0.0)
    result["target"] = targets
    
    return result


def get_feature_columns() -> List[str]:
    """Return list of feature column names (excluding target)."""
    return [c for c in [
        "close", "open", "body", "range", "upper_wick", "lower_wick",
        "ret_1d", "ret_3d", "ret_5d",
        "ma5", "ma10", "ma20", "ma50",
        "ma5_dist", "ma10_dist", "ma20_dist", "ma50_dist",
        "ma_bullish", "ma_trend",
        "rsi", "macd_dif", "macd_hist",
        "boll_pos", "boll_width",
        "vol_ratio", "atr",
        "momentum_10", "momentum_20", "volatility",
    ] if c in [
        "close", "open", "body", "range", "upper_wick", "lower_wick",
        "ret_1d", "ret_3d", "ret_5d",
        "ma5", "ma10", "ma20", "ma50",
        "ma5_dist", "ma10_dist", "ma20_dist", "ma50_dist",
        "ma_bullish", "ma_trend",
        "rsi", "macd_dif", "macd_hist",
        "boll_pos", "boll_width",
        "vol_ratio", "atr",
        "momentum_10", "momentum_20", "volatility",
    ]]


def build_feature_matrix(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Build clean feature matrix, removing NaN rows."""
    if df is None:
        return None
    feature_cols = get_feature_columns()
    matrix = df[feature_cols].copy()
    matrix = matrix.replace([np.inf, -np.inf], np.nan)
    matrix = matrix.dropna()
    return matrix
