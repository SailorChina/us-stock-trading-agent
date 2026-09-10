#!/usr/bin/env python3
"""daily_pick — after-close US stock scan that outputs today's long candidates.

This is the product the project is for: every day after the US close you run
one command and get, per style, a ranked shortlist with entry context.

Philosophy baked in:
  * candidates are ranked by factors that are separately measurable via
    strategy_validator.py --mode cross --style <style>. A style is not
    'working' until it validates; never trust a raw scan by itself.
  * three SEPARATE rankers (momentum / reversal / quality), never a melted
    composite — mixing trend-following with mean-reversion cancels both.
  * the market regime is a GATE: in bear/volatile markets the scan says
    'no new longs' instead of handing out an entry.
  * every name passes liquidity/price filters at scan time from real prices.

Usage:
    python scripts/daily_pick.py                      # all styles, default pool
    python scripts/daily_pick.py --style momentum --top 5
    python scripts/daily_pick.py --universe configs/universe_us.json --limit 100
"""
import argparse
import json
import os
import sys
import threading
from datetime import datetime

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)

import numpy as np
import stock_selector as sel
from risk_manager import vol_target_position

DEFAULT_UNIVERSE = os.path.join(_SCRIPT_DIR, "..", "configs", "universe_us.json")
FETCH_BARS = 800          # 3 years: long enough for 12-1 momentum and MA200
FETCH_TIMEOUT_S = 12

# Which styles the nightly scan runs by default. Deliberately NOT "all of
# them": these two families have the strongest replication record (12-1
# momentum; profitability/quality). Everything in stock_selector.STYLES stays
# selectable via --styles.
DEFAULT_STYLES = ["mom_12_1", "quality"]


def _guarded_fetch(symbol: str, bars: int):
    """fetch_kline wrapped in a daemon thread so one bad symbol cannot hang
    the whole nightly scan."""
    from tech_engine import fetch_kline
    box = {}

    def _run():
        try:
            box["df"] = fetch_kline(symbol, "1d", bars)
        except Exception as exc:
            box["err"] = exc

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=FETCH_TIMEOUT_S)
    if t.is_alive():
        return None
    if "err" in box:
        return None
    return box.get("df")


def _hot_symbols(top: int = 40) -> list:
    """US hot-list names as an additional dynamic pool (best effort)."""
    try:
        from tech_engine import get_hot_list
        hot = get_hot_list("US", top)
    except Exception:
        return []
    out = []
    for item in (hot or {}).get("data", []) if isinstance(hot, dict) else (hot or []):
        if isinstance(item, dict):
            code = item.get("code") or item.get("symbol") or ""
            if str(code).startswith("US."):
                out.append(code)
    return out


def _liquidity(df) -> dict:
    c = df["close"].to_numpy(dtype=float)
    v = df["volume"].to_numpy(dtype=float)
    n = len(c)
    px = float(c[-1])
    adv = float(np.mean(c[-21:] * v[-21:])) if n >= 21 else float(np.mean(c * v))
    return {"price": px, "adv_usd": adv, "bars": n}


def _sector_cap(rows: list, max_per_sector: int) -> list:
    """Cap how many names from one sector can make a list.

    Signals cluster by sector (in the 60-name event study the five worst
    reversal names were all semis), so an un-diversified top-N is really one
    leveraged bet wearing five tickers.
    """
    if max_per_sector <= 0:
        return rows
    counts: dict = {}
    out = []
    for r in rows:
        sec = sel.sector_of(r["symbol"])
        if counts.get(sec, 0) >= max_per_sector:
            continue
        counts[sec] = counts.get(sec, 0) + 1
        out.append(r)
    return out


