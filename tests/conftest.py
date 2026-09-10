"""Shared pytest fixtures for the US stock trading agent."""
import sys, os, json, tempfile, pytest
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))


def _patch_futu_log_dir():
    """Redirect the futu SDK's log directory into the workspace.

    futu's FTLog hardcodes its log path to ``%APPDATA%\\com.futunn.FutuOpenD\\Log``
    (futu/common/ft_logger.py). When that write is blocked by a sandboxed /
    restricted environment, the SDK dies silently with no traceback, which shows up
    as network tests hanging forever instead of failing.

    Two details drive the implementation:
      * ``ft_logger`` runs ``logger = FTLog()`` at *module import* time, and the
        TimedRotatingFileHandler opens the log file right there — so the redirect
        must happen before ``futu`` is imported, not after (the instance is a
        singleton guarded by ``hasattr``, so it can never be re-pointed later).
      * The path comes from ``os.getenv("appdata")``, so we temporarily shim
        ``os.getenv`` for the duration of the import only, then restore it. This
        avoids mutating APPDATA, which would break site-packages resolution.

    Runs in pytest_configure, i.e. before any test module imports futu.
    """
    if "futu.common.ft_logger" in sys.modules:
        return  # already imported: too late to redirect

    # Prefer a workspace-local log dir (easy to find, gitignored), but fall back
    # to the system temp dir. The workspace sits under Desktop, and writes there
    # are intermittently denied by the sandbox; when that happens the SDK raises
    # PermissionError at import, every test module that touches futu fails to
    # COLLECT, and it reads like a code break when it is purely environmental.
    # Probe with a real write rather than trusting os.access().
    candidates = [
        Path(__file__).parent.parent / "data" / "_futu_log",
        Path(tempfile.gettempdir()) / "_futu_log",
    ]
    log_dir = None
    for cand in candidates:
        try:
            cand.mkdir(parents=True, exist_ok=True)
            probe = cand / ".write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            log_dir = cand
            break
        except Exception:
            continue
    if log_dir is None:
        return  # nowhere writable: let the SDK fail on its own terms

    original_getenv = os.getenv

    def _getenv(key, default=None):
        if isinstance(key, str) and key.lower() == "appdata":
            return str(log_dir)
        return original_getenv(key, default)

    os.getenv = _getenv
    try:
        import futu.common.ft_logger  # noqa: F401  (import is the side effect)
    except Exception:
        pass  # futu missing: network tests will fail on their own terms
    finally:
        os.getenv = original_getenv


def _make_futu_threads_daemon():
    """Make futu's internal threads daemons.

    ``futu/common/callback_executor.py`` starts its worker thread *without*
    setDaemon (unlike network_manager, which does call it), so any live
    OpenQuoteContext keeps a non-daemon thread alive and the interpreter never
    exits after pytest prints its summary — the suite looks like it hangs forever
    when it actually finished minutes ago.

    futu exposes an official switch for exactly this
    (``SysConfig.set_all_thread_daemon``), which is far cleaner than force-killing
    the process. Must run before any context is created.
    """
    try:
        from futu.common.sys_config import SysConfig

        SysConfig.set_all_thread_daemon(True)
    except Exception:
        pass


def pytest_configure(config):
    config.addinivalue_line("markers", "network: mark test as requiring network access")
    _patch_futu_log_dir()
    _make_futu_threads_daemon()



def pytest_unconfigure(config):
    """Release the shared futu connection when the session ends.

    With daemon threads enabled this is no longer what makes the process exit, but
    it still matters: OpenD caps concurrent connections (~128), and a session that
    leaks one per run will eventually starve later runs.
    """
    try:
        import futu_pool

        futu_pool.close_futu_context()
    except Exception:
        pass


@pytest.fixture
def sample_kline_df():
    """Sample K-line DataFrame for indicator tests."""
    import pandas as pd
    import numpy as np
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=60, freq="1D")
    close = 100 + np.cumsum(np.random.randn(60) * 0.5)
    return pd.DataFrame({
        "time_key": dates,
        "open": close + np.random.randn(60) * 0.1,
        "high": close + abs(np.random.randn(60) * 0.3),
        "low": close - abs(np.random.randn(60) * 0.3),
        "close": close,
        "volume": np.random.randint(1_000_000, 10_000_000, 60).astype(float),
        "last_close": [100.0] + list(close[:-1]),
    })


@pytest.fixture
def sample_tech_result():
    """Sample technical analysis result for format tests."""
    return {
        "status": "ok",
        "symbol": "US.NVDA",
        "data": {
            "rating": "Overweight",
            "score": 72,
            "price": {"latest_price": 230.0, "change_pct": 2.5},
            "dimensions": {
                "trend": {"score": 15, "reason": "MA bullish"},
                "momentum": {"score": 12, "reason": "RSI OK"},
                "volatility": {"score": 8, "reason": "ATR normal"},
                "volume": {"score": 10, "reason": "OBV rising"},
            },
            "indicators": {
                "ma": {"MA5": 228, "MA10": 225, "MA20": 220, "MA60": 200},
                "ema": {"EMA12": 229, "EMA26": 224},
                "macd": {"dif": 1.5, "dea": 1.2, "hist": 0.3, "signal": "bullish"},
                "rsi": 58.0,
                "kdj": {"k": 60, "d": 55, "j": 70},
                "boll": {"upper": 240, "mid": 220, "lower": 200, "position_pct": 65},
                "atr": 5.5,
                "aroon": {"aroon_up": 80, "aroon_down": 40, "aroon_diff": 40},
                "adx": {"adx": 25, "plus_di": 30, "minus_di": 15},
                "vwap": 225.5,
            },
            "signals": ["Price above MA20", "MACD golden cross", "Aroon up strong"],
            "signal_strength": 72,
            "trade_plan": {
                "entry_zone": 226.5, "stop_loss": 215.0,
                "target_1": 249.5, "target_2": 261.0,
                "risk_reward": 2.0, "atr": 5.5,
                "position_size_pct": 50.0, "risk_usd": 11.5,
            },
            "last_time": "2024-06-01",
            "bar_count": 60,
        },
    }


@pytest.fixture
def sample_watchlist(tmp_path):
    """Sample watchlist JSON file."""
    wl = {"watchlist": [
        {"symbol": "US.NVDA", "note": "AI play", "sector": "Tech", "priority": "high"},
        {"symbol": "US.TSLA", "note": "EV", "sector": "Auto", "priority": "medium"},
    ]}
    path = tmp_path / "watchlist_test.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(wl, f)
    return str(path)


@pytest.fixture
def sample_positions():
    """Sample positions for portfolio diagnosis."""
    return [
        {"symbol": "US.NVDA", "shares": 10, "entry_price": 220.0, "current_price": 230.0,
         "sector": "Tech", "stop_loss": 210.0},
        {"symbol": "US.TSLA", "shares": 5, "entry_price": 250.0, "current_price": 240.0,
         "sector": "Auto", "stop_loss": 235.0},
    ]


@pytest.fixture
def mock_futu_unavailable(monkeypatch):
    """Mock Futu API to simulate connection failure."""
    import futures
    def mock_init(*args, **kwargs):
        raise ConnectionError("Futu OpenD not running")
    monkeypatch.setattr("futu.OpenQuoteContext", mock_init)