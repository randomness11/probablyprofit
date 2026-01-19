"""
Gemini Agent

AI-powered trading agent using Google's Gemini models.
Updated to use the new google-genai SDK.
"""

import asyncio
import json
from typing import Any, Optional

from loguru import logger

from probablyprofit.agent.base import BaseAgent, Decision, Observation
from probablyprofit.agent.formatters import ObservationFormatter, get_decision_schema
from probablyprofit.api.client import PolymarketClient
from probablyprofit.api.exceptions import AgentException, NetworkException, ValidationException
from probablyprofit.risk.manager import RiskManager
from probablyprofit.utils.resilience import retry
from probablyprofit.utils.validators import (
    validate_confidence,
    validate_strategy,
    wrap_strategy_safely,
)

# Try new SDK first, fall back to old
try:
    from google import genai
    from google.genai import types

    NEW_SDK = True
except ImportError:
    try:
        import google.generativeai as genai

        NEW_SDK = False
        logger.warning("Using deprecated google.generativeai - consider upgrading to google-genai")
    except ImportError:
        genai = None
        NEW_SDK = False


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
        model: str = "gemini-2.0-flash",
        name: str = "GeminiAgent",
        loop_interval: int = 60,
        strategy: Optional[Any] = None,
        dry_run: bool = False,
    ):
        super().__init__(
            client, risk_manager, name, loop_interval, strategy=strategy, dry_run=dry_run
        )

        if genai is None:
            raise ImportError("Google Gemini SDK not installed. Run: pip install google-genai")

        self.model_name = model
        self.api_key = google_api_key

        # Validate and sanitize strategy prompt to prevent injection attacks
        sanitized_strategy, strategy_warnings = validate_strategy(strategy_prompt)
        self.strategy_prompt = wrap_strategy_safely(sanitized_strategy)

        # Surface strategy validation warnings to user
        if strategy_warnings:
            logger.warning("Strategy validation warnings:")
            for warning in strategy_warnings:
                logger.warning(f"  - {warning}")

        if NEW_SDK:
            # New google-genai SDK
            self.genai_client = genai.Client(api_key=google_api_key)
        else:
            # Old google-generativeai SDK
            genai.configure(api_key=google_api_key)
            self.model = genai.GenerativeModel(
                model_name=model, generation_config={"response_mime_type": "application/json"}
            )

        logger.info(f"GeminiAgent '{name}' initialized with model {model}")

    @retry(
        max_attempts=3,
        base_delay=2.0,
        max_delay=30.0,
        retryable_exceptions=(ConnectionError, TimeoutError, NetworkException),
    )
    async def _call_gemini_api(self, prompt: str) -> str:
        """
        Call Gemini API with retry logic.

        Args:
            prompt: The prompt to send

        Returns:
            Response content text

        Raises:
            NetworkException: On connection/timeout errors (will be retried)
            AgentException: On non-retryable errors
        """
        try:
            if NEW_SDK:
                response = await asyncio.to_thread(
                    self.genai_client.models.generate_content,
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                    ),
                )
                return response.text
            else:
                response = await asyncio.to_thread(self.model.generate_content, prompt)
                if not response or not response.text:
                    raise AgentException("Empty response from Gemini")
                return response.text

        except (ConnectionError, TimeoutError) as e:
            logger.warning(f"Gemini API connection error (will retry): {e}")
            raise NetworkException(f"Gemini API connection error: {e}")
        except Exception as e:
            error_str = str(e).lower()
            if any(
                x in error_str
                for x in ["timeout", "connection", "rate limit", "429", "503", "502", "quota"]
            ):
                logger.warning(f"Gemini API transient error (will retry): {e}")
                raise NetworkException(f"Gemini API transient error: {e}")
            raise AgentException(f"Gemini API error: {e}")

    def _format_observation(self, observation: Observation) -> str:
        """
        Format observation using concise formatter for Gemini.
        """
        return ObservationFormatter.format_concise(observation, self.memory)

    async def decide(self, observation: Observation) -> Decision:
        """
        Use Gemini to make a trading decision with validation.
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

            # Call API with retry logic
            content = await self._call_gemini_api(prompt)
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
                confidence=confidence,
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
