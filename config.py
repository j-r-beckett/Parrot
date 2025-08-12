from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    debug: bool = False

    sms_gateway_url: str = Field(...)
    sms_gateway_username: str = Field(...)
    sms_gateway_password: str = Field(...)

    anthropic_api_key: str = Field(...)
    anthropic_max_tokens: int = 1024
    anthropic_model: str = "claude-sonnet-4-20250514"


settings = AppSettings()
