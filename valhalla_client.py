from typing import Literal
import httpx
from schemas import Directions


TravelMode = Literal["drive", "walk", "bike", "transit"]


class ValhallaClient:
    def __init__(self):
        self.client = None
        self.base_url = "https://valhalla1.openstreetmap.de"

    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=10.0,
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()

    async def directions(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        mode: TravelMode = "drive",
    ) -> Directions:
        """
        Get directions between two points.

        Args:
            start: Tuple of (latitude, longitude) for start point
            end: Tuple of (latitude, longitude) for end point
            mode: Travel mode - "drive", "walk", "bike", or "transit"

        Returns:
            Directions object with parsed route information
        """
        # Map travel modes to Valhalla costing models
        costing_map = {
            "drive": "auto",
            "walk": "pedestrian",
            "bike": "bicycle",
            "transit": "multimodal",
        }

        costing = costing_map[mode]

        # Build request payload
        payload = {
            "locations": [
                {"lat": start[0], "lon": start[1]},
                {"lat": end[0], "lon": end[1]},
            ],
            "costing": costing,
            "units": "miles",  # Always use miles
        }

        # Make the request
        response = await self.client.post("/route", json=payload)
        response.raise_for_status()

        # Parse the response
        data = response.json()
        trip = data.get("trip", {})

        return Directions.from_valhalla_response(trip)
