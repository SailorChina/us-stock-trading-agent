"""Test: agent.py - CLI and signal functions."""
import pytest
import sys, os, json, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from agent import normalize_symbol, _adjust_trade_plan, run_quick_signal, run_full_analysis


def test_normalize_symbol():
    assert normalize_symbol("nvda") == "US.NVDA"
    assert normalize_symbol("NVDA") == "US.NVDA"
    assert normalize_symbol("US.NVDA") == "US.NVDA"
    assert normalize_symbol("aapl") == "US.AAPL"
    assert normalize_symbol("tsla") == "US.TSLA"
    assert normalize_symbol("google") == "US.GOOG"
    assert normalize_symbol("alphabet") == "US.GOOG"
    assert normalize_symbol("microsoft") == "US.MSFT"
    assert normalize_symbol("amazon") == "US.AMZN"
    # Chinese names may not be in SYMBOL_MAP, so test with known aliases only
    assert normalize_symbol("tesila") == "US.TSLA"


def test_normalize_symbol_invalid():
    try:
        normalize_symbol("xyz_invalid!@#")
        assert False, "Should raise ValueError"
    except ValueError:
        pass


@pytest.mark.network
@pytest.mark.timeout(30)
def test_adjust_trade_plan_basic():
    tp = {"entry_zone": 220.0, "stop_loss": 200.0, "target_1": 240.0}
    result = _adjust_trade_plan(tp, current_price=230.0, atr=5.0)
    assert result["current_price"] == 230.0
    assert result["entry_zone"] == round(230.0 * 0.985, 2)
    assert result["stop_loss"] < result["entry_zone"]
    assert result["risk_reward"] > 0


@pytest.mark.network
@pytest.mark.timeout(30)
def test_adjust_trade_plan_no_atr():
    tp = {"entry_zone": 220.0}
    result = _adjust_trade_plan(tp, current_price=230.0, atr=None)
    assert result["entry_zone"] == round(230.0 * 0.985, 2)


@pytest.mark.network
@pytest.mark.timeout(30)
def test_adjust_trade_plan_none_tp():
    result = _adjust_trade_plan(None, current_price=230.0, atr=5.0)
    assert result is None


@pytest.mark.network
@pytest.mark.timeout(30)
def test_adjust_trade_plan_zero_price():
    tp = {"entry_zone": 220.0}
    result = _adjust_trade_plan(tp, current_price=0, atr=5.0)
    assert result == tp


@pytest.mark.network
@pytest.mark.timeout(90)
def test_run_quick_signal_returns_dict():
    result = run_quick_signal("US.NVDA")
    assert isinstance(result, dict)
    assert "symbol" in result
    if "error" not in result:
        assert "current_price" in result
        assert "rating" in result
        assert "action" in result
        assert "trade_plan" in result


@pytest.mark.network
@pytest.mark.timeout(90)
def test_run_full_analysis_returns_dict():
    result = run_full_analysis("US.NVDA")
    assert isinstance(result, dict)
    assert "symbol" in result
    assert "modules" in result
    assert "generated_at" in result
    assert "elapsed_sec" in result


def test_command_top_outputs_json(monkeypatch, capsys):
    """Regression: `top` must emit JSON to stdout (was silently empty)."""
    import agent
    import json
    monkeypatch.setattr(
        agent, "scan_smart_money",
        lambda top_n=10, min_score=20: {"status": "ok", "count": 1,
                                        "data": [{"symbol": "US.NVDA", "score": 80}]},
    )
    monkeypatch.setattr(sys, "argv", ["agent.py", "top", "5"])
    agent.main()
    out = capsys.readouterr().out
    assert out.strip(), "top command produced no stdout"
    data = json.loads(out)
    assert data["results"]["data"][0]["symbol"] == "US.NVDA"


def test_command_scan_outputs_json(monkeypatch, capsys):
    """Regression: `scan` must emit JSON to stdout (was silently empty)."""
    import agent
    import json
    import tech_engine
    monkeypatch.setattr(tech_engine, "get_price", lambda s: {"latest_price": 100})
    monkeypatch.setattr(
        tech_engine, "generate_signal",
        lambda *a, **k: {"status": "ok", "data": {"rating": "Buy", "score": 70,
                                                  "signal_strength": 60}},
    )
    monkeypatch.setattr(sys, "argv", ["agent.py", "scan", "NVDA,AAPL"])
    agent.main()
    out = capsys.readouterr().out
    assert out.strip(), "scan command produced no stdout"
    data = json.loads(out)
    assert len(data["results"]) == 2
    assert data["results"][0]["symbol"] == "US.NVDA"


def test_command_signal_outputs_json(monkeypatch, capsys):
    """Regression: CLI must actually print `output` (the final print branch
    used to be unreachable because it was joined to the command dispatch chain)."""
    import agent
    import json
    monkeypatch.setattr(
        agent, "get_tech_analysis",
        lambda *a, **k: {"data": {"rating": "Buy", "score": 70, "trade_plan": {},
                                  "indicators": {"atr": 2}, "signals": [],
                                  "resonance": {"alignment": ""}}},
    )
    monkeypatch.setattr(agent, "get_price", lambda *a, **k: {"latest_price": 100})
    monkeypatch.setattr(sys, "argv", ["agent.py", "signal", "NVDA"])
    agent.main()
    out = capsys.readouterr().out
    assert out.strip(), "signal command produced no stdout"
    data = json.loads(out)
    assert data["symbol"] == "US.NVDA"
    assert data["action"] in ("BUY", "SELL", "HOLD")