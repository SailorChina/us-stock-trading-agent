import pytest
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), chr(46)+chr(46), chr(115)+chr(99)+chr(114)+chr(105)+chr(112)+chr(116)+chr(115)))

def test_diagnose_portfolio_basic():
    from portfolio_diagnose import diagnose_portfolio
    positions = [
        dict(symbol=chr(85)+chr(83)+chr(46)+chr(78)+chr(86)+chr(68)+chr(65), shares=10, entry_price=800, current_price=850, sector=chr(116)+chr(101)+chr(99)+chr(104), stop_loss=780, target_1=900),
        dict(symbol=chr(85)+chr(83)+chr(46)+chr(65)+chr(65)+chr(80)+chr(76), shares=20, entry_price=175, current_price=170, sector=chr(116)+chr(101)+chr(99)+chr(104), stop_loss=165, target_1=190),
    ]
    r = diagnose_portfolio(positions, total_capital=100000)
    assert r[chr(116)+chr(111)+chr(116)+chr(97)+chr(108)+chr(95)+chr(99)+chr(97)+chr(112)+chr(105)+chr(116)+chr(97)+chr(108)] == 100000
    assert r[chr(112)+chr(111)+chr(115)+chr(105)+chr(116)+chr(105)+chr(111)+chr(110)+chr(95)+chr(99)+chr(111)+chr(117)+chr(110)+chr(116)] == 2
    assert r[chr(116)+chr(111)+chr(116)+chr(97)+chr(108)+chr(95)+chr(118)+chr(97)+chr(108)+chr(117)+chr(101)] > 0
    assert r[chr(99)+chr(97)+chr(115)+chr(104)] > 0
    assert 0 <= r[chr(114)+chr(105)+chr(115)+chr(107)+chr(95)+chr(115)+chr(99)+chr(111)+chr(114)+chr(101)] <= 100
    assert r[chr(114)+chr(105)+chr(115)+chr(107)+chr(95)+chr(108)+chr(101)+chr(118)+chr(101)+chr(108)] in [chr(20302), chr(20013), chr(39640)]
    assert isinstance(r[chr(115)+chr(101)+chr(99)+chr(116)+chr(111)+chr(114)+chr(95)+chr(115)+chr(117)+chr(109)+chr(109)+chr(97)+chr(114)+chr(121)], list)
    assert isinstance(r[chr(115)+chr(117)+chr(103)+chr(103)+chr(101)+chr(115)+chr(116)+chr(105)+chr(111)+chr(110)+chr(115)], list)

def test_diagnose_portfolio_profit():
    from portfolio_diagnose import diagnose_portfolio
    positions = [dict(symbol=chr(85)+chr(83)+chr(46)+chr(78)+chr(86)+chr(68)+chr(65), shares=10, entry_price=800, current_price=1000, sector=chr(116)+chr(101)+chr(99)+chr(104), stop_loss=780, target_1=1100)]
    r = diagnose_portfolio(positions, total_capital=100000)
    assert r[chr(116)+chr(111)+chr(116)+chr(97)+chr(108)+chr(95)+chr(112)+chr(110)+chr(108)] > 0
    assert r[chr(116)+chr(111)+chr(116)+chr(97)+chr(108)+chr(95)+chr(112)+chr(110)+chr(108)+chr(95)+chr(112)+chr(99)+chr(116)] > 0

def test_diagnose_portfolio_loss():
    from portfolio_diagnose import diagnose_portfolio
    positions = [dict(symbol=chr(85)+chr(83)+chr(46)+chr(84)+chr(83)+chr(76)+chr(65), shares=10, entry_price=250, current_price=200, sector=chr(97)+chr(117)+chr(116)+chr(111), stop_loss=230, target_1=280)]
    r = diagnose_portfolio(positions, total_capital=100000)
    assert r[chr(116)+chr(111)+chr(116)+chr(97)+chr(108)+chr(95)+chr(112)+chr(110)+chr(108)] < 0
    assert r[chr(116)+chr(111)+chr(116)+chr(97)+chr(108)+chr(95)+chr(112)+chr(110)+chr(108)+chr(95)+chr(112)+chr(99)+chr(116)] < 0

def test_diagnose_portfolio_broken_stop():
    from portfolio_diagnose import diagnose_portfolio
    positions = [dict(symbol=chr(85)+chr(83)+chr(46)+chr(84)+chr(83)+chr(76)+chr(65), shares=10, entry_price=250, current_price=220, sector=chr(97)+chr(117)+chr(116)+chr(111), stop_loss=230, target_1=280)]
    r = diagnose_portfolio(positions, total_capital=100000)
    assert any(chr(27490)+chr(25439) in s for s in r[chr(115)+chr(117)+chr(103)+chr(103)+chr(101)+chr(115)+chr(116)+chr(105)+chr(111)+chr(110)+chr(115)])

