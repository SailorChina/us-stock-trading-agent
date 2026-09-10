#!/usr/bin/env python3
"""stock_selector — pure, look-ahead-free factor scores for stock selection.

The daily stock picker (daily_pick.py) and the cross-sectional validator
(strategy_validator.py --mode cross --style X) BOTH use these functions, so a
factor can never be added to the live picker without being measurable.

Every scorer takes only an OHLCV DataFrame (past data) and returns
{"score": 0-100, "reasons": [...], "stats": {...}}. Nothing here touches the
network, which is what makes validation without look-ahead possible.

Three styles, deliberately kept as SEPARATE rankers instead of one melted
composite — blending long-horizon momentum with mean-reversion would cancel
both to zero:

  * momentum  — trend following: 12-1 momentum, trend structure, 52w-high
                proximity, volume confirmation. For holdings of weeks.
  * reversal  — buy weakness ONLY inside an intact longer uptrend: pullback
                depth + short-term oversold, while requiring close > MA200
                and positive 1y return (no falling knives).
  * quality   — low-volatility / stability / liquidity proxies, so the list
                is tradeable and survivable (a 100%-vol name is unownable
                at any sane size).
"""
import json
import math
import os
import sys
from typing import Callable, Dict, Optional

import numpy as np
import pandas as pd

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)

MIN_BARS = 120          # bare minimum to score at all
IDEAL_BARS = 253        # enough for MA200 + 12-1 momentum


# ---------------------------------------------------------------------------
# tiny pure indicator toolkit (vectorised, on the close/high/low/volume arrays)
# ---------------------------------------------------------------------------

def _arr(df: pd.DataFrame, col: str) -> np.ndarray:
    return df[col].to_numpy(dtype=float)


def _last(series: pd.Series) -> Optional[float]:
    v = series.dropna()
    return float(v.iloc[-1]) if len(v) else None


def _ma(arr: np.ndarray, p: int) -> Optional[float]:
    if len(arr) < p:
        return None
    return float(np.mean(arr[-p:]))


def _rsi(arr: np.ndarray, period: int = 14) -> Optional[float]:
    if len(arr) < period + 1:
        return None
    d = np.diff(arr[-(period + 1):])
    gain = d[d > 0].sum() / period
    loss = -d[d < 0].sum() / period
    if loss == 0:
        return 100.0 if gain > 0 else 50.0
    rs = gain / loss
    return float(100.0 - 100.0 / (1.0 + rs))


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> Optional[float]:
    if len(close) < period + 1:
        return None
    tr = np.maximum(high[-period:] - low[-period:],
                    np.maximum(np.abs(high[-period:] - close[-period - 1:-1]),
                               np.abs(low[-period:] - close[-period - 1:-1])))
    return float(np.mean(tr))


def _annualized_vol(close: np.ndarray) -> Optional[float]:
    if len(close) < 21:
        return None
    r = np.diff(close[-22:]) / close[-22:-1]
    r = r[np.isfinite(r) & (r > -1)]
    if len(r) < 10:
        return None
    return float(np.std(r, ddof=1) * math.sqrt(252))


# ---------------------------------------------------------------------------
# the three styles
# ---------------------------------------------------------------------------

