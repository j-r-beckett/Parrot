from mirascope.core import anthropic, BaseMessageParam, Messages, BaseDynamicConfig
from mirascope.llm import CallResponse
from anthropic import AsyncAnthropic
from dynaconf.utils.boxing import DynaBox
from typing import List, Callable, Awaitable, Union
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
        messages: List[dict],
        tools: list,
        query: str,
    ) -> tuple[str, List[dict]]:
        """
        Execute a single step of the assistant conversation.

        Returns a tuple of (response_text, updated_messages).
        """
        if query:
            messages = messages + [Messages.User(query).model_dump()]
        response = await self.call_llm(messages, tools)

        # Handle message_param - it might be a BaseMessageParam or a dict
        message_param = response.message_param
        if hasattr(message_param, "model_dump"):
            # It's a BaseMessageParam, convert to dict
            messages.append(message_param.model_dump())
        else:
            # It's already a dict (e.g., from thinking mode)
            messages.append(message_param)

        if response.tools:
            tool_call_results = []
            for tool_call in response.tools:
                try:
                    result = await tool_call.call()
                    tool_call_results.append((tool_call, result))
                except Exception as ex:
                    tool_call_results.append((tool_call, str(ex)))
            # Convert tool message params to dicts
            tool_messages = response.tool_message_params(tool_call_results)
            for msg in tool_messages:
                if hasattr(msg, "model_dump"):
                    messages.append(msg.model_dump())
                else:
                    messages.append(msg)
            return await self.step(messages, tools, "")
        else:
            return response.content, messages

    async def _call_sonnet_4(self, messages: List[dict], tools: list) -> CallResponse:
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

    async def _call_haiku_3_5(self, messages: List[dict], tools: list) -> CallResponse:
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