def run_pick(universe_path: str = DEFAULT_UNIVERSE, styles=None, top: int = 8,
             include_hot: bool = True, limit: int = None,
             min_price: float = 3.0, min_adv: float = 20_000_000.0,
             max_per_sector: int = 3, fetcher=None) -> dict:
    """Main entry. `fetcher` injectable for offline tests."""
    from market_regime import get_regime
    fetch = fetcher or (lambda s, b: _guarded_fetch(s, b))

    report = {
        "generated_at": datetime.now().isoformat(),
        "scan": {"universe_file": os.path.basename(universe_path),
                 "styles": list(styles or DEFAULT_STYLES)},
        "regime": {},
        "gate": {},
        "candidates": {},
        "errors": [],
    }

    # 1. market regime = gate
    try:
        report["regime"] = get_regime()
    except Exception as exc:
        report["regime"] = {"regime": "unknown", "error": str(exc)}
    regime = report["regime"].get("regime", "unknown")
    gate_blocked = regime in ("bear", "volatile")
    report["gate"] = {"regime": regime, "block_new_longs": gate_blocked}

    # 2. universe = curated pool + dynamic hot list (deduped, capped)
    symbols = [s for s in sel.load_universe(universe_path) if s]
    if include_hot:
        for s in _hot_symbols(40):
            if s not in symbols:
                symbols.append(s)
    if limit:
        symbols = symbols[:limit]

    # 3. fetch once per symbol, score under every requested style
    scored = {st: [] for st in (styles or DEFAULT_STYLES)}
    n_ok = n_fail = 0
    for sym in symbols:
        df = fetch(sym, FETCH_BARS)
        if df is None or len(df) < 60:
            n_fail += 1
            continue
        liq = _liquidity(df)
        if liq["price"] < min_price or liq["adv_usd"] < min_adv:
            n_fail += 1
            continue
        n_ok += 1
        ctx = sel.context_for_entry(df)
        for st in scored:
            res = sel.score_style(st, df)
            if res["score"] > 0:
                scored[st].append({
                    "symbol": sym,
                    "score": res["score"],
                    "reasons": res["reasons"],
                    "stats": res["stats"],
                    "close": ctx.get("close"),
                    "atr_pct": ctx.get("atr_pct"),
                    "returns": ctx.get("returns", []),
                    "adv_usd": round(liq["adv_usd"]),
                    "price": liq["price"],
                })

    report["scan"]["symbols_scanned"] = len(symbols)
    report["scan"]["symbols_passed_filters"] = n_ok
    report["scan"]["symbols_dropped"] = n_fail

    # 4. rank and enrich the top names per style
    for st, rows in scored.items():
        rows.sort(key=lambda r: r["score"], reverse=True)
        diversified = _sector_cap(rows, max_per_sector)
        picked = diversified[:top]
        enriched = []
        for r in picked:
            pos = vol_target_position(r["close"] or 0.0, returns=r["returns"])
            stop = None
            if r["close"] and r["atr_pct"]:
                stop = round(r["close"] * (1.0 - 2.0 * r["atr_pct"] / 100.0), 2)
            enriched.append({
                "symbol": r["symbol"],
                "score": r["score"],
                "close": r["close"],
                "atr_pct": r["atr_pct"],
                "stop_loss": stop,
                "position_pct": pos.get("position_pct") if "position_pct" in pos else None,
                "reasons": r["reasons"],
            })
        report["candidates"][st] = enriched

    report["conclusion"] = ("NO_NEW_LONGS" if gate_blocked
                            else "scan complete - see candidates")
    return report


def _console(report: dict) -> str:
    lines = []
    reg = report["regime"].get("regime", "?")
    lines.append(f"Regime: {reg}  |  new-longs {'BLOCKED' if report['gate']['block_new_longs'] else 'allowed'}")
    lines.append(f"Scanned {report['scan']['symbols_scanned']} symbols, "
                 f"{report['scan']['symbols_passed_filters']} passed filters "
                 f"({report['scan']['symbols_dropped']} dropped)")
    for st, rows in report["candidates"].items():
        lines.append("")
        lines.append(f"== {st.upper()} ({len(rows)} candidates) ==")
        if report["gate"]["block_new_longs"]:
            lines.append("   regime gate: no new longs today")
        for r in rows:
            stop = r["stop_loss"] or "-"
            pct = r["position_pct"]
            pct = f"{pct}%" if isinstance(pct, (int, float)) else "-"
            lines.append(f"  {r['symbol']:10s} score={r['score']:5.1f} "
                         f"close={r['close']} stop={stop} pos={pct} | {', '.join(r['reasons'][:2])}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="daily US stock picker")
    ap.add_argument("--universe", default=DEFAULT_UNIVERSE)
    ap.add_argument("--styles", default=",".join(DEFAULT_STYLES),
                    help="comma separated; any of " + "|".join(sorted(sel.STYLES)))
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--no-hot", action="store_true")
    ap.add_argument("--min-price", type=float, default=3.0)
    ap.add_argument("--min-adv", type=float, default=20_000_000.0)
    ap.add_argument("--max-per-sector", type=int, default=3,
                    help="max names per sector in each style list (0 = off)")
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    report = run_pick(universe_path=args.universe,
                      styles=[s.strip() for s in args.styles.split(",") if s.strip()],
                      top=args.top, include_hot=not args.no_hot, limit=args.limit,
                      min_price=args.min_price, min_adv=args.min_adv,
                      max_per_sector=args.max_per_sector)

    out = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"Saved: {args.output}", file=sys.stderr)
    print(_console(report))
    print("NOTE: research candidates only - validate any style with "
          "strategy_validator.py --mode cross --style <style> before sizing up.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
