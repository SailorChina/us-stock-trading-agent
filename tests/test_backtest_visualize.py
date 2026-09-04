import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from backtest_visualize import load_backtest, _is_symbol, compute_equity_curve, compute_drawdown, generate_html

def test_is_symbol():
    assert _is_symbol('US.NVDA') is True
    assert _is_symbol('HK.00700') is True
    assert _is_symbol('file.json') is False
    assert _is_symbol('backtest.py') is False
    assert _is_symbol('backtest') is False
    assert _is_symbol('C:\\ath\\file') is False

def test_load_backtest_from_json(tmp_path):
    data = {'trades': [{'date': '2024-01-01','type': 'buy', 'price': 100, 'hshares': 10, 'pnl': 0, 'pln0_ctc': 0}, {'date': '2024-01-03','type': 'sell', 'price': 110, 'hshares': 10, 'pnl': 100, 'pln_pct': 10}], 'symbol': 'US.TSLA', 'strategy': 'M@', 'total_trades': 1, 'win_rate': 100.0, 'total_return_pct': 10.0, 'final_value': 110000}
    f = tmp_path / 'bt.json'
    f.write_text(json.dumps(data))
    result = load_backtest(str(f))
    assert result['symbol'] == 'US.TSLA'
    assert len(result['trades']) == 2

def test_compute_equity_curve():
    trades = [{'pnl': 100, 'date': '2024-01-01'}, {'pnl': -50, 'date': '2024-01-03'}]
    dates, equity = compute_equity_curve(trades, initial_capital=1000)
    assert equity == [1000, 1100, 1050]
    assert dates == ['start', '2024-01-01', '2024-01-03']

def test_compute_drawdown():
    equity = [1000, 1100, 1050, 900, 950]
    dd = compute_drawdown(equity)
    assert dd == 18.18

def test_generate_html_output(tmp_path):
    report = {'trades': [{'date': '2024-01-01', 'type': 'sell', 'price': 110, 'hshares': 10, 'pnl': 100, 'pln_pct': 10}], 'symbol': 'US.TSLA', 'strategy': 'M@', 'total_trades': 1, 'win_rate': 100.0, 'total_return_pct': 10.0, 'final_value': 110000}
    out = tmp_path / 'report.html'
    html = generate_html(report, str(out))
    assert 'US.TSLA' in html
    assert 'Backtest Report' in html
    assert 'Equity Curve' in html
    out.write_text(html)
    assert out.stat().st_size > 500
