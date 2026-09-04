import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

def test_logger(caplog):
    from logger import setup_logger, log_trade_event, log_analysis_event
    logger = setup_logger('test')
    with caplog.at_level('INFO', logger='test'):
        log_trade_event(logger, 'US.NVDA', 'BUY', 220.5, 10, pnl=150.0)
        log_analysis_event(logger, 'US.TSLA', 'HOLD', 45)
    assert 'NVDA' in caplog.text
    assert 'TSLA' in caplog.text
    assert 'HOLD' in caplog.text