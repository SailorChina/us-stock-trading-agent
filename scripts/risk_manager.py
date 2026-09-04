#!/usr/bin/env python3
import json, sys, argparse, logging
from dataclasses import dataclass, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class RiskReport:
    symbol: str
    position_pct: float
    risk_per_trade_pct: float
    max_loss_usd: float
    stop_loss: Optional[float]
    target_1: Optional[float]
    target_2: Optional[float]
    reward_risk_ratio: Optional[float]
    risk_level: str
    suggestions: list

def calculate_atr_stop(entry_price, atr, multiplier=2.0):
    return round(entry_price - atr * multiplier, 2)

def calculate_risk_reward(entry, stop, target):
    risk = entry - stop
    if risk <= 0: return 0.0
    reward = target - entry
    return round(reward / risk, 2)

def assess_risk_level(position_pct, risk_per_trade, rr_ratio):
    if position_pct > 0.20 or risk_per_trade > 0.05: return "high"
    elif position_pct > 0.10 or risk_per_trade > 0.03: return "medium"
    else: return "low"

def generate_risk_report(symbol, entry_price, current_price, position_pct, atr=3.0,
                         total_capital=100000.0, stop_type="atr", stop_pct=0.05,
                         support_level=None, target_multiplier=2.0):
    if stop_type == "atr":
        stop_loss = calculate_atr_stop(entry_price, atr, multiplier=2.0)
    elif stop_type == "support":
        stop_loss = support_level if support_level else entry_price * (1 - stop_pct)
    else:
        stop_loss = entry_price * (1 - stop_pct)
    stop_loss = round(stop_loss, 2)
    risk = entry_price - stop_loss
    target_1 = round(entry_price + risk * target_multiplier, 2)
    target_2 = round(entry_price + risk * target_multiplier * 1.5, 2)
    rr = calculate_risk_reward(entry_price, stop_loss, target_1)
    shares = total_capital * position_pct / entry_price
    risk_usd = (entry_price - stop_loss) * shares
    risk_pct = risk_usd / total_capital
    risk_level = assess_risk_level(position_pct, risk_pct, rr)
    suggestions = []
    if position_pct > 0.20:
        suggestions.append(f"position too heavy ({position_pct*100:.1f}%), reduce below 20%")
    if risk_pct > 0.02:
        suggestions.append(f"single trade risk too high ({risk_pct*100:.1f}%), reduce position")
    if rr < 2.0:
        suggestions.append(f"RR ratio low ({rr:.2f}), find better entry")
    if current_price < stop_loss:
        suggestions.append(f"current price {current_price} below stop {stop_loss}!")
    if risk_level == "high":
        suggestions.append("HIGH RISK - proceed with caution")
    elif risk_level == "low":
        suggestions.append("risk可控 - can proceed")
    return RiskReport(symbol=symbol, position_pct=position_pct,
                      risk_per_trade_pct=round(risk_pct * 100, 2),
                      max_loss_usd=round(risk_usd, 2),
                      stop_loss=stop_loss, target_1=target_1, target_2=target_2,
                      reward_risk_ratio=rr, risk_level=risk_level, suggestions=suggestions)

def portfolio_check(positions, total_capital=100000.0):
    total_pct = sum(p.get("position_pct", 0) for p in positions)
    max_single = max((p.get("position_pct", 0) for p in positions), default=0)
    checks = {"total_position_pct": round(total_pct * 100, 1),
              "max_single_pct": round(max_single * 100, 1),
              "cash_ratio": round((1 - total_pct) * 100, 1),
              "status": "ok", "warnings": []}
    if total_pct > 0.90:
        checks["status"] = "warning"
        checks["warnings"].append(f"total position {total_pct*100:.1f}% near limit")
    if max_single > 0.20:
        checks["status"] = "warning"
        checks["warnings"].append(f"single position {max_single*100:.1f}% exceeds 20% cap")
    if (1 - total_pct) < 0.10:
        checks["warnings"].append("cash reserve below 10%")
    return checks


