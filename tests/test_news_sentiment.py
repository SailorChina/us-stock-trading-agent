"""Test: news sentiment analysis."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from news_sentiment import analyze_sentiment, get_sentiment_summary

def test_positive_sentiment():
    score = analyze_sentiment("英伟达股价大涨突破新高")
    assert score > 0.1

def test_negative_sentiment():
    score = analyze_sentiment("公司亏损暴跌跌破支撑位")
    assert score < -0.1

def test_neutral_sentiment():
    score = analyze_sentiment("公司公告发布财报数据")
    assert -0.1 <= score <= 0.1

def test_sentiment_summary():
    sentiments = [0.5, 0.3, -0.2, 0.0, 0.1]
    summary = get_sentiment_summary(sentiments)
    assert summary["total_news"] == 5
    assert summary["positive"] >= 0
    assert summary["negative"] >= 0
    assert summary["neutral"] >= 0
