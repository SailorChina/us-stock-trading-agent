#!/usr/bin/env python3
"""Strategy Validator — does the composite score actually predict anything?

The rest of this project produces scores, ratings and confidence numbers.
Nothing ever checked whether any of it has predictive value. This module is
the missing piece: it walks a symbol's history and, at every bar, rebuilds
the decision score using ONLY data available up to that bar, then measures
the forward N-day return.

Design rules that matter:
  * no look-ahead — each bar is scored on `df[:t+1]` only, using the pure
    `signal_from_df` rather than the network-bound `generate_signal`;
  * overlapping signals are collapsed into non-overlapping trades, otherwise
    a 5-day horizon on daily bars counts the same move five times;
  * every headline number carries its own uncertainty, because an IC of 0.08
    on 40 samples is noise, not alpha.

Usage:
    # single symbol, scored over time (few effective samples - see note below)
    python scripts/strategy_validator.py --symbol US.NVDA --horizon 5 --bars 500

    # cross-sectional: rank a universe each date (the mode that has power)
    python scripts/strategy_validator.py --mode cross --horizon 10 --bars 250 --limit 40
"""
import argparse
import json
import math
import os
import statistics
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)

# Decision-engine weights for the three factors that can be rebuilt from
# price history alone (earnings / regime / smart money are point-in-time and
# are deliberately excluded — this validates the technical block only).
TECH_W, ENH_W, CANDLE_W = 30, 20, 15
BLOCK_W = TECH_W + ENH_W + CANDLE_W


def _spearman(x: List[float], y: List[float]) -> Optional[float]:
    """Rank correlation, with a numpy fallback if scipy is unavailable."""
    if len(x) < 3:
        return None
    try:
        from scipy.stats import spearmanr
        r = spearmanr(x, y).correlation
        return None if r is None or math.isnan(r) else float(r)
    except Exception:
        import numpy as np
        rx = np.argsort(np.argsort(x)).astype(float)
        ry = np.argsort(np.argsort(y)).astype(float)
        if rx.std() == 0 or ry.std() == 0:
            return None
        return float(np.corrcoef(rx, ry)[0, 1])


def score_history(symbol: str, df, horizon: int = 5, window_bars: int = 0,
                  min_bars: int = 60, step: int = 1,
                  scorer=None) -> List[Dict]:
    """Score every bar using only past data, and attach the forward return.

    `scorer` is an optional callable(df) -> {"score": 0-100}; it lets the
    cross-sectional validator measure a *specific style* (momentum /
    reversal / quality from stock_selector) instead of the whole composite.
    Default: the historical composite of the decision engine's technical block.

    `window_bars <= 0` (the default) means "all history up to bar t". A short
    trailing window is a trap: any factor needing a long lookback (MA200,
    12-1 momentum) silently scores 0 on every bar and the IC degenerates to
    None instead of raising.
    """
    from tech_engine import signal_from_df
    from enhanced_indicators import enhanced_signal_score
    from candlestick_patterns import get_latest_patterns, pattern_score

    if df is None or len(df) < min_bars + horizon + 1:
        return []

    closes = df["close"].values
    stamps = df["time_key"].tolist() if "time_key" in df.columns else list(range(len(df)))

    rows = []
    for t in range(min_bars, len(df) - horizon, step):
        lo = 0 if window_bars <= 0 else max(0, t + 1 - window_bars)
        window = df.iloc[lo:t + 1].copy()

        if scorer is not None:
            try:
                composite = scorer(window).get("score")
            except Exception:
                continue
            if composite is None:
                continue
        else:
            try:
                tech = signal_from_df(window)
                if tech.get("status") != "ok":
                    continue
                tech_score = tech["data"]["score"]
                enh = enhanced_signal_score(window) or {}
                enh_score = enh.get("score", 50)
                pats = get_latest_patterns(window, 5) or []
                pscore = pattern_score(pats) if pats else {"score": 50, "signal": "neutral"}
                candle_score = pscore.get("score", 50)
            except Exception:
                continue
            composite = (tech_score * TECH_W + enh_score * ENH_W
                         + candle_score * CANDLE_W) / BLOCK_W
        fwd = (closes[t + horizon] - closes[t]) / closes[t] if closes[t] else 0.0

        rows.append({
            "bar": t,
            "date": str(stamps[t])[:10],
            "score": round(float(composite), 2),
            "fwd_ret": float(fwd),
        })
    return rows


