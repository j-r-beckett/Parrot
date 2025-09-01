import math
from pydantic_ai import Agent
from pydantic_ai.tools import RunContext
from assistant.dependencies import AssistantDependencies
import integrations.valhalla as valhalla_client


def euclidean_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate Euclidean distance between two lat/lon points."""
    return math.sqrt((lat1 - lat2) ** 2 + (lon1 - lon2) ** 2)


def register_citi_bike_tool(agent: Agent[AssistantDependencies, str]) -> None:
    """Register Citi Bike tool on the agent."""

    @agent.tool
    async def find_citibike_directions(
        ctx: RunContext[AssistantDependencies], location: str
    ) -> str:
        """Find the closest Citi Bike station to a location and return walking directions to it."""
        # Step 1: Geocode the location
        lat, lon = await ctx.deps.geocode(location)

        # Step 2: Get Citi Bike stations
        stations = await ctx.deps.citi_bike_client.get_stations()

        # Step 3: Sort stations by Euclidean distance and get the closest
        closest_station = min(
            stations,
            key=lambda station: euclidean_distance(lat, lon, station.lat, station.lon),
        )

        # Step 4: Get walking directions to the closest station
        directions = await valhalla_client.directions(
            ctx.deps.valhalla_client,
            (lat, lon),
            (closest_station.lat, closest_station.lon),
            "walk",
        )

        return directions.model_dump_json()
