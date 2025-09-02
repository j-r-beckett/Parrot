from contextlib import asynccontextmanager
from typing import AsyncGenerator, cast
import asyncio
from litestar import Litestar
import httpx

from config import settings
from database.manager import create_db_pool
from integrations.sms_proxy import create_sms_proxy_client, register_and_maintain
from integrations.citi_bike import CitiBikeClient


@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None, None]:
    weather_httpx_client = httpx.AsyncClient(
        base_url=settings.nws.api_url,
        headers={"User-Agent": cast(str, settings.nws.user_agent)},
        timeout=10.0,
        follow_redirects=True,
    )

    nominatim_httpx_client = httpx.AsyncClient(
        base_url=settings.nominatim.api_url,
        headers={"User-Agent": cast(str, settings.nominatim.user_agent)},
        timeout=10.0,
        follow_redirects=True,
    )

    valhalla_httpx_client = httpx.AsyncClient(
        base_url="https://valhalla1.openstreetmap.de",
        timeout=10.0,
        follow_redirects=True,
    )

    # Create database connection factory and pool
    logger = app.logger
    if logger is None:
        raise RuntimeError("App logger is None")
    db_pool = await create_db_pool(settings.interactions_db, logger)

    # Create clients
    sms_proxy_client = create_sms_proxy_client(settings.sms_proxy_url)

    # Create and initialize CitiBike client
    citi_bike_httpx_client = CitiBikeClient.create_httpx_client()
    citi_bike_client = CitiBikeClient(citi_bike_httpx_client, logger)
    await citi_bike_client.__aenter__()

    # Start sms-proxy registration task
    if settings.ring != "local":
        registration_task = asyncio.create_task(
            register_and_maintain(
                sms_proxy_client,
                client_id=f"parrot-hub-{settings.ring}",
                webhook_url=f"{settings.webhook.base_url}/webhook/sms-proxy",
                ring=settings.ring,
                logger=logger,
                on_received=True,  # We want to receive SMS
                on_delivered=True,  # We want delivery notifications
            )
        )
    else:
        registration_task = None

    # Store clients in app state
    app.state.sms_proxy_client = sms_proxy_client
    app.state.weather_httpx_client = weather_httpx_client
    app.state.nominatim_httpx_client = nominatim_httpx_client
    app.state.valhalla_httpx_client = valhalla_httpx_client
    app.state.citi_bike_client = citi_bike_client
    app.state.db_pool = db_pool

    try:
        yield
    finally:
        if registration_task:
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
        await citi_bike_client.__aexit__(None, None, None)
        await citi_bike_httpx_client.aclose()
        await db_pool.close()
