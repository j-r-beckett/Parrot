from litestar import Request, post
import httpx
from typing import Callable, Optional, Any, Awaitable
from schemas import SmsDelivered, SmsReceived
import uuid
from dynaconf.utils.boxing import DynaBox
from logging import Logger


def create_sms_gateway_client(sms_config: DynaBox) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=sms_config.url,
        auth=(
            sms_config.username,
            sms_config.password,
        ),
        timeout=5.0,
    )


async def send_sms(
    gateway_client: httpx.AsyncClient, msg: str, phone_number: str, logger: Logger
) -> None:
    msg_id = str(uuid.uuid4())
    body = {
        "id": msg_id,
        "textMessage": {"text": msg},
        "phoneNumbers": [phone_number],
    }
    response = await gateway_client.post("/message", json=body)
    response.raise_for_status()
    logger.info("SMS message submitted to gateway")


async def init_webhooks(
    gateway_client: httpx.AsyncClient,
    registrar: Callable[[Any], None],
    route_prefix: str,
    webhook_target_url: str,
    on_delivered: Optional[Callable[[SmsDelivered], Awaitable[None]]] = None,
    on_received: Optional[Callable[[Any], Awaitable[None]]] = None,
) -> None:
    # get active webhooks
    get_webhooks_response = await gateway_client.get("/webhooks")
    get_webhooks_response.raise_for_status()
    active_webhooks = [hook["id"] for hook in get_webhooks_response.json()]

    # delete active webhooks
    for webhook_id in active_webhooks:
        delete_webhook_response = await gateway_client.delete(f"/webhooks/{webhook_id}")
        delete_webhook_response.raise_for_status()

    # set up webhook endpoints; accumulate a list of webhook events to register
    events = []

    if on_delivered:
        events.append(("sms:delivered", f"{route_prefix}/delivered"))

        @post(f"{route_prefix}/delivered")
        async def hook(request: Request, data: SmsDelivered) -> str:
            await on_delivered(data)
            return ""

        registrar(hook)

    if on_received:
        events.append(("sms:received", f"{route_prefix}/received"))

        @post(f"{route_prefix}/received")
        async def hook(request: Request, data: SmsReceived) -> str:
            import asyncio

            asyncio.create_task(on_received(data))
            return ""

        registrar(hook)

    # register webhooks
    for event, route in events:
        create_webhook_response = await gateway_client.post(
            "/webhooks", json={"url": f"{webhook_target_url}{route}", "event": event}
        )
        create_webhook_response.raise_for_status()
