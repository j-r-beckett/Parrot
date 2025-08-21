from mirascope import BaseDynamicConfig, Messages, BaseMessageParam
from mirascope.core import anthropic
from anthropic import AsyncAnthropic
from dynaconf.utils.boxing import DynaBox
from typing import List, Callable
from collections.abc import Awaitable
from logging import Logger
import asyncio
from asyncio import CancelledError, QueueShutDown


class ExperimentalAssistant:
    def __init__(
        self,
        tools,
        logger: Logger,
        process_outbound_msg: Callable[[str], Awaitable[str]],
        llm_config: DynaBox,
    ):
        self.tools = tools
        self.logger = logger
        self.process_outbound_msg = process_outbound_msg
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

        self.in_queue = asyncio.Queue()

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

    async def _llm_step(self, query: str) -> str:
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
            return await self._llm_step("")
        else:
            return response.content

    async def start(self):
        # todo: load messages from sqlite, append to self.messages
        self.run_task = asyncio.create_task(self._run())

    async def stop(self):
        self.in_queue.shutdown()
        await self.run_task
        # todo: store self.messages in sqlite

    async def submit_msg(self, msg: str):
        await self.in_queue.put(msg)

    async def _run(self):
        llm_step_task = None
        next_msg_task = asyncio.create_task(self.in_queue.get())

        try:
            while True:
                if llm_step_task:
                    done, pending = await asyncio.wait(
                        [llm_step_task, next_msg_task],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if llm_step_task in done:
                        llm_result = await llm_step_task
                        await self.process_outbound_msg(llm_result)
                        if next_msg_task in done:
                            next_msg = await next_msg_task
                            llm_step_task = asyncio.create_task(
                                self._llm_step(next_msg)
                            )
                            next_msg_task = asyncio.create_task(self.in_queue.get())
                        else:
                            llm_step_task = None
                    else:
                        assert llm_step_task in pending
                        assert next_msg_task in done
                        llm_step_task.cancel()
                        try:
                            await llm_step_task
                        except CancelledError:
                            pass
                        next_msg = await next_msg_task
                        llm_step_task = asyncio.create_task(self._llm_step(next_msg))
                        next_msg_task = asyncio.create_task(self.in_queue.get())
                else:
                    next_msg = await next_msg_task
                    llm_step_task = asyncio.create_task(self._llm_step(next_msg))
        except QueueShutDown:
            if llm_step_task:
                llm_result = await llm_step_task
                await self.process_outbound_msg(llm_result)
