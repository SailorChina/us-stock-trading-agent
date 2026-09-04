# configs/loader.py - Settings loader for US Stock Trading Agent
"""Load and cache settings from configs/settings.toml"""
import os
import tomllib
from pathlib import Path

_SETTINGS_CACHE = {}

def _get_config_path():
    """Find settings.toml in common locations."""
    candidates = [
        Path(__file__).parent / "settings.toml",
        Path(__file__).parent.parent / "configs" / "settings.toml",
        Path.cwd() / "configs" / "settings.toml",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None

def load_settings():
    """Load settings from settings.toml, cached by file path."""
    config_path = _get_config_path()
    if config_path is None:
        return _default_settings()
    key = str(config_path.resolve())
    if key not in _SETTINGS_CACHE:
        try:
            with open(config_path, "rb") as f:
                _SETTINGS_CACHE[key] = tomllib.load(f)
        except Exception:
            _SETTINGS_CACHE[key] = _default_settings()
    return _SETTINGS_CACHE[key]

def get(key, default=None):
    """Get a settings value by dotted key, e.g. get('general.default_timeframe')."""
    settings = load_settings()
    parts = key.split(".")
    current = settings
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return default
    return current

def _default_settings():
    """Return default settings when config file is unavailable."""
    return {
        "general": {"default_timeframe": "1d", "default_time_range": 7, "default_risk_level": "medium"},
        "futu": {"host": "127.0.0.1", "port": 11111, "env": "SIMULATE"},
        "technical": {"default_indicators": ["MA","MACD","RSI","KDJ","BOLL","ATR","OBV"]},
        "portfolio": {"total_capital_default": 100000, "max_single_position_pct": 20},
        "risk": {"atr_stop_multiplier": 2.0, "fixed_stop_pct": 5},
        "sentiment": {"vix_very_low": 15, "vix_low": 20, "vix_medium": 30, "vix_high": 40},
    }
