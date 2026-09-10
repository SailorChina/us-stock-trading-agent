#!/usr/bin/env python3
"""daily_pick — after-close US stock scan that outputs today's long candidates.

This is the product the project is for: every day after the US close you run
one command and get a ranked shortlist, and (with --capital) an order-ready
target book sized in dollars.

Philosophy baked in:
  * candidates are ranked by factors that are separately measurable via
    strategy_validator.py --mode cross --style <style>. A style is not
    'working' until it validates; never trust a raw scan by itself.
  * the default ranker is the ONE style that cleared the t>3 bar:
    mom_12_1_raw. Everything else measured flat or negative.
  * every name passes liquidity/price filters at scan time from real prices.
  * there is NO market-timing gate. One was carried here and removed: it could
    not fire (it read US.VIX / US.SPX, which futu does not recognise), and six
    market filters tested against this signal all reduced both return and
    significance. See the comment in run_pick() and section 8 of
    knowledge/factor_evidence_2026.md.

Usage:
    python scripts/daily_pick.py                                # scan, default pool
    python scripts/daily_pick.py --top 5 --capital 3000 --sheet  # $3,000 book
    python scripts/daily_pick.py --from-cache --limit 40         # offline smoke test
"""
import argparse
import collections
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)

import numpy as np
import stock_selector as sel
from risk_manager import vol_target_position

DEFAULT_UNIVERSE = os.path.join(_SCRIPT_DIR, "..", "configs", "universe_us.json")
FETCH_BARS = 800          # 3 years: long enough for 12-1 momentum and MA200
FETCH_TIMEOUT_S = 12

# Pacing, rate-limit handling and the paginating fetch live in futu_pacing so
# that this scanner and live_trader cannot drift apart again -- they once held
# two copies of this logic and only one of them paginated, which made the two
# tools disagree about the same signal on the same day.
from futu_pacing import (MAX_PER_WINDOW as FETCH_MAX_PER_WINDOW,
                         WINDOW_S as FETCH_WINDOW_S,
                         COOLDOWN_S as FETCH_RETRY_COOLDOWN_S,
                         PacedFetcher as _PacedFetcher)

# Which styles the nightly scan runs by default. Now driven by measurement
# rather than priors: on the 228-name / ~12-year cached history (21-day
# rebalance, 129 periods) `mom_12_1_raw` is the only ranker that cleared the
# Harvey-Liu-Zhu t>3 bar for a new factor -- +15.4%/yr over SPY, HAC t=3.58,
# 11 of 12 years positive, and it holds out of sample. Everything else
# measured either flat or negative:
#   mom_12_1 (vol-scaled)  t=1.03   <- the vol scaling destroys the signal
#   momentum (composite)   t=-0.25
#   reversal               t=-0.24
#   st_reversal            t=+0.53  (but -57% max drawdown)
#   quality                t=-2.41  <- significantly NEGATIVE, must not lead
#   low_vol                t=-3.23  <- significantly NEGATIVE, must not lead
# They all stay selectable via --styles so the validator keeps watching them,
# but nothing unvalidated is allowed to drive the default nightly list.
DEFAULT_STYLES = ["mom_12_1_raw"]


def _guarded_fetch(symbol: str, bars: int):
    """Deprecated alias: the timeout-guarded fetch now lives in futu_pacing.

    Kept so nothing that still imports the old name breaks, and so the reason is
    written down: this function and live_trader's fetch were two copies of one
    concern, and only one of them paginated.
    """
    from futu_pacing import fetch_kline_guarded
    return fetch_kline_guarded(symbol, bars, timeout_s=FETCH_TIMEOUT_S)


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


