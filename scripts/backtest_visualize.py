#!/usr/bin/env python3
"""Backtest Visualizer - generates interactive HTML report from backtest results."""
import argparse, json, os, sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False


def _is_symbol(s):
    """Check if input looks like a stock symbol (e.g. US.NVDA, HK.00700)."""
    import re
    # Reject file paths and non-symbol formats
    if s.endswith(".py") or os.path.isabs(s) or os.path.isfile(s):
        return False
    # Must match market.code pattern: XX.NNNN or XX.NNNNNN
    return bool(re.match(r"^[A-Z]{2}\.[A-Z0-9]{2,10}$", s))


def load_backtest(path):
    """Load backtest JSON from file or run backtest.py."""
    if path.endswith(".py") or path == "backtest" or _is_symbol(path):
        # Run backtest.py on the symbol
        import subprocess
        result = subprocess.run(
            [sys.executable, os.path.join(SCRIPT_DIR, "backtest.py"), path, "--count", "200"],
            capture_output=True, text=True, timeout=60
        )
        try:
            return json.loads(result.stdout)
        except Exception:
            print(f"Backtest error: {result.stderr[:200]}", file=sys.stderr)
            sys.exit(1)
    else:
        with open(path, encoding="utf-8") as f:
            return json.load(f)


def compute_equity_curve(trades, initial_capital=100000):
    """Build equity curve from trades list."""
    equity = [initial_capital]
    dates = ["start"]
    for t in trades:
        equity.append(equity[-1] + t.get("pnl", 0))
        dates.append(t.get("date", ""))
    return dates, equity


def compute_drawdown(equity):
    """Compute max drawdown from equity curve."""
    peak = equity[0]
    max_dd = 0.0
    for val in equity:
        if val > peak:
            peak = val
        dd = (peak - val) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
    return round(max_dd * 100, 2)


def compute_sharpe(trades, risk_free=0.03):
    """Simplified Sharpe ratio from trade PnLs."""
    pnls = [t.get("pnl_pct", 0) for t in trades if t.get("pnl_pct") is not None]
    if len(pnls) < 2:
        return 0.0
    import numpy as np
    mean_ret = np.mean(pnls) / 100
    std_ret = np.std(pnls) / 100
    if std_ret == 0:
        return 0.0
    return round(mean_ret / std_ret * np.sqrt(252) - risk_free, 2)


