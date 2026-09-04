# US Stock Trading Agent

美股交易专家 Agent，整合技术分析、基本面分析、资金流向、期权异动、新闻解读、风险管理六大维度。

## 脚本清单

| 脚本 | 功能 | 验证状态 |
|------|------|----------|
| `us_stock_analyzer.py` | 单股综合分析（技术+资金+新闻） | ✅ NVDA Overweight 68.8分 |
| `backtest.py` | 策略回测（MA5/20） | ✅ NVDA 55笔，695%收益 |
| `scan_stocks.py` | 选股扫描（sector/scan/meme） | ✅ Sector缓存0s命中 |
| `risk_manager.py` | 止损/仓位/风险计算 | ✅ NVDA止损204.48 |
| `portfolio_diagnose.py` | 组合健康诊断 | ✅ 2持仓风险分35 |
| `auto_trader.py` | 信号转订单 | ✅ 已修复API兼容 |
| `market_sentiment.py` | 市场情绪（VIX/指数/M7） | ✅ Yahoo备用生效 |
| `diagnose.py` | 环境健康检查 | ✅ 12项检查 |
| `trade_journal.py` | 交易日志持久化 | ✅ JSONL记录 |
| `news_sentiment.py` | 新闻情感分析（新） | ✅ NVDA偏多40% |
| `options_analysis.py` | 期权/衍生品分析（新） | ✅ 异动查询正常 |
| `cache_util.py` | 缓存工具（新） | ✅ Sector缓存0ms |

## 快速使用

```bash
# 单股分析
python scripts/us_stock_analyzer.py NVDA --quick

# 回测
python scripts/backtest.py US.NVDA --period daily --count 30

# 选股（板块热度）
python scripts/scan_stocks.py --mode sector --top 5

# 市场情绪
python scripts/market_sentiment.py --mode full

# 新闻情感
python scripts/news_sentiment.py --symbol US.NVDA --size 10

# 期权分析
python scripts/options_analysis.py --symbol US.NVDA --mode full

# 风险计算
python scripts/risk_manager.py --action stop-loss --symbol US.NVDA --entry 220 --atr 7.76

# 组合诊断
python scripts/portfolio_diagnose.py --positions-json positions.json --capital 100000

# 环境检查
python scripts/diagnose.py
```

## 数据源

- **Futu OpenAPI** (Primary): K线、资金流向、新闻搜索
- **Yahoo Finance** (Fallback): VIX、指数、M7报价、Sector ETF
- **Sina API** (Sector): 板块热度排名（缓存30分钟）

## 已知限制

- Futu Basic 订阅：部分实时行情不可用，IV/PCR需升级
- Sector 首次扫描约 85-195s（缓存后 0ms）
- 周末/盘后 Yahoo 数据点有限
- 自动交易需开通美股交易权限

## 依赖

- Python >= 3.10
- futu-api >= 10.4.6408
- pandas, numpy, scipy
- stock_signals (富途牛牛量化)

