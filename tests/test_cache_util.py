"""Test: cache_util - retry and cache functions."""
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from cache_util import retry_call, get_cached, invalidate


def test_retry_call_success():
    calls = []
    def fn():
        calls.append(1)
        return "ok"
    assert retry_call(fn) == "ok"
    assert len(calls) == 1


def test_retry_call_fallback():
    calls = []
    def fn():
        calls.append(1)
        if len(calls) < 2:
            raise ValueError("temp error")
        return "ok"
    assert retry_call(fn, max_attempts=3, delay=0.01) == "ok"
    assert len(calls) == 2


def test_retry_call_exhausted():
    def fn():
        raise ValueError("always fails")
    try:
        retry_call(fn, max_attempts=2, delay=0.01)
        assert False, "Should raise"
    except ValueError:
        pass


def test_get_cached_miss_then_hit(tmp_path):
    cache_dir = str(tmp_path / "cache")
    os.makedirs(cache_dir, exist_ok=True)
    import cache_util
    orig = cache_util.CACHE_DIR
    cache_util.CACHE_DIR = cache_dir
    try:
        call_count = [0]
        def fetch():
            call_count[0] += 1
            return {"value": 42}
        data1, hit1 = get_cached("test_key1", fetch, ttl_minutes=30)
        assert data1 == {"value": 42}
        assert hit1 is False
        assert call_count[0] == 1
        data2, hit2 = get_cached("test_key1", fetch, ttl_minutes=30)
        assert data2 == {"value": 42}
        assert hit2 is True
        assert call_count[0] == 1
    finally:
        cache_util.CACHE_DIR = orig


def test_get_cached_expired(tmp_path):
    import cache_util
    cache_dir = str(tmp_path / "cache2")
    os.makedirs(cache_dir, exist_ok=True)
    orig = cache_util.CACHE_DIR
    cache_util.CACHE_DIR = cache_dir
    try:
        call_count = [0]
        def fetch():
            call_count[0] += 1
            return {"value": call_count[0]}
        data1, _ = get_cached("test_key2", fetch, ttl_minutes=30)
        assert data1["value"] == 1
        import hashlib
        h = hashlib.md5("test_key2".encode()).hexdigest()[:8]
        cache_path = os.path.join(cache_dir, h + ".json")
        with open(cache_path, "r") as f:
            cached = json.load(f)
        cached["cached_at"] = time.time() - 3600
        with open(cache_path, "w") as f:
            json.dump(cached, f)
        data2, hit2 = get_cached("test_key2", fetch, ttl_minutes=30)
        assert data2["value"] == 2
        assert hit2 is False
    finally:
        cache_util.CACHE_DIR = orig


def test_invalidate(tmp_path):
    import cache_util
    cache_dir = str(tmp_path / "cache3")
    os.makedirs(cache_dir, exist_ok=True)
    orig = cache_util.CACHE_DIR
    cache_util.CACHE_DIR = cache_dir
    try:
        def fetch():
            return {"value": 99}
        get_cached("test_key3", fetch)
        invalidate("test_key3")
        data, hit = get_cached("test_key3", fetch)
        assert hit is False
    finally:
        cache_util.CACHE_DIR = orig