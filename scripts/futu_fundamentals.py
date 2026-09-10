#!/usr/bin/env python3
"""futu_fundamentals -- point-in-time quarterly fundamentals from Futu OpenAPI.

Why this exists: the project had no fundamental data at all, so the only thing
ever measured as "quality" was a LOW-VOLATILITY PROXY, which tested negative
(t=-2.42). Real quality (ROE/ROIC/margins) and value (E/P, B/P) could not be
computed. The Futu API exposes them per symbol, 29 fields per quarter, 96
quarters deep, with a next_key to page back -- enough for a genuine
point-in-time panel.

Two things this module is careful about:

1. LOOK-AHEAD. A quarter ending 2024-03-31 is not knowable on 2024-04-01. Every
   record therefore carries BOTH the period end date and an `available_date`
   (period end + REPORT_LAG_DAYS). Anything consuming this must filter on
   available_date, never on the period date.

2. FETCH COST. Fundamentals are per-symbol only: the screener cannot filter or
   retrieve them for the US market (documented sparse coverage, and retrieves
   can come back None even when the filter matched). So this is ~1.8s per
   symbol per page and has to be cached, not recomputed.

Usage:
    python scripts/futu_fundamentals.py --build            # fetch missing symbols
    python scripts/futu_fundamentals.py --build --force     # refetch everything
    python scripts/futu_fundamentals.py --status            # cache coverage
    python scripts/futu_fundamentals.py --symbol US.AAPL    # inspect one name
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import time
from typing import Dict, List, Optional

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_SCRIPT_DIR)
DEFAULT_UNIVERSE = os.path.join(ROOT, "configs", "universe_us.json")
CACHE_DIR = os.path.join(ROOT, "data", "_fund_cache")
SKILL_SCRIPTS = os.path.expanduser(
    os.path.join("~", ".workbuddy", "skills", "futuapi", "scripts"))

# A quarter is published weeks after it ends. 45 days is deliberately
# conservative: too early and the panel silently leaks the future, too late and
# the factor just looks stale. Not tuned -- chosen to be safe.
REPORT_LAG_DAYS = 45


def _writable_dir(*candidates: str) -> str:
    """First candidate that accepts a real write.

    Probed by actually creating a file: os.access() reports writable under
    sandboxes that then refuse the write. The repo lives under Desktop, whose
    writes are intermittently denied, so the fetcher would die without this
    fallback.

    The probe file is deleted on a BEST-EFFORT basis. Requiring the delete to
    succeed was a real bug: this host's safe-delete shim refuses os.remove, so
    a perfectly writable directory was being rejected and the code fell through
    to the temp dir for no reason. Writing is the only thing that actually
    matters here.
    """
    for cand in candidates:
        probe = os.path.join(cand, ".write_probe")
        try:
            os.makedirs(cand, exist_ok=True)
            with open(probe, "w", encoding="utf-8") as f:
                f.write("ok")
        except Exception:
            continue
        try:
            os.remove(probe)
        except Exception:
            pass          # delete shim may block us; the write already proved it
        return cand
    return tempfile.gettempdir()


LOG_DIR = _writable_dir(os.path.join(ROOT, "data", "_futu_log"),
                        os.path.join(tempfile.gettempdir(), "_futu_log"))
SHIM = os.path.join(tempfile.gettempdir(), "_futu_fund_shim.py")

# MainIndex (--statement-type 4) field ids -> stable names. Verified against the
# live structure_list; the ids are stable across quarters and symbols.
FIELDS = {
    14002: "gross_margin",
    14003: "operating_margin",
    14004: "ebit_margin",
    14005: "net_margin",
    14006: "ebitda_margin",
    14007: "tax_rate",
    14009: "rd_to_revenue",
    14017: "lt_debt_to_equity",
    14018: "financial_leverage",
    14019: "interest_debt_ratio",
    14020: "current_ratio",
    14021: "quick_ratio",
    14024: "receivables_turnover",
    14025: "inventory_turnover",
    14028: "asset_turnover",
    14029: "roe",
    14030: "roa",
    14031: "roic",
    14032: "fcf_to_revenue",
    14033: "fcf_to_net_income",
    14050: "equity_ratio",
}

WRAPPER = SHIM


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------

def _wrapper_path() -> str:
    """Return the futu-log shim path, writing it if needed.

    futu's FTLog builds its path from os.getenv("appdata") at import time and
    opens the file immediately. With %APPDATA% unwritable the call dies with no
    traceback. The shim must patch os.getenv BEFORE futu is imported, so it runs
    the target script through runpy rather than importing it.
    """
    p = WRAPPER
    with open(p, "w", encoding="utf-8") as f:
        f.write(
            "import os, runpy, sys\n"
            "LOG = r'%s'\n"
            "os.makedirs(LOG, exist_ok=True)\n"
            "_real = os.getenv\n"
            "os.getenv = lambda k, d=None: (LOG if (k and k.lower() == 'appdata') else _real(k, d))\n"
            "os.environ['APPDATA'] = LOG\n"
            "ROOT = r'%s'\n"
            "t = os.path.join(ROOT, sys.argv[1].replace('/', os.sep))\n"
            "sys.argv = [os.path.basename(t)] + sys.argv[2:]\n"
            "runpy.run_path(t, run_name='__main__')\n"
            % (LOG_DIR, SKILL_SCRIPTS))
    return p


def _call_skill(script: str, args: List[str]) -> dict:
    """Run one futuapi skill script and return its JSON payload."""
    os.makedirs(LOG_DIR, exist_ok=True)
    py = sys.executable
    r = subprocess.run([py, _wrapper_path(), script] + args,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=180)
    # Both the SDK connection log and the payload go to stdout, and the
    # disconnect log is usually LAST -- so scan backwards for the JSON line.
    for line in reversed((r.stdout or "").split("\n")):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except Exception:
                continue
    return {"_error": ((r.stdout or "") + (r.stderr or ""))[-300:]}


def _periods_from_data(data: dict) -> List[dict]:
    """Parse one API response page into period records."""
    data = data or {}
    struct = {s.get("field_id"): s.get("display_name")
              for s in (data.get("structure_list") or [])}
    out = []
    for rep in (data.get("report_list") or []):
        end = rep.get("date_time_str")
        if not end:
            continue
        try:
            end_d = dt.date.fromisoformat(end[:10])
        except Exception:
            continue
        vals = {}
        for item in (rep.get("item_list") or rep.get("items") or []):
            fid = item.get("field_id")
            name = FIELDS.get(fid) or struct.get(fid)
            v = item.get("data", item.get("value"))
            if name and v is not None:
                try:
                    vals[name] = float(v)
                except (TypeError, ValueError):
                    pass
        out.append({
            "period_text": rep.get("period_text"),
            "period_end": end_d.isoformat(),
            "available_date": (end_d + dt.timedelta(days=REPORT_LAG_DAYS)).isoformat(),
            "financial_type": rep.get("financial_type"),
            "fiscal_year": rep.get("fiscal_year"),
            "values": vals,
        })
    return out


def _periods_from(payload: dict) -> List[dict]:
    return _periods_from_data(payload.get("data") or {})


# ---------------------------------------------------------------------------
# direct SDK path
# ---------------------------------------------------------------------------
# Calling the SDK in-process instead of spawning the futuapi script once per
# page is not a micro-optimisation: a subprocess pays Python start-up, a fresh
# `import futu`, and a NEW OpenD handshake on every page. Measured here at ~10s
# per symbol (5 pages); reusing one context brings it to ~2-3s, which is the
# difference between ~35 minutes and ~10 for the whole universe.

_CTX = None
_APPLIED = False

# OpenD enforces 30 financial-statement requests per 30 seconds, and it does so
# by FAILING the request, not by queueing it. Measured: an unthrottled burst
# failed all 228 symbols in about a second. So pace requests just under the
# documented ceiling -- 1368 requests (228 names x 6 pages) then takes ~23
# minutes, which is the rate limit's price, not the SDK's.
MIN_REQUEST_INTERVAL_S = 1.05
_last_request = [0.0]


def _throttle() -> None:
    gap = time.time() - _last_request[0]
    if gap < MIN_REQUEST_INTERVAL_S:
        time.sleep(MIN_REQUEST_INTERVAL_S - gap)
    _last_request[0] = time.time()


def _apply_log_redirect() -> None:
    """Point the futu SDK log at a writable dir.

    Must happen BEFORE the first `import futu`: ft_logger runs `FTLog()` at
    module import time and opens the log file right there. With %APPDATA%
    unwritable that raises PermissionError, or kills the process with no
    traceback at all. Done lazily (not at import) so merely importing this
    module never mutates global env for a test.
    """
    global _APPLIED
    if _APPLIED:
        return
    _real = os.getenv

    def _patched(key, default=None):
        if key and key.lower() == "appdata":
            return LOG_DIR
        return _real(key, default)

    os.makedirs(LOG_DIR, exist_ok=True)
    os.getenv = _patched
    os.environ["APPDATA"] = LOG_DIR
    _APPLIED = True


def _ctx():
    """One lazily created quote context, reused for every call."""
    global _CTX
    if _CTX is not None:
        return _CTX
    _apply_log_redirect()
    import futu  # noqa: E402  (import must follow the redirect)
    futu.SysConfig.set_all_thread_daemon(True)   # else the process hangs on exit
    _CTX = futu.OpenQuoteContext(host="127.0.0.1", port=11111)
    return _CTX


def close() -> None:
    global _CTX
    if _CTX is not None:
        try:
            _CTX.close()
        except Exception:
            pass
        _CTX = None


def fetch_symbol_direct(symbol: str, max_pages: int = 6) -> dict:
    """Page a symbol's MainIndex history over one shared connection.

    Paced to stay under OpenD's 30-per-30s statement limit, with one retry
    after a cooldown if the limit is hit anyway (a shared OpenD means other
    clients consume the same budget).
    """
    ctx = _ctx()
    seen: Dict[str, dict] = {}
    key = None
    for _ in range(max_pages):
        kw = dict(statement_type=4, num=12)
        if key:
            kw["next_key"] = key
        ret, data = None, None
        for attempt in (1, 2):
            _throttle()
            ret, data = ctx.get_financials_statements(symbol, **kw)
            if ret == 0:
                break
            msg = str(data)
            if "频率" in msg or "too frequent" in msg.lower():
                if attempt == 1:
                    time.sleep(31.0)
                    continue
            break
        if ret != 0:
            return {"symbol": symbol, "error": str(data)[:200], "periods": []}
        reps = _periods_from_data(data)
        if not reps:
            break
        for r in reps:
            seen[r["period_text"]] = r
        key = (data or {}).get("next_key")
        if not key or key == "-1":
            break
    periods = sorted(seen.values(), key=lambda r: r["period_end"])
    return {"symbol": symbol, "fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
            "report_lag_days": REPORT_LAG_DAYS, "periods": periods}


def fetch_symbol(symbol: str, max_pages: int = 6) -> Optional[dict]:
    """Prefer the direct SDK call; fall back to the skill script if it breaks.

    The fallback exists because the direct path depends on the SDK version's
    method signature, and the skill scripts are maintained upstream. It is
    slower, not different.
    """
    try:
        return fetch_symbol_direct(symbol, max_pages)
    except Exception as e:
        fallback = _fetch_symbol_subprocess(symbol, max_pages)
        if fallback is not None:
            fallback["direct_error"] = "%s: %s" % (type(e).__name__, e)
            return fallback
        return {"symbol": symbol, "error": str(e)[:200], "periods": []}


def _fetch_symbol_subprocess(symbol: str, max_pages: int = 6) -> Optional[dict]:
    """Fallback: page via the futuapi skill script, one process per page."""
    seen: Dict[str, dict] = {}
    key = None
    for _ in range(max_pages):
        args = [symbol, "--statement-type", "4", "--num", "12", "--json"]
        if key:
            args += ["--next-key", key]
        payload = _call_skill("quote/get_financials_statements.py", args)
        if "_error" in payload:
            return {"symbol": symbol, "error": payload["_error"][:200], "periods": []}
        reps = _periods_from(payload)
        if not reps:
            break
        for r in reps:
            seen[r["period_text"]] = r
        key = (payload.get("data") or {}).get("next_key")
        if not key:
            break
    periods = sorted(seen.values(), key=lambda r: r["period_end"])
    return {"symbol": symbol, "fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
            "report_lag_days": REPORT_LAG_DAYS, "periods": periods}


# ---------------------------------------------------------------------------
# cache
# ---------------------------------------------------------------------------

def cache_path(symbol: str) -> str:
    return os.path.join(CACHE_DIR, symbol.replace(".", "_") + ".json")


def load_cache() -> Dict[str, dict]:
    out = {}
    if not os.path.isdir(CACHE_DIR):
        return out
    for f in sorted(os.listdir(CACHE_DIR)):
        if not f.endswith(".json"):
            continue
        try:
            d = json.load(open(os.path.join(CACHE_DIR, f), encoding="utf-8"))
            if d.get("periods"):
                out[d["symbol"]] = d
        except Exception:
            continue
    return out


def build(symbols: List[str], max_pages: int = 6, force: bool = False,
          sleep_s: float = 0.0) -> dict:
    os.makedirs(CACHE_DIR, exist_ok=True)
    stats = {"fetched": 0, "skipped": 0, "failed": 0, "empty": 0, "periods": 0}
    t0 = time.time()
    for i, sym in enumerate(symbols, 1):
        p = cache_path(sym)
        if os.path.exists(p) and not force:
            stats["skipped"] += 1
            continue
        rec = fetch_symbol(sym, max_pages)
        if rec is None or rec.get("error"):
            stats["failed"] += 1
            print("[%3d/%d] %-10s FAIL %s" % (i, len(symbols), sym,
                                              (rec or {}).get("error", "?")[:60]),
                  flush=True)
            continue
        if not rec["periods"]:
            stats["empty"] += 1
            print("[%3d/%d] %-10s no periods" % (i, len(symbols), sym), flush=True)
        else:
            json.dump(rec, open(p, "w", encoding="utf-8"), ensure_ascii=False)
            stats["fetched"] += 1
            stats["periods"] += len(rec["periods"])
            if stats["fetched"] % 10 == 1:
                el = time.time() - t0
                print("[%3d/%d] %-10s %3d periods  oldest %s  (%.0fs elapsed)"
                      % (i, len(symbols), sym, len(rec["periods"]),
                         rec["periods"][0]["period_end"], el), flush=True)
        if sleep_s:
            time.sleep(sleep_s)
    stats["elapsed_s"] = round(time.time() - t0, 1)
    return stats


def load_universe(path: str) -> List[str]:
    d = json.load(open(path, encoding="utf-8"))
    syms = d.get("symbols", d) if isinstance(d, dict) else d
    return [s for s in syms if isinstance(s, str) and s.startswith("US.")]


# ---------------------------------------------------------------------------
# point-in-time access
# ---------------------------------------------------------------------------

def latest_asof(rec: dict, as_of: str, fields: Optional[List[str]] = None) -> Dict[str, float]:
    """Fundamentals known as of `as_of` -- the only correct way to read this.

    Filters on available_date, so a quarter that has ended but not yet been
    published is invisible. Returns the most recent qualifying quarter's values.
    """
    best = None
    for p in rec.get("periods", []):
        if p["available_date"] <= as_of:
            if best is None or p["period_end"] > best["period_end"]:
                best = p
    if best is None:
        return {}
    vals = best["values"]
    return {k: v for k, v in vals.items() if not fields or k in fields}


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Futu point-in-time fundamentals cache")
    ap.add_argument("--build", action="store_true", help="fetch symbols missing from the cache")
    ap.add_argument("--force", action="store_true", help="refetch even if cached")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--symbol", default="")
    ap.add_argument("--universe", default=DEFAULT_UNIVERSE)
    ap.add_argument("--pages", type=int, default=6, help="12 quarters per page")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args(argv)

    symbols = load_universe(args.universe)
    if args.limit:
        symbols = symbols[:args.limit]

    if args.status or (not args.build and not args.symbol):
        cache = load_cache()
        print("cache dir : %s" % CACHE_DIR)
        print("universe  : %d symbols" % len(symbols))
        print("cached    : %d symbols" % len(cache))
        if cache:
            ps = [len(v["periods"]) for v in cache.values()]
            ends = [v["periods"][0]["period_end"] for v in cache.values() if v["periods"]]
            print("periods   : min %d / median %d / max %d per symbol"
                  % (min(ps), sorted(ps)[len(ps) // 2], max(ps)))
            print("oldest    : %s" % (min(ends) if ends else "-"))
            have = set(cache)
            missing = [s for s in symbols if s not in have]
            print("missing   : %d%s" % (len(missing),
                                        ("  e.g. " + ", ".join(missing[:6])) if missing else ""))
        return 0

    if args.symbol:
        rec = fetch_symbol(args.symbol, args.pages)
        for p in (rec or {}).get("periods", [])[-6:]:
            print("%-10s end=%s avail=%s %s" % (
                p["period_text"], p["period_end"], p["available_date"],
                {k: round(v, 2) for k, v in list(p["values"].items())[:6]}))
        return 0

    stats = build(symbols, max_pages=args.pages, force=args.force)
    print("fetched=%d skipped=%d failed=%d empty=%d periods=%d elapsed=%.0fs"
          % (stats["fetched"], stats["skipped"], stats["failed"], stats["empty"],
             stats["periods"], stats["elapsed_s"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
