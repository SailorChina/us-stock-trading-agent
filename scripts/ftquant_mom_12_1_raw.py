# -*- coding: utf-8 -*-
"""富途量化（FTQuant）策略 —— mom_12_1_raw 纯 12-1 动量

【策略来源】
本策略是本仓库已验证信号 mom_12_1_raw 的富途量化移植版。
验证证据（228 只美股 / 11.6 年 / 21 日调仓 / 前 10 只 / 扣 8bps 成本）：
    年化 34.3% | Sharpe 1.12 | 最大回撤 -28.4%
    相对 SPY 超额 +15.4%/年 | HAC t=3.58 | bootstrap p=0.008
    11/12 个自然年为正；样本内 t=3.00、样本外 t=2.34 双双显著
详见 knowledge/factor_evidence_2026.md 第 5 节。

【信号定义（唯一重要的一行）】
    动量 = 收盘价(t-21) / 收盘价(t-252) - 1
即"过去 12 个月收益、跳过最近 1 个月"。
跳过最近一个月不是可选优化：那个窗口里含短期反转效应，留着会部分抵消动量。

【关键教训：不要做波动率缩放】
本仓库实测过"把 12-1 收益除以实现波动率"（所谓 Sharpe 动量），
在同一份数据上 t 值从 3.58 掉到 1.03 —— 是净损害。
所以这里**不做任何缩放**，直接用原始收益率排序。

【平台限制与设计取舍】
富途量化的驱动标的要在界面上逐个声明（数量有限），**无法扫描全市场**。
因此本策略的定位是"执行端"：在你声明的 N 个标的里按动量排序、取前 K 个持有。
选股端（从 228 只里筛出这 N 只）由本仓库的 daily_pick.py 每天收盘后完成：
    python scripts/daily_pick.py --styles mom_12_1_raw --top 12
把输出的 12 只填进界面的驱动资产即可。

【沙箱限制（实测）】
- 禁用 import：ctypes / socket / multiprocessing / subprocess / sqlite
- 禁止写文件（open 带 w/a/x/+ 会抛 ForbiddenOpError），读文件允许
- 没有 numpy / pandas，只有标准库 + futu SDK，Python 3.8
所以下面全部是纯 Python 实现。
"""

from futu.common.ft_logger import logger as ftlogger
import traceback

try:
    import futu
    import sys
    import math
    import time
    from futu.common.constant import *
    from futu.common.err import *
    from futu.common.thread_cache import get_thread_cache
    from futu.quant.wrapper_utils import log_info, log_warn, log_error
    from futu.quant.open_quant_context import OpenQuantContext
    from futu.quant.common import QuantParam, QuantRunParam
    from futu.quant.strategy_base import (StrategyBase, declare_trig_symbol,
                                          show_variable, declare_strategy_type,
                                          check_bar_type)
    from futu.quant.strategy_interface_v2 import *
    from futu.quant.constant_v2 import *
    from futu.quant.runner import main, enable_debug_mode
except:
    traceback.print_exc()
    ftlogger.warning('Import exception:', exc_info=True)
    raise RuntimeError('quit')


# select 参数的含义（来自 SDK 默认值 select=2）：
#   1  = 当前这一根（可能还没走完）
#   2  = 最近一根已收完的 K 线
#   2+k = 往前数 k 根
# 算 12-1 动量要用"已收完"的 K 线，所以下面统一走 _SELECT_BASE 偏移。
_SELECT_BASE = 2


