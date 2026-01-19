"""
Reddit Data Source

Community sentiment and discussion analysis from Reddit.
Scrapes relevant subreddits for prediction market alpha.
"""

import asyncio
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger
from pydantic import BaseModel


class RedditPost(BaseModel):
    """A Reddit post or comment."""

    id: str
    title: str
    text: str
    author: str
    subreddit: str
    score: int = 0
    num_comments: int = 0
    created_at: datetime
    url: Optional[str] = None
    is_comment: bool = False

    @property
    def engagement(self) -> int:
        """Total engagement."""
        return self.score + self.num_comments * 2


class RedditSentiment(BaseModel):
    """Aggregated Reddit sentiment for a topic."""

    topic: str
    posts: List[RedditPost] = []
    sentiment_score: float = 0.0  # -1 to +1
    volume: int = 0
    top_subreddits: List[str] = []
    hot_discussions: List[str] = []
    timestamp: datetime = datetime.now()

    @property
    def sentiment_label(self) -> str:
        if self.sentiment_score > 0.2:
            return "bullish"
        elif self.sentiment_score < -0.2:
            return "bearish"
        return "neutral"

    def format_for_prompt(self) -> str:
        """Format for AI agent consumption."""
        if not self.posts:
            return f"No recent Reddit activity for '{self.topic}'"

        lines = [
            f"🔴 REDDIT SENTIMENT ({self.timestamp.strftime('%Y-%m-%d %H:%M')}):",
            f"Topic: {self.topic}",
            f"Sentiment: {self.sentiment_label.upper()} (score: {self.sentiment_score:+.2f})",
            f"Volume: {self.volume} posts/comments analyzed",
            "",
        ]

        if self.top_subreddits:
            lines.append(f"Active subreddits: {', '.join(self.top_subreddits[:5])}")

        # Top posts by engagement
        top_posts = sorted(
            [p for p in self.posts if not p.is_comment], key=lambda p: p.engagement, reverse=True
        )[:3]

        if top_posts:
            lines.append("")
            lines.append("Hot discussions:")
            for i, post in enumerate(top_posts, 1):
                title = post.title[:80] + "..." if len(post.title) > 80 else post.title
                lines.append(f"  [{i}] r/{post.subreddit}: {title} ({post.score} pts)")

        return "\n".join(lines)


# Sentiment keywords
BULLISH_KEYWORDS = [
    "bullish",
    "moon",
    "buy",
    "long",
    "calls",
    "up",
    "rally",
    "winning",
    "confirmed",
    "happening",
    "yes",
    "will win",
    "undervalued",
    "cheap",
    "opportunity",
    "lfg",
    "wagmi",
    "breakout",
    "pump",
    "rocket",
    "soar",
    "surge",
]

BEARISH_KEYWORDS = [
    "bearish",
    "dump",
    "sell",
    "short",
    "puts",
    "down",
    "crash",
    "losing",
    "denied",
    "not happening",
    "no",
    "will lose",
    "overvalued",
    "expensive",
    "trap",
    "ngmi",
    "rekt",
    "breakdown",
    "tank",
    "plunge",
    "collapse",
    "fail",
]


def analyze_sentiment(text: str) -> float:
    """Basic sentiment analysis. Returns -1 to +1."""
    text_lower = text.lower()

    bullish = sum(1 for kw in BULLISH_KEYWORDS if kw in text_lower)
    bearish = sum(1 for kw in BEARISH_KEYWORDS if kw in text_lower)

    total = bullish + bearish
    if total == 0:
        return 0.0

    return (bullish - bearish) / total


# Subreddits relevant to prediction markets
DEFAULT_SUBREDDITS = [
    # Crypto & Finance
    "cryptocurrency",
    "bitcoin",
    "ethereum",
    "wallstreetbets",
    "stocks",
    "investing",
    "economics",
    "finance",
    # Politics
    "politics",
    "news",
    "worldnews",
    "conservative",
    "liberal",
    # Sports
    "sports",
    "nfl",
    "nba",
    "soccer",
    # Prediction markets
    "polymarket",
    "predictit",
    # General
    "technology",
    "science",
    "futurology",
]


