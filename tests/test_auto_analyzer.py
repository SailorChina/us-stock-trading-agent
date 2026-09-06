"""Test: auto_analyzer - scan and report."""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from auto_analyzer import run_once, print_summary


@pytest.mark.network
def test_run_once_returns_list():
    result = run_once()
    assert isinstance(result, list)
    if len(result) > 0:
        assert "symbol" in result[0]
        assert "action" in result[0]


def test_print_summary_empty():
    import io
    old = sys.stderr
    sys.stderr = buf = io.StringIO()
    try:
        print_summary([])
        out = buf.getvalue()
    finally:
        sys.stderr = old
    assert "0 stocks" in out


def test_print_summary_with_holds():
    import io
    old = sys.stderr
    sys.stderr = buf = io.StringIO()
    try:
        print_summary([
            {"symbol": "US.AAPL", "action": "HOLD", "tech_rating": "Hold", "tech_score": 45},
            {"symbol": "US.MSFT", "action": "HOLD", "tech_rating": "Hold", "tech_score": 40},
        ])
        out = buf.getvalue()
    finally:
        sys.stderr = old
    assert "HOLD" in out
    assert "2 stocks" in out