def test_diagnose_portfolio_high_conc():
    from portfolio_diagnose import diagnose_portfolio
    positions = [dict(symbol=chr(85)+chr(83)+chr(46)+chr(78)+chr(86)+chr(68)+chr(65), shares=100, entry_price=800, current_price=850, sector=chr(116)+chr(101)+chr(99)+chr(104), stop_loss=780)]
    r = diagnose_portfolio(positions, total_capital=100000)
    assert any(chr(38598)+chr(20013) in s or chr(20179)+chr(20301) in s for s in r[chr(115)+chr(117)+chr(103)+chr(103)+chr(101)+chr(115)+chr(116)+chr(105)+chr(111)+chr(110)+chr(115)])

def test_diagnose_portfolio_low_cash():
    from portfolio_diagnose import diagnose_portfolio
    positions = [
        dict(symbol=chr(85)+chr(83)+chr(46)+chr(78)+chr(86)+chr(68)+chr(65), shares=100, entry_price=800, current_price=800, sector=chr(116)+chr(101)+chr(99)+chr(104), stop_loss=750),
        dict(symbol=chr(85)+chr(83)+chr(46)+chr(65)+chr(65)+chr(80)+chr(76), shares=100, entry_price=175, current_price=175, sector=chr(116)+chr(101)+chr(99)+chr(104), stop_loss=165),
    ]
    r = diagnose_portfolio(positions, total_capital=100000)
    assert any(chr(29616)+chr(37329) in s for s in r[chr(115)+chr(117)+chr(103)+chr(103)+chr(101)+chr(115)+chr(116)+chr(105)+chr(111)+chr(110)+chr(115)])

def test_diagnose_portfolio_empty():
    from portfolio_diagnose import diagnose_portfolio
    r = diagnose_portfolio([], total_capital=100000)
    assert r[chr(112)+chr(111)+chr(115)+chr(105)+chr(116)+chr(105)+chr(111)+chr(110)+chr(95)+chr(99)+chr(111)+chr(117)+chr(110)+chr(116)] == 0
    assert r[chr(116)+chr(111)+chr(116)+chr(97)+chr(108)+chr(95)+chr(118)+chr(97)+chr(108)+chr(117)+chr(101)] == 0
    assert r[chr(99)+chr(97)+chr(115)+chr(104)] == 100000

def test_diagnose_portfolio_dict_input():
    from portfolio_diagnose import diagnose_portfolio
    positions = dict(positions=[dict(symbol=chr(85)+chr(83)+chr(46)+chr(77)+chr(83)+chr(70)+chr(84), shares=5, entry_price=400, current_price=420, sector=chr(116)+chr(101)+chr(99)+chr(104))])
    r = diagnose_portfolio(positions, total_capital=100000)
    assert r[chr(112)+chr(111)+chr(115)+chr(105)+chr(116)+chr(105)+chr(111)+chr(110)+chr(95)+chr(99)+chr(111)+chr(117)+chr(110)+chr(116)] == 1

def test_load_positions_from_json():
    from portfolio_diagnose import load_positions
    import tempfile, os
    data = [dict(symbol=chr(85)+chr(83)+chr(46)+chr(65)+chr(65)+chr(80)+chr(76), shares=10, entry_price=175, current_price=180, sector=chr(116)+chr(101)+chr(99)+chr(104))]
    with tempfile.NamedTemporaryFile(mode=chr(119), suffix=chr(46)+chr(106)+chr(115)+chr(111)+chr(110), delete=False) as fh:
        json.dump(data, fh)
        path = fh.name
    try:
        result = load_positions(path)
        assert isinstance(result, list)
        assert result[0][chr(115)+chr(121)+chr(109)+chr(98)+chr(111)+chr(108)] == chr(85)+chr(83)+chr(46)+chr(65)+chr(65)+chr(80)+chr(76)
    finally:
        os.unlink(path)

def test_load_positions_from_string():
    from portfolio_diagnose import load_positions
    s = json.dumps([dict(symbol=chr(85)+chr(83)+chr(46)+chr(71)+chr(79)+chr(79)+chr(71), shares=5, entry_price=140, current_price=145, sector=chr(116)+chr(101)+chr(99)+chr(104))])
    result = load_positions(s)
    assert isinstance(result, list)
    assert result[0][chr(115)+chr(121)+chr(109)+chr(98)+chr(111)+chr(108)] == chr(85)+chr(83)+chr(46)+chr(71)+chr(79)+chr(79)+chr(71)
