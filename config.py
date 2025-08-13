from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class ClaudeLlmConfig(BaseModel):
    short_name: Literal["claude-sonnet-4"] = "claude-sonnet-4"
    model_name: str = "claude-sonnet-4-20250514"  # Claude Sonnet 4
    api_key: str
    max_tokens: int = 1024


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    debug: bool = False

    sms_gateway_url: str = Field(...)
    sms_gateway_username: str = Field(...)
    sms_gateway_password: str = Field(...)

    active_llm: Literal["claude-sonnet-4"] = "claude-sonnet-4"

    anthropic_api_key: str = Field(...)

    nws_api_url: str = Field(default="https://api.weather.gov")
    nws_user_agent: str = Field(default="ludd-0.1")

    @property
    def llm_config(self) -> ClaudeLlmConfig:
        if self.active_llm == "claude-sonnet-4":
            return ClaudeLlmConfig(api_key=self.anthropic_api_key)
        else:
            raise ValueError(f"Unsupported LLM: {self.active_llm}")


settings = AppSettings()
