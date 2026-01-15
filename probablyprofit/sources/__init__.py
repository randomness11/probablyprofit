"""Data sources for market intelligence."""

from probablyprofit.sources.aggregator import AlphaSignal, SignalAggregator, create_aggregator
from probablyprofit.sources.perplexity import NewsContext, PerplexityClient
from probablyprofit.sources.reddit import RedditClient, RedditPost, RedditSentiment
from probablyprofit.sources.sentiment import MarketSentiment, SentimentAnalyzer
from probablyprofit.sources.trends import GoogleTrendsClient, TrendData, TrendsSentiment
from probablyprofit.sources.twitter import Tweet, TwitterClient, TwitterSentiment

__all__ = [
    # Perplexity (news)
    "PerplexityClient",
    "NewsContext",
    # Sentiment
    "SentimentAnalyzer",
    "MarketSentiment",
    # Twitter
    "TwitterClient",
    "TwitterSentiment",
    "Tweet",
    # Reddit
    "RedditClient",
    "RedditSentiment",
    "RedditPost",
    # Google Trends
    "GoogleTrendsClient",
    "TrendsSentiment",
    "TrendData",
    # Aggregator
    "SignalAggregator",
    "AlphaSignal",
    "create_aggregator",
]
