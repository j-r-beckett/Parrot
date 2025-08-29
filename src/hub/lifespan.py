from contextlib import asynccontextmanager
from typing import AsyncGenerator
import asyncio
from litestar import Litestar
import httpx

from config import settings
from assistant.llm import Assistant
from database.manager import create_db_pool
from clients.sms_proxy import create_sms_proxy_client, register_and_maintain


@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None, None]:
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
    db_pool = await create_db_pool(settings.conversations_db, app.logger)

    # Create clients
    sms_proxy_client = create_sms_proxy_client(settings.sms_proxy_url)

    # Start sms-proxy registration task
    registration_task = asyncio.create_task(
        register_and_maintain(
            sms_proxy_client,
            client_id=f"parrot-hub-{settings.ring}",
            webhook_url=f"{settings.webhook.base_url}/webhook/sms-proxy",
            ring=settings.ring,
            logger=app.logger,
            on_received=True,  # We want to receive SMS
            on_delivered=True,  # We want delivery notifications
        )
    )

    # Store clients in app state
    app.state.sms_proxy_client = sms_proxy_client
    app.state.weather_httpx_client = weather_httpx_client
    app.state.nominatim_httpx_client = nominatim_httpx_client
    app.state.valhalla_httpx_client = valhalla_httpx_client
    app.state.assistant = assistant
    app.state.db_pool = db_pool

    try:
        yield
    finally:
        # Cancel registration task
        registration_task.cancel()
        try:
            await registration_task
        except asyncio.CancelledError:
            pass

        # Close all clients
        await sms_proxy_client.aclose()
        await weather_httpx_client.aclose()
        await nominatim_httpx_client.aclose()
        await valhalla_httpx_client.aclose()
        await db_pool.close()
