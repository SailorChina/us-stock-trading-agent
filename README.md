# US Stock Trading Agent

美股交易专家 Agent，整合**技术分析、资金流向、新闻情感、期权异动、风险管理**五大维度，为美股提供全面的交易分析与决策支持。

## 功能概览

| 维度 | 模块 | 功能 |
|------|------|------|
| **技术分析** | `tech_engine.py` | VCP形态、MACD/RSI/KDJ/BOLL/ATR/OBV/ADXR、多周期共振、TD序列、五档评级 |
| **增强指标** | `enhanced_indicators.py` | CCI、RVI、StochRSI、Williams %R、OBV背离检测 |
| **K线形态** | `candlestick_patterns.py` | Doji、Hammer、Engulfing、Morning/Evening Star、三白兵/三鸦 |
| **聪明钱** | `smart_money_screener.py` | 机构持仓、买卖经纪商、资金流向、卖空追踪 |
| **热门榜单** | `tech_engine.py` | Futu热门榜单扫描（Market.US枚举）、盘前异动 |
| **新闻情感** | `news_sentiment.py` | Futu新闻API、正负向词库分析、综合情感评分 |
| **期权异动** | `options_analysis.py` | IV隐含波动率、PCR看跌看涨比、异常期权成交 |
| **财报分析** | `earnings_analyzer.py` | PE/Forward PE、EPS增长、营收增长、分析师目标价 |
| **决策引擎** | `decision_engine.py` | 六因子综合评分、权重融合、自适应交易计划（多空双向） |
| **策略验证** | `strategy_validator.py` | 无前视回测、横截面排序验证、事件研究（稀有信号）、IC+Newey-West t、分位组单调性、vs 买入持有 |
| **每日选股** | `daily_pick.py` + `stock_selector.py` | 收盘后扫描：`mom_12_1_raw` 排行（唯一通过验证的风格）、流动性过滤、2×ATR 止损、**等金额下单清单**（`--capital`/`--sheet`，小资金可执行）、离线复核（`--from-cache`）、**限频感知取数** |
| **风险管理** | `risk_manager.py` | ATR止损、风险收益比、动态仓位、组合诊断 |
| **市场情绪** | `market_sentiment.py` | VIX分级、指数报价、Magnificent 7 |
| **市场状态** | `market_regime.py` | Bull/Bear/Volatile/Neutral 自动识别 |
| **一键选股** | `auto_selector.py` | 聪明钱+热门榜单扫描，并行全量分析，输出 ranked 表格 |

## 测试状态

```
343 passed (全部通过，非沙箱/无文件锁环境)
pytest tests/ -q
```

> 注：WorkBuddy 沙箱或本机文件锁活跃时，个别删除/写入类用例（如
> test_cache_util、test_log_trade）会随锁状态失败，非代码问题。

```

| 测试文件 | 测试数 | 覆盖模块 |
|----------|--------|----------|
| `test_agent.py` | 8 | 统一入口、信号生成、交易计划 |
| `test_auto_analyzer.py` | 3 | 自动分析摘要输出 |
| `test_auto_trader.py` | 3 | 模拟盘下单、交易日志 |
| `test_backtest.py` | 3 | MA策略回测逻辑 |
| `test_backtest_visualize.py` | 5 | 权益曲线、最大回撤、HTML报告 |
| `test_config.py` | 2 | TOML配置加载与点路径查询 |
| `test_daily_checklist.py` | 3 | 每日检查清单 |
| `test_diagnose.py` | 1 | 环境健康检查 |
| `test_hot_list.py` | 1 | 热门榜单扫描 |
| `test_journal.py` | 2 | 交易日志持久化 |
| `test_logger.py` | 1 | 日志系统 |
| `test_macro_calendar.py` | 2 | 宏观经济日历（VIX/10Y/DXY） |
| `test_market_regime.py` | 2 | 市场状态判断 |
| `test_market_sentiment.py` | 3 | 市场情绪（VIX/指数/M7） |
| `test_news_sentiment.py` | 4 | 新闻情感分析（正/负/中性） |
| `test_options_analysis.py` | 13 | IV/PCR分类、异常期权 |
| `test_portfolio_diagnose.py` | 10 | 组合诊断（高风险/低现金/止损破位等） |
| `test_premarket_scanner.py` | 2 | 盘前/盘后异动扫描 |
| `test_risk.py` | 6 | ATR止损、风险收益比、仓位管理 |
| `test_scan_stocks.py` | 1 | 选股扫描入口 |
| `test_smart_money.py` | 3 | 聪明钱筛选 |
| `test_smart_money_screener.py` | 3 | 智能筛选器 |
| `test_syntax.py` | 1 | 所有脚本编译检查 |
| `test_tech_engine.py` | 24 | 技术指标计算、信号生成、格式化输出 |
| `test_trade_journal.py` | 2 | 交易日志增强 |
| `test_us_stock_analyzer.py` | 2 | 综合分析入口 |
| `test_watchlist.py` | 4 | 自选股原子写入 |
| **`test_candlestick_patterns.py`** | **6** | **K线形态检测与评分** |
| **`test_enhanced_indicators.py`** | **10** | **CCI/RVI/StochRSI/WR/OBV背离** |
| **`test_earnings_analyzer.py`** | **3** | **财报评分逻辑** |
| **`test_decision_engine.py`** | **4** | **多因子决策引擎** |
| `test_decision_precomputed.py` | 23 | 决策引擎 precomputed 复用（离线）+ auto_selector 接线 + 打分正确性 + regime 门控 |
| **`test_ml_predictor_honesty.py`** | **8** | **ML 正确性：跨标模型隔离、scaler 无泄露、val 选模型、基线对比** |
| **`test_strategy_validator.py`** | **33** | **无前视验证、横截面 IC+Newey-West、分位组、非重叠模拟、风格回调、事件研究** |
| **`test_vol_targeting.py`** | **9** | **波动率目标仓位：vol 高者仓位小、约束生效报告、零波动保护** |
| **`test_stock_selector.py`** | **21** | **选股因子：三风格方向性、不接落刀、企稳确认、板块归簇、12-1动量/短期反转/低波动** |
| **`test_daily_pick.py`** | **19** | **每日扫描：排行、无市场择时门控、流动性过滤、热门池并入、坏数据存活、板块上限、等金额清单、限频节流与冷却重试、取数/过滤分开计数、盘中未完成 bar 警告** |

## 快速使用

### 核心命令

```bash
# 单股全面分析
python scripts/agent.py analyze US.NVDA

