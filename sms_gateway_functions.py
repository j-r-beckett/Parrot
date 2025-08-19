from dynaconf.utils.boxing import DynaBox
import httpx
from typing import Tuple, Any, List, Dict
from litestar.status_codes import HTTP_200_OK
from logging import Logger
import uuid
from schemas import WebhookEventType


async def send_sms(
    client: httpx.AsyncClient, msg: str, phone_number: str, logger: Logger
) -> None:
    msg_id = str(uuid.uuid4())
    body = {
        "id": msg_id,
        "textMessage": {"text": msg},
        "phoneNumbers": [phone_number],
    }
    response = await client.post("/message", json=body)
    response.raise_for_status()
    logger.info("SMS message submitted to gateway")


async def gateway_health(client: httpx.AsyncClient) -> Tuple[bool, Any]:
    try:
        response = await client.get("/health")
        if response.content:
            return (response.status_code == HTTP_200_OK, response.json())
        response.raise_for_status()
        return (False, "Unknown failure")
    except Exception as e:
        return (False, e)


async def webhook_health(
    client: httpx.AsyncClient, expected_events: Dict[WebhookEventType, str]
) -> Tuple[bool, Any]:
    current_hooks = [event for _, event in await _active_webhooks(client)]
    if not set(expected_events.keys()).issubset(current_hooks):
        return (
            False,
            f"Expected webhooks: {list(expected_events)}, actual webhooks: {current_hooks}",
        )
    return (True, current_hooks)


async def init_webhooks(
    client: httpx.AsyncClient, events: Dict[WebhookEventType, str]
) -> None:
    # first clear any existing webhooks
    for id, _ in await _active_webhooks(client):
        response = await client.delete(f"/webhooks/{id}")
        response.raise_for_status()

    # then set new ones
    for event_type, route in events.items():
        # Proxy port 8081 -> 8000 (this app's port)
        # With adb, that's `adb reverse tcp:8081 tcp:8000`
        base_url = f"http://127.0.0.1:8081{route}"
        response = await client.post(
            "/webhooks",
            json={"url": base_url, "event": event_type},
        )
        response.raise_for_status()


async def _active_webhooks(client: httpx.AsyncClient) -> List[Tuple[str, str]]:
    response = await client.get("/webhooks")
    response.raise_for_status()
    return [(hook["id"], hook["event"]) for hook in response.json()]


def create_sms_client(sms_config: DynaBox) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=sms_config.url,
        auth=(
            sms_config.username,
            sms_config.password,
        ),
        timeout=5.0,
    )