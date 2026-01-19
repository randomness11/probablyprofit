"""
Anthropic Agent

AI-powered trading agent using Claude for decision-making.
"""

import json
from typing import AsyncIterator, Callable, Optional

from anthropic import Anthropic
from loguru import logger

from probablyprofit.agent.base import BaseAgent, Decision, Observation
from probablyprofit.agent.formatters import ObservationFormatter, get_decision_schema
from probablyprofit.api.client import PolymarketClient
from probablyprofit.api.exceptions import AgentException, NetworkException, ValidationException
from probablyprofit.risk.manager import RiskManager
from probablyprofit.utils.ai_rate_limiter import AIRateLimiter, anthropic_rate_limited
from probablyprofit.utils.resilience import retry
from probablyprofit.utils.validators import (
    validate_confidence,
    validate_strategy,
    wrap_strategy_safely,
)


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

        # Validate and sanitize strategy prompt to prevent injection attacks
        sanitized_strategy, strategy_warnings = validate_strategy(strategy_prompt)
        self.strategy_prompt = wrap_strategy_safely(sanitized_strategy)

        # Surface strategy validation warnings to user
        if strategy_warnings:
            logger.warning("Strategy validation warnings:")
            for warning in strategy_warnings:
                logger.warning(f"  - {warning}")

        self.model = model
        self.temperature = temperature

        # Initialize rate limiter for Anthropic API
        self._rate_limiter = AIRateLimiter.get_or_create("anthropic")

        logger.info(f"AnthropicAgent '{name}' initialized with model {model}")

    def _format_observation(self, observation: Observation) -> str:
        """
        Format observation into a prompt for Claude.

        Args:
            observation: Market observation

        Returns:
            Formatted prompt string
        """
        # Use shared formatter to eliminate duplication
        formatted = ObservationFormatter.format_full_observation(
            observation, self.memory, include_history=5, max_markets=20
        )
        return (
            formatted
            + "\nBased on the above information and your trading strategy, what should you do next?\n"
        )

    def _parse_decision(self, response: str, observation: Observation) -> Decision:
        """
        Parse Claude's response into a Decision object with validation.

        Args:
            response: Claude's response text
            observation: Original observation

        Returns:
            Decision object

        Raises:
            ValidationException: If decision data is invalid
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

            # Validate and create decision
            action = data.get("action", "hold")
            confidence = float(data.get("confidence", 0.5))

            # Validate confidence
            try:
                validate_confidence(confidence)
            except ValidationException:
                logger.warning(f"Invalid confidence {confidence}, clamping to 0-1")
                confidence = max(0.0, min(1.0, confidence))

            # Parse price with validation
            price = None
            if "price" in data and data["price"] is not None:
                price = float(data["price"])
                if price < 0 or price > 1:
                    logger.warning(f"Invalid price {price}, clamping to 0-1")
                    price = max(0.0, min(1.0, price))

            decision = Decision(
                action=action,
                market_id=data.get("market_id"),
                outcome=data.get("outcome"),
                size=float(data.get("size", 0)),
                price=price,
                reasoning=data.get("reasoning", response),
                confidence=confidence,
            )

            return decision

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON decision: {e}")
            raise AgentException(f"Invalid JSON in AI response: {e}")
        except ValueError as e:
            logger.error(f"Invalid numeric value in decision: {e}")
            raise AgentException(f"Invalid numeric value: {e}")
        except Exception as e:
            logger.error(f"Unexpected error parsing decision: {e}")
            raise AgentException(f"Error parsing decision: {e}")

    @retry(
        max_attempts=3,
        base_delay=2.0,
        max_delay=30.0,
        retryable_exceptions=(
            ConnectionError,
            TimeoutError,
            NetworkException,
        ),
    )
    async def _call_claude_api(self, messages: list) -> str:
        """
        Call Claude API with retry logic.

        Args:
            messages: Messages to send to Claude

        Returns:
            Response text from Claude

        Raises:
            NetworkException: On connection/timeout errors (will be retried)
            AgentException: On non-retryable errors
        """
        try:
            # Run synchronous API call in thread pool to avoid blocking
            import asyncio

            response = await asyncio.to_thread(
                self.anthropic.messages.create,
                model=self.model,
                max_tokens=2048,
                temperature=self.temperature,
                messages=messages,
            )

            # Record successful request and token usage
            self._rate_limiter.record_success()
            if hasattr(response, "usage") and response.usage:
                self._rate_limiter.record_tokens(
                    response.usage.input_tokens + response.usage.output_tokens
                )

            return response.content[0].text

        except (ConnectionError, TimeoutError) as e:
            logger.warning(f"Claude API connection error (will retry): {e}")
            raise NetworkException(f"Claude API connection error: {e}")
        except Exception as e:
            # Check if it's a retryable Anthropic error
            error_str = str(e).lower()
            if any(x in error_str for x in ["timeout", "connection", "rate limit", "529", "503"]):
                logger.warning(f"Claude API transient error (will retry): {e}")
                raise NetworkException(f"Claude API transient error: {e}")
            # Non-retryable error
            raise AgentException(f"Claude API error: {e}")

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
            # Apply rate limiting before API call
            await self._rate_limiter.acquire(estimated_tokens=2000)

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
""",
                }
            ]

            # Call Claude with retry
            response_text = await self._call_claude_api(messages)
            logger.debug(f"Claude response: {response_text[:200]}...")

            # Parse into decision
            decision = self._parse_decision(response_text, observation)

            logger.info(
                f"[{self.name}] Decision: {decision.action} "
                f"(confidence: {decision.confidence:.0%})"
            )
            logger.info(f"[{self.name}] Reasoning: {decision.reasoning[:200]}...")

            return decision

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from Claude: {e}")
            # Safe default for parsing errors only
            return Decision(
                action="hold",
                reasoning=f"JSON parsing error, defaulting to hold: {e}",
                confidence=0.0,
            )
        except AgentException:
            # Re-raise agent exceptions (already logged)
            raise
        except Exception as e:
            logger.error(f"Error getting decision from Claude: {e}")
            raise AgentException(f"Claude decision error: {e}")

    def decide_streaming(
        self,
        observation: Observation,
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> Decision:
        """
        Use Claude to make a trading decision with streaming output.

        This method streams the AI's response in real-time, allowing
        the CLI to display thinking as it happens.

        Args:
            observation: Current market observation
            on_chunk: Callback function called with each text chunk

        Returns:
            Decision based on AI analysis
        """
        logger.info(f"[{self.name}] Asking Claude for trading decision (streaming)...")

        try:
            # Format observation into prompt
            observation_prompt = self._format_observation(observation)

            # Build messages
            messages = [
                {
                    "role": "user",
                    "content": f"""{self.strategy_prompt}

{observation_prompt}

First, briefly analyze the markets and explain your thinking.
Then provide your trading decision as a JSON object:
```json
{{
    "action": "buy" | "sell" | "hold",
    "market_id": "condition_id of the market (if buy/sell)",
    "outcome": "outcome to bet on (if buy/sell)",
    "size": number of shares,
    "price": limit price between 0 and 1 (if buy/sell),
    "reasoning": "brief explanation of your decision",
    "confidence": 0.0 to 1.0
}}
```

If you recommend holding or not trading, explain why and use action: "hold".
""",
                }
            ]

            # Stream from Claude
            full_response = ""

            with self.anthropic.messages.stream(
                model=self.model,
                max_tokens=2048,
                temperature=self.temperature,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    full_response += text
                    if on_chunk:
                        on_chunk(text)

            # Parse into decision
            decision = self._parse_decision(full_response, observation)

            logger.info(
                f"[{self.name}] Decision: {decision.action} "
                f"(confidence: {decision.confidence:.0%})"
            )

            return decision

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from Claude: {e}")
            return Decision(
                action="hold",
                reasoning=f"JSON parsing error, defaulting to hold: {e}",
                confidence=0.0,
            )
        except Exception as e:
            logger.error(f"Error getting decision from Claude: {e}")
            from probablyprofit.api.exceptions import AgentException

            raise AgentException(f"Claude decision error: {e}")
