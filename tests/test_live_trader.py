"""Tests for live_trader -- the pure decision layer only.

No network, no orders. The point is that order PLANNING is where bugs cost
real money, so it must be testable without an OpenD connection or an account.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import live_trader as lt


def _series(start: float, daily: float, n: int):
    """Geometric price path."""
    out = [start]
    for _ in range(n - 1):
        out.append(out[-1] * (1 + daily))
    return out


# ---------------------------------------------------------------------------
# momentum
# ---------------------------------------------------------------------------

def test_momentum_needs_full_history():
    assert lt.momentum_12_1(_series(100, 0.001, 100)) is None


def test_momentum_matches_manual_computation():
    """12-1 uses close(t-21) / close(t-252) - 1 -- and nothing else."""
    closes = _series(100.0, 0.001, 300)
    expected = closes[-1 - lt.SKIP] / closes[-1 - lt.LOOKBACK] - 1.0
    assert lt.momentum_12_1(closes) == pytest.approx(expected)


def test_momentum_skips_the_most_recent_month():
    """The skip is the whole point (that window carries short-term reversal).
    A spike in the LAST month must not change the score at all."""
    a = _series(100.0, 0.001, 300)
    b = list(a)
    b[-1] = b[-2] * 1.5          # +50% on the final bar
    b[-5] = b[-6] * 0.7          # and a crash a week ago
    assert lt.momentum_12_1(a) == pytest.approx(lt.momentum_12_1(b))


def test_momentum_is_positive_for_an_uptrend_and_negative_for_a_downtrend():
    assert lt.momentum_12_1(_series(100.0, 0.002, 300)) > 0
    assert lt.momentum_12_1(_series(100.0, -0.002, 300)) < 0


def test_momentum_orders_a_strong_trend_above_a_weak_one():
    strong = lt.momentum_12_1(_series(100.0, 0.003, 300))
    weak = lt.momentum_12_1(_series(100.0, 0.0005, 300))
    assert strong > weak


# ---------------------------------------------------------------------------
# ATR
# ---------------------------------------------------------------------------

def test_atr_needs_enough_bars():
    assert lt.atr([100.0] * 5) is None


def test_atr_is_zero_on_a_flat_series():
    assert lt.atr([100.0] * 60) == pytest.approx(0.0)


def test_atr_grows_with_volatility():
    calm = lt.atr([100 + (i % 2) * 0.1 for i in range(60)])
    wild = lt.atr([100 + (i % 2) * 5.0 for i in range(60)])
    assert wild > calm


# ---------------------------------------------------------------------------
# ranking
# ---------------------------------------------------------------------------

def test_rank_universe_sorts_by_momentum_descending():
    hist = {
        "US.STRONG": _series(100.0, 0.003, 300),
        "US.FLAT": _series(100.0, 0.0, 300),
        "US.WEAK": _series(100.0, -0.002, 300),
    }
    ranked = lt.rank_universe(hist)
    assert [r["symbol"] for r in ranked] == ["US.STRONG", "US.FLAT", "US.WEAK"]


def test_rank_universe_drops_names_with_short_history():
    hist = {"US.OK": _series(100.0, 0.002, 300), "US.SHORT": _series(100.0, 0.002, 50)}
    ranked = lt.rank_universe(hist)
    assert [r["symbol"] for r in ranked] == ["US.OK"]


def test_rank_universe_returns_an_empty_list_when_nothing_is_scoreable():
    assert lt.rank_universe({"US.SHORT": [1.0, 2.0, 3.0]}) == []


# ---------------------------------------------------------------------------
# planning -- the part that must never be wrong
# ---------------------------------------------------------------------------

def _ranked(*specs):
    """specs: (symbol, momentum, close)."""
    return [{"symbol": s, "momentum": m, "close": c, "atr": c * 0.02}
            for s, m, c in specs]


def test_plan_buys_the_top_names_when_starting_flat():
    ranked = _ranked(("US.A", 0.9, 100.0), ("US.B", 0.8, 50.0), ("US.C", 0.7, 25.0))
    p = lt.plan(ranked, holdings={}, capital=10000.0, top_n=2)
    assert p["targets"] == ["US.A", "US.B"]
    assert {b["symbol"] for b in p["buys"]} == {"US.A", "US.B"}
    assert p["sells"] == []


def test_plan_sells_what_falls_out_of_the_target_set():
    ranked = _ranked(("US.A", 0.9, 100.0), ("US.B", 0.8, 50.0))
    p = lt.plan(ranked, holdings={"US.ZOMBIE": 10.0}, capital=0.0, top_n=2)
    assert p["sells"] == ["US.ZOMBIE"]


def test_plan_keeps_names_that_are_still_in_the_target_set():
    ranked = _ranked(("US.A", 0.9, 100.0), ("US.B", 0.8, 50.0))
    p = lt.plan(ranked, holdings={"US.A": 5.0}, capital=1000.0, top_n=2)
    assert p["holds"] == ["US.A"]
    # already held, so not re-bought
    assert {b["symbol"] for b in p["buys"]} == {"US.B"}


def test_plan_splits_the_budget_evenly_across_new_names():
    ranked = _ranked(("US.A", 0.9, 100.0), ("US.B", 0.8, 100.0), ("US.C", 0.7, 100.0))
    p = lt.plan(ranked, holdings={}, capital=9000.0, top_n=3)
    assert p["per_name"] == pytest.approx(3000.0)
    assert all(b["qty"] == 30 for b in p["buys"])


def test_plan_reinvests_proceeds_from_sells():
    """Freeing cash by selling must raise the budget for the new names,
    otherwise a full rebalance silently under-deploys capital."""
    # US.OLD is scoreable but ranked too low to make the top 1 -- that is the
    # realistic case, and it lets the planner price the shares being sold.
    ranked = _ranked(("US.NEW", 0.9, 100.0), ("US.OLD", 0.1, 100.0))
    p = lt.plan(ranked, holdings={"US.OLD": 50.0}, capital=0.0, top_n=1)
    assert p["sells"] == ["US.OLD"]
    # 50 shares of a $100 name = $5,000 released
    assert p["budget_total"] == pytest.approx(5000.0)
    assert p["buys"][0]["qty"] == 50


def test_plan_does_not_credit_proceeds_it_cannot_price():
    """A holding that isn't in the ranking still gets sold, but its value is
    NOT added to the budget (we cannot know the price). Under-deploy, never
    overspend."""
    ranked = _ranked(("US.NEW", 0.9, 100.0))
    p = lt.plan(ranked, holdings={"US.GONE": 50.0}, capital=1000.0, top_n=1)
    assert p["sells"] == ["US.GONE"]
    assert p["budget_total"] == pytest.approx(1000.0)


def test_plan_skips_names_that_are_too_expensive_for_one_share():
    ranked = _ranked(("US.PRICEY", 0.9, 10000.0))
    p = lt.plan(ranked, holdings={}, capital=500.0, top_n=1)
    assert p["buys"] == []


def test_plan_places_the_stop_below_entry():
    ranked = _ranked(("US.A", 0.9, 100.0))
    p = lt.plan(ranked, holdings={}, capital=10000.0, top_n=1)
    b = p["buys"][0]
    assert b["stop"] < b["ref_price"]


def test_plan_stop_uses_the_atr_multiple():
    ranked = [{"symbol": "US.A", "momentum": 0.9, "close": 100.0, "atr": 5.0}]
    p = lt.plan(ranked, holdings={}, capital=10000.0, top_n=1)
    assert p["buys"][0]["stop"] == pytest.approx(100.0 - lt.ATR_STOP_MULT * 5.0)


def test_plan_stop_never_goes_non_positive():
    """A huge ATR must not produce a negative stop price."""
    ranked = [{"symbol": "US.A", "momentum": 0.9, "close": 10.0, "atr": 50.0}]
    p = lt.plan(ranked, holdings={}, capital=10000.0, top_n=1)
    assert p["buys"][0]["stop"] > 0


def test_plan_handles_an_empty_ranking():
    p = lt.plan([], holdings={}, capital=1000.0, top_n=5)
    assert p["buys"] == [] and p["sells"] == [] and p["targets"] == []


def test_plan_ignores_zero_quantity_holdings():
    """A closed position must not be treated as held."""
    ranked = _ranked(("US.A", 0.9, 100.0))
    p = lt.plan(ranked, holdings={"US.A": 0.0, "US.B": 0.0}, capital=1000.0, top_n=1)
    assert p["sells"] == []
    assert {b["symbol"] for b in p["buys"]} == {"US.A"}


# ---------------------------------------------------------------------------
# safety defaults
# ---------------------------------------------------------------------------

def test_dry_run_is_the_default():
    """--execute must be opt-in. Guards against a refactor that flips the
    default and starts sending orders on a bare invocation."""
    args = lt.main.__doc__ or ""
    ap_default = None
    import inspect
    src = inspect.getsource(lt.main)
    assert '"--execute"' in src
    # the flag must be store_true on an option that defaults to False
    assert "action=\"store_true\", help=\"actually place orders" in src


def test_default_environment_is_simulate():
    import inspect
    src = inspect.getsource(lt.main)
    assert 'default="simulate"' in src


def test_real_env_requires_an_unlock_password():
    """--env real without --unlock must abort, never trade silently."""
    rc = lt.main(["--env", "real", "--execute", "--from-cache"])
    assert rc == 2


def test_universe_loader_reads_the_repo_config():
    syms = lt.load_universe(lt.DEFAULT_UNIVERSE)
    assert len(syms) > 100
    assert all(s.startswith("US.") for s in syms)


def test_momentum_constants_match_the_validated_configuration():
    """The signal that was validated is 12-1: 252 lookback, 21 skip."""
    assert lt.LOOKBACK == 252
    assert lt.SKIP == 21


# ---------------------------------------------------------------------------
# concentration warning
# ---------------------------------------------------------------------------

def test_concentration_warning_fires_on_a_lopsided_basket():
    """Pure momentum piles into whichever sector leads. On 2026-09-10 the top
    10 held 6 semis; the operator should be told before buying."""
    semis = ["US.NVDA", "US.AMD", "US.MU", "US.AMAT", "US.MRVL", "US.TER",
             "US.KO", "US.PG", "US.JPM", "US.XOM"]
    warn = lt._concentration_warning(semis, threshold=5)
    assert "WARNING" in warn
    assert "semis" in warn


def test_concentration_warning_is_silent_on_a_spread_basket():
    spread = ["US.KO", "US.PG", "US.JPM", "US.XOM", "US.UNP", "US.NEE", "US.WMT"]
    assert lt._concentration_warning(spread, threshold=5) == ""


def test_concentration_warning_handles_an_empty_basket():
    assert lt._concentration_warning([]) == ""
