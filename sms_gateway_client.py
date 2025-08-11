from config import AppSettings
import httpx
from typing import Tuple, Any, List, Dict
from litestar.status_codes import HTTP_200_OK
from logging import Logger
import uuid
from schemas import WebhookEventType


class SmsGatewayClient:
    def __init__(
        self, settings: AppSettings, webhook_events: Dict[WebhookEventType, str]
    ):
        self.client = None
        self.webhook_events = webhook_events
        self.settings = settings

    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            base_url=self.settings.sms_gateway_url,
            auth=(
                self.settings.sms_gateway_username,
                self.settings.sms_gateway_password,
            ),
            timeout=5.0,
        )

        await self._init_webhooks(self.webhook_events)

        return self

    async def __aexit__(self, *args):
        await self.client.aclose()

    async def send_sms(self, msg: str, phone_number: str, logger: Logger) -> None:
        msg_id = str(uuid.uuid4())
        body = {
            "id": msg_id,
            "textMessage": {"text": msg},
            "phoneNumbers": [phone_number],
        }
        response = await self.client.post("/message", json=body)
        response.raise_for_status()
        logger.info("SMS message submitted to gateway")

    async def gateway_health(self) -> Tuple[bool, Any]:
        try:
            response = await self.client.get("/health")
            if response.content:
                return (response.status_code == HTTP_200_OK, response.json())
            response.raise_for_status()
            return (False, "Unknown failure")
        except Exception as e:
            return (False, e)

    async def webhook_health(self) -> Tuple[bool, Any]:
        current_hooks = [event for _, event in await self._active_webhooks()]
        if not set(set(self.webhook_events.keys())).issubset(current_hooks):
            return (
                False,
                f"Expected webhooks: {list(self.webhook_events)}, actual webhooks: {current_hooks}",
            )
        return (True, current_hooks)

    async def _init_webhooks(self, events: Dict[WebhookEventType, str]) -> None:
        # first clear any existing webhooks
        for id, _ in await self._active_webhooks():
            response = await self.client.delete(f"/webhooks/{id}")
            response.raise_for_status()

        # then set new ones
        for event_type, route in events.items():
            # Proxy port 8081 -> 8000 (this app's port)
            # With adb, that's `adb reverse tcp:8081 tcp:8000`
            base_url = f"http://127.0.0.1:8081{route}"
            response = await self.client.post(
                "/webhooks",
                json={"url": base_url, "event": event_type},
            )
            response.raise_for_status()

    async def _active_webhooks(self) -> List[Tuple[str, str]]:
        response = await self.client.get("/webhooks")
        response.raise_for_status()
        return [
            (hook["id"], hook["event"]) for hook in response.json()
        ]  # schemas are for suckers