def momentum_score(df: pd.DataFrame) -> Dict:
    c = _arr(df, "close")
    v = _arr(df, "volume")
    n = len(c)
    stats: Dict[str, float] = {"bars": n}

    if n < MIN_BARS:
        return {"score": 0, "reasons": ["insufficient history"], "stats": stats}

    reasons = []
    score = 0.0

    # --- 1. trend structure (max 30): close vs MA200, MA20 vs MA50 ---------
    ma20, ma50, ma200 = _ma(c, 20), _ma(c, 50), _ma(c, 200)
    if ma200 and c[-1] > ma200:
        score += 20
        reasons.append(f"above MA200 ({c[-1]:.2f}>{ma200:.2f})")
    elif ma200 and c[-1] <= ma200:
        reasons.append("below MA200")
    if ma20 and ma50 and ma20 > ma50:
        score += 10
        reasons.append("MA20>MA50")

    # --- 2. 12-1 momentum when history allows, else headline 1y return -----
    if n >= 253:
        m12_1 = c[-21] / c[-253] - 1.0          # skip the most recent month
        mom = min(max(m12_1, -0.5), 1.0)
        stats["mom12_1"] = round(m12_1 * 100, 1)
        reasons.append(f"12-1 momentum {m12_1 * 100:+.0f}%")
    else:
        mom = c[-1] / c[0] - 1.0
        reasons.append(f"span return {mom * 100:+.0f}% (short history)")
    score += min(25.0, max(0.0, mom * 25.0 / 0.20))     # 20% -> 25pts
    stats["span_ret_pct"] = round((c[-1] / c[0] - 1.0) * 100, 1)

    # --- 3. recent relative strength (max 15): 63d return -----------------
    if n >= 64:
        r63 = c[-1] / c[-64] - 1.0
        stats["ret_63d_pct"] = round(r63 * 100, 1)
        score += min(15.0, max(0.0, r63 * 15.0 / 0.12))
        if r63 <= 0:
            reasons.append(f"63d return {r63 * 100:+.1f}%")

    # --- 4. distance from 52w high (max 15): leaders only -----------------
    if n >= 63:
        hi52 = float(np.max(c[-253:])) if n >= 253 else float(np.max(c))
        dist = c[-1] / hi52
        stats["dist_52w_high"] = round(dist, 3)
        score += min(15.0, max(0.0, (dist - 0.80) * 15.0 / 0.18))
        if dist >= 0.98:
            reasons.append("near 52w high")

    # --- 5. volume confirmation (max 15) ----------------------------------
    if n >= 65:
        vv = float(np.mean(v[-5:])) / max(float(np.mean(v[-65:-5])), 1.0)
        stats["vol_ratio"] = round(vv, 2)
        score += min(15.0, max(0.0, (vv - 0.7) * 15.0 / 1.3))
        if vv < 0.7:
            reasons.append("volume contracting")

    return {"score": round(min(100.0, score), 1), "reasons": reasons[:5], "stats": stats}


def reversal_score(df: pd.DataFrame) -> Dict:
    """Buy weakness ONLY inside an intact longer uptrend (no falling knives)."""
    c = _arr(df, "close")
    n = len(c)
    stats: Dict[str, float] = {"bars": n}

    if n < MIN_BARS:
        return {"score": 0, "reasons": ["insufficient history"], "stats": stats}

    reasons = []
    score = 0.0

    # gate 1: long-term uptrend must be intact, else this is a falling knife
    ma200 = _ma(c, 200)
    uptrend = bool(ma200 and c[-1] > ma200)
    ret_1y_ok = bool(n >= 253 and c[-1] > c[-253]) or (n < 253 and c[-1] > c[0])
    if not uptrend or not ret_1y_ok:
        reasons.append("not in an uptrend - skipping falling knife")
        return {"score": 0.0, "reasons": reasons, "stats": stats}
    score += 20
    reasons.append("uptrend intact (>MA200)")

    # gate 2: must actually have pulled back recently (not making new highs)
    hi20 = float(np.max(c[-20:]))
    dd20 = c[-1] / hi20 - 1.0
    stats["dd_20d_pct"] = round(dd20 * 100, 1)
    if dd20 > -0.03:
        reasons.append("no pullback (near 20d high)")
        return {"score": 0.0, "reasons": reasons, "stats": stats}
    score += min(20.0, abs(dd20) * 20.0 / 0.12)          # deeper pullback -> more
    reasons.append(f"{dd20 * 100:.1f}% off 20d high")

    # gate 3: short-term oversold
    z = 0.0
    if n >= 21:
        m20 = float(np.mean(c[-20:]))
        s20 = float(np.std(c[-20:]))
        if s20 > 0:
            z = (c[-1] - m20) / s20
            stats["z_20d"] = round(z, 2)
    rsi14 = _rsi(c, 14)
    if rsi14 is not None:
        stats["rsi14"] = round(rsi14, 1)
    if z <= -1.5 or (rsi14 is not None and rsi14 <= 35):
        score += 20
        reasons.append(f"oversold (z={z:.1f}, rsi={rsi14:.0f})")
    else:
        reasons.append("not yet oversold")
    if rsi14 is not None and rsi14 <= 15:
        score += 5

    # gate 4: STABILISATION — the lesson from the 60-name event study.
    # Buying a pullback while it is still falling produced clustered -10%+
    # losses (all five worst names were semis). Require an UP DAY: the bar
    # must close above the previous close, i.e. someone is finally bidding.
    rising = bool(n >= 2 and c[-1] > c[-2])
    if not rising:
        reasons.append("still falling - wait for confirmation")
        return {"score": 0.0, "reasons": reasons, "stats": stats}
    ma5 = _ma(c, 5)
    if ma5 and c[-1] > ma5:
        score += 30
        reasons.append("stabilising: up day + reclaimed MA5")
    else:
        score += 12
        reasons.append("up day, still below MA5")

    # trend health bonus within the pullback (higher lows vs MA50)
    ma50 = _ma(c, 50)
    if ma50 and c[-1] > ma50:
        score += 10
        reasons.append("holding above MA50")

    return {"score": round(min(100.0, score), 1), "reasons": reasons[:5], "stats": stats}


