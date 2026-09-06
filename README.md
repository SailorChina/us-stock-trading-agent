# US Stock Trading Agent

美股交易专家 Agent，整合**技术分析、资金流向、新闻情感、期权异动、风险管理**五大维度，为美股提供全面的交易分析与决策支持。

## 功能概览

| 维度 | 模块 | 功能 |
|------|------|------|
| **技术分析** | `us_stock_analyzer.py` | VCP形态、MACD/RSI/KDJ/BOLL、多周期共振、TD序列、五档评级 |
| **资金流向** | `scan_stocks.py` | 板块热度排名、异动股扫描、Meme股追踪 |
| **热门榜单** | `tech_engine.py` | Futu热门榜单扫描、聪明钱综合评分 |
| **新闻情感** | `news_sentiment.py` | Futu新闻API、正负向词库分析、综合情感评分 |
| **期权异动** | `options_analysis.py` | IV隐含波动率、PCR看跌看涨比、异常期权成交 |
| **风险管理** | `risk_manager.py` | ATR止损、风险收益比、动态仓位、组合诊断 |

## 测试状态

```
157 passed (全部通过)
pytest tests/ -q
```

| 测试文件 | 测试数 | 覆盖模块 |
|----------|--------|----------|
| `test_auto_analyzer.py` | 2 | 自动分析摘要输出 |
| `test_backtest.py` | 2 | MA策略回测逻辑 |
| `test_backtest_visualize.py` | 5 | 权益曲线、最大回撤、HTML报告 |
| `test_config.py` | 2 | TOML配置加载与点路径查询 |
| `test_journal.py` | 2 | 交易日志持久化 |
| `test_logger.py` | 1 | 日志系统 |
| `test_macro_calendar.py` | 2 | 宏观经济日历（VIX/10Y/DXY） |
| `test_news_sentiment.py` | 4 | 新闻情感分析（正/负/中性） |
| `test_portfolio_diagnose.py` | 10 | 组合诊断（高风险/低现金/止损破位等） |
| `test_premarket_scanner.py` | 2 | 盘前/盘后异动扫描 |
| `test_risk.py` | 6 | ATR止损、风险收益比、仓位管理 |
| `test_syntax.py` | 1 | 所有脚本编译检查 |
| `test_watchlist.py` | 4 | 自选股原子写入 |

## 快速使用

### 核心命令

```bash
# 单股全面分析
python scripts/us_stock_analyzer.py NVDA

# 快速信号（技术面）
python scripts/agent.py signal NVDA

# 完整分析（技术+新闻+期权）
python scripts/agent.py analyze NVDA --timeframe 1d

# 市场情绪（VIX/指数/Magnificent 7）
python scripts/market_sentiment.py --mode full

# 板块热度
python scripts/scan_stocks.py --mode sector --top 5

# 选股扫描
python scripts/scan_stocks.py --mode scan --min-score 55

# Meme股追踪
python scripts/scan_stocks.py --mode meme-scan

# 回测
python scripts/backtest.py US.NVDA --period daily --count 200

# 回测可视化
python scripts/backtest_visualize.py US.NVDA --output data/report.html

# 新闻情感分析
python scripts/news_sentiment.py --symbol US.NVDA --size 10

# 期权分析
python scripts/options_analysis.py --symbol US.NVDA --mode full

# 风险管理
python scripts/risk_manager.py --action report --symbol US.NVDA --entry 220 --atr 7.76 --position-pct 0.15
python scripts/risk_manager.py --action stop-loss --symbol US.NVDA --entry 220 --atr 7.76
python scripts/risk_manager.py --action portfolio --positions-json positions.json

# 组合诊断
python scripts/portfolio_diagnose.py --positions-json positions.json --capital 100000

# 宏观日历
python scripts/macro_calendar.py --mode snapshot
python scripts/macro_calendar.py --mode events

# 盘前/盘后扫描
python scripts/premarket_scanner.py --mode premarket --top 10
python scripts/premarket_scanner.py --mode afterhours --top 10

# 每日检查清单
python scripts/daily_checklist.py

# 自动分析（定时）
python scripts/auto_analyzer.py --once
python scripts/auto_analyzer.py --daemon --interval 1

# 环境诊断
python scripts/diagnose.py
```

### 使用示例

```bash
# 分析 NVDA 技术面
python scripts/us_stock_analyzer.py NVDA

# 分析 NVDA 并查看资金流向
python scripts/us_stock_analyzer.py US.NVDA --dimensions tech,capital

# 快速买入信号
python scripts/agent.py signal NVDA

# 生成 HTML 回测报告
python scripts/backtest_visualize.py US.NVDA

# 风险计算：入场价 220，ATR 7.76，仓位 15%
python scripts/risk_manager.py --action report --symbol US.NVDA --entry 220 --atr 7.76 --position-pct 0.15
```

