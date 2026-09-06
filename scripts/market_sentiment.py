#!/usr/bin/env python3

"""US Market Sentiment - with Yahoo Finance fallback for Basic tier"""

import json, sys, argparse, urllib.request, time, logging, threading

from datetime import datetime

from cache_util import retry_call


def _futu_connect(fn,*args,timeout=3):
    r=[None];e=[None]
    def _run():
        try:
            from futu import OpenQuoteContext,RET_OK
            ctx=OpenQuoteContext();ctx.open();f2=getattr(ctx,fn);r[0]=f2(*args)
        except Exception as ex:e[0]=ex
    t=threading.Thread(target=_run,daemon=True);t.start();t.join(timeout=timeout)
    if t.is_alive():return None
    if e[0]:return None
    return r[0]




logger = logging.getLogger(__name__)

from futu import OpenQuoteContext, RET_OK



# Yahoo Finance mapping: Futu code -> Yahoo symbol

_YAHOO_MAP = {

    "US.DJI": "^DJI",

    "US.IXIC": "^IXIC",

    "US.SPX": "^GSPC",

    "US.VIX": "^VIX",

    "US.AAPL": "AAPL",

    "US.GOOG": "GOOG",

    "US.MSFT": "MSFT",

    "US.AMZN": "AMZN",

    "US.NVDA": "NVDA",

    "US.META": "META",

    "US.TSLA": "TSLA",

}



_YAHOO_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"



def _yahoo_get(symbol, period="5d"):
    """Fetch quote from Yahoo Finance - single attempt, 5s timeout."""
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/" + symbol + "?interval=1d&period=" + period
        req = urllib.request.Request(url, headers={
            "User-Agent": _YAHOO_UA,
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
        })
        data = json.loads(urllib.request.urlopen(req, timeout=5).read())
        result = data.get("chart", {}).get("result")
        if result and result[0]["indicators"]["quote"][0]["close"]:
            closes = result[0]["indicators"]["quote"][0]["close"]
            opens = result[0]["indicators"]["quote"][0]["open"]
            valid_close = [c for c in closes if c is not None]
            valid_open = [o for o in opens if o is not None]
            if len(valid_close) >= 2:
                return {
                    "close": valid_close[-1],
                    "open": valid_open[-1] if valid_open else valid_close[-1],
                    "prev_close": valid_close[-2],
                }
            elif valid_close:
                return {
                    "close": valid_close[-1],
                    "open": valid_open[-1] if valid_open else valid_close[-1],
                    "prev_close": valid_close[-1],
                }
    except Exception:
        pass
    return None


def _yahoo_batch(symbols, period="5d"):

    """Fetch multiple symbols with rate limiting (1.5s between calls)."""

    results = {}

    for sym in symbols:

        ysym = _YAHOO_MAP.get(sym, sym.replace("US.", ""))

        # VIX needs longer period for reliable data

        p = "14d" if ysym == "^VIX" else period

        q = _yahoo_get(ysym, period=p)

        results[sym] = q

        time.sleep(0.3)

    return results



def _calc_change(q):

    if q and q["prev_close"] and q["prev_close"] != 0:

        return (q["close"] - q["prev_close"]) / q["prev_close"] * 100

    return 0.0



def classify_vix(value):

    if value < 15:

        return "very_low"

    elif value < 20:

        return "low"

    elif value < 30:

        return "medium"

    elif value < 40:

        return "high"

    else:

        return "extreme"



def get_market_overview():

    # Try Futu first

    futu_data = {}

    try:

        _result = _futu_connect("get_stock_quote", ["US.DJI", "US.IXIC", "US.SPX"],timeout=3)

        if _result is not None:
            ret, data = _result

        if ret == RET_OK and data is not None and len(data) > 0:

            for _, row in data.iterrows():

                futu_data[row["code"]] = {

                    "source": "futu",

                    "name": row.get("stock_name", ""),

                    "price": float(row.get("last_price", 0)),

                    "change_pct": float(row.get("change_ratio", 0)),

                }

    except Exception:

        pass

    if futu_data:

        return futu_data



    # Fallback to Yahoo

    yahoo_results = _yahoo_batch(["US.DJI", "US.IXIC", "US.SPX"], period="10d")

    names = {"US.DJI": "Dow Jones", "US.IXIC": "NASDAQ", "US.SPX": "S&P 500"}

    return {

        code: {

            "source": "yahoo",

            "name": names.get(code, code),

            "price": round(q["close"], 2) if q else None,

            "change_pct": round(_calc_change(q), 2) if q else None,

        }

        for code, q in yahoo_results.items()

    }



def get_vix():

    # Try Futu first

    try:

        _result = _futu_connect("get_stock_quote", ["US.VIX"],timeout=3)

        if _result is not None:
            ret, data = _result

        if ret == RET_OK and data is not None and len(data) > 0:

            row = data.iloc[0]

            value = float(row.get("last_price", 0))

            if value > 0:

                return {

                    "source": "futu",

                    "value": value,

                    "timestamp": datetime.now().strftime("%Y-%m-%d"),

                    "level": classify_vix(value),

                }

    except Exception:

        pass

    # Fallback to Yahoo

    q = _yahoo_get("^VIX", period="14d")

    if q and q["close"] and q["close"] > 0:

        return {

            "source": "yahoo",

            "value": round(q["close"], 2),

            "timestamp": datetime.now().strftime("%Y-%m-%d"),

            "level": classify_vix(q["close"]),

            "change_pct": round(_calc_change(q), 2),

        }

    return {"error": "VIX unavailable"}



def get_magnificent_seven():

    symbols = ["US.AAPL", "US.GOOG", "US.MSFT", "US.AMZN", "US.NVDA", "US.META", "US.TSLA"]

    # Try Futu first

    futu_data = []

    try:

        _result = _futu_connect("get_stock_quote", symbols,timeout=3)

        if _result is not None:
            ret, data = _result

        if ret == RET_OK and data is not None and len(data) > 0:

            futu_data = [

                {

                    "symbol": row["code"].split(".")[-1],

                    "name": row.get("stock_name", ""),

                    "price": float(row.get("last_price", 0)),

                    "change_pct": float(row.get("change_ratio", 0)),

                    "source": "futu",

                }

                for _, row in data.iterrows()

            ]

    except Exception:

        pass

    if futu_data:

        return futu_data

    # Fallback to Yahoo

    yahoo_results = _yahoo_batch(symbols, period="5d")

    return [

        {

            "symbol": code.split(".")[-1],

            "price": round(q["close"], 2) if q else None,

            "change_pct": round(_calc_change(q), 2) if q else None,

            "source": "yahoo",

        }

        for code, q in yahoo_results.items()

    ]



def main():

    parser = argparse.ArgumentParser(description="US Market Sentiment")

    parser.add_argument("--mode", default="overview", choices=["overview", "vix", "hot", "magnificent", "full"])

    parser.add_argument("--output", default=None)

    args = parser.parse_args()

    report = {"generated_at": datetime.now().isoformat(), "mode": args.mode}

    if args.mode in ("overview", "full"):

        report["indices"] = get_market_overview()

    if args.mode in ("vix", "full"):

        report["vix"] = get_vix()

    if args.mode in ("magnificent", "full"):

        report["magnificent_seven"] = get_magnificent_seven()

    output = json.dumps(report, ensure_ascii=False, indent=2, default=str)

    if args.output:

        with open(args.output, "w", encoding="utf-8") as f:

            f.write(output)

    else:

        print(output)



if __name__ == "__main__":

    main()