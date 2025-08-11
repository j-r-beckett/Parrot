from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    debug: bool = False

    sms_gateway_url: str = Field(...)
    sms_gateway_username: str = Field(...)
    sms_gateway_password: str = Field(...)


settings = AppSettings()
