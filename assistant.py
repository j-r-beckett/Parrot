from mirascope import CallResponse, BaseDynamicConfig, Messages, BaseMessageParam
from mirascope.core import anthropic
from anthropic import AsyncAnthropic
from dynaconf.utils.boxing import DynaBox
from typing import List
from logging import Logger


class Assistant:
    def __init__(self, tools, logger: Logger, llm_config: DynaBox):
        self.tools = tools
        self.logger = logger
        self.llm_config = llm_config
        # Create the client once during initialization
        self.client = AsyncAnthropic(api_key=llm_config.api_key)
        self.messages: List[BaseMessageParam] = [
            Messages.System(
                "You are a helpful, but efficient, assistant. Be as terse as possible, and convey "
                "the bare minimum of information required to answer the user's question. Do not include "
                "any filler words, preambles, postambles, or editorials. Do not convey to the user "
                "information they already know. "
                "In general, you should be substantially more terse than your natural inclination. "
                "For instance, if the user asks what the weather will be like tomorrow, you should answer "
                "like this: 'High 85, low 68, showers in the afternoon'. No need to tell them the date, "
                "or suggest they bring an umbrella, or tell them about gust speed. Just convey the bare minimum "
                "needed to answer their question. This is to respect the user's time; if they have additional "
                "questions or need more information, they will ask for it."
                "This is a general principle that should be applied to all user questions. "
                "You have access to a suite of tools to help answer user requests. Use them as you see fit. "
                "User's query: "
            )
        ]

    async def call(self) -> CallResponse:
        @anthropic.call(model="claude-sonnet-4-20250514")
        async def call() -> BaseDynamicConfig:
            return {
                "messages": self.messages,
                "tools": self.tools,
                "client": self.client,
                "call_params": anthropic.AnthropicCallParams(
                    max_tokens=self.llm_config.max_tokens,
                    thinking={
                        "type": "enabled",
                        "budget_tokens": self.llm_config.max_tokens // 2,
                    },
                ),
            }

        return call()

    async def step(self, query: str) -> str:
        if query:
            self.messages.append(Messages.User(query))
        response = await self.call()
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
