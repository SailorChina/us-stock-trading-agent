#!/usr/bin/env python3
"""live_trader — run the validated mom_12_1_raw signal through Futu OpenAPI.

Why this exists alongside the FTQuant strategy: the Futu Quant GUI
(scripts/ftquant_mom_12_1_raw.py) can only trade the handful of drive symbols
you declare by hand, so it cannot do stock SELECTION. OpenAPI has no such limit
-- it can score the whole 228-name universe, which is what the signal was
validated on (see knowledge/factor_evidence_2026.md section 5).

SAFETY MODEL -- read this before running anything:
  * Default is DRY RUN. Without --execute nothing is sent; you get a printed
    plan. This is deliberate: the ordering code is the easy part to get wrong.
  * Default environment is SIMULATE. Real money needs BOTH --execute and
    --env real, and the account must be unlocked first.
  * Never unlock a real account from a script you have not dry-run.

Signal (validated: 228 names / 11.6y / 21d rebalance / top 10 / 8bps cost):
    12-1 momentum = close(t-21) / close(t-252) - 1
    34.3% CAGR, Sharpe 1.12, max drawdown -28.4%, excess over SPY +15.4%/yr,
    HAC t=3.58, bootstrap p=0.008, 11 of 12 calendar years positive.
No volatility scaling -- that variant measured t=1.03 on identical data.

Usage:
    # 1. always start here: see the plan, place nothing
    python scripts/live_trader.py --top 10

    # 2. simulate orders against the paper account
    python scripts/live_trader.py --top 10 --execute

    # 3. real money (requires unlock; be deliberate)
    python scripts/live_trader.py --top 10 --execute --env real --unlock YOUR_PWD
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from typing import Dict, List, Optional

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
ROOT = os.path.dirname(_SCRIPT_DIR)
DEFAULT_UNIVERSE = os.path.join(ROOT, "configs", "universe_us.json")
CACHE_DIR = os.path.join(ROOT, "data", "_hist_cache")


# ---------------------------------------------------------------------------
# Futu SDK writes its Python log under %APPDATA%. If that write is denied the
# process dies with rc=1 and NO traceback, which reads exactly like an OpenD
# outage. Redirect before the first `import futu`.
# Deliberately done inside a function called from main(), NOT at import time:
# patching os.getenv on import would leak into every test that merely imports
# this module.
# ---------------------------------------------------------------------------
_LOG_DIR = os.path.join(ROOT, "data", "_futu_log")
_redirected = False


def _redirect_futu_logs() -> str:
    global _redirected
    if not _redirected:
        os.makedirs(_LOG_DIR, exist_ok=True)
        _real_getenv = os.getenv

        def _patched(key, default=None):
            if key and key.lower() == "appdata":
                return _LOG_DIR
            return _real_getenv(key, default)

        os.getenv = _patched
        os.environ["APPDATA"] = _LOG_DIR
        _redirected = True
    return _LOG_DIR


# ---------------------------------------------------------------------------
# Tunables -- the validated configuration. Do not "improve" without measuring.
# ---------------------------------------------------------------------------
OPEN_D_HOST = "127.0.0.1"
OPEN_D_PORT = 11111

LOOKBACK = 252          # 12 months
SKIP = 21               # skip the most recent month (it holds the reversal effect)
MIN_BARS = LOOKBACK + SKIP + 2
ATR_PERIOD = 14
ATR_STOP_MULT = 2.0


# ---------------------------------------------------------------------------
# universe + history
# ---------------------------------------------------------------------------

def load_universe(path: str) -> List[str]:
    data = json.load(open(path, encoding="utf-8"))
    syms = data.get("symbols", data) if isinstance(data, dict) else data
    return [s for s in syms if isinstance(s, str) and s.startswith("US.")]


def _from_cache(symbol: str):
    """Local CSV cache -> list of closes. Used by --from-cache."""
    import pandas as pd
    f = os.path.join(CACHE_DIR, symbol.replace(".", "_") + ".csv")
    if not os.path.exists(f):
        return None
    df = pd.read_csv(f)
    return df["close"].to_numpy(dtype=float)


def fetch_closes(symbols: List[str], from_cache: bool, ctx) -> Dict[str, list]:
    """Return {symbol: [closes newest-last]}, skipping anything too short."""
    out: Dict[str, list] = {}
    if from_cache:
        for s in symbols:
            arr = _from_cache(s)
            if arr is not None and len(arr) >= MIN_BARS:
                out[s] = list(arr)
        return out

    for s in symbols:
        try:
            ret, df, _ = ctx.request_history_kline(
                s, start=(_date_days_ago(LOOKBACK * 2)), end=_today(),
                max_count=MIN_BARS + 40)
            if ret != 0 or df is None or df.empty or len(df) < MIN_BARS:
                continue
            out[s] = [float(x) for x in df["close"].tolist()]
        except Exception:
            continue
    return out


def _today() -> str:
    import datetime
    return datetime.date.today().strftime("%Y-%m-%d")


def _date_days_ago(days: int) -> str:
    import datetime
    return (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# signal
# ---------------------------------------------------------------------------

def momentum_12_1(closes: List[float]) -> Optional[float]:
    """THE signal: close(t-21) / close(t-252) - 1. Returns None if too short."""
    if len(closes) < MIN_BARS:
        return None
    recent = closes[-1 - SKIP]
    year = closes[-1 - LOOKBACK]
    if year <= 0:
        return None
    return recent / year - 1.0


def atr(closes: List[float], period: int = ATR_PERIOD) -> Optional[float]:
    """Close-to-close ATR proxy. Good enough for stop placement."""
    if len(closes) < period + 2:
        return None
    moves = [abs(closes[i] - closes[i - 1]) for i in range(len(closes) - period, len(closes))]
    return sum(moves) / len(moves) if moves else None


def rank_universe(hist: Dict[str, list]) -> List[dict]:
    """Score every name, drop the unscoreable, sort by momentum descending."""
    rows = []
    for sym, closes in hist.items():
        m = momentum_12_1(closes)
        if m is None:
            continue
        rows.append({
            "symbol": sym,
            "momentum": m,
            "close": float(closes[-1]),
            "atr": atr(closes),
        })
    rows.sort(key=lambda r: r["momentum"], reverse=True)
    return rows


# ---------------------------------------------------------------------------
# planning
# ---------------------------------------------------------------------------

def plan(ranked: List[dict], holdings: Dict[str, float], capital: float,
         top_n: int) -> dict:
    """Decide buys and sells. Pure function -- unit tested without any network."""
    targets = ranked[:top_n]
    target_syms = {t["symbol"] for t in targets}
    held_syms = {s for s, q in holdings.items() if q and q > 0}

    sells = sorted(held_syms - target_syms)
    holds = sorted(held_syms & target_syms)

    # capital for new positions: free cash plus whatever the sells release.
    # NOTE: we can only price a held name if it also appears in `ranked`. A
    # holding that failed to score (delisted, or too little history) is still
    # SOLD, but its proceeds are NOT added to the budget -- so the plan
    # under-deploys rather than overspending. Conservative on purpose.
    freed = 0.0
    by_sym = {r["symbol"]: r for r in ranked}
    for s in sells:
        px = by_sym.get(s)
        if px:
            freed += holdings[s] * px["close"]
    budget_total = capital + freed

    to_buy = [t for t in targets if t["symbol"] not in held_syms]
    per_name = budget_total / len(to_buy) if to_buy else 0.0

    buys = []
    for t in to_buy:
        px = t["close"]
        qty = int(per_name // px) if px > 0 else 0
        if qty <= 0:
            continue
        stop = px - ATR_STOP_MULT * t["atr"] if t["atr"] else px * 0.92
        buys.append({
            "symbol": t["symbol"], "qty": qty, "ref_price": px,
            "notional": round(qty * px, 2), "stop": round(max(stop, 0.01), 2),
            "momentum_pct": round(t["momentum"] * 100, 1),
        })

    return {
        "sells": sells,
        "holds": holds,
        "buys": buys,
        "budget_total": round(budget_total, 2),
        "per_name": round(per_name, 2),
        "targets": [t["symbol"] for t in targets],
    }


def _concentration_warning(symbols: List[str], threshold: int = 5) -> str:
    """Flag a lopsided basket before it is bought.

    The signal is pure momentum, so in a sector-led market it will pile into
    that sector: on 2026-09-10 it picked 6 semis out of 10. The backtest that
    validated the signal ran through exactly such a period, so this is the
    strategy working as designed -- but it means the book carries one industry
    cycle, and a sector reversal hits every name at once.
    """
    try:
        from stock_selector import sector_of
    except Exception:
        return ""
    counts: Dict[str, int] = {}
    for s in symbols:
        sec = sector_of(s)
        counts[sec] = counts.get(sec, 0) + 1
    worst = max(counts.items(), key=lambda kv: kv[1]) if counts else None
    if worst and worst[1] >= threshold:
        return ("WARNING: %d of %d names are in '%s'. The signal is pure momentum, so it\n"
                "         concentrates in whichever sector leads. A sector reversal hits the\n"
                "         whole book at once -- consider capping per-sector exposure."
                % (worst[1], len(symbols), worst[0]))
    return ""


# ---------------------------------------------------------------------------
# execution
# ---------------------------------------------------------------------------

def _futu():
    import futu as ft
    ft.SysConfig.set_all_thread_daemon(True)   # otherwise the process hangs on exit
    return ft


def get_holdings(ft, trade_ctx, trd_env) -> Dict[str, float]:
    ret, data = trade_ctx.position_list_query(trd_env=trd_env)
    if ret != ft.RET_OK:
        raise RuntimeError("position_list_query failed: %s" % data)
    out = {}
    for _, row in data.iterrows():
        qty = float(row.get("qty", 0) or 0)
        if qty > 0:
            out[str(row["code"])] = qty
    return out


def get_cash(ft, trade_ctx, trd_env) -> float:
    ret, data = trade_ctx.accinfo_query(trd_env=trd_env)
    if ret != ft.RET_OK:
        raise RuntimeError("accinfo_query failed: %s" % data)
    for col in ("cash", "power", "total_assets"):
        if col in data.columns:
            return float(data[col].iloc[0] or 0)
    return 0.0


def execute_plan(ft, quote_ctx, trade_ctx, trd_env, plan_data: dict) -> List[str]:
    """Place the plan. Returns a log of what was attempted."""
    log = []
    for sym in plan_data["sells"]:
        try:
            ret, data = trade_ctx.place_order(
                price=0, qty=0, code=sym, trd_side=ft.TrdSide.SELL,
                order_type=ft.OrderType.MARKET, trd_env=trd_env)
            log.append("SELL %s -> %s" % (sym, "ok" if ret == ft.RET_OK else data))
        except Exception as e:
            log.append("SELL %s -> EXC %s" % (sym, e))

    for b in plan_data["buys"]:
        try:
            ret, data = trade_ctx.place_order(
                price=b["ref_price"], qty=b["qty"], code=b["symbol"],
                trd_side=ft.TrdSide.BUY, order_type=ft.OrderType.MARKET,
                trd_env=trd_env)
            log.append("BUY %s x%s -> %s" % (
                b["symbol"], b["qty"], "ok" if ret == ft.RET_OK else data))
        except Exception as e:
            log.append("BUY %s -> EXC %s" % (b["symbol"], e))
    return log


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="mom_12_1_raw live rebalance (dry run by default)")
    ap.add_argument("--top", type=int, default=10, help="how many names to hold (10 is validated)")
    ap.add_argument("--universe", default=DEFAULT_UNIVERSE)
    ap.add_argument("--limit", type=int, default=0, help="cap universe size (debug)")
    ap.add_argument("--from-cache", action="store_true", help="use data/_hist_cache instead of the network")
    ap.add_argument("--execute", action="store_true", help="actually place orders (default: plan only)")
    ap.add_argument("--env", choices=["simulate", "real"], default="simulate")
    ap.add_argument("--unlock", default="", help="trade password, real env only")
    ap.add_argument("--json", action="store_true", help="emit the plan as JSON")
    args = ap.parse_args(argv)

    # Refuse impossible combinations BEFORE opening any connection.
    if args.execute and args.env == "real" and not args.unlock:
        print("refusing: --env real needs --unlock PASSWORD")
        return 2

    symbols = load_universe(args.universe)
    if args.limit:
        symbols = symbols[:args.limit]
    if not symbols:
        print("empty universe"); return 2

    _redirect_futu_logs()          # must precede the first `import futu`
    ft = _futu()

    quote_ctx = ft.OpenQuoteContext(host=OPEN_D_HOST, port=OPEN_D_PORT)
    trade_ctx = ft.OpenSecTradeContext(filter_trdmarket=ft.TrdMarket.US,
                                       host=OPEN_D_HOST, port=OPEN_D_PORT,
                                       security_firm=ft.SecurityFirm.FUTUSECURITIES)
    trd_env = ft.TrdEnv.SIMULATE if args.env == "simulate" else ft.TrdEnv.REAL

    try:
        if args.execute and args.env == "real":
            ret, data = trade_ctx.unlock_trade(args.unlock)
            if ret != ft.RET_OK:
                print("unlock failed: %s" % data); return 2

        hist = fetch_closes(symbols, args.from_cache, quote_ctx)
        if not hist:
            print("no history fetched (%d symbols requested)" % len(symbols)); return 2

        ranked = rank_universe(hist)
        if not ranked:
            print("nothing scoreable"); return 2

        holdings = get_holdings(ft, trade_ctx, trd_env)
        cash = get_cash(ft, trade_ctx, trd_env)
        plan_data = plan(ranked, holdings, cash, args.top)

        if args.json:
            print(json.dumps({"ranked": ranked[:args.top], "plan": plan_data,
                              "cash": cash, "holdings": holdings}, indent=1, ensure_ascii=False))
        else:
            print("=== mom_12_1_raw | env=%s | %s ===" % (
                args.env, "EXECUTE" if args.execute else "DRY RUN (nothing will be sent)"))
            print("scored %d of %d names | cash %.2f | holding %d" % (
                len(ranked), len(symbols), cash, len(holdings)))
            print("\ntop %d by 12-1 momentum:" % args.top)
            for i, r in enumerate(ranked[:args.top], 1):
                print("  %2d. %-9s %+7.1f%%   close %.2f   ATR %.2f" % (
                    i, r["symbol"], r["momentum"] * 100, r["close"], r["atr"] or 0))
            print("\nplan: sell %d, buy %d, keep %d | budget %.2f (%.2f per new name)" % (
                len(plan_data["sells"]), len(plan_data["buys"]),
                len(plan_data["holds"]), plan_data["budget_total"], plan_data["per_name"]))
            for s in plan_data["sells"]:
                print("  SELL  %s" % s)
            for b in plan_data["buys"]:
                print("  BUY   %-9s x%-5d @ ~%.2f  = %.0f   stop %.2f  (mom %+.1f%%)" % (
                    b["symbol"], b["qty"], b["ref_price"], b["notional"], b["stop"], b["momentum_pct"]))
            for s in plan_data["holds"]:
                print("  KEEP  %s" % s)

            warn = _concentration_warning([t["symbol"] for t in ranked[:args.top]])
            if warn:
                print("\n" + warn)

        if args.execute:
            for line in execute_plan(ft, quote_ctx, trade_ctx, trd_env, plan_data):
                print(line)
        else:
            print("\n(dry run -- re-run with --execute to send these orders)")
        return 0
    finally:
        try:
            quote_ctx.close()
        except Exception:
            pass
        try:
            trade_ctx.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
