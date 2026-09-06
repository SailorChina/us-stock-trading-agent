import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from us_stock_analyzer import normalize_symbol


def test_normalize_english():
    assert normalize_symbol('NVDA') == 'US.NVDA'
    assert normalize_symbol('aapl') == 'US.AAPL'
    assert normalize_symbol('MSFT') == 'US.MSFT'
    assert normalize_symbol('tsla') == 'US.TSLA'


def test_normalize_prefixed():
    assert normalize_symbol('US.NVDA') == 'US.NVDA'
    assert normalize_symbol('us.tsla') == 'US.TSLA'


def test_normalize_pinyin():
    assert normalize_symbol('yingweida') == 'US.NVDA'
    assert normalize_symbol('tesila') == 'US.TSLA'
    assert normalize_symbol('guge') == 'US.GOOG'


def test_normalize_invalid():
    try:
        normalize_symbol('notarealsymbolxyz')
        assert False
    except ValueError:
        pass


def test_normalize_short():
    assert normalize_symbol('AMD') == 'US.AMD'
    assert normalize_symbol('meta') == 'US.META'


@pytest.mark.network
@pytest.mark.timeout(30)
def test_get_tech_analysis_returns_dict():
    from us_stock_analyzer import get_tech_analysis
    result = get_tech_analysis('US.NVDA')
    assert isinstance(result, dict)
    assert 'status' in result


@pytest.mark.network
@pytest.mark.timeout(30)
def test_get_capital_anomaly_no_crash():
    from us_stock_analyzer import get_capital_anomaly
    result = get_capital_anomaly('US.NVDA')
    assert isinstance(result, dict)
    assert result['status'] in ('skipped', 'pending', 'error', 'ok')


@pytest.mark.network
@pytest.mark.timeout(30)
def test_get_news_returns_dict():
    from us_stock_analyzer import get_news
    result = get_news('US.NVDA', size=3)
    assert isinstance(result, dict)
