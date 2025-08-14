from typing import Literal
from datetime import datetime
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


class Forecast(BaseModel):
    """Individual forecast period data"""

    time: str  # Human readable time
    temperature: str  # Degrees Fahrenheit
    precipitation_probability: str  # Percentage
    description: str  # Human readable description of the forecast

    @classmethod
    def from_hourly_period(cls, period: dict) -> "Forecast":
        precip_prob = f"{period['probabilityOfPrecipitation']['value']}%"
        temperature = f"{period['temperature']}F"

        raw_time = datetime.fromisoformat(period["startTime"])
        time = raw_time.strftime("%A %b %d, %-I:%M %p")
        description = period["shortForecast"]

        return cls(
            time=time,
            temperature=temperature,
            precipitation_probability=precip_prob,
            description=description,
        )

    @classmethod
    def from_12hour_period(cls, period: dict) -> "Forecast":
        precip_prob = f"{period['probabilityOfPrecipitation']['value']}%"
        temperature = f"{period['temperature']}F"

        raw_time = datetime.fromisoformat(period["startTime"])
        time = f"{raw_time.strftime('%b %d')}, {period['name']}"
        description = period["detailedForecast"]

        return cls(
            time=time,
            temperature=temperature,
            precipitation_probability=precip_prob,
            description=description,
        )


class HourlyForecast(BaseModel):
    """Schema for hourly forecast data from NWS"""

    forecasts: list[Forecast]

    @classmethod
    def from_nws_response(cls, periods: list) -> "HourlyForecast":
        """Create HourlyForecast from NWS API response periods"""
        forecasts = [Forecast.from_hourly_period(period) for period in periods]
        return cls(forecasts=forecasts)


class TwelveHourForecast(BaseModel):
    """Schema for 12-hour forecast data from NWS"""

    forecasts: list[Forecast]

    @classmethod
    def from_nws_response(cls, periods: list) -> "TwelveHourForecast":
        """Create TwelveHourForecast from NWS API response periods"""
        forecasts = [Forecast.from_12hour_period(period) for period in periods]
        return cls(forecasts=forecasts)
