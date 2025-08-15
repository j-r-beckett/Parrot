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
                "As a general rule, provide only the minimum amount of information necessary to answer the user's query. "
                "Do not include any filler text. "
                "You have access to a suite of tools. These tools generally return raw data. "
                "Part of your job as an assistant is to shield the user from the complexity of these tools. "
                "You should use the tools to gain the knowledge needed to answer user queries, but you don't "
                "necessarily need to use all information returned by the tool or mimic the structure of the data "
                "returned by the tool in your response to the user."
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
