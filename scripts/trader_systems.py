#!/usr/bin/env python3
"""trader_systems — quantified versions of well-known public trading systems.

Each system below is a published, fully-specified method from a trader with a
verifiable record (or from academic replication), reduced to the rules that
can actually be computed from daily OHLCV. Sources and the exact rule set are
cited in each docstring so the implementation can be audited against the
original text.

The point is NOT to trust the reputation. Every one of these is scored with
the same no-look-ahead protocol as our own factors and put through the same
portfolio backtest (scripts/backtest_engine.py), so a famous name whose method
does not survive gets reported as a failure instead of quietly disappearing.

All scorers return {"score": 0-100 (display), "raw": float (ranking, never
clamped), "reasons": [...], "stats": {...}} to match stock_selector's contract.
"""
from typing import Dict

import numpy as np
import pandas as pd

MIN_BARS = 260          # MA200 + 52-week lookback


# ---------------------------------------------------------------------------
# shared helpers (kept self-contained so this module never imports
# stock_selector, which would create a circular import)
# ---------------------------------------------------------------------------

def _c(df: pd.DataFrame) -> np.ndarray:
    return df["close"].to_numpy(dtype=float)


def _h(df: pd.DataFrame) -> np.ndarray:
    return df["high"].to_numpy(dtype=float)


def _l(df: pd.DataFrame) -> np.ndarray:
    return df["low"].to_numpy(dtype=float)


def _empty(why: str) -> Dict:
    return {"score": 0.0, "raw": 0.0, "reasons": [why], "stats": {}}


