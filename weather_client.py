from config import AppSettings
import httpx
from typing import Any
from logging import Logger


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

    async def get_temperature(self, logger: Logger, lat: float, lon: float) -> float:
        # Step 1: Get grid information from coordinates
        points_response = await self.client.get(f"/points/{lat},{lon}")

        if points_response.status_code == 404:
            raise ValueError(
                f"No forecast data for coordinates {lat},{lon} (might be ocean or outside US)"
            )

        # Write points response to file
        with open("/home/jimmy/repos/ludd/points.txt", "w") as f:
            f.write(points_response.text)
        logger.info("Wrote points response to points.txt")

        points_response.raise_for_status()
        points_data = points_response.json()

        # Extract grid coordinates
        properties = points_data.get("properties", {})
        grid_id = properties.get("gridId")
        grid_x = properties.get("gridX")
        grid_y = properties.get("gridY")

        if not all([grid_id, grid_x is not None, grid_y is not None]):
            raise ValueError(
                f"Missing grid data in points response: gridId={grid_id}, gridX={grid_x}, gridY={grid_y}"
            )

        # Step 2: Get hourly forecast for the grid point
        forecast_response = await self.client.get(
            f"/gridpoints/{grid_id}/{grid_x},{grid_y}/forecast/hourly"
        )

        # Write forecast response to file
        with open("/home/jimmy/repos/ludd/forecast.txt", "w") as f:
            f.write(forecast_response.text)
        logger.info("Wrote forecast response to forecast.txt")

        # Step 3: Get 12-hour forecast (daily/nightly periods)
        forecast_12_response = await self.client.get(
            f"/gridpoints/{grid_id}/{grid_x},{grid_y}/forecast"
        )

        # Write 12-hour forecast response to file
        with open("/home/jimmy/repos/ludd/forecast_12.txt", "w") as f:
            f.write(forecast_12_response.text)
        logger.info("Wrote 12-hour forecast response to forecast_12.txt")

        if forecast_response.status_code == 404:
            raise ValueError(
                f"No forecast data for grid point {grid_id}/{grid_x},{grid_y}"
            )
        elif forecast_response.status_code == 500:
            raise ValueError(
                f"NWS API error for grid point {grid_id}/{grid_x},{grid_y} (possibly during forecast update, try again in a minute)"
            )

        forecast_response.raise_for_status()
        forecast_data = forecast_response.json()

        # Extract temperature from first period (current/nearest hour)
        periods = forecast_data.get("properties", {}).get("periods", [])

        if not periods:
            raise ValueError("No forecast periods available in response")

        first_period = periods[0]
        temperature = first_period.get("temperature")

        if temperature is None:
            raise ValueError(
                f"No temperature data in first forecast period: {first_period}"
            )

        return float(temperature)
