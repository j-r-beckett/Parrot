from config import AppSettings
from anthropic import AsyncAnthropic
from anthropic.types import Message
from typing import List, Dict, Any
from logging import Logger
from decimal import Decimal


class AnthropicClient:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)

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
        response = await self.client.messages.create(
            max_tokens=self.settings.anthropic_max_tokens,
            messages=messages,
            model=self.settings.anthropic_model,
        )
        logger.info("Message sent to Anthropic API")
        return " ".join(
            block.text for block in response.content if block.type == "text"
        )

    async def health(self) -> tuple[bool, Any]:
        try:
            response = await self.client.messages.create(
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}],
                model=self.settings.anthropic_model,
            )
            cost = self._calculate_cost(response)
            return (
                True,
                f"Anthropic health! Cost: ${cost}; projected cost for a day of usage: ${cost * 2 * 60 * 24}",
            )
        except Exception as e:
            return (False, str(e))