def _cache_fetcher(cache_dir: str = None):
    """Offline fetcher backed by data/_hist_cache, for tests and fast reruns.

    The nightly scan fetches 800 bars per name over the network with a 12s
    per-symbol timeout; a cache-backed rerun is instant and deterministic, and
    it is the only way to run the pipeline without OpenD.
    """
    import pandas as pd
    d = cache_dir or os.path.join(_SCRIPT_DIR, "..", "data", "_hist_cache")

    def fetch(symbol: str, bars: int):
        p = os.path.join(d, symbol.replace(".", "_") + ".csv")
        if not os.path.exists(p):
            return None
        try:
            df = pd.read_csv(p)
        except Exception:
            return None
        if df is None or df.empty:
            return None
        return df.tail(bars).reset_index(drop=True)
    return fetch


def order_sheet(rows: list, capital: float) -> list:
    """Turn ranked candidates into an order-ready book sized in DOLLARS.

    Equal dollar weight, because that is what the backtest measured: each
    period's return is the equal-weighted mean across held names, i.e. the same
    dollar in every name. It is also the shape the Futu app's "by amount" order
    mode wants, which is the only way to trade this list on a $3,000 account --
    OpenAPI rejects sub-1-share quantities and silently truncates a fractional
    qty >= 1, and several of these names cost more than a whole $600 slot.

    Pure function, no network: unit tested.
    """
    if not rows or capital <= 0:
        return []
    per = capital / len(rows)
    out = []
    for r in rows:
        px = r.get("close") or 0.0
        stop = None
        if px and r.get("atr_pct"):
            stop = round(px * (1.0 - 2.0 * float(r["atr_pct"]) / 100.0), 2)
        out.append({
            "symbol": r["symbol"],
            "amount": round(per, 2),
            "ref_price": round(px, 2),
            "est_shares": round(per / px, 4) if px > 0 else 0.0,
            "whole_share_ok": bool(px > 0 and per >= px),
            "stop_loss": stop,
        })
    return out


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


def _live_regime() -> dict:
    """Read the live market regime. Imported lazily so the offline path and the
    unit tests never touch futu."""
    import market_regime
    return market_regime.get_regime()