class Strategy(StrategyBase):

    # ------------------------------------------------------------------
    # 1. 驱动标的
    # ------------------------------------------------------------------
    def trigger_symbols(self):
        """最多声明 12 个驱动标的。

        请在富途量化界面的「驱动资产」里逐个选择标的；没用的槽位留空即可，
        策略会自动跳过（见 _active_stocks）。
        标的数量建议就是 daily_pick.py 选出的候选数（默认 12）。
        """
        self.s01 = declare_trig_symbol(True)
        self.s02 = declare_trig_symbol(True)
        self.s03 = declare_trig_symbol(True)
        self.s04 = declare_trig_symbol(True)
        self.s05 = declare_trig_symbol(True)
        self.s06 = declare_trig_symbol(True)
        self.s07 = declare_trig_symbol(True)
        self.s08 = declare_trig_symbol(True)
        self.s09 = declare_trig_symbol(True)
        self.s10 = declare_trig_symbol(True)
        self.s11 = declare_trig_symbol(True)
        self.s12 = declare_trig_symbol(True)

        self.stocks = [self.s01, self.s02, self.s03, self.s04, self.s05, self.s06,
                       self.s07, self.s08, self.s09, self.s10, self.s11, self.s12]

    # ------------------------------------------------------------------
    # 2. 可调参数（界面上会渲染成设置项，不需要改代码）
    # ------------------------------------------------------------------
    def global_variables(self):
        # 持仓只数：验证过 10 只是风险收益最优（对比 3 只：中位数只低 10pp，
        # 但最差年份好一倍，-7.6% vs -15.7%）
        self.top_n = show_variable(4, GlobalType.INT)

        # 调仓间隔（交易日）。21 ≈ 每月一次，是验证时用的频率。
        self.rebalance_days = show_variable(21, GlobalType.INT)

        # 12-1 动量的两个回看参数
        self.lookback = show_variable(252, GlobalType.INT)   # 12 个月
        self.skip = show_variable(21, GlobalType.INT)        # 跳过最近 1 个月

        # ATR 止损倍数：2 倍 ATR 是我们的默认风控
        self.atr_period = show_variable(14, GlobalType.INT)
        self.atr_stop_mult = show_variable(2.0, GlobalType.FLOAT)

        # 单只最大仓位占总资产比例（%），防止某只过高
        self.max_weight_pct = show_variable(25.0, GlobalType.FLOAT)

        # 内部状态（不要手改）
        self.bar_count = show_variable(0, GlobalType.INT)       # 自增计数器
        self.last_rebal = show_variable(0, GlobalType.INT)      # 上次调仓时的计数

    def custom_indicator(self):
        pass

    # ------------------------------------------------------------------
    # 3. 初始化
    # ------------------------------------------------------------------
    def initialize(self):
        declare_strategy_type(AlgoStrategyType.SECURITY)
        self.trigger_symbols()
        self.global_variables()
        self.custom_indicator()
        log_info('mom_12_1_raw 策略初始化完成：持仓 %s 只，每 %s 个交易日调仓'
                 % (self.top_n, self.rebalance_days))

    # ------------------------------------------------------------------
    # 辅助：拿到有效的驱动标的
    # ------------------------------------------------------------------
    def _active_stocks(self):
        out = []
        for s in self.stocks:
            if s is None:
                continue
            code = getattr(s, 'code', None)
            if code:
                out.append(s)
        return out

    def _code(self, stock):
        return getattr(stock, 'code', str(stock))

    # ------------------------------------------------------------------
    # 核心：12-1 动量
    # ------------------------------------------------------------------
    def _momentum(self, stock):
        """返回 (t-21)/(t-252)-1；数据不足或取数失败返回 None。

        这是整个策略唯一真正重要的计算。不做波动率缩放，不做额外平滑。
        """
        try:
            px_recent = bar_close(stock, BarType.D1, self.skip + _SELECT_BASE)
            px_year = bar_close(stock, BarType.D1, self.lookback + _SELECT_BASE)
        except BaseException as e:
            log_warn('取数失败 %s: %s' % (self._code(stock), e))
            return None
        if px_year is None or px_recent is None or px_year <= 0:
            return None
        return float(px_recent) / float(px_year) - 1.0

    # ------------------------------------------------------------------
    # 辅助：止损价
    # ------------------------------------------------------------------
    def _stop_price(self, stock, entry_price):
        """按 2 倍 ATR 计算止损价。ATR 取不到就退回 8% 固定止损。"""
        try:
            atr = atr_atr(stock, self.atr_period, BarType.D1, _SELECT_BASE, THType.ALL)
            if atr and float(atr) > 0:
                return float(entry_price) - self.atr_stop_mult * float(atr)
        except BaseException as e:
            log_warn('ATR 失败 %s: %s' % (self._code(stock), e))
        return float(entry_price) * 0.92

    # ------------------------------------------------------------------
    # 辅助：清仓
    # ------------------------------------------------------------------
    def _liquidate(self, stock):
        code = self._code(stock)
        try:
            qty = position_holding_qty(stock)
        except BaseException as e:
            log_warn('查询持仓失败 %s: %s' % (code, e))
            return
        if not qty or qty <= 0:
            return
        try:
            cancel_order_by_symbol(stock)          # 先撤掉挂着的老止损单
        except BaseException:
            pass
        try:
            close_positions(stock)
            log_info('已清仓 %s，数量 %s' % (code, qty))
        except BaseException as e:
            log_warn('清仓失败 %s: %s' % (code, e))

    # ------------------------------------------------------------------
    # 辅助：建仓
    # ------------------------------------------------------------------
    def _enter(self, stock, budget):
        """用给定预算市价买入，并挂上 ATR 止损单。"""
        code = self._code(stock)
        try:
            # 注意：current_price 的第二个参数是行情时段 THType，不是价格类型
            px = current_price(stock, THType.ALL)
        except BaseException:
            px = None
        if not px or float(px) <= 0:
            log_warn('拿不到现价，跳过 %s' % code)
            return
        px = float(px)

        # 按 1 手（美股通常 1 股）计算数量
        try:
            lot = lot_size(stock) or 1
        except BaseException:
            lot = 1
        qty = int(budget / px)
        qty = (qty // int(lot)) * int(lot)
        if qty <= 0:
            log_info('预算 %.0f 不够买 1 手 %s（现价 %.2f），跳过' % (budget, code, px))
            return

        # 用最大可买量做上限，避免废单
        try:
            max_qty = max_qty_to_buy_on_cash(stock, OrdType.MKT, px, TSType.ALL)
            if max_qty is not None and float(max_qty) > 0:
                qty = min(qty, int(float(max_qty)))
        except BaseException:
            pass
        if qty <= 0:
            return

        try:
            place_market(stock, qty, OrderSide.BUY, TimeInForce.DAY)
            log_info('买入 %s 数量 %s 现价 %.2f' % (code, qty, px))
        except BaseException as e:
            log_warn('买入失败 %s: %s' % (code, e))
            return

        # 挂 ATR 止损（这是"大神们"真正的护城河所在：不是选股，是止损）
        stop = self._stop_price(stock, px)
        if stop and stop > 0:
            try:
                place_stop(stock, round(stop, 2), qty, OrderSide.SELL, TimeInForce.GTC)
                log_info('已挂止损 %s @ %.2f' % (code, round(stop, 2)))
            except BaseException as e:
                log_warn('挂止损失败 %s: %s' % (code, e))

    # ------------------------------------------------------------------
    # 调仓
    # ------------------------------------------------------------------
    def _rebalance(self):
        stocks = self._active_stocks()
        if not stocks:
            log_info('没有驱动标的，跳过调仓')
            return

        # 1) 算动量并排序
        ranked = []
        for s in stocks:
            m = self._momentum(s)
            if m is not None:
                ranked.append((m, s))
        if not ranked:
            log_info('所有标的动量都算不出来（历史不足 253 根？），跳过')
            return
        ranked.sort(key=lambda kv: kv[0], reverse=True)

        target = [s for _, s in ranked[:max(1, int(self.top_n))]]
        target_codes = set(self._code(s) for s in target)

        log_info('动量排名：' + ', '.join(
            '%s %+.1f%%' % (self._code(s), m * 100) for m, s in ranked[:8]))
        log_info('目标持仓：' + ', '.join(sorted(target_codes)))

        # 2) 卖掉不在目标里的
        for s in stocks:
            if self._code(s) not in target_codes:
                self._liquidate(s)

        # 3) 等权买入目标
        try:
            cash = total_cash(Currency.USD)
        except BaseException:
            cash = None
        if cash is None:
            try:
                cash = cash_buying_power(Currency.USD)
            except BaseException:
                cash = None
        if not cash or float(cash) <= 0:
            log_info('拿不到可用资金，跳过买入')
            return

        budget_each = float(cash) / float(len(target))
        cap = None
        try:
            cap = float(total_cash(Currency.USD)) * self.max_weight_pct / 100.0
        except BaseException:
            pass
        if cap and cap > 0:
            budget_each = min(budget_each, cap)

        for s in target:
            if position_holding_qty(s) and position_holding_qty(s) > 0:
                continue                      # 已持有，不动（避免重复下单）
            self._enter(s, budget_each)

    # ------------------------------------------------------------------
    # 4. 主逻辑
    # ------------------------------------------------------------------
    def handle_data(self):
        try:
            self.bar_count = self.bar_count + 1
            due = (self.bar_count - self.last_rebal) >= self.rebalance_days
            if due or self.last_rebal == 0:
                log_info('=== 第 %d 根 K 线，执行调仓 ===' % self.bar_count)
                self._rebalance()
                self.last_rebal = self.bar_count
        except BaseException as e:
            log_warn('handle_data 异常：%s' % e)

    # ------------------------------------------------------------------
    # 5. 回测统计钩子（平台在有回测时调用）
    # ------------------------------------------------------------------
    def handle_statistics(self):
        pass
