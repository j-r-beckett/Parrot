from config import AppSettings
from anthropic import AsyncAnthropic
from typing import List, Dict, Any
from logging import Logger


class AnthropicClient:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def send_message(
        self, messages: List[Dict[str, str]], logger: Logger
    ) -> str:
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
            return (True, "Anthropic API is accessible")
        except Exception as e:
            return (False, str(e))