"""
Gemini Agent

AI-powered trading agent using Google's Gemini models.
"""

import json
from typing import Any, Optional
import google.generativeai as genai
from loguru import logger

from probablyprofit.agent.base import BaseAgent, Observation, Decision
from probablyprofit.agent.formatters import ObservationFormatter, get_decision_schema
from probablyprofit.api.client import PolymarketClient
from probablyprofit.api.exceptions import AgentException, ValidationException
from probablyprofit.risk.manager import RiskManager
from probablyprofit.utils.validators import validate_confidence


class GeminiAgent(BaseAgent):
    """
    AI-powered trading agent using Google's Gemini models.
    """

    def __init__(
        self,
        client: PolymarketClient,
        risk_manager: RiskManager,
        google_api_key: str,
        strategy_prompt: str,
        model: str = "gemini-1.5-pro",
        name: str = "GeminiAgent",
        loop_interval: int = 60,
        strategy: Optional[Any] = None,
        dry_run: bool = False,
    ):
        super().__init__(client, risk_manager, name, loop_interval, strategy=strategy, dry_run=dry_run)

        genai.configure(api_key=google_api_key)
        self.model_name = model
        self.model = genai.GenerativeModel(
            model_name=model,
            generation_config={"response_mime_type": "application/json"}
        )
        self.strategy_prompt = strategy_prompt
        
        logger.info(f"GeminiAgent '{name}' initialized with model {model} (Long Context Ready)")

    def _format_observation(self, observation: Observation) -> str:
        """
        Format observation using concise formatter for Gemini.

        Args:
            observation: Market observation

        Returns:
            Concise formatted prompt string
        """
        # Use concise format for faster/cheaper Gemini model
        return ObservationFormatter.format_concise(observation, self.memory)

    async def decide(self, observation: Observation) -> Decision:
        """
        Use Gemini to make a trading decision with validation.

        Args:
            observation: Current market observation

        Returns:
            Decision based on AI analysis

        Raises:
            AgentException: If decision-making fails
        """
        logger.info(f"[{self.name}] Asking Gemini for decision...")

        try:
            obs_text = self._format_observation(observation)

            prompt = f"""{self.strategy_prompt}

CURRENT SITUATION:
{obs_text}

Respond with a JSON object with this schema:
{get_decision_schema()}
"""

            # Note: The generation_config in init enforces JSON mode
            response = self.model.generate_content(prompt)

            if not response or not response.text:
                raise AgentException("Empty response from Gemini")

            content = response.text
            logger.debug(f"Gemini response: {content[:200]}...")

            data = json.loads(content)

            # Validate and create decision
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
            logger.error(f"Failed to parse JSON from Gemini: {e}")
            raise AgentException(f"Invalid JSON in AI response: {e}")
        except ValueError as e:
            logger.error(f"Invalid numeric value in decision: {e}")
            raise AgentException(f"Invalid numeric value: {e}")
        except Exception as e:
            logger.error(f"Error getting decision from Gemini: {e}")
            raise AgentException(f"Gemini decision error: {e}")
