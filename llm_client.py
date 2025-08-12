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
        self._last_result_lock = asyncio.Lock()

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
        try:
            if max_tokens is None:
                max_tokens = self.config.max_tokens

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

            async with self._last_result_lock:
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
            async with self._last_result_lock:
                self._last_result = (e, datetime.now())
            raise

    async def health(self, logger: Logger) -> tuple[bool, Any]:
        async with self._last_result_lock:
            last_result = self._last_result

        # If necessary, update _last_result by calling send_message
        if (
            last_result is None  # No last result
            or (
                last_result[0] is not None  # Last was a failure
                and datetime.now() - last_result[1]
                > timedelta(seconds=15)  # And it's stale
            )
        ):
            # Make a real API call
            await self.send_message(
                messages=[Messages.User("Hi")],
                logger=logger,
                max_tokens=1,
            )

            # self._last_result is updated by the API call; benign race condition
            async with self._last_result_lock:
                exception, timestamp = self._last_result
        else:
            exception, timestamp = last_result

        if exception is None:
            return (
                True,
                f"Most recent request at {timestamp.isoformat()} was successful",
            )
        else:
            return (
                False,
                f"Most recent request at {timestamp.isoformat()} failed: {exception}",
            )
