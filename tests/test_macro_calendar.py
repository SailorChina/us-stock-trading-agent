import pytest
import sys, os, json
import time as _time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from cache_util import retry_call


def _yahoo_accessible():
    urls = [
        "https://query1.finance.yahoo.com/v8/finance/chart/^VIX?interval=1d&period=5d",
        "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB?interval=1d&period=5d",
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



@pytest.mark.network
@pytest.mark.timeout(30)
def test_list_macro_events():
    from macro_calendar import list_macro_events
    events = list_macro_events()
    assert isinstance(events, list)
    assert len(events) >= 3
    codes = [e["code"] for e in events]
    assert "VIX" in codes
    assert "CPI" in codes


@pytest.mark.network
@pytest.mark.timeout(30)
def test_get_macro_snapshot():
    if not _yahoo_accessible():
        pytest.skip("Yahoo Finance unavailable")
    from macro_calendar import get_macro_snapshot
    snap = get_macro_snapshot()
    assert "generated_at" in snap
    assert isinstance(snap.get("market_regime"), str)
