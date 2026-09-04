#!/usr/bin/env python3
import logging, sys
from datetime import datetime

def setup_logger(name="us_stock_agent", level="INFO", log_file=None):
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
        ch = logging.StreamHandler(sys.stderr)
        ch.setFormatter(fmt)
        logger.addHandler(ch)
    return logger

def log_trade_event(logger, symbol, action, price, shares, pnl=None, note=""):
    msg = f"{action} {shares}x {symbol} @ {price}"
    if pnl is not None:
        msg += f" PnL={pnl:+.2f}"
    if note:
        msg += f" ({note})"
    logger.info(msg)

def log_analysis_event(logger, symbol, rating, score, reason=""):
    msg = f"ANALYSIS {symbol}: {rating} (score={score})"
    if reason:
        msg += f" reason={reason}"
    logger.info(msg)

def log_error_event(logger, module, symbol, error):
    logger.error(f"{module} error for {symbol}: {error}")

if __name__ == "__main__":
    log = setup_logger()
    log_trade_event(log, "US.NVDA", "BUY", 220.5, 10, pnl=150.0)
    log_analysis_event(log, "US.TSLA", "HOLD", 45)
