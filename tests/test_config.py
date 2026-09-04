"""Test: settings.toml parses correctly via loader."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "configs"))
import loader

def test_load_settings():
    s = loader.load_settings()
    assert "general" in s
    assert "futu" in s
    assert "risk" in s
    assert s["general"]["default_timeframe"] == "1d"
    assert s["futu"]["host"] == "127.0.0.1"
    assert s["futu"]["port"] == 11111
    assert s["sentiment"]["vix_low"] == 20

def test_get_by_dotpath():
    assert loader.get("general.default_timeframe") == "1d"
    assert loader.get("futu.host") == "127.0.0.1"
    assert loader.get("sentiment.vix_high") == 40
    assert loader.get("nonexistent.key", "default") == "default"
