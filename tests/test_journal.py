"""Test: trade journal persistence - each test uses a unique temp file."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import trade_journal

def test_add_and_list(tmp_path):
    path = str(tmp_path / "journal.jsonl")
    orig = trade_journal.JOURNAL_PATH
    trade_journal.JOURNAL_PATH = path
    try:
        entry = trade_journal.add_trade("BUY", "US.NVDA", 10, 220.0,
                                         stop_loss=204.0, target_1=239.87, reason="test")
        assert entry["symbol"] == "US.NVDA"
        assert entry["action"] == "BUY"
        trades = trade_journal.list_trades(limit=10, symbol="US.NVDA")
        assert trades["count"] == 1
        assert trades["trades"][0]["price"] == 220.0
    finally:
        trade_journal.JOURNAL_PATH = orig

def test_list_analyses(tmp_path):
    path = str(tmp_path / "journal2.jsonl")
    orig = trade_journal.JOURNAL_PATH
    trade_journal.JOURNAL_PATH = path
    try:
        trade_journal.add_analysis("US.TSLA", {"rating": "BUY", "score": 75})
        analyses = trade_journal.list_analyses(limit=10, symbol="US.TSLA")
        assert analyses["count"] == 1
        assert analyses["analyses"][0]["symbol"] == "US.TSLA"
    finally:
        trade_journal.JOURNAL_PATH = orig
