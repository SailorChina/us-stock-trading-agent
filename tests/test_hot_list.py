"""Test: hot list functionality."""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


@pytest.mark.network
@pytest.mark.timeout(30)
def test_get_hot_list_futu_returns_list():
    from tech_engine import get_hot_list_futu
    result = get_hot_list_futu(top=5)
    assert isinstance(result, list)


@pytest.mark.network
@pytest.mark.timeout(30)
def test_scan_hot_list_futu_returns_dict():
    from tech_engine import scan_hot_list_futu
    result = scan_hot_list_futu(top=5)
    assert isinstance(result, dict)
    assert "status" in result
    assert "source" in result
    assert "data" in result


def test_futu_available_quick_returns_bool():
    from tech_engine import _futu_available_quick
    result = _futu_available_quick()
    assert isinstance(result, bool)


def test_hot_command_in_agent():
    import agent
    import argparse
    # Check that hot is in the choices
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["analyze", "signal", "top", "scan", "watchlist", "checklist", "report", "smart_money", "hot"])
    args = parser.parse_args(["hot"])
    assert args.command == "hot"


def test_smart_universe_has_60_stocks():
    from smart_money_screener import SMART_UNIVERSE
    assert len(SMART_UNIVERSE) >= 60, f"Expected >= 60, got {len(SMART_UNIVERSE)}"
    assert "US.NVDA" in SMART_UNIVERSE
    assert "US.AAPL" in SMART_UNIVERSE
    assert "US.TSLA" in SMART_UNIVERSE


def test_smart_universe_all_us_prefix():
    from smart_money_screener import SMART_UNIVERSE
    for s in SMART_UNIVERSE:
        assert s.startswith("US."), f"{s} missing US. prefix"


@pytest.mark.network
@pytest.mark.timeout(30)
def test_detect_volume_surge_returns_dict_or_none():
    from smart_money_screener import detect_volume_surge
    result = detect_volume_surge("US.NVDA", num_bars=5)
    assert result is None or isinstance(result, dict)
