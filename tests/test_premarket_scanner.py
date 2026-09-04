import pytest
import sys, os, json
import time as _time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from cache_util import retry_call


def _yahoo_accessible():
    urls = [
        "https://query1.finance.yahoo.com/v8/finance/chart/AAPL?interval=1d&period=1d",
        "https://query1.finance.yahoo.com/v8/finance/chart/MSFT?interval=1d&period=1d",
    ]
    import urllib.request
    for url in urls:
        ok = False
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                retry_call(lambda: urllib.request.urlopen(req, timeout=10), max_attempts=2, delay=0.5)
                ok = True
                break
            except Exception:
                if attempt < 2:
                    _time.sleep(1)
        if ok:
            return True
    return False


def test_premarket_scan():
    if not _yahoo_accessible():
        pytest.skip("Yahoo Finance unavailable")
    from premarket_scanner import run_premarket_scan
    result = run_premarket_scan(top=5, threshold=0.0)
    assert result["status"] == "ok", f"scan failed: {result}"
    assert "top_movers" in result
    assert result["elapsed_sec"] >= 0


def test_afterhours_scan():
    from premarket_scanner import run_afterhours_scan
    result = run_afterhours_scan(top=3)
    assert result["status"] == "ok"
    assert len(result["top_movers"]) <= 3
