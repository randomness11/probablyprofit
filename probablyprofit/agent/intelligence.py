"""
Intelligence-Enhanced Agent

Wraps any base agent with news and sentiment intelligence.
"""

import os
from typing import Any, List, Optional
from loguru import logger

from probablyprofit.agent.base import BaseAgent, Observation
from probablyprofit.api.client import PolymarketClient, Market
from probablyprofit.risk.manager import RiskManager


class IntelligenceAgent(BaseAgent):
    """
    Wraps any trading agent with real-time news and sentiment intelligence.
    
    This agent enhances observations with:
    - News context from Perplexity API
    - Sentiment analysis
    - Market-specific intelligence
    
    Example:
        base_agent = OpenAIAgent(...)
        intel_agent = IntelligenceAgent(
            wrapped_agent=base_agent,
            perplexity_api_key="pplx-...",
            top_n_markets=3,
        )
        await intel_agent.run()
    """
    
    def __init__(
        self,
        wrapped_agent: BaseAgent,
        perplexity_api_key: Optional[str] = None,
        top_n_markets: int = 3,
        enable_sentiment: bool = True,
    ):
        """
        Initialize intelligence wrapper.
        
        Args:
            wrapped_agent: The base agent to wrap
            perplexity_api_key: Perplexity API key for news
            top_n_markets: Number of top markets to fetch news for
            enable_sentiment: Whether to calculate sentiment
        """
        # Inherit settings from wrapped agent
        super().__init__(
            client=wrapped_agent.client,
            risk_manager=wrapped_agent.risk_manager,
            name=f"Intel-{wrapped_agent.name}",
            loop_interval=wrapped_agent.loop_interval,
            strategy=wrapped_agent.strategy,
            dry_run=wrapped_agent.dry_run,
        )
        
        self.wrapped_agent = wrapped_agent
        self.top_n_markets = top_n_markets
        self.enable_sentiment = enable_sentiment
        
        # Initialize Perplexity client if key provided
        self.perplexity = None
        if perplexity_api_key:
            try:
                from probablyprofit.sources.perplexity import PerplexityClient
                self.perplexity = PerplexityClient(api_key=perplexity_api_key)
                logger.info("📰 News intelligence enabled via Perplexity")
            except ImportError:
                logger.warning("Perplexity client not available")
        
        # Initialize sentiment analyzer
        self.sentiment_analyzer = None
        if enable_sentiment:
            try:
                from probablyprofit.sources.sentiment import SentimentAnalyzer
                self.sentiment_analyzer = SentimentAnalyzer()
                logger.info("📊 Sentiment analysis enabled")
            except ImportError:
                logger.warning("Sentiment analyzer not available")
    
    def _get_top_markets(self, markets: List[Market], n: int) -> List[Market]:
        """Get top N markets by volume."""
        sorted_markets = sorted(markets, key=lambda m: m.volume, reverse=True)
        return sorted_markets[:n]
    
    async def _enrich_observation(self, observation: Observation) -> Observation:
        """
        Enrich observation with intelligence data.
        
        Args:
            observation: Base observation
            
        Returns:
            Enhanced observation with news and sentiment
        """
        # Get top markets for news fetching
        top_markets = self._get_top_markets(observation.markets, self.top_n_markets)
        
        news_summaries = []
        sentiment_summaries = []
        market_sentiments = {}
        
        # Fetch news for top markets
        if self.perplexity and top_markets:
            logger.info(f"📰 Fetching news for {len(top_markets)} top markets...")
            
            for market in top_markets:
                try:
                    context = await self.perplexity.get_market_context(market.question)
                    news_summaries.append(context.format_for_prompt())
                    
                    # Calculate sentiment if enabled
                    if self.sentiment_analyzer:
                        sentiment = await self.sentiment_analyzer.analyze(
                            market_id=market.condition_id,
                            market_question=market.question,
                            news_context=context,
                            price_history=market.outcome_prices,  # Limited, but available
                        )
                        sentiment_summaries.append(sentiment.format_for_prompt())
                        market_sentiments[market.condition_id] = sentiment.model_dump()
                        
                except Exception as e:
                    logger.warning(f"Failed to fetch intel for market: {e}")
        
        # Combine into observation
        if news_summaries:
            observation.news_context = "\n\n---\n\n".join(news_summaries)
        
        if sentiment_summaries:
            observation.sentiment_summary = "\n".join(sentiment_summaries)
        
        if market_sentiments:
            observation.market_sentiments = market_sentiments
        
        return observation
    
    async def observe(self) -> Observation:
        """
        Observe with intelligence enrichment.
        """
        # Get base observation
        observation = await super().observe()
        
        # Enrich with intelligence
        observation = await self._enrich_observation(observation)
        
        return observation
    
    async def decide(self, observation: Observation):
        """
        Delegate decision to wrapped agent with enriched observation.
        """
        return await self.wrapped_agent.decide(observation)


def wrap_with_intelligence(
    agent: BaseAgent,
    enable_news: bool = True,
    top_n_markets: int = 3,
) -> BaseAgent:
    """
    Convenience function to wrap an agent with intelligence.
    
    Args:
        agent: Agent to wrap
        enable_news: Whether to enable news fetching
        top_n_markets: Markets to fetch news for
        
    Returns:
        Intelligence-wrapped agent (or original if no API key)
    """
    perplexity_key = os.getenv("PERPLEXITY_API_KEY")
    
    if not perplexity_key and enable_news:
        logger.warning("PERPLEXITY_API_KEY not set - news intelligence disabled")
        return agent
    
    return IntelligenceAgent(
        wrapped_agent=agent,
        perplexity_api_key=perplexity_key,
        top_n_markets=top_n_markets,
        enable_sentiment=True,
    )
