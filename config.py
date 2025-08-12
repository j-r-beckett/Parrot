from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    debug: bool = False

    sms_gateway_url: str = Field(...)
    sms_gateway_username: str = Field(...)
    sms_gateway_password: str = Field(...)

    anthropic_api_key: str = Field(...)


settings = AppSettings()
