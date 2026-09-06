#!/usr/bin/env python3
"""Agent environment health check"""
import json, sys, subprocess, os
from datetime import datetime

def check_python():
    return {"python": sys.version, "version_info": sys.version_info[:3]}

def check_packages():
    pkg_map = {"futu-api": "futu", "akshare": "akshare", "pandas": "pandas", "numpy": "numpy", "scipy": "scipy"}
    result = {}
    for pkg, mod_name in pkg_map.items():
        try:
            mod = __import__(mod_name)
            ver = getattr(mod, "__version__", "unknown")
            result[pkg] = {"installed": True, "version": ver}
        except ImportError:
            result[pkg] = {"installed": False, "version": None}
    return result

def check_futu_opend():
    import socket
    host = "127.0.0.1"
    port = 11111
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        r = s.connect_ex((host, port))
        s.close()
        return {"reachable": r == 0, "port": port}
    except Exception as e:
        return {"reachable": False, "error": str(e)}

def check_futu_basic():
    """Check if Futu Basic subscription is active by testing a quote call."""
    import threading
    result = {"basic_active": False, "note": "timeout"}

    def _check():
        try:
            from futu import OpenQuoteContext, RET_OK
            with OpenQuoteContext() as ctx:
                ret, data = ctx.get_stock_quote(["US.SPY"])
                if ret == RET_OK and data is not None and len(data) > 0:
                    result["basic_active"] = True
                    result["price"] = float(data.iloc[0].get("last_price", 0))
                else:
                    result["basic_active"] = False
                    result["ret"] = ret
        except Exception as e:
            result["basic_active"] = False
            result["error"] = str(e)

    t = threading.Thread(target=_check, daemon=True)
    t.start()
    t.join(timeout=5)
    if t.is_alive():
        return {"basic_active": False, "error": "timeout after 5s"}
    return result

def check_news_api():
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://ai-news-search.futunn.com/news_search?keyword=NVDA&size=1&sort_type=2&lang=zh-CN",
            headers={"User-Agent": "agent-diagnose/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            count = len(data.get("data", []))
            return {"news_api_ok": True, "news_count": count}
    except Exception as e:
        return {"news_api_ok": False, "error": str(e)}

def check_yahoo_finance():
    """Check Yahoo Finance API availability as fallback data source."""
    import urllib.request, json, time
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                "https://query1.finance.yahoo.com/v8/finance/chart/AAPL?interval=1d&period=5d",
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            result = data.get("chart", {}).get("result")
            if result and result[0]["indicators"]["quote"][0]["close"]:
                closes = result[0]["indicators"]["quote"][0]["close"]
                valid = [c for c in closes if c is not None]
                return {"yahoo_finance_ok": True, "price": round(valid[-1], 2) if valid else None}
            return {"yahoo_finance_ok": False, "error": "No data returned"}
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
            else:
                return {"yahoo_finance_ok": False, "error": str(e)}


def main():
    report = {
        "diagnosed_at": datetime.now().isoformat(),
        "python": check_python(),
        "packages": check_packages(),
        "futu_opend": check_futu_opend(),
        "futu_basic": check_futu_basic(),
        "news_api": check_news_api(),
                "yahoo_finance": check_yahoo_finance(),
            }
    # Summary
    all_ok = True
    issues = []
    for k, v in report.items():
        if k == "python":
            continue
        if isinstance(v, dict):
            if not v.get("installed", v.get("reachable", v.get("ok", True))):
                all_ok = False
                issues.append(k)
            elif "basic_active" in v and not v["basic_active"]:
                issues.append("futu_basic")
    report["summary"] = {"all_ok": all_ok, "issues": issues}
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
