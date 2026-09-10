# 富途 Skills 数据面探索报告（2026-09-10）

目标：搞清 `futuapi` 技能（173 个脚本）在**选股与策略交易**上真正能提供什么，
哪些能变成**可验证的因子**，以及卡在哪里。

全部结论来自本机实测，不是读文档推断。

---

## 1. 可用端点清单（18 个测了，15 个返回真实数据）

单次调用耗时 1.8–4.3 秒，均为 OpenD 直连。

| 端点 | 状态 | 返回形态 | 对因子的价值 |
|---|---|---|---|
| `get_financials_statements`（type=4 关键指标） | ✅ | **每期 29 个字段**，含 ROE/ROIC/毛利率/净利率/FCF-收入比/杠杆/周转率，带 `fiscal_year`/`period_text`/`date_time` | **★★★★★ 真质量因子** |
| `get_valuation_detail` | ✅ | `trend` / `market_distribution` / `plate_distribution` / `profit_growth_rate` | ★★★★ 估值因子（结构待细解） |
| `get_option_chain` | ✅ | **1296 个合约** | ★★★★ 期权/波动率 |
| `get_option_expiration_date` | ✅ | 23 个到期日 | ★★★ |
| `get_capital_flow` | ✅ | 100 行 | ★★ 时间戳可疑，见 §3-B3 |
| `get_capital_distribution` | ✅ | 超大/大/中/小单 流入流出 | ★★★ 资金结构 |
| `get_short_interest` | ✅ | 10 期 | ★★★★ 空头因子 |
| `get_daily_short_volume` | ✅ | 10 期 | ★★★★ 空头因子 |
| `get_research_rating_summary` | ✅ | 10 家机构评级 | ★★★★ **评级变动**因子 |
| `get_insider_trade_list` | ✅ | 10 条 | ★★★★ 内部人交易因子 |
| `get_shareholders_overview` | ✅ | 主要股东/类型/持有期 | ★★★ |
| `get_earnings_calendar` | ✅ | 34 条 | ★★★ 事件驱动 |
| `get_hot_list` / `get_top_movers_rank` | ✅ | 各 10 条 | ★★ 热度 |
| `get_plate_list` | ✅ | 50 个板块 | ★★★ 板块因子 |
| `get_option_volatility` | ❌ | `只支持期权代码` — 要传具体期权，不能传正股 | — |
| `get_institution_holding_list` | ❌ | 需 `--market` + `--institution-id`（要先拿机构列表） | — |
| `get_market_state` / `get_fed_watch_*` | ❌ | 参数签名与命令行不一致（文档/实现脱节） | — |

**结论：数据面确实很丰富。** 但"有数据"和"能建因子"之间隔着时间序列深度，
见下一节。

---

## 2. 最大的收获：**时点（point-in-time）季度基本面可以建起来**

这是本项目此前**完全空白**、且被我标记为"A 级证据但算不出来"的缺口。

实测 `get_financials_statements US.NVDA --statement-type 4 --num 12`：

- 返回 **12 个季度**（2025/Q1 → 2027/Q2）
- **返回 `next_key` ⇒ 可翻页继续回溯历史**
- 每期带 `period_text` / `date_time_str` / `financial_type`

字段样例（US.AAPL 2026/Q3）——都是**真值**，且带 YoY/QoQ：

| 字段 | 值 |
|---|---|
| 毛利率 | 48.65% |
| 归母净利率 | 27.62% |
| **净资产收益率 ROE** | **148.75%** |
| 总资产净利率 ROA | 36.08% |
| **投入资本回报率 ROIC** | **71.75%** |
| 自由现金流/收入 | 29.28% |
| 财务杠杆 | 356.46% |
| 存货周转率 | 28.17 次 |

同时还有 `get_valuation_detail` 提供 PE/PB/PS 的**历史趋势**与历史分位。

⇒ **可以构造真正的质量因子（ROE/ROIC/毛利率）与价值因子（E/P、B/P），
并且按财报期做时点对齐 + 发布滞后处理。** 这正是 Hou-Xue-Zhang 复现里存活下来的
两类因子。

**代价**：只能**逐标的**取（约 1.8s/只）。228 只 ≈ 7 分钟，可接受。

---

## 3. 三个硬阻塞（都有实测证据）

### B1 —— 选股接口无法构建宽基全市场池

这是最重要的阻塞，因为它直接卡住"治幸存者偏差"这条路。

**证据**：

1. `get_stock_filter --limit 250/300` → `请求个数超过限制`
   ⇒ **单次上限恰好 200 行**。
2. 尝试用市值区间翻页（`--max-market-cap` 接上一页最小市值）→
   `简单属性，财务属性，形态属性不支持对同一字段重复指定筛选条件`
   ⇒ **排序和筛选不能是同字段**。
3. 改成一页「排序用价格 + 筛选用市值」绕开冲突 → 返回行里 `market_val` **全为 0**
   （文档已说明：只有参与筛排的字段才有值）⇒ **无法取得下一页的分界值**。
