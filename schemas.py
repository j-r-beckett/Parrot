from typing import Literal
from pydantic import BaseModel, Field

WebhookEventType = Literal["sms:received", "sms:sent", "sms:delivered", "sms:failed"]


class SmsDeliveredPayload(BaseModel):
    delivered_at: str = Field(alias="deliveredAt")
    message_id: str = Field(alias="messageId")
    phone_number: str = Field(alias="phoneNumber")


class SmsDelivered(BaseModel):
    device_id: str = Field(alias="deviceId")
    event: WebhookEventType
    id: str
    payload: SmsDeliveredPayload
    webhook_id: str = Field(alias="webhookId")