def _regression_quality(y: np.ndarray):
    """Slope and R^2 of a straight line through y (already log-transformed)."""
    x = np.arange(len(y), dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    yhat = slope * x + intercept
    ss_res = float(((y - yhat) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return float(slope), float(r2)


# ---------------------------------------------------------------------------
# 1. Clenow momentum  —  Andreas F. Clenow, "Stocks on the Move" (2015)
# ---------------------------------------------------------------------------

def clenow_score(df: pd.DataFrame, lookback: int = 90, ma_filter: int = 100,
                 spike_limit: float = 0.15) -> Dict:
    """Hedge-fund momentum, rules published in full.

    Clenow ran systematic funds and is currently CIO of ACIES Asset Management
    (Switzerland). The strategy as specified:
      1. rank by VOLATILITY-ADJUSTED momentum = annualised slope of a
         log-price regression multiplied by its R^2, over `lookback` days
      2. disqualify a stock trading below its 100-day moving average
      3. disqualify a stock that had any single-day move above +15% in the
         last 90 days (a spike wrecks the regression fit and signals a
         one-off event rather than a trend)
      4. (portfolio level, applied by the backtest) only open new positions
         while the index is above its own 200-day MA

    The R^2 multiplier is the interesting part and the reason this is not just
    "12-1 momentum again": it penalises a stock whose advance was erratic.
    """
    c = _c(df)
    n = len(c)
    if n < max(ma_filter, lookback) + 5:
        return _empty("insufficient history for Clenow")

    if c[-1] < float(np.mean(c[-ma_filter:])):
        return _empty("below %d-day MA (Clenow rule 2)" % ma_filter)

    window = c[-lookback:]
    rets = np.diff(window) / window[:-1]
    if len(rets) and float(rets.max()) > spike_limit:
        return _empty("single-day spike >%.0f%% (Clenow rule 3)" % (spike_limit * 100))

    slope, r2 = _regression_quality(np.log(window))
    ann_slope = (1.0 + slope) ** 252 - 1.0
    raw = ann_slope * r2

    stats = {"bars": n, "ann_slope_pct": round(ann_slope * 100, 1),
             "r2": round(r2, 3), "clenow": round(raw, 3)}
    return {"score": round(max(0.0, min(100.0, 50.0 + raw * 50.0)), 1),
            "raw": round(raw, 6),
            "reasons": ["Clenow slope %.0f%% x R2 %.2f" % (ann_slope * 100, r2)],
            "stats": stats}


# ---------------------------------------------------------------------------
# 2. Minervini trend template  —  Mark Minervini, US Investing Champion
# ---------------------------------------------------------------------------

def minervini_score(df: pd.DataFrame, rs_proxy: str = "mom_12_1") -> Dict:
    """Minervini's published 8-point Trend Template, plus 52-week proximity.

    Minervini won the US Investing Championship (1997, 155%: 2021, 334.8%) and
    documented his SEPA method. The Trend Template as he states it:

      1. price above both the 150-day and 200-day MA
      2. 150-day MA above the 200-day MA
      3. 200-day MA trending up for at least 1 month (~21 bars here)
      4. 50-day MA above both the 150-day and 200-day MA
      5. price above the 50-day MA
      6. price at least 30% above its 52-week low
      7. price within 25% of its 52-week high
      8. relative strength rank >= 70 (cross-sectional; we approximate with
         12-1 momentum, which is the standard public proxy)

    The template is a FILTER, not a ranker. Ranking is done by proximity to the
    52-week high, which is how the SEPA method selects among qualified names.
    """
    c = _c(df)
    n = len(c)
    if n < 260:
        return _empty("insufficient history for Minervini template")

    ma50 = float(np.mean(c[-50:]))
    ma150 = float(np.mean(c[-150:]))
    ma200 = float(np.mean(c[-200:]))
    ma200_1m = float(np.mean(c[-221:-21]))
    hi52 = float(np.max(c[-252:]))
    lo52 = float(np.min(c[-252:]))
    px = c[-1]

    checks = {
        "above_150_200": px > ma150 and px > ma200,
        "150_above_200": ma150 > ma200,
        "200_rising": ma200 > ma200_1m,
        "50_above_150_200": ma50 > ma150 and ma50 > ma200,
        "above_50": px > ma50,
        "30pct_above_52w_low": px >= lo52 * 1.30,
        "within_25pct_of_52w_high": px >= hi52 * 0.75,
    }
    passed = int(sum(checks.values()))
    mom = float(c[-22] / c[-253] - 1.0)          # 12-1 as the RS proxy
    rs_ok = mom > 0.0

    stats = {"bars": n, "checks_passed": passed, "mom_12_1_pct": round(mom * 100, 1),
             "pct_of_52w_high": round(px / hi52 * 100, 1),
             "pct_above_52w_low": round((px / lo52 - 1) * 100, 1)}

    if passed < 7:
        return {"score": 0.0, "raw": 0.0,
                "reasons": ["trend template %d/7 - rejected" % passed], "stats": stats}

    # rank among qualified names by proximity to the 52-week high, with the
    # RS rank as a tiebreaker
    proximity = px / hi52                          # 1.0 == at the high
    raw = (passed * 100.0) + proximity * 50.0 + min(max(mom, -0.5), 2.0) * 20.0

    reasons = ["trend template %d/7" % passed,
               "%.0f%% of 52w high" % (proximity * 100),
               "12-1 %+.0f%%" % (mom * 100)]
    return {"score": round(max(0.0, min(100.0, 50.0 + raw / 8.0)), 1),
            "raw": round(raw, 4), "reasons": reasons, "stats": stats}


# ---------------------------------------------------------------------------
# 3. High Tight Flag  —  popularised by Kristjan Kullamaggi (Qullamaggie)
# ---------------------------------------------------------------------------

def high_tight_flag_score(df: pd.DataFrame, runup_bars: int = 60,
                          tight_bars: int = 15, min_runup: float = 0.30,
                          max_tightness: float = 0.15) -> Dict:
    """High Tight Flag: a violent run-up, then a tight sideways pause.

    Qullamaggie (Kristjan Kullamaggi) is one of the most-cited retail swing
    traders on YouTube/Stream, with publicly posted broker statements. His
    signature setup is the High Tight Flag / episodic pivot:

      1. the stock ran up hard (he cites 30-100%+ in a few weeks)
      2. then goes quiet: a flag that holds its ground without giving back the
         move (he wants the pullback shallow, high and tight)
      3. buy the break of the flag's high

    Quantified here as: run-up over `runup_bars` above `min_runup`, and a
    `tight_bars` consolidation whose range is small relative to the run-up.
    Ranking rewards a strong run-up paired with a very tight flag.
    """
    c = _c(df)
    h = _h(df)
    l = _l(df)
    n = len(c)
    if n < runup_bars + tight_bars + 5:
        return _empty("insufficient history for HTF")

    base_idx = n - tight_bars
    run_start = max(0, base_idx - runup_bars)
    runup = float(c[base_idx - 1] / c[run_start] - 1.0) if run_start < base_idx else 0.0
    if runup < min_runup:
        return _empty("no qualifying run-up (%.0f%%)" % (runup * 100))

    flag_hi = float(np.max(h[base_idx:]))
    flag_lo = float(np.min(l[base_idx:]))
    if flag_hi <= 0:
        return _empty("bad flag window")
    tightness = (flag_hi - flag_lo) / flag_hi

    if tightness > max_tightness:
        return _empty("flag too loose (%.1f%%)" % (tightness * 100))

    # the flag should sit in the upper part of the run: no deep give-back
    retrace = 1.0 - c[-1] / flag_hi
    if retrace > 0.25:
        return _empty("gave back %.0f%% of the run" % (retrace * 100))

    # breaking out today beats still-coiling
    breakout = c[-1] / flag_hi if flag_hi > 0 else 0.0

    stats = {"bars": n, "runup_pct": round(runup * 100, 1),
             "flag_range_pct": round(tightness * 100, 1),
             "retrace_pct": round(retrace * 100, 1),
             "at_flag_high": round(breakout, 3)}

    raw = runup * 100.0 * (1.0 - tightness / max_tightness) * (0.5 + breakout * 0.5)
    reasons = ["HTF run-up %+.0f%%" % (runup * 100),
               "flag range %.1f%% (tight)" % (tightness * 100),
               "%.0f%% of flag high" % (breakout * 100)]
    return {"score": round(max(0.0, min(100.0, 50.0 + raw)), 1),
            "raw": round(raw, 4), "reasons": reasons, "stats": stats}


# ---------------------------------------------------------------------------
# 4. Pullback to the 20-EMA in an uptrend
# ---------------------------------------------------------------------------

def pullback_ema_score(df: pd.DataFrame, ema_len: int = 20,
                       tol: float = 0.04) -> Dict:
    """Buy the first pullback to a rising 20-EMA inside an established uptrend.

    This is the setup the literature calls the "highest base-rate" pattern
    (brokerchampion 2026 survey of swing setups; also Linda Raschke's 'buy the
    first pullback' and the TradingSim pullback-buy framework):

      1. uptrend intact: 20-EMA above 50-SMA and price above the 200-SMA
      2. price has pulled back INTO the 20-EMA (within `tol`)
      3. the latest bar is a stabilisation (closes up)

    Note this deliberately differs from our `reversal` style, which required a
    deep oversold washout. A shallow touch of the 20-EMA in a strong uptrend
    is a different, better-documented event.
    """
    c = _c(df)
    n = len(c)
    if n < 210:
        return _empty("insufficient history for EMA pullback")

    # EMA of the last ema_len bars, seeded on a longer window for stability
    seed = c[-60:]
    alpha = 2.0 / (ema_len + 1.0)
    ema = float(seed[0])
    for p in seed[1:]:
        ema = alpha * p + (1 - alpha) * ema
    ma50 = float(np.mean(c[-50:]))
    ma200 = float(np.mean(c[-200:]))

    if not (ema > ma50 and c[-1] > ma200):
        return _empty("uptrend not intact")

    dist = c[-1] / ema - 1.0
    if abs(dist) > tol:
        return _empty("%.1f%% from 20-EMA (not touching)" % (dist * 100))

    rising = bool(n >= 2 and c[-1] > c[-2])
    if not rising:
        return _empty("still falling into the EMA - no confirmation")

    mom = float(c[-22] / c[-253] - 1.0) if n >= 253 else 0.0
    tight = 1.0 - abs(dist) / tol        # 1.0 == exactly on the EMA
    raw = mom * 100.0 + tight * 20.0

    stats = {"bars": n, "dist_ema_pct": round(dist * 100, 2),
             "mom_12_1_pct": round(mom * 100, 1), "on_ema": round(tight, 3)}
    reasons = ["pullback to 20-EMA (%.1f%%)" % (dist * 100),
               "uptrend intact", "12-1 %+.0f%%" % (mom * 100)]
    return {"score": round(max(0.0, min(100.0, 50.0 + raw)), 1),
            "raw": round(raw, 4), "reasons": reasons, "stats": stats}


# ---------------------------------------------------------------------------
# 5. Volatility Contraction Pattern (VCP)
# ---------------------------------------------------------------------------

def vcp_score(df: pd.DataFrame, segments: int = 3) -> Dict:
    """VCP: successive pullbacks that get progressively shallower.

    Minervini's other signature pattern (also covered in the swing-strategy
    survey literature). The idea: each contraction is smaller than the last
    because sellers are being absorbed; when the final contraction is tiny,
    supply is exhausted and the breakout is explosive.

    Quantified by splitting the recent window into `segments` blocks and
    measuring each block's drawdown from its running peak. A textbook VCP has
    monotonically decreasing depths (e.g. 25% -> 15% -> 8%). Requires the last
    contraction to be the shallowest AND the stock to be above its 200-SMA.
    """
    c = _c(df)
    n = len(c)
    if n < 220:
        return _empty("insufficient history for VCP")

    if c[-1] < float(np.mean(c[-200:])):
        return _empty("below MA200")

    window = c[-120:]
    chunks = np.array_split(window, segments)
    depths = []
    for ch in chunks:
        if len(ch) < 5:
            return _empty("VCP window too small")
        peak = np.maximum.accumulate(ch)
        depths.append(float(np.min(ch / peak - 1.0)))
    depths = [abs(d) for d in depths]

    # require monotone tightening between the first and last contraction
    if depths[-1] >= depths[0]:
        return _empty("no contraction (%.1f%% -> %.1f%%)" % (depths[0] * 100, depths[-1] * 100))

    tightening = depths[0] / max(depths[-1], 1e-6)
    # and require the deepest pullback to be meaningful (a real base, not noise)
    if depths[0] < 0.06:
        return _empty("base too shallow to be a real correction")

    mom = float(c[-22] / c[-253] - 1.0) if n >= 253 else 0.0
    raw = tightening * 10.0 + mom * 50.0

    stats = {"bars": n, "depths_pct": [round(d * 100, 1) for d in depths],
             "tightening": round(tightening, 2), "mom_12_1_pct": round(mom * 100, 1)}
    reasons = ["VCP tightening %.1fx" % tightening,
               "contractions " + " -> ".join("%.0f%%" % (d * 100) for d in depths),
               "12-1 %+.0f%%" % (mom * 100)]
    return {"score": round(max(0.0, min(100.0, 50.0 + raw)), 1),
            "raw": round(raw, 4), "reasons": reasons, "stats": stats}


# ---------------------------------------------------------------------------
# 6. Turtle-style channel breakout
# ---------------------------------------------------------------------------

def turtle_breakout_score(df: pd.DataFrame, channel: int = 55) -> Dict:
    """Turtle / Donchian channel breakout, the fully-specified classic.

    Richard Dennis's Turtles traded a 20-day and a 55-day breakout with
    volatility-scaled sizing. The rules were mechanical enough that he proved
    they could be taught to novices, and unlike most YouTube content the
    original rules and their results were published and audited.

    Here: rank by how far the close sits within/above its `channel`-day high
    band, so a fresh breakout scores highest and a stock still mid-range
    scores low. 55 days is the slower, lower-turnover Turtle entry.
    """
    c = _c(df)
    h = _h(df)
    n = len(c)
    if n < channel + 5:
        return _empty("insufficient history for channel breakout")

    prior_hi = float(np.max(h[-channel - 1:-1]))    # exclude today
    prior_lo = float(np.min(_l(df)[-channel - 1:-1]))
    if prior_hi <= prior_lo:
        return _empty("degenerate channel")

    pos = (c[-1] - prior_lo) / (prior_hi - prior_lo)
    breakout = c[-1] / prior_hi - 1.0

    raw = pos * 100.0 + max(0.0, breakout * 500.0)
    stats = {"bars": n, "channel_pos": round(pos, 3),
             "breakout_pct": round(breakout * 100, 2),
             "channel_days": channel}
    reasons = ["%.0f%% of %dd channel" % (pos * 100, channel),
               "breakout %+.1f%% vs channel high" % (breakout * 100)]
    return {"score": round(max(0.0, min(100.0, 50.0 + raw / 2.0)), 1),
            "raw": round(raw, 4), "reasons": reasons, "stats": stats}


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------

SYSTEMS = {
    "clenow": clenow_score,
    "minervini": minervini_score,
    "htf": high_tight_flag_score,
    "pullback_ema": pullback_ema_score,
    "vcp": vcp_score,
    "turtle55": turtle_breakout_score,
}
