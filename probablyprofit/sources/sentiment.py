"""
Sentiment Analyzer

Aggregates sentiment signals from multiple sources.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel
from loguru import logger


class SentimentLevel(str, Enum):
    """Sentiment levels."""
    VERY_BULLISH = "very_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    VERY_BEARISH = "very_bearish"


class MarketSentiment(BaseModel):
    """Aggregated sentiment for a market."""
    market_id: str
    market_question: str
    overall_sentiment: SentimentLevel = SentimentLevel.NEUTRAL
    confidence: float = 0.5
    
    # Component signals
    news_sentiment: Optional[float] = None  # -1 to 1
    social_sentiment: Optional[float] = None  # -1 to 1
    volume_signal: Optional[float] = None  # -1 to 1 (negative = selling pressure)
    price_momentum: Optional[float] = None  # -1 to 1
    
    # Metadata
    sources_count: int = 0
    last_updated: datetime = datetime.now()
    raw_data: Dict[str, Any] = {}
    
    def to_score(self) -> float:
        """Convert sentiment to numeric score (-1 to 1)."""
        mapping = {
            SentimentLevel.VERY_BULLISH: 0.9,
            SentimentLevel.BULLISH: 0.5,
            SentimentLevel.NEUTRAL: 0.0,
            SentimentLevel.BEARISH: -0.5,
            SentimentLevel.VERY_BEARISH: -0.9,
        }
        return mapping.get(self.overall_sentiment, 0.0)
    
    def format_for_prompt(self) -> str:
        """Format sentiment for AI agent prompt."""
        score = self.to_score()
        direction = "📈 BULLISH" if score > 0.2 else ("📉 BEARISH" if score < -0.2 else "➡️ NEUTRAL")
        
        lines = [
            f"📊 SENTIMENT ANALYSIS:",
            f"Overall: {direction} (score: {score:+.2f}, confidence: {self.confidence:.0%})",
        ]
        
        if self.news_sentiment is not None:
            lines.append(f"  News: {self.news_sentiment:+.2f}")
        if self.social_sentiment is not None:
            lines.append(f"  Social: {self.social_sentiment:+.2f}")
        if self.volume_signal is not None:
            lines.append(f"  Volume: {self.volume_signal:+.2f}")
        if self.price_momentum is not None:
            lines.append(f"  Momentum: {self.price_momentum:+.2f}")
        
        return "\n".join(lines)


class SentimentAnalyzer:
    """
    Aggregates sentiment from multiple sources.
    
    Example:
        analyzer = SentimentAnalyzer()
        sentiment = await analyzer.analyze(
            market_id="0x123...",
            market_question="Will Bitcoin hit $100k?",
            news_context=news_context,  # from PerplexityClient
            price_history=[0.45, 0.48, 0.52, 0.55],
            volume_history=[1000, 1200, 1500, 1800],
        )
    """
    
    def __init__(
        self,
        news_weight: float = 0.4,
        social_weight: float = 0.2,
        volume_weight: float = 0.2,
        momentum_weight: float = 0.2,
    ):
        """
        Initialize analyzer with component weights.
        
        Args:
            news_weight: Weight for news sentiment
            social_weight: Weight for social sentiment  
            volume_weight: Weight for volume signals
            momentum_weight: Weight for price momentum
        """
        self.weights = {
            "news": news_weight,
            "social": social_weight,
            "volume": volume_weight,
            "momentum": momentum_weight,
        }
        # Normalize weights
        total = sum(self.weights.values())
        self.weights = {k: v/total for k, v in self.weights.items()}
        
        logger.info(f"SentimentAnalyzer initialized with weights: {self.weights}")
    
    def _calculate_momentum(
        self,
        prices: List[float],
        window: int = 5,
    ) -> float:
        """
        Calculate price momentum signal.
        
        Returns:
            -1 to 1 momentum score
        """
        if len(prices) < 2:
            return 0.0
        
        prices = prices[-window:]
        
        # Simple: compare current to average
        current = prices[-1]
        avg = sum(prices[:-1]) / len(prices[:-1])
        
        if avg == 0:
            return 0.0
        
        change = (current - avg) / avg
        # Clamp to -1, 1
        return max(-1.0, min(1.0, change * 5))  # Scale up small changes
    
    def _calculate_volume_signal(
        self,
        volumes: List[float],
    ) -> float:
        """
        Calculate volume signal.
        
        Increasing volume during price rise = bullish
        Increasing volume during price fall = bearish
        
        Returns:
            -1 to 1 volume signal
        """
        if len(volumes) < 2:
            return 0.0
        
        recent = volumes[-3:] if len(volumes) >= 3 else volumes
        earlier = volumes[:-3] if len(volumes) > 3 else [volumes[0]]
        
        recent_avg = sum(recent) / len(recent)
        earlier_avg = sum(earlier) / len(earlier) if earlier else recent_avg
        
        if earlier_avg == 0:
            return 0.0
        
        # Volume increasing = positive signal (market activity)
        change = (recent_avg - earlier_avg) / earlier_avg
        return max(-1.0, min(1.0, change * 2))
    
    def _news_to_score(self, sentiment: str, confidence: float) -> float:
        """Convert news sentiment to numeric score."""
        base = {
            "bullish": 0.6,
            "bearish": -0.6,
            "neutral": 0.0,
        }.get(sentiment.lower(), 0.0)
        
        return base * confidence
    
    async def analyze(
        self,
        market_id: str,
        market_question: str,
        news_context: Optional[Any] = None,  # NewsContext
        price_history: Optional[List[float]] = None,
        volume_history: Optional[List[float]] = None,
        social_data: Optional[Dict[str, Any]] = None,
    ) -> MarketSentiment:
        """
        Perform sentiment analysis.
        
        Args:
            market_id: Market identifier
            market_question: Market question
            news_context: NewsContext from PerplexityClient
            price_history: Recent price history
            volume_history: Recent volume history
            social_data: Optional social media data
            
        Returns:
            MarketSentiment object
        """
        signals = {}
        sources_count = 0
        
        # News sentiment
        news_score = None
        if news_context is not None:
            news_score = self._news_to_score(
                news_context.sentiment, 
                news_context.confidence
            )
            signals["news"] = news_score
            sources_count += 1
        
        # Price momentum
        momentum_score = None
        if price_history and len(price_history) >= 2:
            momentum_score = self._calculate_momentum(price_history)
            signals["momentum"] = momentum_score
            sources_count += 1
        
        # Volume signal
        volume_score = None
        if volume_history and len(volume_history) >= 2:
            volume_score = self._calculate_volume_signal(volume_history)
            signals["volume"] = volume_score
            sources_count += 1
        
        # Social sentiment (placeholder for future integration)
        social_score = None
        if social_data:
            social_score = social_data.get("sentiment_score", 0.0)
            signals["social"] = social_score
            sources_count += 1
        
        # Calculate weighted average
        weighted_sum = 0.0
        weight_sum = 0.0
        
        for signal_type, score in signals.items():
            if score is not None:
                weight = self.weights.get(signal_type, 0.0)
                weighted_sum += score * weight
                weight_sum += weight
        
        overall_score = weighted_sum / weight_sum if weight_sum > 0 else 0.0
        
        # Convert to sentiment level
        if overall_score >= 0.5:
            level = SentimentLevel.VERY_BULLISH
        elif overall_score >= 0.2:
            level = SentimentLevel.BULLISH
        elif overall_score <= -0.5:
            level = SentimentLevel.VERY_BEARISH
        elif overall_score <= -0.2:
            level = SentimentLevel.BEARISH
        else:
            level = SentimentLevel.NEUTRAL
        
        # Confidence based on number of sources
        confidence = min(1.0, 0.3 + (sources_count * 0.2))
        
        return MarketSentiment(
            market_id=market_id,
            market_question=market_question,
            overall_sentiment=level,
            confidence=confidence,
            news_sentiment=news_score,
            social_sentiment=social_score,
            volume_signal=volume_score,
            price_momentum=momentum_score,
            sources_count=sources_count,
            last_updated=datetime.now(),
            raw_data=signals,
        )
