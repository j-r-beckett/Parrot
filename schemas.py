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
    id: str
    payload: SmsDeliveredPayload


class SmsReceivedPayload(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    message: str
    received_at: str
    message_id: str
    phone_number: str


class SmsReceived(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    device_id: str
    id: str
    payload: SmsReceivedPayload


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


class Directions(BaseModel):
    """Schema for Valhalla directions response"""

    steps: list[str]  # List of instruction strings
    total_time: str  # Formatted as "n hours, m minutes" or "m minutes"
    total_distance: str  # Total distance in miles

    @classmethod
    def from_valhalla_response(cls, trip: dict) -> "Directions":
        """Create Directions from Valhalla API response"""
        steps = []

        # Process each maneuver in the legs
        for leg in trip.get("legs", []):
            for maneuver in leg.get("maneuvers", []):
                # Combine instruction with verbal_post_transition_instruction
                instruction = maneuver.get("instruction", "")
                verbal_post = maneuver.get("verbal_post_transition_instruction", "")
                if verbal_post:
                    full_instruction = f"{instruction} {verbal_post}"
                else:
                    full_instruction = instruction

                steps.append(full_instruction)

        # Get total time and distance from summary
        summary = trip.get("summary", {})
        total_time_seconds = summary.get("time", 0)
        total_time_formatted = cls._format_time(total_time_seconds)
        total_distance = summary.get("length", 0)

        return cls(
            steps=steps,
            total_time=total_time_formatted,
            total_distance=f"{total_distance} miles",
        )

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format seconds into 'n hours, m minutes' or 'm minutes'"""
        total_minutes = int(seconds / 60)
        hours = total_minutes // 60
        minutes = total_minutes % 60

        if hours > 0:
            if minutes > 0:
                return f"{hours} hours, {minutes} minutes"
            else:
                return f"{hours} hours"
        else:
            return f"{minutes} minutes"
