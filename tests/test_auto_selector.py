"""Tests for auto_selector module."""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


def test_auto_selector_imports():
    import auto_selector
    assert hasattr(auto_selector, "scan_smart")
    assert hasattr(auto_selector, "scan_hot")
    assert hasattr(auto_selector, "merge_and_rank")
    assert hasattr(auto_selector, "run_full_analysis")
    assert hasattr(auto_selector, "run_analysis_parallel")
    assert hasattr(auto_selector, "format_table")


def test_futu_available_quick():
    from auto_selector import _futu_available
    result = _futu_available()
    assert isinstance(result, bool)


def test_merge_and_rank_empty():
    from auto_selector import merge_and_rank
    result = merge_and_rank({"data": []}, {"data": []}, top_n=5)
    assert isinstance(result, list)
    assert len(result) == 0


def test_merge_and_rank_with_data():
    from auto_selector import merge_and_rank
    smart = {"status": "ok", "count": 2, "data": [
        {"symbol": "US.NVDA", "total_score": 63, "price": {"latest_price": 230, "change_pct": 0.84}}
    ]}
    hot = {"status": "ok", "count": 1, "data": [
        {"code": "US.NVDA", "hot_score": 85}
    ]}
    result = merge_and_rank(smart, hot, top_n=5)
    assert len(result) >= 1
    assert result[0]["symbol"] == "US.NVDA"
    assert result[0]["smart_score"] == 63
    assert result[0]["hot_score_raw"] == 85
    assert result[0]["composite"] > 0


def test_format_table_empty():
    from auto_selector import format_table
    result = format_table([], {}, {})
    assert isinstance(result, str)
    assert "ONE-CLICK AUTO SELECTOR" in result


def test_format_table_with_data():
    from auto_selector import format_table
    candidates = [{"symbol": "US.NVDA", "price": 230.36, "change_pct": 0.84,
                   "smart_score": 63, "hot_score_norm": 25.5, "tech_rating": "Overweight",
                   "composite": 88.5}]
    result = format_table(candidates, {}, {})
    assert isinstance(result, str)
    assert "NVDA" in result
    assert "88.5" in result


@pytest.mark.network
@pytest.mark.timeout(60)
def test_scan_smart_returns_list():
    from auto_selector import scan_smart
    result = scan_smart(top_n=10, min_score=15)
    assert isinstance(result, dict)
    assert "status" in result
    assert "data" in result


@pytest.mark.network
@pytest.mark.timeout(30)
def test_scan_hot_returns_dict():
    from auto_selector import scan_hot
    result = scan_hot(top_n=10)
    assert isinstance(result, dict)
    assert "status" in result
    assert "data" in result


def test_auto_command_in_agent():
    import agent
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["analyze", "signal", "top", "scan", "watchlist",
                         "checklist", "report", "smart_money", "hot", "divergence",
                         "candlestick", "earnings", "decision", "ml-predict", "ml-backtest", "auto"])
    args = parser.parse_args(["auto"])
    assert args.command == "auto"


def test_auto_selector_main_exists():
    import auto_selector
    assert hasattr(auto_selector, "main")
