import httpx
from logging import Logger
from schemas import HourlyForecast, TwelveHourForecast


async def _get_grid_info(
    client: httpx.AsyncClient, lat: float, lon: float
) -> tuple[str, int, int]:
    """Get grid information from coordinates"""
    response = await client.get(f"/points/{lat},{lon}")

    if response.status_code == 404:
        raise ValueError(
            f"No forecast data for coordinates {lat},{lon} (ocean or outside US?)"
        )

    response.raise_for_status()

    properties = response.json()["properties"]

    return properties["gridId"], properties["gridX"], properties["gridY"]


async def hourly_forecast(
    client: httpx.AsyncClient, logger: Logger, lat: float, lon: float
) -> HourlyForecast:
    grid_id, grid_x, grid_y = await _get_grid_info(client, lat, lon)

    forecast_response = await client.get(
        f"/gridpoints/{grid_id}/{grid_x},{grid_y}/forecast/hourly"
    )

    forecast_response.raise_for_status()
    forecast_data = forecast_response.json()

    return HourlyForecast.from_nws_response(forecast_data["properties"]["periods"])


async def twelve_hour_forecast(
    client: httpx.AsyncClient, logger: Logger, lat: float, lon: float
) -> TwelveHourForecast:
    grid_id, grid_x, grid_y = await _get_grid_info(client, lat, lon)

    forecast_response = await client.get(
        f"/gridpoints/{grid_id}/{grid_x},{grid_y}/forecast"
    )

    forecast_response.raise_for_status()
    forecast_data = forecast_response.json()

    logger.info("Resp: %s", forecast_response.json()["properties"]["periods"][0])

    return TwelveHourForecast.from_nws_response(
        forecast_data["properties"]["periods"]
    )
