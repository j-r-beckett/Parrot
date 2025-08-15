from valhalla_client import ValhallaClient
from nominatim_client import NominatimClient
from decorators import add_docstring
from typing import Literal


def navigation_tool(
    valhalla_client: ValhallaClient, nominatim_client: NominatimClient
):
    description = "Returns turn-by-turn navigation directions between two locations formatted as JSON."

    @add_docstring(description)
    async def navigate(
        start: str, 
        destination: str, 
        mode: Literal["drive", "walk", "bike", "transit"] = "drive"
    ) -> str:
        # Geocode the start and destination locations
        start_coords = await nominatim_client.geocode(start)
        dest_coords = await nominatim_client.geocode(destination)
        
        # Get directions
        directions = await valhalla_client.directions(
            start=start_coords,
            end=dest_coords,
            mode=mode
        )
        
        return directions.model_dump_json()

    return navigate