"""Cache utility for sector data - speeds up repeated lookups"""
import json, os, time, hashlib
from datetime import datetime, timedelta

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(CACHE_DIR, exist_ok=True)

def _cache_path(key):
    h = hashlib.md5(key.encode()).hexdigest()[:8]
    return os.path.join(CACHE_DIR, h + ".json")

def get_cached(key, fetch_func, ttl_minutes=30):
    """Get cached data or fetch and cache with TTL."""
    path = _cache_path(key)
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            age_min = (time.time() - data.get("cached_at", 0)) / 60
            if age_min < ttl_minutes:
                return data.get("data"), True
    except Exception:
        pass
    data = fetch_func()
    if data is not None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"data": data, "cached_at": time.time(), "ttl_min": ttl_minutes}, f, ensure_ascii=False)
    return data, False

def invalidate(key):
    """Clear cache for a key."""
    path = _cache_path(key)
    if os.path.exists(path):
        os.remove(path)
