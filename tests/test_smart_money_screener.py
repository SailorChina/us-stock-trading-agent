import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import smart_money_screener as sm


def test_smart_universe_all_us_prefix():
    for s in sm.SMART_UNIVERSE:
        assert s.startswith('US.'), f'{s} missing US. prefix'


def test_smart_universe_size():
    assert len(sm.SMART_UNIVERSE) >= 40, f'Expected >= 40, got {len(sm.SMART_UNIVERSE)}'


def test_smart_universe_key_stocks():
    for sym in ['US.NVDA', 'US.TSLA', 'US.AAPL', 'US.MSFT', 'US.AMZN']:
        assert sym in sm.SMART_UNIVERSE


@pytest.mark.network
@pytest.mark.timeout(30)
def test_detect_volume_surge_short():
    result = sm.detect_volume_surge('US.NVDA', num_bars=5)
    assert result is None or isinstance(result, dict)


@pytest.mark.network
@pytest.mark.timeout(30)
def test_get_top_brokers_returns_none_or_dict():
    result = sm.get_top_brokers('US.NVDA')
    assert result is None or isinstance(result, dict)


def test_format_report_single_stock():
    results = [{
        'symbol': 'US.NVDA', 'total_score': 75,
        'flow_score': 25, 'squeeze_score': 10, 'tech_score': 25, 'mom_score': 15,
        'signals': ['Smart70%', '3d buying'],
        'price': {'latest_price': 230.0, 'change_pct': 2.5},
        'tech': {'status': 'ok', 'data': {
            'rating': 'Overweight', 'score': 72,
            'trade_plan': {'entry_zone': 226.5, 'stop_loss': 215.0, 'risk_reward': 2.0},
        }},
    }]
    output = sm.format_report(results)
    assert 'NVDA' in output
    assert '75' in output
    assert 'SMART MONEY' in output
    assert 'Entry=$226.5' in output


def test_format_report_many():
    results = []
    for i, sym in enumerate(['US.NVDA', 'US.TSLA', 'US.AAPL']):
        results.append({
            'symbol': sym, 'total_score': 80 - i * 5,
            'flow_score': 20, 'squeeze_score': 5, 'tech_score': 25, 'mom_score': 10,
            'signals': [],
            'price': {'latest_price': 200.0 + i * 10, 'change_pct': 1.0},
            'tech': {'status': 'ok', 'data': {
                'rating': 'Hold', 'score': 55,
                'trade_plan': {'entry_zone': 195.0, 'stop_loss': 185.0, 'risk_reward': 1.5},
            }},
        })
    output = sm.format_report(results)
    assert 'NVDA' in output
    assert 'TSLA' in output
    assert 'AAPL' in output
