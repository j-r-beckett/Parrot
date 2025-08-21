from decorators import add_docstring
from typing import Literal, Callable, Awaitable
from schemas import Directions


def navigation_tool(
    get_directions: Callable[[tuple[float, float], tuple[float, float], Literal["drive", "walk", "bike", "transit"]], Awaitable[Directions]], 
    geocode: Callable[[str], Awaitable[tuple[float, float]]]
):
    description = "Returns turn-by-turn navigation directions between two locations formatted as JSON."

    @add_docstring(description)
    async def navigate(
        start: str, 
        destination: str, 
        mode: Literal["drive", "walk", "bike", "transit"] = "drive"
    ) -> str:
        # Geocode the start and destination locations
        start_coords = await geocode(start)
        dest_coords = await geocode(destination)
        
        # Get directions
        directions = await get_directions(
            start_coords,
            dest_coords,
            mode
        )
        
        return directions.model_dump_json()

    return navigate