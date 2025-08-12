from config import ClaudeLlmConfig
from ai_sdk import anthropic, stream_text, generate_text
from ai_sdk.types import CoreUserMessage, CoreAssistantMessage, CoreSystemMessage
from typing import List, Dict, Any, Optional, Tuple
from logging import Logger
from decimal import Decimal
import asyncio
from datetime import datetime, timedelta


class LlmClient:
    def __init__(self, config: ClaudeLlmConfig):
        self.config = config

        if config.short_name == "claude-sonnet-4":
            self.model = anthropic(
                config.model_name,
                api_key=config.api_key,
                max_tokens=config.max_tokens,
            )
        else:
            raise ValueError(f"Unsupported model: {config.short_name}")

        self._last_result: Optional[Tuple[Optional[Exception], datetime]] = None
        self._lock = asyncio.Lock()

    def _calculate_cost(self, usage) -> Decimal:
        input_cost = Decimal(str(usage.prompt_tokens)) * self.config.input_token_cost
        output_cost = (
            Decimal(str(usage.completion_tokens)) * self.config.output_token_cost
        )

        return input_cost + output_cost

    async def send_message(
        self,
        messages: List[CoreUserMessage | CoreAssistantMessage | CoreSystemMessage],
        logger: Logger,
    ) -> str:
        try:
            # Test: Try using generate_text instead of stream_text to see if usage is populated
            # Convert to sync call wrapped in asyncio
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: generate_text(model=self.model, messages=messages)
            )
            text = response.text

            async with self._lock:
                self._last_result = (None, datetime.now())

            logger.info(f"Message sent to LLM ({self.config.short_name})")

            # Log usage if available
            logger.debug(f"Response usage object: {response.usage}")
            if response.usage:
                cost = self._calculate_cost(response.usage)
                logger.info(
                    f"Usage: {response.usage.prompt_tokens} prompt tokens, {response.usage.completion_tokens} completion tokens, cost: ${cost}"
                )
            else:
                logger.warning("No usage information available from response")

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
            stream_res = stream_text(model=self.model, prompt="Hi", system="Hi")
            await stream_res.text()

            now = datetime.now()
            async with self._lock:
                self._last_result = (None, now)
            return (True, f"Most recent request at {now.isoformat()} was successful")
        except Exception as e:
            now = datetime.now()
            async with self._lock:
                self._last_result = (e, now)
            return (False, f"Most recent request failed: {e}")
