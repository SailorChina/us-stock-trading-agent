---
name: us-stock-trading-agent
description: >
  美股交易专家 Agent。整合技术分析、资金流向、新闻情感、期权异动、风险管理五大维度，
  为美股提供全面的交易分析与决策支持。
  
  使用场景：
  - 单只股票全面分析（技术面+资金+新闻+期权）
  - 多空信号生成与评级（Buy/Overweight/Hold/Underweight/Sell）
  - 交易计划制定（入场/止损/目标/仓位）
  - 组合/持仓诊断与风险预警
  - 选股与板块扫描
  - 市场情绪与VIX分析
  - 新闻情感分析
  - 盘前/盘后异动监控
  - 宏观经济日历
  - 回测与策略验证
  
  触发关键词：美股分析、股票分析、买卖信号、选股、交易计划、
  技术分析、资金流向、期权异动、情绪分析、持仓诊断、
  止损止盈、仓位管理、板块轮动、美股推荐、NVDA分析、TSLA分析、
  盘前扫描、宏观日历、回测、Risk Manager
metadata:
  version: 2.0.0
  author: agent-builder
  requires:
    - futuapi
    - tech-signal-FUTU-skill
    - futu-capital-anomaly
    - futu-derivatives-anomaly
    - futu-technical-anomaly
    - futu-stock-digest
    - futu-comment-sentiment
    - python >= 3.10
    - futu-api >= 10.4.6408
    - pandas >= 2.0
    - stock_signals (富途牛牛量化)
