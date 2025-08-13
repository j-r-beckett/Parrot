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
    temperature: int  # Fahrenheit
    precipitation_probability: int  # Percentage
    description: str  # Human readable description of the forecast

    @classmethod
    def from_nws_period(
        cls, period: dict, verbosity: Literal["short", "detailed"]
    ) -> "Forecast":
        """Create a Forecast from NWS API period data

        Args:
            period: NWS API period object
            verbosity: "short" for shortForecast, "detailed" for detailedForecast
        """
        # Convert ISO 8601 to US style time
        dt = datetime.fromisoformat(period["startTime"])
        time_str = dt.strftime("%b %d, %-I:%M %p")

        precip_prob = period["probabilityOfPrecipitation"]["value"]

        description = period[f"{verbosity}Forecast"]

        return cls(
            time=time_str,
            temperature=period["temperature"],
            precipitation_probability=precip_prob,
            description=description,
        )


class HourlyForecast(BaseModel):
    """Schema for hourly forecast data from NWS"""

    forecasts: list[Forecast]

    @classmethod
    def from_nws_response(cls, periods: list) -> "HourlyForecast":
        """Create HourlyForecast from NWS API response periods"""
        forecasts = [
            Forecast.from_nws_period(period, verbosity="short") for period in periods
        ]
        return cls(forecasts=forecasts)


class SemidiurnalForecast(BaseModel):
    """Schema for 12-hour (semidiurnal) forecast data from NWS"""

    forecasts: list[Forecast]

    @classmethod
    def from_nws_response(cls, periods: list) -> "SemidiurnalForecast":
        """Create SemidiurnalForecast from NWS API response periods"""
        forecasts = [
            Forecast.from_nws_period(period, verbosity="detailed") for period in periods
        ]
        return cls(forecasts=forecasts)
