"""Test: scan_stocks - yahoo fallback and structure."""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from scan_stocks import yahoo_sector_ranking, DEFAULT_TIMEOUT_SCAN, _YAHOO_SECTOR


def test_yahoo_sector_map_has_keys():
    assert "IBB" in _YAHOO_SECTOR
    assert "XLK" in _YAHOO_SECTOR
    assert _YAHOO_SECTOR["XLK"] == "Technology"
    assert len(_YAHOO_SECTOR) > 5


@pytest.mark.network
def test_yahoo_sector_ranking_returns_list():
    result = yahoo_sector_ranking(top=5)
    assert isinstance(result, list)
    if len(result) > 0:
        item = result[0]
        assert "ticker" in item
        assert "chg_1d" in item


def test_defaults():
    assert isinstance(DEFAULT_TIMEOUT_SCAN, int)
    assert DEFAULT_TIMEOUT_SCAN > 0