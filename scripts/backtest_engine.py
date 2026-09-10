"""Offline portfolio backtest over the cached long history.

Why this exists: rank IC measures whether the ranking is directionally right,
but it understates tail-concentrated factors and says nothing about what a
trader actually earns. This module answers the only question that matters for
the product -- "if I buy the top-N names every rebalance and pay costs, what
do I get?" -- with annualised return, max drawdown, hit rate, turnover, and a
bootstrap p-value against the equal-weight universe.

Everything reads from data/_hist_cache/*.csv, so it runs in seconds offline.
"""
from __future__ import annotations

import glob
import math
import os
import random
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from strategy_validator import score_history, newey_west_se, _max_drawdown

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, "data", "_hist_cache")

# One-way trading cost assumption. US large caps: commission ~0 spread for
# liquid names, but slippage + market impact on a rebalance is real. 8 bps
# one-way (16 bps round trip) is a conservative middle for a retail/systematic
# book trading liquid large/mid caps.
COST_BPS_ONE_WAY = 8.0

# Bars per year for daily US equity data.
BARS_PER_YEAR = 252


def load_cache() -> Dict[str, pd.DataFrame]:
    """Load every cached symbol into memory once."""
    data = {}
    for f in glob.glob(os.path.join(CACHE_DIR, "*.csv")):
        sym = os.path.basename(f)[:-4].replace("_", ".")
        try:
            df = pd.read_csv(f)
        except Exception:
            continue
        if df is None or len(df) < 300:
            continue
        data[sym] = df.sort_values("time_key").reset_index(drop=True)
    return data


def cached_fetcher(cache: Dict[str, pd.DataFrame]) -> Callable:
    """Return a fetcher(symbol, ktype, num) that serves from the local cache."""
    def _fetch(symbol, ktype="1d", num=3000, *a, **kw):
        df = cache.get(symbol)
        if df is None:
            return None
        return df.tail(int(num)).reset_index(drop=True) if num else df
    return _fetch


def _spread(x: List[float]) -> float:
    if not x:
        return 0.0
    return float(max(x) - min(x))


