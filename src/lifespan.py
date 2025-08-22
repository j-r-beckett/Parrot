from contextlib import asynccontextmanager
from typing import AsyncGenerator
from functools import partial
from litestar import Litestar
from mirascope import Messages
import httpx

from src.config import settings
from src.assistant.llm import Assistant
from src.database.manager import create_db_pool
from src.clients.sms_gateway import create_sms_gateway_client, send_sms, init_webhooks
from src.schemas.sms import SmsDelivered, SmsReceived
from src.assistant.tools.weather import forecast_tool
from src.assistant.tools.datetime import datetime_tool
from src.assistant.tools.navigation import navigation_tool
import src.clients.nominatim as nominatim_client
import src.clients.valhalla as valhalla_client


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
    db_pool = await create_db_pool()
    
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