def quality_score(df: pd.DataFrame, min_price: float = 3.0,
                  min_adv_usd: float = 20_000_000.0) -> Dict:
    """Low-vol / stability / liquidity proxies — tradeable and survivable."""
    c = _arr(df, "close")
    v = _arr(df, "volume")
    n = len(c)
    stats: Dict[str, float] = {"bars": n}

    if n < MIN_BARS:
        return {"score": 0, "reasons": ["insufficient history"], "stats": stats}

    reasons = []
    score = 0.0
    px = float(c[-1])

    if px < min_price:
        reasons.append(f"price {px:.2f} < {min_price:.0f}")
        return {"score": 0.0, "reasons": reasons, "stats": stats}
    score += 15

    adv = float(np.mean(c[-21:] * v[-21:])) if n >= 21 else float(np.mean(c * v))
    stats["adv_usd_m"] = round(adv / 1e6, 0)
    if adv >= min_adv_usd:
        score += 20
    else:
        reasons.append(f"thin liquidity (adv ${adv/1e6:.0f}M)")

    vol = _annualized_vol(c)
    if vol is not None:
        stats["ann_vol_pct"] = round(vol * 100, 1)
        if vol <= 0.45:
            score += 25
            reasons.append(f"moderate vol {vol*100:.0f}%")
        elif vol <= 0.80:
            score += 12
        else:
            reasons.append(f"very high vol {vol*100:.0f}%")

    # stability: count of nasty down days and max drawdown over ~63 bars
    if n >= 64:
        w = c[-64:]
        drawdowns = w / np.maximum.accumulate(w) - 1.0
        mdd = float(np.min(drawdowns))
        stats["mdd_63d_pct"] = round(mdd * 100, 1)
        if mdd > -0.15:
            score += 20
        elif mdd > -0.30:
            score += 8
        big_downs = int(np.sum(np.diff(w) / w[:-1] < -0.05))
        if big_downs == 0:
            score += 10
        elif big_downs <= 2:
            score += 5

    # return quality: Sharpe-like ratio of the last 63 daily returns
    if n >= 64:
        r = np.diff(c[-64:]) / c[-64:-1]
        r = r[np.isfinite(r) & (r > -1)]
        if len(r) >= 20 and float(np.std(r, ddof=1)) > 0:
            sharpe = float(np.mean(r)) / float(np.std(r, ddof=1)) * math.sqrt(252)
            stats["sharpe_63d"] = round(sharpe, 1)
            score += min(10.0, max(0.0, sharpe))

    return {"score": round(min(100.0, score), 1), "reasons": reasons[:4], "stats": stats}


