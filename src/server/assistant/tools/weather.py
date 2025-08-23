import clients.weather as weather_client
from utils.decorators import add_docstring
from logging import Logger
from typing import Callable, Awaitable
import httpx


def forecast_tool(
    weather_httpx_client: httpx.AsyncClient, 
    geocode: Callable[[str], Awaitable[tuple[float, float]]], 
    logger: Logger
):
    description = "Returns a weather forecast formatted as JSON."

    @add_docstring(description)
    async def forecast(location: str) -> str:
        lat, lon = await geocode(location)
        forecast = await weather_client.twelve_hour_forecast(weather_httpx_client, logger, lat, lon)
        return forecast.model_dump_json()

    return forecast