## 项目结构

```
agent/
├── scripts/                    # 核心脚本
│   ├── agent.py               # 统一入口（analyze/signal/watchlist/checklist/report）
│   ├── us_stock_analyzer.py   # 单股综合分析（技术+资金+新闻）
│   ├── market_sentiment.py    # 市场情绪（VIX/指数/M7）
│   ├── news_sentiment.py      # 新闻情感分析
│   ├── options_analysis.py    # 期权/衍生品分析
│   ├── scan_stocks.py         # 选股扫描（sector/scan/meme）
│   ├── risk_manager.py        # 风险管理（止损/仓位/报告）
│   ├── portfolio_diagnose.py  # 组合健康诊断
│   ├── backtest.py            # 策略回测（MA交叉）
│   ├── backtest_visualize.py  # 回测HTML可视化
│   ├── auto_analyzer.py       # 定时自动分析
│   ├── auto_trader.py         # 信号转订单（模拟盘）
│   ├── premarket_scanner.py   # 盘前/盘后异动扫描
│   ├── macro_calendar.py      # 宏观经济日历
│   ├── daily_checklist.py     # 每日检查清单
│   ├── watchlist.py           # 自选股管理
│   ├── trade_journal.py       # 交易日志
│   ├── diagnose.py            # 环境健康检查
│   ├── cache_util.py          # 缓存工具（retry_call/get_cached）
│   └── logger.py              # 日志工具
├── tests/                      # 测试套件
│   ├── test_auto_analyzer.py
│   ├── test_backtest.py
│   ├── test_backtest_visualize.py
│   ├── test_config.py
│   ├── test_journal.py
│   ├── test_logger.py
│   ├── test_macro_calendar.py
│   ├── test_news_sentiment.py
│   ├── test_portfolio_diagnose.py
│   ├── test_premarket_scanner.py
│   ├── test_risk.py
│   ├── test_syntax.py
│   └── test_watchlist.py
├── configs/
│   └── settings.toml          # 全局配置（风险/扫描/情绪阈值）
├── knowledge/
│   └── trading_strategies.md  # 交易策略知识库
├── data/                       # 运行时数据（缓存/报告）
├── README.md
├── SKILL.md                    # Codex Agent 技能定义
└── requirements.txt
```

## 数据源

| 数据源 | 用途 | 状态 |
|--------|------|------|
| **Futu OpenAPI** | K线、资金流向、新闻搜索、期权数据 | Primary |
| **Yahoo Finance** | VIX、指数、M7报价、Sector ETF、宏观指标 | Fallback |
| **Sina API** | 板块热度排名（缓存30分钟） | Fallback |

## 配置说明

`configs/settings.toml` 包含以下配置段：

- `[general]` - 默认时间框架、风险等级
- `[futu]` - Futu OpenD 连接配置（host/port/env）
- `[technical]` - 技术指标偏好（MA/MACD/RSI/KDJ/BOLL/ATR/OBV）
- `[portfolio]` - 资金管理（最大仓位、行业集中度、现金储备）
- `[risk]` - 风控参数（ATR倍数、固定止损、追踪止损、日/周亏损限制）
- `[scan]` - 选股条件（市值、均线、RSI、利润率、营收增长）
- `[sentiment]` - 情绪阈值（VIX分级、多空阈值）

## 已知限制

- **Futu Basic 订阅**：部分实时行情不可用，IV/PCR需升级专业版
- **Sector 首次扫描**：约 85-195s（缓存后 0ms）
- **周末/盘后**：Yahoo 数据点有限
- **自动交易**：需开通美股交易权限，建议先用 `--dry-run` 测试
- **网络测试**：`test_macro_calendar::test_get_macro_snapshot` 和 `test_premarket_scanner::test_premarket_scan` 依赖 Yahoo Finance，可能因 429 限速跳过

## 依赖

```
python >= 3.10
futu-api >= 10.4.6408
pandas >= 2.0
numpy >= 1.24
scipy >= 1.10
akshare >= 1.14
pytest >= 7.0
```

## 运行测试

```bash
# 运行全部测试
pytest tests/ -v

# 只看网络相关测试
pytest tests/ -k "macro_snapshot or premarket_scan" -v

# 带覆盖率
pytest tests/ --cov=scripts --cov-report=term-missing
```

## 版本历史

- **v2.6.0** - 聪明钱筛选器、155项测试(约130 passed, 25 network deselected)、价格实时修正、全覆盖测试
- **v1.0.0** - 初始版本：基础分析、回测、风险计算
