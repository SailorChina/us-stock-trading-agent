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
| **每日选股** | `daily_pick.py` + `stock_selector.py` | 收盘后扫描：momentum/reversal/quality 三层独立排行、regime 门控、流动性过滤、2×ATR 止损 + 波动率目标仓位 |
| **风险管理** | `risk_manager.py` | ATR止损、风险收益比、动态仓位、组合诊断 |
| **市场情绪** | `market_sentiment.py` | VIX分级、指数报价、Magnificent 7 |
| **市场状态** | `market_regime.py` | Bull/Bear/Volatile/Neutral 自动识别 |
| **一键选股** | `auto_selector.py` | 聪明钱+热门榜单扫描，并行全量分析，输出 ranked 表格 |

## 测试状态

```
331 passed (全部通过，非沙箱/无文件锁环境)
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
| **`test_stock_selector.py`** | **11** | **选股因子：趋势/回调低吸/质量的方向性、不接落刀、淘汰低价股** |
| **`test_daily_pick.py`** | **7** | **每日扫描：三风格排行、regime 门控、流动性过滤、热门池并入、坏数据存活** |

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
python scripts/daily_pick.py                       # momentum + reversal + quality
python scripts/daily_pick.py --style momentum --top 10
# 单独验证某个风格（live 与验证共用同一打分函数）：
python scripts/strategy_validator.py --mode cross --style momentum --limit 20

# 事件研究（稀有信号风格如 reversal 的正确验证法：信号日 vs 该股平常日）：
python scripts/strategy_validator.py --mode events --style reversal --horizon 10 --bars 400 --limit 15

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
