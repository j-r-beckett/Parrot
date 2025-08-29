from litestar import get, Request
from litestar.di import Provide
from typing import Optional
import httpx
import json
import uuid
from functools import partial
from mirascope import Messages
from aiosqlitepool import SQLiteConnectionPool
from config import settings
from assistant.llm import Assistant
from assistant.tools.weather import forecast_tool
from assistant.tools.datetime import datetime_tool
from assistant.tools.navigation import navigation_tool
import clients.nominatim as nominatim_client
import clients.valhalla as valhalla_client
from dependencies import (
    get_weather_httpx_client,
    get_nominatim_httpx_client,
    get_valhalla_httpx_client,
    get_assistant,
    get_db_pool,
)


@get(
    "/assist",
    dependencies={
        "weather_httpx_client": Provide(get_weather_httpx_client),
        "nominatim_httpx_client": Provide(get_nominatim_httpx_client),
        "valhalla_httpx_client": Provide(get_valhalla_httpx_client),
        "assistant": Provide(get_assistant),
        "db_pool": Provide(get_db_pool),
    },
)
async def assist(
    request: Request,
    weather_httpx_client: httpx.AsyncClient,
    nominatim_httpx_client: httpx.AsyncClient,
    valhalla_httpx_client: httpx.AsyncClient,
    assistant: Assistant,
    db_pool: SQLiteConnectionPool,
    q: str,
    conversation_id: Optional[str] = None,
) -> str:
    # Generate conversation_id if not provided
    if not conversation_id:
        conversation_id = str(uuid.uuid4())

    # Load existing messages from database
    messages = []
    async with db_pool.connection() as db:
        cursor = await db.execute(
            "SELECT message FROM messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        )
        rows = await cursor.fetchall()
        messages = [json.loads(row[0]) for row in rows]

    # Add system prompt if this is a new conversation
    if not messages:
        messages = [Messages.System(settings.prompts.assistant).model_dump()]

    # Create partial functions with httpx clients bound
    geocode = partial(nominatim_client.geocode, nominatim_httpx_client)
    get_directions = partial(valhalla_client.directions, valhalla_httpx_client)

    # Set up tools
    tools = [
        forecast_tool(weather_httpx_client, geocode, request.logger),
        datetime_tool(geocode),
        navigation_tool(get_directions, geocode),
    ]

    # Remember the original message count
    original_message_count = len(messages)

    # Call step method
    response, all_messages = await assistant.step(messages, tools, q)

    # Save only the new messages to database
    new_messages = all_messages[original_message_count:]
    async with db_pool.connection() as db:
        for msg in new_messages:
            await db.execute(
                "INSERT INTO messages (conversation_id, message) VALUES (?, ?)",
                (conversation_id, json.dumps(msg)),
            )
        await db.commit()

    return response