def information_coefficient(rows: List[Dict]) -> Dict:
    """Spearman IC between score and forward return, with a rough 95% band."""
    n = len(rows)
    if n < 3:
        return {"ic": None, "n": n, "significant": False, "note": "too few samples"}
    ic = _spearman([r["score"] for r in rows], [r["fwd_ret"] for r in rows])
    if ic is None:
        return {"ic": None, "n": n, "significant": False, "note": "degenerate scores"}
    se = 1.0 / math.sqrt(n - 1)          # approximate SE of a correlation
    return {
        "ic": round(ic, 4),
        "n": n,
        "std_error": round(se, 4),
        "ci95": [round(ic - 1.96 * se, 4), round(ic + 1.96 * se, 4)],
        "significant": bool(abs(ic) > 1.96 * se),
    }


def bucket_returns(rows: List[Dict], buckets: int = 5) -> List[Dict]:
    """Sort bars by score into buckets; a real signal rises monotonically."""
    if len(rows) < buckets:
        return []
    ordered = sorted(rows, key=lambda r: r["score"])
    size = len(ordered) // buckets
    out = []
    for b in range(buckets):
        chunk = ordered[b * size:(b + 1) * size] if b < buckets - 1 else ordered[b * size:]
        if not chunk:
            continue
        out.append({
            "bucket": b + 1,
            "score_lo": round(chunk[0]["score"], 2),
            "score_hi": round(chunk[-1]["score"], 2),
            "n": len(chunk),
            "mean_fwd_ret_pct": round(sum(c["fwd_ret"] for c in chunk) / len(chunk) * 100, 3),
            "win_rate": round(sum(1 for c in chunk if c["fwd_ret"] > 0) / len(chunk), 3),
        })
    return out


def _max_drawdown(equity: List[float]) -> float:
    peak, mdd = equity[0], 0.0
    for v in equity:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1.0)
    return mdd


def simulate(rows: List[Dict], threshold: float = 60.0, horizon: int = 5,
             benchmark_ret: Optional[float] = None) -> Dict:
    """Threshold strategy with non-overlapping trades vs buy-and-hold.

    `benchmark_ret` is the buy-and-hold return over the same span, computed
    from the price series. It MUST NOT be derived by compounding `fwd_ret`
    over every bar: those windows overlap, so compounding them counts the
    same move several times and inflates the benchmark absurdly.
    """
    if not rows:
        return {"trades": 0}

    trades, i = [], 0
    while i < len(rows):
        if rows[i]["score"] >= threshold:
            trades.append(rows[i]["fwd_ret"])
            i += horizon          # hold, then skip — no overlapping exposure
        else:
            i += 1

    equity, e = [], 1.0
    for r in trades:
        e *= (1.0 + r)
        equity.append(e)

    strat_ret = (e - 1.0) * 100 if trades else 0.0
    bh_ret = 0.0 if benchmark_ret is None else benchmark_ret * 100
    return {
        "threshold": threshold,
        "horizon_bars": horizon,
        "trades": len(trades),
        "win_rate": round(sum(1 for t in trades if t > 0) / len(trades), 3) if trades else 0.0,
        "strategy_return_pct": round(strat_ret, 2),
        "buy_hold_return_pct": round(bh_ret, 2),
        "excess_vs_buy_hold_pct": round(strat_ret - bh_ret, 2),
        "max_drawdown_pct": round(_max_drawdown(equity) * 100, 2) if equity else 0.0,
        "exposure_bars": len(trades) * horizon,
        "bars_in_sample": len(rows),
    }


