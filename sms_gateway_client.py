from config import AppSettings
import httpx
from typing import Tuple, Any
from litestar.status_codes import HTTP_200_OK
from logging import Logger
import uuid


class SmsGatewayClient:
    def __init__(self, settings: AppSettings):
        self.client = None
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
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()

    async def send_sms(self, msg: str, phone_number: str, logger: Logger):
        msg_id = str(uuid.uuid4())
        body = {
            "id": msg_id,
            "textMessage": {"text": msg},
            "phoneNumbers": [phone_number],
        }
        response = await self.client.post("/message", json=body)
        response.raise_for_status()
        logger.info("SMS message submitted to gateway")

    async def health(self) -> Tuple[bool, Any]:
        try:
            response = await self.client.get("/health")
            if response.content:
                return (response.status_code == HTTP_200_OK, response.json())
            response.raise_for_status()
        except Exception as e:
            return (False, e)
