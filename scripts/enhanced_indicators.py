#!/usr/bin/env python3
"""Enhanced Technical Indicators - CCI, RVI, StochRSI, Williams %R, OBV Divergence"""
import numpy as np
import pandas as pd
from typing import Dict, Tuple, Optional


def calc_cci(df: pd.DataFrame, period: int = 14) -> Dict:
    """Commodity Channel Index - measures current price relative to average price."""
    if len(df) < period + 1:
        return {"cci": 0.0, "signal": "neutral"}
    typical = (df["high"] + df["low"] + df["close"]) / 3
    sma = typical.rolling(window=period).mean()
    mad = typical.rolling(window=period).apply(lambda x: np.abs(x - x.mean()).mean())
    cci = (typical - sma) / (0.015 * mad + 1e-10)
    val = float(cci.iloc[-1])
    if val > 100:
        signal = "overbought"
    elif val < -100:
        signal = "oversold"
    elif val > 0:
        signal = "bullish"
    else:
        signal = "bearish"
    return {"cci": round(val, 2), "signal": signal}


def calc_rvi(df: pd.DataFrame, period: int = 14) -> Dict:
    """Relative Vigor Index - measures conviction of a price trend."""
    if len(df) < period + 1:
        return {"rvi": 0.0, "signal": "neutral"}
    close = df["close"].values
    open_ = df["open"].values
    high = df["high"].values
    low = df["low"].values
    
    body = (close - open_) / 2
    mid_range = (high + low) / 2
    
    # RVI: weighted convolution [3,2,1,-1,-2,-3] / 6
    w = np.array([3, 2, 1, -1, -2, -3], dtype=float)
    num = np.convolve(body, w[::-1], mode="valid") / 6.0
    den = np.convolve(mid_range, w[::-1], mode="valid") / 6.0
    
    pad_len = period + 2 - len(w)
    rvi_vals = np.concatenate([np.full(pad_len, np.nan), num / (den + 1e-10)])
    
    # Current RVI = mean of last `period` values
    recent = rvi_vals[-period:]
    rvi_val = float(np.nanmean(recent))
    
    # Signal line = 4-period SMA of RVI
    sig_recent = rvi_vals[-4:] if len(rvi_vals) >= 4 else rvi_vals
    signal_val = float(np.nanmean(sig_recent))
    
    if rvi_val > signal_val and rvi_val > 0:
        signal = "bullish"
    elif rvi_val < signal_val and rvi_val < 0:
        signal = "bearish"
    else:
        signal = "neutral"
    
    return {"rvi": round(rvi_val, 4), "signal_line": round(signal_val, 4), "signal": signal}



def calc_stoch_rsi(df: pd.DataFrame, rsi_period: int = 14, stoch_period: int = 14) -> Dict:
    """Stochastic RSI - RSI within RSI."""
    if len(df) < rsi_period + stoch_period:
        return {"stoch_rsi": 50.0, "k": 50.0, "d": 50.0, "signal": "neutral"}
    
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=rsi_period).mean()
    avg_loss = loss.rolling(window=rsi_period).mean()
    rs = avg_gain / (avg_loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))
    
    stoch_rsi = (rsi - rsi.rolling(stoch_period).min()) / (rsi.rolling(stoch_period).max() - rsi.rolling(stoch_period).min() + 1e-10)
    k = stoch_rsi
    d = k.rolling(3).mean()
    
    k_val = float(k.iloc[-1])
    d_val = float(d.iloc[-1]) if not np.isnan(d.iloc[-1]) else k_val
    
    if k_val < 20:
        signal = "oversold"
    elif k_val > 80:
        signal = "overbought"
    elif k_val > d_val:
        signal = "bullish"
    else:
        signal = "bearish"
    
    return {"stoch_rsi": round(k_val, 2), "k": round(k_val, 2), "d": round(d_val, 2), "signal": signal}


def calc_williams_r(df: pd.DataFrame, period: int = 14) -> Dict:
    """Williams %R - momentum indicator comparing close to high-low range."""
    if len(df) < period:
        return {"wr": -50.0, "signal": "neutral"}
    
    high_n = df["high"].rolling(period).max()
    low_n = df["low"].rolling(period).min()
    wr = (high_n - df["close"]) / (high_n - low_n + 1e-10) * -100
    
    val = float(wr.iloc[-1])
    if val < -80:
        signal = "oversold"
    elif val > -20:
        signal = "overbought"
    else:
        signal = "neutral"
    
    return {"williams_r": round(val, 2), "signal": signal}


