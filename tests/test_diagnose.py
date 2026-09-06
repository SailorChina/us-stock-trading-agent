import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import diagnose


def test_check_python():
    result = diagnose.check_python()
    assert 'python' in result
    assert isinstance(result['version_info'], (list, tuple))
    assert len(result['version_info']) == 3


def test_check_packages():
    result = diagnose.check_packages()
    assert isinstance(result, dict)
    assert result.get('pandas', {}).get('installed', False) == True
    assert result.get('numpy', {}).get('installed', False) == True


def test_check_futu_opend():
    result = diagnose.check_futu_opend()
    assert isinstance(result, dict)
    assert 'reachable' in result
    assert 'port' in result
    assert result['port'] == 11111


def test_check_futu_basic_fails_gracefully():
    result = diagnose.check_futu_basic()
    assert isinstance(result, dict)
    assert 'basic_active' in result


def test_check_news_api():
    result = diagnose.check_news_api()
    assert isinstance(result, dict)
    assert 'news_api_ok' in result
    assert isinstance(result.get('news_count'), int)