def check_portfolio_risk(positions, total_capital=100000):
    """Check portfolio-level risk: concentration, cash, sector exposure"""
    if not isinstance(positions, list):
        positions = [positions]
    total_value = sum(p.get("shares", 0) * p.get("current_price", 0) for p in positions)
    cash = total_capital - total_value
    cash_pct = (cash / total_capital * 100) if total_capital > 0 else 100
    sector_map = {}
    single_max = 0
    for p in positions:
        val = p.get("shares", 0) * p.get("current_price", 0)
        sector = p.get("sector", "unknown")
        sector_map[sector] = sector_map.get(sector, 0) + val
        pct = (val / total_capital * 100) if total_capital > 0 else 0
        single_max = max(single_max, pct)
    sector_max = max(sector_map.values()) if sector_map else 0
    sector_max_pct = (sector_max / total_value * 100) if total_value > 0 else 0
    flags = []
    if cash_pct < 10: flags.append("现金低于10%")
    if single_max > 20: flags.append(f"单股仓位{single_max:.1f}%超限")
    if sector_max_pct > 40: flags.append(f"行业集中{sector_max_pct:.1f}%超限")
    return {
        "total_value": round(total_value, 2), "cash": round(cash, 2), "cash_pct": round(cash_pct, 1),
        "single_max_pct": round(single_max, 1), "sector_max_pct": round(sector_max_pct, 1),
        "flags": flags, "risk_level": "高" if flags else "正常"
    }

def dynamic_position_size(entry_price, atr, capital=100000, risk_pct=2, risk_level="medium"):
    """Calculate position size based on ATR stop distance and risk tolerance"""
    stop_distance = atr * 2.0
    risk_per_share = stop_distance
    if risk_per_share <= 0: return {"error": "ATR must be positive"}
    risk_usd = capital * (risk_pct / 100)
    shares = int(risk_usd / risk_per_share)
    position_value = shares * entry_price
    position_pct = (position_value / capital * 100) if capital > 0 else 0
    return {
        "entry_price": entry_price, "atr": atr, "stop_distance": round(stop_distance, 2),
        "shares": shares, "position_value": round(position_value, 2),
        "position_pct": round(position_pct, 2), "risk_usd": round(risk_usd, 2),
        "risk_level": risk_level
    }

def main():
    parser = argparse.ArgumentParser(description="Risk Manager")
    parser.add_argument("--action", default="report", choices=["report", "portfolio", "stop-loss"])
    parser.add_argument("--symbol", default="US.NVDA")
    parser.add_argument("--entry", type=float)
    parser.add_argument("--current", type=float)
    parser.add_argument("--position-pct", type=float, default=0.10)
    parser.add_argument("--atr", type=float, default=3.0)
    parser.add_argument("--capital", type=float, default=100000.0)
    parser.add_argument("--stop-type", default="atr", choices=["atr", "support", "fixed"])
    parser.add_argument("--stop-pct", type=float, default=0.05)
    parser.add_argument("--support", type=float)
    parser.add_argument("--positions-json")
    args = parser.parse_args()
    if args.action == "report":
        if not args.entry:
            print("need --entry", file=sys.stderr); sys.exit(1)
        report = generate_risk_report(symbol=args.symbol, entry_price=args.entry,
            current_price=args.current or args.entry, position_pct=args.position_pct,
            atr=args.atr, total_capital=args.capital, stop_type=args.stop_type,
            stop_pct=args.stop_pct, support_level=args.support)
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    elif args.action == "portfolio":
        if not args.positions_json:
            print("need --positions-json", file=sys.stderr); sys.exit(1)
        with open(args.positions_json, encoding="utf-8") as f:
            positions = json.load(f)
        print(json.dumps(portfolio_check(positions, args.capital), ensure_ascii=False, indent=2))
    elif args.action == "stop-loss":
        if not args.entry or not args.atr:
            print("need --entry and --atr", file=sys.stderr); sys.exit(1)
        stop = calculate_atr_stop(args.entry, args.atr, multiplier=2.0)
        print(json.dumps({"symbol": args.symbol, "entry": args.entry, "atr": args.atr,
            "stop_loss": stop, "stop_pct": round((args.entry - stop) / args.entry * 100, 2)},
            ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
