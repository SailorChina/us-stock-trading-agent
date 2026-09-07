#!/usr/bin/env python3
"""Smart Money Screener - Following the institutions, efficient Futu API usage"""
import json, sys, os, time, socket, threading
import numpy as np
import pandas as pd
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from tech_engine import fetch_kline, get_price, generate_signal


# Quick Futu availability check
def _futu_available(timeout=2):
    try:
        socket.create_connection(("127.0.0.1", 11111), timeout=timeout)
        return True
    except Exception:
        return False


SMART_UNIVERSE = [
    "US.SPY", "US.QQQ", "US.IWM",
    "US.AAPL", "US.MSFT", "US.NVDA", "US.TSLA", "US.AMZN",
    "US.META", "US.GOOG", "US.AMD", "US.NFLX", "US.AVGO",
    "US.INTC", "US.UBER", "US.LLY", "US.WMT", "US.JNJ",
    "US.PFE", "US.BAC", "US.JPM", "US.GS", "US.MS",
    "US.XOM", "US.COP", "US.PD", "US.ABBV", "US.TMO",
    "US.BRK.B", "US.V", "US.JCI", "US.HON", "US.UNH",
    "US.BA", "US.LMT", "US.RTI", "US.CAT", "US.MMM",
    "US.PYPL", "US.ABN", "US.EL", "US.KO", "US.PEP",
    "US.MCD", "US.NKE", "US.DIS", "US.HD", "US.LOW",
    "US.DIA", "US.VTI", "US.MU", "US.LRCX",
    "US.MA", "US.BMY", "US.AMGN", "US.REGN", "US.TGT",
    "US.SBUX", "US.ABBV", "US.GS",
]

def scan_smart_money(top_n=15, min_score=20):
    if not _futu_available():
        print("Smart Money Scanner: Futu OpenD not available, returning empty", file=sys.stderr)
        return []

    from futu import OpenQuoteContext, RET_OK

    print(f"Smart Money Scanner {datetime.now().strftime('%Y-%m-%d %H:%M')}", file=sys.stderr)
    print(f"Scanning {len(SMART_UNIVERSE)} stocks...", file=sys.stderr)

    results = []
    ctx = OpenQuoteContext(host="127.0.0.1", port=11111)

    try:
        # 1. Fetch short selling data once
        short_map = {}
        ret, result = ctx.get_short_selling_rank()
        if ret == RET_OK and result is not None:
            df = result[1] if isinstance(result, tuple) else result
            if df is not None:
                for _, r in df.iterrows():
                    short_map[r.get("security", "")] = {
                        "short_ratio": float(r.get("short_ratio", 0)),
                        "short_number": int(r.get("short_number", 0)),
                    }
        print(f"  Short data: {len(short_map)} stocks", file=sys.stderr)

        # 2. Fetch capital flow for each stock (batch with delays)
        flow_map = {}
        for sym in SMART_UNIVERSE:
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
                            cons = sum(1 for _, row in daily.iterrows()
                                      if row["smart"] > 0)
                            flow_map[sym] = {"dom": dom, "cons": cons, "ts": ts, "tr": tr}
                time.sleep(0.1)
            except Exception as e:
                print(f"  Flow error {sym}: {e}", file=sys.stderr)
        print(f"  Flow data: {len(flow_map)} stocks", file=sys.stderr)

        # 3. Score each stock
        for sym in SMART_UNIVERSE:
            score = 0
            signals = []

            # Capital flow (0-30)
            fl = flow_map.get(sym, {})
            fl_score = 0
            if fl:
                if fl["dom"] > 0.3: fl_score += 15; signals.append(f"Smart{fl['dom']:.0%}")
                elif fl["dom"] > 0: fl_score += 8
                if fl["cons"] >= 3: fl_score += 10; signals.append(f"{fl['cons']}d buying")
                elif fl["cons"] >= 1: fl_score += 5
                if abs(fl["ts"]) + abs(fl["tr"]) > 1e6: fl_score += 5
            fl_score = min(30, fl_score)

            # Short squeeze (0-20)
            sq = short_map.get(sym, {})
            sq_score = 0
            if sq.get("short_ratio", 0) > 5:
                sq_score = min(20, int(sq["short_ratio"] * 1.5))
                signals.append(f"Short{sq['short_ratio']:.0f}%")

            # Technical (0-25)
            tech = generate_signal(sym, num_bars=60)
            tc = 0
            if tech["status"] == "ok":
                d = tech["data"]
                rs = {"Buy": 25, "Overweight": 18, "Hold": 10, "Underweight": 4, "Sell": 0}
                tc = rs.get(d["rating"], 5)
                if d["score"] >= 60: tc = min(25, tc + 5)

            # Momentum (0-15)
            pr = get_price(sym)
            mc = 0
            if pr:
                chg = pr.get("change_pct", 0)
                mc = 15 if chg > 3 else 10 if chg > 1 else 5 if chg > 0 else 0

            total = fl_score + sq_score + tc + mc
            if total >= min_score:
                results.append({
                    "symbol": sym, "total_score": total,
                    "flow_score": fl_score, "squeeze_score": sq_score,
                    "tech_score": tc, "mom_score": mc,
                    "signals": signals[:4], "price": pr, "tech": tech,
                })
            time.sleep(0.05)

    finally:
        ctx.close()

    results.sort(key=lambda x: x["total_score"], reverse=True)
    return results[:top_n]




