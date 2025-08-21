from mirascope.core import anthropic, BaseMessageParam, Messages, BaseDynamicConfig
from mirascope.llm import CallResponse
from anthropic import AsyncAnthropic
from dynaconf.utils.boxing import DynaBox
from typing import List, Callable, Awaitable
from logging import Logger


def create_llm_call(llm_config: DynaBox) -> Callable:
    """Create an LLM call function with config bound via closure."""
    client = AsyncAnthropic(api_key=llm_config.api_key)
    
    async def call(
        messages: List[BaseMessageParam],
        tools: list
    ) -> CallResponse:
        """Call the LLM with the given messages and tools."""
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
    
    return call


async def step(
    llm_call: Callable[[List[BaseMessageParam], list], Awaitable[CallResponse]],
    messages: List[BaseMessageParam],
    tools: list,
    query: str
) -> tuple[str, List[BaseMessageParam]]:
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
        return response.content, messages