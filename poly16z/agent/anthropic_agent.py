"""
Anthropic Agent

AI-powered trading agent using Claude for decision-making.
"""

import json
from typing import Optional
from anthropic import Anthropic
from loguru import logger

from poly16z.agent.base import BaseAgent, Observation, Decision
from poly16z.api.client import PolymarketClient
from poly16z.risk.manager import RiskManager


class AnthropicAgent(BaseAgent):
    """
    AI-powered trading agent using Claude.

    This agent uses natural language prompts to define trading strategies.
    Users can specify their strategy in plain English, and Claude will
    analyze market data and make trading decisions accordingly.

    Example:
        strategy_prompt = '''
        You are a momentum trader. Look for markets where:
        1. Price has moved >10% in the last hour
        2. Volume is above average
        3. The market has good liquidity

        When you find such markets, take a position in the direction
        of the momentum. Use 5% of available capital per trade.
        '''

        agent = AnthropicAgent(
            client=polymarket_client,
            risk_manager=risk_manager,
            anthropic_api_key="sk-...",
            strategy_prompt=strategy_prompt
        )
        await agent.run()
    """

    def __init__(
        self,
        client: PolymarketClient,
        risk_manager: RiskManager,
        anthropic_api_key: str,
        strategy_prompt: str,
        model: str = "claude-sonnet-4-5-20250929",
        name: str = "AnthropicAgent",
        loop_interval: int = 60,
        temperature: float = 1.0,
    ):
        """
        Initialize Anthropic agent.

        Args:
            client: Polymarket API client
            risk_manager: Risk management system
            anthropic_api_key: Anthropic API key
            strategy_prompt: Natural language strategy description
            model: Claude model to use
            name: Agent name
            loop_interval: Seconds between loop iterations
            temperature: Sampling temperature for Claude
        """
        super().__init__(client, risk_manager, name, loop_interval)

        self.anthropic = Anthropic(api_key=anthropic_api_key)
        self.strategy_prompt = strategy_prompt
        self.model = model
        self.temperature = temperature

        logger.info(f"AnthropicAgent '{name}' initialized with model {model}")

    def _format_observation(self, observation: Observation) -> str:
        """
        Format observation into a prompt for Claude.

        Args:
            observation: Market observation

        Returns:
            Formatted prompt string
        """
        # Format markets
        markets_info = []
        for market in observation.markets[:20]:  # Limit to top 20 markets
            markets_info.append(
                f"Market: {market.question}\n"
                f"  ID: {market.condition_id}\n"
                f"  Outcomes: {', '.join(market.outcomes)}\n"
                f"  Prices: {', '.join(f'{p:.2%}' for p in market.outcome_prices)}\n"
                f"  Volume: ${market.volume:,.0f}\n"
                f"  Liquidity: ${market.liquidity:,.0f}\n"
                f"  End Date: {market.end_date.strftime('%Y-%m-%d %H:%M')}\n"
            )

        # Format positions
        positions_info = []
        for pos in observation.positions:
            positions_info.append(
                f"Position in {pos.market_id}:\n"
                f"  Outcome: {pos.outcome}\n"
                f"  Size: {pos.size:.2f} shares\n"
                f"  Avg Price: {pos.avg_price:.2%}\n"
                f"  Current Price: {pos.current_price:.2%}\n"
                f"  Unrealized P&L: ${pos.unrealized_pnl:.2f}\n"
            )

        # Build prompt
        prompt = f"""Current Market State:

Time: {observation.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
Account Balance: ${observation.balance:,.2f}

Active Positions ({len(observation.positions)}):
{chr(10).join(positions_info) if positions_info else "No open positions"}

Top Markets ({len(markets_info)}):
{chr(10).join(markets_info)}

Recent Trading History:
{self.memory.get_recent_history(5)}

Based on the above information and your trading strategy, what should you do next?
"""
        return prompt

    def _parse_decision(self, response: str, observation: Observation) -> Decision:
        """
        Parse Claude's response into a Decision object.

        Args:
            response: Claude's response text
            observation: Original observation

        Returns:
            Decision object
        """
        try:
            # Try to parse as JSON first
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                json_str = response[json_start:json_end].strip()
                data = json.loads(json_str)
            elif response.strip().startswith("{"):
                data = json.loads(response)
            else:
                # Parse from natural language response
                response_lower = response.lower()

                # Determine action
                if any(word in response_lower for word in ["buy", "long", "purchase"]):
                    action = "buy"
                elif any(word in response_lower for word in ["sell", "short", "close"]):
                    action = "sell"
                else:
                    action = "hold"

                data = {
                    "action": action,
                    "reasoning": response,
                }

            # Create decision
            decision = Decision(
                action=data.get("action", "hold"),
                market_id=data.get("market_id"),
                outcome=data.get("outcome"),
                size=float(data.get("size", 0)),
                price=float(data["price"]) if "price" in data else None,
                reasoning=data.get("reasoning", response),
                confidence=float(data.get("confidence", 0.5)),
            )

            return decision

        except Exception as e:
            logger.error(f"Error parsing decision: {e}")
            # Return safe default
            return Decision(
                action="hold",
                reasoning=f"Error parsing decision: {e}",
            )

    async def decide(self, observation: Observation) -> Decision:
        """
        Use Claude to make a trading decision.

        Args:
            observation: Current market observation

        Returns:
            Decision based on AI analysis
        """
        logger.info(f"[{self.name}] Asking Claude for trading decision...")

        try:
            # Format observation into prompt
            observation_prompt = self._format_observation(observation)

            # Build messages
            messages = [
                {
                    "role": "user",
                    "content": f"""{self.strategy_prompt}

{observation_prompt}

Respond with a JSON object containing your trading decision:
{{
    "action": "buy" | "sell" | "hold",
    "market_id": "condition_id of the market (if buy/sell)",
    "outcome": "outcome to bet on (if buy/sell)",
    "size": number of shares,
    "price": limit price between 0 and 1 (if buy/sell),
    "reasoning": "brief explanation of your decision",
    "confidence": 0.0 to 1.0
}}

If you recommend holding or not trading, just respond with action: "hold" and explain why.
"""
                }
            ]

            # Call Claude
            response = self.anthropic.messages.create(
                model=self.model,
                max_tokens=2048,
                temperature=self.temperature,
                messages=messages,
            )

            # Extract response
            response_text = response.content[0].text
            logger.debug(f"Claude response: {response_text[:200]}...")

            # Parse into decision
            decision = self._parse_decision(response_text, observation)

            logger.info(
                f"[{self.name}] Decision: {decision.action} "
                f"(confidence: {decision.confidence:.0%})"
            )
            logger.info(f"[{self.name}] Reasoning: {decision.reasoning[:200]}...")

            return decision

        except Exception as e:
            logger.error(f"Error getting decision from Claude: {e}")
            # Return safe default
            return Decision(
                action="hold",
                reasoning=f"Error in decision-making: {e}",
            )
