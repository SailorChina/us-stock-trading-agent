"""Offline tests: daily_pick after-close scanner.

Everything network is injected, so the scan logic itself is tested without
touching futu: universe loading, per-style ranking, the market-filter policy,
and the dollar-sized order book.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import numpy as np
import pandas as pd
import pytest

import daily_pick as dp


def _df(n=320, base=100.0, seed=5):
    rng = np.random.default_rng(seed)
    close = np.maximum(base * np.cumprod(1 + rng.normal(0.003, 0.012, n)), 1.0)
    return _frame(close, seed)


def _pullback_df(n=320, base=100.0, seed=6):
    """Uptrend pullback that ends on an UP day (reversal needs stabilisation)."""
    rng = np.random.default_rng(seed)
    close = base * np.cumprod(1 + rng.normal(0.004, 0.01, n))
    peak = close[-7]
    for j in range(6, 1, -1):
        close[-j] = peak * (0.965 ** (7 - j))
    close[-1] = close[-2] * 1.012
    return _frame(close, seed)


def _frame(close, seed):
    rng = np.random.default_rng(seed)
    n = len(close)
    close = np.maximum(close, 1.0)
    high = close * (1 + np.abs(rng.normal(0, 0.006, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.006, n)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    volume = rng.integers(5_000_000, 20_000_000, n).astype(float)
    return pd.DataFrame({
        "time_key": pd.date_range("2023-01-01", periods=n, freq="D"),
        "open": open_, "high": high, "low": low, "close": close, "volume": volume,
    })


@pytest.fixture
def fake_data(monkeypatch, tmp_path):
    import market_regime
    monkeypatch.setattr(market_regime, "get_regime",
                        lambda: {"regime": "bull", "vix": 14.0, "status": "ok"})
    uni = tmp_path / "universe.json"
    uni.write_text(json.dumps({"symbols": ["US.A", "US.B", "US.C", "US.D"]}),
                   encoding="utf-8")
    return str(uni)


def _run(fake_data, fetcher, **kw):
    return dp.run_pick(universe_path=fake_data, include_hot=False,
                       fetcher=fetcher, **kw)


def test_scan_returns_candidates_for_every_style(fake_data):
    def fetcher(sym, bars):
        return _pullback_df(seed=8) if sym == "US.A" else _df(seed=abs(hash(sym)) % 1000)
    rep = _run(fake_data, fetcher, top=2)
    assert rep["gate"]["block_new_longs"] is False
    assert rep["conclusion"] == "scan complete - see candidates"
    assert set(rep["candidates"]) == set(dp.DEFAULT_STYLES)
    for style, rows in rep["candidates"].items():
        assert rows, f"{style} produced no candidates"
        row = rows[0]
        assert {"symbol", "score", "close", "stop_loss", "position_pct"} <= set(row)
        assert row["score"] > 0
        assert row["stop_loss"] < row["close"]


def test_scores_are_ranked_descending(fake_data):
    rep = _run(fake_data, lambda sym, bars: _df(seed=abs(hash(sym)) % 997), top=8)
    for rows in rep["candidates"].values():
        scores = [r["score"] for r in rows]
        assert scores == sorted(scores, reverse=True)


def test_bear_regime_does_not_gate_longs(fake_data, monkeypatch):
    """A market filter must NOT silently re-sample the portfolio.

    This asserted the opposite until the gate was checked. Two findings killed
    it: (1) it could never fire -- it read US.VIX / US.SPX, which futu does not
    recognise, so both came back 0 and classify_regime(0, 0) returned
    "neutral" every day; (2) even repaired it would hurt -- six market filters
    measured on this signal (21d/top-5/228 names) all lowered return AND
    significance, e.g. SPY>200d MA 44.8%->32.9% (t 2.75->1.68), SPY dd<10%
    ->36.8% (t=2.01). Same shape as Clenow's index rule.
    So a bear READING must still produce candidates.
    """
    import market_regime
    monkeypatch.setattr(market_regime, "get_regime",
                        lambda: {"regime": "bear", "vix": 32.0, "status": "ok"})
    rep = _run(fake_data, lambda sym, bars: _df(seed=abs(hash(sym)) % 997))
    assert rep["gate"]["block_new_longs"] is False
    assert rep["conclusion"] == "scan complete - see candidates"
    assert any(rows for rows in rep["candidates"].values()), \
        "a bear reading must not empty the list"


def test_regime_fn_is_injectable_so_offline_runs_never_import_futu(fake_data):
    called = []

    def fake_regime():
        called.append(1)
        return {"regime": "not_read", "note": "offline"}

    rep = _run(fake_data, lambda sym, bars: _df(seed=1), regime_fn=fake_regime)
    assert called == [1]
    assert rep["regime"]["regime"] == "not_read"


def test_low_liquidity_symbols_are_filtered_out(fake_data):
    good = _df(seed=1)
    bad = _df(seed=2)
    bad["close"] = 0.5                        # penny stock

    def fetcher(sym, bars):
        return good if sym == "US.A" else bad

    rep = _run(fake_data, fetcher)
    seen = {r["symbol"] for rows in rep["candidates"].values() for r in rows}
    assert "US.A" in seen
    assert seen <= {"US.A"}, f"low-liquidity symbols leaked through: {seen}"


# --- sector diversification -------------------------------------------------

def test_sector_cap_limits_concentration():
    """Top-N must not be one leveraged bet wearing five tickers."""
    rows = [{"symbol": s, "score": 90 - i} for i, s in enumerate(
        ["US.NVDA", "US.AMD", "US.INTC", "US.MU", "US.AMAT", "US.JPM"])]
    capped = dp._sector_cap(rows, max_per_sector=1)
    assert [r["symbol"] for r in capped] == ["US.NVDA", "US.JPM"]
    capped2 = dp._sector_cap(rows, max_per_sector=2)
    assert [r["symbol"] for r in capped2] == ["US.NVDA", "US.AMD", "US.JPM"]
    assert dp._sector_cap(rows, max_per_sector=0) == rows      # 0 disables


def test_run_pick_applies_sector_cap(monkeypatch, tmp_path):
    import market_regime
    monkeypatch.setattr(market_regime, "get_regime",
                        lambda: {"regime": "bull", "vix": 14.0, "status": "ok"})
    uni = tmp_path / "semis.json"
    uni.write_text(json.dumps({"symbols": ["US.NVDA", "US.AMD", "US.INTC", "US.MU"]}),
                   encoding="utf-8")

    def fetcher(sym, bars):
        return _pullback_df(seed=abs(hash(sym)) % 500)         # reversal setups

    rep = dp.run_pick(universe_path=str(uni), include_hot=False, top=4,
                      styles=["reversal"], max_per_sector=1, fetcher=fetcher)
    assert len(rep["candidates"]["reversal"]) <= 1, \
        "all-semis universe must not fill the list"


def test_hot_list_symbols_are_added(fake_data, monkeypatch):
    import tech_engine
    monkeypatch.setattr(tech_engine, "get_hot_list",
                        lambda market, top: {"status": "ok",
                                             "data": [{"code": "US.HOT1"},
                                                      {"code": "US.HOT2"}]})
    seen_symbols = []

    def fetcher(sym, bars):
        seen_symbols.append(sym)
        return _df(seed=abs(hash(sym)) % 900)

    dp.run_pick(universe_path=fake_data, include_hot=True, fetcher=fetcher, top=1)
    assert "US.HOT1" in seen_symbols
    assert "US.HOT2" in seen_symbols


def test_scan_survives_bad_fetches(fake_data):
    def fetcher(sym, bars):
        return None if sym == "US.B" else _df(seed=abs(hash(sym)) % 900)

    rep = _run(fake_data, fetcher, top=2)
    assert rep["scan"]["symbols_scanned"] == 4
    assert rep["scan"]["symbols_passed_filters"] == 3
    assert any(rows for rows in rep["candidates"].values())


# --- dollar-sized order book ------------------------------------------------

def test_order_sheet_is_equal_dollar_and_reports_sub_share_slots():
    """A $600 slot cannot buy a whole $1,028 share, and that must be visible."""
    rows = [
        {"symbol": "US.CHEAP", "close": 100.0, "atr_pct": 3.0},
        {"symbol": "US.PRICEY", "close": 1028.0, "atr_pct": 4.0},
    ]
    sheet = dp.order_sheet(rows, 1200.0)
    assert [o["symbol"] for o in sheet] == ["US.CHEAP", "US.PRICEY"]
    assert all(o["amount"] == 600.0 for o in sheet), "must be equal DOLLAR weight"
    assert sheet[0]["whole_share_ok"] is True            # 6 shares
    assert sheet[1]["whole_share_ok"] is False           # 0.58 shares
    assert sheet[1]["est_shares"] == pytest.approx(0.5837, abs=1e-3)
    # stop is 2x ATR below entry
    assert sheet[0]["stop_loss"] == pytest.approx(100.0 * (1 - 0.06), abs=0.01)
    assert sheet[1]["stop_loss"] == pytest.approx(1028.0 * (1 - 0.08), abs=0.01)


def test_order_sheet_handles_degenerate_input():
    assert dp.order_sheet([], 3000.0) == []
    assert dp.order_sheet([{"symbol": "US.A", "close": 10.0}], 0.0) == []
    # a nameless row with no price must not raise -- it just cannot be sized
    out = dp.order_sheet([{"symbol": "US.A", "close": 0.0}], 100.0)
    assert out[0]["est_shares"] == 0.0 and out[0]["whole_share_ok"] is False


def test_capital_puts_a_book_in_the_report(fake_data):
    rep = _run(fake_data, lambda sym, bars: _df(seed=abs(hash(sym)) % 997),
               top=2, capital=3000.0)
    book = rep["book"]
    assert book["style"] == dp.DEFAULT_STYLES[0]
    assert book["capital"] == 3000.0
    assert book["orders"], "capital must produce orders"
    assert sum(o["amount"] for o in book["orders"]) == pytest.approx(3000.0, abs=1.0)


def test_no_capital_means_no_book(fake_data):
    rep = _run(fake_data, lambda sym, bars: _df(seed=abs(hash(sym)) % 997))
    assert rep["book"] == {}


def test_cache_fetcher_reads_the_offline_cache(tmp_path):
    """--from-cache is the only way to run the pipeline without OpenD."""
    (tmp_path / "US_TEST.csv").write_text(
        "time_key,open,high,low,close,volume,last_close\n"
        + "\n".join(f"2026-01-{i+1:02d} 00:00:00,1,1,1,{100+i},1000,1" for i in range(10)),
        encoding="utf-8")
    fetch = dp._cache_fetcher(str(tmp_path))
    df = fetch("US.TEST", 5)
    assert list(df["close"]) == [105.0, 106.0, 107.0, 108.0, 109.0], "must tail(bars)"
    assert fetch("US.MISSING", 5) is None


# --- rate-limited fetching --------------------------------------------------

def test_paced_fetcher_retries_a_none_once():
    """A None from the API is USUALLY the rate limit, not a dead ticker."""
    calls = []

    def fetch(sym, bars):
        calls.append(sym)
        return None if len(calls) == 1 else "df"

    f = dp._PacedFetcher(fetch=fetch, cooldown_s=0.0)
    assert f("US.A", 800) == "df"
    assert calls == ["US.A", "US.A"], "must retry the SAME symbol"
    assert f.cooldowns_used == 1
    assert f.failed == 0


def test_paced_fetcher_gives_up_so_dead_universes_do_not_sleep_forever():
    calls = []

    def fetch(sym, bars):
        calls.append(sym)
        return None

    f = dp._PacedFetcher(fetch=fetch, cooldown_s=0.0, max_cooldowns=2)
    for s in ("US.A", "US.B", "US.C"):
        assert f(s, 800) is None
    assert f.cooldowns_used == 2, "cooldowns must be capped"
    assert calls == ["US.A", "US.A", "US.B", "US.B", "US.C"], \
        "after the cap the remaining names are tried once, not slept on"
    assert f.failed == 3


def test_paced_fetcher_spaces_requests_inside_a_window():
    """30 calls / 30s is the budget; a 3rd call in a tiny window must wait."""
    import time as _t
    calls = []
    f = dp._PacedFetcher(fetch=lambda s, b: calls.append(s) or "df",
                         max_per_window=2, window_s=0.3, cooldown_s=0.0)
    t0 = _t.monotonic()
    for s in ("US.A", "US.B", "US.C"):
        f(s, 800)
    assert len(calls) == 3
    assert _t.monotonic() - t0 >= 0.25, "the third call must be paced, not fired"


def test_scan_separates_unfetchable_from_filtered_out(fake_data, monkeypatch):
    """Conflating these hid a broken online path that gutted the universe.

    The online run used to report "228 scanned, 48 passed, 180 dropped", which
    reads like a strict liquidity filter. In fact 180 FETCHES had been refused
    by the rate limit, so the candidate list came from the surviving handful and
    disagreed with the offline list. The counters must be distinct.
    """
    good = _df(seed=1)
    penny = _df(seed=2)
    penny["close"] = 0.5                       # passes fetch, fails liquidity

    def fetcher(sym, bars):
        if sym == "US.A":
            return good
        if sym == "US.B":
            return penny
        return None                            # US.C, US.D: fetch refused

    rep = _run(fake_data, fetcher)
    scan = rep["scan"]
    assert scan["symbols_scanned"] == 4
    assert scan["symbols_passed_filters"] == 1
    assert scan["symbols_filtered_out"] == 1
    assert scan["symbols_unfetchable"] == 2
    assert scan["symbols_dropped"] == 3


# --- history-kline BUDGET preflight -----------------------------------------

def test_quota_preflight_counts_only_symbols_not_already_covered():
    """Re-requesting a symbol inside the 30-day window is FREE.

    So the cost of a scan is not len(universe); it is the number of names not
    already covered. Getting this wrong either refuses a scan that was actually
    affordable or, worse, waves through one that is not.
    """
    q = dp.history_quota_preflight(
        ["US.A", "US.B", "US.C"],
        quota=(240, 60, ["US.A", "US.B"]))
    assert q["checked"] is True
    assert q["covered"] == 2
    assert q["needs_charge"] == 1
    assert q["ok"] is True
    assert "shortfall" not in q


def test_quota_preflight_refuses_a_scan_the_budget_cannot_cover():
    """A 228-name scan needs 228 budget; on the base 100 tier it is impossible.

    That failure is quantitative and silent -- a partial universe with no
    exception -- so it has to be caught before the fetch, not deduced from a
    suspiciously short candidate list afterwards.
    """
    # 4 names, only 1 covered -> 3 to charge, and 5 remain: this FITS
    q = dp.history_quota_preflight(["US.A", "US.B", "US.C", "US.D"],
                                   quota=(295, 5, ["US.A"]))
    assert q["needs_charge"] == 3 and q["remaining"] == 5
    assert q["ok"] is True

    # 4 names, none covered -> 4 to charge, but only 2 remain: short by 2
    q2 = dp.history_quota_preflight(["US.A", "US.B", "US.C", "US.D"],
                                    quota=(298, 2, []))
    assert q2["needs_charge"] == 4 and q2["ok"] is False and q2["shortfall"] == 2

    # an empty covered list is the worst case: the whole scan must be charged
    q3 = dp.history_quota_preflight(list("ABCDEFGHIJ"), quota=(90, 100, []))
    assert q3["needs_charge"] == 10 and q3["ok"] is True


def test_run_pick_surfaces_a_quota_shortfall(fake_data):
    """A budget shortfall must be loud, not folded into "few candidates"."""
    def quota_fn(symbols):
        return dp.history_quota_preflight(symbols, quota=(298, 2, []))

    rep = _run(fake_data, lambda sym, bars: _df(seed=1), top=2, quota_fn=quota_fn)
    assert rep["scan"]["quota"]["ok"] is False
    assert "PARTIAL universe" in rep["scan"]["quota_warning"]
    assert "QUOTA" in dp._console(rep).upper() or \
           "BUDGET" in dp._console(rep).upper()


def test_run_pick_offline_does_not_touch_the_quota(fake_data):
    rep = _run(fake_data, lambda sym, bars: _df(seed=1), top=2)
    assert rep["scan"]["quota"]["checked"] is False


def test_quota_preflight_accepts_the_detail_payload_shape():
    """get_detail=True returns a list of DICTS, not code strings.

    The live payload is [{"code": "US.NEM", "name": "纽曼矿业"}, ...]. Feeding
    that straight to set() raises "unhashable type: dict", which the caller's
    try/except turns into "{'checked': False}" -- i.e. the budget silently goes
    unchecked, which is the same failure shape as everything else in this file.
    """
    q = dp.history_quota_preflight(
        ["US.A", "US.B"], quota=(10, 290, [{"code": "US.A", "name": "x"}]))
    assert q["checked"] is True
    assert q["covered"] == 1 and q["needs_charge"] == 1
    # plain strings must keep working too
    q2 = dp.history_quota_preflight(["US.A"], quota=(10, 290, ["US.A"]))
    assert q2["covered"] == 1 and q2["needs_charge"] == 0
    # and an empty detail list (get_detail=False) means nothing is covered
    q3 = dp.history_quota_preflight(["US.A"], quota=(10, 290, []))
    assert q3["covered"] == 0 and q3["needs_charge"] == 1


# --- bar completeness -------------------------------------------------------

def test_bar_completeness_warning_flags_an_open_session():
    """A partial intraday bar must not pass silently as a close.

    Daily bars carry the session's own date; during the US session the last bar
    is a PARTIAL day being fed into 12-1 momentum as though it were final.
    Nothing errors -- the signal is just quietly wrong, which is worse.
    """
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    msg = dp._bar_completeness_warning(today)
    # only meaningful while the US session is open; skip otherwise
    if datetime.now(timezone.utc).hour < 21:
        assert "INCOMPLETE" in msg
    assert dp._bar_completeness_warning("2020-01-02") == ""
    assert dp._bar_completeness_warning(None) == ""
