"""Tests for futu_pacing: the shared, paginating, rate-limit-aware fetch.

These exist because two fetch implementations once disagreed. live_trader asked
for a date range in a single request and futu answered with the FIRST max_count
bars, so its series ended 2026-07-27 while the scan ran on 2026-09-10 -- and it
picked a different top-5 from the same signal, with no error anywhere. The
freshness guard that prevents a repeat is tested here too.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import pandas as pd
import pytest

import futu_pacing as fp


def _df(bars: int, last_date: str, base: float = 100.0):
    """A daily frame whose LAST bar is `last_date`."""
    dates = pd.date_range(end=pd.Timestamp(last_date), periods=bars, freq="D")
    close = [base + i for i in range(bars)]
    return pd.DataFrame({"time_key": dates, "close": close})


# --- helpers ----------------------------------------------------------------

def test_closes_from_returns_oldest_first_or_none():
    df = _df(5, "2026-09-10")
    assert fp.closes_from(df) == [100.0, 101.0, 102.0, 103.0, 104.0]
    assert fp.closes_from(None) is None
    assert fp.closes_from(pd.DataFrame()) is None
    assert fp.closes_from(pd.DataFrame({"close": []})) is None
    # a frame without a close column is unusable, not a crash
    assert fp.closes_from(pd.DataFrame({"time_key": [1]})) is None


def test_last_bar_date_reports_the_newest_bar():
    assert fp.last_bar_date(_df(3, "2026-09-10")) == "2026-09-10"
    assert fp.last_bar_date(_df(3, "2026-07-27")) == "2026-07-27"
    assert fp.last_bar_date(None) is None
    assert fp.last_bar_date(pd.DataFrame({"close": [1]})) is None


# --- pacing -----------------------------------------------------------------

def test_paced_fetcher_retries_a_none_once():
    """A None is USUALLY the rate limit, not a dead ticker."""
    calls = []

    def fetch(sym, bars):
        calls.append(sym)
        return None if len(calls) == 1 else "df"

    f = fp.PacedFetcher(fetch=fetch, cooldown_s=0.0)
    assert f("US.A", 800) == "df"
    assert calls == ["US.A", "US.A"], "must retry the SAME symbol"
    assert f.cooldowns_used == 1 and f.failed == 0


def test_paced_fetcher_caps_cooldowns_so_a_dead_universe_cannot_sleep_forever():
    calls = []

    def fetch(sym, bars):
        calls.append(sym)
        return None

    f = fp.PacedFetcher(fetch=fetch, cooldown_s=0.0, max_cooldowns=2)
    for s in ("US.A", "US.B", "US.C"):
        assert f(s, 800) is None
    assert f.cooldowns_used == 2
    assert calls == ["US.A", "US.A", "US.B", "US.B", "US.C"]
    assert f.failed == 3


def test_paced_fetcher_spaces_requests_inside_a_window():
    import time as _t
    calls = []
    f = fp.PacedFetcher(fetch=lambda s, b: calls.append(s) or "df",
                        max_per_window=2, window_s=0.3, cooldown_s=0.0)
    t0 = _t.monotonic()
    for s in ("US.A", "US.B", "US.C"):
        f(s, 800)
    assert len(calls) == 3
    assert _t.monotonic() - t0 >= 0.25, "the third call must be paced"


# --- the freshness guard that would have caught the stale-data bug -----------

def test_live_trader_drops_and_reports_stale_bars(capsys):
    """A series ending six weeks ago must be dropped, not scored.

    This is the exact failure that produced real orders from a wrong top-5: the
    fetch returned 315 bars ending 2026-07-27 for a scan run on 2026-09-10, and
    nothing complained.
    """
    import live_trader as lt

    def fetcher(sym, bars):
        return _df(300, "2026-07-27") if sym == "US.STALE" else _df(300, "2026-09-10")

    out = lt.fetch_closes(["US.STALE", "US.FRESH"], from_cache=False, ctx=None,
                          max_stale_days=10, fetcher=fetcher)
    assert "US.FRESH" in out
    assert "US.STALE" not in out, "a stale series must never reach the signal"
    printed = capsys.readouterr().out
    assert "STALE" in printed and "US.STALE" in printed, printed


def test_live_trader_keeps_a_fresh_series(capsys):
    import live_trader as lt

    def fetcher(sym, bars):
        return _df(300, "2026-09-10")

    out = lt.fetch_closes(["US.A"], from_cache=False, ctx=None,
                          max_stale_days=10, fetcher=fetcher)
    assert "US.A" in out
    assert "STALE" not in capsys.readouterr().out
