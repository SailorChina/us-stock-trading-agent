#!/usr/bin/env python3
"""Market Regime Detection - Bull/Bear/Volatile/Neutral classification."""
import json, sys, argparse, threading
from datetime import datetime

try:
    from futu import OpenQuoteContext, RET_OK
    FUTU_OK = True
except ImportError:
    FUTU_OK = False


def get_regime():
    """Detect current market regime using VIX + SPX trend + breadth.

    HONESTY NOTE (2026-09-10): both inputs are read from `US.VIX` and `US.SPX`,
    and futu recognises NEITHER -- both come back "unknown symbol". Previously
    that failure was silent: vix and spx_chg stayed 0, classify_regime(0, 0)
    hit its `vix < 20 and spx_chg > -1` branch, and this function reported a
    confident "neutral" every single day. Anything downstream that treated the
    reading as real was being misled (daily_pick's "no new longs in a bear
    market" gate was, and could never have fired).

    So the failure is now reported instead of smoothed over: if neither quote
    succeeds the result is `regime: "unknown"`, `status: "unavailable"`. Callers
    that need a regime must handle that case rather than trust a default.

    Separately: even with working data, a market-timing gate is NOT wanted on
    this strategy. Six market filters measured against the validated momentum
    signal all reduced both return and significance (SPY>200d MA: 44.8% -> 32.9%,
    HAC t 2.75 -> 1.68). See knowledge/factor_evidence_2026.md section 8.
    """
    result = {"generated_at": datetime.now().isoformat(), "regime": "unknown"}
    
    if not FUTU_OK:
        result["status"] = "futu_unavailable"
        return result
    
    # Threaded with 3s timeout using shared pool
    _r = [None]; _e = [None]
    def _run():
        try:
            from futu_pool import get_futu_context, RET_OK
            ctx = get_futu_context()
            got_any = False
            ret_vix, df_vix = ctx.get_stock_quote(["US.VIX"])
            vix_val = 0
            if ret_vix == RET_OK and df_vix is not None and len(df_vix) > 0:
                vix_val = float(df_vix.iloc[0].get("last_price", 0))
                got_any = got_any or vix_val > 0
            ret_spx, df_spx = ctx.get_stock_quote(["US.SPX"])
            spx_val = 0
            spx_chg = 0
            if ret_spx == RET_OK and df_spx is not None and len(df_spx) > 0:
                spx_val = float(df_spx.iloc[0].get("last_price", 0))
                spx_chg = float(df_spx.iloc[0].get("change_ratio", 0))
                got_any = got_any or spx_val > 0
            if not got_any:
                # Do NOT classify. classify_regime(0, 0) returns "neutral",
                # which reads as a real market call and is not one.
                _r[0] = {
                    "status": "unavailable",
                    "regime": "unknown",
                    "error": "US.VIX and US.SPX are not available from this "
                             "data source (both return 'unknown symbol')",
                }
                return
            regime = classify_regime(vix_val, spx_chg)
            _r[0] = {
                "status": "ok",
                "vix": round(vix_val, 2),
                "spx": round(spx_val, 2),
                "spx_chg_pct": round(spx_chg, 2),
                "regime": regime,
                "confidence": get_confidence(vix_val, spx_chg),
            }
        except Exception as ex:
            _e[0] = ex
    _t = threading.Thread(target=_run, daemon=True)
    _t.start()
    _t.join(timeout=3)
    if _t.is_alive():
        result["error"] = "timeout"
        return result
    if _e[0]:
        result["error"] = str(_e[0])
        return result
    result.update(_r[0])
    return result


def classify_regime(vix, spx_chg):
    """Classify market regime based on VIX and SPX movement."""
    if vix < 15 and spx_chg > 0:
        return "bull"
    elif vix < 20 and spx_chg > -1:
        return "neutral"
    elif vix > 30:
        return "volatile"
    elif vix > 25 and spx_chg < -1:
        return "bear"
    elif spx_chg > 2:
        return "bull"
    elif spx_chg < -2:
        return "bear"
    else:
        return "neutral"


def get_confidence(vix, spx_chg):
    """Confidence score 0-100 for regime classification."""
    if vix < 12 or vix > 40:
        return 85  # Clear signal
    elif abs(spx_chg) > 2:
        return 75
    elif vix < 18 and spx_chg > 0:
        return 60
    elif vix > 25 and spx_chg < 0:
        return 60
    return 40  # Mixed signals


def main():
    parser = argparse.ArgumentParser(description="Market Regime Detector")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    result = get_regime()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        regime = result.get("regime", "unknown")
        vix = result.get("vix", 0)
        conf = result.get("confidence", 0)
        print(f"Market Regime: {regime.upper()}")
        print(f"  VIX: {vix:.2f}  |  Confidence: {conf}/100")
        if result.get("spx"):
            print(f"  SPX: {result['spx']:.2f} ({result['spx_chg_pct']:+.2f}%)")


if __name__ == "__main__":
    main()