#!/usr/bin/env python3
"""Futu connection pool — shared OpenQuoteContext to avoid connection churn."""
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

_ctx = None
_conn_key = ("127.0.0.1", 11111)


def get_futu_context(host="127.0.0.1", port=11111):
    """Get or create a shared Futu quote context.
    
    Reuses the same connection for the same host:port to avoid
    creating dozens of connections during scans.
    """
    global _ctx, _conn_key
    key = (host, port)
    if _ctx is not None and _conn_key == key:
        return _ctx
    from futu import OpenQuoteContext
    _ctx = OpenQuoteContext(host=host, port=port)
    _conn_key = key
    return _ctx


def close_futu_context():
    """Close the shared context. Call on exit or when done."""
    global _ctx
    if _ctx is not None:
        try:
            _ctx.close()
        except Exception:
            pass
        _ctx = None


def with_futu(func, *args, **kwargs):
    """Run a function with the shared Futu context.
    
    Usage:
        with_futu(lambda ctx: ctx.get_market_snapshot(["US.NVDA"]))
    """
    ctx = get_futu_context()
    try:
        return func(ctx, *args, **kwargs)
    finally:
        # Don't close — context is shared
        pass


def batch_get_price(symbols):
    """Batch get prices for multiple symbols in one connection."""
    from futu import RET_OK
    ctx = get_futu_context()
    try:
        ret, df = ctx.get_market_snapshot(symbols)
        if ret != RET_OK or df is None or len(df) == 0:
            return {}
        result = {}
        for _, row in df.iterrows():
            code = row.get("code", "")
            last = float(row.get("last_price", 0))
            prev = float(row.get("prev_close_price", 0))
            result[code] = {
                "symbol": code,
                "latest_price": last,
                "prev_close": prev,
                "change_pct": round((last - prev) / prev * 100, 2) if prev > 0 else 0,
                "volume": int(row.get("volume", 0)),
                "high": float(row.get("high_price", 0)),
                "low": float(row.get("low_price", 0)),
            }
        return result
    except Exception as e:
        print(f"[futu_pool] batch_get_price error: {e}", file=sys.stderr)
        return {}


def batch_get_capital_flow(symbols):
    """Batch get capital flow data with shared context."""
    from futu import RET_OK
    import pandas as pd
    ctx = get_futu_context()
    flow_map = {}
    try:
        for sym in symbols:
            try:
                ret, df = ctx.get_capital_flow(sym)
                if ret == RET_OK and df is not None and len(df) > 10:
                    df = df.sort_values("capital_flow_item_time").tail(5 * 72)
                    if len(df) >= 12:
                        df["date"] = pd.to_datetime(df["capital_flow_item_time"]).dt.date
                        daily = df.groupby("date").agg({
                            "super_in_flow": "sum", "big_in_flow": "sum",
                            "mid_in_flow": "sum", "sml_in_flow": "sum",
                        }).reset_index()
                        daily["smart"] = daily["super_in_flow"] + daily["big_in_flow"]
                        daily["retail"] = daily["mid_in_flow"] + daily["sml_in_flow"]
                        daily = daily.tail(5).reset_index(drop=True)
                        if len(daily) >= 1:
                            ts = daily["smart"].sum()
                            tr = daily["retail"].sum()
                            dom = ts / (abs(ts) + abs(tr) + 1)
                            cons = sum(1 for _, row in daily.iterrows() if row["smart"] > 0)
                            flow_map[sym] = {"dom": dom, "cons": cons, "ts": ts, "tr": tr}
            except Exception as e:
                print(f"[futu_pool] flow error {sym}: {e}", file=sys.stderr)
        return flow_map
    except Exception as e:
        print(f"[futu_pool] batch_get_capital_flow error: {e}", file=sys.stderr)
        return flow_map


if __name__ == "__main__":
    # Test shared context
    ctx = get_futu_context()
    print(f"Context created: {ctx}")
    from futu import RET_OK
    ret, df = ctx.get_market_snapshot(["US.NVDA"])
    if ret == RET_OK and len(df) > 0:
        row = df.iloc[0]
        print(f"NVDA: ${row.get('last_price', 0)} ({row.get('change_ratio', 0):+.2f}%)")
    close_futu_context()