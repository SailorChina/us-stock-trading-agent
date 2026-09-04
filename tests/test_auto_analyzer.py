import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))


def test_print_summary():
    from auto_analyzer import print_summary
    import io
    old_stderr = sys.stderr
    sys.stderr = buf = io.StringIO()
    try:
        print_summary([
            {'symbol': 'US.NVDA', 'action': 'HOLD', 'tech_rating': 'Hold', 'tech_score': 45, 'trade_plan': {}},
            {'symbol': 'US.TSLA', 'action': 'HOLD', 'tech_rating': 'Hold', 'tech_score': 40, 'trade_plan': {}},
        ])
        output = buf.getvalue()
    finally:
        sys.stderr = old_stderr
    assert '2 stocks' in output
    assert 'HOLD' in output
    assert 'NO SIGNALS' in output


def test_print_summary_with_buy():
    from auto_analyzer import print_summary
    import io
    old_stderr = sys.stderr
    sys.stderr = buf = io.StringIO()
    try:
        print_summary([
            {'symbol': 'US.NVDA', 'action': 'BUY', 'tech_rating': 'Buy', 'tech_score': 72, 'trade_plan': {'entry_zone': 220, 'stop_loss': 200}},
            {'symbol': 'US.TSLA', 'action': 'HOLD', 'tech_rating': 'Hold', 'tech_score': 40, 'trade_plan': {}},
        ])
        output = buf.getvalue()
    finally:
        sys.stderr = old_stderr
    assert 'NVDA' in output
    assert 'BUY' in output
    assert '2 stocks' in output
    assert 'BUY CANDIDATES' in output
