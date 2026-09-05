#!/usr/bin/env python3
import json, sys, os, time
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from cache_util import retry_call


def fetch_kline(symbol, ktype="1d", num=60, start_date=None, end_date=None):
    try:
        from futu import OpenQuoteContext, KLType, AuType
        kl_map = {"1m": KLType.K_1M, "3m": KLType.K_3M, "5m": KLType.K_5M,
                  "15m": KLType.K_15M, "30m": KLType.K_30M, "60m": KLType.K_60M,
                  "1d": KLType.K_DAY, "1w": KLType.K_WEEK, "1M": KLType.K_MON}
        kl_type = kl_map.get(ktype, KLType.K_DAY)
        ctx = OpenQuoteContext(host="127.0.0.1", port=11111)
        try:
            page_size = min(num, 1000)
            ret, df, next_key = ctx.request_history_kline(symbol, start=start_date, end=end_date,
                                                          ktype=kl_type, autype=AuType.QFQ, max_count=page_size)
            if ret != 0 or df is None or df.empty:
                return None
            all_rows = [df]
            page_count = 1
            while next_key is not None and page_count < (num // page_size) + 2:
                ret2, df2, next_key2 = ctx.request_history_kline(symbol, start=start_date, end=end_date,
                                                                 ktype=kl_type, autype=AuType.QFQ,
                                                                 max_count=page_size, page_req_key=next_key)
                if ret2 != 0 or df2 is None or df2.empty:
                    break
                all_rows.append(df2)
                next_key = next_key2
                page_count += 1
            result = pd.concat(all_rows, ignore_index=True)
            keep = ["time_key", "open", "high", "low", "close", "volume", "last_close"]
            result = result[[c for c in keep if c in result.columns]]
            result = result.sort_values("time_key").reset_index(drop=True)
            result = result.tail(num).reset_index(drop=True)
            return result
        finally:
            ctx.close()
    except Exception as e:
        print(f"[tech_engine] fetch_kline error for {symbol}: {e}", file=sys.stderr)
        return None


def get_price(symbol):
    try:
        from futu import OpenQuoteContext
        ctx = OpenQuoteContext(host="127.0.0.1", port=11111)
        try:
            ret, df = ctx.get_market_snapshot([symbol])
            if ret != 0 or df is None or len(df) == 0:
                return None
            row = df.iloc[0]
            last = float(row.get("last_price", 0))
            prev = float(row.get("prev_close_price", 0))
            high = float(row.get("high_price", 0))
            low = float(row.get("low_price", 0))
            vol = float(row.get("volume", 0))
            open_p = float(row.get("open_price", 0))
            chg = ((last - prev) / prev * 100) if prev > 0 else 0
            return {"symbol": symbol, "latest_price": last, "open": open_p,
                    "high": high, "low": low, "prev_close": prev,
                    "change_pct": round(chg, 2), "volume": int(vol),
                    "update_time": str(row.get("update_time", ""))[:19],
                    "pe_ratio": float(row.get("pe_ratio", 0)) if pd.notna(row.get("pe_ratio")) else None}
        finally:
            ctx.close()
    except Exception as e:
        print(f"[tech_engine] get_price error: {e}", file=sys.stderr)
        return None


def get_premarket_hot(top=20):
    try:
        from futu import OpenQuoteContext
        ctx = OpenQuoteContext(host="127.0.0.1", port=11111)
        try:
            ret, result = ctx.get_us_pre_market_rank()
            if ret != 0 or result is None:
                return []
            if isinstance(result, tuple):
                df = result[1] if len(result) > 1 else result[0]
            else:
                df = result
            if df is None or len(df) == 0:
                return []
            rows = []
            for _, r in df.head(top).iterrows():
                rows.append({"code": str(r.get("security", "")), "name": str(r.get("name", "")),
                             "last_price": float(r.get("pre_market_price", 0)),
                             "change_pct": float(r.get("change_ratio", 0)),
                             "volume": int(r.get("volume", 0))})
            return rows
        finally:
            ctx.close()
    except Exception as e:
        print(f"[tech_engine] get_premarket_hot error: {e}", file=sys.stderr)
        return []


def get_hot_list(market="US", top=20):
    try:
        from futu import OpenQuoteContext
        ctx = OpenQuoteContext(host="127.0.0.1", port=11111)
        try:
            ret, result = ctx.get_hot_list([market], count=top)
            if ret != 0 or result is None:
                return []
            if isinstance(result, tuple):
                df = result[1] if len(result) > 1 else result[0]
            else:
                df = result
            if df is None or len(df) == 0:
                return []
            rows = []
            for _, r in df.head(top).iterrows():
                rows.append({"code": str(r.get("code", "")), "name": str(r.get("name", "")),
                             "last_price": float(r.get("last_price", 0)),
                             "change_pct": float(r.get("change_ratio", 0)),
                             "volume": int(r.get("volume", 0)),
                             "hot_score": float(r.get("hot_score", 0))})
            return rows
        finally:
            ctx.close()
    except Exception as e:
        print(f"[tech_engine] get_hot_list error: {e}", file=sys.stderr)
        return []


def calc_ma(df, periods=(5, 10, 20, 60)):
    result = {}
    for p in periods:
        col = f"MA{p}"
        df[col] = df["close"].rolling(window=p).mean()
        result[col] = float(df[col].iloc[-1]) if pd.notna(df[col].iloc[-1]) else 0.0
    return result


def calc_ema(df, periods=(12, 26, 9)):
    result = {}
    for p in periods:
        col = f"EMA{p}"
        df[col] = df["close"].ewm(span=p, adjust=False).mean()
        result[col] = float(df[col].iloc[-1]) if pd.notna(df[col].iloc[-1]) else 0.0
    return result


def calc_macd(df, fast=12, slow=26, signal=9):
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    df["MACD"] = ema_fast - ema_slow
    df["MACD_signal"] = df["MACD"].ewm(span=signal, adjust=False).mean()
    df["MACD_hist"] = df["MACD"] - df["MACD_signal"]
    return {"dif": float(df["MACD"].iloc[-1]) if pd.notna(df["MACD"].iloc[-1]) else 0.0,
            "dea": float(df["MACD_signal"].iloc[-1]) if pd.notna(df["MACD_signal"].iloc[-1]) else 0.0,
            "hist": float(df["MACD_hist"].iloc[-1]) if pd.notna(df["MACD_hist"].iloc[-1]) else 0.0,
            "signal": "bullish" if df["MACD"].iloc[-1] > df["MACD_signal"].iloc[-1] else "bearish"}


def calc_rsi(df, period=14):
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else 50.0


def calc_kdj(df, n=9, m1=3, m2=3):
    low_n = df["low"].rolling(window=n).min()
    high_n = df["high"].rolling(window=n).max()
    rsv = (df["close"] - low_n) / (high_n - low_n) * 100
    rsv = rsv.fillna(50.0)
    k = rsv.ewm(com=m1-1, adjust=False).mean()
    d = k.ewm(com=m2-1, adjust=False).mean()
    j = 3 * k - 2 * d
    return {"k": float(k.iloc[-1]) if pd.notna(k.iloc[-1]) else 50.0,
            "d": float(d.iloc[-1]) if pd.notna(d.iloc[-1]) else 50.0,
            "j": float(j.iloc[-1]) if pd.notna(j.iloc[-1]) else 50.0}


def calc_boll(df, period=20, std_mult=2.0):
    df["BOLL_mid"] = df["close"].rolling(window=period).mean()
    rolling_std = df["close"].rolling(window=period).std()
    df["BOLL_upper"] = df["BOLL_mid"] + rolling_std * std_mult
    df["BOLL_lower"] = df["BOLL_mid"] - rolling_std * std_mult
    upper = float(df["BOLL_upper"].iloc[-1]) if pd.notna(df["BOLL_upper"].iloc[-1]) else 0.0
    mid = float(df["BOLL_mid"].iloc[-1]) if pd.notna(df["BOLL_mid"].iloc[-1]) else 0.0
    lower = float(df["BOLL_lower"].iloc[-1]) if pd.notna(df["BOLL_lower"].iloc[-1]) else 0.0
    close_val = float(df["close"].iloc[-1])
    width = ((upper - lower) / mid * 100) if mid > 0 else 0
    pos = ((close_val - lower) / (upper - lower) * 100) if (upper - lower) > 0 else 50
    return {"upper": upper, "mid": mid, "lower": lower, "width_pct": round(width, 2), "position_pct": round(pos, 1)}


def calc_atr(df, period=14):
    high = df["high"]; low = df["low"]; close_prev = df["close"].shift(1)
    tr1 = high - low
    tr2 = abs(high - close_prev)
    tr3 = abs(low - close_prev)
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return float(atr.iloc[-1]) if pd.notna(atr.iloc[-1]) else 0.0


def calc_obv(df):
    obv = [0]
    for i in range(1, len(df)):
        if df["close"].iloc[i] > df["close"].iloc[i-1]:
            obv.append(obv[-1] + df["volume"].iloc[i])
        elif df["close"].iloc[i] < df["close"].iloc[i-1]:
            obv.append(obv[-1] - df["volume"].iloc[i])
        else:
            obv.append(obv[-1])
    df["OBV"] = obv
    return float(df["OBV"].iloc[-1]) if len(obv) > 0 else 0.0


def generate_signal(symbol, timeframe="1d", num_bars=60):
    df = fetch_kline(symbol, ktype=timeframe, num=num_bars)
    if df is None or len(df) < 20:
        return {"module": "tech", "status": "error",
                "error": f"Insufficient data for {symbol} (need >=20 bars, got {len(df) if df is not None else 0})"}
    price = get_price(symbol)
    ma = calc_ma(df)
    ema = calc_ema(df)
    macd = calc_macd(df)
    rsi = calc_rsi(df)
    kdj = calc_kdj(df)
    boll = calc_boll(df)
    atr = calc_atr(df)
    obv = calc_obv(df)
    dims = {}
    # 1. Trend - 20pts
    trend_score = 0
    closes = df["close"].tolist()
    ma5 = ma["MA5"]; ma10 = ma["MA10"]; ma20 = ma["MA20"]; ma60 = ma["MA60"]
    latest = price["latest_price"] if price else closes[-1]
    if ma5 > ma10 > ma20: trend_score += 10
    elif ma5 < ma10 < ma20: trend_score += 0
    elif ma5 > ma20: trend_score += 6
    else: trend_score += 2
    if latest > ma20: trend_score += 5
    elif latest > ma10: trend_score += 3
    if ma5 > ma60: trend_score += min(5, int((ma5 - ma60) / ma60 * 100))
    dims["trend"] = {"score": min(20, trend_score), "reason": f"MA5={ma5:.1f} MA20={ma20:.1f} Price={latest:.1f}"}
    # 2. Momentum - 20pts
    mom_score = 0
    if macd["dif"] > macd["dea"]: mom_score += 8
    elif macd["dif"] > 0: mom_score += 4
    if macd["hist"] > 0: mom_score += 4
    if rsi > 50: mom_score += 5
    elif rsi > 40: mom_score += 2
    if 40 < rsi < 60: mom_score += 3
    elif rsi < 30: mom_score += 5
    elif rsi > 70: mom_score += 1
    dims["momentum"] = {"score": min(20, mom_score),
                        "reason": f"MACD={macd['dif']:.2f}/{macd['dea']:.2f} RSI={rsi:.1f} signal={macd['signal']}"}
    # 3. Volatility - 15pts
    vol_score = 0
    if boll["position_pct"] > 80: vol_score += 2
    elif boll["position_pct"] > 50: vol_score += 5
    elif boll["position_pct"] > 20: vol_score += 8
    else: vol_score += 3
    if boll["width_pct"] < 5: vol_score += 5
    elif boll["width_pct"] < 10: vol_score += 2
    dims["volatility"] = {"score": min(15, vol_score),
                          "reason": f"BOLL_pos={boll['position_pct']}% width={boll['width_pct']}%"}
    # 4. KDJ - 15pts
    kdj_score = 0
    if kdj["k"] > kdj["d"] and kdj["k"] < 80: kdj_score += 8
    elif kdj["k"] > kdj["d"]: kdj_score += 4
    if 20 < kdj["j"] < 80: kdj_score += 7
    elif kdj["j"] < 20: kdj_score += 10
    elif kdj["j"] > 80: kdj_score += 2
    dims["kdj"] = {"score": min(15, kdj_score), "reason": f"K={kdj['k']:.1f} D={kdj['d']:.1f} J={kdj['j']:.1f}"}
    # 5. Volume - 15pts
    vol_trend_score = 0
    obv_vals = df["OBV"].tolist()
    if len(obv_vals) >= 10:
        obv_recent = sum(obv_vals[-5:]) / 5
        obv_older = sum(obv_vals[:-5]) / max(1, len(obv_vals) - 5)
        if obv_recent > obv_older: vol_trend_score += 10
        else: vol_trend_score += 3
    avg_vol = df["volume"].iloc[-20:].mean() if len(df) >= 20 else df["volume"].mean()
    latest_vol = df["volume"].iloc[-1]
    if latest_vol > avg_vol * 1.5: vol_trend_score += 5
    obv_dir = "up" if vol_trend_score >= 7 else "down"
    dims["volume"] = {"score": min(15, vol_trend_score),
                      "reason": f"OBV_trend={obv_dir} vol_ratio={latest_vol/avg_vol:.1f}x" if avg_vol > 0 else "insufficient volume data"}
    # Total
    total_score = sum(d["score"] for d in dims.values())
    if total_score >= 75: rating = "Buy"
    elif total_score >= 55: rating = "Overweight"
    elif total_score >= 40: rating = "Hold"
    elif total_score >= 25: rating = "Underweight"
    else: rating = "Sell"
    # Trade plan
    entry = round(latest * 0.985, 2)
    stop = round(entry - atr * 2.0, 2) if atr > 0 else round(entry * 0.95, 2)
    risk = entry - stop
    tp1 = round(entry + risk * 2.0, 2)
    tp2 = round(entry + risk * 2.5, 2)
    rr = round((tp1 - entry) / risk, 2) if risk > 0 else 0
    signals = []
    if macd["dif"] > macd["dea"]: signals.append("MACD golden cross")
    if rsi < 30: signals.append("RSI oversold (<30)")
    elif rsi > 70: signals.append("RSI overbought (>70)")
    if kdj["k"] > kdj["d"] and kdj["k"] < 50: signals.append("KDJ golden cross")
    if latest > ma20: signals.append("Price above MA20")
    elif latest < ma20: signals.append("Price below MA20")
    if boll["position_pct"] < 20: signals.append("Near Bollinger lower band")
    elif boll["position_pct"] > 80: signals.append("Near Bollinger upper band")
    return {"module": "tech", "status": "ok", "symbol": symbol,
            "generated_at": datetime.now().isoformat(),
            "data": {"rating": rating, "score": total_score, "price": price,
                     "dimensions": dims,
                     "indicators": {"ma": ma, "ema": ema, "macd": macd, "rsi": round(rsi, 1),
                                    "kdj": kdj, "boll": boll, "atr": round(atr, 2)},
                     "signals": signals,
                     "trade_plan": {"entry_zone": entry, "stop_loss": stop, "target_1": tp1, "target_2": tp2,
                                    "risk_reward": rr, "atr": round(atr, 2),
                                    "position_size_pct": round(100 / max(1, rr), 1),
                                    "risk_usd": round(risk * 100 / max(1, rr), 2)},
                     "last_time": str(df["time_key"].iloc[-1])[:10], "bar_count": len(df)}}


def get_tech_summary(symbol, timeframe="1d"):
    result = generate_signal(symbol, timeframe=timeframe, num_bars=60)
    if result["status"] != "ok":
        return result
    d = result["data"]
    return {"symbol": symbol, "rating": d["rating"], "score": d["score"],
            "price": d["price"], "signals": d["signals"],
            "trade_plan": d["trade_plan"], "last_time": d["last_time"]}


def format_tech_output(data):
    if data.get("status") != "ok":
        return f"[Tech] {data.get('error', 'Unavailable')}"
    d = dict(data.get("data", data))
    if "symbol" not in d and "symbol" in data:
        d["symbol"] = data["symbol"]
    lines = []
    lines.append("=" * 60)
    lines.append(f"  {d['symbol']}  Technical Analysis")
    lines.append(f"  Rating: {d['rating']} (Score: {d['score']}/100)")
    lines.append(f"  Price: ${d['price']['latest_price']:.2f}  ({d['price']['change_pct']:+.2f}%)  ATR: ${d['indicators']['atr']:.2f}")
    lines.append(f"  Data: {d['bar_count']} bars  Last: {d['last_time']}")
    lines.append("")
    lines.append("  Dimension Scores:")
    for dim, info in d["dimensions"].items():
        score = info["score"]
        bar_len = int(score / 20 * 10)
        bar = "#" * bar_len + "-" * (10 - bar_len)
        lines.append(f"    {dim.capitalize():12s}: [{bar}] {score}/20")
        lines.append(f"              {info['reason']}")
    lines.append("")
    ind = d["indicators"]
    lines.append("  Key Indicators:")
    lines.append(f"    MA5={ind['ma']['MA5']:.1f} MA10={ind['ma']['MA10']:.1f} MA20={ind['ma']['MA20']:.1f} MA60={ind['ma']['MA60']:.1f}")
    lines.append(f"    MACD: DIF={ind['macd']['dif']:.3f} DEA={ind['macd']['dea']:.3f} Hist={ind['macd']['hist']:.3f} ({ind['macd']['signal']})")
    lines.append(f"    RSI(14): {ind['rsi']:.1f}")
    lines.append(f"    KDJ: K={ind['kdj']['k']:.1f} D={ind['kdj']['d']:.1f} J={ind['kdj']['j']:.1f}")
    lines.append(f"    BOLL: Upper={ind['boll']['upper']:.1f} Mid={ind['boll']['mid']:.1f} Lower={ind['boll']['lower']:.1f} (pos={ind['boll']['position_pct']}%)")
    lines.append("")
    if d["signals"]:
        lines.append("  Signals:")
        for s in d["signals"]:
            lines.append(f"    - {s}")
        lines.append("")
    tp = d["trade_plan"]
    lines.append("  Trade Plan:")
    lines.append(f"    Entry: ${tp['entry_zone']}  Stop: ${tp['stop_loss']}")
    lines.append(f"    Target1: ${tp['target_1']}  Target2: ${tp['target_2']}")
    lines.append(f"    R:R = {tp['risk_reward']:.1f}:1  Position: {tp['position_size_pct']:.1f}%")
    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)


def scan_premarket(top=20):
    stocks = get_premarket_hot(top)
    return {"status": "ok", "source": "futu_premarket", "count": len(stocks), "data": stocks}


def scan_hot_list(market="US", top=20):
    stocks = get_hot_list(market, top)
    return {"status": "ok" if stocks else "empty", "source": "futu_hot_list", "count": len(stocks), "data": stocks}
