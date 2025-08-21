import weather_client
from nominatim_client import NominatimClient
from decorators import add_docstring
from logging import Logger
import httpx


def forecast_tool(
    weather_httpx_client: httpx.AsyncClient, nominatim_client: NominatimClient, logger: Logger
):
    description = "Returns a weather forecast formatted as JSON."

    @add_docstring(description)
    async def forecast(location: str) -> str:
        lat, lon = await nominatim_client.geocode(location)
        forecast = await weather_client.twelve_hour_forecast(weather_httpx_client, logger, lat, lon)
        return forecast.model_dump_json()

    return forecast
