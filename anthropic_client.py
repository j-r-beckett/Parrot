from config import AppSettings
from anthropic import AsyncAnthropic
from anthropic.types import Message, MessageParam
from typing import List, Dict, Any, Optional, Tuple
from logging import Logger
from decimal import Decimal
import asyncio
from datetime import datetime, timedelta


class AnthropicClient:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._last_result: Optional[Tuple[Optional[Exception], datetime]] = None
        self._lock = asyncio.Lock()

    def _calculate_cost(self, response: Message) -> Decimal:
        usage = response.usage

        input_cost = Decimal(str(usage.input_tokens)) * self.settings.input_token_cost

        cache_miss_cost = Decimal("0")
        cache_hit_cost = Decimal("0")
        if (
            hasattr(usage, "cache_creation_input_tokens")
            and usage.cache_creation_input_tokens
        ):
            cache_miss_cost = (
                Decimal(str(usage.cache_creation_input_tokens))
                * self.settings.cache_miss_input_token_cost
            )
        if hasattr(usage, "cache_read_input_tokens") and usage.cache_read_input_tokens:
            cache_hit_cost = (
                Decimal(str(usage.cache_read_input_tokens))
                * self.settings.cache_hit_input_token_cost
            )

        output_cost = (
            Decimal(str(usage.output_tokens)) * self.settings.output_token_cost
        )

        total_cost = input_cost + cache_miss_cost + cache_hit_cost + output_cost
        return total_cost

    async def send_message(self, messages: List[Dict[str, str]], logger: Logger) -> str:
        try:
            response = await self.client.messages.create(
                max_tokens=self.settings.anthropic_max_tokens,
                messages=messages,
                model=self.settings.anthropic_model,
            )
            async with self._lock:
                self._last_result = (None, datetime.now())
            logger.info("Message sent to Anthropic API")
            return " ".join(
                block.text for block in response.content if block.type == "text"
            )
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
            await self.client.messages.create(
                max_tokens=1,
                messages=[{"role": "user", "content": "Hi"}],
                model=self.settings.anthropic_model,
                system=[{"type": "text", "text": "Hi"}],
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
