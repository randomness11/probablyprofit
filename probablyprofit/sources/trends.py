"""
Google Trends Data Source

Search interest trends as a leading indicator for prediction markets.
Rising search interest often precedes price movements.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger
from pydantic import BaseModel


class TrendData(BaseModel):
    """Trend data for a keyword."""

    keyword: str
    current_interest: int  # 0-100 scale
    avg_interest: float
    peak_interest: int
    trend_direction: str  # "rising", "falling", "stable"
    percent_change: float  # Change from average
    related_queries: List[str] = []
    timestamp: datetime = datetime.now()

    @property
    def is_trending(self) -> bool:
        """Check if significantly above average."""
        return self.current_interest > self.avg_interest * 1.5

    @property
    def is_spiking(self) -> bool:
        """Check if dramatically above average."""
        return self.current_interest > self.avg_interest * 2.5


class TrendsSentiment(BaseModel):
    """Aggregated trends sentiment for a topic."""

    topic: str
    keywords: List[TrendData] = []
    overall_trend: str = "stable"  # rising, falling, stable, spiking
    interest_score: float = 0.0  # 0-100 normalized
    momentum: float = 0.0  # Rate of change
    timestamp: datetime = datetime.now()

    def format_for_prompt(self) -> str:
        """Format for AI agent consumption."""
        if not self.keywords:
            return f"No Google Trends data for '{self.topic}'"

        lines = [
            f"📈 GOOGLE TRENDS ({self.timestamp.strftime('%Y-%m-%d %H:%M')}):",
            f"Topic: {self.topic}",
            f"Overall Trend: {self.overall_trend.upper()}",
            f"Interest Score: {self.interest_score:.0f}/100",
            f"Momentum: {self.momentum:+.1f}%",
            "",
        ]

        # Individual keywords
        for kw in self.keywords[:5]:
            icon = "🔥" if kw.is_spiking else ("📈" if kw.is_trending else "➖")
            lines.append(
                f"  {icon} '{kw.keyword}': {kw.current_interest}/100 ({kw.percent_change:+.0f}% vs avg)"
            )

        # Related queries
        all_related = []
        for kw in self.keywords:
            all_related.extend(kw.related_queries[:3])

        if all_related:
            lines.append("")
            lines.append(f"Related searches: {', '.join(set(all_related)[:5])}")

        return "\n".join(lines)


class GoogleTrendsClient:
    """
    Google Trends client for search interest analysis.

    Uses unofficial API (no auth required).
    Note: Google may rate limit or block excessive requests.

    Usage:
        client = GoogleTrendsClient()
        trend = await client.get_interest("Bitcoin ETF")
    """

    # Google Trends API endpoints
    TRENDS_BASE = "https://trends.google.com/trends/api"

    def __init__(self, timeout: float = 30.0):
        """Initialize Google Trends client."""
        self.timeout = timeout
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            },
            follow_redirects=True,
        )
        self._last_request = 0.0
        self._min_interval = 1.0

        logger.info("GoogleTrendsClient initialized")

    async def _rate_limit(self):
        """Basic rate limiting."""
        import time

        now = time.time()
        elapsed = now - self._last_request
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)
        self._last_request = time.time()

    async def get_interest(
        self,
        keyword: str,
        timeframe: str = "now 7-d",
        geo: str = "US",
    ) -> TrendData:
        """
        Get search interest for a keyword.

        Args:
            keyword: Search term
            timeframe: Time range (now 1-H, now 4-H, now 1-d, now 7-d, today 1-m, today 3-m)
            geo: Geographic region

        Returns:
            TrendData object
        """
        await self._rate_limit()

        # Build widget token request
        try:
            # First, get the explore page to get widget token
            explore_url = "https://trends.google.com/trends/explore"
            params = {
                "q": keyword,
                "date": timeframe,
                "geo": geo,
            }

            # Get initial page
            response = await self._client.get(explore_url, params=params)

            # For now, use a simpler approach - scrape the interest data
            # This is a simplified version that estimates interest

            # Fallback: Use daily trends API
            trend_data = await self._get_daily_trends(keyword, geo)

            if trend_data:
                return trend_data

            # If API fails, return neutral data
            logger.warning(f"Google Trends API unavailable for '{keyword}', using neutral fallback data")
            return TrendData(
                keyword=keyword,
                current_interest=50,
                avg_interest=50.0,
                peak_interest=50,
                trend_direction="stable",
                percent_change=0.0,
                related_queries=[],
                timestamp=datetime.now(),
            )

        except Exception as e:
            logger.error(f"Google Trends error for '{keyword}': {e}")
            return TrendData(
                keyword=keyword,
                current_interest=50,
                avg_interest=50.0,
                peak_interest=50,
                trend_direction="stable",
                percent_change=0.0,
                timestamp=datetime.now(),
            )

    async def _get_daily_trends(
        self,
        keyword: str,
        geo: str = "US",
    ) -> Optional[TrendData]:
        """Get trend data using daily trends API."""
        try:
            # Use the realtime trends endpoint
            url = "https://trends.google.com/trends/api/realtimetrends"
            params = {
                "hl": "en-US",
                "tz": "-480",
                "cat": "all",
                "fi": "0",
                "fs": "0",
                "geo": geo,
                "ri": "300",
                "rs": "20",
                "sort": "0",
            }

            response = await self._client.get(url, params=params)

            # Google prepends ")]}'" to JSON responses
            text = response.text
            if text.startswith(")]}'"):
                text = text[5:]

            import json

            data = json.loads(text)

            # Search for our keyword in trending stories
            keyword_lower = keyword.lower()
            for story in data.get("storySummaries", {}).get("trendingStories", []):
                title = story.get("title", "").lower()
                if keyword_lower in title:
                    # Found related trend
                    traffic = story.get("entityNames", [])

                    return TrendData(
                        keyword=keyword,
                        current_interest=80,  # If trending, assume high
                        avg_interest=50.0,
                        peak_interest=100,
                        trend_direction="rising",
                        percent_change=60.0,
                        related_queries=traffic[:5],
                        timestamp=datetime.now(),
                    )

            # Keyword not in current trends - estimate based on query
            return None

        except Exception as e:
            logger.debug(f"Daily trends API error: {e}")
            return None

    async def get_trending_now(
        self,
        geo: str = "US",
        category: str = "all",
    ) -> List[str]:
        """
        Get currently trending searches.

        Args:
            geo: Geographic region
            category: Category filter

        Returns:
            List of trending search terms
        """
        await self._rate_limit()

        try:
            url = "https://trends.google.com/trends/api/dailytrends"
            params = {
                "hl": "en-US",
                "tz": "-480",
                "geo": geo,
                "ns": "15",
            }

            response = await self._client.get(url, params=params)

            text = response.text
            if text.startswith(")]}'"):
                text = text[5:]

            import json

            data = json.loads(text)

            trending = []
            for day in data.get("default", {}).get("trendingSearchesDays", []):
                for search in day.get("trendingSearches", []):
                    title = search.get("title", {}).get("query", "")
                    if title:
                        trending.append(title)

            return trending[:20]

        except Exception as e:
            logger.error(f"Error fetching trending searches: {e}")
            return []

    async def get_sentiment(
        self,
        topic: str,
        additional_keywords: Optional[List[str]] = None,
    ) -> TrendsSentiment:
        """
        Get aggregated trends sentiment for a topic.

        Args:
            topic: Main topic
            additional_keywords: Extra keywords to track

        Returns:
            TrendsSentiment object
        """
        logger.info(f"Fetching Google Trends for: {topic}")

        # Extract keywords from topic
        keywords = self._extract_keywords(topic)
        if additional_keywords:
            keywords.extend(additional_keywords)

        # Dedupe
        keywords = list(dict.fromkeys(keywords))[:5]

        # Fetch trend data for each keyword
        trend_data = []
        for kw in keywords:
            data = await self.get_interest(kw)
            trend_data.append(data)

        if not trend_data:
            return TrendsSentiment(
                topic=topic,
                keywords=[],
                overall_trend="stable",
                interest_score=50.0,
                momentum=0.0,
                timestamp=datetime.now(),
            )

        # Calculate overall metrics
        avg_interest = sum(t.current_interest for t in trend_data) / len(trend_data)
        avg_change = sum(t.percent_change for t in trend_data) / len(trend_data)

        # Determine overall trend
        rising_count = sum(1 for t in trend_data if t.trend_direction == "rising")
        falling_count = sum(1 for t in trend_data if t.trend_direction == "falling")
        spiking = any(t.is_spiking for t in trend_data)

        if spiking:
            overall = "spiking"
        elif rising_count > falling_count:
            overall = "rising"
        elif falling_count > rising_count:
            overall = "falling"
        else:
            overall = "stable"

        return TrendsSentiment(
            topic=topic,
            keywords=trend_data,
            overall_trend=overall,
            interest_score=avg_interest,
            momentum=avg_change,
            timestamp=datetime.now(),
        )

    def _extract_keywords(self, topic: str) -> List[str]:
        """Extract searchable keywords from topic."""
        import re

        # Remove common words
        stop_words = {
            "will",
            "the",
            "a",
            "an",
            "in",
            "on",
            "at",
            "by",
            "for",
            "to",
            "of",
            "and",
            "or",
            "be",
            "is",
            "are",
            "was",
            "were",
            "this",
            "that",
            "it",
            "what",
            "when",
            "where",
            "who",
            "how",
            "before",
            "after",
            "than",
            "more",
            "less",
            "any",
            "some",
        }

        # Find words and phrases
        words = re.findall(r"\b\w+\b", topic.lower())
        keywords = [w for w in words if w not in stop_words and len(w) > 2]

        # Also try to find named entities (capitalized words in original)
        named = re.findall(r"\b[A-Z][a-z]+\b", topic)
        keywords = named + keywords

        return keywords[:5]

    async def get_market_sentiment(
        self,
        market_question: str,
    ) -> TrendsSentiment:
        """
        Get trends sentiment for a prediction market question.

        Args:
            market_question: The market question

        Returns:
            TrendsSentiment
        """
        return await self.get_sentiment(market_question)

    async def close(self):
        """Close HTTP client."""
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
