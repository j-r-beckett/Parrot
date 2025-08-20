from mirascope import BaseDynamicConfig, Messages, BaseMessageParam
from mirascope.core import anthropic
from anthropic import AsyncAnthropic
from dynaconf.utils.boxing import DynaBox
from typing import List, Callable
from collections.abc import Awaitable
from logging import Logger
import asyncio
from asyncio import CancelledError


class Assistant:
    def __init__(
        self,
        tools,
        logger: Logger,
        process_outbound_msg: Callable[[str], Awaitable[str]],
        cleanup: Callable[[], Awaitable[None]],
        llm_config: DynaBox,
    ):
        self.tools = tools
        self.logger = logger
        self.process_outbound_msg = process_outbound_msg
        self.cleanup = cleanup
        self.llm_config = llm_config
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

        self.incoming_messages = asyncio.Queue()

    @anthropic.call(model="claude-sonnet-4-20250514")
    async def _call(self) -> BaseDynamicConfig:
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

    async def _step(self, query: str) -> str:
        if query:
            self.messages.append(Messages.User(query))
        response = await self._call()
        self.messages.append(response.message_param)
        if response.tools:
            tool_call_results = []
            for tool_call in response.tools:
                result = await tool_call.call()
                tool_call_results.append((tool_call, result))
            self.messages += response.tool_message_params(tool_call_results)
            return await self._step("")
        else:
            return response.content

    async def submit_msg(self, msg: str):
        await self.incoming_messages.put(msg)

    async def start(self):
        await self._load_messages()

        step_task = None

        while True:
            new_message_task = asyncio.create_task(self.incoming_messages.get())
            if step_task:
                done, pending = await asyncio.wait(
                    [step_task, new_message_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if step_task in done:
                    result = await step_task
                    await self.process_outbound_msg(result)
                    if new_message_task in done:
                        msg = await new_message_task
                        step_task = asyncio.create_task(self._step(msg))
                    else:
                        new_message_task.cancel()
                        try:
                            await new_message_task
                        except CancelledError:
                            pass
                        await self._store_messages()
                        await self.cleanup()
                        return
                else:
                    assert step_task in pending
                    assert new_message_task in done
                    step_task.cancel()
                    try:
                        await step_task
                    except CancelledError:
                        pass
                    msg = await new_message_task
                    step_task = asyncio.create_task(self._step(msg))
            else:
                msg = await new_message_task
                step_task = asyncio.create_task(self._step(msg))

    async def _load_messages(self):
        # todo: load messages from sqlite, append to self.messages
        pass

    async def _store_messages(self):
        # todo: store self.messages in sqlite
        pass
