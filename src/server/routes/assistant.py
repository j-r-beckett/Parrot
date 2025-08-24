from litestar import get, Request
from litestar.datastructures import State
from litestar.di import Provide
from typing import Optional, Literal
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
import clients.weather as weather_client
from schemas.weather import HourlyForecast, TwelveHourForecast
from schemas.navigation import Directions


async def get_weather_httpx_client(state: State) -> httpx.AsyncClient:
    return state.weather_httpx_client


async def get_nominatim_httpx_client(state: State) -> httpx.AsyncClient:
    return state.nominatim_httpx_client


async def get_valhalla_httpx_client(state: State) -> httpx.AsyncClient:
    return state.valhalla_httpx_client


async def get_assistant(state: State) -> Assistant:
    return state.assistant


async def get_db_pool(state: State) -> SQLiteConnectionPool:
    return state.db_pool


@get(
    "/testweather/hourly", dependencies={"weather_httpx_client": Provide(get_weather_httpx_client)}
)
async def test_weather_hourly(
    request: Request, weather_httpx_client: httpx.AsyncClient, lat: float, lon: float
) -> HourlyForecast:
    return await weather_client.hourly_forecast(weather_httpx_client, request.logger, lat, lon)


@get(
    "/testweather/12hour",
    dependencies={"weather_httpx_client": Provide(get_weather_httpx_client)},
)
async def test_weather_12hour(
    request: Request, weather_httpx_client: httpx.AsyncClient, lat: float, lon: float
) -> TwelveHourForecast:
    return await weather_client.twelve_hour_forecast(weather_httpx_client, request.logger, lat, lon)


@get(
    "/testagent",
    dependencies={
        "weather_httpx_client": Provide(get_weather_httpx_client),
        "nominatim_httpx_client": Provide(get_nominatim_httpx_client),
        "valhalla_httpx_client": Provide(get_valhalla_httpx_client),
        "assistant": Provide(get_assistant),
        "db_pool": Provide(get_db_pool),
    },
)
async def test_agent(
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
            (conversation_id,)
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
                (conversation_id, json.dumps(msg))
            )
        await db.commit()
    
    return response


@get("/testgeocoding", dependencies={"nominatim_httpx_client": Provide(get_nominatim_httpx_client)})
async def test_geocoding(
    request: Request, nominatim_httpx_client: httpx.AsyncClient, text: str
) -> tuple[float, float]:
    return await nominatim_client.geocode(nominatim_httpx_client, text)


@get(
    "/testnav",
    dependencies={
        "valhalla_httpx_client": Provide(get_valhalla_httpx_client),
        "nominatim_httpx_client": Provide(get_nominatim_httpx_client),
    },
)
async def test_nav(
    request: Request,
    valhalla_httpx_client: httpx.AsyncClient,
    nominatim_httpx_client: httpx.AsyncClient,
    start: str,
    end: str,
    mode: Literal["drive", "walk", "bike", "transit"] = "drive",
) -> Directions:
    # Geocode the start and end locations
    start_coords = await nominatim_client.geocode(nominatim_httpx_client, start)
    end_coords = await nominatim_client.geocode(nominatim_httpx_client, end)

    return await valhalla_client.directions(
        valhalla_httpx_client,
        start=start_coords,
        end=end_coords,
        mode=mode,
    )