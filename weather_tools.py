from weather_client import WeatherClient
from nominatim_client import NominatimClient
from decorators import add_docstring
from logging import getLogger

logger = getLogger(__name__)


def forecast_tool(weather_client: WeatherClient, nominatim_client: NominatimClient):
    description = "Returns a weather forecast formatted as JSON."

    @add_docstring(description)
    async def forecast(location: str) -> str:
        lat, lon = await nominatim_client.geocode(location)
        forecast = await weather_client.twelveHour_forecast(logger, lat, lon)
        return forecast.model_dump_json()

    return forecast