def detect_obv_divergence(df: pd.DataFrame, window: int = 20) -> Dict:
    """Detect OBV divergence with price - strong reversal signal."""
    if len(df) < window + 5:
        return {"divergence": "none", "strength": 0}
    
    close = df["close"].values
    volume = df["volume"].values
    
    # Calculate OBV
    obv = [0.0]
    for i in range(1, len(close)):
        if close[i] > close[i-1]:
            obv.append(obv[-1] + volume[i])
        elif close[i] < close[i-1]:
            obv.append(obv[-1] - volume[i])
        else:
            obv.append(obv[-1])
    
    obv_series = pd.Series(obv)
    
    # Find local maxima/minima in recent window
    price_window = close[-window:]
    obv_window = obv_series.values[-window:]
    
    # Simple divergence: price making higher highs but OBV making lower highs
    price_highs = []
    obv_highs = []
    price_lows = []
    obv_lows = []
    
    for i in range(2, len(price_window) - 2):
        if (price_window[i] > price_window[i-1] and price_window[i] > price_window[i-2] and
            price_window[i] > price_window[i+1] and price_window[i] > price_window[i+2]):
            price_highs.append(price_window[i])
            obv_highs.append(obv_window[i])
        if (price_window[i] < price_window[i-1] and price_window[i] < price_window[i-2] and
            price_window[i] < price_window[i+1] and price_window[i] < price_window[i+2]):
            price_lows.append(price_window[i])
            obv_lows.append(obv_window[i])
    
    divergence = "none"
    strength = 0
    
    if len(price_highs) >= 2 and len(obv_highs) >= 2:
        if price_highs[-1] > price_highs[-2] and obv_highs[-1] < obv_highs[-2]:
            divergence = "bearish_divergence"
            strength = 75
        elif price_highs[-1] < price_highs[-2] and obv_highs[-1] > obv_highs[-2]:
            divergence = "bullish_divergence"
            strength = 75
    
    if len(price_lows) >= 2 and len(obv_lows) >= 2:
        if price_lows[-1] < price_lows[-2] and obv_lows[-1] > obv_lows[-2]:
            divergence = "bullish_divergence"
            strength = 80
        elif price_lows[-1] > price_lows[-2] and obv_lows[-1] < obv_lows[-2]:
            divergence = "bearish_divergence"
            strength = 80
    
    return {"divergence": divergence, "strength": strength}


def calc_all_enhanced(df: pd.DataFrame) -> Dict:
    """Calculate all enhanced indicators at once."""
    return {
        "cci": calc_cci(df),
        "rvi": calc_rvi(df),
        "stoch_rsi": calc_stoch_rsi(df),
        "williams_r": calc_williams_r(df),
        "obv_divergence": detect_obv_divergence(df),
    }


def enhanced_signal_score(df: pd.DataFrame) -> Dict:
    """Combine all enhanced indicators into a single score."""
    indicators = calc_all_enhanced(df)
    
    score = 50
    reasons = []
    
    # CCI contribution
    cci = indicators["cci"]["cci"]
    if cci < -100:
        score += 12; reasons.append(f"CCI oversold({cci:.0f})")
    elif cci < -50:
        score += 6; reasons.append(f"CCI bearish({cci:.0f})")
    elif cci > 100:
        score -= 12; reasons.append(f"CCI overbought({cci:.0f})")
    elif cci > 50:
        score -= 6; reasons.append(f"CCI bullish({cci:.0f})")
    
    # RVI contribution
    rvi = indicators["rvi"]["signal"]
    if rvi == "bullish":
        score += 8; reasons.append("RVI bullish")
    elif rvi == "bearish":
        score -= 8; reasons.append("RVI bearish")
    
    # StochRSI contribution
    srsi = indicators["stoch_rsi"]["signal"]
    if srsi == "oversold":
        score += 10; reasons.append("StochRSI oversold")
    elif srsi == "overbought":
        score -= 10; reasons.append("StochRSI overbought")
    
    # Williams %R contribution
    wr = indicators["williams_r"]["signal"]
    if wr == "oversold":
        score += 10; reasons.append("WR oversold")
    elif wr == "overbought":
        score -= 10; reasons.append("WR overbought")
    
    # OBV Divergence
    div = indicators["obv_divergence"]
    if div["divergence"] == "bullish_divergence":
        score += div["strength"]; reasons.append(f"OBV bullish div({div['strength']})")
    elif div["divergence"] == "bearish_divergence":
        score -= div["strength"]; reasons.append(f"OBV bearish div({div['strength']})")
    
    score = max(0, min(100, score))
    
    if score >= 65:
        rating = "bullish"
    elif score <= 35:
        rating = "bearish"
    else:
        rating = "neutral"
    
    return {
        "score": score, "rating": rating, "reasons": reasons,
        "indicators": indicators,
    }
