#!/usr/bin/env python3
"""fundamental_factors -- real quality/value factors from cached fundamentals.

The question this answers, which the project could not answer before: does
QUALITY actually work here? Until now the only thing ever measured under that
name was `low_vol`, a volatility proxy, and it tested significantly NEGATIVE
(t=-2.42). Real quality (ROE / ROIC / gross margin) could not be computed at
all because there was no fundamental data.

Point-in-time discipline is the whole game here. A quarter ending 2026-06-26 is
NOT known on 2026-06-27; futu_fundamentals stamps every record with an
`available_date` (period end + a conservative lag) and `latest_asof` filters on
it. Scoring on the period end instead would leak the future into the backtest
and manufacture alpha that cannot be traded.

Factors are built as CROSS-SECTIONAL PERCENTILES, per date, because that is what
the portfolio construction consumes (rank the universe, buy the top N). Rank
rather than raw value also removes the need to winsorise outliers like Apple's
148% ROE caused by buyback-shrunken equity.

Usage:
    python scripts/fundamental_factors.py --validate --horizon 21 --top 5
    python scripts/fundamental_factors.py --corr            # quality vs momentum
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Optional

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)

import numpy as np

import backtest_engine as be
import futu_fundamentals as ff

QUALITY_FIELDS = ["roe", "roic", "gross_margin"]
MIN_METRICS = 2          # need at least this many of the three to score a name
MIN_PEERS = 20           # skip a date if fewer names are scorable


# ---------------------------------------------------------------------------
# panel construction
# ---------------------------------------------------------------------------

def _grid_dates(df, horizon: int, min_bars: int = 60) -> List[str]:
    """The rebalance dates for one symbol, exactly as backtest_engine sees them."""
    if df is None or "time_key" not in df.columns:
        return []
    stamps = df["time_key"].tolist()
    return [str(stamps[t])[:10] for t in range(min_bars, len(df) - horizon, horizon)]


def _pct_rank(vals: List[float]) -> List[float]:
    """Percentile rank 0-100, ties averaged. Cross-sectional by construction."""
    n = len(vals)
    if n < 2:
        return [50.0] * n
    order = sorted(range(n), key=lambda i: vals[i])
    out = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg = (i + j) / 2.0
        for k in range(i, j + 1):
            out[order[k]] = avg / (n - 1) * 100.0
        i = j + 1
    return out


def raw_quality_by_date(fund_cache: Dict[str, dict], dates_by_symbol: Dict[str, List[str]],
                        fields: Optional[List[str]] = None) -> Dict[str, Dict[str, Dict[str, float]]]:
    """{date: {symbol: {field: value}}} using only data knowable at that date."""
    fields = fields or QUALITY_FIELDS
    out: Dict[str, Dict[str, Dict[str, float]]] = {}
    for sym, rec in fund_cache.items():
        for d in dates_by_symbol.get(sym, []):
            vals = ff.latest_asof(rec, d, fields)
            if not vals:
                continue
            out.setdefault(d, {})[sym] = vals
    return out


def quality_panel(fund_cache: Dict[str, dict], price_cache: Dict[str, "object"],
                  horizon: int, fields: Optional[List[str]] = None
                  ) -> Dict[str, Dict[str, float]]:
    """{symbol: {date: 0-100}} equal-weight composite of the ranked metrics."""
    fields = fields or QUALITY_FIELDS
    dates_by_symbol = {s: _grid_dates(df, horizon) for s, df in price_cache.items()}
    raw = raw_quality_by_date(fund_cache, dates_by_symbol, fields)

    panel: Dict[str, Dict[str, float]] = {}
    skipped = 0
    for d, per_sym in raw.items():
        syms = [s for s, v in per_sym.items() if len(v) >= MIN_METRICS]
        if len(syms) < MIN_PEERS:
            skipped += 1
            continue
        accum = {s: [] for s in syms}
        for f in fields:
            have = [s for s in syms if f in per_sym[s]]
            if len(have) < MIN_PEERS:
                continue
            ranks = _pct_rank([per_sym[s][f] for s in have])
            for s, r in zip(have, ranks):
                accum[s].append(r)
        for s, rs in accum.items():
            if rs:
                panel.setdefault(s, {})[d] = float(np.mean(rs))
    panel["_meta"] = {"dates_skipped": skipped}
    return panel


def momentum_panel(price_cache, horizon: int) -> Dict[str, Dict[str, float]]:
    """The validated momentum ranker, reshaped into the same panel format."""
    from strategy_validator import score_history
    from stock_selector import STYLES
    scorer = STYLES["mom_12_1_raw"]
    out: Dict[str, Dict[str, float]] = {}
    for sym, df in price_cache.items():
        try:
            rows = score_history(sym, df, horizon=horizon, step=horizon,
                                 window_bars=0, scorer=scorer)
        except Exception:
            continue
        if rows:
            out[sym] = {r["date"]: float(r.get("raw", r["score"])) for r in rows}
    return out


def orthogonality(mom: Dict[str, Dict[str, float]],
                  qual: Dict[str, Dict[str, float]]) -> dict:
    """How much do the two rankers overlap? Drives whether combining can help."""
    from strategy_validator import _spearman
    per_date = []
    for sym in set(mom) & set(qual):
        for d in set(mom[sym]) & set(qual[sym]):
            per_date.append((d, sym, mom[sym][d], qual[sym][d]))
    by_date: Dict[str, list] = {}
    for d, s, m, q in per_date:
        by_date.setdefault(d, []).append((m, q))
    ics = []
    for d, rows in by_date.items():
        if len(rows) < 30:
            continue
        ic = _spearman([r[0] for r in rows], [r[1] for r in rows])
        if ic is not None:
            ics.append(ic)
    if not ics:
        return {"dates": 0}
    return {"dates": len(ics), "mean_rank_corr": float(np.mean(ics))}


def gate_by_quality(mom: Dict[str, Dict[str, float]],
                    qual: Dict[str, Dict[str, float]], min_pct: float) -> Dict[str, Dict[str, float]]:
    """Momentum scores, but only for names above a quality percentile floor.

    Below the floor the score is dropped entirely rather than set low: a low
    score would still be eligible when the pool of good names is thin, which is
    exactly when quality matters most.
    """
    out: Dict[str, Dict[str, float]] = {}
    for sym, md in mom.items():
        qd = qual.get(sym, {})
        keep = {d: v for d, v in md.items()
                if qd.get(d) is not None and qd[d] >= min_pct}
        if keep:
            out[sym] = keep
    return out


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------

def summarize(name: str, r: dict) -> str:
    if r.get("status") != "ok":
        return "%-26s %s" % (name, r.get("status"))
    p = r["portfolio_net"]
    return ("%-26s n=%-4s CAGR %6.1f%%  Sharpe %5.2f  MDD %6.1f%%  held %.1f  "
            "ex/pool %+6.2f%%  t=%5s  boot=%s" % (
                name, r.get("rebalances"), p["cagr_pct"], p["sharpe"],
                p["max_drawdown_pct"], r.get("avg_names_held", 0.0),
                r["mean_excess_per_period_pct"], r["excess_hac_t"],
                r["excess_bootstrap_p"]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="fundamental factors (quality/value)")
    ap.add_argument("--horizon", type=int, default=21)
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--corr", action="store_true")
    ap.add_argument("--min-quality", type=float, default=60.0)
    ap.add_argument("--restrict-to-covered", action="store_true", default=True,
                    help="run every strategy on the names that have fundamentals (fair comparison)")
    ap.add_argument("--full-universe", dest="restrict_to_covered", action="store_false",
                    help="let the momentum baseline use the whole price cache instead")
    ap.add_argument("--exclude-etf", action="store_true", default=True)
    args = ap.parse_args(argv)

    fund = ff.load_cache()
    price = be.load_cache()
    etfs = {"US.SPY", "US.QQQ", "US.IWM", "US.RSP", "US.QUAL", "US.MTUM", "US.USMV"}
    if args.exclude_etf:
        price = {k: v for k, v in price.items() if k not in etfs}
    if not fund:
        print("no fundamentals cached -- run: python scripts/futu_fundamentals.py --build")
        return 2

    print("fundamentals cached: %d symbols" % len(fund))
    print("price cache        : %d symbols" % len(price))
    print("report lag         : %d days" % ff.REPORT_LAG_DAYS)
    print()

    qual = quality_panel(fund, price, args.horizon)
    qual.pop("_meta", None)
    covered = len(qual)
    dates = sorted({d for m in qual.values() for d in m})
    print("quality panel: %d symbols, %d dates (%s .. %s)"
          % (covered, len(dates), dates[0] if dates else "-", dates[-1] if dates else "-"))
    if covered < 30:
        print("too few symbols covered -- let the fundamentals fetch finish")
        return 2

    # A quality factor can only be measured on names that HAVE fundamentals.
    # Comparing it against a momentum book drawn from the full universe would
    # flatter whichever side happens to sit in the easier subset, so by default
    # every strategy below runs on the SAME covered names.
    if args.restrict_to_covered:
        price = {k: v for k, v in price.items() if k in qual}
        print("restricted to covered names: %d symbols (--full-universe to disable)"
              % len(price))
    print()

    mom = momentum_panel(price, args.horizon)
    print("momentum panel: %d symbols" % len(mom))
    print()

    if args.corr or args.validate:
        o = orthogonality(mom, qual)
        print("quality vs momentum rank correlation: %s" % json.dumps(o, default=str))
        print()

    if args.validate:
        from stock_selector import STYLES
        print("%-26s %s" % ("strategy", "metrics (net of %.0fbps/side)" % be.COST_BPS_ONE_WAY))
        print("-" * 118)
        print(summarize("momentum (baseline)",
                        be.backtest_style("mom_12_1_raw", price, horizon=args.horizon,
                                          top_n=args.top, scorer=STYLES["mom_12_1_raw"])))
        print(summarize("quality top-%d" % args.top,
                        be.backtest_style("quality", price, horizon=args.horizon,
                                          top_n=args.top, panel=qual)))
        for floor in (50.0, 60.0, 70.0):
            cand = gate_by_quality(mom, qual, floor)
            print(summarize("momentum + qual>=%.0f" % floor,
                            be.backtest_style("mom+q", price, horizon=args.horizon,
                                              top_n=args.top, panel=cand)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