# 快速信号（技术面）
python scripts/agent.py signal US.NVDA

# 综合决策（六因子融合）
python scripts/agent.py decision US.NVDA

# 市场情绪（VIX/指数/Magnificent 7）
python scripts/market_sentiment.py --mode full

# 增强指标（CCI/RVI/StochRSI/WR/OBV背离）
python scripts/agent.py divergence US.NVDA

# K线形态识别
python scripts/agent.py candlestick US.NVDA

# 财报分析
python scripts/agent.py earnings US.NVDA

# 热门榜单
python scripts/tech_engine.py --mode hot-list --market US --top 10

# 选股扫描
python scripts/scan_stocks.py --mode scan --min-score 55

# 板块热度
python scripts/scan_stocks.py --mode sector --top 5

# Meme股追踪
python scripts/scan_stocks.py --mode meme-scan

# 盘前扫描
python scripts/scan_stocks.py --mode premarket

# 期权分析
python scripts/options_analysis.py --symbol US.NVDA --mode full

# 回测
python scripts/backtest.py US.NVDA --period daily --count 200

# 回测可视化
python scripts/backtest_visualize.py US.NVDA --output data/report.html

# 策略验证：综合分到底有没有预测力（无前视历史回测）
python scripts/strategy_validator.py --symbol US.NVDA --horizon 5 --bars 400 --threshold 60

# 横截面验证（推荐，统计功效更强）：每日对一篮子股票打分排序
python scripts/strategy_validator.py --mode cross --horizon 10 --bars 300 --limit 15

# 每日选股扫描（美东收盘后跑，输出今日多头候选）：
python scripts/daily_pick.py                       # 默认 mom_12_1_raw（唯一通过验证的风格）
python scripts/daily_pick.py --styles mom_12_1_raw,st_reversal --top 10
python scripts/daily_pick.py --styles momentum,reversal --max-per-sector 2

# 实盘可执行的清单（$3,000 账户：5 只等金额、每只 $600、附 2×ATR 止损）：
python scripts/daily_pick.py --top 5 --capital 3000 --sheet --no-hot \
       --output data/daily_pick_latest.json
#   → 附 top-5 排名、等金额下单清单、数据新鲜度与盘中未完成 bar 警告。
#   → 取数有节流（30 次/30 秒，228 只约 4 分钟），因为不限频会被富途静默拒绝、
#     只取到前几十只 —— 那会产出"看起来合理但基于残缺池子"的清单。
#   → 还会先查「历史 K 线额度」：额度按标的计（30 天内重复请求免费）、按账户资产分级
#     （开户 100 / 1 万 HKD 300 / 50 万 HKD 1000 / 500 万 HKD 2000）。
#     228 只全池首次覆盖要 228 个额度 —— **账户档位必须 ≥ 池子规模**，
#     否则扫描会静默地只覆盖一部分。查询：ctx.get_history_kl_quota(get_detail=True)
# 离线复核（不联网、秒级、确定性；用 data/_hist_cache）：
python scripts/daily_pick.py --from-cache --top 5 --capital 3000 --sheet

# 可选风格：mom_12_1_raw / mom_12_1 / momentum / reversal / quality / st_reversal / low_vol
#          + 已知交易系统：clenow / minervini / htf / pullback_ema / vcp / turtle55
# 注意（实测结论）：只有 mom_12_1_raw 通过了显著性检验（HAC t=2.36，超额 +1.37%/期）。
#   mom_12_1 / momentum / reversal / st_reversal 实测无超额（t≈0），
#   quality / low_vol 实测显著为负（t=-2.42 / -3.31）。
#   **没有任何市场择时门控能改善它**：6 种过滤器（SPY>200MA、回撤<5/10/15%、波动率<20/25%）
#   全部同时降低收益与显著性（详见 knowledge/factor_evidence_2026.md 第 8 节）。
#   海外知名交易系统（Clenow 指数回归动量 / Minervini 趋势模板 / Qullamaggie 高紧旗 /
#   VCP / 20-EMA 回调 / 海龟突破）全部实测未达显著（t 在 [-1.75, 1.24]），
#   详见 knowledge/factor_evidence_2026.md 第 5.4 节。它们保留在 --styles 供持续复测。
python scripts/daily_pick.py --styles clenow,minervini --top 10     # 对比大神的选股结果
# 单独验证某个风格（live 与验证共用同一打分函数）：
python scripts/strategy_validator.py --mode cross --style mom_12_1_raw --horizon 21 --bars 3000 --limit 228

# 组合级回测（离线，读 data/_hist_cache/，回答"买进去赚多少"）：
python -c "import sys;sys.path.insert(0,'scripts');import backtest_engine as be,json;print(json.dumps(be.backtest_style('mom_12_1_raw',be.load_cache(),horizon=21,top_n=10),indent=1,default=str))"

# 事件研究（稀有信号风格如 reversal 的正确验证法：信号日 vs 该股平常日）：
python scripts/strategy_validator.py --mode events --style reversal --horizon 10 --bars 400 --limit 15

# 实盘/模拟盘执行（富途 OpenAPI；默认 DRY RUN、默认模拟盘）：
python scripts/live_trader.py --top 5 --from-cache                                # 只看计划，不发单
python scripts/live_trader.py --top 5 --capital 3000 --fractional --from-cache    # $3000 计划 + 按金额委托单
python scripts/live_trader.py --top 5 --execute                                   # 模拟盘实单（零风险）
# $3,000 该怎么做（实测结论，见 knowledge/factor_evidence_2026.md 第 5.6 节）：
#   OpenAPI 只能整股 —— qty=0.29 被拒「数量不合法」，qty=1.5 被**静默截断为 1 股**；
#   而 $3,000 按整股买 top-10 有 85% 现金拖累（10 只里 8 只买不起）。
#   ⇒ 选股跑在本仓库（228 只全池），下单在富途牛牛 App 的「按金额」碎股模式
#     （5000+ 标的、$5 起、碎股免佣、$1 平台费/笔）。
# 实测推荐：5 只等权、约每 21 个交易日调仓（top-5 的 HAC t=2.81，样本内外双双 >2）。

# 富途量化（GUI）策略 + 本地离线校验（从客户端 futu.zip 读真实导出名单比对 API）：
python scripts/validate_ftquant_strategy.py

# 新闻情感分析
python scripts/news_sentiment.py --symbol US.NVDA --size 10

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