def _verdict(ic_info: Dict, buckets: List[Dict], sim: Dict) -> Dict:
    n = ic_info.get("n", 0)
    ic = ic_info.get("ic")
    if n < 30:
        return {"verdict": "insufficient_samples",
                "detail": f"only {n} scored bars — any IC here is noise"}
    if ic is None or not ic_info.get("significant"):
        return {"verdict": "no_evidence",
                "detail": (f"IC={ic} is inside the noise band "
                           f"{ic_info.get('ci95')} — no demonstrated predictive power")}
    if buckets and len(buckets) >= 2:
        spread = buckets[-1]["mean_fwd_ret_pct"] - buckets[0]["mean_fwd_ret_pct"]
    else:
        spread = 0.0
    if ic < 0:
        return {"verdict": "inverse",
                "detail": (f"IC={ic} is significantly NEGATIVE — high scores preceded "
                           f"weak returns. Trading it long would lose money.")}
    return {"verdict": "predictive" if spread > 0 else "weak",
            "detail": (f"IC={ic} significant; top-minus-bottom bucket spread "
                       f"{spread:.2f}% over the forward horizon"),
            "top_minus_bottom_pct": round(spread, 2)}


# A default cross-sectional universe — liquid US large caps across sectors.
# Cross-sectional validation needs BREADTH: one symbol scored on overlapping
# 5-day windows yields ~37 independent observations, while ranking 40 symbols
# on 25 non-overlapping dates yields ~1000 pairs and a meaningful t-statistic.
DEFAULT_UNIVERSE = [
    "US.NVDA", "US.AAPL", "US.MSFT", "US.GOOGL", "US.AMZN", "US.META",
    "US.TSLA", "US.AVGO", "US.JPM", "US.V", "US.UNH", "US.XOM", "US.LLY",
    "US.MA", "US.COST", "US.HD", "US.PG", "US.JNJ", "US.ABBV", "US.ORCL",
    "US.CRM", "US.AMD", "US.ADBE", "US.NFLX", "US.PEP", "US.KO", "US.WMT",
    "US.MRK", "US.BAC", "US.CVS", "US.INTC", "US.QCOM", "US.TXN", "US.AMGN",
    "US.HON", "US.SBUX", "US.NKE", "US.MCD", "US.GS", "US.CAT",
]


def newey_west_se(x: List[float], lags: Optional[int] = None) -> Optional[float]:
    """HAC (Newey-West) standard error of the MEAN of a series.

    IC observations are autocorrelated (adjacent periods share market regime),
    so the naive SE is far too small — which is exactly how people talk
    themselves into seeing alpha. This widens it back out.
    """
    arr = np.asarray(x, dtype=float)
    n = len(arr)
    if n < 3:
        return None
    if lags is None:
        lags = max(1, int(4 * (n / 100.0) ** (2.0 / 9.0)))
    lags = min(lags, n - 1)
    d = arr - arr.mean()
    s = float((d * d).mean())                      # gamma_0
    for l in range(1, lags + 1):
        gamma_l = float((d[l:] * d[:-l]).mean())
        s += 2.0 * (1.0 - l / (lags + 1.0)) * gamma_l
    return math.sqrt(max(s, 1e-12) / n)


def ic_stats(ics: List[float], lags: Optional[int] = None) -> Dict:
    """Mean IC with both naive and autocorrelation-robust t-statistics."""
    n = len(ics)
    if n < 3:
        return {"n_periods": n, "mean_ic": None, "std_ic": None, "icir": None,
                "se_newey_west": None, "t_stat_newey_west": None,
                "t_stat_naive": None, "significant": False,
                "note": "too few periods"}
    mean_ic = float(np.mean(ics))
    std_ic = float(np.std(ics, ddof=1))
    se_nw = newey_west_se(ics, lags)
    se_naive = std_ic / math.sqrt(n)
    t_nw = mean_ic / se_nw if se_nw else None
    return {
        "n_periods": n,
        "mean_ic": round(mean_ic, 4),
        "std_ic": round(std_ic, 4),
        "icir": round(mean_ic / std_ic, 4) if std_ic else None,
        "se_newey_west": round(se_nw, 4) if se_nw else None,
        "t_stat_newey_west": round(t_nw, 3) if t_nw is not None else None,
        "t_stat_naive": round(mean_ic / se_naive, 3) if se_naive else None,
        "significant": bool(t_nw is not None and abs(t_nw) > 1.96),
        "note": "naive SE understates risk when IC is autocorrelated",
    }


