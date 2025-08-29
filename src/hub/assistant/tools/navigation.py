from typing import Literal
from pydantic_ai import Agent
from pydantic_ai.tools import RunContext
from assistant.dependencies import AssistantDependencies
import clients.valhalla as valhalla_client


def register_navigation_tool(agent: Agent[AssistantDependencies, str]) -> None:
    """Register navigation tool on the agent."""
    
    @agent.tool
    async def navigate(
        ctx: RunContext[AssistantDependencies],
        start: str,
        destination: str,
        mode: Literal["drive", "walk", "bike", "transit"] = "drive",
    ) -> str:
        """Returns turn-by-turn navigation directions between two locations formatted as JSON."""
        # Geocode the start and destination locations
        start_coords = await ctx.deps.geocode(start)
        dest_coords = await ctx.deps.geocode(destination)

        # Get directions
        directions = await valhalla_client.directions(
            ctx.deps.valhalla_client, start_coords, dest_coords, mode
        )

        return directions.model_dump_json()