# ML预测（价格方向）
python scripts/agent.py ml-predict US.NVDA
python scripts/ml_predictor.py --symbol US.NVDA --mode predict

# ML回测（Walk-forward验证）
python scripts/agent.py ml-backtest US.NVDA
python scripts/ml_predictor.py --symbol US.NVDA --mode backtest

# 智能筛选（聪明钱）
python scripts/smart_money_screener.py --mode quick
```

### 使用示例

```bash
# 分析 NVDA 技术面 + 交易计划
python scripts/agent.py analyze US.NVDA

# 综合决策（六因子融合）
python scripts/agent.py decision US.NVDA

# K线形态识别
python scripts/agent.py candlestick US.NVDA

# 增强指标 + OBV背离检测
python scripts/agent.py divergence US.NVDA

# 财报分析
python scripts/agent.py earnings US.NVDA

# 生成 HTML 回测报告
python scripts/backtest_visualize.py US.NVDA

# 风险计算：入场价 220，ATR 7.76，仓位 15%
python scripts/risk_manager.py --action report --symbol US.NVDA --entry 220 --atr 7.76 --position-pct 0.15

# 聪明钱筛选
python scripts/smart_money_screener.py --mode full
```

## 项目结构

```
agent/
├── scripts/                    # 核心脚本
│   ├── agent.py               # 统一入口（analyze/signal/decision/candlestick/earnings等）
│   ├── tech_engine.py         # 技术分析引擎（K线/指标/信号/热门榜单）
│   ├── enhanced_indicators.py  # 增强指标（CCI/RVI/StochRSI/WR/OBV背离）
│   ├── candlestick_patterns.py # K线形态识别（9种经典形态）
│   ├── earnings_analyzer.py   # 财报分析（PE/EPS/营收/分析师目标）
│   ├── ml_predictor.py        # ML价格方向预测（RF/GBM）
│   ├── ml_features.py         # 特征工程（28维技术指标）
│   ├── decision_engine.py     # 六因子综合决策引擎
│   ├── smart_money_screener.py # 聪明钱筛选器
│   ├── market_sentiment.py    # 市场情绪（VIX/指数/M7）
│   ├── news_sentiment.py      # 新闻情感分析
│   ├── options_analysis.py    # 期权/衍生品分析（IV/PCR）
│   ├── scan_stocks.py         # 选股扫描（sector/scan/meme/premarket）
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
├── tests/                      # 测试套件（180 tests）
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
| **Futu OpenAPI** | K线、热门榜单、资金流向、新闻搜索、期权数据、IV/PCR | Primary |
| **Yahoo Finance** | VIX、指数、M7报价、Sector ETF、财报/分析师数据 | Fallback |
| **Sina API** | 板块热度排名（缓存30分钟） | Fallback |

## 配置说明

`configs/settings.toml` 包含以下配置段：

- `[general]` - 默认时间框架、风险等级
- `[futu]` - Futu OpenD 连接配置（host/port/env）
- `[technical]` - 技术指标偏好（MA/MACD/RSI/KDJ/BOLL/ATR/OBV/ADX）
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

