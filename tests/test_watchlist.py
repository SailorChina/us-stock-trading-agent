"""Test: watchlist CRUD operations - each test uses a unique temp file."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import watchlist

def test_add_and_list(tmp_path):
    path = str(tmp_path / "watchlist.json")
    orig = watchlist.WATCHLIST_PATH
    watchlist.WATCHLIST_PATH = path
    try:
        r = watchlist.add_stock("US.TSLA", "AI play", "Tech", "high")
        assert r["status"] == "added"
        wl = watchlist.load_watchlist()
        assert len(wl["watchlist"]) == 1
        assert wl["watchlist"][0]["symbol"] == "US.TSLA"
    finally:
        watchlist.WATCHLIST_PATH = orig

def test_remove(tmp_path):
    path = str(tmp_path / "watchlist2.json")
    orig = watchlist.WATCHLIST_PATH
    watchlist.WATCHLIST_PATH = path
    try:
        watchlist.add_stock("US.AAPL", "test")
        r = watchlist.remove_stock("US.AAPL")
        assert r["status"] == "removed"
        assert len(watchlist.load_watchlist()["watchlist"]) == 0
    finally:
        watchlist.WATCHLIST_PATH = orig

def test_update_existing(tmp_path):
    path = str(tmp_path / "watchlist3.json")
    orig = watchlist.WATCHLIST_PATH
    watchlist.WATCHLIST_PATH = path
    try:
        watchlist.add_stock("US.MSFT", "old note")
        r = watchlist.add_stock("US.MSFT", "new note", "Tech", "low")
        assert r["status"] == "updated"
        wl = watchlist.load_watchlist()
        assert wl["watchlist"][0]["note"] == "new note"
    finally:
        watchlist.WATCHLIST_PATH = orig


def test_atomic_write(tmp_path):
    path = str(tmp_path / 'atomic.json')
    orig2 = watchlist.WATCHLIST_PATH
    watchlist.WATCHLIST_PATH = path
    try:
        watchlist.add_stock('US.AAPL', 'atomic test')
        assert not os.path.exists(path + '.tmp')
        with open(path) as f:
            wl = json.load(f)
        assert wl['watchlist'][0]['symbol'] == 'US.AAPL'
    finally:
        watchlist.WATCHLIST_PATH = orig2
