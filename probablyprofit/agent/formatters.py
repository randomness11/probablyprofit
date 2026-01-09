"""
Shared formatting utilities for AI agents.

This eliminates duplication across Anthropic, OpenAI, and Gemini agents.
"""

from typing import List
from probablyprofit.agent.base import Observation, AgentMemory
from probablyprofit.api.client import Market, Position


class ObservationFormatter:
    """
    Formats observations for AI agents.

    Consolidates the formatting logic that was duplicated across
    AnthropicAgent, OpenAIAgent, and GeminiAgent.
    """

    @staticmethod
    def format_markets(markets: List[Market], limit: int = 20) -> str:
        """
        Format market data for AI consumption.

        Args:
            markets: List of markets to format
            limit: Maximum number of markets to include

        Returns:
            Formatted string describing markets
        """
        if not markets:
            return "No markets available"

        markets_info = []
        for market in markets[:limit]:
            markets_info.append(
                f"Market: {market.question}\n"
                f"  ID: {market.condition_id}\n"
                f"  Outcomes: {', '.join(market.outcomes)}\n"
                f"  Prices: {', '.join(f'{p:.2%}' for p in market.outcome_prices)}\n"
                f"  Volume: ${market.volume:,.0f}\n"
                f"  Liquidity: ${market.liquidity:,.0f}\n"
                f"  End Date: {market.end_date.strftime('%Y-%m-%d %H:%M')}\n"
            )

        return "\n".join(markets_info)

    @staticmethod
    def format_positions(positions: List[Position]) -> str:
        """
        Format position data for AI consumption.

        Args:
            positions: List of positions to format

        Returns:
            Formatted string describing positions
        """
        if not positions:
            return "No open positions"

        positions_info = []
        for pos in positions:
            positions_info.append(
                f"Position in {pos.market_id}:\n"
                f"  Outcome: {pos.outcome}\n"
                f"  Size: {pos.size:.2f} shares\n"
                f"  Avg Price: {pos.avg_price:.2%}\n"
                f"  Current Price: {pos.current_price:.2%}\n"
                f"  Unrealized P&L: ${pos.unrealized_pnl:+.2f}\n"
            )

        return "\n".join(positions_info)

    @staticmethod
    def format_full_observation(
        observation: Observation,
        memory: AgentMemory,
        include_history: int = 5,
        max_markets: int = 20,
    ) -> str:
        """
        Format complete observation for AI consumption.

        Args:
            observation: Observation to format
            memory: Agent memory for history
            include_history: Number of historical entries to include
            max_markets: Maximum markets to include

        Returns:
            Formatted observation string
        """
        sections = [
            f"""Current Market State:

Time: {observation.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
Account Balance: ${observation.balance:,.2f}

Active Positions ({len(observation.positions)}):
{ObservationFormatter.format_positions(observation.positions)}

Top Markets ({min(len(observation.markets), max_markets)}):
{ObservationFormatter.format_markets(observation.markets, max_markets)}

Recent Trading History:
{memory.get_recent_history(include_history)}"""
        ]
        
        # Add intelligence context if available
        if observation.news_context:
            sections.append(f"\n{observation.news_context}")
        
        if observation.sentiment_summary:
            sections.append(f"\n{observation.sentiment_summary}")
        
        return "\n".join(sections)

    @staticmethod
    def format_concise(observation: Observation, memory: AgentMemory) -> str:
        """
        Format concise observation (for faster/cheaper models).

        Args:
            observation: Observation to format
            memory: Agent memory for history

        Returns:
            Concise formatted observation
        """
        return f"""Timestamp: {observation.timestamp}
Balance: ${observation.balance:,.2f}
Markets: {len(observation.markets)} available
Positions: {len(observation.positions)} open

Recent Activity:
{memory.get_recent_history(3)}
"""


def get_decision_schema() -> str:
    """
    Get the JSON schema for AI decision responses.

    Returns:
        JSON schema as string
    """
    return """{
    "action": "buy" | "sell" | "hold",
    "market_id": "string (condition_id of the market if buy/sell)",
    "outcome": "string (outcome to bet on if buy/sell)",
    "size": float (number of shares),
    "price": float (limit price between 0 and 1 if buy/sell)",
    "reasoning": "string (brief explanation of decision)",
    "confidence": float (0.0 to 1.0)
}"""
