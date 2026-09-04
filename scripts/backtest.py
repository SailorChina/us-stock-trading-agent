#!/usr/bin/env python3
import json, sys, argparse
from datetime import datetime
import pandas as pd

try:
    from stock_signals.indicators import fetch_kline
    HAS_FETCH=True
except ImportError:
    HAS_FETCH=False

def simple_ma_strategy(df, ma_fast=5, ma_slow=20):
    if len(df) < ma_slow + 5:
        return {"error": "数据不足", "min_required": ma_slow + 5, "actual": len(df)}
    df = df.copy()
    df["ma_fast"] = df["close"].rolling(ma_fast).mean()
    df["ma_slow"] = df["close"].rolling(ma_slow).mean()
    trades = []
    position = 0
    entry_price = 0.0
    shares = 0
    cash = 100000.0
    for i in range(ma_slow + 1, len(df)):
        prev = df.iloc[i - 1]
        row = df.iloc[i]
        price = row["close"]
        if position == 0 and prev["ma_fast"] <= prev["ma_slow"] and row["ma_fast"] > row["ma_slow"]:
            shares = int(cash / price * 0.95)
            cost = shares * price
            cash -= cost
            position = 1
            entry_price = price
        elif position == 1 and prev["ma_fast"] >= prev["ma_slow"] and row["ma_fast"] < row["ma_slow"]:
            revenue = shares * price
            cash += revenue
            trades.append({
                "type": "sell",
                "date": str(row["time"])[:10],
                "price": round(price, 2),
                "shares": shares,
                "pnl": round(revenue - shares * entry_price, 2),
                "pnl_pct": round((revenue / (shares * entry_price) - 1) * 100, 2)
            })
            position = 0
            shares = 0
            entry_price = 0.0
    if position == 1:
        price = df.iloc[-1]["close"]
        revenue = shares * price
        cash += revenue
        trades.append({
            "type": "sell_final",
            "date": str(df.iloc[-1]["time"])[:10],
            "price": round(price, 2),
            "shares": shares,
            "pnl": round(revenue - shares * entry_price, 2),
            "pnl_pct": round((revenue / (shares * entry_price) - 1) * 100, 2)
        })
    final_value = cash
    total_return = (final_value / 100000 - 1) * 100
    win_trades = [t for t in trades if t.get("pnl", 0) > 0]
    win_rate = len(win_trades) / len(trades) * 100 if trades else 0.0
    return {
        "strategy": f"MA{ma_fast}/{ma_slow}",
        "trades": trades,
        "total_trades": len(trades),
        "win_rate": round(win_rate, 1),
        "total_return_pct": round(total_return, 2),
        "final_value": round(final_value, 2)
    }

def main():
    p = argparse.ArgumentParser(description="Backtest US Stock MA Strategy")
    p.add_argument("symbol", help="e.g. US.NVDA")
    p.add_argument("--period", default="daily", choices=["daily", "weekly"])
    p.add_argument("--count", type=int, default=200, help="max bars to fetch")
    p.add_argument("--ma-fast", type=int, default=5)
    p.add_argument("--ma-slow", type=int, default=20)
    p.add_argument("--output", default=None)
    a = p.parse_args()

    ktype = "1d" if a.period == "daily" else "1w"
    print(f"获取 {a.symbol} K线 ({a.period}, count={a.count})...", file=sys.stderr)

    if not HAS_FETCH:
        print(json.dumps({"error": "stock_signals.indicators.fetch_kline不可用"}, ensure_ascii=False, indent=2))
        sys.exit(1)

    df = fetch_kline(a.symbol, ktype=ktype, num=a.count)
    if not isinstance(df, pd.DataFrame) or len(df) == 0:
        print(json.dumps({"error": "K线数据为空"}, ensure_ascii=False, indent=2))
        sys.exit(1)
    # Filter unadjusted split artifacts and stale pre-2020 data
    df = df[df["close"] > 0].copy()
    cutoff = pd.Timestamp("2020-01-01")
    df = df[df["time"] >= cutoff].copy()
    if len(df) < a.ma_slow + 5:
        print(json.dumps({"error": "数据不足（过滤后仅剩" + str(len(df)) + "条）"}, ensure_ascii=False, indent=2))
        sys.exit(1)
    # Filter extreme single-day drops (>40%) — likely split artifacts
    df = df.copy()
    df["pct"] = df["close"].pct_change()
    df = df[df["pct"] >= -0.40].drop(columns=["pct"]).reset_index(drop=True)
    print(f"使用 {len(df)} 条近期K线回测（过滤 splits 异常后）", file=sys.stderr)

    result = simple_ma_strategy(df, a.ma_fast, a.ma_slow)
    result["symbol"] = a.symbol
    result["period"] = a.period
    out = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if a.output:
        with open(a.output, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"已保存: {a.output}", file=sys.stderr)
    else:
        print(out)

if __name__ == "__main__":
    main()