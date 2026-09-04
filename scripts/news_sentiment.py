#!/usr/bin/env python3
"""US Stock News Sentiment Analysis - analyzes news sentiment for stocks"""
import json, sys, argparse, urllib.request, re
from cache_util import retry_call
from datetime import datetime

# Enhanced sentiment lexicons
POSITIVE_WORDS = [
    '涨','升','利好','突破','创新高','走强','反弹','上涨','增长','盈利',
    '超预期','景气','繁荣','机会','潜力','看好','推荐','买入','增持',
    '强','高','利好','牛市','突破','上涨','增长','盈利','机会','潜力',
    'bullish','strong','growth','profit','opportunity','breakthrough',
    'rally','surge','gain','beat','upgrade','positive','buy','outperform',
    'acquire','partnership','launch','deal','investment','collaboration',
    'ai','innovation','technology','future','demand','revenue','margin',
]

NEGATIVE_WORDS = [
    '跌','降','利空','跌破','新低','走弱','下跌','下滑','亏损','萎缩',
    '不及预期','低迷','衰退','风险','压力','看空','卖出','减持','警告',
    'weak','bearish','decline','loss','risk','breakdown','fall',
    'drop','miss','downgrade','sell','negative','underperform','warning',
    'lawsuit','investigation','fraud','scandal','ban','tariff','sanction',
    'delay','cancel','cut','warn','warning','concern','threat','crisis',
]

NEUTRAL_WORDS = [
    '声明','公告','报告','数据','发布','公布','调整','变动','提交','报告',
    'report','statement','announcement','filing','disclosure','update',
]

def analyze_sentiment(text):
    """Analyze sentiment score from -1 to 1"""
    if not text:
        return 0.0
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    text_lower = text.lower()
    pos = sum(1 for w in POSITIVE_WORDS if w in text_lower)
    neg = sum(1 for w in NEGATIVE_WORDS if w in text_lower)
    neu = sum(1 for w in NEUTRAL_WORDS if w in text_lower)
    total = pos + neg + neu
    if total == 0:
        return 0.0
    # Neutral words reduce confidence but don't change direction
    return (pos - neg) / max(total, 1)

def fetch_news(symbol, keyword=None, size=10):
    """Fetch news from Futu API"""
    if not keyword:
        keyword = symbol.replace('US.', '')
    url = f'https://ai-news-search.futunn.com/news_search?keyword={keyword}&size={size}&sort_type=2&lang=zh-CN'
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        data = retry_call(lambda: (lambda: json.loads(urllib.request.urlopen(req, timeout=10)).read()))()
        return data.get('data', [])
    except Exception as e:
        return []

def analyze_news(news_list):
    """Analyze sentiment of news list"""
    results = []
    sentiments = []
    for news in news_list:
        title = news.get('title', '')
        sentiment = analyze_sentiment(title)
        sentiments.append(sentiment)
        label = 'positive' if sentiment > 0.15 else ('negative' if sentiment < -0.15 else 'neutral')
        results.append({
            'title': title,
            'sentiment': round(sentiment, 2),
            'sentiment_label': label,
            'publish_time': news.get('publish_time', ''),
        })
    return results, sentiments

def get_sentiment_summary(sentiments):
    """Get summary statistics"""
    if not sentiments:
        return {'overall': 'neutral', 'positive': 0, 'negative': 0, 'neutral': 0,
                'avg_sentiment': 0.0, 'total_news': 0}
    positive = len([s for s in sentiments if s > 0.15])
    negative = len([s for s in sentiments if s < -0.15])
    neutral = len(sentiments) - positive - negative
    total = len(sentiments)
    avg = sum(sentiments) / total
    if avg > 0.15:
        overall = 'positive'
    elif avg < -0.15:
        overall = 'negative'
    else:
        overall = 'neutral'
    return {
        'overall': overall, 'positive': positive, 'negative': negative,
        'neutral': neutral, 'avg_sentiment': round(avg, 2), 'total_news': total,
        'positive_pct': round(positive/total*100, 1),
        'negative_pct': round(negative/total*100, 1),
    }

def main():
    parser = argparse.ArgumentParser(description='US Stock News Sentiment Analysis')
    parser.add_argument('--symbol', required=True, help='Stock symbol (e.g., US.NVDA)')
    parser.add_argument('--size', type=int, default=10, help='Number of news articles')
    parser.add_argument('--output', default=None)
    args = parser.parse_args()
    
    symbol = args.symbol
    keyword = symbol.replace('US.', '') if symbol.startswith('US.') else symbol
    
    print(f'Fetching {args.size} news articles for {symbol}...')
    news_list = fetch_news(symbol, keyword=keyword, size=args.size)
    
    if not news_list:
        result = {'status': 'error', 'error': 'No news found'}
    else:
        news_analysis, sentiments = analyze_news(news_list)
        summary = get_sentiment_summary(sentiments)
        result = {
            'symbol': symbol, 'keyword': keyword,
            'generated_at': datetime.now().isoformat(),
            'summary': summary, 'news': news_analysis
        }
    
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f'Saved to {args.output}')
    else:
        print(output)

if __name__ == '__main__':
    main()
