import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import trade_journal


def test_add_and_list(tmp_path):
    trade_journal.JOURNAL_PATH = str(tmp_path / 'journal.jsonl')
    entry = trade_journal.add_trade(action='BUY', symbol='US.NVDA', shares=10, price=230.0, stop_loss=220.0, reason='Golden cross')
    assert entry['action'] == 'BUY'
    assert entry['symbol'] == 'US.NVDA'
    result = trade_journal.list_trades(limit=5)
    assert result['count'] == 1
    assert result['trades'][0]['symbol'] == 'US.NVDA'


def test_add_analysis(tmp_path):
    trade_journal.JOURNAL_PATH = str(tmp_path / 'journal2.jsonl')
    entry = trade_journal.add_analysis(symbol='US.TSLA', analysis_result={'rating': 'Buy', 'score': 75})
    assert entry['type'] == 'analysis'
    result = trade_journal.list_analyses(limit=5)
    assert result['count'] == 1


def test_list_trades_empty(tmp_path):
    trade_journal.JOURNAL_PATH = str(tmp_path / 'empty.jsonl')
    result = trade_journal.list_trades()
    assert result['count'] == 0
    assert result['trades'] == []


def test_list_trades_symbol_filter(tmp_path):
    trade_journal.JOURNAL_PATH = str(tmp_path / 'filter.jsonl')
    trade_journal.add_trade('BUY', 'US.NVDA', 10, 230.0)
    trade_journal.add_trade('BUY', 'US.TSLA', 5, 250.0)
    result = trade_journal.list_trades(symbol='US.NVDA')
    assert result['count'] == 1
    assert result['trades'][0]['symbol'] == 'US.NVDA'


def test_list_trades_limit(tmp_path):
    trade_journal.JOURNAL_PATH = str(tmp_path / 'limit.jsonl')
    for i in range(5):
        trade_journal.add_trade('BUY', 'US.AAPL', 1, 150.0 + i)
    result = trade_journal.list_trades(limit=3)
    assert result['count'] == 3


def test_list_analyses_empty(tmp_path):
    trade_journal.JOURNAL_PATH = str(tmp_path / 'analyses_empty.jsonl')
    result = trade_journal.list_analyses()
    assert result['count'] == 0