- **v3.13.0** - **模拟账户实跑 + 修掉「用六周前的数据选股」的静默 bug**（完整证据见 `knowledge/factor_evidence_2026.md` 第 10 节）：① **用富途 skill 真操控了模拟账户**：`trade/get_accounts.py`（10 个账户）、`get_portfolio.py`、`get_orders.py`，模拟盘 US/SIMULATE **现金 $1,000,002.59、0 持仓**；`live_trader.py --top 5 --execute` 真发 5 笔市价单并全部成交。② **★ 发现 `live_trader` 一直在用过期数据下单**：它发单次区间请求 `request_history_kline(start=504天前, end=今天, max_count=315)`，而**富途返回的是区间的【前】315 根而非最后 315 根** —— 实测 `[2025-04-24..2026-09-10]` 返回 315 根、**最后一根停在 2026-07-27（早 45 天）**，MU 动量算成 +987.7%（正确值 +543%），**全程无报错且输出看起来合理**，据此下了真实（模拟）单、选出的是另一组 top-5（MU/INTC/MRVL/AMAT/AMD vs 正确的 MU/WDC/STX/INTC/DELL）。③ **修复**：抽出共享模块 `scripts/futu_pacing.py`（**会翻页** + 节流 30/30 秒 + 冷却 31s 重试同一只 + 冷却封顶 6），`daily_pick` 与 `live_trader` **共用同一份** —— **根因就是两份取数实现迟早会不一致**；并加**数据新鲜度守卫**（最后一根 bar 距今 > 10 天就跳过并警告，而不是拿去打分）。④ **富途量化回测确认无法脱离 GUI**：`runner._set_cmd_args` 的 `run_mode/strategy_id` 全部来自原生模块 `_futuinternal`，`RunMode.BACKTEST` 亦由其提供，`NNPython.exe` 是平台专用启动器（`argv[1]` 是 run id，传 `-c` 只回显）⇒ 逆向原生 IPC 不做。⑤ **但拿到了平台自己的 import 白名单**：`quant_canvas_import_checker.py` 规定**只允许 Python 标准库 + `futu`**（实测 118 个模块）；`validate_ftquant_strategy.py` 已改为**从客户端 SDK 直接读该白名单**（`ast` 解析，随版本更新），不再用手写黑名单 —— **黑名单漏掉的 `import numpy` 会一路通过本地校验、然后在 GUI 里被拒，等于把失败推迟**。新增 11 项测试（`futu_pacing` 节流/重试/封顶、`closes_from`/`last_bar_date`、**过期数据必须被丢弃并告警**、白名单来自客户端而非硬编码）
- **v3.12.0** - **移除市场择时门控 + 修好每日清单的在线路径**（完整证据见 `knowledge/factor_evidence_2026.md` 第 8、9 节）：① **测了 6 种市场门控，全部有害** —— 同口径（`mom_12_1_raw` / 21 日 / top-5 / 228 只）下**无门控是最好的**：44.8% / Sharpe 1.14 / HAC **t=2.75**；SPY>200 日均线 32.9%（t=1.68）、回撤<5% 32.5%（t=1.62）、回撤<10% 36.8%（t=2.01）、回撤<15% 37.6%（t=2.12）、波动率<20% 36.2%（t=1.90）、波动率<25% 42.0%（t=2.36）。唯一改善回撤的"回撤<5%"（-27.2% vs -31.7%）要付 **12.3pp 年化 + t 从 2.75 掉到 1.62** —— 不成立。形态与 Clenow 的指数规则完全一致：**过滤器把回撤和反弹起点一起切掉了**。② **顺带查出 `daily_pick` 的门控从来不会触发**：它读 `US.VIX` / `US.SPX`，而**富途不认识这两个代码**（实测 `未知股票 VIX`），两值恒为 0、`classify_regime(0,0)` **每天返回 `neutral`** ⇒ 一个不会触发的安全网比没有更糟（清单看起来有风控、实际满仓裸奔）。已移除该门控（regime 只作上下文打印），并把 `market_regime.get_regime()` 的**静默假中性**改成 `regime="unknown" / status="unavailable"`。③ **在线取数路径此前是完全坏的，而且坏得不出声**：`request_history_kline` 有**滑窗限频（实测约 60 次/30 秒；冷启动连续约 40 次成功后每次立即失败）**，未节流的 228 只扫描只取到前几十只，报"180 dropped"看起来像流动性过滤，实际是取数被拒——**同一天的在线 top-5 与离线 top-5 是不同的组合**（在线 MU/INTC/AMAT/CRWD/PANW vs 离线 MU/WDC/STX/INTC/DELL），"看起来合理但是错的"是最坏的失败模式。新增 `_PacedFetcher`（**节流 30 次/30 秒 + 限频冷却 31 秒后重试同一只 + 冷却次数封顶 6**），并把计数**拆成 `symbols_unfetchable` 与 `symbols_filtered_out`**（正是混在一起才掩盖了故障）。④ 修掉在线路径另外两个静默失败：**futu 日志重定向**（不重定向时 `%APPDATA%` 写入被拒 → 取数线程抛异常被吞 → **0/228**；修复后 12 只从 0 passed 变 12 passed）与**进程永不退出**（`SysConfig.set_all_thread_daemon(True)`；原来扫描跑完进程挂死且 stdout 不刷新，与网络故障无法区分）；外加**盘中未完成 bar 警告**（日线带当日日期，盘中最后一根是半个交易日，会被当成收盘价喂进 12-1 动量——不报错，只是信号悄悄变错）。⑤ **额度预算（比频率更根本，查清了才敢说"每天扫 228 只"可行）**：`request_history_kline` 还有一层**额度**——**每只标的 30 天内只计 1 次、重复请求免费**，且**按账户资产分级（开户 100 / 1 万 HKD 300 / 50 万 HKD 1000 / 500 万 HKD 2000）**。本机账户 300 档，实测 `covered=228, needs_charge=0` ⇒ **228 只已在窗口内，每晚重复扫描不再消耗额度**；但**首次覆盖需 228 个额度，所以若账户只有 100 档则扫不完全池、且不报错**，上线前必须确认档位 ≥ 池子规模（剩余空间仅 53 ⇒ 短期无法扩池）。新增 `history_quota_preflight()`：读数据**之前**用 `get_detail=True` 的已覆盖名单精确算账，不够就输出 `PARTIAL universe` 警告，**读不出来也明确说"未检查"**（踩到的坑：该接口第三项返回的是 **dict 列表**不是代码字符串，直接 `set()` 会 `unhashable type: dict`，被 `try/except` 吞掉后表现成"未检查"）。⑥ `daily_pick` 新增 **`--capital` / `--sheet`**（输出等金额下单清单：$3,000 → 5 只 × $600、估算股数、2×ATR 止损）、**`--from-cache`**（离线确定性复核）、`--output`（落盘 JSON）。⑦ 顺带发现并记录：`backtest_engine.load_cache()` 会把放在 `_hist_cache` 里的基准 ETF（SPY/QQQ/RSP/IWM/MTUM/QUAL/USMV，共 7 只）一起读进来，所以历史验证跑的是 235 只而非 228 只 —— 本次测试已显式限定到池子。**验证**：节流后在线扫描 **228/228 全部取到**（修复前只有几十只），且**在线 top-5 与离线 top-5 完全一致**（MU/WDC/STX/INTC/DELL，修复前是 MU/INTC/AMAT/CRWD/PANW）。测试 507 → **523 passed**（`test_daily_pick.py` 9 → 24）
- **v3.11.0** - **时点季度基本面落地 + 真质量因子首测**（完整证据见 `knowledge/factor_evidence_2026.md` 第 7 节；数据面实测另见 `knowledge/futu_data_exploration_2026-09-10.md`）：① 新增 `scripts/futu_fundamentals.py`，用 `get_financials_statements --statement-type 4` 建**时点季度基本面缓存**（`data/_fund_cache/`，**228/228 只、15,745 个季度、最早回溯 2006-12-30**），每期 29 个字段（ROE/ROIC/毛利/净利/FCF 比/杠杆/周转）；**无前视靠 `available_date`（期末 + 45 天）**，打分按它过滤而不是按期末——按期末打分等于偷看未来，而且**表现为好结果而非报错**。② 工程要点：**进程内直连比子进程快 70 倍**（子进程每页都重新 import futu + 新建 OpenD 握手 ≈10s/只，复用单一 context **0.14s/只**）；**财务接口限频 30 次/30 秒且超限直接失败不排队**（不限频 1 秒内全 fail），限到 ~1 次/秒 + 一次冷却重试。③ `backtest_engine.backtest_style` 新增 **`panel=`**（按 `{symbol:{date:score}}` 打分），让时点因子复用全部既有指标。④ **真质量因子实测（176 只有 12 年历史的标的，动量基准跑同一批）**：质量单独**无超额**（21d/top-5 t=0.46、21d/top-10 t=0.25、63d/top-5 t=0.39），但**回撤永远最低**（比动量低 8–10pp）⇒ **是防御属性、不是收益来源**；**质量≥50 做过滤从不改善 Sharpe**（1.16→1.16、1.12→1.06、1.03→0.92）⇒ 权衡而非改进；质量与动量**秩相关三配置都约 0.118** ⇒ 信息不同但不互补。⑤ **两条方法学教训**：**部分缓存会翻转结论的符号**（62 只时说"质量门控恶化回撤"，176 只上变成"改善 4.4pp"）；**"好得不真实"必须先诊断**（曾打印 CAGR 71.3% / Sharpe 3.40 / 回撤 -3.4%，病因是门控后只剩寥寥几个调仓期，靠加 `rebalances` 到输出才暴露）。74 项新增测试
- **v3.10.0** - **$3,000 小资金落地：碎股能力实测 + 持仓数的剂量反应**（完整证据见 `knowledge/factor_evidence_2026.md` 第 5.6 节）：① **实测而非假设富途 OpenAPI 的碎股能力** —— 直连模拟账户实际发单：`qty=0.29` 被拒「数量不合法」、`qty=1.5` **被静默截断为 1.0 股**、`qty=2` 正常 ⇒ **只能整股**，且 ≥1 的小数会被**静默向下取整**（`execute_plan` 已加 `int()` 防护，否则会悄悄少买）；同时发现客户端内置 `futu.zip` 是**裁剪版、不含 `place_order`**（FTQuant 沙箱本身也无法下单）。② `live_trader` 新增 **`--capital`**（按 $3,000 规划而不是账户现金——模拟账户有 100 万，否则仓位被放大 300 倍）与 **`--fractional`**（输出 App「按金额」碎股委托单）；新增 `order_sheet()`（**等权按金额**，正是 `backtest_engine` 度量的口径）；`plan()` 现在**显式报告买不起的标的与现金拖累**（`unaffordable` / `deployed` / `cash_left`），此前是静默跳过。③ **实测整股限制的代价（$3,000，2026-09-10 真实名单）**：买 top-10 → **85% 现金拖累**（10 只里 8 只买不起）；买 top-5 → 48%。**明确不做"换便宜票"**——价格不是这个信号的一部分，换票等于换策略。④ **持仓数的剂量反应（本轮最重要的新证据）**：4 个切点 × 2 个调仓频率**全部单调** —— 21 日 top-3 **+3.54%/期（t=3.00）** > top-5 **+2.29%（t=2.81）** > top-10 +1.41%（t=2.44）> top-20 +0.62%（t=1.71）；63 日（top-3 +11.86% t=2.97 / top-5 +6.88% t=2.47 / top-10 +4.04% t=2.27 / top-20 +2.07% t=1.76）同序。**top-5 的样本内/外双双 >2（2.29/2.04），top-10 的样本外掉到 1.71**。单调剂量反应是真实效应的特征，不是挑参数；同时记下反面证据——**越集中，幸存者偏差被放大得越多**（2026-09-10 的 top-5 全是 AI 存储/半导体周期的赢家）。⑤ **成本实测**：小账户按**笔数**付费而非金额，$1/笔落在 $3,000 上是 **1.14%/年**（top-5/21日，34 笔）vs **2.31%/年**（top-10/21日，69 笔）；同一笔 $1 在 $150,000 账户只有 0.05% —— 小账户的成本劣势是结构性的。⑥ **$3,000 推荐配置：5 只等权 $600、按金额碎股、约每 21 个交易日调仓**（净年化 44.5%、最大回撤 **-31.6%**、最差年份 -15.0%）；对比 top-10 净 32.7% / 回撤 -28.2% / 最差 -7.6% —— **这是用回撤换收益，不是免费午餐**；不建议 3 只（回撤 -33.5%，单票暴雷无法分散）。新增 12 项测试（`order_sheet` 等权与碎股标记、`unaffordable`/`cash_left`、`--capital` 默认值、`int()` 防护），live_trader 测试 33 → 42
- **v3.9.1** - **OpenAPI 执行脚本 `live_trader.py`（默认 dry-run、默认模拟盘）**：FTQuant 的驱动标的要在界面逐个声明、无法扫全市场，所以"带选股的下单"只能走 OpenAPI（无池子限制，可打分信号被验证时的全部 228 只）。安全模型：**不加 `--execute` 只出计划不发单**；**默认模拟盘**，真钱需 `--execute` + `--env real` + `--unlock` **三者同时**，缺密码则**在建连接之前**退出；下单计划是**纯函数**（`plan` / `rank_universe` / `momentum_12_1`），无需 OpenD 与账户即可单测。实测打通全链路（模拟账户可用 1,000,002.59）：扫 228/228、产出 10 只计划含 ATR 止损、**未发出任何订单**。修掉测试抓出的真 bug：`OpenUSTradeContext` 不存在，正确构造是 `OpenSecTradeContext(filter_trdmarket=TrdMarket.US, security_firm=SecurityFirm.FUTUSECURITIES)`。新增**板块集中度警告**（2026-09-10 的 top-10 有 6 只半导体、含存储实为 8/10 同一产业周期）。33 项测试
- **v3.9.0** - **富途量化（FTQuant）策略移植 + 离线校验器**：从客户端安装目录逆向出平台 Python 环境与 SDK（`C:/Program Files/FTNN/app/<版本>/PythonEnv/`，`pkgs/futu.zip` 共 376 函数 / 410 类，`res/strategy_template.py` 为官方模板）；沙箱限制实测自 `futu/common/safe_env.py`：**禁 `ctypes/socket/subprocess/multiprocessing`、禁写文件（读允许）、无 numpy/pandas、Python 3.8**；**驱动标的须在界面逐个声明** ⇒ **无法扫描全市场**，因此定为**选股在本仓库、执行在平台**。产出 `scripts/ftquant_mom_12_1_raw.py`（12-1 动量排序 + 等权持有 + ATR 止损 + 每 21 根 K 线调仓，并**在文件内写明不做波动率缩放**的原因）与 `scripts/validate_ftquant_strategy.py`（从真实 `futu.zip` 读出导出名单，离线校验语法、**每个 API 调用是否真实存在**、禁用 import、是否写文件、是否有 `class Strategy(StrategyBase)`），把"只有点运行才知道拼错 API"的最差反馈回路前移到本地、秒级。修正一个真 bug：`current_price` 的第二个参数是 `THType`（时段）而非不存在的 `PriceType`
- **v3.8.0** - **实测海外知名交易系统 —— 简单因子胜出**（完整证据见 `knowledge/factor_evidence_2026.md` 第 5.4 节）：① 新增 `scripts/trader_systems.py`，把 6 套公开系统**按原文规则实现**：`clenow`（Andreas Clenow / 瑞士对冲基金 CIO 的 90 天对数回归斜率 × R²、100 日均线过滤、15% 单日跳空过滤）、`minervini`（Mark Minervini / 美国投资冠军的 8 条趋势模板）、`htf`（Kristjan Kullamaggi / Qullamaggie 的高紧旗）、`pullback_ema`（20-EMA 回调）、`vcp`（波动收缩模式）、`turtle55`（Richard Dennis 海龟 55 日通道突破）；② 回测引擎 `backtest_style` 新增 `scorer=` 与 `gate=` 参数，使外部策略无需注册即可测、市场过滤器可按期切换持仓/现金；③ 6 套系统注册进 `stock_selector.STYLES`（验证器与选股器**共用同一打分路径**），但**刻意不进 `daily_pick.DEFAULT_STYLES`**。**实测（同一 228 只池、21 日调仓、前 10 只、8bps、11.6 年）**：**没有任何一套著名系统在统计上打败最简单的 12-1 动量** —— mom_12_1_raw **34.3% / t=2.36**，其后 minervini 24.5%（t=1.24，但**回撤最低 -23.0%**）、htf 18.8%（0.51）、vcp 18.8%（0.45）、clenow 18.7%（0.37）、pullback_ema 13.7%（-0.73）、turtle55 9.3%（-1.75），6 套全部未过 t>2。**逐项排除口径不公**：扫 5/10/21/63 四种调仓频率，`mom_12_1_raw` 每种都是最好的；剔 40 只高价股做中小盘切片（188 只）排序不变；每个系统都用其文献默认参数。**三个具体发现**：(a) **Clenow 的市场过滤器（指数 200 日均线上方才开仓）是净损害** —— 加在 clenow 上 18.7%→16.4%，加在我们的动量上 34.3%→25.4%（t 2.36→1.15），因为它同时滤掉了大量反弹起点；(b) 唯一有增量价值的是**"Minervini 模板做过滤 + 动量做排序"**（6/7 门槛）：29.9%、Sharpe 1.05、回撤 **-25.2%**（优于纯动量），但少赚 4.4pp/年且 t 仅 1.84 → **属风险-收益权衡而非改进，故未改默认**；(c) Minervini 模板作为**风险过滤**有价值（回撤最低），作为**收益来源**没有。**限定条件**：只建模了各系统的"选股层"，未建模其风险管理（ATR 仓位/止损/分批）——他们实盘收益可能主要来自后者。新增 45 项测试（每套系统的契约、拒绝逻辑、R² 偏好、趋势模板计数、HTF 紧凑度、VCP 收缩序列、以及"默认清单绝不被著名名字污染"的守卫）
- **v3.7.0** - **扩样本到 228 只 / 12 年，做组合级回测 —— 找到了唯一通过检验的因子**（完整证据见 `knowledge/factor_evidence_2026.md` 第 5 节）：① 股票池 **118 → 228 只**（futu 快照实测校验有效性与流动性后合并；注意快照接口一次 20 个代码会静默丢数据，必须小批次 + 单只重试）；② 新增**本地长历史缓存**（`data/_hist_cache/`，228 只 × 3000 根日线 ≈ 2014-10 ~ 2026-09），后续所有回测离线秒级完成，不再反复联网踩超时；③ 新增**组合级回测引擎 `backtest_engine.py`**——回答"按这个信号买进去到底赚多少"：年化、Sharpe、最大回撤、胜率、换手率、8bps 单边交易成本、相对基准的 HAC t 与中心化块自举 p 值，另有 IS/OOS 切分与逐年分解；④ 新增 **`mom_12_1_raw` 排名器**（纯 12-1 动量、**不做波动率缩放**），并把它设为 `daily_pick` 默认风格。**实测（228 只、~12 年、139 个调仓期、前 10 只、含成本）**：**mom_12_1_raw CAGR 29.6% / Sharpe 1.21 / 超额相对 SPY +15.4%/年 / HAC t=3.58（越过 Harvey-Liu-Zhu t>3 门槛）/ bootstrap p=0.008 / 11-12 个自然年为正 / 样本内 t=3.00、样本外 t=2.34 双双显著**；对照：`mom_12_1`（波动率缩放版）同数据 t 仅 1.03 → **波动率缩放是净损害**；`quality` t=-2.42、`low_vol` t=-3.31 **显著为负**（不再作默认腿部）；池子等权 +3.5%/年（t=2.55）但**跑输 QQQ 0.8%/年**，说明这部分"超额"主要是科技成长 beta + 幸存者偏差，不是选股能力。⑤ 修正 bootstrap 实现缺陷：未中心化的块自举会构造性保留均值，**任何正均值序列都返回 p≈0.5**、永远无法拒绝；改为重采样 `d - mean(d)` 后与 HAC t 在所有风格上完全一致。新增 19 项测试（含 bootstrap 中心化、成本方向、年化口径、缓存 fetcher）
- **v3.6.0** - **按文献证据重建因子库**（调研与来源见 `knowledge/factor_evidence_2026.md`）：① **修复 `fetch_kline` 只能取到约 1 年历史**（不给日期范围时 futu 固定返回 251 根日线/52 根周线，与 `num` 无关）—— 后果是**所有需要长回看的因子静默全 0 分**、验证器只报"无证据"而不报错，12-1 动量（需 274 根）根本无法计算；现在 `num>250` 时自动推算起始日期，实测稳定取到 800 根（3 年），横截面调仓期也从 9 期提升到 35 期；② 新增**证据背书的三因子**：`mom_12_1`（纯 12-1 动量、波动率缩放、MA200 趋势过滤——旧的 momentum 混了 52 周高点追逐，是另一回事）、`st_reversal`（短期反转，方向与动量相反，独立验证）、`low_vol`（低风险异象，作可选防守腿）；③ `daily_pick` 默认风格改为**显式 `DEFAULT_STYLES=[mom_12_1, quality]`**（不再静默扫描所有已注册风格），取数 400→800 根；④ 验证器打分窗口默认改为**截至当天的全部历史**（短窗口会让 MA200/12-1 类因子静默归零）。**实测（60 只流动股、800 根≈3年、21 日、35 期、2100 对）**：mom_12_1 IC=+0.0129（NW t=0.37）、前 20% 组合 +189.3% vs 等权 +135.8%（超额 **+53.5pp**）——但**胜率仅 48.6%**，超额由少数大赢家驱动，**未达显著**；st_reversal IC=-0.0289（t=-1.13）；low_vol IC=-0.0930（t=-1.76，三年 -103.9pp，与 2026 年"低波动为最差因子"的机构口径一致）。**结论：暂无因子达到统计显著，mom_12_1 是唯一方向为正者，不可据此加杠杆**。新增 5 项测试
- **v3.5.2** - 按实测改造 reversal 并**复测（结论：企稳确认救不了它，但病因定位了）**：① 新增**企稳确认硬门控**——回调中"仍在下跌"的票直接 0 分（必须收阳，即有人开始接），收阳且**收复 MA5** 记 +30、仅收阳 +12；回调深度与超卖权重从 30 降到 20 让位（暴力反弹反而分数更低，因为它已经吃掉了折价与超卖，入场更差）；② 新增**板块归簇** `SECTORS`/`sector_of`（半导体单独一簇），扫描器加 `--max-per-sector`（默认 3，0 关闭），事件研究加板块分解 / `worst_sector` / `sector_spread_pct` —— 一个坏板块再也无法藏在还算体面的均值里。**60 只池复测：信号 127→92（企稳确实滤掉了一批），但每股超额 -0.31%→-0.66%（t=-0.63）仍未通过**；关键诊断是**板块**：semis 33 个信号、平均超额 **-8.0%**，而 software +1.41%、consumer +2.64%，板块间价差 13.3 个百分点，最差 4 只（MU/MRVL/AMAT/AMD）全是半导体 -10%~-18%。**结论：问题不在"接刀时机"，而在于高波动趋势股的回调往往就是趋势反转的起点**——下一步应在 reversal 上加波动率/贝塔过滤（只在低波动趋势股上做回调），而不是继续微调入场规则。新增 7 项测试
- **v3.5.1** - 验证器新增**事件研究模式** `--mode events`：reversal 这类"稀有信号"风格无法用横截面 IC 验证（典型一天几乎每只票都是 0 分，排序统计量退化，实测 IC 全 None）。事件研究问对的问题：**信号触发后，未来收益是否好于该股自己的平常日**。逐 symbol 走历史：得分 ≥ 阈值记为信号日并跳过 horizon 根（同一段行情不重复计数），其余日构成该股自身基线；每股超额 = 信号日均值 − 平常日均值，以 **symbol 为独立样本做单样本 t 检验**（一只大牛股造不出显著性）。注意：事件研究的打分窗口是**截至当天的全部历史**（reversal 需要真实 MA200 判定趋势，120 根窗口永远算不出来会静默全 0——踩过并修复）；CLI 阈值按模式取默认（single 60 / events 20）。**实测（15 只流动股、400 根、10 日持有）：10 只票 36 个非重叠信号，信号日 +2.48% vs 平常日 +0.90% → 每股超额 +1.58%，t=1.80（10 个独立样本）——方向偏正但不够显著**，需扩大样本再判。5 项新增测试
- **v3.5.0** - 按产品目标（每日收盘选股）重构：新增纯因子引擎 `stock_selector.py`（momentum 趋势动量 / reversal 回调低吸 / quality 低波质量 三种**独立**排行——合并成一个综合分会互相抵消）+ 每日扫描命令 `daily_pick.py`（自建流动性池 + futu 热门榜并集，实价重过滤流动性；单只取数带守护线程，坏代码不拖垮整夜任务；regime 为**门控**：bear/volatile 直接输出 NO_NEW_LONGS；每候选附 close / ATR% / 2×ATR 止损 / 波动率目标仓位；输出标注"研究候选非买入保证"）。关键纪律：`strategy_validator.py --mode cross` 新增 `--style composite|momentum|reversal|quality`，**live 选股与验证共用同一打分回调** —— 因子不可能只进实盘不进验证。25 项新增离线测试（含"回调趋势内的刀不接"：无前序上涨时 reversal 必为 0）
- **v3.4.0** - `strategy_validator.py` 新增**横截面验证** `--mode cross`（有统计功效的模式）：单标的纵向验证重叠窗口把 186 个样本压到 ~37 个独立观测，而检测 IC=0.05 需 ~1500 个 —— `no_evidence` 其实是"还没测出来"。横截面模式改为**每个调仓日对整个股票池打分排序**：调仓日之间间隔 = horizon（前视窗口永不重叠）、每日一个横截面 IC、IC 序列同时给 naive 与 **Newey-West HAC t 统计量**（相邻期共享市场状态，naive 标准误太小正是 alpha 被发明出来的方式）、前 quantile 组合 vs 等权股票池 + 胜率 + 最大回撤。内置 40 只流动性美股默认股票池。**实测（15 只大型股、300 根、10 日、19 期、285 对）：mean IC=-0.1084，NW t=-2.18 显著为负；按分数买前 20% 收益 -19.49% vs 等权 +11.64%，超额 -31.12%，仅 31.6% 期间跑赢 → `inverse`**。即：该技术分在横截面上**奖励已涨上去的名字、其后 10 天倾向回归**——现阶段直接拿它选股是亏钱的（这也印证了把动量簇权重从 65% 降到 50% 的方向）。新增 9 项离线测试
- **v3.4.0** - `risk_manager.py` 新增**波动率目标仓位** `vol_target_position`：固定百分比仓位在 15% 波动率和 80% 波动率的标的上意味着天差地别的风险；波动率目标按"该仓位实际贡献的组合风险"来定仓位 = target_vol / 已实现年化波动。三重约束（波动率目标 / 硬性最大仓位 / ATR 止损风险上限）逐一列出、报告哪一条实际生效（`capped_by`），而不是默默取最小。默认值按单票场景调优：10% 年化波动贡献、25% 仓位上限、1% ATR 风险。10 项离线测试
- **v3.4.0** - `decision_engine.py` 把**市场状态从"10% 分数"改成前置门控**：熊市/高波动只让综合分少 5 分，远不足以拦下多头——但对股票多头来说"有没有暴露"远比"选哪只"重要。现在 regime 权重为 0（不参与投票、不掺水置信度），`apply_regime_gate` 在 bear/volatile 下把 BUY/STRONG_BUY 降级为 HOLD 并记录被拦下的原决策；做空不受影响（下跌正是做空的用途）；门控在生成交易计划**之前**执行，被压制的多头不会拿到可执行的多头入场。权重同时按"信息是否独立"重排：旧 30/20/15 的技术/增强/K线是虚假分散（CCI/RVI/StochRSI/WR 与 MACD/RSI 本质是同一个动量信号，K线形态是全栈复现证据最弱的一类）→ 新权重 technical 35 / enhanced 10（仅作确认）/ candlestick 5（象征性）/ earnings 25 / smart_money 15，`FACTOR_WEIGHTS` 为模块级常量便于调参后用 validator 复测。新增 6 项门控测试
- **v3.4.0** - 新增策略验证体系 `strategy_validator.py`：这是第一次真正检验"综合分有没有用"。逐根 K 线重算综合分，**只用该时刻可得的数据**（为此把 `generate_signal` 拆成纯函数 `signal_from_df(df)` + 取数包装层——原函数自己抓数，只能给"现在"打分，无法回测），再衡量未来 N 日收益。输出：Spearman 信息系数 IC 及近似 95% 置信带（样本少时 IC 会自动落入噪声带，不会把噪音当 alpha）、五分位分组收益与单调性、阈值策略 vs 买入持有（**非重叠**持仓，否则 5 日周期会把同一段行情数 5 遍）及最大回撤，并给出 `predictive / inverse / no_evidence / insufficient_samples` 明确结论。**US.NVDA 实测（400 根、5 日）**：IC=-0.0498，置信带 [-0.19, 0.09] 不显著；分组收益 0.29/1.52/0.69/0.59/0.33% 非单调（最高分组反而不如第二组）；score≥60 策略收益 5.26% vs 买入持有 25.85%，跑输 20.6 个点 → 结论 `no_evidence`。17 项离线测试，含"篡改未来K线后早期打分不得变化"的前视护栏
- **v3.4.0** - 修复 `ml_predictor.py` 会让输出 confidently wrong 的一组问题：① 模型固定存 `data/ml_model.joblib` 且**文件名不含 symbol**，用 NVDA 训练完再预测 AAPL 会直接加载 NVDA 模型且无任何提示 —— 改为按 symbol 隔离，且仅当 bundle 记录的 symbol 与特征列都匹配才复用；② `StandardScaler` 在切分训练/测试**之前**对全量数据 fit，泄露测试集统计量、虚报准确率 —— 改为只在训练集 fit；③ 用测试集准确率**选** RF/GBM 再把该准确率当诚实指标（选择偏差）—— 改为 train/val/test 三分，val 选模型、test 只做最终评估，并显式标注 `metrics_out_of_sample`；④ 新增多数类基线 `baseline_accuracy` 与 `edge_over_baseline`（55% 上涨的数据集上 55% 准确率等于瞎猜）；⑤ `forecast_7d` 取的是 `len-offset` 即**历史**K线，却叫"7日预测" —— 改为名副其实的 `recent_bar_signals`；⑥ `ml_features` 尾部的 5 根K线曾用 `close[-1]` 当未来价造标签 —— 改为 NaN 标签（训练排除、预测保留）。新增 8 项离线测试
- **v3.4.0** - 修复 `decision_engine.py` 打分正确性：① **取数失败被当成看空** —— 因子失败时 `weighted_score=0` 但权重仍计入，技术面（权重30）一挂就凭空扣 15 分，把"数据中断"翻译成"卖出信号"。现在失败因子标记 `available=False` 并从分母剔除；② 权重不归一化，`--fast`（跳过聪明钱）模式总分系统性低约 10%，与全量模式不可比 —— 改为按**可用**权重做加权平均；③ `confidence` 原为 `composite*0.9+5` 的确定性变换，纯装饰 —— 改为因子一致性（离散度）+ 数据完整度 + 偏离中性程度的合成，且可读因子 <2 个时一致性记 0（"无分歧"是"无证据"而非"全体同意"）；④ 新增 `factor_spread` / `conflict`，因子严重打架时显式暴露而非平均成安静的 HOLD；⑤ **SELL/STRONG_SELL 曾输出多头交易计划**（方向自相矛盾）—— 现在按方向生成多/空计划；⑥ 无可读因子时返回 HOLD + `insufficient_data`，不再凭空造方向。新增 5 项离线回归测试
- **v3.3.6** - 修复测试套件"跑完不退出"（`tests/conftest.py`）：① futu 日志硬写 `%APPDATA%`，写入被拒时 SDK 静默挂死 —— 在 `import futu` 前临时劫持 `os.getenv`，把日志重定向到 `data/_futu_log`（`ft_logger` 在 import 时即创建单例 handler，事后无法改路径）；② `futu/common/callback_executor.py` 的线程未设 daemon，任何存活的 `OpenQuoteContext` 都会让 pytest 打印完总结后永久挂起 —— 改用官方开关 `SysConfig.set_all_thread_daemon(True)`，并在 `pytest_unconfigure` 关闭共享 context。修复后全量 251 项约 3.5 分钟内正常退出（此前会挂起 30 分钟以上）
- **v3.3.6** - 修复决策引擎 precomputed 快路径：因子赋值误嵌套在 `else` 分支，导致传入缓存数据时 technical/enhanced/candlestick 三项因子被静默丢弃（综合分失真）；smart_money 改读 `total_score`；决策阈值调整为 70/45/35/25；auto_selector 现在把 tech/enhanced/candlestick/earnings/regime/price 全部复用给决策引擎（regime 调整到 decision 之前执行），并修复 `run_analysis_parallel` 漏传 `smart_money_data` 导致聪明钱因子从不生效的问题；新增 13 项离线回归测试
- **v3.3.7** - 修复 `scripts/agent.py` CLI 完全不输出结果的严重 bug：`main()` 末尾的 `elif args.output / else: print(output)` 输出块与命令分发同属一个 `if/elif` 链，命令一旦命中就被短路，导致 analyze/signal/top/scan 等所有命令都不打印任何结果、`--output` 写文件也是死代码。把 `elif args.output:` 改为独立的 `if args.output:` 修复。同时修复 `top`/`scan` 两个命令只赋值 `result` 未赋值 `output`（输出块可达后本会 NameError）的问题。新增 3 项 CLI 回归测试（`test_agent.py` 现 11 项）
- **v3.3.5** - 修复futu API扫描后退化问题：缓存smart money的price/tech/kline数据，analysis阶段直接使用缓存而非重新请求API，所有模块（tech/candlestick/enhanced）现在显示完整数据
- **v3.3.4** - 修复get_hot_list API参数(['US']->'US')、移除shared ctx.close()防止共享连接中断、analysis改为顺序执行避免线程安全崩溃、238测试全部通过
- **v3.3.2** - 修复composite score计算错误（除以total_weight改为直接用weighted_score之和）、修复price=0 bug、compute_decision_fast提速15倍(48s→3s)、修复options_analysis._futu_call未定义错误
- **v3.3.0** - 新增一键选股(auto命令)、auto_selector模块、futu_pool共享连接池优化、10项auto_selector测试 - 新增K线形态识别、增强指标(CCI/RVI/StochRSI/WR/OBV背离)、财报分析、六因子决策引擎、180测试全部通过
- **v2.8.0** - 修复6个深度BUG：get_price连接池泄漏、get_hot_list Market枚举、scan_stocks ScanConfig未定义、options IV/PCR错误API、market_sentiment连接泄漏
- **v2.7.0** - 聪明钱筛选器、155项测试、价格实时修正
- **v1.0.0** - 初始版本：基础分析、回测、风险计算
