import math
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.tools import RunContext
from assistant.dependencies import AssistantDependencies
from assistant.tool_wrapper import safe_tool
from typing import List, Optional
from integrations.citi_bike import Station


class CitiBikeStationResult(BaseModel):
    num_ebikes: int
    num_bikes: int
    address: str
    distance_miles: float


def euclidean_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate Euclidean distance between two lat/lon points."""
    return math.sqrt((lat1 - lat2) ** 2 + (lon1 - lon2) ** 2)


def register_citi_bike_tool(agent: Agent[AssistantDependencies, str]) -> None:
    """Register Citi Bike tool on the agent."""

    @agent.tool
    @safe_tool
    async def find_citibike_stations(
        ctx: RunContext[AssistantDependencies], location: str
    ) -> List[CitiBikeStationResult]:
        """Find the closest Citi bake stations to the user's location. It returns the closest station with ebikes but no regular bikes (which offers ebikes at regular bike prices), the closest station with ebikes, and the closest station with regular bikes. Some of these stations may be the same (the closest station may have both ebikes and regular bikes, for example), so it deduplicates."""
        # Step 1: Geocode the location
        lat, lon = await ctx.deps.geocode(location)

        # Step 2: Get and sort stations by distance
        all_stations = await ctx.deps.citi_bike_client.get_stations()
        stations_by_distance = sorted(
            all_stations,
            key=lambda station: euclidean_distance(lat, lon, station.lat, station.lon),
        )

        # Step 3: Find the three types of stations
        ebike_station: Optional[Station] = None  # closest with ≥1 ebike
        bike_station: Optional[Station] = None  # closest with ≥1 regular bike
        free_station: Optional[Station] = (
            None  # closest with ≥1 ebike and 0 regular bikes
        )

        for station in stations_by_distance:
            if ebike_station is None and station.num_ebikes > 0:
                ebike_station = station
            if bike_station is None and station.num_bikes > 0:
                bike_station = station
            if (
                free_station is None
                and station.num_ebikes > 0
                and station.num_bikes == 0
            ):
                free_station = station

            # Stop early if we found all three
            if ebike_station and bike_station and free_station:
                break

        # Step 4: Deduplicate and create results
        unique_stations = []
        if ebike_station:
            unique_stations.append(ebike_station)
        if bike_station and bike_station is not ebike_station:
            unique_stations.append(bike_station)
        if free_station and free_station is not ebike_station:
            # free_station will never equal bike_station, they are mutually exclusive
            unique_stations.append(free_station)

        # Step 5: Get addresses and distances for unique stations
        results = []
        for station in unique_stations:
            address = await ctx.deps.reverse_geocode(station.lat, station.lon)
            distance = euclidean_distance(lat, lon, station.lat, station.lon)
            distance_miles = distance * 69.0  # 1 degree ~= 69 miles

            results.append(
                CitiBikeStationResult(
                    address=address,
                    num_bikes=station.num_bikes,
                    num_ebikes=station.num_ebikes,
                    distance_miles=round(distance_miles, 2),
                )
            )

        return results