# Coarse sector buckets. Reversal signals clustered hard by sector in the
# 60-name event study (the five worst names were all semis, each -10%+), so
# diversification has to be enforced at the picker level, not hoped for.
SECTORS: Dict[str, str] = {
    "US.NVDA": "semis", "US.AMD": "semis", "US.INTC": "semis", "US.QCOM": "semis",
    "US.TXN": "semis", "US.AMAT": "semis", "US.MU": "semis", "US.MRVL": "semis",
    "US.AVGO": "semis", "US.KLAC": "semis", "US.LRCX": "semis", "US.MCHP": "semis",
    "US.NXPI": "semis", "US.ADI": "semis", "US.TSM": "semis", "US.ARM": "semis",
    "US.MSFT": "software", "US.ORCL": "software", "US.CRM": "software",
    "US.ADBE": "software", "US.NOW": "software", "US.INTU": "software",
    "US.WDAY": "software", "US.TEAM": "software", "US.SNOW": "software",
    "US.NET": "software", "US.DDOG": "software", "US.CRWD": "software",
    "US.PANW": "software", "US.ZS": "software", "US.MDB": "software",
    "US.SHOP": "software", "US.PLTR": "software", "US.SNPS": "software",
    "US.CDNS": "software", "US.ANET": "networking", "US.AAPL": "hardware",
    "US.GOOGL": "internet", "US.META": "internet", "US.AMZN": "internet",
    "US.NFLX": "internet", "US.SPOT": "internet", "US.RBLX": "internet",
    "US.ABNB": "internet", "US.DASH": "internet", "US.PYPL": "payments",
    "US.SQ": "payments", "US.MA": "payments", "US.V": "payments",
    "US.JPM": "financials", "US.BAC": "financials", "US.WFC": "financials",
    "US.GS": "financials", "US.MS": "financials", "US.C": "financials",
    "US.AXP": "financials", "US.BLK": "financials", "US.SCHW": "financials",
    "US.MCO": "financials", "US.MMC": "financials", "US.PLD": "reits",
    "US.AMT": "reits", "US.CCI": "reits", "US.EQIX": "reits", "US.CBRE": "reits",
    "US.UNH": "healthcare", "US.LLY": "healthcare", "US.JNJ": "healthcare",
    "US.PFE": "healthcare", "US.MRK": "healthcare", "US.ABBV": "healthcare",
    "US.AMGN": "healthcare", "US.TMO": "healthcare", "US.DHR": "healthcare",
    "US.ISRG": "healthcare", "US.MDT": "healthcare", "US.SYK": "healthcare",
    "US.VRTX": "healthcare", "US.REGN": "healthcare", "US.GILD": "healthcare",
    "US.BIIB": "healthcare", "US.CVS": "healthcare",
    "US.WMT": "consumer", "US.COST": "consumer", "US.PG": "consumer",
    "US.KO": "consumer", "US.PEP": "consumer", "US.MCD": "consumer",
    "US.SBUX": "consumer", "US.NKE": "consumer", "US.HD": "consumer",
    "US.LOW": "consumer", "US.TGT": "consumer", "US.CMG": "consumer",
    "US.DIS": "consumer", "US.LULU": "consumer", "US.TJX": "consumer",
    "US.CL": "consumer", "US.EL": "consumer", "US.TSLA": "autos",
    "US.XOM": "energy", "US.CVX": "energy", "US.COP": "energy", "US.SLB": "energy",
    "US.CAT": "industrial", "US.DE": "industrial", "US.HON": "industrial",
    "US.BA": "industrial", "US.GE": "industrial", "US.RTX": "industrial",
    "US.LMT": "industrial", "US.UNP": "industrial", "US.ADP": "industrial",
    "US.FISV": "industrial", "US.UBER": "transport", "US.DAL": "transport",
    "US.T": "telecom", "US.VZ": "telecom", "US.TMUS": "telecom",
    "US.COIN": "crypto", "US.MSTR": "crypto",
}


def sector_of(symbol: str) -> str:
    """Coarse sector bucket; unmapped names fall into 'other'."""
    return SECTORS.get(str(symbol).upper(), "other")


# ---------------------------------------------------------------------------
# Evidence-backed factor family (v3.6.0)
#
# Sourced from the replication literature rather than from chart lore:
#   * Hou-Xue-Zhang (2020) rebuilt 452 published anomalies; only momentum,
#     profitability, investment and value survived robust re-estimation
#     (liquidity anomalies failed 95/102, mostly because equal-weighted tests
#     ride untradeable microcaps - our universe is large caps, so that trap is
#     avoided by construction).
#   * Jegadeesh-Titman (1993) / Carhart (1997): 12-1 momentum is the single
#     most replicated cross-sectional signal. Skipping the most recent month
#     is not a detail - that month carries short-term reversal, which partly
#     cancels momentum.
#   * Jegadeesh (1990) / Lehmann (1990): short-term (1-month) REVERSAL is a
#     separate documented effect: last month's losers bounce. Different from
#     our pullback-in-uptrend rule, so it gets measured on its own.
#   * Frazzini-Pedersen (2014) / Baker-Bradley-Wurgler (2011): the low-risk
#     anomaly. It was the WORST factor in 2026 YTD, so the validator decides
#     for our sample instead of the narrative.
# ---------------------------------------------------------------------------

