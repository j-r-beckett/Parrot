from mirascope import llm, BaseDynamicConfig, Messages, BaseMessageParam
from config import settings
from typing import List


class Assistant:
    def __init__(self, tools):
        self.tools = tools
        self.messages: List[BaseMessageParam] = [
            Messages.System("You are a helpful assistant")
        ]

    @llm.call(provider=settings.provider, model=settings.model_name)
    def call(self) -> BaseDynamicConfig:
        return {"messages": self.messages, "tools": self.tools}

    def step(self, query: str) -> str:
        if query:
            self.messages.append(Messages.User(query))
        response = self.call()
        self.messages.append(response.message_param)
        if response.tools:
            tool_call_results = [
                (tool_call, tool_call.call()) for tool_call in response.tools
            ]
            self.messages += response.tool_message_params(tool_call_results)
            return self.step("")
        else:
            return response.content
