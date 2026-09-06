import pytest
"""Test: auto_trader - signal to order conversion (dry-run)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from auto_trader import place_order, log_trade, auto_trade_from_signal


@pytest.mark.network
@pytest.mark.timeout(30)
def test_place_order_dry_run():
    result = place_order("US.NVDA", "BUY", 10, 226.5, dry_run=True)
    assert isinstance(result, dict)
    assert result["symbol"] == "US.NVDA"


@pytest.mark.network
@pytest.mark.timeout(30)
def test_log_trade(tmp_path):
    import logging
    logger = logging.getLogger("test_trader2")
    entry = log_trade("BUY", "US.NVDA", 10, 226.5)
    assert isinstance(entry, dict)
    assert entry["symbol"] == "US.NVDA"


@pytest.mark.network
@pytest.mark.timeout(30)
def test_auto_trade_from_signal_returns_dict(tmp_path):
    signal_file = str(tmp_path / "signal.json")
    import json
    with open(signal_file, "w") as f:
        json.dump({"symbol": "US.NVDA", "action": "BUY", "current_price": 230.0, "shares": 10}, f)
    result = auto_trade_from_signal(signal_file)
    assert isinstance(result, dict)