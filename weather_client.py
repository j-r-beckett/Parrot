from config import AppSettings
import httpx
import json
from typing import Any
from logging import Logger
from schemas import HourlyForecast, SemidiurnalForecast


class WeatherClient:
    def __init__(self, settings: AppSettings):
        self.client = None
        self.settings = settings

    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            base_url=self.settings.nws_api_url,
            headers={"User-Agent": self.settings.nws_user_agent},
            timeout=10.0,
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()

    async def _get_grid_info(self, lat: float, lon: float) -> tuple[str, int, int]:
        """Get grid information from coordinates"""
        response = await self.client.get(f"/points/{lat},{lon}")

        if response.status_code == 404:
            raise ValueError(
                f"No forecast data for coordinates {lat},{lon} (ocean or outside US?)"
            )

        response.raise_for_status()

        properties = response.json()["properties"]

        return properties["gridId"], properties["gridX"], properties["gridY"]

    async def hourly_forecast(
        self, logger: Logger, lat: float, lon: float
    ) -> HourlyForecast:
        grid_id, grid_x, grid_y = await self._get_grid_info(lat, lon)

        forecast_response = await self.client.get(
            f"/gridpoints/{grid_id}/{grid_x},{grid_y}/forecast/hourly"
        )

        forecast_response.raise_for_status()
        forecast_data = forecast_response.json()

        return HourlyForecast.from_nws_response(forecast_data["properties"]["periods"])

    async def semidiurnal_forecast(
        self, logger: Logger, lat: float, lon: float
    ) -> SemidiurnalForecast:
        grid_id, grid_x, grid_y = await self._get_grid_info(lat, lon)

        forecast_response = await self.client.get(
            f"/gridpoints/{grid_id}/{grid_x},{grid_y}/forecast"
        )

        forecast_response.raise_for_status()
        forecast_data = forecast_response.json()

        return SemidiurnalForecast.from_nws_response(
            forecast_data["properties"]["periods"]
        )
