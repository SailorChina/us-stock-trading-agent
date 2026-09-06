"""Test: daily_checklist - stock check and summary."""
import pytest
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from daily_checklist import check_stock, get_vix_level, get_sector_heat, pre_market_check


@pytest.mark.network
@pytest.mark.timeout(30)
def test_check_stock_returns_dict():
    result = check_stock("US.NVDA")
    assert isinstance(result, dict)
    assert "symbol" in result
    assert "status" in result
    if result["status"] == "ok":
        assert "rating" in result
        assert "score" in result
        assert "trade_plan" in result


@pytest.mark.network
@pytest.mark.timeout(30)
def test_check_stock_invalid():
    result = check_stock("US.INVALID_SYMBOL_xyz")
    assert isinstance(result, dict)
    assert "status" in result


@pytest.mark.network
@pytest.mark.timeout(30)
def test_get_vix_level():
    result = get_vix_level()
    assert isinstance(result, tuple)
    assert len(result) == 2


@pytest.mark.network
@pytest.mark.timeout(30)
def test_get_sector_heat():
    result = get_sector_heat()
    assert isinstance(result, list)


@pytest.mark.network
@pytest.mark.timeout(30)
def test_pre_market_check_no_watchlist(tmp_path):
    import daily_checklist
    orig = daily_checklist.WATCHLIST_PATH
    daily_checklist.WATCHLIST_PATH = str(tmp_path / "empty_wl.json")
    try:
        result = daily_checklist.pre_market_check()
        assert result["status"] == "empty"
    finally:
        daily_checklist.WATCHLIST_PATH = orig


@pytest.mark.network
@pytest.mark.timeout(30)
def test_pre_market_check_with_watchlist(tmp_path):
    import daily_checklist
    orig = daily_checklist.WATCHLIST_PATH
    wl_path = str(tmp_path / "test_wl.json")
    daily_checklist.WATCHLIST_PATH = wl_path
    try:
        with open(wl_path, "w", encoding="utf-8") as f:
            json.dump({"watchlist": [{"symbol": "US.NVDA", "note": "test", "sector": "Tech", "priority": "high"}]}, f)
        result = daily_checklist.pre_market_check()
        assert "buy_candidates" in result
        assert "sell_candidates" in result
        assert "market_context" in result
        assert "all_results" in result
        assert isinstance(result["all_results"], list)
    finally:
        daily_checklist.WATCHLIST_PATH = orig