#!/usr/bin/env python3
"""Shared pacing + pagination for futu history fetches.

Why this module exists: daily_pick and live_trader each had their own fetch, and
duplicate fetch code is exactly how they silently diverged.

live_trader asked for ONE request with a date range:

    ctx.request_history_kline(sym, start=<504 days ago>, end=<today>,
                              max_count=315)

and futu returned the FIRST 315 bars of that range, not the last. Verified
directly: for [2025-04-24 .. 2026-09-10] it returned 315 rows ending
**2026-07-27** -- six weeks short of the scan date. No error, no warning. The
consequence was a top-5 picked on stale prices (MU/INTC/MRVL/AMAT/AMD) that
disagreed with the correct one (MU/WDC/STX/INTC/DELL) from the same signal, and
real orders were placed from it.

Two independent limits also have to be respected, and they are different things:
  * FREQUENCY: ~60 calls / 30s, over which every call fails immediately with no
    exception. Handle by pacing + a cooldown retry.
  * BUDGET: 1 per distinct symbol per rolling 30 days, tiered by account size.
    Re-requesting a symbol inside the window is free. Not handled here; see
    daily_pick.history_quota_preflight, which checks it before scanning.
"""
from __future__ import annotations

import collections
import threading
import time
from typing import Optional

# Pacing, from measurement (see docstring): a cold burst succeeds for ~40 calls
# and then everything fails until the window rolls. Stay under half the limit.
MAX_PER_WINDOW = 30
WINDOW_S = 30.0
COOLDOWN_S = 31.0          # a full window, so the retry is not refused
FETCH_TIMEOUT_S = 12.0     # one bad symbol must not hang the whole scan


def fetch_kline_guarded(symbol: str, bars: int, timeout_s: float = FETCH_TIMEOUT_S):
    """tech_engine.fetch_kline in a daemon thread, so one bad symbol cannot hang.

    tech_engine.fetch_kline PAGES until it has `bars` rows and derives an explicit
    start date, which is why it returns current data where a single ranged
    request does not. Reusing it is deliberate: one implementation, already
    exercised by the whole test suite.
    """
    from tech_engine import fetch_kline

    box: dict = {}

    def _run():
        try:
            box["df"] = fetch_kline(symbol, "1d", bars)
        except Exception as exc:      # noqa: BLE001 - reported via the box
            box["err"] = exc

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=timeout_s)
    if t.is_alive():
        return None
    if "err" in box:
        return None
    return box.get("df")


class PacedFetcher:
    """Rate-limit-aware, paginating history fetch.

    An unpaced whole-universe scan does NOT fail loudly, it fails QUANTITATIVELY:
    daily_pick reported "228 scanned, 48 passed, 180 dropped" and live_trader
    "scored 60 of 228", both of which read like filters rather than refusals, and
    both of which produce a plausible-looking list from a gutted universe.
    """

    def __init__(self, fetch=None, max_per_window: int = MAX_PER_WINDOW,
                 window_s: float = WINDOW_S, cooldown_s: float = COOLDOWN_S,
                 max_cooldowns: int = 6):
        self._fetch = fetch or fetch_kline_guarded
        self._max = max_per_window
        self._window = window_s
        self._cooldown = cooldown_s
        self._max_cooldowns = max_cooldowns
        self._times: collections.deque = collections.deque()
        self.cooldowns_used = 0
        self.failed = 0

    def _throttle(self) -> None:
        now = time.monotonic()
        while self._times and now - self._times[0] > self._window:
            self._times.popleft()
        if len(self._times) >= self._max:
            pause = self._window - (now - self._times[0]) + 0.05
            if pause > 0:
                time.sleep(pause)
            now = time.monotonic()
            while self._times and now - self._times[0] > self._window:
                self._times.popleft()
        self._times.append(now)

    def __call__(self, symbol: str, bars: int):
        self._throttle()
        df = self._fetch(symbol, bars)
        if df is not None:
            return df
        # A None here is USUALLY the rate limit, not a dead ticker. Cool down a
        # full window and retry the same name once. The cap matters: without it a
        # universe full of genuinely unavailable symbols becomes an hour of sleep.
        if self.cooldowns_used >= self._max_cooldowns:
            self.failed += 1
            return None
        self.cooldowns_used += 1
        time.sleep(self._cooldown)
        self._times.clear()
        self._throttle()
        df = self._fetch(symbol, bars)
        if df is None:
            self.failed += 1
        return df


def closes_from(df) -> Optional[list]:
    """DataFrame -> [closes, oldest first], or None if unusable."""
    if df is None or len(df) == 0 or "close" not in df.columns:
        return None
    return [float(x) for x in df["close"].tolist()]


def last_bar_date(df) -> Optional[str]:
    if df is None or len(df) == 0 or "time_key" not in df.columns:
        return None
    return str(df["time_key"].iloc[-1])[:10]