def _pearson(x: List[float], y: List[float]) -> Optional[float]:
    if len(x) < 3:
        return None
    mx, my = sum(x) / len(x), sum(y) / len(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx <= 0 or syy <= 0:
        return None
    return float(sxy / math.sqrt(sxx * syy))


def _stats_from_series(rets: List[float], horizon: int) -> Dict:
    """Annualised stats from a list of per-rebalance portfolio returns."""
    if not rets:
        return {}
    arr = np.array(rets, dtype=float)
    n = len(arr)
    eq = np.cumprod(1.0 + arr)
    total = float(eq[-1] - 1.0) * 100
    periods_per_year = BARS_PER_YEAR / max(1, horizon)
    years = n / periods_per_year
    cagr = ((eq[-1]) ** (1.0 / years) - 1.0) * 100 if years > 0 and eq[-1] > 0 else float("nan")
    vol = float(arr.std(ddof=1)) * math.sqrt(periods_per_year) * 100 if n > 1 else 0.0
    mean_per = float(arr.mean())
    sharpe = (mean_per * periods_per_year) / (arr.std(ddof=1) * math.sqrt(periods_per_year)) if n > 1 and arr.std(ddof=1) > 0 else float("nan")
    equity_curve = [1.0] + list(eq)
    mdd = _max_drawdown(equity_curve) * 100
    win = float((arr > 0).mean())
    return {
        "periods": n,
        "total_return_pct": round(total, 1),
        "cagr_pct": round(cagr, 1) if cagr == cagr else None,
        "ann_vol_pct": round(vol, 1),
        "sharpe": round(sharpe, 2) if sharpe == sharpe else None,
        "max_drawdown_pct": round(mdd, 1),
        "hit_rate": round(win, 3),
        "best_period_pct": round(float(arr.max()) * 100, 1),
        "worst_period_pct": round(float(arr.min()) * 100, 1),
    }


def _block_bootstrap_p(port: List[float], bench: List[float], n_iter: int = 2000,
                       block: int = 3) -> Optional[float]:
    """Centered block-bootstrap p-value for "mean excess <= 0".

    Method: form the paired excess series d = port - bench. Under the null
    that the strategy has no edge, the expected excess is zero, so resample
    the CENTERED series (d - mean(d)) with a circular block bootstrap, then
    measure how often the resampled mean reaches the observed mean. If the
    edge is real, the centered resamples cluster near zero and rarely get
    there; if it is noise, they reach it about half the time.

    Centering is essential: resampling the RAW excess series preserves its
    mean by construction, so an uncentered version returns p~=0.5 for every
    series with a positive mean and can never detect anything. (An earlier
    version of this function made exactly that mistake.)

    Block length 3 keeps short-run serial correlation that an i.i.d. shuffle
    would destroy. Chosen over the HAC t as a secondary check because it makes
    no distributional assumption, but the HAC t remains primary: momentum-type
    factors carry long positive autocorrelation that no short block captures.
    """
    if len(port) < 5 or len(port) != len(bench):
        return None
    diff = np.array(port) - np.array(bench)
    obs = float(diff.mean())
    n = len(diff)
    centered = diff - obs          # null world: the edge (obs) is removed
    rng = random.Random(12345)
    count = 0
    for _ in range(n_iter):
        # circular block resample of the CENTERED series
        idx = []
        while len(idx) < n:
            start = rng.randrange(n)
            for k in range(block):
                idx.append((start + k) % n)
        sample = centered[idx[:n]]
        if float(sample.mean()) >= obs:
            count += 1
    return round(count / n_iter, 4)


def backtest_style(style: str, cache: Dict[str, pd.DataFrame], horizon: int = 21,
                   top_n: int = 10, min_names: int = 30,
                   cost_bps: float = COST_BPS_ONE_WAY,
                   top_quantile: Optional[float] = None,
                   index_members: Optional[Dict[str, List[str]]] = None,
                   scorer: Optional[Callable] = None,
                   gate: Optional[Callable] = None) -> Dict:
    """Buy the top-N ranked names every `horizon` bars; measure what a trader gets.

    Unlike rank IC, this reports the *tradeable* outcome: annualised return,
    Sharpe, max drawdown, hit rate, turnover (and the cost drag it implies),
    all versus an equal-weight hold of the same universe.

    `index_members` (date -> [symbols]) applies point-in-time membership when
    supplied, which removes survivorship/look-ahead contamination.

    `scorer` lets a caller pass a ranker directly (e.g. one from
    trader_systems.py) without registering it in stock_selector.STYLES.

    `gate` is an optional callable(date) -> bool. When it returns False the
    portfolio sits in cash for that period (0% return) while the benchmark
    keeps running. This is how a portfolio-level market filter -- such as
    Clenow's "only open new positions while the index is above its 200-day
    MA" -- gets evaluated, since it is a switch on the whole book rather than
    a per-stock score.
    """
    if scorer is None:
        from stock_selector import STYLES
        scorer = None if style == "composite" else STYLES.get(style)
        if style != "composite" and scorer is None:
            return {"status": "unknown_style", "style": style, "known": sorted(STYLES)}

    fetched = cached_fetcher(cache)
    per_symbol: Dict[str, Dict] = {}
    for sym in cache:
        try:
            rows = score_history(sym, cache[sym], horizon=horizon, step=horizon,
                                 window_bars=0, scorer=scorer)
        except Exception:
            continue
        if rows:
            per_symbol[sym] = {r["date"]: r for r in rows}

    counts: Dict[str, int] = {}
    for m in per_symbol.values():
        for d in m:
            counts[d] = counts.get(d, 0) + 1
    dates = sorted(d for d, c in counts.items() if c >= min_names)
    if len(dates) < 6:
        return {"status": "insufficient_periods", "style": style, "periods": len(dates)}

    port_rets, bench_rets, ics = [], [], []
    prev_hold: set = set()
    turnovers = []
    holding_sizes = []

    for d in dates:
        members = None
        if index_members is not None:
            members = index_members.get(d)
        pairs = []
        for sym, m in per_symbol.items():
            if d not in m:
                continue
            if members is not None and sym not in members:
                continue
            pairs.append((sym, m[d]["score"], m[d]["fwd_ret"]))
        if len(pairs) < min_names:
            continue

        bench = float(np.mean([p[2] for p in pairs]))

        # market filter: when risk-off, hold cash for the period and drop the
        # book, so the next rebalance pays full re-entry turnover
        if gate is not None and not gate(d):
            port_rets.append(0.0)
            bench_rets.append(bench)
            turnovers.append(0.0)
            holding_sizes.append(0)
            ics.append(None)
            prev_hold = set()
            continue

        # rank IC
        from strategy_validator import _spearman
        ic = _spearman([p[1] for p in pairs], [p[2] for p in pairs])
        ics.append(ic)

        ranked = sorted(pairs, key=lambda p: p[1], reverse=True)
        if top_quantile is not None:
            k = max(1, int(round(len(ranked) * top_quantile)))
        else:
            k = min(top_n, len(ranked))
        held = ranked[:k]
        hold_syms = {h[0] for h in held}
        holding_sizes.append(len(hold_syms))

        gross = float(np.mean([h[2] for h in held]))
        bench = float(np.mean([p[2] for p in pairs]))
        # turnover: fraction of names swapped vs previous holding
        if prev_hold:
            turn = len(hold_syms - prev_hold) / max(1, len(hold_syms))
        else:
            turn = 1.0
        turnovers.append(turn)
        cost = turn * (cost_bps / 10000.0) * 2  # round trip on the swapped fraction
        port_rets.append(gross - cost)
        bench_rets.append(bench)
        prev_hold = hold_syms

    if len(port_rets) < 6:
        return {"status": "insufficient_periods", "style": style, "periods": len(port_rets)}

    p_stats = _stats_from_series(port_rets, horizon)
    b_stats = _stats_from_series(bench_rets, horizon)
    gross_stats = _stats_from_series(
        [pr + t * (cost_bps / 10000.0) * 2 for pr, t in zip(port_rets, turnovers)], horizon)

    excess = [a - b for a, b in zip(port_rets, bench_rets)]
    nw = newey_west_se(excess)
    mean_ex = float(np.mean(excess)) * 100
    t_ex = (mean_ex / (nw * 100)) if nw and nw > 0 else None
    p_boot = _block_bootstrap_p(port_rets, bench_rets)

    ic_mean = float(np.mean([i for i in ics if i is not None])) if any(i is not None for i in ics) else None

    return {
        "status": "ok",
        "style": style,
        "horizon_bars": horizon,
        "top_n": top_n if top_quantile is None else f"{top_quantile:.0%}",
        "rebalances": len(port_rets),
        "universe_size": len(cache),
        "avg_names_held": round(float(np.mean(holding_sizes)), 1),
        "avg_turnover": round(float(np.mean(turnovers)), 3),
        "cost_bps_one_way": cost_bps,
        "mean_ic": round(ic_mean, 4) if ic_mean is not None else None,
        "portfolio_gross": gross_stats,
        "portfolio_net": p_stats,
        "benchmark": b_stats,
        "mean_excess_per_period_pct": round(mean_ex, 2),
        "excess_hac_t": round(t_ex, 2) if t_ex is not None else None,
        "excess_bootstrap_p": p_boot,
        "total_excess_pct": round(p_stats.get("total_return_pct", 0) - b_stats.get("total_return_pct", 0), 1),
    }


def split_period(style: str, cache: Dict[str, pd.DataFrame], horizon: int = 21,
                 top_n: int = 10, split_frac: float = 0.6, **kw) -> Dict:
    """In-sample / out-of-sample split: does the edge survive on unseen data?

    A factor that only works in the half you tuned on is a fitted artifact.
    Reuses backtest_style on a truncated cache (rows up to the split) and on
    the rows after it.
    """
    # determine a global split date from the union of all timestamps
    all_dates = sorted({d for df in cache.values() for d in df["time_key"].tolist()})
    if len(all_dates) < 500:
        return {"status": "insufficient_history"}
    cut = all_dates[int(len(all_dates) * split_frac)]
    ins, oos = {}, {}
    for sym, df in cache.items():
        a = df[df["time_key"] <= cut]
        b = df[df["time_key"] >= cut]
        if len(a) >= 400:
            ins[sym] = a.reset_index(drop=True)
        if len(b) >= 400:
            oos[sym] = b.reset_index(drop=True)
    r_ins = backtest_style(style, ins, horizon=horizon, top_n=top_n, **kw)
    r_oos = backtest_style(style, oos, horizon=horizon, top_n=top_n, **kw)
    return {"status": "ok", "style": style, "split_date": str(cut)[:10],
            "in_sample": r_ins, "out_of_sample": r_oos}


def monthly_ic_decay(style: str, cache: Dict[str, pd.DataFrame], horizon: int = 21,
                     top_n: int = 10, min_names: int = 30) -> Dict:
    """Year-by-year breakdown: is the edge stable or driven by one regime?"""
    from stock_selector import STYLES
    scorer = None if style == "composite" else STYLES.get(style)
    if style != "composite" and scorer is None:
        return {"status": "unknown_style"}

    per_symbol = {}
    for sym, df in cache.items():
        try:
            rows = score_history(sym, df, horizon=horizon, step=horizon,
                                 window_bars=0, scorer=scorer)
        except Exception:
            continue
        if rows:
            per_symbol[sym] = {r["date"]: r for r in rows}

    counts = {}
    for m in per_symbol.values():
        for d in m:
            counts[d] = counts.get(d, 0) + 1
    dates = sorted(d for d, c in counts.items() if c >= min_names)

    by_year: Dict[str, List[float]] = {}
    for d in dates:
        pairs = [(m[d]["score"], m[d]["fwd_ret"]) for m in per_symbol.values() if d in m]
        if len(pairs) < min_names:
            continue
        ranked = sorted(pairs, key=lambda p: p[0], reverse=True)
        k = min(top_n, len(ranked))
        top = float(np.mean([r for _, r in ranked[:k]]))
        uni = float(np.mean([r for _, r in pairs]))
        yr = str(d)[:4]
        by_year.setdefault(yr, []).append(top - uni)

    return {"status": "ok", "style": style,
            "by_year_excess_pct": {y: round(float(np.mean(v)) * 100, 2) for y, v in sorted(by_year.items())}}