4. **决定性一击**：`--min-market-cap 1e12`（≥$1T）与 `--max-market-cap 1e10`（≤$10B）
   返回了**完全相同的 50 行**（按价格排序的 BRK.A / SBNC / LICT / FMBL / NVR / SEB…）
   ⇒ **市值筛选被静默忽略，完全不生效。**

**结论**：`get_stock_filter` 实际只能当「按某字段取前 200 名」用。
`--sort market_val --limit 200` 可以稳定拿到**市值前 200**（门槛 $105.86B，
偏超大盘、含大量外国 ADR）。

### B2 —— V2 选股器被 protobuf 版本打坏

`get_stock_screen`（协议 3252，本应支持 244+ 因子）任何配置都直接报：

```
'google._upb._message.FieldDescriptor' object has no attribute 'label'
```

`FieldDescriptor.label` 在 protobuf 4+ 已移除，本机是 **protobuf 7.35.1**。
⇒ **V2 完全不可用**。这条不是我的用法问题——同一个配置连 `MARKET=US` 最简筛选都过不去。

（潜在修法：把 protobuf 降到 3.x。**但我不会自作主张降级** —— protobuf 被
pandas/numpy 之外的多个包依赖，降级风险大于收益。且 V1 的 200 行限制依然存在，
修好 V2 也未必能突破。）

### B3 —— 部分时间序列"有行数但没时间轴"

`get_capital_flow US.NVDA` 返回 100 行，但**每一行的 `last_valid_time` 完全相同**
（`2026-09-10 05:31:52`）。看起来是 100 个切片而非 100 天。
⇒ 在搞清时间轴语义之前，**不能当因子用**（会把"同一时刻的 100 个分位"误当成"100 天历史"）。

同类需要先验证时间轴再用的：`get_capital_distribution`。

### B2 附带发现（文档与实现脱节）

技能文档明确写了两个坑，值得记下（省了大量试错）：

> **美股财务因子筛选覆盖稀疏**：`ROE`/`NET_PROFIT` 作 US **filter** 命中极少
> （实测 ROE ANNUAL 全美仅 ~3 只）
> **financial retrieve 可能不返回值**：即使 filter 生效，retrieve 的 `dval` 仍可能为 None

⇒ 所以基本面**必须走 `get_financials_statements` 逐标的**，不能靠选股器批量筛。

---

## 4. 因此：可建的新因子清单（按证据强度排序）

| 优先级 | 因子 | 数据来源 | 证据等级 | 可回溯性 |
|---|---|---|---|---|
| **P0** | 质量：ROE / ROIC / 毛利率 / 净利率 | `get_financials_statements` type=4 | **A**（Hou-Xue-Zhang 存活） | ✅ 12 期 + 翻页 |
| **P0** | 价值：E/P、B/P（PE/PB 倒数） | `get_valuation_detail` + 价格 | **A** | ✅ 历史趋势 |
| P1 | 空头：空头比例 / 挤空压力 | `get_short_interest`、`get_daily_short_volume` | B（有文献支持） | ⚠️ 仅 10 期 |
| P1 | 分析师评级变动 | `get_research_rating_summary` | B | ⚠️ 10 条 |
| P2 | 内部人买入 | `get_insider_trade_list` | B | ⚠️ 10 条 |
| P2 | 资金结构（大单净流入） | `get_capital_distribution` | C | ❓ 时间轴待验证 |
| P3 | 板块轮动强度 | `get_plate_list` + 板块行情 | C | — |
| — | 期权 IV / 偏度 | `get_option_chain` | C | 需 1296 合约/标的，成本高 |

**最重要的一句**：P0 两项是**本项目历史上第一次能够真正测"价值/质量"**。
此前的 `quality` 风格只是**低波动代理**，而且实测**显著为负**（t=-2.42）。
现在可以测真正的质量因子了。

---

## 5. 建议的执行顺序

1. **建基本面缓存**：228 只 × 12 期（约 7 分钟），落 `data/_fund_cache/`。
   需要处理发布滞后（财报期结束 → 实际可得日期，保守用 +45 天）。
2. **构造并验证 P0 因子**：ROE / ROIC / 毛利率 的**横截面分位**，
   与 `mom_12_1_raw` 做**正交性检验**（相关性多高？叠加后是否优于纯动量？）。
   这一步直接回答一个此前无解的问题：**质量在这个池子里到底有没有用。**
3. **组合层检验**：`mom_12_1_raw` + 质量筛选 是否改善回撤
   （此前 Minervini 模板做过滤能降回撤但降收益，质量因子是真因子，可能更好）。
4. P1/P2 因子在 P0 之后做，且必须先验证时间轴语义。

**不要做的事**：不要把 B1 绕过去强行扩池（市值筛选是失效的，扩不出可信的宽基池）；
不要为了修 V2 去降级 protobuf。

---

## 6. 与既有结论的关系

- 本报告**不推翻**任何既有结论：`mom_12_1_raw`（top-5，t=2.81）仍然是通过检验的唯一因子。
- 本报告**新增的是能力**：第一次有了真价值/质量数据，以及空头/评级/内部人等另类数据。
- **幸存者偏差仍未解决**，且原计划的解法（用选股器建宽基池）被 B1 证伪。
  这条要在池子相关的一切结论上继续保留警告。