def momentum_12_1_score(df: pd.DataFrame, lookback: int = 252,
                        skip: int = 21) -> Dict:
    """Pure 12-1 momentum: return from t-252 to t-21, skipping the last month."""
    c = _arr(df, "close")
    n = len(c)
    stats: Dict[str, float] = {"bars": n}

    if n < lookback + skip + 1:
        return {"score": 0, "reasons": ["insufficient history for 12-1"], "stats": stats}

    mom = float(c[-1 - skip] / c[-1 - lookback] - 1.0)
    stats["mom_12_1_pct"] = round(mom * 100, 1)
    reasons = [f"12-1 momentum {mom * 100:+.0f}%"]

    vol = _annualized_vol(c)
    if vol:
        stats["ann_vol_pct"] = round(vol * 100, 1)
        mom = mom / max(vol, 0.10)            # vol-scaled momentum (Sharpe-like)

    score = 50.0 + mom * 60.0
    ma200 = _ma(c, 200)
    if ma200 and c[-1] < ma200:
        score -= 15.0
        reasons.append("below MA200 (trend broken)")
    else:
        reasons.append("above MA200")

    return {"score": round(max(0.0, min(100.0, score)), 1),
            "reasons": reasons, "stats": stats}


def momentum_12_1_raw_score(df: pd.DataFrame, lookback: int = 252,
                            skip: int = 21) -> Dict:
    """Pure 12-1 momentum, NO volatility scaling. THE VALIDATED SIGNAL.

    Empirical note (228-name / ~12y cache, 21-day rebalance, 129 periods):
    this is the ONLY ranker that cleared Harvey-Liu-Zhu's t>3 bar for a new
    factor. Measured excess over SPY = +21.0%/yr, HAC t=3.35; over QQQ
    +16.3% (t=2.68); over the equal-weight pool +16.8% (t=2.83); positive in
    11 of 12 calendar years; and it survives an in-sample / out-of-sample
    split (IS +16.7%/yr t=3.00, OOS +25.2%/yr t=2.34).

    Why dividing by volatility is WRONG here: `momentum_12_1_score` scales
    the 12-1 return by realised vol ("Sharpe momentum"). On the identical
    data that variant measured t=-0.19 -- the vol term is dominated by
    names whose vol spiked for idiosyncratic reasons, so the scaling injects
    noise rather than concentrating signal. Raw return is the better ranker
    in this universe. Both are kept so the validator can keep watching.

    Construction: return from t-252 to t-21, dropping the most recent month
    because that window contains the short-term reversal effect and would
    otherwise partially cancel the momentum signal.
    """
    c = _arr(df, "close")
    n = len(c)
    stats: Dict[str, float] = {"bars": n}

    if n < lookback + skip + 1:
        return {"score": 0, "reasons": ["insufficient history for 12-1"], "stats": stats}

    mom = float(c[-1 - skip] / c[-1 - lookback] - 1.0)
    stats["mom_12_1_pct"] = round(mom * 100, 1)
    reasons = [f"12-1 momentum {mom * 100:+.0f}% (raw, unscaled)"]

    # Rank on the RAW return, clamp only for the reported 0-100 display value.
    # An earlier version clamped the ranking variable itself at 100, which in a
    # momentum bull market flattened every name above +50% 12-1 into a single
    # tie and destroyed the ordering exactly where the signal is strongest.
    # `raw` carries the ordering; `score` is a monotone display transform.
    raw = mom * 100.0
    ma200 = _ma(c, 200)
    if ma200 and c[-1] < ma200:
        raw -= 10.0
        reasons.append("below MA200 (trend broken)")
    else:
        reasons.append("above MA200")

    stats["raw_rank_score"] = round(raw, 1)
    score = max(0.0, min(100.0, 50.0 + raw))

    return {"score": round(score, 1), "raw": round(raw, 4),
            "reasons": reasons[:5], "stats": stats}
    return {"score": round(score, 1), "reasons": reasons[:5], "stats": stats}


