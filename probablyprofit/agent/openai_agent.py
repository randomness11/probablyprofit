"""
OpenAI Agent

AI-powered trading agent using GPT-4 for decision-making.
"""

import json
from typing import Any, Optional
from openai import OpenAI
from loguru import logger

from probablyprofit.agent.base import BaseAgent, Observation, Decision
from probablyprofit.agent.formatters import ObservationFormatter, get_decision_schema
from probablyprofit.api.client import PolymarketClient
from probablyprofit.api.exceptions import AgentException, ValidationException
from probablyprofit.risk.manager import RiskManager
from probablyprofit.utils.validators import validate_confidence


class OpenAIAgent(BaseAgent):
    """
    AI-powered trading agent using OpenAI's GPT models.
    """

    def __init__(
        self,
        client: PolymarketClient,
        risk_manager: RiskManager,
        openai_api_key: str,
        strategy_prompt: str,
        model: str = "gpt-4o",
        name: str = "OpenAIAgent",
        loop_interval: int = 60,
        strategy: Optional[Any] = None,
        dry_run: bool = False,
    ):
        """
        Initialize OpenAI agent.
        """
        super().__init__(client, risk_manager, name, loop_interval, strategy=strategy, dry_run=dry_run)

        self.openai = OpenAI(api_key=openai_api_key)
        self.model = model
        self.strategy_prompt = strategy_prompt
        self.temperature = 0.7

        logger.info(f"OpenAIAgent '{name}' initialized with model {model}")

    def _format_observation(self, observation: Observation) -> str:
        """
        Format observation using shared formatter.

        Args:
            observation: Market observation

        Returns:
            Formatted prompt string
        """
        return ObservationFormatter.format_full_observation(
            observation, self.memory, include_history=5, max_markets=20
        )

    async def decide(self, observation: Observation) -> Decision:
        """
        Use GPT-4 or o1 to make a trading decision with validation.

        Args:
            observation: Current market observation

        Returns:
            Decision based on AI analysis

        Raises:
            AgentException: If decision-making fails
        """
        logger.info(f"[{self.name}] Asking {self.model} for decision...")

        try:
            obs_text = self._format_observation(observation)
            
            # OpenAI 'o1' and 'o3' models have specific constraints:
            # 1. No 'system' role (use 'developer' or merge into 'user')
            # 2. No 'temperature' parameter (fixed at 1.0 usually)
            # 3. No 'response_format' json_object in early preview (sometimes)
            
            is_reasoning_model = self.model.startswith("o1") or self.model.startswith("o3")
            
            messages = []
            
            if is_reasoning_model:
                # For o1, we put everything in the user prompt or use developer role if available.
                # Currently safe bet is to prepend system instruction to user content.
                combined_prompt = f"""{self.strategy_prompt}
                
---
MARKET DATA:
{obs_text}

Respond in strict JSON format.
Output schema:
{get_decision_schema()}
"""
                messages.append({"role": "user", "content": combined_prompt})
                
                # Reasoning models don't support temperature
                kwargs = {}
                # Some o1 preview models support max_completion_tokens instead of max_tokens
            else:
                # Standard GPT-4 setup
                system_prompt = f"""{self.strategy_prompt}

You are a trading bot. Respond in strict JSON format.
Output schema:
{get_decision_schema()}
"""
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": obs_text}
                ]
                kwargs = {"temperature": self.temperature}

            # Call API
            response = self.openai.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
                **kwargs
            )

            if not response.choices or len(response.choices) == 0:
                raise AgentException("No response choices from OpenAI")

            content = response.choices[0].message.content
            logger.debug(f"AI response: {content[:200]}...")

            data = json.loads(content)

            # Validate and create decision with proper error handling
            action = data.get("action", "hold")
            confidence = float(data.get("confidence", 0.5))

            # Validate confidence
            try:
                validate_confidence(confidence)
            except ValidationException:
                logger.warning(f"Invalid confidence {confidence}, clamping to 0-1")
                confidence = max(0.0, min(1.0, confidence))

            # Parse and validate price
            price = None
            if "price" in data and data["price"] is not None:
                try:
                    price = float(data["price"])
                    if price < 0 or price > 1:
                        logger.warning(f"Invalid price {price}, clamping to 0-1")
                        price = max(0.0, min(1.0, price))
                except (ValueError, TypeError) as e:
                    logger.warning(f"Could not parse price: {e}")
                    price = None

            return Decision(
                action=action,
                market_id=data.get("market_id"),
                outcome=data.get("outcome"),
                size=float(data.get("size", 0)),
                price=price,
                reasoning=data.get("reasoning", ""),
                confidence=confidence
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from OpenAI: {e}")
            raise AgentException(f"Invalid JSON in AI response: {e}")
        except ValueError as e:
            logger.error(f"Invalid numeric value in decision: {e}")
            raise AgentException(f"Invalid numeric value: {e}")
        except Exception as e:
            logger.error(f"Error getting decision from OpenAI: {e}")
            raise AgentException(f"OpenAI decision error: {e}")