def _cross_verdict(ic: Dict, port: Dict) -> Dict:
    n = ic.get("n_periods", 0)
    if n < 12:
        return {"verdict": "insufficient_periods",
                "detail": f"only {n} rebalance periods - the IC t-stat is not meaningful yet"}
    mic = ic.get("mean_ic")
    if not ic.get("significant"):
        return {"verdict": "no_evidence",
                "detail": (f"mean IC={mic}, Newey-West t={ic.get('t_stat_newey_west')} "
                           f"- indistinguishable from zero")}
    if mic is not None and mic < 0:
        return {"verdict": "inverse",
                "detail": (f"mean IC={mic} is significantly negative - buying the "
                           f"highest-scoring names loses money")}
    return {"verdict": "predictive",
            "detail": (f"mean IC={mic} with Newey-West t={ic.get('t_stat_newey_west')}; "
                       f"top-quantile excess {port.get('excess_pct')}% vs equal-weight universe")}


def validate_events(symbols: Optional[List[str]] = None, style: str = "reversal",
                    threshold: float = 20.0, horizon: int = 10,
                    bars: int = 400, window_bars: int = 0, min_bars: int = 60,
                    limit: Optional[int] = None, fetcher=None,
                    scorer=None, min_active: int = 5) -> Dict:
    """EVENT-STUDY validation for rare-signal styles such as reversal.

    Ranking styles (momentum, quality) are validated cross-sectionally, but a
    rare-signal style cannot be: on a typical day almost every name scores 0,
    so a per-date rank correlation is degenerate. The right question is not
    "does higher score beat lower score?" but "after a signal fires, is the
    forward return better than that name's own normal days?"

    NOTE: the scoring window is ALL history up to bar t (window_bars=0), not a
    short trailing window — reversal_score requires a real MA200 to know the
    trend is intact, and a 120-bar window can never produce one, which would
    silently zero out every day.

    Per symbol: walk the history bar by bar; when score >= threshold, record
    the forward return and step over the next `horizon` bars (no overlapping
    exposure — otherwise the same move is counted repeatedly). Every other
    bar contributes to that symbol's own baseline. Per-symbol excess =
    mean(signal days) - mean(normal days), then a one-sample t-test on the
    per-symbol excesses (symbols are the independent units, so one hot name
    cannot fabricate significance).
    """
    from tech_engine import fetch_kline
    from stock_selector import STYLES, sector_of
    fetch = fetcher or fetch_kline
    score_fn = scorer if scorer is not None else STYLES.get(style)
    if score_fn is None:
        return {"status": "unknown_style", "style": style,
                "known_styles": sorted(STYLES),
                "verdict": "unknown_style", "detail": f"unknown style '{style}'"}

    syms = list(symbols or DEFAULT_UNIVERSE)
    if limit:
        syms = syms[:limit]

    per_symbol = []
    failed = []
    for sym in syms:
        try:
            df = fetch(sym, "1d", bars)
        except Exception as exc:
            failed.append(f"{sym}: {exc}")
            continue
        if df is None or len(df) < min_bars + horizon + 1:
            failed.append(f"{sym}: insufficient history")
            continue
        closes = df["close"].values
        n = len(closes)

        events, normal = [], []
        t = min_bars
        while t <= n - 1 - horizon:
            fwd = (closes[t + horizon] - closes[t]) / closes[t] if closes[t] else 0.0
            lo = 0 if window_bars <= 0 else max(0, t + 1 - window_bars)
            window = df.iloc[lo:t + 1].copy()
            try:
                hit = (score_fn(window) or {}).get("score", 0.0) >= threshold
            except Exception:
                hit = False
            if hit:
                events.append(float(fwd))
                t += horizon                      # no overlapping exposure
            else:
                normal.append(float(fwd))
                t += 1
        if events:
            base = float(np.mean(normal)) if normal else 0.0
            per_symbol.append({"symbol": sym, "sector": sector_of(sym),
                               "n_events": len(events),
                               "mean_event_ret": float(np.mean(events)),
                               "baseline_ret": base,
                               "excess": float(np.mean(events)) - base})

    report = {
        "mode": "event_study",
        "style": style,
        "threshold": threshold,
        "horizon_bars": horizon,
        "generated_at": datetime.now().isoformat(),
        "universe_size": len(syms),
        "symbols_active": len(per_symbol),
        "status": "ok",
    }
    if failed:
        report["fetch_failures"] = failed[:15]

    if len(per_symbol) < min_active:
        report["verdict"] = "insufficient_signals"
        report["detail"] = (f"only {len(per_symbol)} symbols produced >=1 signal "
                            f"in {len(syms)} (need >= {min_active}) - nothing to conclude")
        return report

    n_events = sum(p["n_events"] for p in per_symbol)
    excesses = np.asarray([p["excess"] for p in per_symbol], dtype=float)
    mean_excess = float(excesses.mean())
    se = float(excesses.std(ddof=1)) / np.sqrt(len(excesses))
    t_stat = mean_excess / se if se > 0 else None
    overall_event = float(np.mean([p["mean_event_ret"] for p in per_symbol]))
    overall_base = float(np.mean([p["baseline_ret"] for p in per_symbol]))

    # Signals cluster by sector; surface it so a single bad sector cannot hide
    # inside an acceptable-looking average.
    by_sector: Dict[str, list] = {}
    for p in per_symbol:
        by_sector.setdefault(p.get("sector", "other"), []).append(p)
    breakdown = sorted(
        [{"sector": sec, "symbols": len(items),
          "signals": int(sum(i["n_events"] for i in items)),
          "mean_excess_pct": round(float(np.mean([i["excess"] for i in items])) * 100, 2)}
         for sec, items in by_sector.items()],
        key=lambda d: d["mean_excess_pct"])
    report["sector_breakdown"] = breakdown
    if breakdown and len(breakdown) >= 2:
        report["worst_sector"] = breakdown[0]["sector"]
        report["sector_spread_pct"] = round(
            breakdown[-1]["mean_excess_pct"] - breakdown[0]["mean_excess_pct"], 2)

    report.update({
        "signals": int(n_events),
        "events_per_symbol_avg": round(n_events / len(per_symbol), 1),
        "mean_event_ret_pct": round(overall_event * 100, 3),
        "baseline_ret_pct": round(overall_base * 100, 3),
        "mean_excess_pct": round(mean_excess * 100, 3),
        "t_stat": round(t_stat, 3) if t_stat is not None else None,
        "significant": bool(t_stat is not None and abs(t_stat) > 2.0),
        "per_symbol": per_symbol,
    })

    if t_stat is None:
        verdict, detail = "degenerate", "no variance in per-symbol excess"
    elif abs(t_stat) <= 2.0:
        verdict, detail = ("no_evidence",
                           f"per-symbol excess {mean_excess*100:.2f}% "
                           f"(t={t_stat:.2f}) indistinguishable from zero")
    elif t_stat > 2.0:
        verdict, detail = ("predictive",
                           f"signal days beat that name's normal days by "
                           f"{mean_excess*100:.2f}% per {horizon}-bar hold (t={t_stat:.2f})")
    else:
        verdict, detail = ("inverse",
                           f"signal days UNDERperform normal days by "
                           f"{abs(mean_excess)*100:.2f}% per {horizon}-bar hold (t={t_stat:.2f})")
    report["verdict"] = verdict
    report["detail"] = detail
    return report


