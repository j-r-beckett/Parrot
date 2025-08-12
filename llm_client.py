from config import ClaudeLlmConfig
from mirascope.core.anthropic import AnthropicCallResponse, anthropic_call
from mirascope.core.base import BaseDynamicConfig, Messages, BaseMessageParam
from mirascope.core.costs import calculate_cost
from typing import List, Any, Optional, Tuple
from logging import Logger
import asyncio
from datetime import datetime, timedelta
from anthropic import AsyncAnthropic


class LlmClient:
    def __init__(self, config: ClaudeLlmConfig):
        self.config = config
        self._last_result: Optional[Tuple[Optional[Exception], datetime]] = None
        self._lock = asyncio.Lock()

    async def send_message(
        self,
        messages: List[BaseMessageParam],
        logger: Logger,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Send messages to LLM using Mirascope.

        Args:
            messages: List of Mirascope message objects
            logger: Logger instance for logging
            max_tokens: Maximum tokens to generate (defaults to self.config.max_tokens)

        Returns:
            The generated text response
        """
        if max_tokens is None:
            max_tokens = self.config.max_tokens

        try:
            # Create the async call function with API key in client initialization
            client = AsyncAnthropic(api_key=self.config.api_key)

            @anthropic_call(
                model=self.config.model_name,
                call_params={
                    "max_tokens": max_tokens,
                },
                client=client,
            )
            async def _make_call() -> BaseDynamicConfig:
                return {
                    "messages": messages,
                }

            response: AnthropicCallResponse = await _make_call()

            text = response.content

            async with self._lock:
                self._last_result = (None, datetime.now())

            logger.info(f"Message sent to LLM ({self.config.short_name})")

            # Log usage
            cost = calculate_cost(
                "anthropic", self.config.model_name, response.cost_metadata
            )
            cost_str = (
                f"${cost:.6f}"
                if cost is not None
                else "N/A (model not in pricing database)"
            )
            logger.info(
                f"Usage: {response.input_tokens} prompt tokens, {response.output_tokens} completion tokens, cost: {cost_str}"
            )

            return text
        except Exception as e:
            async with self._lock:
                self._last_result = (e, datetime.now())
            raise

    async def health(self) -> tuple[bool, Any]:
        async with self._lock:
            last_result = self._last_result

        # Check if we should use cached result
        if last_result:
            exception, timestamp = last_result
            if exception is None:
                return (
                    True,
                    f"Most recent request at {timestamp.isoformat()} was successful",
                )

            # Failed request - only retry if > 15 seconds old
            if datetime.now() - timestamp < timedelta(seconds=15):
                return (
                    False,
                    f"Most recent request at {timestamp.isoformat()} failed: {exception}",
                )

        # Make a real API call
        try:
            # Create a minimal logger for health checks
            import logging

            health_logger = logging.getLogger("health_check")

            await self.send_message(
                messages=[Messages.User("Hi")],
                logger=health_logger,
                max_tokens=1,
            )

            now = datetime.now()
            async with self._lock:
                self._last_result = (None, now)
            return (True, f"Most recent request at {now.isoformat()} was successful")
        except Exception as e:
            now = datetime.now()
            async with self._lock:
                self._last_result = (e, now)
            return (False, f"Most recent request failed: {e}")
