import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

def test_list_macro_events():
    from macro_calendar import list_macro_events
    events = list_macro_events()
    assert isinstance(events, list)
    assert len(events) >= 3
    codes = [e['code'] for e in events]
    assert 'VIX' in codes
    assert 'CPI' in codes


def test_get_macro_snapshot():
    from macro_calendar import get_macro_snapshot
    snap = get_macro_snapshot()
    assert 'generated_at' in snap
    assert snap['market_regime'] in ['calm', 'normal', 'elevated', 'fear']
