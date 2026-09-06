"""Shared pytest fixtures for the US stock trading agent."""
import sys, os, json, pytest
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
def pytest_configure(config):
    config.addinivalue_line("markers", "network: mark test as requiring network access")



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