def short_term_reversal_score(df: pd.DataFrame, lookback: int = 21) -> Dict:
    """Short-term reversal: last month's LOSERS are expected to bounce.

    Opposite sign to momentum on purpose, and measured separately - the
    cross-sectional validator decides whether it still pays in a liquid
    large-cap universe (it has weakened since the 1990s).
    """
    c = _arr(df, "close")
    n = len(c)
    stats: Dict[str, float] = {"bars": n}
    if n < lookback + 2:
        return {"score": 0, "reasons": ["insufficient history"], "stats": stats}

    ret = float(c[-1] / c[-1 - lookback] - 1.0)
    stats["ret_1m_pct"] = round(ret * 100, 1)
    score = 50.0 - ret * 250.0
    tail = "oversold bounce candidate" if ret < 0 else "already extended"
    return {"score": round(max(0.0, min(100.0, score)), 1),
            "reasons": [f"1m return {ret * 100:+.1f}% -> {tail}"], "stats": stats}


def low_vol_score(df: pd.DataFrame) -> Dict:
    """Low-risk anomaly: prefer low realised volatility and shallow drawdowns."""
    c = _arr(df, "close")
    n = len(c)
    stats: Dict[str, float] = {"bars": n}
    if n < 64:
        return {"score": 0, "reasons": ["insufficient history"], "stats": stats}

    vol = _annualized_vol(c) or 0.0
    w = c[-64:]
    mdd = float(np.min(w / np.maximum.accumulate(w) - 1.0))
    stats["ann_vol_pct"] = round(vol * 100, 1)
    stats["mdd_63d_pct"] = round(mdd * 100, 1)

    vol_part = max(0.0, min(1.0, (0.60 - vol) / 0.60)) * 60.0
    dd_part = max(0.0, min(1.0, (0.35 - abs(mdd)) / 0.35)) * 40.0
    return {"score": round(vol_part + dd_part, 1),
            "reasons": [f"vol {vol*100:.0f}%, 63d max drawdown {mdd*100:.1f}%"],
            "stats": stats}


STYLES: Dict[str, Callable[[pd.DataFrame], Dict]] = {
    "momentum": momentum_score,
    "reversal": reversal_score,
    "quality": quality_score,
    "mom_12_1": momentum_12_1_score,
    "mom_12_1_raw": momentum_12_1_raw_score,
    "st_reversal": short_term_reversal_score,
    "low_vol": low_vol_score,
}


def score_style(style: str, df: pd.DataFrame) -> Dict:
    """Public dispatch used by both the picker and the validator."""
    fn = STYLES.get(style)
    if fn is None:
        return {"score": 0.0, "reasons": [f"unknown style {style}"], "stats": {}}
    try:
        return fn(df)
    except Exception as exc:                     # never let a bad bar kill a scan
        return {"score": 0.0, "reasons": [f"error: {exc}"], "stats": {}}


def context_for_entry(df: pd.DataFrame) -> Dict:
    """Per-candidate entry context: ATR stop distance and daily returns."""
    c = _arr(df, "close")
    h = _arr(df, "high")
    l = _arr(df, "low")
    n = len(c)
    if n < 15:
        return {"error": "insufficient bars"}
    atr = _atr(h, l, c, 14) or 0.0
    returns = [float((c[i] - c[i - 1]) / c[i - 1]) for i in range(1, n) if c[i - 1] > 0]
    return {
        "close": round(float(c[-1]), 2),
        "atr": round(atr, 2) if atr else None,
        "atr_pct": round(atr / c[-1] * 100, 2) if atr and c[-1] > 0 else None,
        "returns": returns[-120:],
    }


def load_universe(path: str) -> list:
    """Load a symbol list from a JSON file {"symbols": [...]}."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        syms = data.get("symbols") if isinstance(data, dict) else data
        return [s for s in syms if isinstance(s, str) and s]
    except Exception:
        return []


if __name__ == "__main__":
    print(__doc__)