def run_pick(universe_path: str = DEFAULT_UNIVERSE, styles=None, top: int = 8,
             include_hot: bool = True, limit: int = None,
             min_price: float = 3.0, min_adv: float = 20_000_000.0,
             max_per_sector: int = 3, fetcher=None,
             capital: float = 0.0, regime_fn=None, quota_fn=None) -> dict:
    """Main entry. `fetcher`, `regime_fn` and `quota_fn` are injectable for
    offline tests."""
    read_regime = regime_fn or _live_regime
    fetch = fetcher or _PacedFetcher()
    live = fetcher is None      # an injected fetcher means offline/tests

    report = {
        "generated_at": datetime.now().isoformat(),
        "scan": {"universe_file": os.path.basename(universe_path),
                 "styles": list(styles or DEFAULT_STYLES)},
        "regime": {},
        "gate": {},
        "candidates": {},
        "errors": [],
    }

    # 1. market regime -- reported as CONTEXT, deliberately NOT used to block.
    #
    # This used to be a gate: regime in ("bear", "volatile") -> no new longs.
    # It was removed after being checked, for two independent reasons:
    #
    # (a) It never fired. get_regime() reads US.VIX and US.SPX; futu knows
    #     neither code ("unknown symbol"), so both values come back 0 and
    #     classify_regime(0, 0) returns "neutral" every single day. A safety
    #     net that cannot fire is worse than no safety net, because the
    #     nightly list looked risk-managed while the book was fully exposed.
    #
    # (b) It would hurt even if repaired. Six market filters measured against
    #     this same signal (21d rebalance / top-5 / 228 names, net of cost) all
    #     LOWERED both return and significance versus simply staying invested:
    #         no gate          44.8%  Sharpe 1.14   HAC t=2.75   <- best overall
    #         SPY > 200d MA    32.9%         0.94          1.68
    #         SPY dd <  5%     32.5%         0.96          1.62
    #         SPY dd < 10%     36.8%         1.02          2.01
    #         SPY dd < 15%     37.6%         1.01          2.12
    #         SPY vol21 < 20%  36.2%         1.03          1.90
    #         SPY vol21 < 25%  42.0%         1.13          2.36
    #     Identical in shape to Clenow's 200-day index rule, which took the
    #     signal from 34.3% to 25.4% (t 2.36 -> 1.15): the filter cuts the
    #     rebound along with the drawdown, and the rebound is where the return
    #     lives. The only gate that improved drawdown (dd < 5%: -27.2% vs
    #     -31.7%) cost 12.3pp of annual return to buy 4.5pp of drawdown.
    #
    # Conclusion: the validated configuration is always-invested. The regime is
    # still printed because it is useful context, but it must not silently
    # re-sample the portfolio. See knowledge/factor_evidence_2026.md section 8.
    try:
        report["regime"] = read_regime()
    except Exception as exc:
        report["regime"] = {"regime": "unknown", "error": str(exc)}
    regime = report["regime"].get("regime", "unknown")
    report["gate"] = {
        "regime": regime,
        "block_new_longs": False,
        "note": "informational only: every tested market filter was net harmful",
    }

    # 2. universe = curated pool + dynamic hot list (deduped, capped)
    symbols = [s for s in sel.load_universe(universe_path) if s]
    if include_hot:
        for s in _hot_symbols(40):
            if s not in symbols:
                symbols.append(s)
    if limit:
        symbols = symbols[:limit]

    # 2b. history-kline BUDGET preflight -- online only.
    #
    # Separate from the frequency limit: this budget is 1 per distinct symbol
    # per rolling 30 days and is TIERED BY ACCOUNT SIZE (100 / 300 / 1000 /
    # 2000). Re-requesting a symbol already inside the window is free, and futu
    # lists the covered codes, so the exact cost of this scan is computable.
    # A 228-name scan costs 228 of it: fine on the 300 tier, impossible on the
    # base 100 tier -- and the latter would show up as a partial universe with
    # no error, which is exactly the shape of failure this file keeps hitting.
    if quota_fn is None:
        quota_fn = history_quota_preflight if live else (lambda syms: {"checked": False})
    try:
        report["scan"]["quota"] = quota_fn(symbols)
    except Exception as exc:
        report["scan"]["quota"] = {"checked": False, "error": str(exc)[:120]}
    q = report["scan"]["quota"]
    if q.get("checked") and not q.get("ok"):
        report["scan"]["quota_warning"] = (
            "history-kline BUDGET is short by %d symbol(s). %d of %d names are "
            "already inside the 30-day window (those are free), but %d more "
            "need charging and only %d remain. The list below would be built "
            "from a PARTIAL universe -- shrink the universe or wait for the "
            "window to roll." % (
                q["shortfall"], q["covered"], len(symbols),
                q["needs_charge"], q["remaining"]))
    elif not q.get("checked"):
        # A preflight that failed is not the same as a preflight that passed.
        # Reporting nothing here would hide the budget check exactly the way the
        # fetch failure was hidden, so say so out loud.
        report["scan"]["quota_error"] = q.get("error") or "not read"

    # 3. fetch once per symbol, score under every requested style
    scored = {st: [] for st in (styles or DEFAULT_STYLES)}
    n_ok = n_unfetchable = n_filtered = 0
    last_bar_dates = []
    for sym in symbols:
        df = fetch(sym, FETCH_BARS)
        if df is None or len(df) < 60:
            n_unfetchable += 1
            continue
        if "time_key" in df.columns and len(df):
            last_bar_dates.append(str(df["time_key"].iloc[-1])[:10])
        liq = _liquidity(df)
        if liq["price"] < min_price or liq["adv_usd"] < min_adv:
            n_filtered += 1
            continue
        n_ok += 1
        ctx = sel.context_for_entry(df)
        for st in scored:
            res = sel.score_style(st, df)
            if res["score"] > 0:
                scored[st].append({
                    "symbol": sym,
                    "score": res["score"],
                    # Rank on the unclamped value when the style exposes one,
                    # so a score that saturates at 100 does not collapse the
                    # ordering into a tie (see momentum_12_1_raw_score).
                    "rank": res.get("raw", res["score"]),
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
    # Split on purpose. Conflating these two hid a broken online path: the run
    # said "180 dropped" and looked like a strict liquidity filter, when in fact
    # 180 FETCHES had been refused by the rate limit and the candidate list was
    # built from the surviving handful.
    report["scan"]["symbols_unfetchable"] = n_unfetchable
    report["scan"]["symbols_filtered_out"] = n_filtered
    report["scan"]["symbols_dropped"] = n_unfetchable + n_filtered
    report["scan"]["last_bar_date"] = max(last_bar_dates) if last_bar_dates else None
    bar_warn = _bar_completeness_warning(report["scan"]["last_bar_date"])
    if bar_warn:
        report["scan"]["bar_warning"] = bar_warn
    if getattr(fetch, "cooldowns_used", 0):
        report["scan"]["fetcher_note"] = (
            "history rate limit hit %d time(s); auto-paced and retried"
            % fetch.cooldowns_used)

    # 4. rank and enrich the top names per style
    for st, rows in scored.items():
        rows.sort(key=lambda r: r["rank"], reverse=True)
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

    # 5. order-ready book, dollar-sized, for the style that drives the default
    # list. One style only: a book needs ONE ranking, and the default ranker is
    # the validated one.
    report["book"] = {}
    if capital and capital > 0:
        primary = (list(styles)[0] if styles else DEFAULT_STYLES[0])
        report["book"] = {
            "style": primary,
            "capital": round(capital, 2),
            "orders": order_sheet(report["candidates"].get(primary, []), capital),
        }

    report["conclusion"] = "scan complete - see candidates"
    return report


def _console(report: dict) -> str:
    lines = []
    reg = report["regime"].get("regime", "?")
    lines.append(f"Regime: {reg} (context only - the strategy stays invested)")
    lines.append(f"Scanned {report['scan']['symbols_scanned']} symbols, "
                 f"{report['scan']['symbols_passed_filters']} passed filters "
                 f"({report['scan'].get('symbols_unfetchable', 0)} unfetchable, "
                 f"{report['scan'].get('symbols_filtered_out', 0)} filtered out)")
    if report["scan"].get("fetcher_note"):
        lines.append(f"NOTE: {report['scan']['fetcher_note']}")
    q = report["scan"].get("quota") or {}
    if q.get("checked"):
        lines.append(f"History-kline budget: {q['used']} used / {q['remaining']} left "
                     f"({q['covered']} of this universe already covered, "
                     f"{q['needs_charge']} to charge)")
    if report["scan"].get("quota_warning"):
        lines.append(f"WARNING: {report['scan']['quota_warning']}")
    if report["scan"].get("quota_error"):
        lines.append(f"NOTE: history-kline budget not checked ({report['scan']['quota_error']})")
    if report["scan"].get("last_bar_date"):
        lines.append(f"Last daily bar: {report['scan']['last_bar_date']}")
    if report["scan"].get("bar_warning"):
        lines.append(f"WARNING: {report['scan']['bar_warning']}")
    for st, rows in report["candidates"].items():
        lines.append("")
        lines.append(f"== {st.upper()} ({len(rows)} candidates) ==")
        for r in rows:
            stop = r["stop_loss"] or "-"
            pct = r["position_pct"]
            pct = f"{pct}%" if isinstance(pct, (int, float)) else "-"
            lines.append(f"  {r['symbol']:10s} score={r['score']:5.1f} "
                         f"close={r['close']} stop={stop} pos={pct} | {', '.join(r['reasons'][:2])}")

    book = report.get("book") or {}
    orders = book.get("orders") or []
    if orders:
        lines.append("")
        lines.append(f"== ORDER SHEET - {book['style']} | ${book['capital']:.0f} "
                     f"equal weight ({len(orders)} names) ==")
        lines.append(f"  {'symbol':10s} {'amount$':>9s} {'price':>9s} "
                     f"{'est_shrs':>9s} {'stop':>9s}")
        for o in orders:
            stop = o["stop_loss"] if o["stop_loss"] is not None else "-"
            lines.append(f"  {o['symbol']:10s} {o['amount']:9.2f} {o['ref_price']:9.2f} "
                         f"{o['est_shares']:9.4f} {str(stop):>9s}")
        under = sum(1 for o in orders if not o["whole_share_ok"])
        if under:
            lines.append(f"  ({under}/{len(orders)} slots are under 1 whole share - "
                         f"use the Futu app 'by amount' mode)")
        lines.append("  Review every ~21 trading days. Stops are 2x ATR below entry.")
    return "\n".join(lines)


def _writable_dir(*candidates: str) -> str:
    """First candidate that accepts a REAL write, else the system temp dir.

    Probed by writing rather than os.access(), which reports writable under
    sandboxes that then refuse the write. Same helper shape used by
    futu_fundamentals.py and tests/conftest.py, for the same reason.
    """
    import tempfile
    for cand in candidates:
        try:
            os.makedirs(cand, exist_ok=True)
            probe = os.path.join(cand, ".write_probe")
            with open(probe, "w", encoding="utf-8") as f:
                f.write("ok")
            os.remove(probe)
            return cand
        except Exception:
            continue
    return tempfile.gettempdir()


def _redirect_futu_logs() -> str:
    """Point futu's log at a writable directory BEFORE futu is imported.

    futu's FTLog builds its path from os.getenv("appdata") at IMPORT time and
    opens the file there. When that write is denied the process dies with rc=1
    and NO traceback -- which reads exactly like an OpenD outage. Must run
    before the first `import futu`, and from main() rather than at module
    import, or it would leak into every test that imports this module.
    """
    log_dir = _writable_dir(os.path.join(_SCRIPT_DIR, "..", "data", "_futu_log"))
    _real = os.getenv

    def _patched(key, default=None):
        if key and key.lower() == "appdata":
            return log_dir
        return _real(key, default)

    os.getenv = _patched
    os.environ["APPDATA"] = log_dir
    return log_dir


def _prepare_futu_runtime() -> None:
    """Make the ONLINE path able to exit.

    futu's callback threads are not daemons and futu_pool caches a live
    OpenQuoteContext, so the scan can finish and the process then hang forever
    with stdout still buffered -- indistinguishable from a network hang. The
    official switch has to be set before any context exists.
    """
    try:
        from futu import SysConfig
        SysConfig.set_all_thread_daemon(True)
    except Exception:
        pass


def _release_futu_runtime() -> None:
    try:
        from futu_pool import close_futu_context
        close_futu_context()
    except Exception:
        pass


def history_quota_preflight(symbols, quota=None) -> dict:
    """Decide whether the history-KLINE BUDGET can cover this scan.

    Two different limits exist and they need different responses:

      * a FREQUENCY limit (~60 calls / 30s, measured). Response: pace and retry.
        Handled by _PacedFetcher.

      * a BUDGET limit: 1 per distinct symbol per rolling 30 days, TIERED BY
        ACCOUNT SIZE -- 100 for a plain account, 300 at 10k HKD, 1000 at 500k
        HKD, 2000 at 5m HKD. Response: check it UP FRONT. Re-requesting a symbol
        already inside the window is free, and futu returns the list of covered
        codes, so the exact cost is computable rather than guessable.

    This matters because a 228-name scan costs 228 of that budget. On the 300
    tier that leaves only 72 symbols of headroom, and on the base 100 tier the
    scan CANNOT complete -- which shows up as a partial universe with no
    exception raised, i.e. the failure mode that looks like a valid answer.

    `quota` is injectable for tests as (used, remaining, covered_codes).
    """
    out = {"checked": False}
    if quota is None:
        try:
            from tech_engine import _get_futu_ctx
            ctx = _get_futu_ctx()
            if ctx is None:
                return out
            ret, data = ctx.get_history_kl_quota(get_detail=True)
            if ret != 0:
                out["error"] = str(data)[:120]
                return out
            quota = data
        except Exception as exc:
            out["error"] = "%s: %s" % (type(exc).__name__, str(exc)[:100])
            return out

    used, remaining, covered_raw = quota
    # get_detail=True returns a list of DICTS ([{"code": "US.NEM", "name": ...},
    # ...]), not a list of code strings -- so a bare set() raises
    # "unhashable type: dict". Tolerate both shapes.
    covered = set()
    for item in (covered_raw or []):
        code = item.get("code") if isinstance(item, dict) else item
        if code:
            covered.add(str(code))
    wants = list(symbols or [])
    needs = [s for s in wants if s not in covered]
    out.update({
        "checked": True,
        "used": int(used),
        "remaining": int(remaining),
        "covered": len(wants) - len(needs),
        "needs_charge": len(needs),
        "ok": len(needs) <= int(remaining),
    })
    if not out["ok"]:
        out["shortfall"] = len(needs) - int(remaining)
    return out


def _bar_completeness_warning(last_bar: str) -> str:
    """Flag a possibly-unfinished intraday bar.

    Daily bars carry the session's own date, so during the US session the last
    bar is a PARTIAL day being fed into 12-1 momentum as though it were a
    close. Nothing errors -- you just get a slightly wrong signal, which is the
    dangerous kind. The US session closes at 20:00-21:00 UTC, so a bar dated
    today (UTC) cannot be final before then. The nightly job is supposed to run
    after the close; this makes a mis-scheduled run visible instead of silent.
    """
    if not last_bar:
        return ""
    now = datetime.now(timezone.utc)
    if last_bar == now.strftime("%Y-%m-%d") and now.hour < 21:
        return ("last daily bar is %s and the US session has not closed yet "
                "(closes 20:00-21:00 UTC) - it may be an INCOMPLETE intraday "
                "bar. Re-run after the US close." % last_bar)
    return ""


def main():
    ap = argparse.ArgumentParser(description="daily US stock picker")
    ap.add_argument("--universe", default=DEFAULT_UNIVERSE)
    ap.add_argument("--styles", default=",".join(DEFAULT_STYLES),
                    help="comma separated; any of " + "|".join(sorted(sel.STYLES)))
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--capital", type=float, default=0.0,
                    help="account size; produces a dollar-sized order sheet, e.g. 3000")
    ap.add_argument("--sheet", action="store_true",
                    help="print the order-ready target book (needs --capital)")
    ap.add_argument("--from-cache", action="store_true",
                    help="read data/_hist_cache instead of the network (offline)")
    ap.add_argument("--no-hot", action="store_true")
    ap.add_argument("--min-price", type=float, default=3.0)
    ap.add_argument("--min-adv", type=float, default=20_000_000.0)
    ap.add_argument("--max-per-sector", type=int, default=3,
                    help="max names per sector in each style list (0 = off)")
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    offline = bool(args.from_cache)
    if args.sheet and not args.capital:
        print("--sheet needs --capital (e.g. --capital 3000)", file=sys.stderr)
        return 2
    if not offline:
        # Order matters: the log redirect must precede any `import futu`,
        # including the one _prepare_futu_runtime does.
        _redirect_futu_logs()
        _prepare_futu_runtime()

    try:
        report = run_pick(universe_path=args.universe,
                          styles=[s.strip() for s in args.styles.split(",") if s.strip()],
                          top=args.top,
                          # --from-cache means offline: the hot list and the live
                          # regime read are both network calls, so they must be
                          # off or the run is not offline at all.
                          include_hot=not (args.no_hot or offline),
                          limit=args.limit,
                          min_price=args.min_price, min_adv=args.min_adv,
                          max_per_sector=args.max_per_sector,
                          fetcher=_cache_fetcher() if offline else None,
                          capital=args.capital,
                          regime_fn=(lambda: {"regime": "not_read",
                                              "note": "offline (--from-cache)"}
                                     ) if offline else None)
    finally:
        if not offline:
            _release_futu_runtime()

    if not args.sheet:
        report.pop("book", None)

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