def generate_html(report, output_path):
    """Generate interactive HTML report."""
    trades = report.get("trades", [])
    symbol = report.get("symbol", "UNKNOWN")
    strategy = report.get("strategy", "MA")
    total_trades = report.get("total_trades", 0)
    win_rate = report.get("win_rate", 0)
    total_return = report.get("total_return_pct", 0)
    final_value = report.get("final_value", 0)

    dates, equity = compute_equity_curve(trades)
    max_dd = compute_drawdown(equity)
    sharpe = compute_sharpe(trades)

    # Trade stats
    wins = [t for t in trades if t.get("pnl", 0) > 0]
    losses = [t for t in trades if t.get("pnl", 0) <= 0]
    avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0
    profit_factor = abs(sum(t["pnl"] for t in wins) / sum(t["pnl"] for t in losses)) if losses and sum(t["pnl"] for t in losses) != 0 else float("inf")

    if HAS_PLOTLY:
        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=("Equity Curve", "Trade PnL Distribution"),
            row_heights=[0.6, 0.4],
            vertical_spacing=0.12
        )
        fig.add_trace(go.Scatter(x=dates, y=equity, mode="lines", name="Equity",
                                  line=dict(color="#2196F3", width=2)), row=1, col=1)
        fig.add_trace(go.Scatter(x=dates, y=equity, mode="markers", marker=dict(size=4),
                                  hovertemplate="Date: %{x}<br>Value: $%{y:.0f}<extra></extra>"), row=1, col=1)
        # Drawdown fill
        peak = []
        p = equity[0]
        for v in equity:
            if v > p: p = v
            peak.append(p)
        fig.add_trace(go.Scatter(x=dates, y=peak, mode="lines", name="Peak",
                                  line=dict(color="rgba(33,150,243,0.3)", width=1), showlegend=False), row=1, col=1)
        # PnL histogram
        pnls = [t.get("pnl", 0) for t in trades]
        colors = ["#4CAF50" if p >= 0 else "#F44336" for p in pnls]
        fig.add_trace(go.Histogram(x=pnls, marker_color=colors, nbinsx=20, name="PnL",
                                    hovertemplate="PnL: $%{x:.0f}<br>Count: %{y}<extra></extra>"), row=2, col=1)
        html_chart = fig.to_html(full_html=False, include_plotlyjs="cdn")
    else:
        html_chart = '<div style="text-align:center;padding:40px;color:#888;">Plotly not available - install with: pip install plotly</div>'

    # Trade table rows
    trade_rows = ""
    for i, t in enumerate(trades[:50]):  # limit to 50 for performance
        pnl_class = "profit" if t.get("pnl", 0) > 0 else "loss"
        trade_rows += f'''<tr>
            <td>{i+1}</td><td>{t.get("date","")}</td><td>{t.get("type","")}</td>
            <td>${t.get("price",0):.2f}</td><td>{t.get("shares",0)}</td>
            <td class="{pnl_class}">${t.get("pnl",0):,.2f}</td>
            <td class="{pnl_class}">{t.get("pnl_pct",0):.2f}%</td>
        </tr>'''

    if len(trades) > 50:
        trade_rows += f'<tr><td colspan="7" style="text-align:center;color:#888;">... and {len(trades)-50} more trades</td></tr>'

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>回测报告 - {symbol} ({strategy})</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0d1117; color: #c9d1d9; margin: 0; padding: 20px; }}
  .container {{ max-width: 1100px; margin: 0 auto; }}
  h1 {{ color: #58a6ff; border-bottom: 1px solid #21262d; padding-bottom: 12px; }}
  .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin: 20px 0; }}
  .stat-card {{ background: #161b22; border: 1px solid #21262d; border-radius: 8px; padding: 16px; text-align: center; }}
  .stat-card .label {{ font-size: 12px; color: #8b949e; text-transform: uppercase; letter-spacing: 1px; }}
  .stat-card .value {{ font-size: 24px; font-weight: 700; margin-top: 4px; }}
  .profit {{ color: #3fb950; }} .loss {{ color: #f85149; }}
  .positive {{ color: #3fb950; }} .negative {{ color: #f85149; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 16px; font-size: 13px; }}
  th {{ background: #161b22; color: #8b949e; padding: 10px; text-align: left; border-bottom: 1px solid #21262d; }}
  td {{ padding: 8px 10px; border-bottom: 1px solid #21262d; }}
  tr:hover {{ background: #161b22; }}
  .chart-container {{ background: #161b22; border: 1px solid #21262d; border-radius: 8px; padding: 16px; margin: 20px 0; }}
  .meta {{ color: #8b949e; font-size: 13px; margin-bottom: 20px; }}
</style>
</head>
<body>
<div class="container">
  <h1>Backtest Report: {symbol} — {strategy}</h1>
  <p class="meta">Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")} &nbsp;|&nbsp; Symbol: {symbol} &nbsp;|&nbsp; Strategy: {strategy}</p>

  <div class="stats-grid">
    <div class="stat-card"><div class="label">Total Return</div><div class="value {'positive' if total_return > 0 else 'negative'}">{total_return:+.1f}%</div></div>
    <div class="stat-card"><div class="label">Win Rate</div><div class="value">{win_rate:.1f}%</div></div>
    <div class="stat-card"><div class="label">Total Trades</div><div class="value">{total_trades}</div></div>
    <div class="stat-card"><div class="label">Max Drawdown</div><div class="value loss">{max_dd:.1f}%</div></div>
    <div class="stat-card"><div class="label">Sharpe Ratio</div><div class="value">{sharpe:.2f}</div></div>
    <div class="stat-card"><div class="label">Profit Factor</div><div class="value">{profit_factor:.2f}</div></div>
    <div class="stat-card"><div class="label">Avg Win</div><div class="value profit">${avg_win:,.0f}</div></div>
    <div class="stat-card"><div class="label">Avg Loss</div><div class="value loss">${avg_loss:,.0f}</div></div>
    <div class="stat-card"><div class="label">Final Value</div><div class="value">${final_value:,.0f}</div></div>
  </div>

  <div class="chart-container">
    <h3 style="margin-top:0;color:#58a6ff;">Equity Curve & Trade PnL</h3>
    {html_chart}
  </div>

  <h3 style="color:#58a6ff;">Trade Log</h3>
  <table>
    <tr><th>#</th><th>Date</th><th>Type</th><th>Price</th><th>Shares</th><th>PnL ($)</th><th>PnL (%)</th></tr>
    {trade_rows}
  </table>
</div>
</body></html>"""

    return html


def main():
    parser = argparse.ArgumentParser(description="Backtest Visualizer")
    parser.add_argument("input", help="Backtest JSON file or symbol (e.g. US.NVDA)")
    parser.add_argument("--output", default=None)
    parser.add_argument("--initial-capital", type=float, default=100000)
    args = parser.parse_args()

    report = load_backtest(args.input)
    report["initial_capital"] = args.initial_capital

    if args.output:
        out_path = args.output
    else:
        date_str = datetime.now().strftime("%Y%m%d")
        symbol = report.get("symbol", "backtest").replace(".", "_")
        out_path = os.path.join(SCRIPT_DIR, "..", "data", f"backtest_{symbol}_{date_str}.html")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    html = generate_html(report, out_path)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Report saved: {out_path}", file=sys.stderr)
    print(json.dumps({"status": "ok", "output": out_path}, ensure_ascii=False))


if __name__ == "__main__":
    main()