def validate_cross_section(symbols: Optional[List[str]] = None, horizon: int = 10,
                           bars: int = 250, quantile: float = 0.2,
                           window_bars: int = 0, min_names: int = 10,
                           limit: Optional[int] = None,
                           fetcher=None, style: str = "composite") -> Dict:
    """Cross-sectional validation: rank many symbols per date, not one over time.

    This is the cure for the sample-size problem in `validate_symbol`. Each
    rebalance date contributes one IC observation computed across the whole
    universe, and rebalances are spaced `horizon` bars apart so forward
    windows never overlap.

    `style` selects WHICH ranker is being validated: "composite" (the decision
    engine's technical block) or a daily_pick style ("momentum" / "reversal" /
    "quality"). The live picker and the validator share the exact same scoring
    function, so a factor cannot be added to the scan without being measured.
    """
    from tech_engine import fetch_kline
    fetch = fetcher or fetch_kline

    scorer = None
    if style != "composite":
        from stock_selector import STYLES
        scorer = STYLES.get(style)
        if scorer is None:
            return {"status": "unknown_style", "style": style,
                    "known_styles": sorted(STYLES),
                    "verdict": "unknown_style",
                    "detail": f"unknown style '{style}'"}

    syms = list(symbols or DEFAULT_UNIVERSE)
    if limit:
        syms = syms[:limit]

    report = {
        "mode": "cross_sectional",
        "style": style,
        "generated_at": datetime.now().isoformat(),
        "horizon_bars": horizon,
        "requested_bars": bars,
        "universe_size": len(syms),
        "top_quantile": quantile,
        "status": "ok",
    }

    per_symbol, failed = {}, []
    for sym in syms:
        try:
            df = fetch(sym, "1d", bars)
        except Exception as e:
            failed.append(f"{sym}: {e}")
            continue
        if df is None or len(df) < 80:
            failed.append(f"{sym}: insufficient history")
            continue
        rows = score_history(sym, df, horizon=horizon, step=horizon,
                             window_bars=window_bars, scorer=scorer)
        if rows:
            per_symbol[sym] = {r["date"]: r for r in rows}

    if len(per_symbol) < 2:
        report["status"] = "insufficient_universe"
        report["symbols_with_data"] = len(per_symbol)
        report["fetch_failures"] = failed[:20]
        report["verdict"] = "insufficient_universe"
        report["detail"] = "cross-sectional ranking needs at least 2 symbols with history"
        return report

    counts: Dict[str, int] = {}
    for m in per_symbol.values():
        for d in m:
            counts[d] = counts.get(d, 0) + 1
    dates = sorted(d for d, c in counts.items() if c >= min_names)

    periods, top_rets, uni_rets = [], [], []
    for d in dates:
        pairs = [(m[d]["score"], m[d]["fwd_ret"]) for m in per_symbol.values() if d in m]
        if len(pairs) < min_names:
            continue
        periods.append({"date": d, "n": len(pairs),
                        "ic": _spearman([p[0] for p in pairs], [p[1] for p in pairs])})

        ranked = sorted(pairs, key=lambda p: p[0], reverse=True)
        n_top = max(1, int(round(len(ranked) * quantile)))
        top_rets.append(float(np.mean([r for _, r in ranked[:n_top]])))
        uni_rets.append(float(np.mean([r for _, r in pairs])))

    if len(periods) < 3:
        report["status"] = "insufficient_periods"
        report["periods"] = len(periods)
        report["verdict"] = "insufficient_periods"
        report["detail"] = f"only {len(periods)} rebalance periods - nothing to conclude"
        return report

    stats = ic_stats([p["ic"] for p in periods if p["ic"] is not None])
    avg_n = float(np.mean([p["n"] for p in periods]))

    equity, e, uni = [], 1.0, 1.0
    for r in top_rets:
        e *= (1.0 + r)
        equity.append(e)
    for r in uni_rets:
        uni *= (1.0 + r)
    top_total, uni_total = (e - 1.0) * 100, (uni - 1.0) * 100

    port = {
        "top_quantile": quantile,
        "avg_names_held": max(1, int(round(avg_n * quantile))),
        "return_pct": round(top_total, 2),
        "universe_return_pct": round(uni_total, 2),
        "excess_pct": round(top_total - uni_total, 2),
        "win_rate_vs_universe": round(
            sum(1 for a, b in zip(top_rets, uni_rets) if a > b) / len(top_rets), 3),
        "max_drawdown_pct": round(_max_drawdown(equity) * 100, 2) if equity else 0.0,
    }

    report.update({
        "symbols_with_data": len(per_symbol),
        "periods": len(periods),
        "avg_names_per_period": round(avg_n, 1),
        "cross_sectional_pairs": int(sum(p["n"] for p in periods)),
        "information_coefficient": stats,
        "portfolio": port,
    })
    report.update(_cross_verdict(stats, port))
    if failed:
        report["fetch_failures"] = failed[:20]
    return report


