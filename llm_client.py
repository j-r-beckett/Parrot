from config import ClaudeLlmConfig
from litellm import acompletion
from typing import List, Dict, Any, Optional, Tuple
from logging import Logger
from decimal import Decimal
import asyncio
from datetime import datetime, timedelta


class LlmClient:
    def __init__(self, config: ClaudeLlmConfig):
        self.config = config
        self._last_result: Optional[Tuple[Optional[Exception], datetime]] = None
        self._lock = asyncio.Lock()

    def _calculate_cost(self, usage) -> Decimal:
        if not usage:
            return Decimal("0")

        # LiteLLM provides usage as a dict with prompt_tokens and completion_tokens
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        input_cost = Decimal(str(prompt_tokens)) * self.config.input_token_cost
        output_cost = Decimal(str(completion_tokens)) * self.config.output_token_cost

        return input_cost + output_cost

    async def send_message(
        self,
        messages: List[Dict[str, str]],
        logger: Logger,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Send messages to LLM using LiteLLM.

        Args:
            messages: List of message dicts with 'role' and 'content'
            logger: Logger instance for logging
            max_tokens: Maximum tokens to generate (defaults to self.config.max_tokens)

        Returns:
            The generated text response
        """
        if max_tokens is None:
            max_tokens = self.config.max_tokens
            
        try:
            response = await acompletion(
                model=self.config.model_name,
                messages=messages,
                max_tokens=max_tokens,
                stream=False,
                api_key=self.config.api_key,
            )

            text = response.choices[0].message.content

            async with self._lock:
                self._last_result = (None, datetime.now())

            logger.info(f"Message sent to LLM ({self.config.short_name})")

            # Log usage if available
            if response.usage:
                usage_dict = (
                    response.usage.model_dump()
                    if hasattr(response.usage, "model_dump")
                    else response.usage
                )
                cost = self._calculate_cost(usage_dict)
                prompt_tokens = usage_dict.get("prompt_tokens", 0)
                completion_tokens = usage_dict.get("completion_tokens", 0)
                logger.info(
                    f"Usage: {prompt_tokens} prompt tokens, {completion_tokens} completion tokens, cost: ${cost}"
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
                messages=[{"role": "user", "content": "Hi"}],
                logger=health_logger,
                max_tokens=1
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
