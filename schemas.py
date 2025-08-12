from typing import Literal
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

WebhookEventType = Literal["sms:received", "sms:sent", "sms:delivered", "sms:failed"]


class SmsDeliveredPayload(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    
    delivered_at: str
    message_id: str
    phone_number: str


class SmsDelivered(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    
    device_id: str
    event: WebhookEventType
    id: str
    payload: SmsDeliveredPayload
    webhook_id: str