def detect_volume_surge(symbol, num_bars=20):
    from tech_engine import fetch_kline
    df = fetch_kline(symbol, ktype="1d", num=num_bars + 10)
    if df is None or len(df) < 20:
        return None
    vol_avg = df["volume"].tail(20).mean()
    vol_latest = df["volume"].iloc[-1]
    if vol_avg > 0:
        ratio = vol_latest / vol_avg
        if ratio > 2.0:
            return {"surge": True, "ratio": round(ratio, 2)}
        elif ratio > 1.5:
            return {"surge": True, "ratio": round(ratio, 2)}
    return None


def get_top_brokers(symbol):
    from futu import OpenQuoteContext, RET_OK
    _r = [None]; _e = [None]
    def _run():
        try:
            ctx = OpenQuoteContext(host="127.0.0.1", port=11111)
            ret, result = ctx.get_top_ten_buy_sell_brokers(symbol)
            if ret == RET_OK and result is not None:
                df = result[1] if isinstance(result, tuple) else result
                if df is not None and len(df) > 0:
                    buys = df[df["buy_sell"] == "buy"].head(3)
                    sells = df[df["buy_sell"] == "sell"].head(3)
                    _r[0] = {
                        "top_buyers": buys["broker"].head(3).tolist() if len(buys) > 0 else [],
                        "top_sellers": sells["broker"].head(3).tolist() if len(sells) > 0 else [],
                        "net_flow": float(df["net_flow"].sum()) if "net_flow" in df.columns else 0,
                    }

        except Exception as ex:
            _e[0] = ex
        finally:
            try:
                ctx.close()
            except Exception:
                pass
    _t = threading.Thread(target=_run, daemon=True)
    _t.start()
    _t.join(timeout=3)
    if _t.is_alive():
        return None
    if _e[0]:
        return None
    return _r[0]

def format_report(results):
    lines = []
    lines.append("=" * 70)
    lines.append("  SMART MONEY SCANNER - Follow the Institutions")
    lines.append(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  {len(results)} candidates")
    lines.append("=" * 70)
    for i, r in enumerate(results):
        p = r.get("price") or {}
        line = f"  #{i+1} {r['symbol']}  Score={r['total_score']}/90"
        if p: line += f"  ${p.get('latest_price',0):.2f}  ({p.get('change_pct',0):+.2f}%)"
        lines.append(line)
        lines.append(f"    Flow={r['flow_score']}/30  Squeeze={r['squeeze_score']}/20  Tech={r['tech_score']}/25  Mom={r['mom_score']}/15")
        if r["signals"]: lines.append(f"    {', '.join(r['signals'])}")
        if r.get("tech") and r["tech"].get("status") == "ok":
            d = r["tech"]["data"]
            lines.append(f"    Tech: {d['rating']}({d['score']})  Entry=${d['trade_plan']['entry_zone']}  Stop=${d['trade_plan']['stop_loss']}  RR={d['trade_plan']['risk_reward']:.1f}:1")
        lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--top", type=int, default=15)
    p.add_argument("--min", type=int, default=20)
    p.add_argument("--json", action="store_true")
    a = p.parse_args()
    results = scan_smart_money(top_n=a.top, min_score=a.min)
    if a.json:
        out = [{"symbol":r["symbol"],"total_score":r["total_score"],"flow_score":r["flow_score"],
                "squeeze_score":r["squeeze_score"],"tech_score":r["tech_score"],"mom_score":r["mom_score"],
                "signals":r["signals"]} for r in results]
        print(json.dumps({"generated_at": datetime.now().isoformat(), "results": out}, indent=2, ensure_ascii=False))
    else:
        print(format_report(results))
