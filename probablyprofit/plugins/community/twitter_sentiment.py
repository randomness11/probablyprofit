"""
Example: Twitter/X Sentiment Data Source Plugin

Shows how to create a data source plugin that fetches social sentiment.
"""
from typing import Dict, Any, List
from datetime import datetime
from loguru import logger

from probablyprofit.plugins import registry, PluginType
from probablyprofit.plugins.base import DataSourcePlugin, PluginConfig


@registry.register(
    "twitter_sentiment",
    PluginType.DATA_SOURCE,
    version="1.0.0",
    author="community",
    description="Fetch Twitter/X sentiment for markets"
)
class TwitterSentimentPlugin(DataSourcePlugin):
    """
    Fetches social sentiment from Twitter/X for prediction market topics.
    
    This is a mock implementation. In production, you'd integrate with:
    - Twitter API v2
    - A sentiment analysis service
    
    Usage:
        from probablyprofit.plugins.community.twitter_sentiment import TwitterSentimentPlugin
        
        plugin = TwitterSentimentPlugin()
        data = await plugin.fetch("Bitcoin price prediction")
    """
    
    def __init__(self, config: PluginConfig = None, bearer_token: str = None):
        super().__init__(config)
        self.bearer_token = bearer_token
        # Mock data for demonstration
        self._mock_sentiments = {
            "bitcoin": {"sentiment": 0.65, "volume": 15000},
            "ethereum": {"sentiment": 0.55, "volume": 8000},
            "trump": {"sentiment": 0.35, "volume": 25000},
            "ai": {"sentiment": 0.80, "volume": 12000},
        }
    
    async def fetch(self, query: str) -> Dict[str, Any]:
        """
        Fetch sentiment for a query.
        
        Returns:
            {
                "query": str,
                "sentiment": float (0-1, 0.5 = neutral),
                "volume": int (tweet count),
                "trending": bool,
                "sample_tweets": list,
                "timestamp": str
            }
        """
        query_lower = query.lower()
        
        # Mock: check if any keyword matches
        sentiment_data = {"sentiment": 0.5, "volume": 100}
        for keyword, data in self._mock_sentiments.items():
            if keyword in query_lower:
                sentiment_data = data
                break
        
        return {
            "query": query,
            "sentiment": sentiment_data["sentiment"],
            "volume": sentiment_data["volume"],
            "trending": sentiment_data["volume"] > 10000,
            "sample_tweets": [
                f"Mock tweet about {query}",
                f"Another tweet mentioning {query}",
            ],
            "timestamp": datetime.now().isoformat(),
        }
    
    async def fetch_batch(self, queries: List[str]) -> List[Dict[str, Any]]:
        """Fetch sentiment for multiple queries."""
        # In production, you'd optimize this with batch API calls
        return [await self.fetch(q) for q in queries]
    
    def get_bullish_topics(self, threshold: float = 0.6) -> List[str]:
        """Get topics with bullish sentiment."""
        return [
            topic for topic, data in self._mock_sentiments.items()
            if data["sentiment"] >= threshold
        ]
