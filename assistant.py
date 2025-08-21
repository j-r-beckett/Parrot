from mirascope.core import anthropic, BaseMessageParam, Messages, BaseDynamicConfig
from mirascope.llm import CallResponse
from anthropic import AsyncAnthropic
from dynaconf.utils.boxing import DynaBox
from typing import List, Callable, Awaitable
from logging import Logger


def create_llm_call(llm_config: DynaBox) -> Callable:
    """Create an LLM call function with config bound via closure."""
    client = AsyncAnthropic(api_key=llm_config.api_key)

    async def call_sonnet_4(
        messages: List[BaseMessageParam], tools: list
    ) -> CallResponse:
        """Call Claude Sonnet 4 with thinking enabled."""

        @anthropic.call(model="claude-sonnet-4-20250514")
        async def _call() -> BaseDynamicConfig:
            return {
                "messages": messages,
                "tools": tools,
                "client": client,
                "call_params": anthropic.AnthropicCallParams(
                    max_tokens=llm_config.max_tokens,
                    thinking={
                        "type": "enabled",
                        "budget_tokens": llm_config.max_tokens // 2,
                    },
                ),
            }

        return await _call()

    async def call_haiku_3_5(
        messages: List[BaseMessageParam], tools: list
    ) -> CallResponse:
        """Call Claude Haiku 3.5 without thinking mode."""

        @anthropic.call(model="claude-3-5-haiku-20241022")
        async def _call() -> BaseDynamicConfig:
            return {
                "messages": messages,
                "tools": tools,
                "client": client,
                "call_params": anthropic.AnthropicCallParams(
                    max_tokens=llm_config.max_tokens,
                ),
            }

        return await _call()

    # Select which function to use based on config
    model_name = llm_config.get("model", "claude-sonnet-4")
    if model_name == "claude-sonnet-4":
        return call_sonnet_4
    elif model_name == "claude-3-5-haiku":
        return call_haiku_3_5
    else:
        raise ValueError(f"Unknown model: {model_name}")


async def step(
    llm_call: Callable[[List[BaseMessageParam], list], Awaitable[CallResponse]],
    messages: List[BaseMessageParam],
    tools: list,
    query: str,
) -> tuple[str, List[str]]:
    """
    Execute a single step of the assistant conversation.

    Returns a tuple of (response_text, updated_messages).
    """
    # Add the user query if provided
    if query:
        messages = messages + [Messages.User(query)]

    # Call the LLM
    response = await llm_call(messages, tools)

    # Add the assistant's response to messages
    messages = messages + [response.message_param]

    # Handle tool calls if any
    if response.tools:
        tool_call_results = []
        for tool_call in response.tools:
            result = await tool_call.call()
            tool_call_results.append((tool_call, result))

        # Add tool results to messages
        messages = messages + response.tool_message_params(tool_call_results)

        # Recurse to get the final response
        return await step(llm_call, messages, tools, "")
    else:
        return response.content, [str(m) for m in messages]
