import httpx
import asyncio
from typing import Optional, Callable, Awaitable, Any
from litestar.types.protocols import Logger
import uuid


def create_sms_proxy_client(url: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=url,
        timeout=5.0,
    )


async def send_sms(
    client: httpx.AsyncClient, msg: str, phone_numbers: list[str], logger: Logger
) -> None:
    msg_id = str(uuid.uuid4())
    body = {
        "message": msg,
        "phone_numbers": phone_numbers,
    }
    response = await client.post("/send", json=body)
    response.raise_for_status()
    logger.info(f"SMS message submitted to sms-proxy (id: {msg_id})")


async def register_and_maintain(
    client: httpx.AsyncClient,
    client_id: str,
    webhook_url: str,
    ring: str,
    logger: Logger,
    on_received: bool = False,
    on_delivered: bool = False,
) -> None:
    """Register with sms-proxy and maintain registration with periodic keep-alive."""
    registration = {
        "id": client_id,
        "webhook_url": webhook_url,
        "ring": ring,
        "sms_received": on_received,
        "sms_delivered": on_delivered,
        "sms_sent": False,
        "sms_failed": False,
    }

    try:
        while True:
            try:
                response = await client.post("/register", json=registration)
                response.raise_for_status()
                logger.debug(f"Registered with sms-proxy as {client_id}")
            except Exception as e:
                logger.error(f"Failed to register with sms-proxy: {e}")

            # Re-register every 5 seconds (sms-proxy expires clients after 60s)
            await asyncio.sleep(5)
    except asyncio.CancelledError:
        logger.info(f"Stopping sms-proxy registration for {client_id}")
        raise
