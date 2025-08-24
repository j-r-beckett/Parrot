import httpx
import asyncio
from typing import Optional, Callable, Awaitable, Any
from logging import Logger
import uuid


def create_smsgap_client(url: str) -> httpx.AsyncClient:
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
    logger.info(f"SMS message submitted to smsgap (id: {msg_id})")


async def register_and_maintain(
    client: httpx.AsyncClient,
    client_id: str,
    webhook_url: str,
    logger: Logger,
    on_received: bool = False,
    on_delivered: bool = False,
) -> None:
    """Register with smsgap and maintain registration with periodic keep-alive."""
    registration = {
        "id": client_id,
        "webhook_url": webhook_url,
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
                logger.debug(f"Registered with smsgap as {client_id}")
            except Exception as e:
                logger.error(f"Failed to register with smsgap: {e}")
            
            # Re-register every 45 seconds (smsgap expires clients after 60s)
            await asyncio.sleep(45)
    except asyncio.CancelledError:
        logger.info(f"Stopping smsgap registration for {client_id}")
        raise