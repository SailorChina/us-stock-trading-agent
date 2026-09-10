"""Tests for validate_ftquant_strategy and our Futu Quant strategy file.

The FTQuant strategy itself cannot be executed from here (it needs the Futu
client's sandbox), so the safety net is static: parse the file, check every
call against the real SDK exports, and assert the design rules that matter.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import validate_ftquant_strategy as vfs

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRATEGY = os.path.join(HERE, "scripts", "ftquant_mom_12_1_raw.py")


# ---------------------------------------------------------------------------
# the checker itself
# ---------------------------------------------------------------------------

FAKE_SDK = {"functions": {"bar_close", "place_market", "place_stop", "current_price",
                          "atr_atr", "close_positions", "cancel_order_by_symbol", "lot_size",
                          "total_cash", "position_holding_qty", "max_qty_to_buy_on_cash"},
            "classes": {"StrategyBase", "Contract"}}


def _write(tmp_path, body):
    p = tmp_path / "s.py"
    p.write_text(body, encoding="utf-8")
    return str(p)


def test_detects_syntax_error(tmp_path):
    p = _write(tmp_path, "class Strategy(StrategyBase)\n    pass\n")
    problems = vfs.check_strategy(p, FAKE_SDK)
    assert any("syntax error" in x for x in problems)


def test_detects_unknown_api_call(tmp_path):
    p = _write(tmp_path, (
        "class Strategy(StrategyBase):\n"
        "    def handle_data(self):\n"
        "        totally_not_an_api(1)\n"
    ))
    problems = vfs.check_strategy(p, FAKE_SDK)
    assert any("unresolved call names" in x and "totally_not_an_api" in x for x in problems)


def test_accepts_real_api_calls(tmp_path):
    p = _write(tmp_path, (
        "class Strategy(StrategyBase):\n"
        "    def handle_data(self):\n"
        "        qty = max_qty_to_buy_on_cash(1, 2, 3, 4)\n"
        "        place_market(1, qty)\n"
    ))
    assert vfs.check_strategy(p, FAKE_SDK) == []


def test_detects_forbidden_socket_import(tmp_path):
    p = _write(tmp_path, (
        "import socket\n"
        "class Strategy(StrategyBase):\n"
        "    def handle_data(self):\n"
        "        pass\n"
    ))
    problems = vfs.check_strategy(p, FAKE_SDK)
    assert any("forbidden import" in x and "socket" in x for x in problems)


def test_detects_forbidden_subprocess_import(tmp_path):
    p = _write(tmp_path, (
        "from subprocess import run\n"
        "class Strategy(StrategyBase):\n"
        "    def handle_data(self):\n"
        "        pass\n"
    ))
    problems = vfs.check_strategy(p, FAKE_SDK)
    assert any("forbidden import" in x and "subprocess" in x for x in problems)


def test_detects_file_write(tmp_path):
    """The sandbox raises ForbiddenOpError on any write mode."""
    p = _write(tmp_path, (
        "class Strategy(StrategyBase):\n"
        "    def handle_data(self):\n"
        "        open('x.json', 'w')\n"
    ))
    problems = vfs.check_strategy(p, FAKE_SDK)
    assert any("forbids writes" in x for x in problems)


def test_allows_file_read(tmp_path):
    """Reading is permitted, so an 'r' mode must NOT be flagged."""
    p = _write(tmp_path, (
        "class Strategy(StrategyBase):\n"
        "    def handle_data(self):\n"
        "        open('x.json', 'r')\n"
    ))
    assert vfs.check_strategy(p, FAKE_SDK) == []


def test_requires_a_strategy_class(tmp_path):
    """No Strategy class at all -> report that, and say nothing about bases
    (there is no class to inspect)."""
    p = _write(tmp_path, "class NotAStrategy:\n    pass\n")
    problems = vfs.check_strategy(p, FAKE_SDK)
    assert any("no class named 'Strategy'" in x for x in problems)


def test_requires_strategy_to_inherit_base(tmp_path):
    """A Strategy class that does NOT inherit StrategyBase -> flag the base.
    The platform instantiates the class and calls its lifecycle hooks, so
    inheriting StrategyBase is what makes those hooks fire."""
    p = _write(tmp_path, (
        "class Strategy:\n"
        "    def handle_data(self):\n"
        "        pass\n"
    ))
    problems = vfs.check_strategy(p, FAKE_SDK)
    assert any("StrategyBase" in x for x in problems)


def test_reports_missing_required_api(tmp_path):
    p = _write(tmp_path, (
        "class Strategy(StrategyBase):\n"
        "    def handle_data(self):\n"
        "        pass\n"
    ))
    thin = {"functions": set(), "classes": {"StrategyBase"}}
    problems = vfs.check_strategy(p, thin)
    assert any("SDK is missing expected APIs" in x for x in problems)


def test_helper_names_are_not_flagged(tmp_path):
    """declare_trig_symbol etc. come from strategy_base, not the interface file."""
    p = _write(tmp_path, (
        "class Strategy(StrategyBase):\n"
        "    def initialize(self):\n"
        "        declare_strategy_type(1)\n"
        "        self.a = declare_trig_symbol(True)\n"
        "        self.b = show_variable(1, 2)\n"
        "        log_info('x')\n"
    ))
    assert vfs.check_strategy(p, FAKE_SDK) == []


# ---------------------------------------------------------------------------
# our actual strategy file
# ---------------------------------------------------------------------------

def test_repo_strategy_file_exists():
    assert os.path.isfile(STRATEGY), "ftquant strategy file is missing"


def test_repo_strategy_parses_and_has_strategy_class():
    import ast
    tree = ast.parse(open(STRATEGY, encoding="utf-8").read())
    names = {c.name for c in ast.walk(tree) if isinstance(c, ast.ClassDef)}
    assert "Strategy" in names


def test_repo_strategy_does_not_use_forbidden_imports():
    src = open(STRATEGY, encoding="utf-8").read()
    for bad in ("import ctypes", "import socket", "import subprocess",
                "import multiprocessing", "import sqlite3"):
        assert bad not in src, "strategy must not use: %s" % bad


def test_repo_strategy_never_writes_files():
    assert "open(" not in open(STRATEGY, encoding="utf-8").read()


def test_repo_strategy_documents_the_no_volatility_scaling_rule():
    """The single most important empirical finding in this repo: dividing the
    12-1 return by realised vol destroyed the signal (t 3.58 -> 1.03). The
    strategy must keep saying so, or someone will 'improve' it back."""
    src = open(STRATEGY, encoding="utf-8").read()
    assert "波动率缩放" in src or "volatility" in src.lower()
    assert "3.58" in src and "1.03" in src


def test_repo_strategy_uses_atr_stop():
    src = open(STRATEGY, encoding="utf-8").read()
    assert "atr_atr" in src
    assert "place_stop" in src


def test_repo_strategy_momentum_skips_the_recent_month():
    """12-1 must skip the last month; without the skip the short-term
    reversal effect inside that window eats part of the momentum signal."""
    src = open(STRATEGY, encoding="utf-8").read()
    assert "skip" in src
    assert "self.skip" in src


@pytest.mark.skipif(vfs.find_sdk() is None, reason="Futu client not installed")
def test_repo_strategy_passes_full_sdk_validation():
    sdk = vfs.load_sdk_exports(vfs.find_sdk())
    assert vfs.check_strategy(STRATEGY, sdk) == []


@pytest.mark.skipif(vfs.find_sdk() is None, reason="Futu client not installed")
def test_sdk_exposes_the_apis_we_depend_on():
    sdk = vfs.load_sdk_exports(vfs.find_sdk())
    for api in vfs._REQUIRED_APIS:
        assert api in sdk["functions"], "SDK lost API: %s" % api


@pytest.mark.skipif(vfs.find_sdk() is None, reason="Futu client not installed")
def test_strategy_base_hook_names_exist_in_sdk():
    """initialize / handle_data / handle_statistics are the lifecycle hooks the
    framework calls; if upstream renames one, our strategy silently stops."""
    sdk = vfs.load_sdk_exports(vfs.find_sdk())
    src = ""
    import zipfile
    with zipfile.ZipFile(vfs.find_sdk()) as z:
        src = z.read("futu/quant/strategy_base.py").decode("utf-8", "replace")
    for hook in ("initialize", "handle_data", "handle_statistics"):
        assert "def %s(" % hook in src, "lifecycle hook missing upstream: %s" % hook