class RedditClient:
    """
    Reddit client for community sentiment analysis.

    Uses Reddit's public JSON API (no auth required for read).
    Rate limited to be respectful.

    Usage:
        client = RedditClient()
        sentiment = await client.get_sentiment("Bitcoin ETF", subreddits=["cryptocurrency"])
    """

    BASE_URL = "https://www.reddit.com"
    OLD_BASE_URL = "https://old.reddit.com"

    def __init__(
        self,
        timeout: float = 30.0,
        user_agent: str = "probablyprofit/1.0",
    ):
        """
        Initialize Reddit client.

        Args:
            timeout: Request timeout
            user_agent: User agent string
        """
        self.timeout = timeout
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": user_agent},
            follow_redirects=True,
        )
        self._last_request = 0.0
        self._min_interval = 2.0  # Seconds between requests (rate limit)

        logger.info("RedditClient initialized")

    async def _rate_limit(self):
        """Respect Reddit rate limits."""
        import time

        now = time.time()
        elapsed = now - self._last_request
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)
        self._last_request = time.time()

    async def search_subreddit(
        self,
        subreddit: str,
        query: str,
        limit: int = 25,
        sort: str = "relevance",
        time_filter: str = "week",
    ) -> List[RedditPost]:
        """
        Search within a subreddit.

        Args:
            subreddit: Subreddit name (without r/)
            query: Search query
            limit: Max results
            sort: Sort order (relevance, hot, top, new)
            time_filter: Time filter (hour, day, week, month, year, all)

        Returns:
            List of RedditPost
        """
        await self._rate_limit()

        try:
            url = f"{self.BASE_URL}/r/{subreddit}/search.json"
            params = {
                "q": query,
                "restrict_sr": "on",
                "limit": limit,
                "sort": sort,
                "t": time_filter,
            }

            response = await self._client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            posts = []
            for child in data.get("data", {}).get("children", []):
                post_data = child.get("data", {})
                posts.append(
                    RedditPost(
                        id=post_data.get("id", ""),
                        title=post_data.get("title", ""),
                        text=post_data.get("selftext", ""),
                        author=post_data.get("author", "[deleted]"),
                        subreddit=post_data.get("subreddit", subreddit),
                        score=post_data.get("score", 0),
                        num_comments=post_data.get("num_comments", 0),
                        created_at=datetime.fromtimestamp(post_data.get("created_utc", 0)),
                        url=f"https://reddit.com{post_data.get('permalink', '')}",
                        is_comment=False,
                    )
                )

            logger.debug(f"r/{subreddit} search returned {len(posts)} posts for '{query}'")
            return posts

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning(f"Reddit rate limited on r/{subreddit}")
            else:
                logger.error(f"Reddit API error: {e}")
            return []
        except Exception as e:
            logger.error(f"Reddit error for r/{subreddit}: {e}")
            return []

    async def get_hot_posts(
        self,
        subreddit: str,
        limit: int = 25,
    ) -> List[RedditPost]:
        """Get hot posts from a subreddit."""
        await self._rate_limit()

        try:
            url = f"{self.BASE_URL}/r/{subreddit}/hot.json"
            params = {"limit": limit}

            response = await self._client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            posts = []
            for child in data.get("data", {}).get("children", []):
                post_data = child.get("data", {})
                # Skip stickied posts
                if post_data.get("stickied", False):
                    continue

                posts.append(
                    RedditPost(
                        id=post_data.get("id", ""),
                        title=post_data.get("title", ""),
                        text=post_data.get("selftext", ""),
                        author=post_data.get("author", "[deleted]"),
                        subreddit=post_data.get("subreddit", subreddit),
                        score=post_data.get("score", 0),
                        num_comments=post_data.get("num_comments", 0),
                        created_at=datetime.fromtimestamp(post_data.get("created_utc", 0)),
                        url=f"https://reddit.com{post_data.get('permalink', '')}",
                        is_comment=False,
                    )
                )

            return posts

        except Exception as e:
            logger.error(f"Error fetching hot posts from r/{subreddit}: {e}")
            return []

    async def search_all(
        self,
        query: str,
        subreddits: Optional[List[str]] = None,
        limit_per_sub: int = 10,
    ) -> List[RedditPost]:
        """
        Search across multiple subreddits.

        Args:
            query: Search query
            subreddits: List of subreddits (uses defaults if None)
            limit_per_sub: Max results per subreddit

        Returns:
            Combined list of posts
        """
        if subreddits is None:
            # Auto-select relevant subreddits based on query
            subreddits = self._select_subreddits(query)

        all_posts = []

        for subreddit in subreddits[:5]:  # Limit to 5 subreddits
            posts = await self.search_subreddit(
                subreddit=subreddit,
                query=query,
                limit=limit_per_sub,
            )
            all_posts.extend(posts)

        return all_posts

    def _select_subreddits(self, query: str) -> List[str]:
        """Auto-select relevant subreddits based on query."""
        query_lower = query.lower()

        subreddits = []

        # Crypto keywords
        if any(kw in query_lower for kw in ["bitcoin", "btc", "crypto", "ethereum", "eth"]):
            subreddits.extend(["cryptocurrency", "bitcoin", "ethereum", "cryptomarkets"])

        # Politics keywords
        if any(
            kw in query_lower
            for kw in ["trump", "biden", "election", "congress", "senate", "president"]
        ):
            subreddits.extend(["politics", "news", "conservative", "liberal"])

        # Sports keywords
        if any(
            kw in query_lower for kw in ["nfl", "nba", "super bowl", "championship", "playoffs"]
        ):
            subreddits.extend(["sports", "nfl", "nba", "sportsbook"])

        # Finance keywords
        if any(
            kw in query_lower for kw in ["stock", "market", "fed", "interest rate", "inflation"]
        ):
            subreddits.extend(["wallstreetbets", "stocks", "investing", "economics"])

        # Tech keywords
        if any(kw in query_lower for kw in ["ai", "tech", "apple", "google", "microsoft"]):
            subreddits.extend(["technology", "artificial", "stocks"])

        # Prediction market subreddits
        subreddits.extend(["polymarket", "predictit"])

        # Dedupe while preserving order
        seen = set()
        unique = []
        for s in subreddits:
            if s not in seen:
                seen.add(s)
                unique.append(s)

        return unique if unique else ["news", "worldnews"]

    async def get_sentiment(
        self,
        topic: str,
        subreddits: Optional[List[str]] = None,
        max_posts: int = 50,
    ) -> RedditSentiment:
        """
        Get aggregated sentiment for a topic.

        Args:
            topic: Topic to analyze
            subreddits: Subreddits to search (auto-selects if None)
            max_posts: Max posts to analyze

        Returns:
            RedditSentiment object
        """
        logger.info(f"Fetching Reddit sentiment for: {topic}")

        posts = await self.search_all(
            query=topic,
            subreddits=subreddits,
            limit_per_sub=max_posts // 5,
        )

        if not posts:
            return RedditSentiment(
                topic=topic,
                posts=[],
                sentiment_score=0.0,
                volume=0,
                timestamp=datetime.now(),
            )

        # Analyze sentiment
        sentiment_scores = []
        subreddit_counts = {}

        for post in posts:
            # Combine title and text for analysis
            full_text = f"{post.title} {post.text}"
            score = analyze_sentiment(full_text)

            # Weight by engagement (log scale)
            import math

            weight = 1 + math.log10(max(post.engagement, 1) + 1)
            sentiment_scores.append(score * weight)

            # Track subreddit activity
            sub = post.subreddit
            subreddit_counts[sub] = subreddit_counts.get(sub, 0) + 1

        # Aggregate
        avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0.0
        avg_sentiment = max(-1.0, min(1.0, avg_sentiment))

        # Top subreddits
        top_subs = sorted(subreddit_counts.keys(), key=lambda s: subreddit_counts[s], reverse=True)

        return RedditSentiment(
            topic=topic,
            posts=posts,
            sentiment_score=avg_sentiment,
            volume=len(posts),
            top_subreddits=top_subs[:5],
            timestamp=datetime.now(),
        )

    async def get_market_sentiment(
        self,
        market_question: str,
    ) -> RedditSentiment:
        """
        Get Reddit sentiment for a prediction market question.

        Args:
            market_question: The market question

        Returns:
            RedditSentiment
        """
        # Extract key terms
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
        }
        words = re.findall(r"\b\w+\b", market_question.lower())
        keywords = [w for w in words if w not in stop_words and len(w) > 2]

        query = " ".join(keywords[:5])
        return await self.get_sentiment(query)

    async def close(self):
        """Close HTTP client."""
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
