"""
Perplexity API Client

Real-time news search and summarization for market context.
Uses Perplexity's Sonar API for fast, accurate web research.
"""

import asyncio
from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel
import httpx
from loguru import logger


class NewsItem(BaseModel):
    """A single news item."""
    title: str
    source: str
    summary: str
    url: Optional[str] = None
    published_at: Optional[datetime] = None
    relevance_score: float = 0.5


class NewsContext(BaseModel):
    """Aggregated news context for a market."""
    market_question: str
    summary: str
    news_items: List[NewsItem] = []
    sentiment: str = "neutral"  # bullish, bearish, neutral
    confidence: float = 0.5
    timestamp: datetime = datetime.now()
    raw_response: Optional[str] = None
    
    def format_for_prompt(self) -> str:
        """Format news context for AI agent prompt."""
        if not self.summary:
            return "No recent news available."
        
        lines = [
            f"📰 NEWS CONTEXT (as of {self.timestamp.strftime('%Y-%m-%d %H:%M')}):",
            f"Sentiment: {self.sentiment.upper()} (confidence: {self.confidence:.0%})",
            f"",
            f"Summary: {self.summary}",
        ]
        
        if self.news_items:
            lines.append("")
            lines.append("Key Sources:")
            for i, item in enumerate(self.news_items[:3], 1):
                lines.append(f"  [{i}] {item.source}: {item.title}")
        
        return "\n".join(lines)


class PerplexityClient:
    """
    Client for Perplexity Sonar API.
    
    Provides real-time news and web research for market intelligence.
    
    Example:
        client = PerplexityClient(api_key="pplx-...")
        context = await client.get_market_context(
            "Will Bitcoin reach $100k by March 2025?"
        )
        print(context.summary)
    """
    
    BASE_URL = "https://api.perplexity.ai"
    
    def __init__(
        self,
        api_key: str,
        model: str = "sonar",
        timeout: float = 30.0,
    ):
        """
        Initialize Perplexity client.
        
        Args:
            api_key: Perplexity API key (starts with pplx-)
            model: Model to use (sonar, sonar-pro)
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
        )
        logger.info(f"PerplexityClient initialized with model: {model}")
    
    async def search(self, query: str, max_tokens: int = 1024) -> Dict[str, Any]:
        """
        Perform a search query.
        
        Args:
            query: Search query
            max_tokens: Max response tokens
            
        Returns:
            Raw API response
        """
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a financial news analyst. Provide concise, factual summaries "
                        "of recent news and developments. Focus on information that would be "
                        "relevant for predicting market outcomes. Always cite your sources."
                    )
                },
                {
                    "role": "user", 
                    "content": query
                }
            ],
            "max_tokens": max_tokens,
            "temperature": 0.2,
            "return_citations": True,
        }
        
        try:
            response = await self._client.post("/chat/completions", json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Perplexity API error: {e}")
            raise
    
    async def get_market_context(
        self,
        market_question: str,
        additional_context: str = "",
    ) -> NewsContext:
        """
        Get news context for a specific market question.
        
        Args:
            market_question: The Polymarket question
            additional_context: Optional additional context
            
        Returns:
            NewsContext with summary and sentiment
        """
        logger.info(f"Fetching news context for: {market_question[:50]}...")
        
        query = f"""
What are the latest news and developments related to this prediction market question:

"{market_question}"

{additional_context}

Provide:
1. A brief summary of recent relevant news (last 7 days if available)
2. Key factors that could influence the outcome
3. Your assessment: is current evidence BULLISH (likely YES), BEARISH (likely NO), or NEUTRAL?
4. Confidence level (low/medium/high)

Be concise and focus on facts, not speculation.
"""
        
        try:
            response = await self.search(query)
            
            # Extract content
            content = ""
            citations = []
            
            if "choices" in response and len(response["choices"]) > 0:
                message = response["choices"][0].get("message", {})
                content = message.get("content", "")
            
            if "citations" in response:
                citations = response.get("citations", [])
            
            # Parse sentiment from response
            sentiment = "neutral"
            confidence = 0.5
            
            content_lower = content.lower()
            if "bullish" in content_lower or "likely yes" in content_lower:
                sentiment = "bullish"
                confidence = 0.7
            elif "bearish" in content_lower or "likely no" in content_lower:
                sentiment = "bearish"
                confidence = 0.7
            
            if "high confidence" in content_lower:
                confidence = 0.85
            elif "low confidence" in content_lower:
                confidence = 0.4
            
            # Build news items from citations
            news_items = []
            for i, citation in enumerate(citations[:5]):
                if isinstance(citation, str):
                    news_items.append(NewsItem(
                        title=f"Source {i+1}",
                        source=citation,
                        summary="",
                        url=citation if citation.startswith("http") else None,
                    ))
                elif isinstance(citation, dict):
                    news_items.append(NewsItem(
                        title=citation.get("title", f"Source {i+1}"),
                        source=citation.get("source", "Unknown"),
                        summary=citation.get("snippet", ""),
                        url=citation.get("url"),
                    ))
            
            return NewsContext(
                market_question=market_question,
                summary=content,
                news_items=news_items,
                sentiment=sentiment,
                confidence=confidence,
                timestamp=datetime.now(),
                raw_response=content,
            )
            
        except Exception as e:
            logger.error(f"Error fetching market context: {e}")
            return NewsContext(
                market_question=market_question,
                summary=f"Failed to fetch news: {e}",
                sentiment="neutral",
                confidence=0.0,
                timestamp=datetime.now(),
            )
    
    async def get_batch_context(
        self,
        market_questions: List[str],
        max_concurrent: int = 3,
    ) -> Dict[str, NewsContext]:
        """
        Get context for multiple markets efficiently.
        
        Args:
            market_questions: List of market questions
            max_concurrent: Max concurrent requests
            
        Returns:
            Dict mapping question to context
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def fetch_with_limit(question: str) -> tuple:
            async with semaphore:
                context = await self.get_market_context(question)
                return (question, context)
        
        tasks = [fetch_with_limit(q) for q in market_questions]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        context_map = {}
        for result in results:
            if isinstance(result, tuple):
                question, context = result
                context_map[question] = context
            elif isinstance(result, Exception):
                logger.error(f"Batch context error: {result}")
        
        return context_map
    
    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, *args):
        await self.close()
