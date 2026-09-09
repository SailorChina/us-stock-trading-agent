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
    python scripts/strategy_validator.py --symbol US.NVDA --horizon 5 --bars 500
"""
import argparse
import json
import math
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

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


def score_history(symbol: str, df, horizon: int = 5, window_bars: int = 120,
                  min_bars: int = 60, step: int = 1) -> List[Dict]:
    """Score every bar using only past data, and attach the forward return.

    Returns a list of {"date", "score", "fwd_ret"} dicts.
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
        lo = max(0, t + 1 - window_bars)
        window = df.iloc[lo:t + 1].copy()

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

        composite = (tech_score * TECH_W + enh_score * ENH_W + candle_score * CANDLE_W) / BLOCK_W
        fwd = (closes[t + horizon] - closes[t]) / closes[t] if closes[t] else 0.0

        rows.append({
            "bar": t,
            "date": str(stamps[t])[:10],
            "score": round(float(composite), 2),
            "fwd_ret": float(fwd),
            "tech": tech_score,
            "enhanced": enh_score,
            "candlestick": candle_score,
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
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--horizon", type=int, default=5, help="forward return horizon in bars")
    parser.add_argument("--bars", type=int, default=500, help="history length to fetch")
    parser.add_argument("--threshold", type=float, default=60.0, help="entry score threshold")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    report = validate_symbol(args.symbol, horizon=args.horizon,
                             bars=args.bars, threshold=args.threshold)
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
