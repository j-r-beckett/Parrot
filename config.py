from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    debug: bool = False

    sms_gateway_url: str = Field(...)
    sms_gateway_username: str = Field(...)
    sms_gateway_password: str = Field(...)

    active_llm: Literal["claude-sonnet-4"] = "claude-sonnet-4"

    anthropic_api_key: str = Field(...)

    nws_api_url: str = Field(default="https://api.weather.gov")
    nws_user_agent: str = Field(default="clanker-0.1")

    provider: str = "anthropic"
    model_name: str = "claude-sonnet-4-20250514"


settings = AppSettings()