def validate_symbol(symbol: str, horizon: int = 5, bars: int = 500,
                    threshold: float = 60.0, window_bars: int = 120) -> Dict:
    """Full walk-forward validation for one symbol."""
    from tech_engine import fetch_kline

    report = {
        "symbol": symbol,
        "generated_at": datetime.now().isoformat(),
        "horizon_bars": horizon,
        "requested_bars": bars,
        "status": "ok",
    }

    df = fetch_kline(symbol, "1d", bars)
    if df is None or len(df) < 80:
        report["status"] = "insufficient_data"
        report["error"] = f"need >=80 bars, got {len(df) if df is not None else 0}"
        return report

    rows = score_history(symbol, df, horizon=horizon, window_bars=window_bars)
    if len(rows) < 10:
        report["status"] = "insufficient_samples"
        report["scored_bars"] = len(rows)
        return report

    ic_info = information_coefficient(rows)
    buckets = bucket_returns(rows)

    # Buy-and-hold over the same span, straight from the price series.
    closes = df["close"].values
    first_bar = rows[0]["bar"]
    benchmark = float(closes[-1] / closes[first_bar] - 1.0) if closes[first_bar] else 0.0

    sim = simulate(rows, threshold=threshold, horizon=horizon, benchmark_ret=benchmark)

    means = [b["mean_fwd_ret_pct"] for b in buckets]
    monotonic = all(means[i] <= means[i + 1] for i in range(len(means) - 1)) if means else False

    report.update({
        "scored_bars": len(rows),
        "score_range": [min(r["score"] for r in rows), max(r["score"] for r in rows)],
        "mean_fwd_ret_pct": round(sum(r["fwd_ret"] for r in rows) / len(rows) * 100, 3),
        "information_coefficient": ic_info,
        "buckets": buckets,
        "bucket_monotonic": monotonic,
        "bucket_spread_pct": round(means[-1] - means[0], 2) if len(means) >= 2 else 0.0,
        "benchmark_buy_hold_pct": round(benchmark * 100, 2),
        "simulation": sim,
    })
    report.update(_verdict(ic_info, buckets, sim))
    return report


