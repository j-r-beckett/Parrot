from mirascope import llm, BaseDynamicConfig, Messages, BaseMessageParam
from mirascope.core import anthropic
from config import settings
from typing import List
from logging import Logger


class Assistant:
    def __init__(self, tools, logger: Logger):
        self.tools = tools
        self.logger = logger
        self.messages: List[BaseMessageParam] = [
            Messages.System(
                "You are a helpful assistant. "
                "Be concise, try to keep responses to under 10 words. "
                "Do not include any filler text. "
            )
        ]

    @anthropic.call(
        model=settings.model_name,
        call_params=anthropic.AnthropicCallParams(
            max_tokens=2048, thinking={"type": "enabled", "budget_tokens": 1024}
        ),
    )
    async def call(self) -> BaseDynamicConfig:
        return {"messages": self.messages, "tools": self.tools}

    async def step(self, query: str) -> str:
        if query:
            self.messages.append(Messages.User(query))
        response = await self.call()
        self.logger.info("Received response: %s", response)
        self.messages.append(response.message_param)
        if response.tools:
            tool_call_results = []
            for tool_call in response.tools:
                result = await tool_call.call()
                tool_call_results.append((tool_call, result))
            self.messages += response.tool_message_params(tool_call_results)
            return await self.step("")
        else:
            return response.content
