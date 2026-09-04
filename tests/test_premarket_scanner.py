import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

def test_premarket_scan():
    from premarket_scanner import run_premarket_scan
    result = run_premarket_scan(top=5, threshold=0.0)
    assert result['status'] == 'ok'
    assert 'top_movers' in result
    assert result['total_scanned'] > 0
    assert result['elapsed_sec'] > 0


def test_afterhours_scan():
    from premarket_scanner import run_afterhours_scan
    result = run_afterhours_scan(top=3)
    assert result['status'] == 'ok'
    assert len(result['top_movers']) <= 3