def main():
    parser = argparse.ArgumentParser(description="Strategy Validator")
    parser.add_argument("--mode", default="single", choices=["single", "cross", "events"],
                        help="single/cross rank a universe; events = event study for rare-signal styles")
    parser.add_argument("--symbol", default="US.NVDA")
    parser.add_argument("--symbols", default=None,
                        help="comma separated universe for --mode cross")
    parser.add_argument("--limit", type=int, default=None, help="cap the universe size")
    parser.add_argument("--horizon", type=int, default=5, help="forward return horizon in bars")
    parser.add_argument("--bars", type=int, default=500, help="history length to fetch")
    parser.add_argument("--threshold", type=float, default=None,
                        help="entry score threshold (single: 60; events: 20 by default)")
    parser.add_argument("--quantile", type=float, default=0.2, help="top quantile to hold")
    parser.add_argument("--style", default="composite",
                        help="ranker to validate: composite|momentum|reversal|quality")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    if args.mode == "cross":
        syms = [s.strip() for s in args.symbols.split(",")] if args.symbols else None
        report = validate_cross_section(syms, horizon=max(2, args.horizon),
                                        bars=args.bars, quantile=args.quantile,
                                        limit=args.limit, style=args.style)
    elif args.mode == "events":
        syms = [s.strip() for s in args.symbols.split(",")] if args.symbols else None
        report = validate_events(syms, style=args.style,
                                 threshold=20.0 if args.threshold is None else args.threshold,
                                 horizon=max(2, args.horizon), bars=args.bars,
                                 limit=args.limit)
    else:
        report = validate_symbol(args.symbol, horizon=args.horizon,
                                 bars=args.bars,
                                 threshold=60.0 if args.threshold is None else args.threshold)
    out = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"Saved: {args.output}", file=sys.stderr)
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
