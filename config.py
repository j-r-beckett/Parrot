from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal
from decimal import Decimal


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    debug: bool = False

    sms_gateway_url: str = Field(...)
    sms_gateway_username: str = Field(...)
    sms_gateway_password: str = Field(...)

    anthropic_api_key: str = Field(...)
    anthropic_max_tokens: int = 1024
    anthropic_model: str = "claude-sonnet-4-20250514"

    input_token_cost: Decimal = Decimal("0.000003")
    cache_miss_input_token_cost: Decimal = Decimal("0.00000375")
    cache_hit_input_token_cost: Decimal = Decimal("0.0000003")
    output_token_cost: Decimal = Decimal("0.000015")


settings = AppSettings()
