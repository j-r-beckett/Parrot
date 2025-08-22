from litestar import Litestar, get, Request, Response, post
from litestar.datastructures import State
from litestar.di import Provide
from litestar.status_codes import HTTP_200_OK, HTTP_503_SERVICE_UNAVAILABLE
from config import settings
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Literal, Callable, Optional
from functools import partial
import httpx
from sms_gateway import create_sms_gateway_client, send_sms, init_webhooks
from schemas import (
    SmsDelivered,
    SmsReceived,
    HourlyForecast,
    TwelveHourForecast,
    Directions,
)
import weather_client
from weather_tools import forecast_tool
from datetime_tools import datetime_tool
from navigation_tools import navigation_tool
from assistant import Assistant
from mirascope import Messages
import nominatim_client
import valhalla_client
import aiosqlite
from aiosqlitepool import SQLiteConnectionPool
import json
import uuid


async def get_sms_gateway_client(state: State) -> httpx.AsyncClient:
    return state.sms_gateway_client


async def get_webhook_events(state: State) -> dict:
    return state.webhook_events


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


async def init_database(db_pool: SQLiteConnectionPool) -> None:
    """Initialize the database schema for conversations."""
    async with db_pool.connection() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversation_id 
            ON messages(conversation_id)
        """)
        await db.commit()


@get(path="/health")
async def health(request: Request) -> str:
    return "healthy"


@get("/testsms", dependencies={"sms_gateway_client": Provide(get_sms_gateway_client)})
async def test_sms(request: Request, sms_gateway_client: httpx.AsyncClient) -> Response:
    await send_sms(
        sms_gateway_client, "hello there 3", settings.sms.settler.number, request.logger
    )

    return Response(content="sent sms", status_code=HTTP_200_OK)


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


@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None, None]:
    async def on_delivered(data: SmsDelivered) -> None:
        app.logger.info("SMS delivered: %s", data)

    async def on_received(data: SmsReceived) -> None:
        app.logger.info("SMS received: %s", data)

        # Create partial functions with httpx clients bound
        geocode = partial(nominatim_client.geocode, app.state.nominatim_httpx_client)
        get_directions = partial(valhalla_client.directions, app.state.valhalla_httpx_client)
        
        # Set up tools
        tools = [
            forecast_tool(
                app.state.weather_httpx_client, geocode, app.logger
            ),
            datetime_tool(geocode),
            navigation_tool(get_directions, geocode),
        ]
        
        # Set up initial messages with system prompt as dict
        messages = [Messages.System(settings.prompts.assistant).model_dump()]
        
        # Process the incoming SMS and generate a response
        response, _ = await app.state.assistant.step(messages, tools, data.payload.message)

        # Send the response back via SMS
        await send_sms(
            app.state.sms_gateway_client,
            response,
            data.payload.phone_number,
            app.logger,
        )

    weather_httpx_client = httpx.AsyncClient(
        base_url=settings.nws.api_url,
        headers={"User-Agent": settings.nws.user_agent},
        timeout=10.0,
        follow_redirects=True,
    )
    
    nominatim_httpx_client = httpx.AsyncClient(
        base_url=settings.nominatim.api_url,
        headers={"User-Agent": settings.nominatim.user_agent},
        timeout=10.0,
        follow_redirects=True,
    )
    
    valhalla_httpx_client = httpx.AsyncClient(
        base_url="https://valhalla1.openstreetmap.de",
        timeout=10.0,
        follow_redirects=True,
    )
    
    # Create the Assistant instance
    assistant = Assistant(settings.llm)
    
    # Create database connection factory and pool
    async def sqlite_connection() -> aiosqlite.Connection:
        return await aiosqlite.connect("conversations.db")
    
    db_pool = SQLiteConnectionPool(connection_factory=sqlite_connection)
    await init_database(db_pool)
    
    async with (
        create_sms_gateway_client(settings.sms.settler) as settler_sms_client,
        create_sms_gateway_client(settings.sms.nomad) as nomad_sms_client,
    ):
        await init_webhooks(
            gateway_client=settler_sms_client,
            registrar=app.register,
            route_prefix="/webhooks/settler",
            webhook_target_url=settings.sms.settler.webhook_target_url,
            on_delivered=on_delivered,
            on_received=on_received,
        )

        app.state.sms_gateway_client = settler_sms_client
        app.state.weather_httpx_client = weather_httpx_client
        app.state.nominatim_httpx_client = nominatim_httpx_client
        app.state.valhalla_httpx_client = valhalla_httpx_client
        app.state.assistant = assistant
        app.state.db_pool = db_pool
        try:
            yield
        finally:
            await weather_httpx_client.aclose()
            await nominatim_httpx_client.aclose()
            await valhalla_httpx_client.aclose()
            await db_pool.close()


app = Litestar(
    route_handlers=[
        health,
        test_sms,
        test_weather_hourly,
        test_weather_12hour,
        test_agent,
        test_geocoding,
        test_nav,
    ],
    lifespan=[lifespan],
    debug=settings.debug,
)
