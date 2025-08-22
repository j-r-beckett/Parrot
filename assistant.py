from mirascope.core import anthropic, BaseMessageParam, Messages, BaseDynamicConfig
from mirascope.llm import CallResponse
from anthropic import AsyncAnthropic
from dynaconf.utils.boxing import DynaBox
from typing import List, Callable, Awaitable
from logging import Logger


class Assistant:
    """Assistant class for managing LLM interactions."""

    def __init__(self, llm_config: DynaBox):
        """Initialize Assistant with LLM configuration."""
        self.client = AsyncAnthropic(api_key=llm_config.api_key)
        self.llm_config = llm_config

        # Select model call function based on config
        model_name = llm_config.get("model", "claude-sonnet-4")
        if model_name == "claude-sonnet-4":
            self.call_llm = self._call_sonnet_4
        elif model_name == "claude-3-5-haiku":
            self.call_llm = self._call_haiku_3_5
        else:
            raise ValueError(f"Unknown model: {model_name}")

    async def step(
        self,
        messages: List[BaseMessageParam],
        tools: list,
        query: str,
    ) -> tuple[str, List[str]]:
        """
        Execute a single step of the assistant conversation.

        Returns a tuple of (response_text, updated_messages).
        """
        if query:
            messages = messages + [Messages.User(query)]
        response = await self.call_llm(messages, tools)
        messages.append(response.message_param)
        if response.tools:
            tool_call_results = [
                (tool_call, await tool_call.call()) for tool_call in response.tools
            ]
            messages.extend(response.tool_message_params(tool_call_results))
            return await self.step(messages, tools, "")
        else:
            return response.content, [str(m) for m in messages]

    async def _call_sonnet_4(
        self, messages: List[BaseMessageParam], tools: list
    ) -> CallResponse:
        """Call Claude Sonnet 4 with thinking enabled."""

        @anthropic.call(model="claude-sonnet-4-20250514")
        async def _call() -> BaseDynamicConfig:
            return {
                "messages": messages,
                "tools": tools,
                "client": self.client,
                "call_params": anthropic.AnthropicCallParams(
                    max_tokens=self.llm_config.max_tokens,
                    thinking={
                        "type": "enabled",
                        "budget_tokens": self.llm_config.max_tokens // 2,
                    },
                ),
            }

        return await _call()

    async def _call_haiku_3_5(
        self, messages: List[BaseMessageParam], tools: list
    ) -> CallResponse:
        """Call Claude Haiku 3.5 without thinking mode."""

        @anthropic.call(model="claude-3-5-haiku-20241022")
        async def _call() -> BaseDynamicConfig:
            return {
                "messages": messages,
                "tools": tools,
                "client": self.client,
                "call_params": anthropic.AnthropicCallParams(
                    max_tokens=self.llm_config.max_tokens,
                ),
            }

        return await _call()
